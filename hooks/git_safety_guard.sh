#!/usr/bin/env sh
# git_safety_guard.sh — PreToolUse guard: block dangerous git operations.
#
# Reads a single tool-call payload as JSON on stdin (same shape as the other
# guards in this folder). Blocks force-push, hard reset, global config
# changes, and force-push specifically to main/master.
#
# Exit code contract:
#   0 = allow
#   2 = block

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
. "${SCRIPT_DIR}/_payload_fields.sh"

INPUT="$(cat)"

# Parse the payload as JSON. A quote-truncating grep used to live here and let
# `git commit -m "wip" && git push --force` straight through — see
# _payload_fields.sh for the measurement.
CMD="$(extract_fields "$INPUT" command)"

# Only bother if this actually looks like a git or gh invocation.
# `gh` must be included: `gh pr create` in a fork targets the upstream repo by
# default, which is the single most costly mistake this guard exists to prevent.
if ! printf '%s' "$CMD" | grep -Eq '(^|[^A-Za-z0-9_])(git|gh)([[:space:]]|$)'; then
    exit 0
fi

# --- force push (--force / --force-with-lease / -f / +refspec) -------------
# Checked in two steps rather than one regex. A single pattern of the form
#   git push .*(--force|[[:space:]]-f...)
# fails on `git push -f origin feature`: the greedy `.*` consumes the space in
# front of `-f`, and the alternation then has no space left to match. That hole
# was live in the shipped guard until the tests caught it (2026-08-07).
if printf '%s' "$CMD" | grep -Eq 'git[[:space:]]+push([[:space:]]|$)'; then
    if printf '%s' "$CMD" | grep -Eq -- '--force(-with-lease)?|[[:space:]]-f([[:space:]]|"|$)|[[:space:]]\+[A-Za-z]'; then
        echo "BLOCK: git_safety_guard — force push (--force / -f / +refspec) detected." >&2
        echo "  Force-pushing rewrites history other people may already have." >&2
        exit 2
    fi
fi

# --- force push explicitly targeting main/master ---------------------------
if printf '%s' "$CMD" | grep -Eq 'git[[:space:]]+push[[:space:]]+.*[[:space:]](main|master)([[:space:]]|$)' \
   && printf '%s' "$CMD" | grep -Eq -- '--force|(^|[[:space:]])-f([[:space:]]|$)'; then
    echo "BLOCK: git_safety_guard — force-push targeting main/master detected." >&2
    exit 2
fi

# --- git reset --hard --------------------------------------------------------
if printf '%s' "$CMD" | grep -Eq 'git[[:space:]]+reset[[:space:]]+.*--hard'; then
    echo "BLOCK: git_safety_guard — 'git reset --hard' (discards uncommitted work) detected." >&2
    exit 2
fi

# --- git config --global (never touch the user's global git config) --------
if printf '%s' "$CMD" | grep -Eq 'git[[:space:]]+config[[:space:]]+.*--global'; then
    echo "BLOCK: git_safety_guard — 'git config --global' detected (never modify global git config from an agent)." >&2
    exit 2
fi

# --- direct commit/merge/force-push to main or master branch ---------------
if printf '%s' "$CMD" | grep -Eq 'git[[:space:]]+branch[[:space:]]+.*-D([[:space:]]|$)'; then
    echo "BLOCK: git_safety_guard — 'git branch -D' (force branch delete) detected." >&2
    exit 2
fi

# --- bypassing the hooks themselves ----------------------------------------
# `--no-verify` and `-c core.hooksPath=` disable the very checks that stand
# between an accidental commit and a public repository. A guard that can be
# turned off by the thing it guards is not a guard.
if printf '%s' "$CMD" | grep -Eq 'git[[:space:]]+.*(--no-verify|-c[[:space:]]+core\.hooksPath)'; then
    echo "BLOCK: git_safety_guard — attempt to bypass git hooks (--no-verify / core.hooksPath)." >&2
    echo "  If a hook is wrong, fix the hook. Do not route around it." >&2
    exit 2
fi

# --- pushing to an upstream you forked from --------------------------------
# In a fork, `upstream` points at someone else's repository. Pushing or opening
# a PR against it publishes work that was only ever meant to be local — which,
# for unpublished research, means disclosure before submission. This is the one
# git mistake in a lab setting that cannot be undone by a revert.
#
# We only block when the repo actually HAS an upstream remote, so ordinary
# `origin` work in your own repo is unaffected.
if printf '%s' "$CMD" | grep -Eq 'git[[:space:]]+push[[:space:]]+.*upstream'; then
    if git remote 2>/dev/null | grep -qx 'upstream'; then
        echo "BLOCK: git_safety_guard — push to 'upstream' in a forked repository." >&2
        echo "  Pushing here publishes to the repo you forked FROM. Push to 'origin' instead." >&2
        echo "  If you truly intend to contribute upstream, open a PR from a branch and" >&2
        echo "  have a human review the diff first." >&2
        exit 2
    fi
fi

# `gh pr create` without --repo defaults to the PARENT of a fork, not your own
# copy. The default is the dangerous direction, so require it to be explicit.
if printf '%s' "$CMD" | grep -Eq 'gh[[:space:]]+pr[[:space:]]+create'; then
    if git remote 2>/dev/null | grep -qx 'upstream' \
       && ! printf '%s' "$CMD" | grep -Eq -- '--repo'; then
        echo "BLOCK: git_safety_guard — 'gh pr create' without --repo inside a fork." >&2
        echo "  Without --repo, gh targets the upstream repository by default." >&2
        echo "  Pin it explicitly: gh pr create --repo <your-org>/<your-fork>" >&2
        exit 2
    fi
fi

exit 0
