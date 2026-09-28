#!/usr/bin/env python
"""Decide which sequencing primer actually reaches the positions you care about.

A Sanger read is only trustworthy for a few hundred bases: the first ~30 are
noise from the dye blob, quality peaks around 60-500, decays through ~700, and
past ~850 basecalls are unreliable even when the trace looks like something.
A variant sitting 900 bases from the primer will often read as wild type, and
the order comes back looking clean.

So before ordering, check the distance from each candidate primer to each target
position. This is the step that decides whether a sequencing result can answer
the question at all.

Usage
-----
    python read_coverage.py --map expected.gb --targets 309,452
    python read_coverage.py --map expected.gb --variants        # use variation features
    python read_coverage.py --map expected.gb --variants --primers "T7 promoter,T7 terminator"

Exit codes: 0 = every target is covered by some primer, 1 = at least one target
is out of reach of all of them, 2 = usage error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _seqcommon import load  # noqa: E402

# Read-quality bands, in bases from the primer 3' end.
GOOD, MARGINAL, MAX_READ = 600, 850, 1000
DEAD_ZONE = 30          # basecalls right after the primer are unusable

PRIMER_HINTS = ("primer", "promoter", "terminator")


def candidate_primers(rec, names):
    """Features usable as sequencing primers, as (name, start, end, strand)."""
    out = []
    for f in rec.features:
        label = f.name or ""
        if names:
            if not any(n.strip().lower() in label.lower() for n in names):
                continue
        elif not any(h in label.lower() for h in (*PRIMER_HINTS,)) \
                and f.type not in ("primer_bind", "promoter", "terminator"):
            continue
        out.append(f)
    return out


def distance(rec, primer, target: int) -> int | None:
    """Bases read before reaching `target`, or None if the primer reads away.

    A primer extends in its own direction; on a circular map it can wrap, so
    the distance is measured the long way round when needed.
    """
    L = len(rec.seq)
    if primer.strand > 0:
        start = primer.end                       # extension begins after the site
        d = target - start
    else:
        start = primer.start
        d = start - target
    if d < 0:
        if not rec.circular:
            return None
        d += L
    return d if d <= MAX_READ else (d if rec.circular else None)


def verdict(d: int | None) -> str:
    if d is None:
        return "reads away"
    if d < DEAD_ZONE:
        return "TOO CLOSE (in the dye blob)"
    if d <= GOOD:
        return "OK"
    if d <= MARGINAL:
        return "marginal"
    return "OUT OF REACH"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--map", required=True)
    ap.add_argument("--targets", default="",
                    help="comma-separated 0-based positions on the map")
    ap.add_argument("--variants", action="store_true",
                    help="use the map's own variation features as targets")
    ap.add_argument("--primers", default="",
                    help="comma-separated feature-name substrings to consider")
    args = ap.parse_args()

    rec = load(Path(args.map))
    targets = []
    if args.targets:
        try:
            targets = [(f"pos{int(t)}", int(t))
                       for t in args.targets.split(",") if t.strip()]
        except ValueError:
            print("--targets must be integers", file=sys.stderr)
            return 2
    if args.variants:
        for f in rec.features:
            if f.type == "variation":
                targets.append((f.name or "variant", f.start))
    if not targets:
        print("no targets: pass --targets or --variants (the map has no "
              "variation features)", file=sys.stderr)
        return 2

    names = [n for n in args.primers.split(",") if n.strip()]
    primers = candidate_primers(rec, names)
    if not primers:
        print("no candidate primers found in the map; name them with --primers",
              file=sys.stderr)
        return 2

    print(f"{Path(args.map).name}  {len(rec.seq)} bp "
          f"{'circular' if rec.circular else 'linear'}")
    print(f"quality bands: <={GOOD} OK, <={MARGINAL} marginal, "
          f">{MARGINAL} out of reach\n")

    covered = {name: False for name, _ in targets}
    rows = []
    for p in primers:
        for tname, tpos in targets:
            d = distance(rec, p, tpos)
            v = verdict(d)
            if v in ("OK", "marginal"):
                covered[tname] = True
            rows.append((p.name, p.strand, tname, tpos, d, v))

    width = max(len(r[0]) for r in rows) + 2
    for name, strand, tname, tpos, d, v in rows:
        dtxt = "-" if d is None else f"{d:5d} bp"
        flag = "" if v in ("OK",) else ("   <<< " + v if v != "reads away" else "")
        print(f"{name[:width]:{width}s} {strand:+d}  ->  {tname:14s} "
              f"@{tpos:6d}  {dtxt:9s} {v}{'' if v != 'OK' else ''}")

    print()
    missing = [t for t, ok in covered.items() if not ok]
    if missing:
        print("NOT COVERED by any primer: " + ", ".join(missing))
        print("Design an internal primer, or sequence from the other end. "
              "Ordering as-is will return a read that cannot answer the "
              "question.")
        return 1
    best = {}
    for name, strand, tname, tpos, d, v in rows:
        if v in ("OK", "marginal") and (tname not in best or d < best[tname][1]):
            best[tname] = (name, d)
    print("use:")
    for tname, (name, d) in sorted(best.items()):
        print(f"  {tname:14s} <- {name} ({d} bp)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
