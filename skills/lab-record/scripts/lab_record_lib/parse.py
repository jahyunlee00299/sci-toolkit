"""Parsing layer: frontmatter split / load / dump / single-key edit. No domain knowledge."""
from __future__ import annotations

import re
from pathlib import Path

import yaml


class LabRecordError(Exception):
    """Config / parse / IO problem (CLI exit code 2)."""


class _Loader(yaml.SafeLoader):
    """SafeLoader that keeps ISO dates as plain strings (round-trip safe)."""


_Loader.yaml_implicit_resolvers = {
    k: [(t, r) for t, r in v if t != "tag:yaml.org,2002:timestamp"]
    for k, v in yaml.SafeLoader.yaml_implicit_resolvers.items()
}

FM_RE = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)(.*)\Z", re.S)


def normalize(text: str) -> str:
    return text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")


def read_text(path: Path) -> str:
    try:
        return normalize(path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise LabRecordError(f"{path}: unreadable ({exc})") from exc


def write_text(path: Path, text: str, exclusive: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "x" if exclusive else "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def parse(text: str) -> tuple[dict, str]:
    m = FM_RE.match(normalize(text))
    if not m:
        raise LabRecordError("no YAML frontmatter block (--- ... ---)")
    try:
        fm = yaml.load(m.group(1), Loader=_Loader)
    except yaml.YAMLError as exc:
        raise LabRecordError(f"malformed frontmatter: {exc}") from exc
    if not isinstance(fm, dict):
        raise LabRecordError("frontmatter is not a mapping")
    return fm, m.group(2)


def dump_fm(fm: dict) -> str:
    return yaml.safe_dump(fm, allow_unicode=True, sort_keys=False,
                          default_flow_style=False, width=10000)


def compose(fm: dict, body: str) -> str:
    return f"---\n{dump_fm(fm)}---\n{body}"


def set_scalar(text: str, key: str, value: str) -> str:
    """Replace one top-level `key: ...` line in the frontmatter, preserving all else."""
    m = FM_RE.match(normalize(text))
    if not m:
        raise LabRecordError("no YAML frontmatter block")
    fm_text, body = m.group(1), m.group(2)
    pat = re.compile(rf"^{re.escape(key)}:.*$", re.M)
    if pat.search(fm_text):
        fm_text = pat.sub(lambda _: f"{key}: {value}", fm_text, count=1)
    else:
        fm_text += f"\n{key}: {value}"
    return f"---\n{fm_text}\n---\n{body}"
