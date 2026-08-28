#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shrunken-version detector — after a skill has been rewritten, structurally
checks *whether any capability was dropped*.

What this solves
------------------
After a skill doc gets sanitized (domain examples stripped) or refactored,
"looks fine" is not a judgment you can trust — a shrunken version can look
like a well-written document too. When the 2026-06-27 sanitization pass took
`update_notion.py` from 15.9KB down to 7.4KB, the file still existed intact
and the exit code was 0, and as a result the automation silently produced
nothing for 4 weeks.

An LLM quality comparison (a blind comparator, etc.) looks at "which is the
better piece of writing". This tool looks at a different axis: **can the new
version still do what the original did.** The two are complementary, not a
substitute for one another.

What this counts
------------------
Four proxy indicators of what a document "says it can do":
  · section headings (##/###)  — topics covered
  · file/path references        — assets it depends on
  · execution commands          — what can actually be run
  · overall length               — narrative loss not caught by the above three

A renamed item is not a loss. Sanitization's whole point is renaming, so if
the total count stays the same, it passes — a false positive here makes the
tool useless.

Usage
-----
    python scripts/capability_diff.py OLD NEW           # compare two files
    python scripts/capability_diff.py --skill docx --baseline <dir>
    exit 0 = no loss / 1 = suspected loss (details on stdout)
"""
from __future__ import annotations

import sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path

# Warn if the length shrinks more than this ratio. The 260727 case was 0.53.
DEFAULT_SHRINK_LIMIT = 0.30

_SECTION_RE = re.compile(r"^#{2,4}\s+(.+?)\s*$", re.MULTILINE)
# path-shaped tokens with an extension, like `scripts/foo.py`, references/bar.md
_REF_RE = re.compile(r"[\w./-]+\.(?:py|md|json|ya?ml|sh|ps1|txt|csv|html)\b")
# execution commands in or out of a code fence — a line starting with an interpreter/runner
_CMD_RE = re.compile(
    r"^\s*(?:\$\s*)?((?:python3?|bash|sh|npx|node|pytest|pwsh|powershell)\s+[\w./\\-]+)",
    re.MULTILINE)

# Common tokens excluded from loss detection — they show up everywhere in a
# document and have nothing to do with capability.
_REF_NOISE = frozenset({
    "requirements.txt", "readme.md", "license.txt", "setup.py",
    "package.json", "config.json", "settings.json",
})


def _norm(s: str) -> str:
    """Normalize for comparison: ignore case, whitespace, and emphasis markers."""
    return re.sub(r"[\s*`_]+", " ", s).strip().lower()


def _sections(text: str) -> list[str]:
    return [m.group(1) for m in _SECTION_RE.finditer(text)]


def _refs(text: str) -> list[str]:
    out = []
    for m in _REF_RE.finditer(text):
        tok = m.group(0).lstrip("./")
        if tok.lower() in _REF_NOISE:
            continue
        out.append(tok)
    return out


def _commands(text: str) -> list[str]:
    return [m.group(1).strip() for m in _CMD_RE.finditer(text)]


def _lost(old_items: list[str], new_items: list[str]) -> list[str]:
    """Items present only in old, not in new.

    Judged by normalized value, not by count. But to avoid misjudging a
    'renamed only' case as a loss, an empty list is returned when the total
    count is unchanged — sanitization is inherently a renaming operation, and
    flagging that too would get this tool turned off.
    """
    if len(new_items) >= len(old_items):
        new_norm = {_norm(i) for i in new_items}
        missing = [i for i in old_items if _norm(i) not in new_norm]
        # treat it as a rename if the count is unchanged.
        return [] if len(new_items) == len(old_items) else missing
    new_norm = {_norm(i) for i in new_items}
    return [i for i in old_items if _norm(i) not in new_norm]


@dataclass
class CapabilityReport:
    lost_sections: list[str] = field(default_factory=list)
    lost_refs: list[str] = field(default_factory=list)
    lost_commands: list[str] = field(default_factory=list)
    shrink_ratio: float = 0.0
    shrank: bool = False
    old_len: int = 0
    new_len: int = 0

    @property
    def ok(self) -> bool:
        return not (self.lost_sections or self.lost_refs
                    or self.lost_commands or self.shrank)

    def render(self, label: str = "") -> str:
        head = f"[{'OK  ' if self.ok else 'LOST'}] {label}".rstrip()
        lines = [f"{head}  ({self.old_len} → {self.new_len} chars, "
                 f"{self.shrink_ratio:+.0%})"]
        for title, items in (("missing sections", self.lost_sections),
                             ("missing references", self.lost_refs),
                             ("missing commands", self.lost_commands)):
            if items:
                shown = ", ".join(items[:5])
                more = f" (+{len(items) - 5})" if len(items) > 5 else ""
                lines.append(f"    {title}: {shown}{more}")
        if self.shrank:
            lines.append(f"    length shrank by {self.shrink_ratio:.0%} — suspected shrunken version")
        return "\n".join(lines)


def diff_capabilities(old: str, new: str,
                      shrink_limit: float = DEFAULT_SHRINK_LIMIT) -> CapabilityReport:
    """Find capabilities missing from the new version relative to the original."""
    old_len, new_len = len(old), len(new)
    ratio = (new_len - old_len) / old_len if old_len else 0.0
    return CapabilityReport(
        lost_sections=_lost(_sections(old), _sections(new)),
        lost_refs=_lost(_refs(old), _refs(new)),
        lost_commands=_lost(_commands(old), _commands(new)),
        shrink_ratio=ratio,
        shrank=ratio < -abs(shrink_limit),
        old_len=old_len,
        new_len=new_len,
    )


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def compare_trees(old_root: Path, new_root: Path,
                  shrink_limit: float = DEFAULT_SHRINK_LIMIT
                  ) -> dict[str, CapabilityReport]:
    """Compare two skill trees file by file (indexed on the original; newly added files are ignored)."""
    reports: dict[str, CapabilityReport] = {}
    for old_file in sorted(old_root.rglob("*")):
        if not old_file.is_file() or old_file.suffix.lower() not in {
                ".md", ".py", ".sh", ".json", ".txt"}:
            continue
        rel = old_file.relative_to(old_root)
        new_file = new_root / rel
        if not new_file.exists():
            rep = CapabilityReport(lost_sections=[f"<the file itself is missing: {rel}>"],
                                   old_len=old_file.stat().st_size, new_len=0,
                                   shrink_ratio=-1.0, shrank=True)
        else:
            rep = diff_capabilities(_read(old_file), _read(new_file), shrink_limit)
        reports[str(rel).replace("\\", "/")] = rep
    return reports


def main() -> int:
    ap = argparse.ArgumentParser(
        description="After a skill has been rewritten, check whether any capability was dropped")
    ap.add_argument("old", help="original file or folder")
    ap.add_argument("new", help="new version's file or folder")
    ap.add_argument("--shrink-limit", type=float, default=DEFAULT_SHRINK_LIMIT,
                    help=f"shrink-warning threshold (default {DEFAULT_SHRINK_LIMIT:.0%})")
    ap.add_argument("--quiet", action="store_true", help="print only losses")
    args = ap.parse_args()

    old, new = Path(args.old), Path(args.new)
    if not old.exists():
        print(f"[ERROR] original not found: {old}")
        return 2
    if not new.exists():
        print(f"[ERROR] new version not found: {new}")
        return 2

    if old.is_file():
        reports = {old.name: diff_capabilities(_read(old), _read(new),
                                               args.shrink_limit)}
    else:
        reports = compare_trees(old, new, args.shrink_limit)

    lost = {k: v for k, v in reports.items() if not v.ok}
    for name, rep in reports.items():
        if args.quiet and rep.ok:
            continue
        print(rep.render(name))

    print("-" * 60)
    if lost:
        print(f"suspected loss in {len(lost)} / {len(reports)} checked — "
              "go back to the original, not the rewrite, and restore what's missing.")
        return 1
    print(f"no capability loss ({len(reports)} checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
