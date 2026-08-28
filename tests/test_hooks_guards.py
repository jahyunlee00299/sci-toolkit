#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bidirectional regression test for the hooks/ safety guards.

A hook must prove it "actually fires", not just that it was "installed". Wiring
it up without measuring whether it fires leaves a silently dead guard that
everyone believes is on.

Why bidirectional:
  Checking MUST BLOCK alone misses over-blocking (a guard that stops legitimate
  work). And an over-blocking guard gets turned off by the user, which ends up
  protecting nothing at all. So "what must be blocked" and "what must be let
  through" are checked with equal weight.

Contract:
  exit 0 = allow, exit 2 = block (any other code is a contract violation)
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
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOKS = ROOT / "hooks"

_fail = 0
_pass = 0
_skip = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global _fail, _pass
    if cond:
        _pass += 1
    else:
        _fail += 1
        print(f"  FAIL  {name}" + (f"  — {detail}" if detail else ""))


def run_guard(guard: str, command: str, cwd: Path | None = None) -> int:
    """Feed a Bash tool-call payload into the guard and get back its exit code."""
    payload = json.dumps({
        "tool_name": "Bash",
        "tool_input": {"command": command},
    })
    proc = subprocess.run(
        ["sh", str(HOOKS / guard)],
        input=payload, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        cwd=str(cwd) if cwd else None, timeout=60,
    )
    return proc.returncode


# (description, command, expected exit)  — 2=block, 0=allow
GIT_CASES = [
    # must block
    ("force push",            "git push --force origin main", 2),
    ("force push -f",         "git push -f origin feature", 2),
    ("reset --hard",          "git reset --hard HEAD~3", 2),
    ("config --global",       "git config --global user.email a@b.c", 2),
    ("branch -D",             "git branch -D old-feature", 2),
    ("hook bypass no-verify", "git commit --no-verify -m 'skip checks'", 2),
    ("hook bypass hooksPath", "git -c core.hooksPath=/dev/null commit -m x", 2),
    # must allow — everyday git operations
    ("status",                "git status", 0),
    ("normal push",           "git push origin feature/my-work", 0),
    ("commit",                "git commit -m 'fix: correct the unit label'", 0),
    ("pull",                  "git pull --ff-only", 0),
    ("diff",                  "git diff --stat", 0),
    ("branch create",         "git checkout -b feature/new", 0),
    ("log",                   "git log --oneline -10", 0),
    ("soft reset",            "git reset --soft HEAD~1", 0),
    ("add",                   "git add specific_file.py", 0),
    # --- double-quote truncation regression (measured 2026-08-08) -----------
    # Back when the guard extracted the payload with
    # grep '"command"...:"[^"]*"', a double quote inside the command is
    # escaped as \" in JSON, so extraction cut off right there — meaning
    # everything dangerous after the quote was never inspected at all. The
    # three cases below are the actual shapes that all passed (exit 0) back
    # then — using a quote in a commit message is not an edge case but the
    # default, so the single most common shape was also the bypass shape.
    # The prior cases missed this because they all used single quotes (JSON
    # does not escape single quotes, so no truncation occurred there).
    ("force push, after a quote",  'git commit -m "wip" && git push --force origin main', 2),
    ("reset --hard, after a quote", 'git commit -m "save" && git reset --hard HEAD~3', 2),
    ("config --global, after a quote",
     'git commit -m "x" && git config --global user.email a@b.c', 2),
    ("double-quoted commit (must still pass)", 'git commit -m "fix: correct the unit label"', 0),
]

DELETE_CASES = [
    ("rm -rf",        "rm -rf /some/path", 2),
    ("sudo rm",       "sudo rm -r /etc/thing", 2),
    ("ls",            "ls -la", 0),
    ("cat",           "cat README.md", 0),
    # double-quote truncation regression — a Windows path with a space
    # requires quotes, so this shape is the standard, not an exception.
    ("rm -rf, after a quoted cd",  'cd "/c/Users/me/My Project" && rm -rf build', 2),
    ("rm -rf, quoted path",     'rm -rf "/c/Users/me/My Project/out"', 2),
    ("double-quoted echo (must still pass)", 'echo "nothing is deleted here"', 0),
]

CLOUD_CASES = [
    ("find on OneDrive", "find ~/OneDrive -name '*.docx'", 2),
    ("ls -R on Dropbox", "ls -R ~/Dropbox/data", 2),
    ("single read",      "cat ~/OneDrive/notes.md", 0),
    ("plain find",       "find ./src -name '*.py'", 0),
    # double-quote truncation regression — cloud folder names commonly have
    # spaces (e.g. "OneDrive - Institution Name"), so writing them WITHOUT
    # quotes is actually the rare case.
    ("find, quoted OneDrive path",
     'find "/c/Users/me/OneDrive - Univ/store" -name "*.pdf"', 2),
    ("ls -R, quoted path", 'ls -R "/c/Users/me/OneDrive - Univ/data"', 2),
    ("quoted single read (must still pass)",
     'cat "/c/Users/me/OneDrive - Univ/notes.md"', 0),
]

