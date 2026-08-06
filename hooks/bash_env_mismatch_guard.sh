#!/usr/bin/env bash
# PreToolUse(Bash) hook — bash/PowerShell environment-mismatch guard.
#
# Rationale (session-log self-improvement audit 2026-06-05):
#   Windows git-bash 에서 반복되는 실패 패턴:
#     * PS_var_in_bash (39): Bash 도구에 PowerShell 구문을 그대로 입력 →
#         `Get-Item ':USERPROFILE\OneDrive*'` 처럼 $env:USERPROFILE 의 $env 가
#         bash 에서 빈 문자열로 확장돼 `:USERPROFILE` 만 남아 실패.
#     * cmd_not_found_other (82): jq / python3 / zip 등 이 bash 환경에 없는 명령 가정.
#     * PS_cmdlet_in_bash (3): Out-File / Get-Content / Copy-Item 을 bash 라인으로 호출.
#   기존 env_workflow_guard 는 PS `&&`/scp/ssh-var 만 커버 → 이 케이스 미커버.
#
# Behavior: PS cmdlet / $env: / bare zip|jq|python3 이 Bash 도구의 command 로
#   들어오고 powershell.exe / pwsh 래퍼가 없으면 BLOCK(exit 2), 안내 출력.
#   powershell.exe -Command "..." 로 감싼 경우는 정상이므로 ALLOW.
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
[bash_env_mismatch_guard] 차단: Bash 도구에서 `$env:VAR` 는 PowerShell 구문이라 bash 가
빈 문자열로 확장합니다 (예: $env:USERPROFILE → `:USERPROFILE` 만 남아 실패).

→ Bash 도구 안에서는:
   - 홈 경로:  $HOME  또는  /c/Users/<사용자명>
   - PowerShell 이 꼭 필요하면 래핑:
       powershell.exe -NoProfile -Command "Get-Item \"$env:USERPROFILE\OneDrive*\""
   - 클라우드 동기화 폴더의 한글 경로는 와일드카드로 찾으세요:
       ls -d "$HOME"/OneDrive*/  (한글 리터럴을 bash 에 직접 넣지 말 것)
MSG
    exit 2 ;;
  PS_CMDLET)
    cat >&2 <<'MSG'
[bash_env_mismatch_guard] 차단: PowerShell cmdlet(Get-Item/Out-File/Copy-Item 등)을
Bash 도구 라인으로 직접 실행했습니다 → `command not found`.

→ 둘 중 하나로:
   - bash 네이티브로 변환: Get-Content→cat, Copy-Item→cp, Test-Path→[ -e ], Out-File→>
   - PS 가 꼭 필요하면 래핑: powershell.exe -NoProfile -Command "..."
     (한글/$env 포함 시 결과를 C:\Temp\out.txt 로 저장 후 bash 에서 읽기
MSG
    exit 2 ;;
  MISSING:jq)
    cat >&2 <<'MSG'
[bash_env_mismatch_guard] 차단: 이 bash 환경에 `jq` 가 없습니다 (자주 발생합니다).
→ 대신 python 으로:  python -c "import json,sys; d=json.load(open('f.json')); print(d['k'])"
MSG
    exit 2 ;;
  MISSING:zip)
    cat >&2 <<'MSG'
[bash_env_mismatch_guard] 차단: 이 bash 환경에 `zip` 이 없습니다.
→ python:  python -c "import zipfile; zipfile.ZipFile('o.zip','w').write('f')"
→ 또는 PS:  powershell.exe -NoProfile -Command "Compress-Archive -Path f -Dest o.zip"
   (docx 는 절대 zip 으로 재패킹 금지
MSG
    exit 2 ;;
  MISSING:python3)
    cat >&2 <<'MSG'
[bash_env_mismatch_guard] 차단: 이 환경에서 실행 명령은 `python3` 가 아니라 `python` 입니다.
→ `python` 사용. 훅/스크립트 안이라면 `command -v python` 로 인터프리터를 먼저 찾으세요.
MSG
    exit 2 ;;
esac

exit 0
