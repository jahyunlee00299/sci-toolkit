"""Lint rules (schema section 4, rules 1-7). One small function per rule."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, NamedTuple

from .baseline import baseline_for
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

    @property
    def records(self) -> list[Record]:
        return self.index.records


def rule1_closed_append_only(ctx: Context) -> list[Violation]:
    base = baseline_for(ctx.root)
    return [Violation(1, r.key, msg) for r in ctx.records for msg in base.check(r)]


def rule2_references_resolve(ctx: Context) -> list[Violation]:
    out = [Violation(2, r.key, f"duplicate id (also at {ctx.index.by_key[r.key].rel})")
           for r in ctx.index.duplicates]
    for r in ctx.records:
        if r.type == "exp" and not r.fm.get("protocol"):
            out.append(Violation(2, r.key, "protocol is missing"))
        for item in as_list(r.fm.get("links")):
            if not isinstance(item, dict):
                out.append(Violation(2, r.key, f"links entry is not a mapping: {item!r}"))
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


def _missing(root: Path, rel) -> bool:
    try:
        p = Path(str(rel)).expanduser()
        return not (p if p.is_absolute() else root / p).exists()  # existence only, never stat mtime
    except OSError:
        return True


def rule7_paths_exist(ctx: Context) -> list[Violation]:
    out = []
    for r in ctx.records:
        for p in as_list(r.fm.get("raw_data")):
            if _missing(ctx.root, p):
                out.append(Violation(7, r.key, f"raw_data path does not exist: {p}"))
        for item in as_list(r.fm.get("links")):
            if isinstance(item, dict) and item.get("path") and _missing(ctx.root, item["path"]):
                out.append(Violation(7, r.key, f"legacy link path does not exist: {item['path']}"))
    return out


RULES: list[Callable[[Context], list[Violation]]] = [
    rule1_closed_append_only, rule2_references_resolve, rule3_prot_pinned, rule4_no_orphans,
    rule5_checklist_values, rule6_people_keys, rule7_paths_exist,
]


def run_all(ctx: Context) -> list[Violation]:
    out = [v for rule in RULES for v in rule(ctx)]
    return sorted(out, key=lambda v: (v.rule, v.id, v.msg))
