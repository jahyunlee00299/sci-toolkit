#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Connectivity check — does anything lead to each shipped tool, and does anything test it?

Why this exists
---------------
The most common failure in this toolkit is a correct artifact that nothing
ever calls. Measured 2026-09-02: nine scripts (hplc_parser, jcr_batch_verify,
excel_formula_check, fetch_public_vector, primer_structure_check,
variant_filter, convert_literature, manuscript_packet, fetch_github) had no
mention in any doc the agent reads, no importer and no test, while doctor
reported 12 OK. The connectivity ledger existed but was read by nothing —
the ledger itself had the failure it was written to prevent.

The rule this enforces
----------------------
Every tool (a non-underscore ``.py`` under ``scripts/`` or ``skills/*/scripts/``)
is classified on two independent axes:

* **reachable** — something leads to it: a doc an agent or user reads
  (README, QUICKSTART, AGENTS.md, CODEX.md, docs/**, the owning skill's
  Markdown), OR another module that imports it, OR an invoker (doctor.py,
  install, a hook, a git hook).
* **exercised** — something verifies it: ``tests/**``, ``skills/*/tests/**``,
  ``doctor.py`` or ``evals/``.

Verdicts:

* ``ORPHAN``   — not reachable. Nothing points at the file. **Exit 1.**
* ``UNTESTED`` — reachable but not exercised. Reported, counted, and exit 0
  unless ``--max-untested N`` is exceeded (the regression test holds the
  ratchet so the number can only go down).
* ``OK``       — both.

Why not fail on UNTESTED outright: measured 2026-09-02, 40+ skill scripts
are downstream copies of skills authored elsewhere and carry no tests here.
Failing on all of them at once would make doctor red for months and train
users to ignore it. A ratchet catches *new* untested tools without lying
about the old ones.

Ledger lines
------------
``docs/feature-connectivity-ledger.md`` entries may carry machine-readable
wiring lines::

    wired-by: tests/test_x.py
    wired-by: doctor.py

Every such path must exist; a dangling one is an ORPHAN-class failure
(exit 1). This is the only part of the ledger checked mechanically.

Usage
-----
    python scripts/connectivity_check.py                   # table, exit 0/1
    python scripts/connectivity_check.py --json            # machine-readable
    python scripts/connectivity_check.py --max-untested 40 # ratchet
    python scripts/connectivity_check.py --root DIR        # another tree
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path

if sys.platform == "win32":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

# --------------------------------------------------------------------------
# What counts as a tool, a reader, an invoker, and a test
# --------------------------------------------------------------------------

#: Globs (relative to root) for tool candidates. Underscore-prefixed files
#: are private helpers of a sibling and are not tools in their own right.
TOOL_GLOBS = (
    "scripts/*.py",
    "scripts/connectors/*.py",
    "skills/*/scripts/*.py",
)

#: Files an agent or user reads to decide what to run.
READER_GLOBS = (
    "README.md",
    "QUICKSTART.md",
    "AGENTS.md",
    "CODEX.md",
    "CLAUDE.md",
    "PROJECT_STRUCTURE.md",
    "docs/**/*.md",
    "skills/*/*.md",
    "skills/*/references/*.md",
    "scripts/**/*.md",
)

#: Files that call or import tools at runtime (not tests).
INVOKER_GLOBS = (
    "doctor.py",
    "doctor_lib/*.py",
    "install/*.py",
    "scripts/**/*.py",
    "skills/*/scripts/**/*.py",
    "skills/*/src/**/*.py",
    "hooks/*.sh",
    "hooks/*.json",
    "scripts/git-hooks/*",
)

#: Files that verify tools.
TEST_GLOBS = (
    "doctor.py",
    "doctor_lib/*.py",
    "tests/**/*.py",
    "skills/*/tests/**/*.py",
    "evals/*.py",
)

LEDGER_REL = "docs/feature-connectivity-ledger.md"
_WIRED_BY = re.compile(r"^\s*(?:[-*]\s*)?wired-by:\s*`?([^`\s]+)`?\s*$", re.MULTILINE)

SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "node_modules", ".venv", "venv"}

VERDICT_OK = "OK"
VERDICT_UNTESTED = "UNTESTED"
VERDICT_ORPHAN = "ORPHAN"


@dataclass
class ToolStatus:
    path: str
    reachable_in: list[str] = field(default_factory=list)
    exercised_in: list[str] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        if not self.reachable_in:
            return VERDICT_ORPHAN
        if not self.exercised_in:
            return VERDICT_UNTESTED
        return VERDICT_OK

    def to_dict(self) -> dict:
        d = asdict(self)
        d["verdict"] = self.verdict
        return d


@dataclass
class Report:
    tools: list[ToolStatus]
    dangling_ledger_paths: list[str]
    ledger_wired_by_count: int
    max_untested: int | None = None

    @property
    def orphans(self) -> list[ToolStatus]:
        return [t for t in self.tools if t.verdict == VERDICT_ORPHAN]

    @property
    def untested(self) -> list[ToolStatus]:
        return [t for t in self.tools if t.verdict == VERDICT_UNTESTED]

    @property
    def ratchet_exceeded(self) -> bool:
        return self.max_untested is not None and len(self.untested) > self.max_untested

    @property
    def ok(self) -> bool:
        return (not self.orphans and not self.dangling_ledger_paths
                and not self.ratchet_exceeded)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "tool_count": len(self.tools),
            "orphan_count": len(self.orphans),
            "untested_count": len(self.untested),
            "max_untested": self.max_untested,
            "ratchet_exceeded": self.ratchet_exceeded,
            "orphans": [t.path for t in self.orphans],
            "untested": [t.path for t in self.untested],
            "tools": [t.to_dict() for t in self.tools],
            "ledger_wired_by_count": self.ledger_wired_by_count,
            "dangling_ledger_paths": self.dangling_ledger_paths,
        }


