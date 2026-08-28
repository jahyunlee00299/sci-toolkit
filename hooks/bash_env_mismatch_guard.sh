#!/usr/bin/env bash
# PreToolUse(Bash) hook — bash/PowerShell environment-mismatch guard.
#
# Rationale (session-log self-improvement audit 2026-06-05):
#   Recurring failure patterns in Windows git-bash:
#     * PS_var_in_bash (39): PowerShell syntax typed directly into the Bash
#         tool -> `Get-Item ':USERPROFILE\OneDrive*'`, where bash expands the
#         $env in $env:USERPROFILE to an empty string, leaving only
#         `:USERPROFILE` and failing.
#     * cmd_not_found_other (82): assumes commands (jq / python3 / zip / etc.)
#         that don't exist in this bash environment.
#     * PS_cmdlet_in_bash (3): calling Out-File / Get-Content / Copy-Item as a
#         plain bash line.
#   The existing env_workflow_guard only covers PS `&&`/scp/ssh-var — none of
#   these cases.
#
# Behavior: if a PS cmdlet / $env: / bare zip|jq|python3 shows up as the Bash
#   tool's command with no powershell.exe / pwsh wrapper, BLOCK (exit 2) and
#   print guidance. A command properly wrapped in
#   powershell.exe -Command "..." is fine, so ALLOW it.
#
# Exit codes: 0 = allow, 2 = block with message.

input=$(cat 2>/dev/null)
[ -z "$input" ] && exit 0

PY=$(command -v python 2>/dev/null || command -v python3 2>/dev/null)
[ -z "$PY" ] && exit 0   # no python -> cannot parse safely, allow

# Environment detection — this guard runs on BOTH the notebook (Git Bash, has
# `python`, no `python3`) and the home PC (WSL, has `python3`, no `python`).
# `python3` is the WRONG command only where a bare `python` exists. Likewise
# `jq`/`zip` are only "missing" if absent on THIS box. Detect at runtime and
# pass to the parser so the same hook file is correct on both machines.
HAVE_PYTHON=0; command -v python  >/dev/null 2>&1 && HAVE_PYTHON=1
HAVE_JQ=0;     command -v jq      >/dev/null 2>&1 && HAVE_JQ=1
HAVE_ZIP=0;    command -v zip     >/dev/null 2>&1 && HAVE_ZIP=1
export GUARD_HAVE_PYTHON="$HAVE_PYTHON" GUARD_HAVE_JQ="$HAVE_JQ" GUARD_HAVE_ZIP="$HAVE_ZIP"

