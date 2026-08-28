#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Single source of truth (SSOT) for `.distignore` rules.

Why this is a separate module:
  This logic used to live only inside `make_checksums.py`; `install.py` and
  `doctor.py` **never read** `.distignore`. So the declaration "these files
  must not be distributed" only applied within the SHA256SUMS manifest's
  scope and had zero effect on the actual install path — the rule existed
  but was never wired in (measured 2026-08-07).

  Copying the same fnmatch logic into two places creates drift where only
  one side gets fixed. Pattern interpretation happens in exactly one place
  here, and callers pass only the root path.

Usage:
    from distignore import load_patterns, is_excluded
    pats = load_patterns(toolkit_root)
    if is_excluded("skills/foo/secrets.json", pats): ...
"""
from __future__ import annotations

import fnmatch
from pathlib import Path

# Always excluded, even if absent from `.distignore` (build artifacts / caches).
# These have no reason to be in the distribution tree, and this must not leak
# through even if a human forgets to add the rule.
ALWAYS_EXCLUDE_DIRS = {
    ".git", "__pycache__", ".cache", ".pytest_cache",
    "node_modules", ".ipynb_checkpoints",
}


def load_patterns(root: Path) -> list[str]:
    """Reads the active patterns from `<root>/.distignore`. Returns an empty list if absent."""
    path = Path(root) / ".distignore"
    if not path.exists():
        return []
    out: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def is_excluded(rel_posix: str, patterns: list[str]) -> bool:
    """Decides whether a root-relative path (POSIX separators) should be excluded from distribution."""
    candidates = (rel_posix, f"/{rel_posix}")
    for pat in patterns:
        for cand in candidates:
            if fnmatch.fnmatch(cand, pat):
                return True
        # For patterns like `**/foo/**`, also check at the path-segment level.
        core = pat.strip("*/")
        if core and f"/{core}/" in f"/{rel_posix}/":
            return True
    return False


def ignore_factory(src_root: Path, patterns: list[str]):
    """Builds the callback to pass to `shutil.copytree(ignore=...)`.

    copytree hands over (directory, names in it) and expects back "names to
    exclude". This reconstructs each entry's root-relative path and judges
    it against `.distignore`.
    """
    src_root = Path(src_root).resolve()

    def _ignore(directory: str, names: list[str]) -> set[str]:
        skipped: set[str] = set()
        here = Path(directory).resolve()
        for name in names:
            if name in ALWAYS_EXCLUDE_DIRS or name.endswith(".pyc"):
                skipped.add(name)
                continue
            try:
                rel = (here / name).relative_to(src_root).as_posix()
            except ValueError:
                continue
            if is_excluded(rel, patterns):
                skipped.add(name)
        return skipped

    return _ignore
