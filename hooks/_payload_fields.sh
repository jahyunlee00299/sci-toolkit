#!/usr/bin/env sh
# _payload_fields.sh — shared payload-field extraction for the guards.
#
# Why this file exists: the safety guards used to pull the command out of the
# hook payload with
#     grep -Eo '"command"[[:space:]]*:[[:space:]]*"[^"]*"'
# The `[^"]*` stops at the first quote INSIDE the JSON string, so a command
# containing a quoted argument was truncated there and everything after it was
# never scanned. Measured 2026-08-08 against the real hook path: force-push,
# `git reset --hard`, `cd "..." && rm -rf ...`, and a recursive `find` over
# OneDrive ALL passed unchallenged as soon as a quoted argument came first —
#     git commit -m "wip" && git push --force origin main     -> allowed
# The shipped tests missed it because every one of their cases used single
# quotes, which JSON does not escape, so the truncation never triggered.
#
# The fix is to parse the payload as JSON instead of pattern-matching it.
# python is already a hard dependency of three other guards in this folder.
#
# Contract:
#   extract_fields <payload> <field>...
#     Prints the named tool_input fields joined by spaces, with newlines
#     folded to spaces (every guard matches against a single flat line).
#
#   Fail-closed: if python is unavailable or the payload does not parse as
#   JSON, the ENTIRE raw payload is printed instead, so a guard over-matches
#   rather than silently letting a dangerous command through.
#
#   An empty result means the payload parsed cleanly and genuinely has no such
#   field (a Read call has no "command"), which is a real allow — not a
#   parse failure.

extract_fields() {
    _pf_payload="$1"
    shift
    _pf_py="$(command -v python 2>/dev/null || command -v python3 2>/dev/null || true)"
    if [ -z "$_pf_py" ]; then
        printf '%s' "$_pf_payload" | tr '\n' ' '
        return 0
    fi
    printf '%s' "$_pf_payload" | GUARD_FIELDS="$*" "$_pf_py" -c '
import json, os, sys

raw = sys.stdin.read()
fields = os.environ.get("GUARD_FIELDS", "command").split()

def fail_closed():
    # Unparseable payload: hand back everything so the caller still scans it.
    sys.stdout.write(raw.replace("\n", " "))
    sys.exit(0)

try:
    payload = json.loads(raw)
except Exception:
    fail_closed()
if not isinstance(payload, dict):
    fail_closed()
tool_input = payload.get("tool_input")
if not isinstance(tool_input, dict):
    fail_closed()

parts = [tool_input[f] for f in fields if isinstance(tool_input.get(f), str)]
sys.stdout.write(" ".join(parts).replace("\n", " "))
'
}
