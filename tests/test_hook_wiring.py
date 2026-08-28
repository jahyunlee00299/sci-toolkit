#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Consistency check: guard scripts in hooks/ vs. _run_hooks_chained.sh's DEFAULT_GUARDS wiring.

_run_hooks_chained.sh hardcodes the list of guards to run in a shell variable
(DEFAULT_GUARDS). Add a new *_guard.sh under hooks/ without adding its name to
that list, and the file exists but is never called -- doctor.py's
check_hooks_config() only checks that hooks.json is valid JSON, it does not
look this deep into the chain's wiring. The reverse direction matters just as
much: if DEFAULT_GUARDS points at a file that doesn't exist, the chain runner
prints a "guard not found" warning on every invocation while that guard blocks
nothing (_run_hooks_chained.sh itself is designed to silently skip missing
files, so without this static check the gap only shows up when you actually
run it).
"""
from __future__ import annotations

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
HOOKS = ROOT / "hooks"
CHAIN = HOOKS / "_run_hooks_chained.sh"

# The chain runner itself and the payload-parsing helper are not "guards" --
# they correctly never appear in DEFAULT_GUARDS, so exclude them from the
# consistency comparison.
NON_GUARD_FILES = {"_run_hooks_chained.sh", "_payload_fields.sh"}


def declared_guards(chain_text: str) -> set[str]:
    m = re.search(r'DEFAULT_GUARDS="([^"]*)"', chain_text)
    if not m:
        return set()
    return set(m.group(1).split())


def actual_guard_files() -> set[str]:
    return {p.name for p in HOOKS.glob("*_guard.sh")} - NON_GUARD_FILES


def main() -> int:
    if not CHAIN.is_file():
        print("SKIP — hooks/_run_hooks_chained.sh not found")
        return 0

    chain_text = CHAIN.read_text(encoding="utf-8")
    declared = declared_guards(chain_text)
    actual = actual_guard_files()

    if not declared:
        print("FAIL — could not find DEFAULT_GUARDS in _run_hooks_chained.sh"
              " (the variable name or format changed — update this test)")
        return 1

    orphaned = actual - declared  # file exists but the chain never calls it
    dangling = declared - actual  # chain calls it but the file is missing

    fail = 0
    print(f"checking: hooks/*_guard.sh ({len(actual)}) vs DEFAULT_GUARDS ({len(declared)})")

    if orphaned:
        fail += 1
        print(f"  FAIL  present under hooks/ but not in DEFAULT_GUARDS (never runs): "
              f"{', '.join(sorted(orphaned))}")
    if dangling:
        fail += 1
        print(f"  FAIL  DEFAULT_GUARDS points at a file that does not exist: "
              f"{', '.join(sorted(dangling))}")

    if not fail:
        print("  OK    every guard file is wired, and every wired name exists")

    print("=" * 60)
    print(f"PASS {1 if not fail else 0} / FAIL {fail}")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
