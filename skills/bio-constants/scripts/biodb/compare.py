"""Claimed-vs-live comparison. Pure functions; exit codes follow the gate contract.

0 = MATCH, 1 = MISMATCH, 2 = BLIND (cannot decide; never a silent pass).
Units are explicit and never guessed: a numeric field needs a unit from its own table.
"""
from __future__ import annotations

from dataclasses import dataclass

from .errors import BlindError

# field -> (unit table to the base unit, base unit label)
NUMERIC = {
    ("uniprot", "mass"): ({"Da": 1.0, "kDa": 1000.0}, "Da"),
    ("uniprot", "mature_mass"): ({"Da": 1.0, "kDa": 1000.0}, "Da"),
    ("uniprot", "length"): ({"aa": 1.0}, "aa"),
    ("uniprot", "taxon"): ({"id": 1.0}, "id"),
    ("pdb", "resolution"): ({"A": 1.0, "nm": 10.0}, "A"),
}
TEXT = {("uniprot", "ec"), ("uniprot", "organism"), ("uniprot", "name"), ("uniprot", "gene"),
        ("pdb", "method"), ("pdb", "uniprot"), ("pdb", "ligand")}


@dataclass
class Verdict:
    verdict: str            # MATCH | MISMATCH | BLIND
    line: str
    code: int


def live_value(source: str, rec: dict, field: str):
    """Extract one comparable live value (base unit for numerics, list[str] for text)."""
    if rec.get("status") == "inactive":
        raise BlindError(f"{rec['accession']} is {rec['reason']}; merged_to={rec.get('merged_to')} "
                         "(re-run with the new accession, not followed automatically)")
    if source == "uniprot":
        if field == "mass":
            return float(rec["mass_da"])
        if field == "mature_mass":
            ch = rec["chains"]
            if len(ch) != 1 or ch[0]["mass_da_computed"] is None:
                raise BlindError(f"mature_mass ambiguous: {len(ch)} Chain feature(s)")
            return float(ch[0]["mass_da_computed"])
        if field == "length":
            return float(rec["length"])
        if field == "taxon":
            return float(rec["taxon_id"])
        if field == "ec":
            return rec["ec"]
        if field == "organism":
            return [rec["organism"]]
        if field == "name":
            return [rec["name"] or ""]
        if field == "gene":
            return [rec["gene"] or ""]
    if source == "pdb":
        if field == "resolution":
            if rec["resolution_a"] is None:
                raise BlindError("no resolution recorded (NMR or unresolved entry)")
            return float(rec["resolution_a"])
        if field == "method":
            return rec["method"]
        if field == "uniprot":
            return [u for p in rec["polymers"] for u in p["uniprot"]]
        if field == "ligand":
            return [lig["comp_id"] for lig in rec["ligands"]]
    raise BlindError(f"unsupported field '{field}' for source '{source}'")


def compare(source: str, ident: str, field: str, rec: dict, claimed: str,
            unit: str | None, rtol: float) -> Verdict:
    head = f"source={source} id={ident} field={field}"
    key = (source, field)
    try:
        live = live_value(source, rec, field)
        if key in NUMERIC:
            table, base = NUMERIC[key]
            if unit not in table:
                raise BlindError(f"unit required for {field}: one of {sorted(table)} (got {unit!r})")
            cl = float(claimed) * table[unit]
            rel = (cl - live) / live
            ok = abs(rel) <= rtol
            v = "MATCH" if ok else "MISMATCH"
            line = (f"{v} {head} live={live:g} {base} claimed={cl:g} {base} "
                    f"(input {claimed} {unit}) rel_diff={rel:+.3%} rtol={rtol:g}")
            note = "; ".join(rec.get("notes", [])) if source == "uniprot" else ""
            if note:
                line += f" note={note}"
            return Verdict(v, line, 0 if ok else 1)
        if key in TEXT:
            want = claimed.strip().lower()
            ok = any(want == x.lower() for x in live)
            v = "MATCH" if ok else "MISMATCH"
            return Verdict(v, f"{v} {head} live={live} claimed={claimed!r}", 0 if ok else 1)
        raise BlindError(f"unsupported field '{field}' for source '{source}'")
    except (BlindError, ValueError) as e:
        return Verdict("BLIND", f"BLIND {head} reason={e}", 2)
