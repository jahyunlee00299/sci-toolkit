#!/usr/bin/env sh
# _run_hooks_chained.sh — single entry point that runs all PreToolUse guards
# in this folder, in sequence, for ONE tool-call event.
#
# Why this exists: if hooks.json registered each guard script as its own
# separate "command" hook, Claude Code would spawn one process PER guard PER
# tool call (a "window flood" of short-lived shells). Instead, hooks.json
# points at only this wrapper; the wrapper reads the hook JSON payload from
# stdin ONCE, then re-feeds the same payload to each guard script in-process
# (one spawn per guard, still, but from a single parent invocation instead
# of N separate hook registrations — and it stops at the first block instead
# of always running all four).
#
# Contract with Claude Code's PreToolUse hook protocol:
#   - stdin  = the hook event JSON (tool_name, tool_input, ...)
#   - exit 0 = allow the tool call
#   - exit 2 = block the tool call (stderr text is surfaced to the model/user
#              as the block reason — this matches Claude Code's documented
#              PreToolUse "block" convention)
#
# Order matters only in that we fail fast on the first guard that blocks;
# each guard is independent and order does not change the outcome otherwise.
#
# Speed (measured on the Windows laptop, git-bash, 2026-09-30): process spawn
# costs 40-160 ms there, and running all ten guards on every call took ~4.0 s
# even for `ls -la` (0.5-0.8 s per guard). Two things fix that, neither of which
# changes what gets blocked:
#
#   1. PREFILTER. Before starting a guard the runner tests, in pure shell (no
#      child process), a NECESSARY condition for that guard to do anything: a
#      keyword that the guard's own first early-exit test looks for. If the
#      keyword is absent from the raw payload, the guard is guaranteed to exit 0
#      without printing anything, so it is skipped. A guard with no entry in
#      prefilter_skip() always runs. The prefilter switches itself off (the full
#      chain runs, exactly as before) whenever the raw text could disagree with
#      the decoded JSON or with what the guards' greps see:
#        - the payload contains a JSON \u or \/ escape (a keyword can hide in one)
#        - the payload contains anything outside printable ASCII (Korean text,
#          control characters, broken bytes: the guards' python/grep behave
#          locale- and byte-dependently there, so they are left untouched)
#        - the payload does not start with "{" and end with "}"
#      Kill switch: SCI_HOOK_PREFILTER=0 runs the full chain unconditionally.
#
#   2. PARSE ONCE. The three guards that read tool_input.command / file_path
#      (destructive_delete, git_safety, cloud_path) used to spawn python each
#      (cloud_path twice). The runner parses the payload once, lazily, and hands
#      the two fields over in SCI_HOOK_* environment variables. Each guard falls
#      back to its own parsing when the variables are absent, so it still works
#      standalone. The hand-over is skipped (guards parse for themselves) when a
#      value is non-ASCII, contains NUL, or is too long for an environment block.

set -eu

