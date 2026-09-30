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

# Directory of this script without forking dirname/pwd (see _run_hooks_chained.sh).
_a=${0%/*}
_b=${0%\\*}
if [ "$_a" = "$0" ]; then SCRIPT_DIR=$_b
elif [ "$_b" = "$0" ]; then SCRIPT_DIR=$_a
elif [ "${#_a}" -ge "${#_b}" ]; then SCRIPT_DIR=$_a
else SCRIPT_DIR=$_b; fi
if [ "$SCRIPT_DIR" = "$0" ]; then SCRIPT_DIR=.; fi
. "${SCRIPT_DIR}/_payload_fields.sh"

# Parsed as JSON rather than pattern-matched. The old quote-truncating grep
# dropped everything after the first quoted argument, so a quoted Windows path
# — which is exactly how a cloud folder with a space in its name is written —
# hid the OneDrive segment from this guard entirely (see _payload_fields.sh).
#
# When _run_hooks_chained.sh has already parsed the payload it hands the two
# fields over in SCI_HOOK_COMMAND / SCI_HOOK_FILE_PATH (same values
# extract_fields would print); standalone, the guard still reads and parses
# stdin itself.
if [ -n "${SCI_HOOK_PARSED:-}" ]; then
    CMD=$SCI_HOOK_COMMAND
    FILE_PATH=$SCI_HOOK_FILE_PATH
else
    INPUT="$(cat)"
    CMD="$(extract_fields "$INPUT" command)"
    FILE_PATH="$(extract_fields "$INPUT" file_path)"
fi
COMBINED="${CMD} ${FILE_PATH}"

# Generic cloud-sync path signature (any OS, any language folder name):
# looks for the well-known provider folder names anywhere in the string.
CLOUD_PATTERN='OneDrive|Dropbox|iCloudDrive|iCloud Drive|Google Drive|GoogleDrive|My Drive'

# Every provider name above contains "drive" or "dropbox" (case-insensitive), so
# without either the grep below cannot match; kw skips it (see _payload_fields.sh).
kw_init "$COMBINED"
if ! kw '*[dD][rR][iI][vV][eE]*' '*[dD][rR][oO][pP][bB][oO][xX]*'; then
    exit 0
fi
if ! printf '%s' "$COMBINED" | grep -Eiq "$CLOUD_PATTERN"; then
    exit 0
fi

# Every rule below asks whether the COMMAND (not the file path) names a cloud
# folder. The answer does not depend on the rule, so grep for it at most once.
CMD_CLOUD=
cmd_in_cloud() {
    if [ -z "$CMD_CLOUD" ]; then
        if printf '%s' "$CMD" | grep -Eiq "$CLOUD_PATTERN"; then CMD_CLOUD=1; else CMD_CLOUD=0; fi
    fi
    [ "$CMD_CLOUD" = "1" ]
}
kw_init "$CMD"

# From here on we know the command/path touches a cloud-sync folder.
# Only block operations that are bulk/recursive in nature.

# --- recursive find / du / grep -r over a cloud path -----------------------
if kw '*find*' && printf '%s' "$CMD" | grep -Eq 'find[[:space:]]' && cmd_in_cloud; then
    echo "BLOCK: cloud_path_guard — recursive 'find' over a cloud-sync (OneDrive/Dropbox/iCloud/Google Drive) path can force a full cloud download. Target a specific file instead, or use the provider's API/skill." >&2
    exit 2
fi

# --- ls -R / ls -r (recursive listing) -------------------------------------
if kw '*ls*' && printf '%s' "$CMD" | grep -Eq 'ls[[:space:]]+(-[A-Za-z]*R[A-Za-z]*)([[:space:]]|$)' && cmd_in_cloud; then
    echo "BLOCK: cloud_path_guard — recursive 'ls -R' over a cloud-sync path detected." >&2
    exit 2
fi

# --- globstar ** pattern -----------------------------------------------------
if kw '*\*\**' && printf '%s' "$CMD" | grep -Eq '\*\*' && cmd_in_cloud; then
    echo "BLOCK: cloud_path_guard — recursive glob ('**') over a cloud-sync path detected." >&2
    exit 2
fi

# --- du (disk usage walk) ----------------------------------------------------
if kw '*du*' && printf '%s' "$CMD" | grep -Eq '(^|[^A-Za-z0-9_])du([[:space:]]|$)' && cmd_in_cloud; then
    echo "BLOCK: cloud_path_guard — 'du' (disk usage recursive walk) over a cloud-sync path detected." >&2
    exit 2
fi

# --- cat with a wildcard (bulk read of many files at once) ------------------
if kw '*cat*' && printf '%s' "$CMD" | grep -Eq '(^|[^A-Za-z0-9_])cat[[:space:]]+[^|;&]*\*' && cmd_in_cloud; then
    echo "BLOCK: cloud_path_guard — bulk 'cat <wildcard>' over a cloud-sync path detected (3+ simultaneous reads risk forcing bulk cloud download)." >&2
    exit 2
fi

# Single-file Read/Write/Edit tool calls (file_path only, no bulk command)
# are allowed through — this guard only targets bulk/recursive operations.
exit 0
