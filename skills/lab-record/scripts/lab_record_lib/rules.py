"""Lint rules (schema section 4, rules 1-9). One small function per rule."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, NamedTuple

from .baseline import baseline_for
from . import catalog as cat
from . import chem
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


def _ref(ctx: Context, owner: cat.Entry, field_: str, kind: str, name) -> list[Violation]:
    if ctx.catalog.resolve(kind, name) is None:
        return [Violation(12, "catalog", f"{owner.label} {field_} {name!r} is not a {kind} in the catalog")]
    return []


def rule12_catalog_references(ctx: Context) -> list[Violation]:
    """Names inside catalog entries must resolve (aliases count; `related` is not an alias)."""
    out: list[Violation] = []
    if not ctx.catalog:
        return out
    for e in ctx.catalog.entries:
        d = e.data
        for rel in d.get("related", []):
            out += _ref(ctx, e, "related", e.kind, rel["name"])
        if e.kind == "enzyme":
            out += [v for n in d.get("catalyzes", []) for v in _ref(ctx, e, "catalyzes", "reaction", n)]
            out += [v for n in d.get("cofactor", []) for v in _ref(ctx, e, "cofactor", "compound", n)]
        elif e.kind == "compound":
            out += [v for n in d.get("regenerated_by", []) for v in _ref(ctx, e, "regenerated_by", "reaction", n)]
        elif e.kind == "reaction":
            if d.get("enzyme"):
                out += _ref(ctx, e, "enzyme", "enzyme", d["enzyme"])
            for key in ("substrates", "products"):
                out += [v for p in d.get(key, []) for v in _ref(ctx, e, key, "compound", p["name"])]
            for c in d.get("cofactors", []):
                out += _ref(ctx, e, "cofactors", "compound", c["name"])
                out += _ref(ctx, e, "cofactors.to", "compound", c["to"])
    return out


def _reaction_sides(ctx: Context, rd, e: cat.Entry):
    """((left, right), missing). Each side item = (coef, counts, charge); `missing` lists
    participants that cannot be resolved or have no (parsable) SMILES. None when unresolved."""
    left, right, missing = [], [], []

    def add(side, name, coef):
        comp = ctx.catalog.resolve("compound", name)
        mol = chem.parse(rd, comp.data["smiles"]) if comp and comp.data.get("smiles") else None
        if mol is None:
            missing.append(str(name))
            return
        counts, charge = chem.composition(rd, mol)
        side.append((coef, counts, charge))

    d = e.data
    for p in d.get("substrates", []):
        add(left, p["name"], p.get("coef", 1))
    for p in d.get("products", []):
        add(right, p["name"], p.get("coef", 1))
    for c in d.get("cofactors", []):
        add(left, c["name"], c.get("coef", 1))
        add(right, c["to"], c.get("coef", 1))
    return (left, right), missing


def rule13_catalog_chemistry(ctx: Context) -> list[Violation]:
    """SMILES parses, InChIKey/formula match it, reactions are element-balanced. Needs RDKit;
    without it nothing here runs and `blind_notes` says so (never a silent pass)."""
    out: list[Violation] = []
    rd = chem.load_rdkit()
    if rd is None or not ctx.catalog:
        return out
    for e in ctx.catalog.entries:
        d = e.data
        if e.kind == "compound" and d.get("smiles"):
            mol = chem.parse(rd, d["smiles"])
            if mol is None:
                out.append(Violation(13, "catalog", f"{e.label} smiles does not parse: {d['smiles']}"))
                continue
            key = d.get("inchikey")
            if key and key.strip().upper() != chem.inchikey(rd, mol):
                out.append(Violation(13, "catalog", f"{e.label} inchikey {key} does not match its smiles "
                                                    f"(RDKit: {chem.inchikey(rd, mol)})"))
            if d.get("formula"):
                got = chem.hill_formula(chem.composition(rd, mol)[0])
                if d["formula"].replace(" ", "") != got:
                    out.append(Violation(13, "catalog", f"{e.label} formula {d['formula']} does not match its "
                                                        f"smiles (RDKit: {got})"))
        elif e.kind == "reaction" and (d.get("substrates") or d.get("products")):
            (left, right), missing = _reaction_sides(ctx, rd, e)
            if not missing:
                problem = chem.balance_problem(left, right)
                if problem:
                    out.append(Violation(13, "catalog", f"{e.label} is not element-balanced: {problem}"))
    return out


def blind_notes(ctx: Context) -> list[str]:
    """Checks that could not run, as `BLIND ...` lines (stderr, exit code unchanged)."""
    notes: list[str] = []
    if not ctx.catalog:
        return notes
    n_smiles = sum(1 for e in ctx.catalog.entries if e.kind == "compound" and e.data.get("smiles"))
    n_rxn = [e for e in ctx.catalog.entries if e.kind == "reaction" and (e.data.get("substrates") or e.data.get("products"))]
    rd = chem.load_rdkit()
    if rd is None:
        if n_smiles:
            notes.append(f"BLIND rdkit is not importable: smiles/inchikey/formula of {n_smiles} compound(s) NOT checked")
        if n_rxn:
            notes.append(f"BLIND rdkit is not importable: element balance of {len(n_rxn)} reaction(s) NOT checked")
        return notes
    for e in n_rxn:
        _, missing = _reaction_sides(ctx, rd, e)
        if missing:
            notes.append(f"BLIND {e.label} element balance not checked: no usable smiles for {', '.join(missing)}")
    return notes


RULES: list[Callable[[Context], list[Violation]]] = [
    rule1_closed_append_only, rule2_references_resolve, rule3_prot_pinned, rule4_no_orphans,
    rule5_checklist_values, rule6_people_keys, rule7_paths_exist,
    rule8_duplicates_and_conflict_copies, rule9_catalog_paths,
    rule12_catalog_references, rule13_catalog_chemistry,  # 10-11 live in the lab repo only
]


def run_all(ctx: Context) -> list[Violation]:
    out = [v for rule in RULES for v in rule(ctx)]
    return sorted(out, key=lambda v: (v.rule, v.id, v.msg))
