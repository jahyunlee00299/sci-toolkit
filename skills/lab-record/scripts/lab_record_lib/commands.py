"""Write-side commands: new (allocate + template), new prot version, close, index."""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from string import Template
from urllib.parse import quote

from . import model
from .baseline import HashBaseline, is_git_root
from .model import DIRS, TYPES, Config, Index, Record, iter_refs, scan_strict
from .parse import LabRecordError, compose, parse, read_text, set_scalar, write_text

TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "templates"
MAX_ATTEMPTS = 100


def _j(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def _clean_title(title: str) -> str:
    title = " ".join(str(title).split())
    if not title:
        raise LabRecordError("--title must not be empty")
    return title


def _default_owner(cfg: Config, owner: str | None):
    if owner:
        return owner
    return next(iter(cfg.people)) if len(cfg.people) == 1 else None


def _next_id(typ: str, existing: set[str], day: str) -> str:
    prefix = TYPES[typ]
    if typ == "prot":
        nums = [int(m.group(1)) for k in existing if (m := re.match(r"^PROT-(\d+)@", k))]
        return f"PROT-{max(nums, default=0) + 1:03d}"
    nums = [int(m.group(1)) for k in existing if (m := re.match(rf"^{prefix}-{day}-(\d{{2}})$", k))]
    n = max(nums, default=0) + 1
    if n > 99:
        raise LabRecordError(f"more than 99 {prefix} records on {day}")
    return f"{prefix}-{day}-{n:02d}"


def _target(root: Path, typ: str, rid: str, version: str | None) -> Path:
    if typ == "prot":
        return root / DIRS[typ] / f"{rid}_{version}.md"
    year = "20" + rid.split("-")[1][:2]
    return root / DIRS[typ] / year / f"{rid}.md"


def _render(typ: str, values: dict) -> str:
    tpl = Template((TEMPLATE_DIR / f"{typ}.md").read_text(encoding="utf-8"))
    return tpl.safe_substitute(values)


def new_record(cfg: Config, typ: str, title: str, *, protocol=None, about=(), from_ids=(),
               version="v1", owner=None, project=None, day: dt.date | None = None) -> Path:
    day = day or dt.date.today()
    yymmdd, title = day.strftime("%y%m%d"), _clean_title(title)
    owner = _default_owner(cfg, owner)
    if typ == "exp" and protocol and not model.PINNED_PROT.match(protocol):
        raise LabRecordError(f"--protocol must be version-pinned (PROT-007@v3), got {protocol}")
    if not model.VERSION_RE.match(version):
        raise LabRecordError(f"--version must look like v3, got {version}")
    for _ in range(MAX_ATTEMPTS):
        rid = _next_id(typ, model.scan_ids(cfg.root), yymmdd)  # re-scan right before every write
        path = _target(cfg.root, typ, rid, version)
        text = _render(typ, {
            "id": rid, "title": _j(title), "title_plain": title, "owner": _j(owner),
            "project": _j(project), "created": day.isoformat(), "supersedes": "null",
            "version": _j(version), "changed_from": "null", "change_reason": '""',
            "protocol": _j(protocol), "about": _j(list(about)), "from_ids": _j(list(from_ids)),
            "participants": _j([owner] if owner else []),
        })
        try:
            write_text(path, text, exclusive=True)
            return path
        except FileExistsError:
            continue  # another session took this id between scan and write: bump
    raise LabRecordError("could not allocate a free id")


def new_prot_version(cfg: Config, prot_id: str, *, title=None, reason="", day=None) -> Path:
    """Copy the latest PROT-NNN version to the next vN+1; mark the old one superseded."""
    day = day or dt.date.today()
    index = Index(scan_strict(cfg.root))
    old = index.latest_prot(prot_id)
    if old is None:
        raise LabRecordError(f"no protocol {prot_id} found")
    for _ in range(MAX_ATTEMPTS):
        old = Index(scan_strict(cfg.root)).latest_prot(prot_id)
        nxt = f"v{int(old.version[1:]) + 1}"
        fm = dict(old.fm)
        fm.update(version=nxt, changed_from=old.version, change_reason=reason or "",
                  status="draft", created=day.isoformat(), updated=day.isoformat(),
                  supersedes=old.key)
        if title:
            fm["title"] = _clean_title(title)
        note = f"- {nxt} ({day.isoformat()}): {reason or 'new version'}\n"
        body = old.body.rstrip("\n") + "\n\n" + note
        path = _target(cfg.root, "prot", prot_id, nxt)
        try:
            write_text(path, compose(fm, body), exclusive=True)
        except FileExistsError:
            continue
        if old.status != "superseded":
            text = set_scalar(read_text(old.path), "status", "superseded")
            write_text(old.path, text)
        return path
    raise LabRecordError("could not allocate a free protocol version")


def close_record(cfg: Config, ref: str, day: dt.date | None = None) -> Path:
    day = day or dt.date.today()
    index = Index(scan_strict(cfg.root))
    rec = index.get(ref)
    if rec is None:
        raise LabRecordError(f"record not found: {ref} (PROT needs a pinned id like PROT-007@v3)")
    if rec.status != "closed":
        text = set_scalar(read_text(rec.path), "status", "closed")
        text = set_scalar(text, "updated", day.isoformat())
        write_text(rec.path, text)
    if not is_git_root(cfg.root):
        fresh = next(r for r in scan_strict(cfg.root) if r.key == rec.key)
        HashBaseline(cfg.root).store(fresh)
    return rec.path


def _esc(text) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def build_index(cfg: Config) -> str:
    index = Index(scan_strict(cfg.root))
    lines = ["<!-- GENERATED by lab_record.py index -- do not edit by hand; regenerate instead -->",
             "", "# Record index (GENERATED)", ""]
    for typ, label in (("prot", "Protocols"), ("exp", "Experiments"),
                       ("disc", "Discussions"), ("dec", "Decisions")):
        lines += [f"## {label}", "", "| ID | Title | Status | Links |", "|---|---|---|---|"]
        for r in index.of_type(typ):
            links = ", ".join(sorted({ref for _, ref in iter_refs(r)}))
            lines.append(f"| [{r.key}]({quote(r.rel)}) | {_esc(r.fm.get('title', ''))} "
                         f"| {r.status} | {_esc(links)} |")
        lines.append("")
    return "\n".join(lines)


def write_index(cfg: Config) -> Path:
    path = cfg.root / "INDEX.md"
    write_text(path, build_index(cfg))
    return path
