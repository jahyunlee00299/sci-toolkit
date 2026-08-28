#!/usr/bin/env python3
"""Regenerate SHA256SUMS — builds a hash manifest of every distributed file.

Used to verify files weren't corrupted after copying to a USB drive/shared
folder (`doctor.py`'s first check reads this file).

Usage:
    python scripts/make_checksums.py            # preview (change summary only)
    python scripts/make_checksums.py --apply    # actually update SHA256SUMS

Rules:
- Follows `.distignore`'s exclusion rules as-is (a file that won't be
  distributed also stays out of the manifest).
- Excludes `SHA256SUMS` itself (it cannot hash itself).
- Normalizes paths to POSIX form starting with `./` (identical on Windows/Linux).
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import io
import subprocess
import sys
from pathlib import Path

# Windows' default console is cp949, which dies on Korean/symbol output. Force UTF-8.
# reconfigure instead of TextIOWrapper — a wrapper takes ownership of the
# underlying stream, so once it's GC'd after import it closes the caller's
# stdout too (measured).
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "SHA256SUMS"
DISTIGNORE = ROOT / ".distignore"

# Always excluded even if not in .distignore (generated output / caches)
#
# `out` was missing from here once, so 6 local run artifacts made it into the
# manifest (260807). Someone who clones the repo doesn't have those files, so
# doctor fails unconditionally with "6 missing" — a manifest that only passes
# on the machine that built it is not an integrity check. .gitignore had
# `out/*`, but this script only reads .distignore, so it wasn't caught there.
ALWAYS_EXCLUDE_DIRS = {".git", "__pycache__", ".cache", ".pytest_cache",
                       "node_modules", ".ipynb_checkpoints", "out"}


def load_patterns() -> list[str]:
    if not DISTIGNORE.exists():
        return []
    out = []
    for line in DISTIGNORE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def is_excluded(rel_posix: str, patterns: list[str]) -> bool:
    candidates = (rel_posix, f"/{rel_posix}")
    for pat in patterns:
        for cand in candidates:
            if fnmatch.fnmatch(cand, pat):
                return True
        # Also check `**/foo/**`-style patterns at the path-segment level
        core = pat.strip("*/")
        if core and f"/{core}/" in f"/{rel_posix}/":
            return True
    return False


def iter_files(patterns: list[str]):
    """Yield the (file, relative path) pairs to put in the manifest in a
    **platform-independent order**.

    `sorted(ROOT.rglob("*"))` sorts Path objects, and that comparison differs
    by OS. On Windows `config/...` comes after `CLAUDE.md`, while on Linux
    `LICENSE` comes first — same file set, different manifest line order,
    which makes CI keep reporting "the manifest is stale" (measured 260807:
    62 lines differed, content identical). Sorting on the relative-path
    string instead gives the same output regardless of which OS built it.
    """
    entries = []
    for p in ROOT.rglob("*"):
        if p.is_dir():
            continue
        rel_parts = p.relative_to(ROOT).parts
        # Only look at path segments **inside** the repo. `p.parts` is an
        # absolute path, so it also includes ancestor folders above ROOT —
        # simply placing the repo under a commonly-named folder like
        # `~/out/sci-toolkit` would then exclude every single file. The
        # manifest ends up with 0 entries and doctor PASSes with
        # "0 file(s) verified" (measured 260807).
        if any(part in ALWAYS_EXCLUDE_DIRS for part in rel_parts):
            continue
        rel = p.relative_to(ROOT).as_posix()
        if p.resolve() == MANIFEST.resolve():
            continue
        if is_excluded(rel, patterns):
            continue
        entries.append((rel, p))
    for rel, p in sorted(entries):
        yield p, rel


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def tracked_files() -> set[str] | None:
    """The set of files git tracks. None if git is unavailable or outside a repo."""
    try:
        proc = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"],
                              capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    out = {p.decode("utf-8", "surrogateescape")
           for p in proc.stdout.split(b"\0") if p}
    return out or None


def untracked_entries(rels: list[str]) -> list[str] | None:
    """Return manifest entries that git does not track.

    Adding `out` to the exclusion list alone only defers the same problem to
    the next output folder. What actually ships is **the set of files
    committed to the repo** — that's exactly what someone else gets on clone.
    So the rule measures against that directly.

    Skips the check (returns None) if git is unavailable or outside a repo —
    this script might run from a copy on a USB drive, and treating the check
    as failed there would be a false positive.
    """
    # tracked_files() reads with `-z`. The default output renders non-ASCII
    # paths as quoted octal escapes like `"docs/06_\352\270..."`, and
    # comparing against that raw form would flag every Korean-named document
    # as "not tracked" (measured 260807: 7 false positives on documents).
    # NUL-separated output has no such escaping.
    tracked = tracked_files()
    if tracked is None:
        return None
    return sorted(r for r in rels if r not in tracked)


def read_existing() -> dict[str, str]:
    if not MANIFEST.exists():
        return {}
    out = {}
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, _, name = line.partition(" *")
        if name:
            out[name.strip()] = digest.strip()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Regenerate SHA256SUMS")
    ap.add_argument("--apply", action="store_true", help="Actually write to the file")
    args = ap.parse_args()

    patterns = load_patterns()
    old = read_existing()

    lines, new = [], {}
    for path, rel in iter_files(patterns):
        digest = sha256(path)
        new[f"./{rel}"] = digest
        lines.append(f"{digest} *./{rel}")

    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed = sorted(k for k in set(new) & set(old) if new[k] != old[k])

    print(f"Manifest targets: {len(new)} file(s) (previously {len(old)})")
    print(f"  added(추가) {len(added)} / changed(변경) {len(changed)} / removed(제거) {len(removed)}")
    # NOTE: the label words below ("추가"/"변경"/"제거") are matched literally by
    # tests/test_checksums_manifest.py, which greps stdout for "[추가]"/"[변경]"/"[제거]".
    # Do not translate them without updating that test too.
    for label, items in (("추가", added), ("변경", changed), ("제거", removed)):
        for k in items[:8]:
            print(f"    [{label}] {k}")
        if len(items) > 8:
            print(f"    [{label}] ... {len(items) - 8} more")

    # Always refuse on empty. A zero-entry integrity manifest doesn't pass
    # the check — it means **nothing was checked at all**, yet doctor would
    # PASS with "0 file(s) verified" in that state. The ancestor-folder bug
    # above manifested exactly this way, and the untracked guard also passes
    # trivially when the list is empty (stray is empty too).
    if not new:
        print("\nRefused — 0 manifest targets.")
        print("Either the exclusion rules matched too broadly (.distignore / ALWAYS_EXCLUDE_DIRS),")
        print("or the script picked the wrong repo root. An empty manifest is not verification.")
        return 1

    # The reverse direction — files git tracks but the manifest is missing.
    # untracked_entries() only checks one direction ("manifest -> tracked"),
    # so it can't catch a real distributed file dropped by an overly broad
    # exclusion rule. `out/.gitkeep` was missing exactly this way.
    tracked = tracked_files()
    if tracked is not None:
        patterns_now = patterns
        dropped = sorted(
            f for f in tracked - {k[2:] for k in new}
            if f != "SHA256SUMS"
            and not is_excluded(f, patterns_now)
            and not any(part in ALWAYS_EXCLUDE_DIRS for part in Path(f).parts))
        if dropped:
            print(f"\nWarning — {len(dropped)} file(s) tracked but missing from the manifest:")
            for k in dropped[:10]:
                print(f"    [missing] {k}")
            print("If the exclusion rules are broader than intended, narrow them; if intended, state it explicitly in .distignore.")

    stray = untracked_entries([k[2:] for k in new])
    if stray:
        print(f"\nRefused — {len(stray)} file(s) not tracked by git would enter the manifest.")
        for k in stray[:10]:
            print(f"    [untracked] {k}")
        if len(stray) > 10:
            print(f"    [untracked] ... {len(stray) - 10} more")
        print("Someone who clones the repo won't have these files, so doctor will definitely fail.")
        print("Add them to .distignore, or if they should be committed, commit them and re-run.")
        return 1
    if stray is None:
        print("\n(not a git repository — skipping the untracked-files check)")

    if args.apply:
        MANIFEST.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        print(f"\nWROTE {MANIFEST} ({len(lines)} entries)")
    else:
        print("\n(preview — pass --apply to actually write)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
