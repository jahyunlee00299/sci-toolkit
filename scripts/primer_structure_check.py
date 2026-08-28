#!/usr/bin/env python3
"""Primer structure check - hairpin and homodimer checks (nearest-neighbor thermodynamics).

Usage:
    python primer_structure_check.py ATCGATCGATCG
    python primer_structure_check.py ATCG... GCTA... --threshold-hairpin -2.0
    python primer_structure_check.py --file primers.json

Import:
    from primer_structure_check import check_primer, check_primers
    result = check_primer("ATCGATCG")

Result format:
    [{"seq", "hairpin_dG", "homodimer_dG", "hairpin_pass", "homodimer_pass"}]

Pass/fail criteria:
    - hairpin: self-complementary >=4 bp AND dG < -2.0 kcal/mol -> FAIL
    - homodimer: >=6 bp complementary -> FAIL (dG threshold applied separately)
"""
import argparse
import json
import math
import sys
from pathlib import Path
from typing import Optional

# Nearest-neighbor parameters (SantaLucia 1998, 1M NaCl, 37 degC)
# Key: 5'->3' double-strand dinucleotide (top/bottom strand)
# Value: (dH kcal/mol, dS cal/mol/K)
_NN_PARAMS: dict[str, tuple[float, float]] = {
    "AA/TT": (-7.9, -22.2),
    "AT/TA": (-7.2, -20.4),
    "TA/AT": (-7.2, -21.3),
    "CA/GT": (-8.5, -22.7),
    "GT/CA": (-8.4, -22.4),
    "CT/GA": (-7.8, -21.0),
    "GA/CT": (-8.2, -22.2),
    "CG/GC": (-10.6, -27.2),
    "GC/CG": (-9.8, -24.4),
    "GG/CC": (-8.0, -19.9),
    # reverse (complement)
    "TT/AA": (-7.9, -22.2),
    "TA/AT": (-7.2, -21.3),
    "AT/TA": (-7.2, -20.4),
    "AC/TG": (-7.8, -21.0),  # reverse of CA/GT
    "TG/AC": (-8.5, -22.7),
    "AG/TC": (-8.4, -22.4),
    "TC/AG": (-8.2, -22.2),
    "GC/CG": (-9.8, -24.4),
    "CG/GC": (-10.6, -27.2),
    "CC/GG": (-8.0, -19.9),
}

# Terminal AT penalty (initiation)
_INIT_AT = (2.3, 4.1)
_INIT_GC = (0.1, -2.8)

_COMPLEMENT = str.maketrans("ACGTacgt", "TGCAtgca")
_R = 1.987e-3  # kcal/mol/K


def _complement(seq: str) -> str:
    return seq.translate(_COMPLEMENT)


def _reverse_complement(seq: str) -> str:
    return _complement(seq)[::-1]


def _nn_dg(seq: str, temp_c: float = 37.0) -> float:
    """Compute double-strand dG (kcal/mol) with the nearest-neighbor model.

    seq is a single-strand 5'->3' sequence. Assumes it binds its own reverse complement.
    """
    seq = seq.upper()
    T = temp_c + 273.15
    dH = 0.0
    dS = 0.0

    for i in range(len(seq) - 1):
        dinuc = seq[i:i+2]
        rc_dinuc = _reverse_complement(dinuc)
        key = f"{dinuc}/{rc_dinuc}"
        if key in _NN_PARAMS:
            h, s = _NN_PARAMS[key]
            dH += h
            dS += s
        else:
            # use an average value when no parameter exists
            dH += -8.0
            dS += -21.0

    # terminal penalty
    for end_base in (seq[0], seq[-1]):
        if end_base in "AT":
            dH += _INIT_AT[0]
            dS += _INIT_AT[1]
        else:
            dH += _INIT_GC[0]
            dS += _INIT_GC[1]

    dG = dH - T * (dS / 1000.0)
    return round(dG, 2)


