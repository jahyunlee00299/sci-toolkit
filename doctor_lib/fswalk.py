"""Shared directory-walk helper used by both the SENTINEL scan and the
dead-automation artifact resolver."""

from __future__ import annotations

import os
from pathlib import Path

# Directories we never want to walk into during a tree scan (huge,
# irrelevant, or already-excluded-from-distribution paths).
SCAN_EXCLUDE_DIRS = {
    ".git",
    "__pycache__",
    ".cache",
    "node_modules",
    ".venv",
    "venv",
    ".mypy_cache",
    ".pytest_cache",
}


def _os_walk(root: Path):
    yield from os.walk(root)


def _walk_files(root: Path):
    for dirpath, dirnames, filenames in _os_walk(root):
        dirnames[:] = [d for d in dirnames if d not in SCAN_EXCLUDE_DIRS and not d.startswith(".git")]
        for fn in filenames:
            yield Path(dirpath) / fn
