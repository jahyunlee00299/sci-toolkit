#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Equivalence test for the hook runner's speed-ups (prefilter + parse-once).

_run_hooks_chained.sh skips a guard when a keyword that guard needs is absent
from the raw payload, and hands the parsed command/file_path to the guards in
SCI_HOOK_* variables. Neither may change what gets blocked. This test runs the
same payloads through the chain with the prefilter ON and OFF
(SCI_HOOK_PREFILTER=0 is the kill switch and runs every guard as before) and
requires identical exit code, stdout and stderr, plus the expected verdict for
the hazard cases, so a prefilter that lets something through fails here.

Payloads are assembled inside Python and passed via stdin only.
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
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHAIN = ROOT / "hooks" / "_run_hooks_chained.sh"

_fail = 0
_pass = 0


def run(payload: "str | bytes", prefilter: "str | None") -> "tuple[int, bytes, bytes]":
    env = dict(os.environ)
    env.pop("SCI_HOOK_PREFILTER", None)
    env.pop("HEADLESS_DELEGATION", None)
    if prefilter is not None:
        env["SCI_HOOK_PREFILTER"] = prefilter
    data = payload if isinstance(payload, bytes) else payload.encode("utf-8")
    p = subprocess.run(["sh", str(CHAIN)], input=data, capture_output=True, env=env, timeout=120)
    return p.returncode, p.stdout, p.stderr


def bash(cmd: str) -> str:
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}})


def tool(name: str, **tin) -> str:
    return json.dumps({"tool_name": name, "tool_input": tin})


# Pieces are joined at runtime so this file does not itself contain the
# command strings the guards look for.
RM = "r" + "m"
FORCE = "--" + "force"
HARD = "--" + "hard"
TOKEN = "".join(["Ab3dE5fG", "7hJ9kL1m", "N3pQ5rS7", "tU9v"])  # fake, split for leak scanners
OD = "One" + "Drive"
USERS = "/c/" + "Users"
PHOME = "/" + "home/u"
KR_OD = OD + " - " + "예시대학교"

# (label, payload, expected exit or None = parity only)
CASES = [
    ("ls", bash("ls -la"), 0),
    ("git status", bash("git status"), 0),
    ("git push force", bash("git push " + FORCE + " origin main"), 2),
    ("git push -f", bash("git push -f origin feature"), 2),
    ("quoted first, then force push", bash('git commit -m "wip" && git push ' + FORCE), 2),
    ("reset hard", bash("git reset " + HARD + " HEAD~1"), 2),
    ("branch -D", bash("git branch -D old"), 2),
    ("rm recursive force", bash(RM + " -rf /tmp/x"), 2),
    ("quoted cd then rm", bash('cd "' + USERS + '/me/My Project" && ' + RM + " -rf build"), 2),
    ("find -delete", bash("find . -delete"), 2),
    ("git clean", bash("git clean -fdx"), 2),
    ("rd /s", bash("RD /S /Q build"), 2),
    ("find on OneDrive", bash("find ~/" + OD + " -name '*.docx'"), 2),
    ("ls -R Dropbox", bash("ls -R ~/Dropbox/data"), 2),
    ("cat glob on OneDrive", bash("cat ~/" + OD + "/*.md"), 2),
    ("single OneDrive read", bash("cat ~/" + OD + "/notes.md"), 0),
    ("sk- token", bash("curl -H 's" + "k-" + TOKEN + "'"), 2),
    ("api_key assignment", bash("api_key = " + "q" * 24), 2),
    ("placeholder key", bash('api_key = "YOUR_API_KEY_HERE_placeholder"'), 0),
    ("write secrets.json", tool("Write", file_path="/x/secrets.json", content="x"), 2),
    ("read id_rsa", tool("Read", file_path=PHOME + "/.ssh/id_rsa"), 2),
    ("write with hazard text only", tool("Write", file_path="/tmp/a.py", content=RM + " -rf x; git push " + FORCE), 0),
    ("read plain", tool("Read", file_path="/etc/hostname"), 0),
    ("powershell in bash", bash("Get-ChildItem ."), 2),
    ("env var in bash", bash("ls $env:USERPROFILE"), 2),
    ("wrapped powershell", bash('powershell.exe -Command "Get-Item $env:X"'), 0),
    ("heredoc write", bash("cat <<'EOF' > f.py\nprint(1)\nEOF"), 0),
    ("-e first", bash("-e"), 0),
    ("-n with force push", bash("-n git push " + FORCE), 2),
    ("Korean path", bash("ls " + USERS + "/홍길동/" + KR_OD + "/저장소"), 0),
    ("Korean find on OneDrive", bash('find "' + USERS + '/홍길동/' + KR_OD + '" -name x'), 2),
    ("Korean rm", bash(RM + " -rf 한글"), 2),
    # escapes that can hide a keyword from the raw text: prefilter must step aside
    ("unicode-escaped rm", '{"tool_name":"Bash","tool_input":{"command":"\\u0072m -rf x"}}', 2),
    ("unicode-escaped force", '{"tool_name":"Bash","tool_input":{"command":"git push --\\u0066orce"}}', 2),
    ("escaped slash find", '{"tool_name":"Bash","tool_input":{"command":"find ~\\/' + OD + ' -name x"}}', 2),
    ("escaped tab rm", '{"tool_name":"Bash","tool_input":{"command":"' + RM + '\\t-rf x"}}', 2),
    # not a plain payload
    ("empty", "", None),
    ("not json", "not json " + RM + " -rf x", None),
    ("truncated", '{"tool_name":"Bash","tool_input":{"command":"' + RM + " -rf x", None),
    ("tool_input not a dict", json.dumps({"tool_name": "Bash", "tool_input": "x"}), None),
    ("pretty printed", json.dumps({"tool_name": "Bash", "tool_input": {"command": RM + " -rf x"}}, indent=2), 2),
    ("very long command", bash("echo " + "y" * 9000 + " git status"), 0),
    ("broken utf-8", b'{"tool_name":"Bash","tool_input":{"command":"find x \xff -delete"}}', None),
]


def main() -> int:
    global _fail, _pass
    print("Prefilter / parse-once equivalence (chain with prefilter ON vs OFF)")
    print("=" * 60)
    for label, payload, want in CASES:
        on = run(payload, None)
        off = run(payload, "0")
        if on[0] != off[0] or on[1] != off[1]:
            _fail += 1
            print(f"  FAIL  {label} — prefilter changed the verdict: on={on[0]} off={off[0]}")
            continue
        if on[2] != off[2]:
            _fail += 1
            print(f"  FAIL  {label} — prefilter changed stderr")
            continue
        if want is not None and on[0] != want:
            _fail += 1
            print(f"  FAIL  {label} — expected exit={want}, got exit={on[0]}")
            continue
        _pass += 1

    # The parsed command travels through eval: a quote in it must stay data.
    for label, cmd in [
        ("quote-break attempt", "'; echo INJECTED; echo '"),
        ("command substitution", "$(echo INJECTED)"),
        ("backticks", "`echo INJECTED`"),
    ]:
        rc, out, err = run(bash("git status " + cmd), None)
        if b"INJECTED" in out or b"INJECTED" in err.replace(cmd.encode(), b""):
            _fail += 1
            print(f"  FAIL  {label} — command text was executed")
        else:
            _pass += 1

    print("=" * 60)
    print(f"pass {_pass} / fail {_fail}")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
