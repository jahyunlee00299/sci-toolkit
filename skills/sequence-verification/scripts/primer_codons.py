#!/usr/bin/env python
"""Recover the codons a stored mutagenesis primer was designed to install.

When a mutation was planned but never saved into a map, the primer record is the
only on-disk evidence of what it was meant to be. SnapGene keeps the primer's
own sequence, but every reader that goes through the feature table — biopython
included — returns the wild-type template under the primer's binding site
instead, so the mismatched bases are invisible exactly where they matter.

Residue numbering comes from a wild-type reference, never from the CDS
annotation. Annotated CDS bounds are routinely a base or two off the real
reading frame (a vector fusion trims the start codon and the label keeps the old
range), and trusting them silently shifts every residue number — the mutation
gets reported at the wrong position with a plausible-looking amino acid.

Usage
-----
    python primer_codons.py MAP.dna --reference WT.dna
    python primer_codons.py MAP.dna --reference WT.dna --filter iPCR
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _seqcommon import (CODON_TABLE, align_offset, load, load_primers,  # noqa: E402
                        revcomp, translate)

_COMP1 = {"A": "T", "T": "A", "G": "C", "C": "G", "N": "N"}


def reference_protein(path: Path) -> str:
    rec = load(path)
    for feat in rec.features:
        if feat.type == "CDS":
            prot = translate(rec.extract(feat), to_stop=True)
            if len(prot) > 50:
                return prot
    best = ""
    for frame in range(3):
        for s in (rec.seq, revcomp(rec.seq)):
            prot = translate(s[frame:], to_stop=True)
            if len(prot) > len(best):
                best = prot
    return best


class Frame:
    """The reading frame of a reference CDS inside a larger construct.

    Holds the mapping between plasmid coordinates and reference residue numbers
    so callers never have to redo the strand/offset arithmetic.
    """

    def __init__(self, template: str, ref_prot: str):
        self.template = template
        self.L = len(template)
        for strand, seq in ((1, template), (-1, revcomp(template))):
            for f in range(3):
                prot = translate(seq[f:])
                off = align_offset(prot, ref_prot)
                if off is not None:
                    self.strand, self.f, self.off, self.sseq = strand, f, off, seq
                    return
        raise LookupError("reference CDS not found in this template")

    def to_index(self, pos: int) -> int:
        """Plasmid coordinate -> absolute index into the translated strand.

        Absolute, i.e. comparable with codon_span(), which is also absolute.
        Subtracting the frame offset here as well double-counts it and shifts
        every edit one base — silently, into a codon that still translates.
        """
        return pos if self.strand > 0 else (self.L - 1 - pos)

    def residue_of(self, pos: int) -> int:
        return (self.to_index(pos) - self.f) // 3 - self.off + 1

    def codon_span(self, residue: int):
        """Index range of `residue`'s codon within the translated strand."""
        s = self.f + 3 * (self.off + residue - 1)
        return s, s + 3

    def wt_codon(self, residue: int) -> str:
        s, e = self.codon_span(residue)
        return self.sseq[s:e]

    def base_for(self, pos: int, base: str) -> str:
        """Orient a base given in plasmid coordinates onto the translated strand."""
        return base if self.strand > 0 else _COMP1.get(base, "N")


def best_alignment(primer: str, template: str):
    """Ungapped best match of `primer`, both orientations, fewest mismatches.

    A mutagenesis primer is designed to mismatch, so an exact hit is not the
    goal; the correct window is the one needing the fewest changes.
    """
    best = None
    p_up = primer.upper()
    for strand, probe in ((1, p_up), (-1, revcomp(p_up))):
        n = len(probe)
        if n == 0 or n > len(template):
            continue
        for i in range(len(template) - n + 1):
            window = template[i:i + n]
            mm = [j for j in range(n) if window[j] != probe[j]]
            if len(mm) > n // 4:
                continue
            if best is None or len(mm) < len(best[3]):
                best = (i, strand, probe, mm)
                if not mm:
                    return best
    return best


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("map", help="SnapGene .dna file holding the primers")
    ap.add_argument("--reference", required=True,
                    help="wild-type CDS file that residue numbers refer to")
    ap.add_argument("--filter", default="",
                    help="only primers whose name contains this text")
    args = ap.parse_args()

    path = Path(args.map)
    primers = load_primers(path)
    if not primers:
        print(f"no primer records in {path.name} "
              "(only SnapGene .dna files store them)", file=sys.stderr)
        return 1

    rec = load(path)
    ref_prot = reference_protein(Path(args.reference))
    try:
        frame = Frame(rec.seq, ref_prot)
    except LookupError as exc:
        print(f"{exc}: {path.name} does not contain the reference CDS",
              file=sys.stderr)
        return 1

    proposals, shown = [], 0
    for p in primers:
        if args.filter and args.filter.lower() not in p["name"].lower():
            continue
        aln = best_alignment(p["sequence"], rec.seq)
        if aln is None:
            print(f"{p['name']:28s} no alignment to this template")
            continue
        start, strand, probe, mm = aln
        shown += 1
        if not mm:
            print(f"{p['name']:28s} @{start:6d} {strand:+d}  exact match "
                  "(not a mutagenesis primer)")
            continue

        by_residue = {}
        for j in mm:
            pos = start + j
            r = frame.residue_of(pos)
            by_residue.setdefault(r, []).append((pos, probe[j]))

        parts = []
        for r, edits in sorted(by_residue.items()):
            wt = frame.wt_codon(r)
            cs, _ = frame.codon_span(r)
            new = list(wt)
            for pos, base in edits:
                idx = frame.to_index(pos) - cs
                if 0 <= idx < 3:
                    new[idx] = frame.base_for(pos, base)
            new_codon = "".join(new)
            wt_aa = CODON_TABLE.get(wt, "?")
            new_aa = CODON_TABLE.get(new_codon, "?")
            token = f"{wt_aa}{r}{new_aa}:{new_codon}"
            parts.append(f"{token}  ({wt}->{new_codon})")
            if wt_aa != new_aa:
                proposals.append(token)
        print(f"{p['name']:28s} @{start:6d} {strand:+d}  {len(mm)} mismatch(es)  "
              + "   ".join(parts))

    if shown == 0:
        print("no primers matched the filter", file=sys.stderr)
        return 1

    if proposals:
        uniq = sorted(set(proposals))
        print("\n--mutate " + " ".join(uniq))
        print("A primer proves INTENT, not that the clone carries it. The map "
              "you build from this is the expected reference to align reads "
              "against, never a record of a verified sequence.")
    else:
        print("\nNo coding change found — these primers are silent or "
              "non-mutagenic against this template.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
