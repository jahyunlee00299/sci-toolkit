#!/usr/bin/env sh
# cloud_path_guard.sh — PreToolUse guard: warn/block recursive scans over
# cloud-sync folders (OneDrive / Dropbox / iCloud / Google Drive).
#
# Recursively walking a cloud-sync folder (find, ls -R, a ** glob, du, cat *)
# can force every file in it to be pulled down from the cloud, which is slow,
# expensive on metered connections, and can silently blow past provider
# rate limits. This guard blocks bulk/recursive filesystem operations whose
# path looks like a cloud-sync root, and lets normal single-file reads
# through.
#
# Reads a single tool-call payload as JSON on stdin (same shape as the other
# guards in this folder).
#
# Exit code contract:
#   0 = allow
#   2 = block

set -eu

INPUT="$(cat)"
FLAT="$(printf '%s' "$INPUT" | tr '\n' ' ')"

CMD="$(printf '%s' "$FLAT" | grep -Eo '"command"[[:space:]]*:[[:space:]]*"[^"]*"' || true)"
FILE_PATH="$(printf '%s' "$FLAT" | grep -Eo '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' || true)"
COMBINED="${CMD} ${FILE_PATH}"
[ "$COMBINED" = " " ] && COMBINED="$FLAT"

# Generic cloud-sync path signature (any OS, any language folder name):
# looks for the well-known provider folder names anywhere in the string.
CLOUD_PATTERN='OneDrive|Dropbox|iCloudDrive|iCloud Drive|Google Drive|GoogleDrive|My Drive'

if ! printf '%s' "$COMBINED" | grep -Eiq "$CLOUD_PATTERN"; then
    exit 0
fi

# From here on we know the command/path touches a cloud-sync folder.
# Only block operations that are bulk/recursive in nature.

# --- recursive find / du / grep -r over a cloud path -----------------------
if printf '%s' "$CMD" | grep -Eq 'find[[:space:]]' && printf '%s' "$CMD" | grep -Eiq "$CLOUD_PATTERN"; then
    echo "BLOCK: cloud_path_guard — recursive 'find' over a cloud-sync (OneDrive/Dropbox/iCloud/Google Drive) path can force a full cloud download. Target a specific file instead, or use the provider's API/skill." >&2
    exit 2
fi

# --- ls -R / ls -r (recursive listing) -------------------------------------
if printf '%s' "$CMD" | grep -Eq 'ls[[:space:]]+(-[A-Za-z]*R[A-Za-z]*)([[:space:]]|$)' && printf '%s' "$CMD" | grep -Eiq "$CLOUD_PATTERN"; then
    echo "BLOCK: cloud_path_guard — recursive 'ls -R' over a cloud-sync path detected." >&2
    exit 2
fi

# --- globstar ** pattern -----------------------------------------------------
if printf '%s' "$CMD" | grep -Eq '\*\*' && printf '%s' "$CMD" | grep -Eiq "$CLOUD_PATTERN"; then
    echo "BLOCK: cloud_path_guard — recursive glob ('**') over a cloud-sync path detected." >&2
    exit 2
fi

# --- du (disk usage walk) ----------------------------------------------------
if printf '%s' "$CMD" | grep -Eq '(^|[^A-Za-z0-9_])du([[:space:]]|$)' && printf '%s' "$CMD" | grep -Eiq "$CLOUD_PATTERN"; then
    echo "BLOCK: cloud_path_guard — 'du' (disk usage recursive walk) over a cloud-sync path detected." >&2
    exit 2
fi

# --- cat with a wildcard (bulk read of many files at once) ------------------
if printf '%s' "$CMD" | grep -Eq '(^|[^A-Za-z0-9_])cat[[:space:]]+[^|;&]*\*' && printf '%s' "$CMD" | grep -Eiq "$CLOUD_PATTERN"; then
    echo "BLOCK: cloud_path_guard — bulk 'cat <wildcard>' over a cloud-sync path detected (3+ simultaneous reads risk forcing bulk cloud download)." >&2
    exit 2
fi

# Single-file Read/Write/Edit tool calls (file_path only, no bulk command)
# are allowed through — this guard only targets bulk/recursive operations.
exit 0
