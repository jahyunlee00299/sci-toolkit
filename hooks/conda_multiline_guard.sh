#!/usr/bin/env bash
# PreToolUse(Bash) hook — block multiline `python -c` under conda run.
#
# Rationale (session-log audit 2026-05-23):
#   `conda run ... python -c "<multiline>"` fails on Windows git-bash because
#   the shell mangles embedded newlines before conda sees them. 133 hits in
#   recent 40-session sample. #   but is repeatedly violated — a hard PreToolUse block is more reliable.
#
# Behavior: if the Bash command contains `conda run` AND `python -c` AND a
#   literal newline inside the JSON-decoded command, emit guidance and exit 2.
#   Single-line `python -c` is allowed.
#
# Exit codes: 0 = allow, 2 = block with message.
#
# Note: parsing is delegated to Python (json module) for correctness — a grep
#   fallback false-positives on JSON \" escape sequences.

input=$(cat 2>/dev/null)
[ -z "$input" ] && exit 0

# Resolve a python interpreter (shared detector)
PY=$(command -v python 2>/dev/null || command -v python3 2>/dev/null)
[ -z "$PY" ] && exit 0   # no python -> cannot parse safely, allow

verdict=$(printf '%s' "$input" | "$PY" -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    print("ALLOW"); sys.exit(0)
cmd = (d.get("tool_input") or {}).get("command", "")
if not cmd:
    print("ALLOW"); sys.exit(0)
has_conda = "conda run" in cmd
has_pyc = ("python -c" in cmd) or ("python3 -c" in cmd)
has_newline = "\n" in cmd
print("BLOCK" if (has_conda and has_pyc and has_newline) else "ALLOW")
' 2>/dev/null)

# [260626] Mitigate a false trigger on WSL (home PC) / headless delegation: this
#   BLOCK exists because "newlines get mangled in Windows git-bash". WSL bash
#   does not have that problem, so downgrade to advisory (exit 0) on WSL/headless.
#   The laptop's git-bash keeps the existing BLOCK.
_IS_WSL=0
[ -f /proc/version ] && grep -qiE 'microsoft|wsl' /proc/version 2>/dev/null && _IS_WSL=1
if [ "$verdict" = "BLOCK" ] && { [ "$_IS_WSL" = "1" ] || [ "${HEADLESS_DELEGATION:-0}" = "1" ]; }; then
    echo "[conda_multiline_guard] (WSL/headless advisory) conda run + multiline python -c detected — usually fine on WSL. Allowed (a .py file is still recommended)." >&2
    exit 0
fi

if [ "$verdict" = "BLOCK" ]; then
    cat >&2 <<'MSG'
[conda_multiline_guard] Blocked: conda run + multiline `python -c` fails on
Windows git-bash because newlines get mangled.

-> Instead: save it as a temp .py file and run that.
   e.g.) cat > /tmp/_run.py << 'EOF'
       <python code>
       EOF
       conda run -n <env> python /tmp/_run.py

Single-line `python -c "..."` is allowed.
MSG
    exit 2
fi

exit 0
