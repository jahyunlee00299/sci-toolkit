#!/usr/bin/env python3
"""Checks that counts written in the docs match reality.

A line on README's first screen like `26 skills · 12 regression tests` is
the first number a user judges this package by, yet nobody updates it when
a skill is added or removed. Measured 260807: a commit that dropped 5
skills and added 1 only edited `31 → 26` (it accounted for the drop but
missed the addition). The actual bundled count was 27, and in that state
doctor reported 10 OK, all 15 tests passed, and CI was green —
**because nothing was checking the count at all.**

SSOT for each number:

  N skills             = entries in config/catalog.json that aren't external = number of folders in skills/
                          (if the two disagree, that disagreement is itself a defect, so both are checked together)
  N regression tests   = number of tests/test_*.py files
  N safety guards      = hooks/*.sh minus the runner (_run_hooks_chained.sh)
  N beginner docs      = numbered docs in docs/ (00_ through 12_)

Whenever a count is written into a doc, add a check for it here too. A
count with no check is guaranteed to go stale.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

ROOT = Path(__file__).resolve().parent.parent


def actual_counts() -> dict[str, int]:
    catalog = json.loads((ROOT / "config" / "catalog.json").read_text(encoding="utf-8"))
    skills = catalog["skills"]
    bundled = {k for k, v in skills.items() if not v.get("external")}
    on_disk = {p.name for p in (ROOT / "skills").iterdir() if p.is_dir()}
    hooks = {p.name for p in (ROOT / "hooks").glob("*.sh")
             if not p.name.startswith("_")}
    docs = {p.name for p in (ROOT / "docs").glob("*.md")
            if re.match(r"^\d{2}_", p.name)}
    tests = {p.name for p in (ROOT / "tests").glob("test_*.py")}
    return {
        "catalog_total": len(skills),
        "bundled": len(bundled),
        "on_disk": len(on_disk),
        "tests": len(tests),
        "hooks": len(hooks),
        "docs": len(docs),
        "_bundled_set": bundled,
        "_disk_set": on_disk,
    }


def find_counts(path: Path, pattern: str) -> list[tuple[int, int, str]]:
    """List of (line number, number, line). pattern must capture the number as group 1."""
    out = []
    rx = re.compile(pattern)
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        for m in rx.finditer(line):
            out.append((i, int(m.group(1)), line.strip()[:80]))
    return out


def main() -> int:
    a = actual_counts()
    failures: list[str] = []
    checked = 0

    # 0) do catalog and disk agree on the same set of skills?
    checked += 1
    only_catalog = sorted(a["_bundled_set"] - a["_disk_set"])
    only_disk = sorted(a["_disk_set"] - a["_bundled_set"])
    if only_catalog or only_disk:
        failures.append(
            f"catalog and skills/ folder disagree — only in catalog: {only_catalog}, "
            f"only on disk: {only_disk}")

    # 0.5) does doctor actually run every test under tests/?
    #
    # doctor's SELF_TEST_SCRIPTS is a hardcoded list, and CI calls only
    # doctor. So dropping a file in tests/ and forgetting to register it
    # means that test **never runs anywhere** while still looking like it
    # exists — a classic way for green-light coverage to outpace actual
    # detection power. Right now two files (test_agents_routing,
    # test_skill_references) are called via their own dedicated check, so
    # they're absent from the registration list yet still run. That's why
    # the criterion here is not "is it in SELF_TEST_SCRIPTS" but "does
    # doctor.py mention this file at all".
    checked += 1
    # doctor.py was split into doctor_lib/ (260902): SELF_TEST_SCRIPTS stayed
    # in doctor.py verbatim, but check_skill_references()/check_agents_routing()
    # — the dedicated calls that reach test_skill_references.py and
    # test_agents_routing.py without going through SELF_TEST_SCRIPTS — moved
    # into doctor_lib/checks_repo.py. Scanning doctor.py alone would now miss
    # them and report two false "never runs" failures, so every doctor_lib/*.py
    # file is concatenated in too.
    doctor_src = (ROOT / "doctor.py").read_text(encoding="utf-8")
    doctor_src += "".join((p).read_text(encoding="utf-8")
                          for p in sorted((ROOT / "doctor_lib").glob("*.py")))
    # Only look at actual execution points. Treating this as a plain
    # substring search over the whole source would let **writing the name
    # in a comment on one line** pass the check — a gate that's green while
    # the test itself runs nowhere, approved by the gate (measured 260807).
    # So only a string literal that appears as `"tests/....py"` counts as
    # an execution path: both SELF_TEST_SCRIPTS entries and
    # _run_test_script() calls take this form.
    executed = set(re.findall(r'["\'](tests/(test_[A-Za-z0-9_]+\.py))["\']',
                              doctor_src))
    executed_names = {name for _full, name in executed}
    unreached = sorted(p.name for p in (ROOT / "tests").glob("test_*.py")
                       if p.name not in executed_names)
    if unreached:
        failures.append(
            f"{len(unreached)} test(s) doctor never runs: {unreached}"
            " — add them to doctor.py's SELF_TEST_SCRIPTS. CI only calls doctor,"
            " so an unregistered test never runs, ever")

    # 1) counts written into the docs
    specs = [
        ("README.md", r"(\d+)\s+skills", a["bundled"], "bundled skills"),
        ("README.md", r"(\d+)\s+regression tests", a["tests"], "regression tests"),
        ("README.md", r"(\d+)\s+safety guards", a["hooks"], "safety guards"),
        ("README.md", r"(\d+)\s+beginner docs", a["docs"], "beginner docs"),
        ("QUICKSTART.md", r"lists\s+(\d+)\s+skills", a["catalog_total"], "installer listing"),
        ("QUICKSTART.md", r"(\d+)\s+are actually installable", a["bundled"], "bundled skills"),
        ("QUICKSTART.md", r"all\s+(\d+)\s+at once", a["bundled"], "bundled skills"),
        ("config/catalog.json", r"All\s+(\d+)\s+skills", a["catalog_total"], "the 'all' preset"),
    ]
    for fname, pat, expect, label in specs:
        p = ROOT / fname
        if not p.exists():
            continue
        hits = find_counts(p, pat)
        if not hits:
            continue          # the phrase being absent is not itself a defect
        for ln, got, ctx in hits:
            checked += 1
            if got != expect:
                failures.append(
                    f"{fname}:{ln}  {label} says {got} → actual {expect}   ({ctx})")

    if failures:
        print(f"FAIL — {len(failures)} doc-count mismatch(es)")
        for f in failures:
            print(f"  - {f}")
        print("\nFix the docs, or if the count's definition changed, update this test's SSOT too.")
        return 1

    print(f"ALL PASS — {checked} doc count(s) checked "
          f"(bundled {a['bundled']} · catalog {a['catalog_total']} · "
          f"tests {a['tests']} · guards {a['hooks']} · docs {a['docs']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
