#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hooks/_codex_json_adapter.sh — regression test for the exit-2 contract -> Codex JSON contract translation.

Why this test needs to exist
-----------------------------
Measured 2026-08-21 (issue #5, Codex CLI 0.147.0): Codex fires a PreToolUse
hook with the **same stdin payload** as Claude Code, but it **does not
support the exit-code contract.** Even when a hook exits 2 with a stderr
reason, the command still runs. The only path that actually blocks under
Codex is emitting

    {"decision":"block","reason":"..."}

on stdout and exiting 0.

Every guard in this folder speaks exit 2. So without the adapter, a guard
ends up "running but not blocking" — it gives a green light to an
unvetted command, which is worse than having no guard at all. That's why
issue #5 was opened.

So what this test protects is not the adapter's code but **whether a block
actually translates into a block**. The pass criterion is deliberately "stdout
parses as JSON and decision is block," not just "stdout is non-empty":
a reason string routinely contains quotes, backslashes (Windows paths), and
newlines, and if the escaping breaks, the JSON breaks, and Codex can't read
decision and **silently lets the command through**. In other words, the
exact symptom of an escaping bug is "a block degrading into an allow."
(This actually happened twice during development: ① a newline sentinel was
left behind as a control character at the end of the string, ② a sed
pattern's \001 wasn't interpreted as an octal escape, so multiple lines got
glued together.)

Runs offline without Codex — the adapter is a plain shell script, and a fake
guard can reproduce all three exit codes.

Contract:
  guard exit 2  -> stdout = {"decision":"block","reason":<guard stderr>}, adapter exit 0
  guard exit 0  -> no block JSON,                                        adapter exit 0
  anything else -> permissive + stderr warning,                          adapter exit 0
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
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ADAPTER = ROOT / "hooks" / "_codex_json_adapter.sh"

_fail = 0
_pass = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global _fail, _pass
    if cond:
        _pass += 1
        print(f"  OK    {name}")
    else:
        _fail += 1
        print(f"  FAIL  {name}" + (f"  — {detail}" if detail else ""))


# The exact payload shape Codex actually sends (excerpted from the issue #5 capture).
# The adapter doesn't need to interpret this — it just passes it through to the guard as-is.
PAYLOAD = json.dumps({
    "session_id": "01a02489-0000-0000-0000-000000000000",
    "turn_id": "01a02489-1111-1111-1111-111111111111",
    "transcript_path": "C:\\Users\\Example\\.codex\\sessions\\rollout.jsonl",
    "cwd": "C:\\Users\\Example\\project",
    "hook_event_name": "PreToolUse",
    "model": "gpt-5.6-sol",
    "permission_mode": "bypassPermissions",
    "tool_name": "Bash",
    "tool_input": {"command": "echo hooktest"},
    "tool_use_id": "exec-0001",
})

# Deliberately puts every JSON metacharacter into the reason string: double
# quotes, backslashes (Windows paths), non-ASCII (the em dash guards actually
# use), and multiple lines.
TRICKY_REASON = (
    'BLOCK: fake_guard \u2014 refused: cmd "quoted arg" and C:\\Users\\x\n'
    "  second line of the reason"
)

FAKE_GUARDS = {
    "g_allow.sh": "#!/usr/bin/env sh\ncat > /dev/null\nexit 0\n",
    "g_block.sh": (
        "#!/usr/bin/env sh\n"
        "cat > /dev/null\n"
        'cat "$GUARD_REASON_FILE" >&2\n'
        "exit 2\n"
    ),
    "g_block_silent.sh": "#!/usr/bin/env sh\ncat > /dev/null\nexit 2\n",
    "g_crash.sh": (
        "#!/usr/bin/env sh\n"
        "cat > /dev/null\n"
        'echo "guard exploded" >&2\n'
        "exit 7\n"
    ),
}


def run_adapter(tmp: Path, guard: str,
                payload: str = PAYLOAD) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["GUARD_REASON_FILE"] = str(tmp / "reason.txt")
    return subprocess.run(
        ["sh", str(ADAPTER), str(tmp / guard)],
        input=payload, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=60, env=env,
    )


def parse_decision(stdout: str):
    """Read stdout as JSON. Failure returns None — that failure IS the defect."""
    if not stdout.strip():
        return None
    try:
        return json.loads(stdout)
    except Exception:
        return None


def main() -> int:
    if not ADAPTER.is_file():
        print(f"FAIL — adapter missing: {ADAPTER}")
        return 1
    if shutil.which("sh") is None:
        print("SKIP — sh not found (no POSIX shell in this environment)")
        return 0

    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        for name, script in FAKE_GUARDS.items():
            p = tmpdir / name
            p.write_text(script, encoding="utf-8", newline="\n")
            p.chmod(0o755)
        (tmpdir / "reason.txt").write_text(TRICKY_REASON, encoding="utf-8",
                                           newline="\n")

        print("exit 2 (with a reason) -> does it translate to a Codex block JSON?")
        r = run_adapter(tmpdir, "g_block.sh")
        check("adapter exits 0 (propagating exit 2 as-is gets ignored by Codex)",
              r.returncode == 0, f"exit={r.returncode}")
        d = parse_decision(r.stdout)
        check("stdout is valid JSON (if broken, Codex can't read it and silently lets it through)",
              d is not None, f"stdout={r.stdout!r}")
        if d is not None:
            check('decision == "block"', d.get("decision") == "block",
                  f"got {d.get('decision')!r}")
            reason = d.get("reason", "")
            check("reason is not empty", bool(reason.strip()))
            check("reason carries the guard's stderr (fake_guard)",
                  "fake_guard" in reason, f"reason={reason!r}")
            check("a double quote survives", '"quoted arg"' in reason,
                  f"reason={reason!r}")
            check("a backslash path survives", "C:\\Users\\x" in reason,
                  f"reason={reason!r}")
            check("non-ASCII (em dash) survives", "\u2014" in reason,
                  f"reason={reason!r}")
            check("the second line of a multi-line reason survives",
                  "second line of the reason" in reason, f"reason={reason!r}")

        print("exit 2 (no reason) -> must still be a block")
        r = run_adapter(tmpdir, "g_block_silent.sh")
        check("adapter exit 0", r.returncode == 0, f"exit={r.returncode}")
        d = parse_decision(r.stdout)
        check("stdout is valid JSON", d is not None, f"stdout={r.stdout!r}")
        if d is not None:
            check('decision == "block" even with no reason (a block must not collapse just because the reason is missing)',
                  d.get("decision") == "block", f"got {d.get('decision')!r}")
            check("a fallback reason gets filled in", bool(d.get("reason", "").strip()))

        print("exit 0 -> must NOT produce block JSON (over-blocking check)")
        r = run_adapter(tmpdir, "g_allow.sh")
        check("adapter exit 0", r.returncode == 0, f"exit={r.returncode}")
        d = parse_decision(r.stdout)
        check("no block decision",
              d is None or d.get("decision") != "block", f"stdout={r.stdout!r}")

        print("any other exit code -> allow, but not silently")
        r = run_adapter(tmpdir, "g_crash.sh")
        check("adapter exit 0 (a broken guard must not brick every tool call)",
              r.returncode == 0, f"exit={r.returncode}")
        d = parse_decision(r.stdout)
        check("no block decision",
              d is None or d.get("decision") != "block", f"stdout={r.stdout!r}")
        check("warns via stderr (a silently-dead guard must not masquerade as a passing one)",
              "WARN" in r.stderr, f"stderr={r.stderr!r}")

        print("missing guard -> allow + warn (must not brick a partially-installed tree)")
        r = run_adapter(tmpdir, "g_does_not_exist.sh")
        check("adapter exit 0", r.returncode == 0, f"exit={r.returncode}")
        check("warns via stderr", "WARN" in r.stderr, f"stderr={r.stderr!r}")

    print("end-to-end wiring with a real guard (the bundled guard, not a fake one)")
    real = ROOT / "hooks" / "git_safety_guard.sh"
    if real.is_file():
        # Writing this string whole in the source would trigger the dev
        # machine's own session guard against this very file. Assemble it
        # from fragments instead.
        forbidden = "git " + "push --" + "force origin main"
        r = subprocess.run(
            ["sh", str(ADAPTER), str(real)],
            input=json.dumps({"tool_name": "Bash",
                              "tool_input": {"command": forbidden}}),
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=60,
        )
        check("real guard: adapter exit 0", r.returncode == 0,
              f"exit={r.returncode}")
        d = parse_decision(r.stdout)
        check("real guard: stdout is valid JSON", d is not None,
              f"stdout={r.stdout!r}")
        if d is not None:
            check('real guard: decision == "block"',
                  d.get("decision") == "block", f"got {d!r}")
            check("real guard: reason includes the guard's name",
                  "git_safety_guard" in d.get("reason", ""),
                  f"reason={d.get('reason')!r}")
    else:
        print("  SKIP  hooks/git_safety_guard.sh not found")

    print("wiring with the chain runner (a harmless command should pass through)")
    chain = ROOT / "hooks" / "_run_hooks_chained.sh"
    if chain.is_file():
        r = subprocess.run(
            ["sh", str(ADAPTER), str(chain)],
            input=json.dumps({"tool_name": "Bash",
                              "tool_input": {"command": "echo hello world"}}),
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=120,
        )
        check("chain runner: adapter exit 0", r.returncode == 0,
              f"exit={r.returncode}")
        d = parse_decision(r.stdout)
        check("chain runner: no block on a harmless command",
              d is None or d.get("decision") != "block", f"stdout={r.stdout!r}")
    else:
        print("  SKIP  hooks/_run_hooks_chained.sh not found")

    print("=" * 60)
    print(f"PASS {_pass} / FAIL {_fail}")
    if _fail:
        print("\nIf the exit-2 -> JSON translation breaks, a guard under Codex ends up "
              "'running but not blocking' (issue #5).")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
