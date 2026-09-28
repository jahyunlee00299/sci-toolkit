#!/usr/bin/env python
"""Answer "which of these files actually carries the variant?" by reading residues.

A filename is not evidence. Neither is an annotated mutagenesis primer: SnapGene
stores a primer's binding site against the wild-type template, so a map can show
`iPCR_E223A` in its primer list and still hold a pure WT coding sequence. The
only way to know is to translate every candidate and look at the residue.

Usage
-----
    python find_variant_maps.py --reference WT.dna --residues 223,271 <paths...>
    python find_variant_maps.py --reference WT.dna --residues 223,271 \\
        --expect 223=A --expect 271=A  <paths...>

`<paths...>` are files or directories (directories are scanned one level deep by
default; pass --recursive to descend). Feed it a shortlist rather than pointing
it at a synced cloud folder: this script opens files, and on cloud storage that
forces placeholder files to download.

Exit codes: 0 = at least one file matched --expect (or no --expect given),
1 = nothing matched what was expected, 2 = usage/IO error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _seqcommon import align_offset, load, revcomp, translate  # noqa: E402

SUFFIXES = (".dna", ".gb", ".gbk", ".genbank")


def collect(paths, recursive: bool):
    out = []
    for p in paths:
        p = Path(p)
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            it = p.rglob("*") if recursive else p.glob("*")
            out.extend(f for f in it if f.suffix.lower() in SUFFIXES)
    return sorted(set(out))


def reference_protein(path: Path) -> str:
    """Longest ORF-ish translation of a reference CDS file."""
    rec = load(path)
    for feat in rec.features:
        if feat.type == "CDS":
            prot = translate(rec.extract(feat), to_stop=True)
            if len(prot) > 50:
                return prot
    # No usable CDS annotation: fall back to the whole sequence, best frame.
    best = ""
    for frame in range(3):
        for strand in (rec.seq, revcomp(rec.seq)):
            prot = translate(strand[frame:], to_stop=True)
            if len(prot) > len(best):
                best = prot
    return best


def residues_in(rec, ref_prot: str, residues):
    """Locate ref_prot inside rec (6 frames) and read the requested residues."""
    for strand_seq in (rec.seq, revcomp(rec.seq)):
        for frame in range(3):
            prot = translate(strand_seq[frame:])
            off = align_offset(prot, ref_prot)
            if off is None:
                continue
            found = {}
            for r in residues:
                i = off + r - 1
                found[r] = prot[i] if 0 <= i < len(prot) else "?"
            return found
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--reference", required=True,
                    help="wild-type CDS file the residue numbering refers to")
    ap.add_argument("--residues", required=True,
                    help="comma-separated 1-based residue numbers, e.g. 223,271")
    ap.add_argument("--expect", action="append", default=[],
                    help="residue=AA that marks a variant, e.g. 223=A (repeatable)")
    ap.add_argument("--recursive", action="store_true")
    args = ap.parse_args()

    try:
        residues = [int(x) for x in args.residues.split(",") if x.strip()]
    except ValueError:
        print("--residues must be integers", file=sys.stderr)
        return 2
    expect = {}
    for item in args.expect:
        if "=" not in item:
            print(f"--expect needs residue=AA, got {item!r}", file=sys.stderr)
            return 2
        k, v = item.split("=", 1)
        expect[int(k)] = v.strip().upper()

    ref_prot = reference_protein(Path(args.reference))
    if len(ref_prot) < 40:
        print(f"reference protein too short ({len(ref_prot)} aa) to anchor on",
              file=sys.stderr)
        return 2
    wt = {r: ref_prot[r - 1] if r - 1 < len(ref_prot) else "?" for r in residues}
    print(f"reference {Path(args.reference).name}: {len(ref_prot)} aa"
          f"   WT " + "  ".join(f"{r}={wt[r]}" for r in residues))
    print()

    files = collect(args.paths, args.recursive)
    if not files:
        print("no sequence files found in the given paths", file=sys.stderr)
        return 2

    hits, scanned, skipped = [], 0, []
    for f in files:
        try:
            rec = load(f)
        except Exception as exc:                      # unreadable / wrong format
            skipped.append((f, str(exc)[:60]))
            continue
        found = residues_in(rec, ref_prot, residues)
        if found is None:
            skipped.append((f, "reference CDS not present"))
            continue
        scanned += 1
        differs = [r for r in residues if found[r] != wt[r]]
        matches_expect = bool(expect) and all(
            found.get(r) == aa for r, aa in expect.items())
        mark = "  <<< VARIANT" if differs else ""
        if matches_expect:
            mark = "  <<< MATCHES --expect"
        print(f"{f.parent.name[:20]:22s} {f.name[:48]:50s} "
              + " ".join(f"{r}={found[r]}" for r in residues) + mark)
        if matches_expect or (not expect and differs):
            hits.append(f)

    print()
    print(f"scanned {scanned} file(s); {len(hits)} carrying the variant")
    for f in skipped:
        print(f"  skipped {f[0].name}: {f[1]}")
    if expect and not hits:
        print("\nNo file carries the expected variant. If a mutagenesis primer is "
              "annotated somewhere, the mutation was planned but never saved into "
              "a map — run primer_codons.py on that file to recover the intended "
              "codons, then build_reference_map.py to create the comparison map.")
        return 1
    for f in hits:
        print(f"  -> {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
