#!/usr/bin/env bash
# PreToolUse(Bash) hook — block multiline inline scripts in Bash commands.
#
# Rationale (self-improvement audit 2026-06-05):
#   heredoc_pysyntax (35 hits in June): inline `python -c "<multiline>"` (no conda)
#   and `content='''...multiline...'''` variable assignments break on git-bash via
#   newline/quote/encoding mangling (e.g. `content='''$ErrorActionPreference...`
#   → SyntaxError, or unicode-escape errors on Korean text).
#   #   but it keeps recurring → hard PreToolUse block is more reliable.
#   conda_multiline_guard only covers the `conda run` subset → this covers the rest.
#
# Behavior: BLOCK (exit 2) when the Bash command contains a multiline
#   `python -c` / `python3 -c` (without conda — that is the other hook's job, but
#   we also catch it to be safe) OR a multiline single/triple-quoted heredoc-style
#   inline payload assigned to a shell var (content=, script=) spanning newlines.
#   Single-line `python -c` and normal multi-statement bash stay allowed.
#
# Exit codes: 0 = allow, 2 = block with message.

input=$(cat 2>/dev/null)
[ -z "$input" ] && exit 0

# [260626] WSL(집컴) 오발동 완화: 이 BLOCK의 근거는 "git-bash(노트북)에서 멀티라인
#   python -c / 따옴표 페이로드가 줄바꿈·인코딩으로 깨진다"는 것. WSL bash는 이 깨짐이
#   없으므로(POSIX 정상) WSL에서는 BLOCK이 순수 오발동 → 헤드리스 goal loop를 자주 멈춤.
#   WSL 감지 시 advisory(exit 0 + stderr)로 강등. 노트북 git-bash는 기존 BLOCK 유지.
#   킬스위치/통합: HEADLESS_DELEGATION=1이면 무조건 advisory(위임 게이트 통합, Task #2).
_IS_WSL=0
[ -f /proc/version ] && grep -qiE 'microsoft|wsl' /proc/version 2>/dev/null && _IS_WSL=1
if [ "$_IS_WSL" = "1" ] || [ "${HEADLESS_DELEGATION:-0}" = "1" ]; then
    _ADVISORY=1
fi

PY=$(command -v python 2>/dev/null || command -v python3 2>/dev/null)
[ -z "$PY" ] && exit 0   # no python -> cannot parse safely, allow

