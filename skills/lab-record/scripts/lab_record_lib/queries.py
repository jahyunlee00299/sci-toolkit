"""Read-only lineage queries: trace (upstream), impact (downstream), open (loose ends)."""
from __future__ import annotations

from pathlib import Path

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


def trace(index: Index, ref: str, root: Path) -> list[str]:
    rec = index.get(ref, latest_ok=True)
    if rec is None:
        raise KeyError(ref)
    lines: list[str] = []

    def walk(r: Record, depth: int, seen: frozenset):
        pad = "  " * depth + ("<- " if depth else "")
        lines.append(pad + _label(r))
        if r.type == "exp":
            for p in as_list(r.fm.get("raw_data")):
                lines.append("  " * (depth + 1) + f"raw_data: {(root / str(p)).as_posix() if not Path(str(p)).is_absolute() else p}")
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
