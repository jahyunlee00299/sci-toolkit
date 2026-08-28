#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bidirectional regression test for the environment-mismatch guards.

The failures all three guards block are recurring failures on the
Windows + git-bash combination:
  · conda_multiline_guard   — `conda run ... python -c "multiple\\nlines"` breaks on newlines
  · inline_multiline_guard  — an inline multiline script breaks on quotes/non-ASCII text
  · bash_env_mismatch_guard — accidentally feeding PowerShell syntax straight into a bash tool

Bidirectional for the same reason as the other guard tests: an
over-blocking guard gets disabled, and a disabled guard is the same as no
guard. Measure both "what must be blocked" and "what must be allowed"
together.

Note: do not pass case strings through a shell. The developer's own session
hooks can mistake it for a real command and block it (measured 2026-08-07).
Always assemble the payload inside Python and pass it only via stdin.
"""
from __future__ import annotations

import sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOKS = ROOT / "hooks"

_fail = 0
_pass = 0
_skip = 0

NL = "\n"  # used to create newlines inside a case


def _is_wsl() -> bool:
    try:
        text = Path("/proc/version").read_text(errors="ignore").lower()
    except OSError:
        return False
    return "microsoft" in text or "wsl" in text


# Per the 260626 decision, conda_multiline_guard.sh / inline_multiline_guard.sh
# deliberately downgrade a blocked multiline inline script on WSL (home PC)
# from BLOCK (exit 2) to advisory (exit 0 + stderr warning), because unlike
# git-bash, WSL bash doesn't mangle newlines. This test used to hard-code
# exit=2 as the expectation in every environment, which was why it only
# failed under WSL — the test, not the guard, hadn't accounted for the
# two-environment contract.
IS_WSL = _is_wsl()
WSL_ADVISORY_EXIT = 0 if IS_WSL else 2


def run_guard(guard: str, command: str) -> "tuple[int, str]":
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    proc = subprocess.run(
        ["sh", str(HOOKS / guard)],
        input=payload, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=60,
    )
    return proc.returncode, proc.stderr


# A case downgraded to WSL-advisory is also registered in ADVISORY_LABELS —
# so that when WSL returns exit=0, we can tell whether that's a genuine
# advisory downgrade (stderr warning present) versus detection itself
# silently breaking (no stderr).
ADVISORY_LABELS: set[tuple[str, str]] = set()

CASES: dict[str, list[tuple[str, str, int]]] = {
    "conda_multiline_guard.sh": [
        ("conda + multiline -c",
         'conda run -n myenv python -c "import os' + NL + 'print(os.getcwd())"',
         WSL_ADVISORY_EXIT),
        ("conda + single-line -c",
         'conda run -n myenv python -c "print(1)"', 0),
        ("conda + running a file",
         'conda run -n myenv python analysis.py --input data.csv', 0),
        ("command unrelated to conda", 'ls -la', 0),
    ],
    # What this guard catches is not `python -c` itself, but **a multiline
    # script inlined directly into a shell variable**. Confirmed by
    # measurement during the 260807 port that behavior matches the original
    # (the original also lets multiline python -c through — out of scope here).
    "inline_multiline_guard.sh": [
        ("multiline inlined into a variable",
         "content='''line1" + NL + "line2" + NL + "line3'''", WSL_ADVISORY_EXIT),
        # This guard's `python -c` check blocks **only when non-ASCII is
        # present**. Pure-ASCII multiline actually works fine on git-bash
        # (measured 260801), so blocking it would be pure friction — same
        # result, more round trips.
        ("multiline -c containing non-ASCII text",
         'python -c "d={\'한글\':1}' + NL + 'print(d)"', WSL_ADVISORY_EXIT),
        ("ASCII multiline -c passes",
         'python -c "a=1' + NL + 'b=2"', 0),
        ("writing a file via heredoc is the recommended pattern",
         "cat > /tmp/x.py << 'EOF'" + NL + "print(1)" + NL + "EOF", 0),
        ("single-line python", 'python -c "print(42)"', 0),
        ("running a script", 'python scripts/analyze.py --flag', 0),
        ("ordinary command", 'git status', 0),
    ],
    "bash_env_mismatch_guard.sh": [
        ("PowerShell cmdlet in bash", 'Get-Item "C:/Users/Public"', 2),
        ("$env: variable in bash", 'ls "$env:USERPROFILE/Documents"', 2),
        ("wrapped in powershell.exe is fine",
         'powershell.exe -NoProfile -Command "Get-Item C:/Users/Public"', 0),
        ("ordinary bash", 'ls -la /tmp', 0),
        ("running python", 'python --version', 0),
    ],
}

ADVISORY_LABELS.update({
    ("conda_multiline_guard.sh", "conda + multiline -c"),
    ("inline_multiline_guard.sh", "multiline inlined into a variable"),
    ("inline_multiline_guard.sh", "multiline -c containing non-ASCII text"),
})


def run_chain(command: str) -> "tuple[int, str]":
    """Run through the chain runner — measures the actual wiring path, not an individual hook."""
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    proc = subprocess.run(
        ["sh", str(HOOKS / "_run_hooks_chained.sh")],
        input=payload, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=120,
    )
    return proc.returncode, proc.stderr


def main() -> int:
    global _fail, _pass, _skip
    print("Bidirectional verification of environment-mismatch guards")
    print("=" * 60)

    for guard, cases in CASES.items():
        if not (HOOKS / guard).is_file():
            print(f"\n[{guard}] SKIP — file not found")
            _skip += 1
            continue
        print(f"\n[{guard}]")
        for label, cmd, want in cases:
            got, stderr = run_guard(guard, cmd)
            verb = "block" if want == 2 else "allow"
            if got != want:
                _fail += 1
                print(f"  FAIL  {verb}: {label} — expected exit={want}, got exit={got}")
                continue
            if IS_WSL and want == 0 and (guard, label) in ADVISORY_LABELS:
                # Distinguish "properly downgraded to advisory" from "detection
                # itself silently broke" by whether stderr carries the warning —
                # both give exit=0, so the exit code alone can't tell them apart.
                if "advisory" not in stderr:
                    _fail += 1
                    print(f"  FAIL  missing advisory warning: {label} — no 'advisory' in stderr "
                          f"(detection may itself be broken)")
                    continue
            _pass += 1

    # ── via the chain runner ────────────────────────────────────────────
    # Even if an individual hook passes, if it isn't registered in the chain
    # it blocks nothing in practice. Whether the wiring is actually alive can
    # only be measured through the real path (C-58: wiring is part of the feature).
    if (HOOKS / "_run_hooks_chained.sh").is_file():
        print("\n[_run_hooks_chained.sh] real wiring path")
        chain_advisory_labels = {"conda multiline", "variable-inlined multiline"}
        chain_cases = [
            ("conda multiline",
             'conda run -n e python -c "import os' + NL + 'print(1)"', WSL_ADVISORY_EXIT),
            ("PowerShell cmdlet", 'Get-Item "C:/Users/Public"', 2),
            ("variable-inlined multiline", "content='''a" + NL + "b'''", WSL_ADVISORY_EXIT),
            ("force push", 'git push --force origin main', 2),
            ("normal command", 'git status', 0),
            ("normal run", 'python scripts/run.py', 0),
        ]
        for label, cmd, want in chain_cases:
            got, stderr = run_chain(cmd)
            verb = "block" if want == 2 else "allow"
            if got != want:
                _fail += 1
                print(f"  FAIL  {verb}: {label} — expected exit={want}, got exit={got}")
                continue
            if IS_WSL and want == 0 and label in chain_advisory_labels:
                if "advisory" not in stderr:
                    _fail += 1
                    print(f"  FAIL  missing advisory warning: {label} — no 'advisory' in stderr "
                          f"(detection may itself be broken)")
                    continue
            _pass += 1
    else:
        print("\n[_run_hooks_chained.sh] SKIP — not present")
        _skip += 1

    print("=" * 60)
    print(f"pass {_pass} / fail {_fail}" + (f" / skip {_skip}" if _skip else ""))
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
