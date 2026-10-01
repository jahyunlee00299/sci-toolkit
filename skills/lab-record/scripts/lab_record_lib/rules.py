"""Lint rules (schema section 4, rules 1-9). One small function per rule."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, NamedTuple

from .baseline import baseline_for
from . import catalog as cat
from . import paths
from .config import is_digits
from .model import BARE_PROT, Index, Record, as_list, iter_refs

CHECKLIST_VALUES = ("ok", "unknown", "n/a")


class Violation(NamedTuple):
    rule: int
    id: str
    msg: str

    def __str__(self) -> str:
        return f"RULE{self.rule} {self.id} {self.msg}"


@dataclass
class Context:
    root: Path
    people: dict
    index: Index
    projects: dict = field(default_factory=dict)
    catalog: cat.Catalog | None = None

    @property
    def records(self) -> list[Record]:
        return self.index.records


def rule1_closed_append_only(ctx: Context) -> list[Violation]:
    base = baseline_for(ctx.root)
    return [Violation(1, r.key, msg) for r in ctx.records for msg in base.check(r)]


def _check_catalog_link(ctx: "Context", r: Record, item: dict) -> list[Violation]:
    rel, name = item["rel"], item.get("name")
    if not name:
        return [Violation(2, r.key, f"links {rel} entry needs `name` (catalog name or alias)")]
    entry = ctx.catalog.resolve(rel, name) if ctx.catalog else None
    if entry is None:
        return [Violation(2, r.key, f"links {rel} name {name!r} is not in the catalog")]
    problem = ctx.catalog.path_problem(entry)
    if problem:
        return [Violation(2, r.key, f"links {rel} {name!r}: catalog path of {entry.label} {problem}: {entry.path}")]
    return []


def _check_link(ctx: "Context", r: Record, item) -> list[Violation]:
    """Format checks of one links[] item (id resolution happens via iter_refs)."""
    if not isinstance(item, dict):
        return [Violation(2, r.key, f"links entry is not a mapping: {item!r}")]
    out, rel = [], item.get("rel")
    gids = [(k, item[k]) for k in ("task", "project") if k in item]
    for k, v in gids:
        if not is_digits(v):
            out.append(Violation(2, r.key, f"links {rel} {k} {v!r} is not digits only"))
    if rel in cat.KINDS:
        out += _check_catalog_link(ctx, r, item)
    elif rel == "asana" and not gids:
        out.append(Violation(2, r.key, "links asana entry needs `task` or `project` (digits)"))
    elif not any(item.get(k) for k in ("id", "path")) and not gids:
        out.append(Violation(2, r.key, f"links entry (rel {rel!r}) has no id, path, task or project"))
    return out


def rule2_references_resolve(ctx: Context) -> list[Violation]:
    out = []
    for r in ctx.records:
        if r.type == "exp" and not r.fm.get("protocol"):
            out.append(Violation(2, r.key, "protocol is missing"))
        for item in as_list(r.fm.get("links")):
            out += _check_link(ctx, r, item)
        for fld, ref in iter_refs(r):
            if BARE_PROT.match(ref):
                continue  # reported by rule 3
            if ctx.index.get(ref) is None:
                out.append(Violation(2, r.key, f"{fld} reference {ref} does not resolve"))
    return out


def rule3_prot_pinned(ctx: Context) -> list[Violation]:
    return [Violation(3, r.key, f"{fld} reference {ref} is not version-pinned (use {ref}@vN)")
            for r in ctx.records for fld, ref in iter_refs(r) if BARE_PROT.match(ref)]


def rule4_no_orphans(ctx: Context) -> list[Violation]:
    out = []
    for r in ctx.records:
        if r.type == "disc" and not as_list(r.fm.get("about")):
            out.append(Violation(4, r.key, "orphan DISC: `about` is empty"))
        if r.type == "dec" and not as_list(r.fm.get("from")):
            out.append(Violation(4, r.key, "orphan DEC: `from` is empty"))
    return out


def rule5_checklist_values(ctx: Context) -> list[Violation]:
    out = []
    for r in ctx.records:
        cl = r.fm.get("context_checklist")
        if cl is None:
            continue
        if not isinstance(cl, dict):
            out.append(Violation(5, r.key, "context_checklist must be a mapping"))
            continue
        for k, v in cl.items():
            if not (isinstance(v, str) and v in CHECKLIST_VALUES):
                out.append(Violation(5, r.key, f"context_checklist.{k}={v!r} (allowed: ok | unknown | n/a)"))
    return out


def rule6_people_keys(ctx: Context) -> list[Violation]:
    out = []
    for r in ctx.records:
        owner = r.fm.get("owner")
        if owner not in ctx.people:
            out.append(Violation(6, r.key, f"owner {owner!r} is not a key in the people map"))
        for p in as_list(r.fm.get("participants")):
            if p not in ctx.people:
                out.append(Violation(6, r.key, f"participant {p!r} is not a key in the people map"))
    return out


def rule7_paths_exist(ctx: Context) -> list[Violation]:
    out = []
    for r in ctx.records:
        for label, raw in paths.iter_path_values(r):
            p, problem = paths.resolve(ctx.root, ctx.projects, r.fm.get("project"), raw)
            if problem:
                out.append(Violation(7, r.key, f"{label} path {raw}: {problem}"))
            elif not paths.exists(p):
                out.append(Violation(7, r.key, f"{label} path does not exist: {raw}"))
    return out


def rule8_duplicates_and_conflict_copies(ctx: Context) -> list[Violation]:
    out = []
    for r in ctx.index.duplicates:
        first = ctx.index.by_key[r.key]
        out.append(Violation(8, r.key, f"duplicate id in {first.rel}, {r.rel}"))
    for r in ctx.records:
        if r.path.stem != r.canonical_stem:
            out.append(Violation(8, r.rel, "filename does not match its id (sync-conflict copy?)"))
    return out


def rule9_catalog_paths(ctx: Context) -> list[Violation]:
    out = []
    for e in (ctx.catalog.entries if ctx.catalog else []):
        problem = ctx.catalog.path_problem(e)
        if problem:
            extra = "" if problem == "does not exist" else f" ({problem})"
            out.append(Violation(9, "catalog", f"{e.label} path missing: {e.path}{extra}"))
    return out


RULES: list[Callable[[Context], list[Violation]]] = [
    rule1_closed_append_only, rule2_references_resolve, rule3_prot_pinned, rule4_no_orphans,
    rule5_checklist_values, rule6_people_keys, rule7_paths_exist,
    rule8_duplicates_and_conflict_copies, rule9_catalog_paths,
]


def run_all(ctx: Context) -> list[Violation]:
    out = [v for rule in RULES for v in rule(ctx)]
    return sorted(out, key=lambda v: (v.rule, v.id, v.msg))