# Directory of this script, without forking dirname/pwd (each fork is 40-160 ms
# on Windows). Handles both / and \ separators: a separator that is absent leaves
# $0 unchanged; when both are present the longer remainder stripped only the last
# path component.
_a=${0%/*}
_b=${0%\\*}
if [ "$_a" = "$0" ]; then SCRIPT_DIR=$_b
elif [ "$_b" = "$0" ]; then SCRIPT_DIR=$_a
elif [ "${#_a}" -ge "${#_b}" ]; then SCRIPT_DIR=$_a
else SCRIPT_DIR=$_b; fi
if [ "$SCRIPT_DIR" = "$0" ]; then SCRIPT_DIR=.; fi

# Guards run in this order; we stop at the first one that blocks.
#
# Safety guards — these prevent loss or disclosure:
#   secret_scan       leaked credentials
#   destructive_delete  unrecoverable deletes
#   git_safety        force-push, history rewrite, pushing to a fork's upstream
#   cloud_path        recursive scans that force a full cloud download
# Environment guards — these prevent commands that silently do the wrong thing
# on Windows git-bash (quoting and newlines break, so the command "succeeds"
# while doing something else):
#   conda_multiline, inline_multiline, bash_env_mismatch
#
# An argument list can override the default set, which is how a caller wires a
# different chain for a different hook event.
DEFAULT_GUARDS="secret_scan_guard.sh destructive_delete_guard.sh git_safety_guard.sh cloud_path_guard.sh conda_multiline_guard.sh inline_multiline_guard.sh bash_env_mismatch_guard.sh"
if [ "$#" -gt 0 ]; then
    GUARDS="$*"
else
    GUARDS="$DEFAULT_GUARDS"
fi

# Read the hook JSON payload once.
PAYLOAD="$(cat)"

# A value inherited from the caller's environment must never be mistaken for
# something this runner parsed.
unset SCI_HOOK_PARSED SCI_HOOK_TOOL_NAME SCI_HOOK_COMMAND SCI_HOOK_FILE_PATH || true

# --- prefilter switch --------------------------------------------------------
PREFILTER=1
if [ "${SCI_HOOK_PREFILTER:-1}" = "0" ]; then
    PREFILTER=0
fi
if [ "$PREFILTER" = "1" ]; then
    case $PAYLOAD in
        *'\u'*|*'\/'*) PREFILTER=0 ;;
    esac
fi
if [ "$PREFILTER" = "1" ]; then
    case $PAYLOAD in
        *[!\ -\~]*) PREFILTER=0 ;;
    esac
fi
if [ "$PREFILTER" = "1" ]; then
    case $PAYLOAD in
        \{*\}) ;;
        *) PREFILTER=0 ;;
    esac
fi
# Every command-inspecting guard reads tool_input.command, so a payload without
# a "command" key (Write / Edit / Read) cannot make any of them act.
HAS_CMD=0
case $PAYLOAD in
    *'"command"'*) HAS_CMD=1 ;;
esac

# prefilter_skip <guard>: succeeds only when the guard is PROVABLY a silent
# exit 0 for this payload. Each keyword list is copied from the guard's own
# first early-exit test and is deliberately a superset (a false "run it" only
# costs time; a false "skip it" would let something through).
prefilter_skip() {
    case $1 in
        secret_scan_guard.sh)
            # rule 1 file names, rule 2 token prefixes, rule 3 key/token/secret words
            case $PAYLOAD in
                *secrets.json*|*.credentials.json*|*.git-credentials*|*id_rsa*|*id_ed25519*) return 1 ;;
                *sk-*|*ghp_*|*gho_*|*github_pat_*|*xox*|*AKIA*|*AIzaSy*) return 1 ;;
                *[kK][eE][yY]*|*[tT][oO][kK][eE][nN]*|*[sS][eE][cC][rR][eE][tT]*) return 1 ;;
            esac
            return 0 ;;
        destructive_delete_guard.sh)
            [ "$HAS_CMD" = "1" ] || return 0
            case $PAYLOAD in
                *rm*|*find*|*git*clean*) return 1 ;;
                *[rR][dD]*/[sS]*) return 1 ;;
                *[rR][eE][mM][oO][vV][eE]-[iI][tT][eE][mM]*) return 1 ;;
            esac
            return 0 ;;
        git_safety_guard.sh)
            [ "$HAS_CMD" = "1" ] || return 0
            # (git|gh) followed by whitespace or end of the command string; in the
            # raw JSON that is a space, a backslash escape, or the closing quote.
            case $PAYLOAD in
                *git' '*|*git\\*|*git\"*|*gh' '*|*gh\\*|*gh\"*) return 1 ;;
            esac
            return 0 ;;
        cloud_path_guard.sh)
            [ "$HAS_CMD" = "1" ] || return 0
            # every provider name in CLOUD_PATTERN contains "drive" or "dropbox"
            case $PAYLOAD in
                *[dD][rR][iI][vV][eE]*|*[dD][rR][oO][pP][bB][oO][xX]*) return 1 ;;
            esac
            return 0 ;;
        conda_multiline_guard.sh)
            [ "$HAS_CMD" = "1" ] || return 0
            case $PAYLOAD in
                *'conda run'*)
                    case $PAYLOAD in
                        *python*)
                            case $PAYLOAD in
                                *'\n'*) return 1 ;;
                            esac ;;
                    esac ;;
            esac
            return 0 ;;
        inline_multiline_guard.sh)
            [ "$HAS_CMD" = "1" ] || return 0
            # needs a newline in the decoded command, plus python -c or NAME=
            case $PAYLOAD in
                *'\n'*)
                    case $PAYLOAD in
                        *python*|*=*) return 1 ;;
                    esac ;;
            esac
            return 0 ;;
        bash_env_mismatch_guard.sh)
            [ "$HAS_CMD" = "1" ] || return 0
            # $env:, PowerShell Verb-Noun cmdlets, or python3 / jq / zip
            case $PAYLOAD in
                *'$env:'*) return 1 ;;
                *Get-*|*Set-*|*Out-*|*Copy-*|*Move-*|*Remove-*|*New-*|*Test-*) return 1 ;;
                *Select-*|*Where-*|*ForEach-*|*Measure-*|*Sort-*) return 1 ;;
                *python3*|*jq*|*zip*) return 1 ;;
            esac
            return 0 ;;
    esac
    return 1
}