verdict=$(printf '%s' "$input" | "$PY" -c '
import json, re, sys
try:
    d = json.load(sys.stdin)
except Exception:
    print("ALLOW"); sys.exit(0)
cmd = (d.get("tool_input") or {}).get("command", "")
if not cmd or "\n" not in cmd:
    print("ALLOW"); sys.exit(0)

# IMPORTANT — heredoc to a file is the RECOMMENDED pattern, not the bug.
#   `cat << EOF > file.py ... EOF`  writes a script to disk (good). The bytes
#   between the heredoc delimiters are FILE DATA, not shell commands, so we must
#   NOT scan them. Strip every heredoc body before looking for inline scripts.
def strip_heredocs(s):
    # match  <<-?  ['\"]?DELIM['\"]?  ...  \nDELIM   (non-greedy, multiline)
    pat = re.compile(r"<<-?\s*([\x27\x22]?)([A-Za-z_][A-Za-z0-9_]*)\1.*?\n\2\b",
                     re.DOTALL)
    prev = None
    while prev != s:
        prev = s
        s = pat.sub("\n<<HEREDOC_STRIPPED>>\n", s, count=1)
    return s

scan = strip_heredocs(cmd)
# if the command is ONLY a heredoc write (nothing risky left), allow.
if "\n" not in scan:
    print("ALLOW"); sys.exit(0)

# A) multiline  python -c "...."  /  python3 -c ....  (true inline, not heredoc)
# FIX 260613: 여는 따옴표~닫는 따옴표 구간 안에 \n 이 있을 때만 차단.
#   (구버전은 m.end() 이후 명령 전체에서 \n 을 찾아, 뒤에 다른 줄이 더 있는
#    멀티스텝 bash 안의 단일라인 python -c 를 오탐 차단했음 — 실측 재발.)
m = re.search(r"python3?\s+-c\s*([\x22\x27])", scan)
if m:
    q = m.group(1)               # 여는 따옴표
    rest = scan[m.end():]        # 따옴표 바로 다음부터
    close = rest.find(q)         # 같은 종류 닫는 따옴표 위치
    span = rest if close == -1 else rest[:close]  # 미종료면 끝까지(안전측)
    if "\n" in span:
        # [260801] 조건 축소 — 측정으로 근거를 나눔.
        #   git-bash에서 멀티라인 `python -c` 를 실제로 실행해 보면
        #     · 줄바꿈/따옴표 → 정상 동작 (rc=0, 여러 줄 그대로 실행됨)
        #     · 한글 등 비ASCII → cp949 로 깨짐 ({"한글":1} → {"��":1})
        #   즉 깨지는 원인은 "멀티라인"이 아니라 "비ASCII 페이로드"다. 종전에는 둘을
        #   묶어 차단해, 순수 ASCII 멀티라인까지 매번 파일로 우회하게 만들었다(순수 마찰:
        #   결과물은 동일하고 왕복만 늘어난다). 비ASCII가 실제로 들어있을 때만 차단한다.
        if any(ord(ch) > 127 for ch in span):
            print("PYC"); sys.exit(0)
        print("ALLOW"); sys.exit(0)

# B) shell var holding a multiline inline script (triple-quote heredoc style).
am = re.search(r"\b(?:content|script|code|payload|ps1?|body)\s*=\s*(\x27\x27\x27|\x22\x22\x22|\x27|\x22)", scan)
if am and "\n" in scan[am.end():]:
    print("VARHEREDOC"); sys.exit(0)

print("ALLOW")
' 2>/dev/null)

# [260626] WSL/헤드리스 위임: 멀티라인 깨짐이 없는 환경이므로 BLOCK→advisory 강등.
if [ "${_ADVISORY:-0}" = "1" ] && { [ "$verdict" = "PYC" ] || [ "$verdict" = "VARHEREDOC" ]; }; then
    echo "[inline_multiline_guard] (WSL/headless advisory) 멀티라인 인라인 감지 — WSL에선 보통 정상이나 가급적 스크립트 파일 경유 권장. 통과." >&2
    exit 0
fi

case "$verdict" in
  PYC)
    cat >&2 <<'MSG'
[inline_multiline_guard] 차단: 멀티라인 `python -c "..."` 안에 비ASCII(한글 등)가
있습니다. git-bash 콘솔이 cp949 라서 인코딩이 깨집니다 — {"한글":1} 이 {"??":1} 이 됩니다.
(순수 ASCII 멀티라인은 정상 동작하므로 차단하지 않습니다.)

→ Write 도구로 ~/scratch/ 에 .py 파일을 만든 뒤 실행하세요:
    Write  ~/scratch/_run.py   (UTF-8 stdout 가드 포함)
    Bash   python ~/scratch/_run.py
   단일 라인 `python -c "..."` 는 허용됩니다.
MSG
    exit 2 ;;
  VARHEREDOC)
    cat >&2 <<'MSG'
[inline_multiline_guard] 차단: 셸 변수에 멀티라인 스크립트를 인라인(content='''...''')
으로 넣으면 따옴표/한글 인코딩이 깨집니다.

→ Write 도구로 스크립트 파일을 직접 생성하세요 (.py / .ps1 / .sh).
   PS1 은 UTF-8 BOM, BAT 은 CP949.
   도구호출 토큰이 평문으로 누출돼 미실행되는 사고도 이 방식으로 예방됩니다.
MSG
    exit 2 ;;
esac

exit 0
