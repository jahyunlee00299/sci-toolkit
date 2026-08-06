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

INPUT="$(cat)"
FLAT="$(printf '%s' "$INPUT" | tr '\n' ' ')"

# Only look at the command field's content; this guard is about shell
# commands, not file writes.
CMD="$(printf '%s' "$FLAT" | grep -Eo '"command"[[:space:]]*:[[:space:]]*"[^"]*"' || true)"
[ -z "$CMD" ] && CMD="$FLAT"

# --- rm -rf / -fr in any option order/spacing, with or without sudo --------
if printf '%s' "$CMD" | grep -Eq '(^|[^A-Za-z0-9_])(sudo[[:space:]]+)?rm[[:space:]]+(-[A-Za-z]*[rRfF][A-Za-z]*[[:space:]]+)*-[A-Za-z]*[rR][A-Za-z]*[fF][A-Za-z]*([[:space:]]|$)'; then
    echo "BLOCK: destructive_delete_guard — 'rm -rf' style recursive force-delete detected." >&2
    exit 2
fi
if printf '%s' "$CMD" | grep -Eq '(^|[^A-Za-z0-9_])(sudo[[:space:]]+)?rm[[:space:]]+(-[A-Za-z]*[fF][A-Za-z]*[[:space:]]+)*-[A-Za-z]*[fF][A-Za-z]*[rR][A-Za-z]*([[:space:]]|$)'; then
    echo "BLOCK: destructive_delete_guard — 'rm -fr' style recursive force-delete detected." >&2
    exit 2
fi

# --- sudo rm (any form) ------------------------------------------------------
if printf '%s' "$CMD" | grep -Eq '(^|[^A-Za-z0-9_])sudo[[:space:]]+rm([[:space:]]|$)'; then
    echo "BLOCK: destructive_delete_guard — 'sudo rm' detected (elevated delete)." >&2
    exit 2
fi

# --- find ... -delete / -exec rm -------------------------------------------
if printf '%s' "$CMD" | grep -Eq 'find[[:space:]].*-delete([[:space:]]|$)'; then
    echo "BLOCK: destructive_delete_guard — 'find ... -delete' bulk-delete pattern detected." >&2
    exit 2
fi
if printf '%s' "$CMD" | grep -Eq 'find[[:space:]].*-exec[[:space:]]+rm[[:space:]]'; then
    echo "BLOCK: destructive_delete_guard — 'find ... -exec rm' bulk-delete pattern detected." >&2
    exit 2
fi

# --- rd /s, Remove-Item -Recurse -Force (Windows equivalents) --------------
if printf '%s' "$CMD" | grep -Eiq 'rd[[:space:]]+/s([[:space:]]|$)'; then
    echo "BLOCK: destructive_delete_guard — 'rd /s' recursive delete detected." >&2
    exit 2
fi
if printf '%s' "$CMD" | grep -Eiq 'remove-item.*-recurse.*-force|remove-item.*-force.*-recurse'; then
    echo "BLOCK: destructive_delete_guard — 'Remove-Item -Recurse -Force' detected." >&2
    exit 2
fi

# --- git clean -fdx / -xfd style whole-tree wipes --------------------------
if printf '%s' "$CMD" | grep -Eq 'git[[:space:]]+clean[[:space:]]+.*-[a-zA-Z]*f[a-zA-Z]*d|git[[:space:]]+clean[[:space:]]+.*-[a-zA-Z]*d[a-zA-Z]*f'; then
    echo "BLOCK: destructive_delete_guard — 'git clean -fd...' whole-tree wipe detected." >&2
    exit 2
fi

exit 0
