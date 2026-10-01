"""Catalog of named lab materials: `<root>/catalog.json` (optional; absent = empty).

{"enzyme": {"<name>": {"project": "<key>", "path": "@/x", "aliases": [...], "note": "..."}},
 "standard": {...}, "sheet": {...}}
Records link an entry with `links: [{rel: enzyme|standard|sheet, name: "<name or alias>"}]`.
`path` resolves like any record path (`@/` = the entry's own project folder, else root-relative).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import paths
from .config import Config
from .model import Record, as_list
from .parse import LabRecordError, read_text

CATALOG_NAME = "catalog.json"
KINDS = ("enzyme", "standard", "sheet")


@dataclass
class Entry:
    kind: str
    name: str
    path: str
    project: str | None = None
    aliases: list = field(default_factory=list)
    note: str = ""

    @property
    def label(self) -> str:
        return f"{self.kind}:{self.name}"


@dataclass
class Catalog:
    root: Path
    projects: dict
    entries: list[Entry] = field(default_factory=list)

    def resolve(self, kind: str, name) -> Entry | None:
        want = str(name).strip().casefold()
        for e in self.entries:
            if e.kind == kind and want in {e.name.casefold(), *(a.casefold() for a in e.aliases)}:
                return e
        return None

    def find(self, name) -> list[Entry]:
        """Every entry (any kind) whose name or alias matches."""
        return [e for k in KINDS if (e := self.resolve(k, name))]

    def full_path(self, e: Entry) -> tuple[Path | None, str | None]:
        return paths.resolve(self.root, self.projects, e.project, e.path, "catalog entry")

    def path_problem(self, e: Entry) -> str | None:
        """None when the target exists; otherwise a short reason (existence check only)."""
        full, problem = self.full_path(e)
        if problem:
            return problem
        return None if paths.exists(full) else "does not exist"


def _entry(path: Path, kind: str, name: str, raw, projects: dict) -> Entry:
    where = f"{path}: {kind}.{name}"
    if not isinstance(raw, dict):
        raise LabRecordError(f"{where} must be an object")
    p = raw.get("path")
    if not (isinstance(p, str) and p.strip()):
        raise LabRecordError(f"{where}.path must be a non-empty string")
    project = raw.get("project")
    if project is not None and project not in projects:
        raise LabRecordError(f"{where}.project {project!r} is not a key in the projects config")
    aliases = raw.get("aliases", [])
    if not isinstance(aliases, list) or not all(isinstance(a, str) and a.strip() for a in aliases):
        raise LabRecordError(f"{where}.aliases must be a list of non-empty strings")
    return Entry(kind, name, p, project, aliases, str(raw.get("note") or ""))


def load_catalog(cfg: Config) -> Catalog:
    cat = Catalog(cfg.root, cfg.projects)
    path = cfg.root / CATALOG_NAME
    if not path.is_file():
        return cat
    try:
        data = json.loads(read_text(path))
    except ValueError as exc:
        raise LabRecordError(f"{path}: invalid JSON ({exc})") from exc
    if not isinstance(data, dict):
        raise LabRecordError(f"{path}: catalog must be a JSON object")
    unknown = sorted(set(data) - set(KINDS))
    if unknown:
        raise LabRecordError(f"{path}: unknown kind {unknown} (allowed: {', '.join(KINDS)})")
    for kind in KINDS:
        group = data.get(kind, {})
        if not isinstance(group, dict):
            raise LabRecordError(f"{path}: {kind} must be an object")
        seen: dict[str, str] = {}
        for name, raw in group.items():
            e = _entry(path, kind, name, raw, cfg.projects)
            own = set()
            for token in (e.name, *e.aliases):
                if token.casefold() in own:
                    continue  # same alias repeated inside one entry: harmless
                own.add(token.casefold())
                if token.casefold() in seen:
                    raise LabRecordError(
                        f"{path}: {kind} name/alias {token!r} is ambiguous ({seen[token.casefold()]} / {name})")
                seen[token.casefold()] = name
            cat.entries.append(e)
    return cat


def catalog_links(rec: Record):
    """Yield (kind, name) for every catalog-typed link of a record."""
    for item in as_list(rec.fm.get("links")):
        if isinstance(item, dict) and item.get("rel") in KINDS and item.get("name"):
            yield item["rel"], str(item["name"])


def users_of(records: list[Record], cat: Catalog, entry: Entry) -> list[Record]:
    out = [r for r in records
           if any(k == entry.kind and cat.resolve(k, n) is entry for k, n in catalog_links(r))]
    return sorted(out, key=lambda r: r.key)
