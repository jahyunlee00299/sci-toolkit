#!/usr/bin/env sh
# _codex_json_adapter.sh — run an exit-2-contract guard under Codex CLI.
#
# Why this exists: measured 2026-08-21 against Codex CLI 0.147.0 (issue #5),
# Codex fires PreToolUse hooks with the same stdin payload as Claude Code, but
# it does NOT honour the exit-code contract. A hook that exits 2 with a reason
# on stderr is ignored and the command runs anyway ("succeeded"). Codex blocks
# only when the hook writes
#     {"decision":"block","reason":"..."}
# to STDOUT and exits 0, which surfaces as
#     Command blocked by PreToolUse hook: <reason>
#
# Every guard in this folder speaks exit 2. Wired into Codex unchanged, they
# would run, detect, print their reason — and let the command through. That is
# the failure mode issue #5 was opened to prevent: a guard that produces a
# green light on an unchecked command is worse than no guard, because nothing
# warns you.
#
# So this adapter sits between them and translates.
#
# Usage (in ~/.codex/hooks.json, absolute paths — Codex does not inject
# ${CLAUDE_PLUGIN_ROOT}):
#
#   {"hooks": {"PreToolUse": [{"matcher": "Bash|Write|Edit", "hooks": [
#     {"type": "command",
#      "command": "sh /abs/path/hooks/_codex_json_adapter.sh /abs/path/hooks/_run_hooks_chained.sh"}
#   ]}]}}
#
#   $1        = the guard (or chain runner) to wrap
#   $2..      = passed through to it unchanged
#   stdin     = the hook event JSON, buffered and re-fed to the wrapped guard
#
# Translation table:
#   guard exit 2  -> stdout {"decision":"block","reason":"<guard stderr>"}, exit 0
#   guard exit 0  -> pass the guard's stdout through if it already looks like
#                    hook JSON, else print nothing;                        exit 0
#   guard other   -> exit 0 (permissive), with a WARN on stderr
#
# The "other" case is deliberately permissive rather than blocking. A crashed
# or missing guard must not brick every tool call in a partially-installed
# tree — the same reasoning as the missing-guard branch in
# _run_hooks_chained.sh — but it is announced on stderr so a silently dead
# guard cannot masquerade as a passing one.
#
# This adapter is NOT a guard: it detects nothing on its own. The leading
# underscore marks it as hook infrastructure, alongside _run_hooks_chained.sh
# and _payload_fields.sh, and keeps it out of the guard inventory in
# tests/test_hook_wiring.py and tests/test_doc_counts.py.

set -eu

# --- emit_block <reason-file> ------------------------------------------------
#
# Prints {"decision":"block","reason":"<escaped file contents>"} on stdout.
#
# The escaping matters more here than anywhere else in this folder: guard
# reasons contain the offending command, which routinely holds quotes,
# backslashes (Windows paths) and newlines. Emit those raw and the JSON is
# malformed, Codex cannot parse the decision, and the block silently degrades
# into an allow — the exact failure this adapter exists to remove.
#
# python does the escaping when available (it is already a hard dependency of
# _payload_fields.sh and three guards). Unlike that file, though, this one
# cannot fall back to raw text: there is no "over-match" direction here, only
# valid JSON or no block at all. So the fallback is a pure-shell escaper that
# handles the JSON string metacharacters, and if even that is unreachable the
# reason degrades to a fixed ASCII string while the BLOCK decision survives.
emit_block() {
    _eb_file="$1"
    _eb_py="$(command -v python 2>/dev/null || command -v python3 2>/dev/null || true)"
    if [ -n "$_eb_py" ]; then
        REASON_FILE="$_eb_file" "$_eb_py" -c '
import json, os, sys
with open(os.environ["REASON_FILE"], "rb") as fh:
    reason = fh.read().decode("utf-8", "replace").strip()
sys.stdout.write(json.dumps({"decision": "block", "reason": reason}))
' && return 0
        echo "WARN: _codex_json_adapter — python escaping failed; using shell fallback." >&2
    fi

    # Pure-shell fallback. Four constraints, each one established by feeding
    # the result back through a JSON parser (2026-08-21) rather than eyeballed:
    #
    #   1. Backslashes are escaped FIRST. Do it later and the backslashes this
    #      step introduces for the other metacharacters get escaped twice.
    #   2. Trailing newlines are stripped by `$(cat ...)`, not by sed. Once
    #      `tr` has folded newlines to a sentinel there is no line terminator
    #      left, so `sed 's/<sentinel>*$//'` silently matches nothing and a
    #      literal control byte survives at the end of the string. A control
    #      byte inside a JSON string is a parse error, and an unparseable
    #      decision degrades into an allow — the exact failure this adapter
    #      exists to remove.
    #   3. Interior newlines become the two characters \ and n. They cannot
    #      survive a `$(...)` capture as themselves, hence folding them to a
    #      \001 sentinel first and rewriting the sentinel afterwards.
    #   4. The sentinel is passed to sed as a variable holding the literal
    #      byte. Written inline as `s/\001/.../` it does not match: sed reads
    #      the pattern's \001 as the character `1`, not as an octal escape, so
    #      the sentinel passed through untouched and every newline in a
    #      multi-line reason vanished (measured — two lines were concatenated
    #      with no separator, and the surviving control byte broke the parse).
    _eb_sentinel="$(printf '\001')"
    _eb_stripped="$(cat "$_eb_file")" || _eb_stripped=""
    _eb_reason="$(
        printf '%s' "$_eb_stripped" \
        | sed -e 's/\\/\\\\/g' \
              -e 's/"/\\"/g' \
              -e 's/\r//g' \
              -e 's/\t/ /g' \
        | tr '\n' "$_eb_sentinel" \
        | sed -e "s/${_eb_sentinel}/\\\\n/g"
    )" || _eb_reason=""

    if [ -z "$_eb_reason" ]; then
        _eb_reason="Blocked by a sci-toolkit guard (reason text unavailable)."
    fi
    printf '{"decision":"block","reason":"%s"}' "$_eb_reason"
}