def _find_hairpin(seq: str, min_bp: int = 4, min_loop: int = 3) -> tuple[float, int]:
    """Return the minimum dG and stem length of a hairpin structure.

    Args:
        seq: primer sequence (5'->3')
        min_bp: minimum number of stem base pairs
        min_loop: minimum loop size

    Returns:
        a (min_dG, max_stem_length) tuple
    """
    seq = seq.upper()
    n = len(seq)
    best_dg = 0.0
    best_stem = 0

    for stem_len in range(min_bp, n // 2 + 1):
        for i in range(n - stem_len * 2 - min_loop + 1):
            stem5 = seq[i:i + stem_len]
            # position after the loop
            for loop_len in range(min_loop, n - i - stem_len * 2 + 1):
                j = i + stem_len + loop_len
                if j + stem_len > n:
                    break
                stem3 = seq[j:j + stem_len]
                # compare stem3 against stem5's reverse complement
                rc_stem5 = _reverse_complement(stem5)
                if stem3 == rc_stem5:
                    dg = _nn_dg(stem5)
                    if dg < best_dg:
                        best_dg = dg
                        best_stem = stem_len

    return best_dg, best_stem


def _find_homodimer(seq: str, min_bp: int = 6) -> tuple[float, int]:
    """Return the minimum dG and maximum complementary length of a homodimer pairing.

    Checks primarily for 3'-end complementarity between two copies of the same primer.
    """
    seq = seq.upper()
    n = len(seq)
    rc_seq = _reverse_complement(seq)
    best_dg = 0.0
    best_bp = 0

    # sliding window search for a complementary region
    for window in range(min_bp, n + 1):
        for i in range(n - window + 1):
            subseq = seq[i:i + window]
            rc_sub = _reverse_complement(subseq)
            # a homodimer is possible if rc_sub occurs in the original sequence
            if rc_sub in seq:
                dg = _nn_dg(subseq)
                if dg < best_dg:
                    best_dg = dg
                    best_bp = window

    return best_dg, best_bp


def check_primer(
    seq: str,
    threshold_hairpin_dg: float = -2.0,
    threshold_homodimer_bp: int = 6,
    temp_c: float = 37.0,
) -> dict:
    """Check a single primer's hairpin and homodimer structure.

    Args:
        seq: primer sequence (5'->3', ACGT only)
        threshold_hairpin_dg: hairpin FAIL threshold dG (kcal/mol), default -2.0
        threshold_homodimer_bp: homodimer FAIL threshold minimum bp count, default 6
        temp_c: computation temperature (degC), default 37.0

    Returns:
        {"seq", "hairpin_dG", "homodimer_dG", "hairpin_pass", "homodimer_pass"}
    """
    seq = seq.strip().upper()
    invalid = set(seq) - set("ACGT")
    if invalid:
        return {
            "seq": seq,
            "hairpin_dG": None,
            "homodimer_dG": None,
            "hairpin_pass": False,
            "homodimer_pass": False,
            "notes": f"Invalid base(s): {invalid}",
        }

    hairpin_dg, hairpin_stem = _find_hairpin(seq)
    homodimer_dg, homodimer_bp = _find_homodimer(seq, min_bp=threshold_homodimer_bp)

    # hairpin FAIL: stem >=4bp AND dG < threshold
    hairpin_pass = not (hairpin_stem >= 4 and hairpin_dg < threshold_hairpin_dg)
    # homodimer FAIL: complementary >=min_bp
    homodimer_pass = homodimer_bp < threshold_homodimer_bp

    return {
        "seq": seq,
        "hairpin_dG": hairpin_dg,
        "homodimer_dG": homodimer_dg,
        "hairpin_pass": hairpin_pass,
        "homodimer_pass": homodimer_pass,
    }


def check_primers(
    seqs: list[str],
    threshold_hairpin_dg: float = -2.0,
    threshold_homodimer_bp: int = 6,
    temp_c: float = 37.0,
) -> list[dict]:
    """Check multiple primers in a batch."""
    return [
        check_primer(seq, threshold_hairpin_dg, threshold_homodimer_bp, temp_c)
        for seq in seqs
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check primer hairpin/homodimer structure with the nearest-neighbor model."
    )
    parser.add_argument(
        "sequences", nargs="*", default=[],
        help="primer sequence(s) (given directly, space-separated)"
    )
    parser.add_argument(
        "--file", "-f", default=None,
        help="primer JSON file (a string array or an array of [{seq:...}])"
    )
    parser.add_argument(
        "--threshold-hairpin", type=float, default=-2.0, metavar="DG",
        help="hairpin FAIL threshold dG in kcal/mol (default: -2.0)"
    )
    parser.add_argument(
        "--threshold-homodimer", type=int, default=6, metavar="BP",
        help="homodimer FAIL threshold minimum bp count (default: 6)"
    )
    parser.add_argument(
        "--temp", type=float, default=37.0, metavar="C",
        help="computation temperature in degC (default: 37.0)"
    )
    parser.add_argument("--output", "-o", default=None, help="output JSON file path")
    args = parser.parse_args()

    if not args.sequences and not args.file:
        parser.error("Either provide sequences directly or specify --file.")
    if args.sequences and args.file:
        parser.error("Direct sequence input and --file cannot be used together.")

    if args.file:
        raw = json.loads(Path(args.file).read_text(encoding="utf-8"))
        if isinstance(raw, list):
            seqs = [
                item["seq"] if isinstance(item, dict) else str(item)
                for item in raw
            ]
        else:
            parser.error("The JSON file must be a string array or an array of [{seq:...}].")
    else:
        seqs = args.sequences

    results = check_primers(
        seqs,
        threshold_hairpin_dg=args.threshold_hairpin,
        threshold_homodimer_bp=args.threshold_homodimer,
        temp_c=args.temp,
    )

    output_json = json.dumps(results, ensure_ascii=False, indent=2)

    if args.output:
        Path(args.output).write_text(output_json, encoding="utf-8")
        print(f"Checked {len(results)} primer(s) -> {args.output}", file=sys.stderr)
    else:
        print(output_json)

    pass_all = sum(1 for r in results if r.get("hairpin_pass") and r.get("homodimer_pass"))
    print(
        f"\nSummary: {pass_all} of {len(results)} total passed "
        f"(both hairpin and homodimer passed)",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
