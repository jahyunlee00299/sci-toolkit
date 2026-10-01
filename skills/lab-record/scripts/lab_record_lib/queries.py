"""Read-only lineage queries: trace (upstream), impact (downstream), open (loose ends)."""
from __future__ import annotations

from pathlib import Path

from . import catalog as catmod
from . import paths
from .model import Index, Record, as_list


def _upstream_refs(rec: Record) -> list[str]:
    if rec.type == "dec":
        return [str(x) for x in as_list(rec.fm.get("from"))]
    if rec.type == "disc":
        return [str(x) for x in as_list(rec.fm.get("about"))]
    if rec.type == "exp" and rec.fm.get("protocol"):
        return [str(rec.fm["protocol"])]
    return []


def _label(rec: Record) -> str:
    return f"{rec.key} [{rec.status}] {rec.fm.get('title', '')}"


def trace(index: Index, ref: str, root: Path, projects: dict | None = None) -> list[str]:
    rec = index.get(ref, latest_ok=True)
    if rec is None:
        raise KeyError(ref)
    lines: list[str] = []

    def walk(r: Record, depth: int, seen: frozenset):
        pad = "  " * depth + ("<- " if depth else "")
        lines.append(pad + _label(r))
        if r.type == "exp":
            for p in as_list(r.fm.get("raw_data")):
                full, _ = paths.resolve(root, projects or {}, r.fm.get("project"), p)
                shown = (full.as_posix() if full is not None else str(p))
                lines.append("  " * (depth + 1) + f"raw_data: {shown}")
        for up in _upstream_refs(r):
            target = index.get(up)
            if target is None:
                lines.append("  " * (depth + 1) + f"<- {up} (UNRESOLVED)")
            elif target.key not in seen:
                walk(target, depth + 1, seen | {r.key})

    walk(rec, 0, frozenset())
    return lines


def impact(index: Index, ref: str) -> list[str]:
    prot = index.get(ref)
    if prot is None or prot.type != "prot":
        raise KeyError(ref)
    exps = [r for r in index.of_type("exp") if str(r.fm.get("protocol")) == prot.key]
    exp_keys = {r.key for r in exps}
    discs = [r for r in index.of_type("disc")
             if {str(a) for a in as_list(r.fm.get("about"))} & (exp_keys | {prot.key})]
    disc_keys = {r.key for r in discs}
    decs = [r for r in index.of_type("dec")
            if {str(a) for a in as_list(r.fm.get("from"))} & disc_keys]
    out = [f"impact of {prot.key}: {len(exps)} EXP, {len(discs)} DISC, {len(decs)} DEC"]
    for title, group in (("EXP", exps), ("DISC", discs), ("DEC", decs)):
        out += [f"{title} {_label(r)}" for r in group]
    return out


def open_items(index: Index) -> list[str]:
    out = []
    for r in index.of_type("disc"):
        qs = [str(q) for q in as_list(r.fm.get("open_questions")) if str(q).strip()]
        if qs:
            out.append(f"DISC {r.key} open_questions: " + " | ".join(qs))
    for r in index.of_type("dec"):
        if str(r.fm.get("revisit_if") or "").strip():
            out.append(f"DEC {r.key} revisit_if: {r.fm['revisit_if']}")
    discussed = {str(a) for d in index.of_type("disc") for a in as_list(d.fm.get("about"))}
    for r in index.of_type("exp"):
        if r.key not in discussed:
            out.append(f"EXP {r.key} not discussed: {r.fm.get('title', '')}")
    return out


def uses(index: Index, cat: catmod.Catalog, name: str) -> list[str]:
    """Records linking a catalog entry (aliases resolve) + PROT -> its EXPs, EXP -> its DISCs."""
    entries = cat.find(name)
    if not entries:
        raise KeyError(name)
    out: list[str] = []
    for e in entries:
        direct = catmod.users_of(index.records, cat, e)
        seen = {r.key for r in direct}
        via: list[tuple[Record, Record]] = []
        queue = list(direct)
        while queue:
            src = queue.pop(0)
            if src.type == "prot":
                nxt = [r for r in index.of_type("exp") if str(r.fm.get("protocol")) == src.key]
            elif src.type == "exp":
                nxt = [r for r in index.of_type("disc")
                       if src.key in {str(a) for a in as_list(r.fm.get("about"))}]
            else:
                nxt = []
            for r in nxt:
                if r.key not in seen:
                    seen.add(r.key)
                    via.append((r, src))
                    queue.append(r)
        out.append(f"uses {e.label}: {len(direct)} direct, {len(via)} via lineage")
        out += [f"DIRECT {_label(r)}" for r in direct]
        out += [f"VIA {_label(r)} (through {src.key})" for r, src in via]
    return out


def catalog_table(index: Index, cat: catmod.Catalog, kind: str | None = None) -> list[str]:
    rows = [e for e in cat.entries if kind in (None, e.kind)]
    if not rows:
        return ["catalog is empty" + (f" for kind {kind}" if kind else "")]
    out = ["kind\tname\tproject\tpath\texists\tused_by"]
    for e in rows:
        full, problem = cat.full_path(e)
        shown = full.as_posix() if full is not None else f"(unresolved: {problem})"
        ok = "yes" if cat.path_problem(e) is None else "no"
        out.append("\t".join([e.kind, e.name, e.project or "-", shown, ok,
                              str(len(catmod.users_of(index.records, cat, e)))]))
    return out
