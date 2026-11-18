"""CLI: key-less lookup and claimed-vs-live reconciliation of biochemical constants.

    bio_const.py uniprot P33160 [--field mass|length|ec|organism|...] [--json]
    bio_const.py pdb 2NAD [--json]
    bio_const.py compare --source uniprot --id P33160 --field mass --claimed 41000 --unit Da
    bio_const.py check bio_claims.toml   (batch gate, exit 1 mismatch / 2 blind / 0 all match)
    bio_const.py rhea --rhea RHEA:21432 | --ec 1.1.1.37
    bio_const.py thermo --reaction "A + B = C" --pH 7.5 --ionic-strength 0.25 --temperature 298.15 \
        --pMg 3.0 [--source web|package] [--claimed-keq 2.28e-5 --rtol 0.05]
Exit: 0 pass / 1 fail / 2 BLIND (network, API failure, ambiguous record, bad unit).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):                      # direct script run
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "biodb"

from . import compare as cmp  # noqa: E402
from . import pdb, rhea, thermo, uniprot  # noqa: E402
from .errors import BlindError  # noqa: E402

FIELD_UNITS = {"mass": "Da", "mature_mass": "Da", "length": "aa", "taxon": "id"}


def _fetch(source: str, ident: str) -> dict:
    return uniprot.fetch(ident) if source == "uniprot" else pdb.fetch(ident)


def _print_record(rec: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(rec, ensure_ascii=False, indent=2))
        return
    for k, v in rec.items():
        print(f"{k}: {v}")


def cmd_lookup(source: str, a) -> int:
    rec = _fetch(source, a.id)
    field = getattr(a, "field", None)
    if field:
        val = cmp.live_value(source, rec, field)
        unit = FIELD_UNITS.get(field, "")
        print(f"{val:g} {unit}".strip() if isinstance(val, float) else val)
    else:
        _print_record(rec, a.json)
    return 0


def cmd_compare(a) -> int:
    try:
        rec = _fetch(a.source, a.id)
    except BlindError as e:
        v = cmp.Verdict("BLIND", f"BLIND source={a.source} id={a.id} field={a.field} reason={e}", 2)
    else:
        v = cmp.compare(a.source, a.id, a.field, rec, a.claimed, a.unit, a.rtol)
    print(v.line)
    return v.code


def cmd_rhea(a) -> int:
    for r in rhea.fetch(a.rhea, a.ec):
        print(" | ".join(f"{k}={v}" for k, v in r.items()))
    return 0


def cmd_thermo(a) -> int:
    cond = thermo.Conditions(a.pH, a.ionic_strength, a.temperature, a.pMg)
    try:
        res = (thermo.web_dg if a.source == "web" else thermo.package_dg)(a.reaction, cond)
    except BlindError as e:
        print(f"BLIND source={a.source} reaction=\"{a.reaction}\" {cond.tag()} reason={e}")
        return 2
    print(thermo.format_result(a.source, a.reaction, res["dg"], res["err"], cond))
    if a.claimed_keq is None:
        return 0
    live = thermo.keq_from_dg(res["dg"], cond.temperature_K)
    rel = (a.claimed_keq - live) / live
    ok = abs(rel) <= a.rtol
    band = (thermo.keq_from_dg(res["dg"] + res["err"], cond.temperature_K),
            thermo.keq_from_dg(res["dg"] - res["err"], cond.temperature_K))
    inside = band[0] <= a.claimed_keq <= band[1]
    print(f"{'MATCH' if ok else 'MISMATCH'} claimed_keq={a.claimed_keq:g} live_keq={live:.4g} "
          f"rel_diff={rel:+.2%} rtol={a.rtol:g} within_1sigma_band={'yes' if inside else 'no'} "
          f"{cond.tag()}")
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bio_const", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    u = sub.add_parser("uniprot")
    u.add_argument("id")
    u.add_argument("--field", choices=["mass", "mature_mass", "length", "ec", "organism",
                                       "taxon", "name", "gene"])
    u.add_argument("--json", action="store_true")
    d = sub.add_parser("pdb")
    d.add_argument("id")
    d.add_argument("--field", choices=["resolution", "method", "uniprot", "ligand"])
    d.add_argument("--json", action="store_true")
    h = sub.add_parser("rhea")
    h.add_argument("--rhea")
    h.add_argument("--ec")
    t = sub.add_parser("thermo")
    t.add_argument("--reaction", required=True)
    for flag, typ in (("--pH", float), ("--ionic-strength", float), ("--temperature", float),
                      ("--pMg", float)):
        t.add_argument(flag, type=typ, required=True)    # no defaults: conditions are explicit
    t.add_argument("--source", choices=["web", "package"], default="web")
    t.add_argument("--claimed-keq", type=float)
    t.add_argument("--rtol", type=float, default=0.05)
    k = sub.add_parser("check")
    k.add_argument("claims", help="bio_claims.toml with [[claim]] tables")
    c = sub.add_parser("compare")
    c.add_argument("--source", required=True, choices=["uniprot", "pdb"])
    c.add_argument("--id", required=True)
    c.add_argument("--field", required=True)
    c.add_argument("--claimed", required=True)
    c.add_argument("--unit", help="Da|kDa (mass), aa (length), A|nm (resolution); never guessed")
    c.add_argument("--rtol", type=float, default=0.01)
    return p


def main(argv=None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    a = build_parser().parse_args(argv)
    try:
        if a.cmd == "compare":
            return cmd_compare(a)
        if a.cmd == "check":
            from . import check
            code, lines = check.run(a.claims)
            print(chr(10).join(lines))
            return code
        if a.cmd == "rhea":
            return cmd_rhea(a)
        if a.cmd == "thermo":
            return cmd_thermo(a)
        return cmd_lookup(a.cmd, a)
    except BlindError as e:
        print(f"BLIND reason={e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
