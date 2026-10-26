"""Catalog of named lab materials: `<root>/catalog.json` (optional; absent = empty).

{"enzyme": {"<name>": {"project": "<key>", "path": "@/x", "aliases": [...], "note": "..."}},
 "standard": {...}, "sheet": {...}, "compound": {...}, "reaction": {...}}
Records link an entry with `links: [{rel: <kind>, name: "<name or alias>"}]`.
`path` resolves like any record path (`@/` = the entry's own project folder, else root-relative);
it is required for enzyme/standard/sheet and optional for the domain kinds compound/reaction.
Domain fields (enzyme organism/cofactor/..., compound smiles/..., reaction equation/keq/..., and
`related`) are format-checked here; their cross-references and chemistry are linted in rules.py.
An unknown top-level kind is skipped with a warning (`Catalog.warnings`), never an error.
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
PATH_KINDS = ("enzyme", "standard", "sheet")  # `path` required
DOMAIN_KINDS = ("compound", "reaction")  # `path` optional
KINDS = PATH_KINDS + DOMAIN_KINDS
REL_VALUES = ("probably_same", "same", "distinct", "variant_of", "member_of")
REL_STATUS = ("unconfirmed", "confirmed")
KEQ_CONDITIONS = ("pH", "ionic_strength", "temperature_K", "pMg")


@dataclass
class Entry:
    kind: str
    name: str
    path: str | None
    project: str | None = None
    aliases: list = field(default_factory=list)
    note: str = ""
    data: dict = field(default_factory=dict)  # the raw entry object (domain fields live here)

    @property
    def label(self) -> str:
        return f"{self.kind}:{self.name}"


@dataclass
class Catalog:
    root: Path
    projects: dict
    entries: list[Entry] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

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
        if e.path is None:
            return None, None
        return paths.resolve(self.root, self.projects, e.project, e.path, "catalog entry")

    def path_problem(self, e: Entry) -> str | None:
        """None when the target exists; otherwise a short reason (existence check only)."""
        if e.path is None:
            return None  # domain entry without a file
        full, problem = self.full_path(e)
        if problem:
            return problem
        return None if paths.exists(full) else "does not exist"


def _str_list(where: str, raw, label: str) -> list:
    if not isinstance(raw, list) or not all(isinstance(a, str) and a.strip() for a in raw):
        raise LabRecordError(f"{where}.{label} must be a list of non-empty strings")
    return raw


def _check_related(where: str, raw) -> None:
    if not isinstance(raw, list):
        raise LabRecordError(f"{where}.related must be a list of {{name, rel, status, basis}}")
    for i, item in enumerate(raw):
        if not (isinstance(item, dict) and isinstance(item.get("name"), str) and item["name"].strip()):
            raise LabRecordError(f"{where}.related[{i}] needs a non-empty `name`")
        if item.get("rel") not in REL_VALUES:
            raise LabRecordError(f"{where}.related[{i}].rel must be one of {', '.join(REL_VALUES)}")
        if item.get("status") not in REL_STATUS:
            raise LabRecordError(f"{where}.related[{i}].status must be one of {', '.join(REL_STATUS)}")


def _check_participants(where: str, raw, label: str, second: str = "coef") -> None:
    if not isinstance(raw, list):
        raise LabRecordError(f"{where}.{label} must be a list of objects")
    for i, item in enumerate(raw):
        if not (isinstance(item, dict) and isinstance(item.get("name"), str) and item["name"].strip()):
            raise LabRecordError(f"{where}.{label}[{i}] needs a non-empty `name`")
        coef = item.get("coef", 1)
        if isinstance(coef, bool) or not isinstance(coef, (int, float)) or coef <= 0:
            raise LabRecordError(f"{where}.{label}[{i}].coef must be a positive number")
        if second == "to" and not (isinstance(item.get("to"), str) and item["to"].strip()):
            raise LabRecordError(f"{where}.{label}[{i}] needs `to` (the converted cofactor name)")


def _check_keq(where: str, raw) -> None:
    if not isinstance(raw, dict):
        raise LabRecordError(f"{where}.keq must be an object")
    v = raw.get("value")
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0:
        raise LabRecordError(f"{where}.keq.value must be a positive number")
    for k in KEQ_CONDITIONS:
        if k in raw and (isinstance(raw[k], bool) or not isinstance(raw[k], (int, float))):
            raise LabRecordError(f"{where}.keq.{k} must be a number")
    if "source" in raw and not isinstance(raw["source"], str):
        raise LabRecordError(f"{where}.keq.source must be a string")


def _check_domain(where: str, kind: str, raw: dict) -> None:
    """Format-only checks of the domain fields; unknown extra fields are tolerated."""
    for key in ("catalyzes", "cofactor", "code_ids", "regenerated_by"):
        if key in raw and not (key == "cofactor" and kind == "compound"):  # compound.cofactor is a bool
            _str_list(where, raw[key], key)
    for key in ("organism", "uniprot", "ec", "smiles", "inchikey", "formula", "equation", "enzyme", "rhea"):
        if key in raw and not (isinstance(raw[key], str) and raw[key].strip()):
            raise LabRecordError(f"{where}.{key} must be a non-empty string")
    if kind == "compound" and "cofactor" in raw and not isinstance(raw["cofactor"], bool):
        raise LabRecordError(f"{where}.cofactor must be true/false on a compound")
    if kind == "reaction" and "reversible" in raw and not isinstance(raw["reversible"], bool):
        raise LabRecordError(f"{where}.reversible must be true/false")
    for key in ("mass_da", "length_aa"):
        if key in raw and (isinstance(raw[key], bool) or not isinstance(raw[key], (int, float)) or raw[key] <= 0):
            raise LabRecordError(f"{where}.{key} must be a positive number")
    if "ids" in raw and not (isinstance(raw["ids"], dict) and all(isinstance(v, str) for v in raw["ids"].values())):
        raise LabRecordError(f"{where}.ids must be an object of strings")
    if "related" in raw:
        _check_related(where, raw["related"])
    if kind == "reaction":
        for key in ("substrates", "products"):
            if key in raw:
                _check_participants(where, raw[key], key)
        if "cofactors" in raw:
            _check_participants(where, raw["cofactors"], "cofactors", second="to")
        if "keq" in raw:
            _check_keq(where, raw["keq"])


def _entry(path: Path, kind: str, name: str, raw, projects: dict) -> Entry:
    where = f"{path}: {kind}.{name}"
    if not isinstance(raw, dict):
        raise LabRecordError(f"{where} must be an object")
    p = raw.get("path")
    if p is None and kind in DOMAIN_KINDS:
        pass
    elif not (isinstance(p, str) and p.strip()):
        raise LabRecordError(f"{where}.path must be a non-empty string")
    project = raw.get("project")
    if project is not None and project not in projects:
        raise LabRecordError(f"{where}.project {project!r} is not a key in the projects config")
    aliases = raw.get("aliases", [])
    if not isinstance(aliases, list) or not all(isinstance(a, str) and a.strip() for a in aliases):
        raise LabRecordError(f"{where}.aliases must be a list of non-empty strings")
    _check_domain(where, kind, raw)
    return Entry(kind, name, p, project, aliases, str(raw.get("note") or ""), raw)


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
    if unknown:  # forward compatibility: a newer tool may add kinds
        cat.warnings.append(f"{path}: unknown kind {unknown} skipped (known: {', '.join(KINDS)})")
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