verdict=$(printf '%s' "$input" | "$PY" -c '
import json, re, sys
try:
    d = json.load(sys.stdin)
except Exception:
    print("ALLOW"); sys.exit(0)
cmd = (d.get("tool_input") or {}).get("command", "")
if not cmd:
    print("ALLOW"); sys.exit(0)

# --- exclude FILE DATA, not commands, from scanning ---
# 1) heredoc bodies (`cat << EOF > f.py ... EOF`) are file contents, not shell.
# 2) inside `ssh host "...remote..."` the remote box is Linux where python3/jq/zip
#    ARE the right commands — do not flag those. Strip remote ssh payloads too.
def strip_noise(s):
    pat = re.compile(r"<<-?\s*([\x27\x22]?)([A-Za-z_][A-Za-z0-9_]*)\1.*?\n\2\b", re.DOTALL)
    prev = None
    while prev != s:
        prev = s
        s = pat.sub("\n<<HEREDOC>>\n", s, count=1)
    # ssh <host> "...."  /  ssh <host> ....  remote payload -> drop quoted payload
    s = re.sub(r"\bssh\s+\S+\s+([\x22\x27]).*?\1", " ssh <REMOTE> ", s, flags=re.DOTALL)
    return s

scan = strip_noise(cmd)
low = scan.lower()
ps_wrapped = ("powershell" in low) or ("pwsh" in low)

CMD_START = r"(?:^|[\n;|&(){}]|\|\||&&|`)\s*"

# --- 1) PowerShell $env: variable used raw in bash (the :USERPROFILE bug) ---
if not ps_wrapped and re.search(r"\$env:[A-Za-z_]", scan):
    print("ENV_VAR"); sys.exit(0)

# --- 2) PowerShell cmdlets issued as a bash command (Verb-Noun at cmd boundary) ---
PS_CMDLETS = (r"Get-Item|Get-ChildItem|Get-Content|Set-Content|Out-File|Copy-Item|"
              r"Move-Item|Remove-Item|New-Item|Test-Path|Select-Object|Where-Object|"
              r"ForEach-Object|Select-String|Measure-Object|Sort-Object|Get-Process")
if not ps_wrapped and re.search(CMD_START + r"(?:" + PS_CMDLETS + r")\b", scan):
    print("PS_CMDLET"); sys.exit(0)

# --- 3) commands not present in THIS bash env ---
#   python3 -> only wrong where a bare `python` exists (notebook Git Bash).
#       On the home PC (WSL) python3 IS correct, so do not flag it there.
#   jq / zip -> flag only if actually absent on this box.
import os
have_python = os.environ.get("GUARD_HAVE_PYTHON") == "1"
have_jq     = os.environ.get("GUARD_HAVE_JQ") == "1"
have_zip    = os.environ.get("GUARD_HAVE_ZIP") == "1"
missing = []
if have_python:   missing.append("python3")   # python3 wrong only when python exists
if not have_jq:   missing.append("jq")
if not have_zip:  missing.append("zip")
if missing:
    m = re.search(CMD_START + r"(" + "|".join(missing) + r")\b", scan)
    if m:
        print("MISSING:" + m.group(1)); sys.exit(0)

print("ALLOW")
' 2>/dev/null)

case "$verdict" in
  ENV_VAR)
    cat >&2 <<'MSG'
[bash_env_mismatch_guard] BLOCKED: `$env:VAR` is PowerShell syntax, and inside
the Bash tool bash expands it to an empty string (e.g. $env:USERPROFILE ->
only `:USERPROFILE` survives, and the command fails).

-> Inside the Bash tool:
   - Home path: $HOME  or  /c/Users/<username>
   - If PowerShell is genuinely needed, wrap it:
       powershell.exe -NoProfile -Command "Get-Item \"$env:USERPROFILE\OneDrive*\""
   - For Korean-named paths under a cloud-sync folder, use a wildcard:
       ls -d "$HOME"/OneDrive*/  (never put a Korean literal directly into bash)
MSG
    exit 2 ;;
  PS_CMDLET)
    cat >&2 <<'MSG'
[bash_env_mismatch_guard] BLOCKED: a PowerShell cmdlet (Get-Item/Out-File/
Copy-Item, etc.) was run directly as a Bash tool line -> `command not found`.

-> Do one of the following:
   - Convert to bash-native: Get-Content->cat, Copy-Item->cp, Test-Path->[ -e ],
     Out-File->>
   - If PS is genuinely needed, wrap it: powershell.exe -NoProfile -Command "..."
     (if the output contains Korean/$env, save it to C:\Temp\out.txt and read
     that from bash)
MSG
    exit 2 ;;
  MISSING:jq)
    cat >&2 <<'MSG'
[bash_env_mismatch_guard] BLOCKED: `jq` is not available in this bash
environment (a common trap here).
-> Use python instead:  python -c "import json,sys; d=json.load(open('f.json')); print(d['k'])"
MSG
    exit 2 ;;
  MISSING:zip)
    cat >&2 <<'MSG'
[bash_env_mismatch_guard] BLOCKED: `zip` is not available in this bash
environment.
-> python:  python -c "import zipfile; zipfile.ZipFile('o.zip','w').write('f')"
-> or PS:  powershell.exe -NoProfile -Command "Compress-Archive -Path f -Dest o.zip"
   (never re-zip a docx by hand — repacking corrupts it)
MSG
    exit 2 ;;
  MISSING:python3)
    cat >&2 <<'MSG'
[bash_env_mismatch_guard] BLOCKED: in this environment the interpreter is
`python`, not `python3`.
-> Use `python`. Inside a hook/script, find the interpreter first with
   `command -v python`.
MSG
    exit 2 ;;
esac

exit 0
