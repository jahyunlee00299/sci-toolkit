#!/usr/bin/env python
"""Translate the protein a plasmid actually expresses and compute its mass.

A molecular weight quoted for a protein is usually the native sequence alone.
The band on a gel is the whole fusion: an expression vector adds a leader (in
pET-28a, MGSSHHHHHHSSGLVPRGSHMASMTGGQQMGRGS, 34 aa, ~3.5 kDa) that a native-only
number leaves out, so a 35.9 kDa enzyme runs near 39 kDa. This script reads the
construct from the map and reports both, instead of relying on a recalled figure.

The reading frame is anchored at a named feature (default "T7 promoter") and the
ORF starts at the first ATG downstream of it. It does NOT pick the longest ORF in
the plasmid: in pET-28a lacI (360 aa) is longer than many inserts, so "longest
ORF" silently reports the wrong protein. With no anchor and no --start-pos the
script refuses rather than guesses.

Usage
-----
    python construct_mw.py MAP.dna --native-start MPSIKL \\
        --mutate E223A --mutate S271A

    --native-start  first residues of the NATIVE protein (as it appears in the
                    fusion); splits leader from native and defines the
                    numbering that --mutate uses (Met1 of the native protein).
    --mutate        substitution on the native numbering, checked against the
                    residue actually there; the wild-type figures are printed too.

Masses are average masses from the sequence (Biopython ProtParam). They are
computed values, not measurements: the initiator Met is kept, and processing
(Met removal, signal peptides, cofactors, PTMs) is not modelled.

Exit codes: 0 = computed, 1 = the construct could not be resolved (no anchor
feature, no ORF, no stop, motif absent or ambiguous, wrong base residue),
2 = usage error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _seqcommon import load, revcomp, translate  # noqa: E402

THROMBIN = "LVPRGS"
HIS_RUN = "HHHHHH"
_MUT = re.compile(r"^([A-Z])(\d+)([A-Z])$")


class ConstructError(Exception):
    """The construct cannot be resolved to one protein; the message says why."""


def find_anchor(rec, label: str):
    """Exact label first, then a unique prefix match.

    SnapGene stores some standard features with the description appended to the
    name ("T7 promoter promoter for bacteriophage T7 RNA p"), so an exact-only
    match misses a real pET-28a map that a synthetic fixture would match.
    """
    feat = rec.find_feature(label)
    if feat is not None:
        return feat
    low = label.lower()
    hits = [f for f in rec.features if f.name.lower().startswith(low)]
    if len({(f.start, f.end) for f in hits}) > 1:
        raise ConstructError(f'anchor "{label}" matches {len(hits)} features '
                             f"({', '.join(f.name[:30] for f in hits)}); be more specific")
    return hits[0] if hits else None


def orf_after_anchor(rec, anchor: str | None, start_pos: int | None):
    """Return (protein, stop_codon, strand) for the first ORF past the anchor."""
    seq, n = rec.seq, len(rec.seq)
    if start_pos is not None:
        origin, strand = start_pos - 1, 1
        window = seq[origin:] + (seq[:origin] if rec.circular else "")
    else:
        feat = find_anchor(rec, anchor)
        if feat is None:
            raise ConstructError(
                f'no feature labelled "{anchor}" in {rec.path.name}; name the promoter '
                "with --anchor or give the start codon with --start-pos")
        strand = feat.strand
        if strand > 0:
            origin = feat.end
            window = seq[origin:] + (seq[:origin] if rec.circular else "")
        else:
            origin = feat.start
            rc = revcomp(seq)
            r0 = n - origin
            window = rc[r0:] + (rc[:r0] if rec.circular else "")
    atg = window.upper().find("ATG")
    if atg < 0:
        raise ConstructError("no ATG downstream of the anchor")
    coding = window[atg:]
    protein = translate(coding, to_stop=True)
    end = len(protein) * 3
    stop = coding[end:end + 3].upper()
    if len(stop) < 3 or translate(stop) != "*":
        raise ConstructError(
            "no stop codon before the sequence ends; the ORF runs off the map")
    if "X" in protein:
        raise ConstructError("ORF contains ambiguous bases (translated as X)")
    return protein, stop, strand


def parse_mutations(tokens):
    out = []
    for t in tokens:
        m = _MUT.match(t.strip().upper())
        if not m:
            raise ValueError(f"malformed --mutate {t!r}; expected e.g. E223A")
        out.append((m.group(1), int(m.group(2)), m.group(3)))
    return out


def apply_mutations(native: str, muts):
    seq = list(native)
    for old, pos, new in muts:
        if pos < 1 or pos > len(seq):
            raise ConstructError(f"{old}{pos}{new}: residue {pos} is outside the "
                                 f"{len(seq)}-residue native protein")
        if seq[pos - 1] != old:
            raise ConstructError(
                f"{old}{pos}{new}: residue {pos} is {seq[pos - 1]!r} "
                f"(context {native[max(0, pos - 4):pos + 3]}), not {old!r}; "
                "check the numbering or the base map")
        seq[pos - 1] = new
    return "".join(seq)


def properties(protein: str) -> dict:
    from Bio.SeqUtils.ProtParam import ProteinAnalysis
    pa = ProteinAnalysis(protein)
    return {
        "aa": len(protein),
        "mw_da": round(pa.molecular_weight(), 2),
        "mw_kda": round(pa.molecular_weight() / 1000, 3),
        "pi": round(pa.isoelectric_point(), 2),
        "ext280_reduced": int(pa.molar_extinction_coefficient()[0]),
    }


def analyse(rec, anchor, start_pos, native_start, mutations) -> dict:
    protein, stop, strand = orf_after_anchor(rec, anchor, start_pos)
    res = {"map": rec.path.name, "orf_strand": strand, "stop_codon": stop,
           "fusion": properties(protein), "fusion_seq": protein}
    res["n_terminal_his"] = HIS_RUN in protein[:60]
    res["c_terminal_his"] = protein.endswith(HIS_RUN)
    if THROMBIN in protein:
        cut = protein.index(THROMBIN) + 4          # LVPR|GS
        res["thrombin_cleaved"] = properties(protein[cut:])
    if native_start:
        motif = native_start.upper()
        hits = [m.start() for m in re.finditer(f"(?={re.escape(motif)})", protein)]
        if len(hits) != 1:
            raise ConstructError(
                f"--native-start {motif!r} found {len(hits)} times in the fusion; "
                "give a longer, unique motif" if hits else
                f"--native-start {motif!r} not found in the {len(protein)} aa fusion")
        leader, native = protein[:hits[0]], protein[hits[0]:]
        res["leader_aa"] = len(leader)
        res["leader_seq"] = leader
        res["native"] = properties(native)
        res["native_seq"] = native
        if mutations:
            mut_native = apply_mutations(native, mutations)
            res["mutations"] = [f"{o}{p}{n}" for o, p, n in mutations]
            res["native_mutant"] = properties(mut_native)
            res["fusion_mutant"] = properties(leader + mut_native)
    elif mutations:
        raise ConstructError("--mutate needs --native-start to define the numbering")
    return res


def _line(label, p):
    return (f"  {label:<34}{p['aa']:>4} aa  {p['mw_kda']:>7.3f} kDa  "
            f"pI {p['pi']:<5} e280 {p['ext280_reduced']} M-1 cm-1")


def render(res: dict) -> str:
    out = [f"{res['map']}  (ORF on {'+' if res['orf_strand'] > 0 else '-'} strand, "
           f"stop {res['stop_codon']})"]
    if "fusion_mutant" in res:
        out.append(_line("fusion, as built (mutant)", res["fusion_mutant"]))
        out.append(_line("fusion, map as read (wild type)", res["fusion"]))
        out.append(_line("native only, mutant", res["native_mutant"]))
        out.append(_line("native only, wild type", res["native"]))
        out.append(f"  mutations on native numbering: {' '.join(res['mutations'])}")
    else:
        out.append(_line("fusion (what runs on the gel)", res["fusion"]))
        if "native" in res:
            out.append(_line("native only", res["native"]))
    if "leader_aa" in res:
        out.append(f"  leader: {res['leader_seq']} ({res['leader_aa']} aa)")
    if "thrombin_cleaved" in res:
        out.append(_line("after thrombin (LVPR|GS)", res["thrombin_cleaved"]))
    out.append("  tags: N-terminal His6 " + ("yes" if res["n_terminal_his"] else "no")
               + ", C-terminal His6 " + ("yes" if res["c_terminal_his"] else
                                          "no (stop codon precedes any C-terminal tag)"))
    out.append("  computed from sequence, not measured; initiator Met kept, no "
               "processing or PTM modelled")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("map", help="plasmid map: SnapGene .dna or GenBank .gb")
    ap.add_argument("--anchor", default="T7 promoter",
                    help='feature label to read downstream of (default "T7 promoter")')
    ap.add_argument("--start-pos", type=int,
                    help="1-based position of the start codon on the forward strand "
                         "(overrides --anchor)")
    ap.add_argument("--native-start", help="first residues of the native protein")
    ap.add_argument("--mutate", action="append", default=[],
                    help="substitution on native numbering, e.g. E223A (repeatable)")
    ap.add_argument("--json", action="store_true", help="print JSON instead of text")
    args = ap.parse_args()

    try:
        muts = parse_mutations(args.mutate)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    path = Path(args.map)
    if not path.is_file():
        print(f"error: {path} is not a file", file=sys.stderr)
        return 2
    try:
        res = analyse(load(path), args.anchor, args.start_pos, args.native_start, muts)
    except ConstructError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1
    except Exception as e:  # unreadable/corrupt map or missing Biopython
        print(f"FAIL: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    print(json.dumps(res, indent=2) if args.json else render(res))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
