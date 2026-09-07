#!/usr/bin/env python3
"""Regression test for verify_numeric_claims.py — the patent numeric-claim gate.

Run: python tests/test_verify_numeric_claims.py   (exit 0 = pass)

Why this test exists: the script guards numbers that land inside a patent
claim's numeric limitation. A claim limitation supported by a false number is
patent-fatal, and the failure it was built for (a stated 91.9% yield whose
inputs re-derive to 72.6%) survived a human review pass that only checked
"does this number have a footnote". So the contracts below are checked at the
code level, not just via the script's own verdict line:

  1. self_test() still catches all three known arithmetic regressions and
     leaves the consistent control case alone (single source of cases — they
     live in the script, not duplicated here).
  2. UNRESOLVED is never reported as a pass. A claim the script could not
     check must be visibly distinct from a claim it checked and cleared;
     collapsing the two is how an unchecked number reaches a filing.
  3. The tolerance boundary actually discriminates — a value inside tolerance
     is CONSISTENT and one outside it is MISMATCH.
"""
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = (REPO_ROOT / "skills" / "patent-invention-disclosure"
               / "scripts" / "verify_numeric_claims.py")

spec = importlib.util.spec_from_file_location("verify_numeric_claims", str(SCRIPT_PATH))
vnc = importlib.util.module_from_spec(spec)
sys.modules["verify_numeric_claims"] = vnc
spec.loader.exec_module(vnc)


def _verdicts(claims, tol=0.02):
    return [r["verdict"] for r in vnc.verify_claims(claims, tol=tol)]


def test_contracts() -> int:
    """Contracts that must hold independently of self_test()'s own verdict."""
    fails = 0

    # 1) An unknown claim type must be UNRESOLVED — never CONSISTENT.
    #    UNRESOLVED means "not checked"; treating it as a pass is the failure
    #    mode this gate exists to prevent.
    v = _verdicts([{"type": "not-a-real-type", "label": "unknown type"}])
    if v != ["UNRESOLVED"]:
        print(f"FAIL  unknown claim type gave {v}, expected ['UNRESOLVED']")
        fails += 1
    else:
        print("PASS  unknown claim type is UNRESOLVED, not a silent pass")

    # 2) A structurally unusable claim (division by zero) must not come back
    #    CONSISTENT either.
    v = _verdicts([{"type": "yield", "label": "zero initial",
                    "initial": 0, "final": 10, "claimed_pct": 50}])
    if v == ["CONSISTENT"]:
        print("FAIL  a divide-by-zero yield claim was reported CONSISTENT")
        fails += 1
    else:
        print(f"PASS  a divide-by-zero yield claim is not CONSISTENT (got {v[0]})")

    # 3) The tolerance boundary discriminates in both directions.
    inside = _verdicts([{"type": "yield", "label": "inside tol",
                         "initial": 100, "final": 50, "claimed_pct": 50.5}])
    outside = _verdicts([{"type": "yield", "label": "outside tol",
                          "initial": 100, "final": 50, "claimed_pct": 60}])
    if inside != ["CONSISTENT"]:
        print(f"FAIL  a within-tolerance claim gave {inside}, expected CONSISTENT")
        fails += 1
    elif outside != ["MISMATCH"]:
        print(f"FAIL  an out-of-tolerance claim gave {outside}, expected MISMATCH")
        fails += 1
    else:
        print("PASS  tolerance boundary separates CONSISTENT from MISMATCH")

    return fails


def main() -> int:
    print("=== verify_numeric_claims.self_test() (3 known regressions + 1 control) ===")
    ok = vnc.self_test()

    print("\n=== additional contract verification (UNRESOLVED never passes, tolerance boundary) ===")
    extra_fails = test_contracts()

    all_ok = ok and extra_fails == 0
    print()
    print("overall result:", "ALL PASS" if all_ok else "SOME FAILURES")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