# What the real hook actually calls is not the individual guards but this
# wrapper. Testing only the individual guards means the test keeps passing
# even if the chain is broken (the wrapper mis-forwards the payload, or fails
# to stop at the first block) — a check that never measures the wiring cannot
# prove it fires. The fake credential is assembled at runtime. secret_scan_guard
# only fires on a complete string, but writing the token as one contiguous
# literal in source makes the doctor's SENTINEL scan flag this very file as a
# leak (measured). Adding this file to the scan's exception list is not the
# answer — that would also stop it from ever catching a real leak that lands
# in this file.
_FAKE_SK_TOKEN = "sk-" + "a1b2c3d4e5" * 3

CHAINED_CASES = [
    ("secret: reading secrets.json", "Read",
     {"file_path": "/home/me/.claude/secrets.json"}, 2),
    ("secret: sk- token", "Bash",
     {"command": f"curl -H 'x: {_FAKE_SK_TOKEN}'"}, 2),
    ("secret: a placeholder passes", "Bash",
     {"command": "export API_KEY=your_api_key_here"}, 0),
    ("git: force push, after a quote", "Bash",
     {"command": 'git commit -m "wip" && git push --force origin main'}, 2),
    ("delete: rm -rf, after a quoted cd", "Bash",
     {"command": 'cd "/c/Users/me/My Project" && rm -rf build'}, 2),
    ("cloud: find, quoted OneDrive", "Bash",
     {"command": 'find "/c/Users/me/OneDrive - Univ" -name "*.docx"'}, 2),
    ("normal: git log", "Bash", {"command": "git log --oneline -5"}, 0),
    ("normal: plain file read", "Read", {"file_path": "/home/me/project/README.md"}, 0),
    ("normal: single-line python -c", "Bash",
     {"command": 'python -c "import sys; print(sys.version)"'}, 0),
]


def run_chained(tool_name: str, tool_input: dict) -> int:
    """Pass the payload through the real hook path (_run_hooks_chained.sh)."""
    payload = json.dumps({"tool_name": tool_name, "tool_input": tool_input},
                         ensure_ascii=False)
    proc = subprocess.run(
        ["sh", str(HOOKS / "_run_hooks_chained.sh")],
        input=payload, capture_output=True, text=True,
        encoding="utf-8", errors="replace", cwd=str(ROOT), timeout=120,
    )
    return proc.returncode


def chained_section() -> None:
    global _skip
    if not (HOOKS / "_run_hooks_chained.sh").is_file():
        print("\n[chained execution path] SKIP — _run_hooks_chained.sh missing")
        _skip += 1
        return
    print("\n[chained execution path] _run_hooks_chained.sh (the entry point the real hook calls)")
    for label, tool, tin, want in CHAINED_CASES:
        got = run_chained(tool, tin)
        verb = "block" if want == 2 else "allow"
        check(f"{verb}: {label}", got == want,
              f"expected exit={want}, got exit={got}  payload={tin!r}")


def section(title: str, guard: str, cases: list[tuple[str, str, int]],
            cwd: Path | None = None) -> None:
    global _skip
    if not (HOOKS / guard).is_file():
        print(f"\n[{title}] SKIP — {guard} missing")
        _skip += 1
        return
    print(f"\n[{title}] {guard}")
    for label, cmd, want in cases:
        got = run_guard(guard, cmd, cwd)
        verb = "block" if want == 2 else "allow"
        check(f"{verb}: {label}", got == want,
              f"expected exit={want}, got exit={got}  cmd={cmd!r}")


def main() -> int:
    print("hooks/ safety guard bidirectional verification")
    print("=" * 60)

    # The fork case only makes sense in a repo that has an upstream remote.
    # Build a temp repo with a real remote attached to reproduce it — so we
    # don't just look at the regex and assume "it'll catch it".
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "forked"
        repo.mkdir()
        git_ok = shutil.which("git") is not None
        if git_ok:
            for args in (["init", "-q"],
                         ["remote", "add", "origin", "https://example.invalid/me/fork.git"],
                         ["remote", "add", "upstream", "https://example.invalid/them/orig.git"]):
                subprocess.run(["git", *args], cwd=str(repo),
                               capture_output=True, text=True)

        section("git safety guard", "git_safety_guard.sh", GIT_CASES)

        if git_ok:
            print("\n[fork protection] in a repo with an upstream remote")
            fork_cases = [
                ("upstream push",        "git push upstream main", 2),
                ("gh pr without --repo", "gh pr create --title x --body y", 2),
                ("origin push (must pass)", "git push origin feature/x", 0),
                ("gh pr with --repo",    "gh pr create --repo me/fork --title x", 0),
            ]
            for label, cmd, want in fork_cases:
                got = run_guard("git_safety_guard.sh", cmd, repo)
                verb = "block" if want == 2 else "allow"
                check(f"{verb}: {label}", got == want,
                      f"expected exit={want}, got exit={got}  cmd={cmd!r}")
        else:
            print("\n[fork protection] SKIP — git not available")

    section("destructive-delete guard", "destructive_delete_guard.sh", DELETE_CASES)
    section("cloud path guard", "cloud_path_guard.sh", CLOUD_CASES)
    chained_section()

    print("=" * 60)
    print(f"passed {_pass} / failed {_fail}" + (f" / skipped {_skip}" if _skip else ""))
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
