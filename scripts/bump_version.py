#!/usr/bin/env python3
"""Bump the patch version in .claude-plugin/plugin.json + add a CHANGELOG.md entry.

Called from the post-commit git hook (scripts/git-hooks/post-commit) — every
commit gets its own patch version. That per-commit granularity (not
per-release) is a deliberate policy choice by the repo owner (260809), not
this script's judgment call; this script only executes it.

Usage: python bump_version.py --commit-subject "<git log -1 --format=%s>"
Exit 0 on success, 1 if plugin.json's version isn't a plain X.Y.Z semver
(so the hook can warn instead of corrupting the file).
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN_JSON = ROOT / ".claude-plugin" / "plugin.json"
CHANGELOG = ROOT / "CHANGELOG.md"

_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def bump_patch(version: str) -> str:
    m = _SEMVER_RE.match(version)
    if not m:
        raise ValueError(f"not a plain X.Y.Z semver: {version!r}")
    major, minor, patch = (int(g) for g in m.groups())
    return f"{major}.{minor}.{patch + 1}"


def _insert_changelog_entry(new_version: str, subject: str) -> None:
    today = datetime.date.today().isoformat()
    entry = f"## [{new_version}] — {today}\n\n- {subject}\n\n"
    text = CHANGELOG.read_text(encoding="utf-8")
    marker = "\n## ["
    idx = text.find(marker)
    if idx == -1:
        text = text.rstrip("\n") + "\n\n" + entry
    else:
        text = text[: idx + 1] + entry + text[idx + 1 :]
    # newline="\n": this repo's .gitattributes pins text files to LF; Python's
    # default text-mode write translates \n -> \r\n on Windows, which would
    # silently defeat that policy (260809 — caught by test_checksums_manifest).
    CHANGELOG.write_text(text, encoding="utf-8", newline="\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit-subject", default="(no subject)")
    args = ap.parse_args()

    data = json.loads(PLUGIN_JSON.read_text(encoding="utf-8"))
    old = data.get("version", "")
    try:
        new = bump_patch(old)
    except ValueError as e:
        print(f"bump_version: SKIP ({e})", file=sys.stderr)
        return 1

    data["version"] = new
    PLUGIN_JSON.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8", newline="\n",
    )
    _insert_changelog_entry(new, args.commit_subject.strip() or "(no subject)")
    print(f"{old} -> {new}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
