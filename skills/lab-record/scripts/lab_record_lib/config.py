"""Layered configuration: local file + shared `<root>/lab-record.config.json`.

Root precedence : --root > env LAB_RECORD_ROOT > local config `root` > cwd walk-up
                  (nearest ancestor directory holding lab-record.config.json).
Shared layer    : `<root>/lab-record.config.json` provides `projects` and `people`.
Merge           : local overrides shared per key (people) / per field (projects).
A shared file never carries `root` (ignored with a warning on stderr).
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .parse import LabRecordError, read_text

DEFAULT_CONFIG = Path.home() / ".config" / "lab-record" / "config.json"
SHARED_NAME = "lab-record.config.json"
GID_RE = re.compile(r"[0-9]+")


@dataclass
class Config:
    root: Path
    people: dict = field(default_factory=dict)
    projects: dict = field(default_factory=dict)
    shared_path: Path | None = None


def is_digits(value) -> bool:
    """ASCII-digits-only gid check (str, or a positive non-bool int with a warning). Format only."""
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        if value > 0:
            print("WARNING: quote gids as strings (YAML may parse 0123 as octal)", file=sys.stderr)
            return True
        return False
    return isinstance(value, str) and re.fullmatch(r"[0-9]+", value) is not None


def _read_json(path: Path, label: str) -> dict:
    try:
        data = json.loads(read_text(path))
    except ValueError as exc:
        raise LabRecordError(f"{path}: invalid JSON ({exc})") from exc
    if not isinstance(data, dict):
        raise LabRecordError(f"{path}: {label} must be a JSON object")
    return data


def _validate(data: dict, path: Path) -> None:
    ignored = [k for k in ("notify",) if k in data]
    ignored += [f"projects.{k}.notion_project" for k, v in (data.get("projects") or {}).items()
                if isinstance(v, dict) and "notion_project" in v]
    if ignored:
        print(f"NOTE: {path}: {', '.join(ignored)} ignored: notifications are off by design", file=sys.stderr)
    if not isinstance(data.get("people") or {}, dict):
        raise LabRecordError(f"{path}: `people` must be an object")
    projects = data.get("projects") or {}
    if not isinstance(projects, dict):
        raise LabRecordError(f"{path}: `projects` must be an object")
    for key, proj in projects.items():
        if not isinstance(proj, dict):
            raise LabRecordError(f"{path}: projects.{key} must be an object")
        folder = proj.get("folder")
        if folder is not None and not (isinstance(folder, str) and folder.strip()):
            raise LabRecordError(f"{path}: projects.{key}.folder must be a non-empty string")
        if isinstance(folder, str) and "\\" in folder:
            raise LabRecordError(f"{path}: projects.{key}.folder must use / separators, got {folder!r}")
        gid = proj.get("asana_project")
        if gid is not None and not is_digits(gid):
            raise LabRecordError(f"{path}: projects.{key}.asana_project must be digits only, got {gid!r}")


def load_config(config_arg: str | None) -> dict:
    """Local layer. Missing default file = {}; missing explicit --config = error."""
    explicit = config_arg is not None
    path = Path(config_arg).expanduser() if explicit else DEFAULT_CONFIG
    if not path.is_file():
        if explicit:
            raise LabRecordError(f"config not found: {path}")
        return {}
    data = _read_json(path, "config")
    _validate(data, path)
    return data


def find_root_from_cwd(start: Path | None = None) -> Path | None:
    cur = (start or Path.cwd()).resolve()
    for d in (cur, *cur.parents):
        if (d / SHARED_NAME).is_file():
            return d
    return None


def load_shared(root: Path) -> tuple[dict, Path | None]:
    path = root / SHARED_NAME
    if not path.is_file():
        return {}, None
    data = _read_json(path, "shared config")
    if "root" in data:
        print(f"WARNING: {path}: `root` is not allowed in a shared config; ignored", file=sys.stderr)
        data = {k: v for k, v in data.items() if k != "root"}
    _validate(data, path)
    return data, path


def merge(shared: dict, local: dict) -> tuple[dict, dict]:
    people = {**(shared.get("people") or {}), **(local.get("people") or {})}
    projects = {k: dict(v) for k, v in (shared.get("projects") or {}).items()}
    for key, proj in (local.get("projects") or {}).items():
        merged = {**projects.get(key, {}), **proj}
        if proj.get("folder") is None and (projects.get(key) or {}).get("folder") is not None:
            merged["folder"] = projects[key]["folder"]  # a local null must not erase the shared folder
        projects[key] = merged
    return people, projects


def resolve_config(root_arg: str | None, config_arg: str | None) -> Config:
    local = load_config(config_arg)
    root = root_arg or os.environ.get("LAB_RECORD_ROOT") or local.get("root")
    if not root:
        found = find_root_from_cwd()
        if found is None:
            raise LabRecordError(
                "no root: pass --root, set LAB_RECORD_ROOT, provide a config with `root`, "
                f"or run inside a folder tree that holds {SHARED_NAME}")
        root = found
    root = Path(root).expanduser()
    if not root.is_dir():
        raise LabRecordError(f"root is not a directory: {root}")
    shared, shared_path = load_shared(root)
    people, projects = merge(shared, local)
    return Config(root=root, people=people, projects=projects, shared_path=shared_path)


RECORD_DIRS = ("protocols", "experiments", "discussions", "decisions")


def announce_root(cfg: Config) -> None:
    """stderr: which root is in use; warn when it holds none of the record folders."""
    print(f"lab-record root: {cfg.root}", file=sys.stderr)
    if not any((cfg.root / d).is_dir() for d in RECORD_DIRS):
        print(f"WARNING: {cfg.root} has none of {', '.join(RECORD_DIRS)} (wrong root?)", file=sys.stderr)
