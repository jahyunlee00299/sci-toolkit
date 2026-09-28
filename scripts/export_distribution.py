#!/usr/bin/env python3
"""Copy the toolkit tree into a clean distribution copy (USB drive/shared folder).

Why this exists: QUICKSTART.md's distribution model is "plug in a USB and use
the `sci-toolkit` folder on it as-is" — the raw working tree is copied onto
the medium before anyone runs `install.py`. `install.py` already reads
`.distignore` at install time (measured 2026-08-07: it used to not, so
`.git`/caches were never actually kept out of a user's `~/.claude/skills`),
but nothing filtered the copy that lands ON the USB in the first place. A
verify pass (2026-09-28) found `.git` (187 commits, real author identity,
recoverable unpublished-research strings via `git log -S`), `out/` (real
feedback.jsonl + downloaded PDFs), `config/credentials.json` and
`config/research_markers.local.json` all present in a raw `cp -r` of this
tree. This script is the missing step: run it once to produce the copy that
actually goes on the medium, instead of copying the working tree directly.

Reuses `scripts/distignore.py` (the sole place `.distignore` patterns are
interpreted — see that module's docstring) rather than reimplementing the
exclusion logic, the same way `install.py` does for its own copy step.

Usage:
    python scripts/export_distribution.py --dest /Volumes/USB/sci-toolkit          # preview
    python scripts/export_distribution.py --dest /Volumes/USB/sci-toolkit --apply  # actually copy
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

# Windows' default console is cp949, which dies on Korean/symbol output. Force UTF-8.
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

ROOT = Path(__file__).resolve().parent.parent  # toolkit root

sys.path.insert(0, str(ROOT / "scripts"))
from distignore import ALWAYS_EXCLUDE_DIRS, ignore_factory, load_patterns  # noqa: E402

# Names that must never appear anywhere in the exported tree, checked after
# the copy as a defense-in-depth assertion — belt and suspenders on top of
# `.distignore`/`ALWAYS_EXCLUDE_DIRS`, in case a future pattern edit narrows
# either one by accident.
MUST_NOT_EXIST = {
    ".git", "__pycache__", ".pytest_cache", "out",
    "credentials.json", "research_markers.local.json",
}


def planned_copy(dest: Path) -> tuple[list[str], list[str]]:
    """Return (would_copy, would_skip) as relative POSIX paths, without touching disk."""
    patterns = load_patterns(ROOT)
    ignore = ignore_factory(ROOT, patterns)
    copy, skip = [], []
    stack = [ROOT]
    while stack:
        directory = stack.pop()
        try:
            names = sorted(p.name for p in directory.iterdir())
        except OSError:
            continue
        skipped = ignore(str(directory), names)
        for name in names:
            p = directory / name
            rel = p.relative_to(ROOT).as_posix()
            if name in skipped:
                skip.append(rel + ("/" if p.is_dir() else ""))
                continue
            if p.is_dir():
                stack.append(p)
            else:
                copy.append(rel)
    return copy, skip


def assert_clean(dest: Path) -> list[str]:
    """Walk the exported copy and report any MUST_NOT_EXIST name that still made it in."""
    hits = []
    for p in dest.rglob("*"):
        if p.name in MUST_NOT_EXIST:
            hits.append(str(p.relative_to(dest)))
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dest", required=True, help="Target directory for the distribution copy (created if absent)")
    ap.add_argument("--apply", action="store_true", help="Actually copy (preview if omitted)")
    args = ap.parse_args()

    dest = Path(args.dest)

    if not args.apply:
        copy, skip = planned_copy(dest)
        print(f"[preview] {len(copy)} file(s) would be copied to {dest}")
        print(f"[preview] {len(skip)} entr(y/ies) would be skipped (.distignore + {sorted(ALWAYS_EXCLUDE_DIRS)})")
        print("\nSkipped (first 20):")
        for rel in skip[:20]:
            print(f"  - {rel}")
        if len(skip) > 20:
            print(f"  ... and {len(skip) - 20} more")
        print("\n(preview — pass --apply to actually copy)")
        return 0

    if dest.exists() and any(dest.iterdir()):
        print(f"error: --dest {dest} already exists and is not empty — remove it or pick an empty target", file=sys.stderr)
        return 2

    patterns = load_patterns(ROOT)
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT, dest, ignore=ignore_factory(ROOT, patterns), dirs_exist_ok=True)

    leaks = assert_clean(dest)
    if leaks:
        print("error: distribution copy still contains excluded paths after copy:", file=sys.stderr)
        for rel in leaks:
            print(f"  - {rel}", file=sys.stderr)
        print("This is a bug in .distignore/ALWAYS_EXCLUDE_DIRS coverage, not something to work around by hand.", file=sys.stderr)
        return 1

    copy, skip = planned_copy(dest)  # counts only, dest already has the real tree at this point
    print(f"[done] copied to {dest}")
    print(f"[done] {len(skip)} entr(y/ies) excluded per .distignore/ALWAYS_EXCLUDE_DIRS")
    print("[done] post-copy check: no .git/__pycache__/.pytest_cache/out/credentials.json/research_markers.local.json in the export")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
