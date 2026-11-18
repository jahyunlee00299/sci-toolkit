"""Batch gate: run every claim in a bio_claims.toml against the live public databases.

    bio_const.py check bio_claims.toml

Claim kinds (one [[claim]] table each):
    compare: source (uniprot|pdb), id, field, claimed, unit, rtol (default 0.01)
    thermo : reaction, pH, ionic_strength, temperature, pMg, claimed_keq, rtol (default 0.05),
             source (web|package, default web)
Exit contract (verification-gates): 1 if any claim MISMATCHes, else 2 if any claim is BLIND or the
file declares no claims (checked nothing is never a pass), else 0.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

from . import compare as cmp
from . import thermo
from .errors import BlindError


def _fetch(source: str, ident: str) -> dict:
    from . import pdb, uniprot
    return uniprot.fetch(ident) if source == "uniprot" else pdb.fetch(ident)


def _compare(c: dict, fetch=_fetch) -> cmp.Verdict:
    need = ("source", "id", "field", "claimed", "unit")
    missing = [k for k in need if k not in c]
    if missing:
        return cmp.Verdict("BLIND", f"BLIND claim={c.get('name', '?')} missing={missing}", 2)
    try:
        rec = fetch(c["source"], c["id"])
    except BlindError as e:
        return cmp.Verdict("BLIND", f"BLIND source={c['source']} id={c['id']} field={c['field']} reason={e}", 2)
    return cmp.compare(c["source"], c["id"], c["field"], rec, str(c["claimed"]), c["unit"],
                       float(c.get("rtol", 0.01)))


def _thermo(c: dict, dg_fn=None) -> cmp.Verdict:
    need = ("reaction", "pH", "ionic_strength", "temperature", "pMg", "claimed_keq")
    missing = [k for k in need if k not in c]
    if missing:
        return cmp.Verdict("BLIND", f"BLIND claim={c.get('name', '?')} missing={missing}", 2)
    cond = thermo.Conditions(float(c["pH"]), float(c["ionic_strength"]), float(c["temperature"]), float(c["pMg"]))
    src = c.get("source", "web")
    fn = dg_fn or (thermo.web_dg if src == "web" else thermo.package_dg)
    try:
        res = fn(c["reaction"], cond)
    except BlindError as e:
        return cmp.Verdict("BLIND", f"BLIND source={src} reaction=\"{c['reaction']}\" {cond.tag()} reason={e}", 2)
    live = thermo.keq_from_dg(res["dg"], cond.temperature_K)
    rtol = float(c.get("rtol", 0.05))
    claimed = float(c["claimed_keq"])
    rel = (claimed - live) / live
    ok = abs(rel) <= rtol
    band = (thermo.keq_from_dg(res["dg"] + res["err"], cond.temperature_K),
            thermo.keq_from_dg(res["dg"] - res["err"], cond.temperature_K))
    inside = band[0] <= claimed <= band[1]
    word = "MATCH" if ok else "MISMATCH"
    return cmp.Verdict(word, f"{word} claimed_keq={claimed:g} live_keq={live:.4g} rel_diff={rel:+.2%} "
                       f"rtol={rtol:g} within_1sigma_band={'yes' if inside else 'no'} source={src} {cond.tag()}",
                       0 if ok else 1)


def run(path: str | Path, fetch=_fetch, dg_fn=None) -> tuple[int, list[str]]:
    try:
        data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as e:
        return 2, [f"BLIND cannot read claims file: {type(e).__name__}"]
    claims = data.get("claim") or []
    if not claims:
        return 2, ["BLIND no [[claim]] declared: nothing was checked"]
    lines, codes = [], []
    for c in claims:
        v = _thermo(c, dg_fn) if "reaction" in c else _compare(c, fetch)
        lines.append(f"[{c.get('name', '?')}] {v.line}" + (f"  # {c['note']}" if c.get("note") else ""))
        codes.append(v.code)
    final = 1 if 1 in codes else 2 if 2 in codes else 0
    lines.append(f"SUMMARY claims={len(codes)} match={codes.count(0)} mismatch={codes.count(1)} blind={codes.count(2)} exit={final}")
    return final, lines
