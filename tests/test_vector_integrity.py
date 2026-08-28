#!/usr/bin/env python3
"""Checks that the bundled SnapGene vectors actually parse.

Measured 260807: `.gitattributes` had only `* text=auto eol=lf` and did not
declare `*.dna` as binary, so line-ending normalization collapsed CRLF byte
pairs **inside** the vector files. `.dna` is a chain of
`[1B type][4B big-endian length][payload]` records, so once bytes vanish
from a payload, every offset after it shifts. Result:

    pACYCDuet-1  features 19 -> 0
    pET-21a(+)   features 15 -> 0
    pET-28a(+)   features 16 -> 0
    pMAL-c6T     features 18 -> 0      (pETDuet-1 was the only one unaffected)

**The sequence itself survives and the parser throws no exception.**
`parse_snapgene()` returns a normal, empty feature list, and
`colony_pcr_mode.suggest_from_snapgene()` operates on CDS features, so primer
design fails silently as "found nothing." doctor, every test, and CI all
stayed green — nobody was checking this axis.

So this check does not ask **does the file exist** but **does parsing it
produce content**. Byte corruption is visible in size or hash only as
"something changed," never as "is this still usable."
"""
from __future__ import annotations

import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

ROOT = Path(__file__).resolve().parent.parent
VECTORS = ROOT / "skills" / "primer-design" / "vectors"
SRC = ROOT / "skills" / "primer-design" / "src"

# Each vector must have at least this many features. Set below the measured
# values so a SnapGene version difference adding/dropping an annotation or
# two still passes, while corruption that collapses the count to 0 is
# always caught.
MIN_FEATURES = 5
MIN_SEQUENCE = 1000


def main() -> int:
    if not VECTORS.is_dir():
        print("SKIP — no primer-design vectors folder (optional install)")
        return 0

    sys.path.insert(0, str(SRC))
    try:
        from primer_design.snapgene_parser import parse_snapgene
    except Exception as e:                      # noqa: BLE001
        print(f"SKIP — could not import the parser: {type(e).__name__}: {e}")
        return 0

    files = sorted(VECTORS.glob("*.dna"))
    if not files:
        print("SKIP — no .dna vectors found")
        return 0

    failures: list[str] = []
    for f in files:
        try:
            seq, _circular, feats = parse_snapgene(str(f))
        except Exception as e:                  # noqa: BLE001
            failures.append(f"{f.name}: parse failed — {type(e).__name__}: {e}")
            continue
        n_seq = len(seq or "")
        n_feat = len(feats or [])
        if n_seq < MIN_SEQUENCE:
            failures.append(f"{f.name}: sequence is {n_seq}bp — expected at least {MIN_SEQUENCE}")
        if n_feat < MIN_FEATURES:
            failures.append(
                f"{f.name}: {n_feat} feature(s) — expected at least {MIN_FEATURES}. "
                "This is the signature of binary corruption from line-ending "
                "normalization (check the `*.dna binary` declaration in .gitattributes)")

    if failures:
        print(f"FAIL — {len(failures)} vector integrity issue(s)")
        for x in failures:
            print(f"  - {x}")
        return 1

    total = sum(len(parse_snapgene(str(f))[2] or []) for f in files)
    print(f"ALL PASS — {len(files)} vector(s), {total} feature(s) parsed total")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