if [ "$#" -lt 1 ]; then
    echo "WARN: _codex_json_adapter — no guard given; usage: $0 <guard> [args...]" >&2
    exit 0
fi

GUARD="$1"
shift

if [ ! -f "$GUARD" ]; then
    echo "WARN: _codex_json_adapter — guard not found, allowing: ${GUARD}" >&2
    exit 0
fi

# Buffer stdin: the payload has to be readable by the guard, and the guard's
# streams have to be captured separately, so it cannot simply be piped.
TMPDIR_ADAPTER="$(mktemp -d 2>/dev/null || echo "${TMPDIR:-/tmp}/codexadapt.$$")"
[ -d "$TMPDIR_ADAPTER" ] || mkdir -p "$TMPDIR_ADAPTER"
PAYLOAD_FILE="${TMPDIR_ADAPTER}/payload.json"
OUT_FILE="${TMPDIR_ADAPTER}/stdout.txt"
ERR_FILE="${TMPDIR_ADAPTER}/stderr.txt"

cleanup() {
    rm -f "$PAYLOAD_FILE" "$OUT_FILE" "$ERR_FILE" 2>/dev/null || true
    rmdir "$TMPDIR_ADAPTER" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

cat > "$PAYLOAD_FILE"

# `set -e` must not kill us on the guard's non-zero exit — that exit code is
# the entire signal we are here to read.
RC=0
sh "$GUARD" "$@" < "$PAYLOAD_FILE" > "$OUT_FILE" 2> "$ERR_FILE" || RC=$?

case "$RC" in
0)
    # Allow. If the guard already emitted hook JSON of its own, hand it
    # through untouched rather than swallowing a decision it meant to make.
    if [ -s "$OUT_FILE" ] && grep -q '"decision"' "$OUT_FILE" 2>/dev/null; then
        cat "$OUT_FILE"
    fi
    # The guard's stderr is diagnostic on an allow; keep it visible.
    [ -s "$ERR_FILE" ] && cat "$ERR_FILE" >&2
    exit 0
    ;;
2)
    # Block. The reason is whatever the guard printed on stderr; guards in
    # this folder use "BLOCK: <guard> — <why>".
    REASON_FILE="$ERR_FILE"
    if [ ! -s "$REASON_FILE" ]; then
        printf 'Blocked by %s (exit 2, no reason given).' "$(basename "$GUARD")" \
            > "$REASON_FILE"
    fi
    emit_block "$REASON_FILE"
    exit 0
    ;;
*)
    echo "WARN: _codex_json_adapter — $(basename "$GUARD") exited ${RC}" \
         "(not 0 or 2); allowing. Guard stderr follows." >&2
    [ -s "$ERR_FILE" ] && cat "$ERR_FILE" >&2
    exit 0
    ;;
esac
