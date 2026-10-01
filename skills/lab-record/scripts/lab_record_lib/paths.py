"""Path-valued fields: `@/` project-relative resolution and existence checks (never read, never mtime)."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterator

from .model import Record, as_list

AT_PREFIX = "@/"
PATH_FIELDS = ("raw_data", "workbook", "matrix_config")


def _join(root: Path, value: str) -> Path:
    p = Path(value).expanduser()
    return p if p.is_absolute() else root / p


_DRIVE_RE = re.compile(r"^[A-Za-z]:")


def _inside(base: str, target: str) -> bool:
    b, t = os.path.normcase(base), os.path.normcase(target)
    try:
        return os.path.commonpath([b, t]) == b
    except ValueError:  # different drives
        return False


def resolve(root: Path, projects: dict, project, value, subject: str = "record") -> tuple[Path | None, str | None]:
    """Return (path, None) or (None, problem). `@/x` resolves against the project's folder
    and may not leave it. Backslashes are refused so every OS gives the same verdict."""
    s = str(value)
    if "\\" in s:
        return None, "use / separators (no backslashes)"
    if not s.startswith(AT_PREFIX):
        return _join(root, s), None
    if not isinstance(project, str) or not project.strip():
        return None, f"uses @/ but the {subject} has no project"
    if project not in projects:
        return None, f"unknown project key {project!r} (not in the projects config)"
    folder = (projects.get(project) or {}).get("folder")
    if not folder:
        return None, f"uses @/ but project {project!r} has no folder in the config"
    if "\\" in str(folder):
        return None, f"project {project!r} folder uses backslashes (use / separators)"
    rest = s[len(AT_PREFIX):]
    if rest.startswith("/") or _DRIVE_RE.match(rest) or Path(rest).is_absolute():
        return None, "escapes project folder (absolute path after @/)"
    base = os.path.abspath(_join(root, folder))
    target = os.path.abspath(os.path.join(base, rest))
    if not _inside(base, target):
        return None, "escapes project folder"
    return Path(target), None


def exists(path: Path) -> bool:
    try:
        return path.exists()  # existence only
    except OSError:
        return False


def iter_path_values(rec: Record) -> Iterator[tuple[str, str]]:
    """Yield (label, raw value) for every path-valued field of a record."""
    for fld in PATH_FIELDS:
        for v in as_list(rec.fm.get(fld)):
            yield fld, str(v)
    for item in as_list(rec.fm.get("links")):
        if isinstance(item, dict) and item.get("path"):
            yield f"{item.get('rel') or 'link'} link", str(item["path"])
