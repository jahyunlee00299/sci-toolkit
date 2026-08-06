#!/usr/bin/env sh
# secret_scan_guard.sh — PreToolUse guard: block obvious secret/token leaks.
#
# Reads a single tool-call payload as JSON on stdin (the shape Claude Code
# hook events use: { "tool_name": "...", "tool_input": { "command": "...",
# "content": "...", "file_path": "...", ... } }). This script does NOT
# depend on a JSON parser being installed — it greps the raw stdin text,
# which is conservative but portable (sh + grep only, no python/jq needed).
#
# Exit code contract (used by _run_hooks_chained.sh):
#   0  = allow
#   2  = block (guard found a likely secret)
#
# This script is intentionally conservative: it only flags patterns that
# look like real secrets, and skips obvious placeholder/example text.

set -eu

INPUT="$(cat)"

# Fold to a single line for simpler grep -E matching, keep original case.
FLAT="$(printf '%s' "$INPUT" | tr '\n' ' ')"

# --- 1) Forbidden filename writes -------------------------------------------
# Writing/editing a real secrets store should never happen in this workflow.
if printf '%s' "$FLAT" | grep -Eq '"file_path"[[:space:]]*:[[:space:]]*"[^"]*(secrets\.json|\.credentials\.json|\.git-credentials|id_rsa|id_ed25519)"'; then
    echo "BLOCK: secret_scan_guard — tool call targets a forbidden credential file (secrets.json / *.credentials.json / SSH private key)." >&2
    exit 2
fi

# --- 2) Known token/key prefixes --------------------------------------------
# These prefixes are essentially unambiguous — real vendor tokens, not
# something a human would type as a placeholder.
if printf '%s' "$FLAT" | grep -Eq 'sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}|gho_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|AIzaSy[A-Za-z0-9_-]{20,}'; then
    echo "BLOCK: secret_scan_guard — command/content contains a recognizable API key/token pattern." >&2
    exit 2
fi

# --- 3) Generic "key/token = long-opaque-string" assignments ----------------
# e.g. api_key: "abcd1234...", access_token=..., secret_key='...'
MATCH="$(printf '%s' "$FLAT" | grep -Eio '(api[_-]?key|apikey|secret[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret)[[:space:]]*[:=][[:space:]]*["'"'"']?[A-Za-z0-9_.\-]{16,}["'"'"']?' || true)"

if [ -n "$MATCH" ]; then
    # Ignore obvious placeholders / documentation examples.
    LOWER_MATCH="$(printf '%s' "$MATCH" | tr '[:upper:]' '[:lower:]')"
    case "$LOWER_MATCH" in
        *your_api_key*|*your-api-key*|*your_key*|*your-key*|*yourkey*|*api_key_here*|*example*|*placeholder*|*xxxx*|*changeme*|*dummy*|*getenv*|*os.environ*|*\<*|*\.\.\.*)
            : # placeholder-looking, allow
            ;;
        *)
            echo "BLOCK: secret_scan_guard — possible hardcoded credential assignment detected: ${MATCH}" >&2
            exit 2
            ;;
    esac
fi

exit 0
