#!/usr/bin/env sh
# destructive_delete_guard.sh — PreToolUse guard: block destructive delete commands.
#
# Reads a single tool-call payload as JSON on stdin (same shape as the other
# guards in this folder — see secret_scan_guard.sh for the field layout).
# Blocks recursive/forced deletes that are very hard to undo.
#
# Exit code contract:
#   0 = allow
#   2 = block

set -eu

# Directory of this script without forking dirname/pwd (see _run_hooks_chained.sh).
_a=${0%/*}
_b=${0%\\*}
if [ "$_a" = "$0" ]; then SCRIPT_DIR=$_b
elif [ "$_b" = "$0" ]; then SCRIPT_DIR=$_a
elif [ "${#_a}" -ge "${#_b}" ]; then SCRIPT_DIR=$_a
else SCRIPT_DIR=$_b; fi
if [ "$SCRIPT_DIR" = "$0" ]; then SCRIPT_DIR=.; fi
. "${SCRIPT_DIR}/_payload_fields.sh"

# Only look at the command field's content; this guard is about shell
# commands, not file writes. Parsed as JSON rather than pattern-matched — a
# quote-truncating grep used to live here and let `cd "..." && rm -rf ...`
# through untouched (see _payload_fields.sh).
#
# When _run_hooks_chained.sh has already parsed the payload it hands the
# command over in SCI_HOOK_COMMAND (same value extract_fields would print);
# standalone, the guard still reads and parses stdin itself.
if [ -n "${SCI_HOOK_PARSED:-}" ]; then
    CMD=$SCI_HOOK_COMMAND
else
    INPUT="$(cat)"
    CMD="$(extract_fields "$INPUT" command)"
fi

# Each rule below needs one of these keywords in the command; kw skips its grep
# when they are absent (see _payload_fields.sh).
kw_init "$CMD"

# --- rm -rf / -fr in any option order/spacing, with or without sudo --------
if kw '*rm*' && printf '%s' "$CMD" | grep -Eq '(^|[^A-Za-z0-9_])(sudo[[:space:]]+)?rm[[:space:]]+(-[A-Za-z]*[rRfF][A-Za-z]*[[:space:]]+)*-[A-Za-z]*[rR][A-Za-z]*[fF][A-Za-z]*([[:space:]]|$)'; then
    echo "BLOCK: destructive_delete_guard — 'rm -rf' style recursive force-delete detected." >&2
    exit 2
fi
if kw '*rm*' && printf '%s' "$CMD" | grep -Eq '(^|[^A-Za-z0-9_])(sudo[[:space:]]+)?rm[[:space:]]+(-[A-Za-z]*[fF][A-Za-z]*[[:space:]]+)*-[A-Za-z]*[fF][A-Za-z]*[rR][A-Za-z]*([[:space:]]|$)'; then
    echo "BLOCK: destructive_delete_guard — 'rm -fr' style recursive force-delete detected." >&2
    exit 2
fi

# --- sudo rm (any form) ------------------------------------------------------
if kw '*sudo*' && printf '%s' "$CMD" | grep -Eq '(^|[^A-Za-z0-9_])sudo[[:space:]]+rm([[:space:]]|$)'; then
    echo "BLOCK: destructive_delete_guard — 'sudo rm' detected (elevated delete)." >&2
    exit 2
fi

# --- find ... -delete / -exec rm -------------------------------------------
if kw '*find*' && printf '%s' "$CMD" | grep -Eq 'find[[:space:]].*-delete([[:space:]]|$)'; then
    echo "BLOCK: destructive_delete_guard — 'find ... -delete' bulk-delete pattern detected." >&2
    exit 2
fi
if kw '*find*' && printf '%s' "$CMD" | grep -Eq 'find[[:space:]].*-exec[[:space:]]+rm[[:space:]]'; then
    echo "BLOCK: destructive_delete_guard — 'find ... -exec rm' bulk-delete pattern detected." >&2
    exit 2
fi

# --- rd /s, Remove-Item -Recurse -Force (Windows equivalents) --------------
if kw '*[rR][dD]*' && printf '%s' "$CMD" | grep -Eiq 'rd[[:space:]]+/s([[:space:]]|$)'; then
    echo "BLOCK: destructive_delete_guard — 'rd /s' recursive delete detected." >&2
    exit 2
fi
if kw '*[rR][eE][mM][oO][vV][eE]-[iI][tT][eE][mM]*' && printf '%s' "$CMD" | grep -Eiq 'remove-item.*-recurse.*-force|remove-item.*-force.*-recurse'; then
    echo "BLOCK: destructive_delete_guard — 'Remove-Item -Recurse -Force' detected." >&2
    exit 2
fi

# --- git clean -fdx / -xfd style whole-tree wipes --------------------------
if kw '*git*' && printf '%s' "$CMD" | grep -Eq 'git[[:space:]]+clean[[:space:]]+.*-[a-zA-Z]*f[a-zA-Z]*d|git[[:space:]]+clean[[:space:]]+.*-[a-zA-Z]*d[a-zA-Z]*f'; then
    echo "BLOCK: destructive_delete_guard — 'git clean -fd...' whole-tree wipe detected." >&2
    exit 2
fi

exit 0
