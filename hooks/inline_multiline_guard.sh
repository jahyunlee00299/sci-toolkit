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

# [260626] Mitigate false triggers on WSL (home PC): this BLOCK's premise is
#   "on git-bash (laptop), a multiline python -c / quoted payload breaks on
#   newlines/encoding." WSL bash doesn't have that breakage (POSIX behaves
#   normally), so on WSL this BLOCK is a pure false trigger that frequently
#   halts the headless goal loop. Downgrade to advisory (exit 0 + stderr) when
#   WSL is detected. The laptop's git-bash keeps the existing BLOCK.
#   Kill-switch / integration: if HEADLESS_DELEGATION=1, always advisory
#   (integrated with the delegation gate, Task #2).
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
# FIX 260613: only block when there is a \n between the opening and closing quote.
#   (the old version searched for \n across the whole command after m.end(), so a
#    single-line python -c inside a larger multi-step bash script with more lines
#    after it was falsely blocked — measured recurrence.)
m = re.search(r"python3?\s+-c\s*([\x22\x27])", scan)
if m:
    q = m.group(1)               # opening quote character
    rest = scan[m.end():]        # everything right after the quote
    close = rest.find(q)         # position of the matching closing quote
    span = rest if close == -1 else rest[:close]  # if unterminated, go to the end (safe side)
    if "\n" in span:
        # [260801] Narrowed the condition — measurement split the rationale in two.
        #   Actually running a multiline `python -c` on git-bash shows:
        #     · newlines/quotes → work fine (rc=0, all lines execute as written)
        #     · non-ASCII (e.g. Korean) → mangled by cp949 ({"한글":1} -> {"??":1})
        #   In other words the real cause of breakage is not "multiline" but "a
        #   non-ASCII payload." The old rule lumped the two together and forced
        #   even pure-ASCII multiline commands through a file every time (pure
        #   friction: same result, more round trips). Now it only blocks when
        #   non-ASCII is actually present.
        if any(ord(ch) > 127 for ch in span):
            print("PYC"); sys.exit(0)
        print("ALLOW"); sys.exit(0)

# B) shell var holding a multiline inline script (triple-quote heredoc style).
am = re.search(r"\b(?:content|script|code|payload|ps1?|body)\s*=\s*(\x27\x27\x27|\x22\x22\x22|\x27|\x22)", scan)
if am and "\n" in scan[am.end():]:
    print("VARHEREDOC"); sys.exit(0)

print("ALLOW")
' 2>/dev/null)

# [260626] WSL/headless delegation: no multiline-breakage risk in this environment, so downgrade BLOCK -> advisory.
if [ "${_ADVISORY:-0}" = "1" ] && { [ "$verdict" = "PYC" ] || [ "$verdict" = "VARHEREDOC" ]; }; then
    echo "[inline_multiline_guard] (WSL/headless advisory) Multiline inline script detected — usually fine on WSL, but routing through a script file is still recommended. Allowing." >&2
    exit 0
fi

case "$verdict" in
  PYC)
    cat >&2 <<'MSG'
[inline_multiline_guard] Blocked: a multiline `python -c "..."` contains
non-ASCII text (e.g. Korean). The git-bash console is cp949, so the encoding
breaks — {"한글":1} becomes {"??":1}.
(Pure-ASCII multiline works fine and is not blocked.)

-> Use the Write tool to create a .py file under ~/scratch/, then run it:
    Write  ~/scratch/_run.py   (with the UTF-8 stdout guard)
    Bash   python ~/scratch/_run.py
   A single-line `python -c "..."` is allowed.
MSG
    exit 2 ;;
  VARHEREDOC)
    cat >&2 <<'MSG'
[inline_multiline_guard] Blocked: inlining a multiline script into a shell
variable (content='''...''') breaks quoting/non-ASCII encoding.

-> Use the Write tool to create the script file directly (.py / .ps1 / .sh).
   PS1 needs a UTF-8 BOM, BAT needs CP949.
   This also prevents the failure mode where a tool-call token leaks in
   plaintext and never gets executed.
MSG
    exit 2 ;;
esac

exit 0
