"""Optional RDKit helpers for catalog chemistry checks. RDKit missing -> callers report BLIND."""
from __future__ import annotations

from collections import Counter

BALANCED_ELEMENTS = ("C", "H", "O", "N", "P")


def load_rdkit():
    """Return (Chem, inchi) or None when RDKit is not importable (tests monkeypatch this)."""
    try:
        from rdkit import Chem, RDLogger
        from rdkit.Chem import inchi
    except ImportError:
        return None
    RDLogger.DisableLog("rdApp.*")
    return Chem, inchi


def parse(rd, smiles: str):
    """Mol or None."""
    return rd[0].MolFromSmiles(smiles)


def inchikey(rd, mol) -> str:
    return rd[1].MolToInchiKey(mol)


def composition(rd, mol) -> tuple[Counter, int]:
    """(element counts with implicit H made explicit, net formal charge)."""
    full = rd[0].AddHs(mol)
    counts = Counter(a.GetSymbol() for a in full.GetAtoms())
    return counts, sum(a.GetFormalCharge() for a in full.GetAtoms())


def hill_formula(counts: Counter) -> str:
    order = [e for e in ("C", "H") if e in counts] + sorted(e for e in counts if e not in ("C", "H"))
    return "".join(e + (str(counts[e]) if counts[e] > 1 else "") for e in order)


def balance_problem(side_left: list[tuple[float, Counter, int]],
                    side_right: list[tuple[float, Counter, int]]) -> str | None:
    """None when balanced. Items are (coef, counts, charge). C, O, N, P must match exactly; H must
    match up to the protons the reaction implicitly exchanges, i.e. delta H == delta charge."""
    def total(items):
        t, q = Counter(), 0.0
        for coef, counts, charge in items:
            for el in BALANCED_ELEMENTS:
                t[el] += coef * counts.get(el, 0)
            q += coef * charge
        return t, q
    (lt, lq), (rt, rq) = total(side_left), total(side_right)
    bad = [f"{el} {lt[el]:g}->{rt[el]:g}" for el in BALANCED_ELEMENTS
           if el != "H" and abs(lt[el] - rt[el]) > 1e-9]
    dh, dq = rt["H"] - lt["H"], rq - lq
    if abs(dh - dq) > 1e-9:
        bad.append(f"H {lt['H']:g}->{rt['H']:g} with charge {lq:+g}->{rq:+g} (H gain must equal charge gain)")
    return "; ".join(bad) or None
