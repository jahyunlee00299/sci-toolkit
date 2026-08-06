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

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

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

for guard in $GUARDS; do
    GUARD_PATH="${SCRIPT_DIR}/${guard}"
    if [ ! -f "$GUARD_PATH" ]; then
        # Missing guard script should not silently allow everything through
        # unnoticed, but it also shouldn't brick every tool call in a
        # partially-installed tree — warn on stderr and continue.
        echo "WARN: _run_hooks_chained — guard not found, skipping: ${guard}" >&2
        continue
    fi

    if ! printf '%s' "$PAYLOAD" | sh "$GUARD_PATH"; then
        # The guard already printed its own "BLOCK: ..." reason on stderr.
        exit 2
    fi
done

exit 0
