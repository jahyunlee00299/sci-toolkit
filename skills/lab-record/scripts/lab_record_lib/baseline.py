"""Rule-1 baselines: what a closed record looked like when it was frozen.

Git mode  : baseline = `git show HEAD:./<path>` (only if HEAD copy was status closed).
Hash mode : baseline = <root>/.lab_record/hashes.json entry written by `close`.
Both reduce to the same snapshot {fm digest, body length, body-prefix sha256}.
A frozen record may change only: body gains a `## Addendum (YYYY-MM-DD)` section, and
status may move closed -> superseded (the sole frontmatter change allowed).
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

from .model import Record
from .parse import LabRecordError, parse, read_text, write_text, normalize

ADDENDUM_RE = re.compile(r"\A\s*## Addendum \(\d{4}-\d{2}-\d{2}\)")
FROZEN_STATUS = ("closed", "superseded")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def snapshot(fm: dict, body: str) -> dict:
    frozen_fm = {k: v for k, v in fm.items() if k != "status"}
    digest = _sha(json.dumps(frozen_fm, sort_keys=True, ensure_ascii=False, default=str))
    b = body.rstrip()
    return {"fm": digest, "len": len(b), "sha": _sha(b)}


def compare(snap: dict, rec: Record) -> list[str]:
    """Return violation messages (empty = unchanged apart from an allowed addendum)."""
    out = []
    if rec.status not in FROZEN_STATUS:
        out.append(f"status changed from closed to {rec.status}")
    if snapshot(rec.fm, "")["fm"] != snap["fm"]:
        out.append("frontmatter of a closed record was edited (write a new record with `supersedes:`)")
    body = normalize(rec.body)
    n = snap["len"]
    if len(body) < n or _sha(body[:n]) != snap["sha"]:
        out.append("body of a closed record was edited (only `## Addendum (YYYY-MM-DD)` may be appended)")
    else:
        rest = body[n:]
        if rest.strip() and not ADDENDUM_RE.match(rest):
            out.append("text appended to a closed record must start with `## Addendum (YYYY-MM-DD)`")
    return out


def _git(root: Path, *args: str):
    try:
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                              encoding="utf-8", errors="replace")
    except OSError:
        return None


def is_git_root(root: Path) -> bool:
    r = _git(root, "rev-parse", "--is-inside-work-tree")
    return bool(r and r.returncode == 0 and r.stdout.strip() == "true")


class GitBaseline:
    def __init__(self, root: Path):
        self.root = root
        self._changed: set[str] | None = None

    def _changed_paths(self) -> set[str] | None:
        """Paths (relative to root) that differ from HEAD; None if git cannot tell."""
        if self._changed is None:
            r = _git(self.root, "-c", "core.quotepath=off", "diff", "--name-only", "-z", "--relative", "HEAD")
            if not r or r.returncode != 0:
                return None
            self._changed = {p for p in r.stdout.split(chr(0)) if p}
        return self._changed

    def check(self, rec: Record) -> list[str]:
        changed = self._changed_paths()
        if changed is not None and rec.rel not in changed:
            return []  # identical to HEAD: cannot violate append-only
        r = _git(self.root, "show", f"HEAD:./{rec.rel}")
        if not r or r.returncode != 0:
            return []  # not committed yet: no baseline to compare against
        try:
            fm, body = parse(r.stdout)
        except LabRecordError:
            return []
        if fm.get("status") != "closed":
            return []
        return compare(snapshot(fm, body), rec)


class HashBaseline:
    def __init__(self, root: Path):
        self.root = root
        self.file = root / ".lab_record" / "hashes.json"

    def _load(self) -> dict:
        if not self.file.is_file():
            return {}
        try:
            data = json.loads(read_text(self.file))
        except ValueError as exc:
            raise LabRecordError(f"{self.file}: invalid JSON ({exc})") from exc
        if not isinstance(data, dict):
            raise LabRecordError(f"{self.file}: expected a JSON object")
        return data

    def store(self, rec: Record) -> None:
        data = self._load()
        data[rec.key] = snapshot(rec.fm, rec.body)
        write_text(self.file, json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n")

    def check(self, rec: Record) -> list[str]:
        snap = self._load().get(rec.key)
        if snap is None:
            if rec.status == "closed":
                return ["closed but no stored hash baseline (close it with `lab_record.py close`)"]
            return []
        return compare(snap, rec)


def baseline_for(root: Path):
    return GitBaseline(root) if is_git_root(root) else HashBaseline(root)
