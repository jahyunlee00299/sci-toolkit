"""Domain model: record types, ids, config, scanning, reference index."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .config import DEFAULT_CONFIG, Config, load_config, resolve_config  # noqa: F401  (re-exported)
from .parse import LabRecordError, parse, read_text

TYPES = {"prot": "PROT", "exp": "EXP", "disc": "DISC", "dec": "DEC"}
DIRS = {"prot": "protocols", "exp": "experiments", "disc": "discussions", "dec": "decisions"}
STATUSES = ("draft", "active", "closed", "superseded")
ID_RES = {
    "prot": re.compile(r"^PROT-\d{3,}$"),
    "exp": re.compile(r"^EXP-\d{6}-\d{2}$"),
    "disc": re.compile(r"^DISC-\d{6}-\d{2}$"),
    "dec": re.compile(r"^DEC-\d{6}-\d{2}$"),
}
BARE_PROT = re.compile(r"^PROT-\d+$")
PINNED_PROT = re.compile(r"^PROT-\d+@v\d+$")
VERSION_RE = re.compile(r"^v(\d+)$")


@dataclass
class Record:
    path: Path
    rel: str
    fm: dict
    body: str
    type: str
    id: str
    version: str | None = None

    @property
    def key(self) -> str:
        return f"{self.id}@{self.version}" if self.type == "prot" else self.id

    @property
    def status(self) -> str:
        return self.fm.get("status")

    @property
    def canonical_stem(self) -> str:
        return f"{self.id}_{self.version}" if self.type == "prot" else self.id


def as_list(value) -> list:
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


def _load_record(root: Path, path: Path) -> Record:
    fm, body = parse(read_text(path))
    typ, rid, status = fm.get("type"), fm.get("id"), fm.get("status")
    if typ not in TYPES:
        raise LabRecordError(f"type must be one of {sorted(TYPES)}, got {typ!r}")
    if not isinstance(rid, str) or not ID_RES[typ].match(rid):
        raise LabRecordError(f"id {rid!r} does not match type {typ}")
    if status not in STATUSES:
        raise LabRecordError(f"status must be one of {STATUSES}, got {status!r}")
    version = None
    if typ == "prot":
        version = fm.get("version")
        if not isinstance(version, str) or not VERSION_RE.match(version):
            raise LabRecordError(f"PROT version must look like v3, got {version!r}")
    return Record(path, path.relative_to(root).as_posix(), fm, body, typ, rid, version)


def scan(root: Path) -> tuple[list[Record], list[str]]:
    """Load every record under the four type dirs. Returns (records, error strings)."""
    records, errors = [], []
    for d in DIRS.values():
        base = root / d
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.md")):
            try:
                records.append(_load_record(root, path))
            except (LabRecordError, ValueError) as exc:
                errors.append(f"{path}: {exc}")
    return records, errors


def scan_strict(root: Path) -> list[Record]:
    records, errors = scan(root)
    if errors:
        raise LabRecordError("; ".join(errors))
    return records


_PROT_NAME = re.compile(r"^(PROT-\d+)_(v\d+)(?!\d)")
_OTHER_NAME = re.compile(r"^((?:EXP|DISC|DEC)-\d{6}-\d{2})(?!\d)")


def key_from_stem(stem: str) -> str:
    """Record key a file name claims: canonical or conflict-copy name -> id (PROT -> 'PROT-007@v3')."""
    m = _PROT_NAME.match(stem)
    if m:
        return f"{m.group(1)}@{m.group(2)}"
    m = _OTHER_NAME.match(stem)
    return m.group(1) if m else stem


def scan_ids(root: Path) -> set[str]:
    """Cheap filename-based id scan (robust to malformed files and sync-conflict copies)."""
    found = set()
    for d in DIRS.values():
        base = root / d
        if base.is_dir():
            found.update(key_from_stem(p.stem) for p in base.rglob("*.md"))
    return found


def files_claiming(root: Path, key: str) -> list[Path]:
    """Every .md under the record dirs whose name claims `key` (canonical or conflict copy)."""
    out = []
    for d in DIRS.values():
        base = root / d
        if base.is_dir():
            out += [p for p in sorted(base.rglob("*.md")) if key_from_stem(p.stem) == key]
    return out


class Index:
    def __init__(self, records: list[Record]):
        self.records = records
        self.by_key: dict[str, Record] = {}
        self.duplicates: list[Record] = []
        for r in records:
            first = self.by_key.get(r.key)
            if first is None:
                self.by_key[r.key] = r
            elif r.path.stem == r.canonical_stem and first.path.stem != first.canonical_stem:
                self.by_key[r.key] = r  # the canonically named file is the keeper
                self.duplicates.append(first)
            else:
                self.duplicates.append(r)

    def get(self, ref, latest_ok: bool = False) -> Record | None:
        ref = str(ref)
        if ref in self.by_key:
            return self.by_key[ref]
        if latest_ok and BARE_PROT.match(ref):
            return self.latest_prot(ref)
        return None

    def latest_prot(self, pid: str) -> Record | None:
        vs = [r for r in self.records if r.type == "prot" and r.id == pid]
        return max(vs, key=lambda r: int(r.version[1:])) if vs else None

    def of_type(self, typ: str) -> list[Record]:
        return sorted((r for r in self.records if r.type == typ), key=lambda r: r.key)


def iter_refs(rec: Record):
    """Yield (field, reference-string) for every ID reference in a record."""
    fm = rec.fm
    if fm.get("protocol") not in (None, ""):
        yield "protocol", str(fm["protocol"])
    for f in ("about", "from"):
        for v in as_list(fm.get(f)):
            yield f, str(v)
    if fm.get("supersedes"):
        yield "supersedes", str(fm["supersedes"])
    for item in as_list(fm.get("links")):
        if isinstance(item, dict) and item.get("id"):
            yield "links", str(item["id"])
    for item in as_list(fm.get("next")):
        if isinstance(item, dict) and item.get("id"):
            yield "next.id", str(item["id"])