# --------------------------------------------------------------------------
# Scanning
# --------------------------------------------------------------------------

def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _in_skipped_dir(path: Path, root: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.relative_to(root).parts)


def _glob_many(root: Path, globs: tuple[str, ...]) -> list[Path]:
    seen: dict[Path, None] = {}
    for g in globs:
        for p in sorted(root.glob(g)):
            if p.is_file() and not _in_skipped_dir(p, root):
                seen.setdefault(p.resolve(), None)
    return list(seen)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def find_tools(root: Path) -> list[Path]:
    return [p for p in _glob_many(root, TOOL_GLOBS)
            if not p.name.startswith("_") and p.name != "__init__.py"]


def _mentions(text: str, tool: Path) -> bool:
    """A file mentions a tool if its basename appears, or if it imports it by stem.

    Basename matching (``hplc_parser.py``) is deliberately strict: the stem alone
    (``hplc_parser``) would match prose such as "the HPLC parser" in an unrelated
    sentence. Imports are the exception because they never carry the extension.
    """
    if tool.name in text:
        return True
    stem = re.escape(tool.stem)
    return re.search(
        rf"^\s*(?:from\s+(?:[\w.]+\.)?{stem}\s+import|import\s+(?:[\w.]+\.)?{stem}\b)",
        text, re.MULTILINE) is not None


def scan(root: Path, max_untested: int | None = None) -> Report:
    root = root.resolve()
    tools = find_tools(root)
    readers = {p: _read_text(p) for p in _glob_many(root, READER_GLOBS)}
    invokers = {p: _read_text(p) for p in _glob_many(root, INVOKER_GLOBS)}
    tests = {p: _read_text(p) for p in _glob_many(root, TEST_GLOBS)}

    statuses: list[ToolStatus] = []
    for tool in tools:
        st = ToolStatus(path=_rel(tool, root))
        me = tool.resolve()
        for p, text in readers.items():
            if _mentions(text, tool):
                st.reachable_in.append(_rel(p, root))
        for p, text in invokers.items():
            if p.resolve() != me and _mentions(text, tool):
                st.reachable_in.append(_rel(p, root))
        for p, text in tests.items():
            if p.resolve() != me and _mentions(text, tool):
                st.exercised_in.append(_rel(p, root))
        statuses.append(st)

    dangling: list[str] = []
    wired_count = 0
    ledger = root / LEDGER_REL
    if ledger.is_file():
        for m in _WIRED_BY.finditer(_read_text(ledger)):
            wired_count += 1
            if not (root / m.group(1)).exists():
                dangling.append(m.group(1))

    return Report(tools=statuses, dangling_ledger_paths=dangling,
                  ledger_wired_by_count=wired_count, max_untested=max_untested)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def print_human(report: Report, verbose: bool = False) -> None:
    print(f"connectivity check — {len(report.tools)} tool(s), "
          f"{report.ledger_wired_by_count} ledger wired-by line(s)")
    print("-" * 70)
    for t in report.tools:
        if t.verdict == VERDICT_OK and not verbose:
            continue
        print(f"[{t.verdict:8}] {t.path}")
        if t.verdict == VERDICT_ORPHAN:
            print("           nothing leads here: no doc names it, no module imports it, no hook runs it")
        elif t.verdict == VERDICT_UNTESTED:
            print(f"           reachable via {t.reachable_in[0]} but no test/doctor names it")
    for d in report.dangling_ledger_paths:
        print(f"[DANGLE  ] ledger wired-by path does not exist: {d}")
    print("-" * 70)
    n_ok = len(report.tools) - len(report.orphans) - len(report.untested)
    ratchet = (f" (max {report.max_untested})" if report.max_untested is not None else "")
    print(f"SUMMARY: {n_ok} ok, {len(report.untested)} untested{ratchet}, "
          f"{len(report.orphans)} orphan, {len(report.dangling_ledger_paths)} dangling ledger path(s)")
    if report.ratchet_exceeded:
        print(f"RATCHET: untested count {len(report.untested)} exceeds {report.max_untested} — "
              "a new tool shipped without a test")
    print("RESULT: " + ("PASS" if report.ok else "FAIL"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=None,
                        help="toolkit root (default: parent of this script's folder)")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of the table")
    parser.add_argument("--max-untested", type=int, default=None, metavar="N",
                        help="fail when more than N reachable tools have no test (ratchet)")
    parser.add_argument("-v", "--verbose", action="store_true", help="also list OK tools")
    args = parser.parse_args(argv)

    root = (args.root or Path(__file__).resolve().parent.parent).resolve()
    report = scan(root, max_untested=args.max_untested)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        print_human(report, verbose=args.verbose)
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
