#!/usr/bin/env python
"""Build the expected-sequence map to align sequencing reads against.

Takes a map that was actually built and verified in the lab, changes only the
codons you name, and checks that nothing else moved. That is the whole design:
a reference map is only trustworthy in proportion to how little of it was
invented.

Do NOT assemble one by simulating a ligation unless you have to. An insert cut
for one vector carries that vector's reading frame — a pETDuet MCS1 insert has
its start codon trimmed to fuse with the upstream tag, so dropping it into
pET-28a's BamHI site shifts the frame and the construct dies a few dozen
residues in. Starting from a measured map keeps the junction that was proven to
express, and the diff stays small enough to audit by eye.

Usage
-----
    python build_reference_map.py --base MEASURED.dna --reference WT.dna \\
        --mutate E223A:GCA --mutate S271A:GCC --out expected.gb

Exit codes: 0 = built and verified, 1 = verification failed (no file written),
2 = usage error.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _seqcommon import CODON_TABLE, load, revcomp, translate  # noqa: E402
from primer_codons import Frame, reference_protein  # noqa: E402

_COMP1 = {"A": "T", "T": "A", "G": "C", "C": "G", "N": "N"}
HIS_TAGS = ("CATCATCATCATCATCAC", "CACCACCACCACCACCAC",
            "CATCACCATCATCACCAC", "CACCATCACCATCACCAT")


def fusion_protein(seq: str, circular: bool = True):
    """Translate the tagged ORF, if this construct has a His-tag fusion.

    Returns (protein, tag_length) or (None, None). Used as an independent check
    that a codon edit did not disturb the reading frame: the fusion length must
    not change.
    """
    doubled = seq + seq if circular else seq
    for strand in (doubled, revcomp(doubled)):
        for tag in HIS_TAGS:
            i = strand.find(tag)
            if i < 0:
                continue
            for back in range(3, 90, 3):
                if strand[i - back:i - back + 3] == "ATG":
                    return translate(strand[i - back:], to_stop=True), back // 3
    return None, None


def parse_mutations(tokens):
    """['E223A:GCA'] -> [(223, 'E', 'A', 'GCA')]"""
    out = []
    for t in tokens:
        if ":" not in t:
            raise ValueError(f"--mutate needs WT<pos>NEW:CODON, got {t!r}")
        tag, codon = t.split(":", 1)
        codon = codon.strip().upper()
        if len(codon) != 3 or any(c not in "ACGT" for c in codon):
            raise ValueError(f"{t!r}: codon must be 3 of ACGT")
        wt_aa, new_aa = tag[0].upper(), tag[-1].upper()
        try:
            pos = int(tag[1:-1])
        except ValueError:
            raise ValueError(f"{t!r}: cannot read a residue number from {tag!r}")
        if CODON_TABLE.get(codon) != new_aa:
            raise ValueError(
                f"{t!r}: codon {codon} encodes "
                f"{CODON_TABLE.get(codon, '?')}, not {new_aa}")
        out.append((pos, wt_aa, new_aa, codon))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True,
                    help="a map that was actually built in the lab")
    ap.add_argument("--reference", required=True,
                    help="wild-type CDS file residue numbers refer to")
    ap.add_argument("--mutate", action="append", required=True,
                    help="WT<pos>NEW:CODON, e.g. E223A:GCA (repeatable)")
    ap.add_argument("--out", required=True, help="output .gb path")
    ap.add_argument("--name", default=None, help="record name (default: out stem)")
    args = ap.parse_args()

    try:
        muts = parse_mutations(args.mutate)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2

    base_path, out_path = Path(args.base), Path(args.out)
    rec = load(base_path)
    ref_prot = reference_protein(Path(args.reference))
    try:
        frame = Frame(rec.seq, ref_prot)
    except LookupError:
        print(f"{base_path.name} does not contain the reference CDS — wrong "
              "base map?", file=sys.stderr)
        return 1

    before_fusion, tag_len = fusion_protein(rec.seq, rec.circular)
    seq = list(rec.seq)
    applied = []
    for pos, wt_aa, new_aa, codon in muts:
        cs, ce = frame.codon_span(pos)
        cur = frame.sseq[cs:ce]
        cur_aa = CODON_TABLE.get(cur, "?")
        if cur_aa != wt_aa:
            print(f"residue {pos} of the base map is {cur_aa}, not the {wt_aa} "
                  f"that {wt_aa}{pos}{new_aa} assumes — refusing to edit",
                  file=sys.stderr)
            return 1
        for k, base in enumerate(codon):
            # codon_span is on the translated strand; map back to the plasmid.
            idx = cs + k
            pos_plasmid = idx if frame.strand > 0 else frame.L - 1 - idx
            seq[pos_plasmid] = base if frame.strand > 0 else _COMP1[base]
        applied.append((pos, wt_aa, new_aa, cur, codon))

    new_seq = "".join(seq)

    # --- verification -----------------------------------------------------
    nt_diff = [i for i in range(len(new_seq)) if new_seq[i] != rec.seq[i]]
    new_frame = Frame(new_seq, ref_prot)
    prot_before = translate(frame.sseq[frame.f:])
    prot_after = translate(new_frame.sseq[new_frame.f:])
    aa_diff = [(i - frame.off + 1, prot_before[i], prot_after[i])
               for i in range(min(len(prot_before), len(prot_after)))
               if prot_before[i] != prot_after[i]]
    after_fusion, _ = fusion_protein(new_seq, rec.circular)

    expected_aa = sorted((p, w, n) for p, w, n, _, _ in applied)
    print(f"base    {base_path.name}  {len(rec.seq)} bp")
    for pos, wt_aa, new_aa, old_c, new_c in applied:
        print(f"  {wt_aa}{pos}{new_aa}: {old_c} -> {new_c}")
    print(f"nt changed: {len(nt_diff)} ({', '.join(map(str, nt_diff))})")
    print(f"aa changed: {aa_diff}")

    ok = True
    if sorted(aa_diff) != expected_aa:
        print("FAIL: residue changes do not match what was requested", file=sys.stderr)
        ok = False
    if len(nt_diff) != 3 * len(applied) and len(nt_diff) > 3 * len(applied):
        print("FAIL: more bases changed than the codons account for", file=sys.stderr)
        ok = False
    if before_fusion is not None:
        if after_fusion is None or len(after_fusion) != len(before_fusion):
            print(f"FAIL: tagged fusion changed length "
                  f"{len(before_fusion)} -> "
                  f"{len(after_fusion) if after_fusion else None} aa "
                  "(reading frame disturbed)", file=sys.stderr)
            ok = False
        else:
            print(f"fusion ORF: {len(before_fusion)} aa unchanged "
                  f"(His6 begins at residue {tag_len + 1}) - frame intact")
    else:
        print("note: no His-tag fusion found; frame check limited to the CDS")
    if not ok:
        print("\nno file written", file=sys.stderr)
        return 1

    # --- emit -------------------------------------------------------------
    from Bio import SeqIO
    from Bio.Seq import Seq
    from Bio.SeqFeature import FeatureLocation, SeqFeature
    from Bio.SeqRecord import SeqRecord

    name = args.name or out_path.stem
    changes = ", ".join(f"{w}{p}{n} {o}->{c}" for p, w, n, o, c in applied)
    out_rec = SeqRecord(
        Seq(new_seq), id=name[:16], name=name[:16],
        description=f"expected reference: {base_path.stem} with {changes}",
        annotations={
            "molecule_type": "DNA",
            "topology": "circular" if rec.circular else "linear",
            "organism": "synthetic construct",
            "date": _dt.date.today().strftime("%d-%b-%Y").upper(),
            "comment": (
                f"Built by sequence-verification/build_reference_map.py from "
                f"{base_path.name} by changing only: {changes}. "
                f"{len(nt_diff)} nt differ from the base map. "
                "NOT an experimentally sequenced record: use it as the "
                "expected sequence when aligning reads, and store the "
                "confirmed sequence separately."),
        })
    for feat in rec.features:
        out_rec.features.append(SeqFeature(
            FeatureLocation(feat.start, feat.end, strand=feat.strand),
            type=feat.type, qualifiers={"label": feat.name}))
    for pos, wt_aa, new_aa, _old, _new in applied:
        cs, ce = frame.codon_span(pos)
        a = cs if frame.strand > 0 else frame.L - ce
        out_rec.features.append(SeqFeature(
            FeatureLocation(a, a + 3, strand=frame.strand),
            type="variation",
            qualifiers={"label": f"{wt_aa}{pos}{new_aa}",
                        "note": "expected variant codon; not yet sequenced"}))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Pin the encoding: GenBank is an ASCII format and Python would otherwise
    # use the Windows code page, which rejects any non-ASCII character that
    # reached a qualifier from a source file.
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        SeqIO.write(out_rec, fh, "genbank")

    reread = next(SeqIO.parse(str(out_path), "genbank"))
    if str(reread.seq).upper() != new_seq:
        print("FAIL: file re-read does not match what was built", file=sys.stderr)
        out_path.unlink(missing_ok=True)
        return 1
    print(f"\nwrote {out_path}  ({len(new_seq)} bp, "
          f"{len(out_rec.features)} features, re-read verified)")
    print("Next: read_coverage.py to pick the sequencing primer that actually "
          "reaches these positions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