# parse_once: fill SCI_HOOK_* from the payload with ONE python spawn. Silent on
# any problem (no python, unparseable JSON, non-ASCII / NUL / oversized value):
# the variables then stay unset and every guard parses for itself, exactly as
# it always did.
PARSE_TRIED=0
parse_once() {
    PARSE_TRIED=1
    _py="$(command -v python 2>/dev/null || command -v python3 2>/dev/null || true)"
    if [ -z "$_py" ]; then
        return 0
    fi
    _out="$(printf '%s' "$PAYLOAD" | "$_py" -c '
import json, sys

def q(v):
    return "\x27" + v.replace("\x27", "\x27\\\x27\x27") + "\x27"

try:
    payload = json.loads(sys.stdin.read())
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        sys.exit(1)
    def field(d, k):
        v = d.get(k)
        return v.replace("\n", " ") if isinstance(v, str) else ""
    tool = field(payload, "tool_name")
    cmd = field(tool_input, "command")
    path = field(tool_input, "file_path")
    joined = tool + cmd + path
    if len(joined) > 8000 or "\x00" in joined or any(ord(c) > 126 for c in joined):
        sys.exit(1)
    sys.stdout.write("SCI_HOOK_TOOL_NAME=%s;SCI_HOOK_COMMAND=%s;SCI_HOOK_FILE_PATH=%s;SCI_HOOK_PARSED=1;" % (q(tool), q(cmd), q(path)))
except SystemExit:
    raise
except Exception:
    sys.exit(1)
' 2>/dev/null)" || return 0
    if [ -n "$_out" ]; then
        eval "$_out"
        export SCI_HOOK_TOOL_NAME SCI_HOOK_COMMAND SCI_HOOK_FILE_PATH SCI_HOOK_PARSED
    fi
    return 0
}

for guard in $GUARDS; do
    GUARD_PATH="${SCRIPT_DIR}/${guard}"
    if [ ! -f "$GUARD_PATH" ]; then
        # Missing guard script should not silently allow everything through
        # unnoticed, but it also shouldn't brick every tool call in a
        # partially-installed tree — warn on stderr and continue.
        echo "WARN: _run_hooks_chained — guard not found, skipping: ${guard}" >&2
        continue
    fi

    if [ "$PREFILTER" = "1" ] && prefilter_skip "$guard"; then
        continue
    fi

    # These three read only the parsed fields; everything else needs the payload.
    case $guard in
        destructive_delete_guard.sh|git_safety_guard.sh|cloud_path_guard.sh)
            if [ "$PARSE_TRIED" = "0" ]; then
                parse_once
            fi
            if [ -n "${SCI_HOOK_PARSED:-}" ]; then
                if ! sh "$GUARD_PATH" </dev/null; then
                    exit 2
                fi
                continue
            fi ;;
    esac

    if ! printf '%s' "$PAYLOAD" | sh "$GUARD_PATH"; then
        # The guard already printed its own "BLOCK: ..." reason on stderr.
        exit 2
    fi
done

exit 0
