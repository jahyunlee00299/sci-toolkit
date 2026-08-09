#!/usr/bin/env sh
# Installs the post-commit version-bump hook (scripts/git-hooks/post-commit)
# into this clone's .git/hooks/. Not automatic on clone — .git/hooks/ isn't
# tracked by git, so every fresh clone (including the lab's) needs this run
# once. Re-run after a `.git` loss/restore too.
set -eu

REPO_ROOT="$(git rev-parse --show-toplevel)"
SRC="$REPO_ROOT/scripts/git-hooks/post-commit"
DST="$REPO_ROOT/.git/hooks/post-commit"

if [ -f "$DST" ] && ! grep -q "sci-toolkit version-bump hook" "$DST" 2>/dev/null; then
    echo "A different post-commit hook already exists at $DST — not overwriting." >&2
    echo "Merge manually: have it call $SRC, or vice versa." >&2
    exit 1
fi

cp "$SRC" "$DST"
chmod +x "$DST"
echo "Installed post-commit version-bump hook -> $DST"
