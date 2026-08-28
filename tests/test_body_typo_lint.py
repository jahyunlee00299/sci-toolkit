#!/usr/bin/env python3
"""Regression test for body_typo_lint.py — bidirectional MUST FLAG / MUST NOT FLAG.

Run: python tests/test_body_typo_lint.py   (exit 0 = pass)

Cases were built by first reading the rules in
`skills/academic-term-rules/SKILL.md` §12/§12a/§12b, then asking "given this
rule, must this be flagged / must it not be flagged". Cases are not written to
fit the implementation — when the implementation disagrees with SKILL.md, the
implementation gets fixed.

This file is a thin runner that wraps body_typo_lint.py's --self-test logic so
it can be judged by exit code in CI/manual runs without a full pytest setup.
The actual cases and pass/fail logic live inside the script's own
self_test() (single source — so cases aren't kept duplicated between this
file and the script).
"""
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "skills" / "manuscript-pipeline" / "scripts" / "body_typo_lint.py"

# Rely on body_typo_lint.py setting up its own UTF-8 stdout/stderr guard at
# import time (wrapping the module again here double-wraps it, which closes
# the prior TextIOWrapper and produces "I/O operation on closed file" —
# measured).
spec = importlib.util.spec_from_file_location("body_typo_lint", str(SCRIPT_PATH))
body_typo_lint = importlib.util.module_from_spec(spec)
sys.modules["body_typo_lint"] = body_typo_lint
spec.loader.exec_module(body_typo_lint)


def test_lint_text_directly() -> int:
    """Separately from self_test(), directly exercise lint_text()/apply_auto_fix()
    to further verify AUTO-FIXABLE and REVIEW-ONLY don't cross-contaminate, and
    that --fix never touches REVIEW-ONLY (SKILL.md §12a/§12b: FLAG-ONLY, auto
    replacement is strictly forbidden — re-confirm this contract at the code level)."""
    fails = 0

    # 1) a REVIEW-ONLY target must remain unchanged in the text even after apply_auto_fix
    text = "The result after conversion.Here was clear."
    fixed = body_typo_lint.apply_auto_fix(text)
    if "conversion.Here" not in fixed:
        print("FAIL  apply_auto_fix touched a REVIEW-ONLY(§12a) target — strict-forbid violation")
        fails += 1
    else:
        print("PASS  apply_auto_fix leaves REVIEW-ONLY(§12a) targets untouched")

    # 2) apply_auto_fix must not touch inside a code fence even for an AUTO-FIXABLE target
    text = "```\n50 ul in the fence\n```\n"
    fixed = body_typo_lint.apply_auto_fix(text)
    if "50 ul in the fence" not in fixed:
        print("FAIL  apply_auto_fix touched inside a code fence")
        fails += 1
    else:
        print("PASS  apply_auto_fix does not touch inside a code fence")

    # 3) a count filtered out by the whitelist is counted, not silently dropped
    # (the extension dot in "data.Rmd" matches as a PUNCT_SPACE_FLAGS
    # candidate, but the §12a filename whitelist must keep it from being
    # reported as REVIEW-ONLY — and that fact must still show up in
    # whitelisted_count, i.e. never silently hidden).
    text = "Raw file was data.Rmd for this run."
    result = body_typo_lint.lint_text(text)
    if result.whitelisted_count < 1:
        print("FAIL  the whitelist-filtered count is not shown (silent-hiding violation)")
        fails += 1
    else:
        print(f"PASS  whitelist-filtered REVIEW-ONLY candidates are counted "
              f"({result.whitelisted_count} item(s))")

    return fails


def main() -> int:
    print("=== body_typo_lint.self_test() (MUST FLAG / MUST NOT FLAG, driven by SKILL.md §12/12a/12b) ===")
    ok = body_typo_lint.self_test()

    print("\n=== additional contract verification (apply_auto_fix never touches REVIEW-ONLY, etc.) ===")
    extra_fails = test_lint_text_directly()

    all_ok = ok and extra_fails == 0
    print()
    print("overall result:", "ALL PASS" if all_ok else "SOME FAILURES")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
