#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression tests for scripts/connectivity_check.py.

Two groups:

  repo  — the live toolkit has 0 ORPHAN tools, 0 dangling ledger paths, and
          no more UNTESTED tools than the ratchet below. The ratchet is the
          measured count on the day it was last lowered; a new tool shipped
          without a test pushes it over and fails here. When you add a test
          for an existing tool, lower the number.

  synth — a throwaway tree exercises each verdict and each adverse shape:
          nothing points at the file (ORPHAN), doc-only (UNTESTED), import +
          test (OK), underscore helper ignored, prose that says "hplc parser"
          without the ``.py`` must NOT count, dangling ``wired-by:`` path,
          ``--max-untested`` ratchet, ``--json`` shape.

Run: python tests/test_connectivity.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

if sys.platform == "win32":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "connectivity_check.py"

# Ratchet: 51 reachable-but-untested tools measured 2026-09-03 (52 on 09-02), after the
# smoke tests for the routed scripts/ tools landed. Only ever lower this number.
MAX_UNTESTED = 51

_results: list[tuple[bool, str]] = []


def check(name: str, cond: bool, note: str = "") -> None:
    _results.append((cond, name))
    tag = "[OK]  " if cond else "[FAIL]"
    print(f"  {tag} {name}" + (f"  {note}" if note and not cond else ""))


def section(title: str) -> None:
    print(f"\n== {title}")


def run(*args: str, cwd: Path | None = None) -> tuple[int, str, dict | None]:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(cwd or ROOT), timeout=120)
    out = (proc.stdout or "") + (proc.stderr or "")
    data = None
    if "--json" in args:
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            data = None
    return proc.returncode, out, data


# --------------------------------------------------------------------------
section("repo: the live toolkit")

rc, out, data = run("--json", "--max-untested", str(MAX_UNTESTED))
check("checker runs and emits JSON", data is not None, out[-400:])
if data:
    check("0 ORPHAN tools (nothing points at them)", data["orphan_count"] == 0,
          f"orphans={data['orphans']}")
    check("0 dangling ledger wired-by paths", not data["dangling_ledger_paths"],
          f"dangling={data['dangling_ledger_paths']}")
    check(f"UNTESTED count {data['untested_count']} <= ratchet {MAX_UNTESTED}",
          data["untested_count"] <= MAX_UNTESTED,
          "a tool shipped without a test — add one, or (never preferred) raise the ratchet")
    check("ledger carries at least one wired-by line", data["ledger_wired_by_count"] >= 1)
    check("exit code agrees with ok flag", (rc == 0) == data["ok"], f"rc={rc} ok={data['ok']}")
    print(f"     tools={data['tool_count']} untested={data['untested_count']} "
          f"orphan={data['orphan_count']} wired-by={data['ledger_wired_by_count']}")


# --------------------------------------------------------------------------
section("synth: verdicts and adverse shapes")


def make_tree(tmp: Path, *, readme: str = "", tests: dict[str, str] | None = None,
              scripts: dict[str, str] | None = None, ledger: str | None = None) -> Path:
    # Start from an empty tree every time — a file left over from the previous
    # case silently changes the verdict of the next one (measured: it did).
    for child in tmp.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    (tmp / "scripts").mkdir(parents=True, exist_ok=True)
    (tmp / "tests").mkdir(exist_ok=True)
    (tmp / "docs").mkdir(exist_ok=True)
    (tmp / "README.md").write_text(readme, encoding="utf-8")
    for name, body in (scripts or {}).items():
        (tmp / "scripts" / name).write_text(body, encoding="utf-8")
    for name, body in (tests or {}).items():
        (tmp / "tests" / name).write_text(body, encoding="utf-8")
    if ledger is not None:
        (tmp / "docs" / "feature-connectivity-ledger.md").write_text(ledger, encoding="utf-8")
    return tmp


with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)

    # ORPHAN: nothing points at the file
    make_tree(tmp, scripts={"lonely.py": "print('hi')\n"})
    rc, out, data = run("--root", str(tmp), "--json")
    check("nothing points at it -> ORPHAN, exit 1",
          rc == 1 and data and data["orphans"] == ["scripts/lonely.py"], out[-300:])

    # UNTESTED: README names it, no test
    make_tree(tmp, readme="run `scripts/lonely.py` to say hi\n",
              scripts={"lonely.py": "print('hi')\n"})
    rc, out, data = run("--root", str(tmp), "--json")
    check("doc-only -> UNTESTED, exit 0",
          rc == 0 and data and data["untested"] == ["scripts/lonely.py"], out[-300:])
    rc, out, data = run("--root", str(tmp), "--json", "--max-untested", "0")
    check("--max-untested 0 turns UNTESTED into exit 1 (ratchet)",
          rc == 1 and data and data["ratchet_exceeded"], out[-300:])

    # OK: imported by a sibling AND named in a test
    make_tree(tmp, scripts={"lonely.py": "print('hi')\n",
                            "caller.py": "import lonely\n"},
              tests={"test_lonely.py": "# runs scripts/lonely.py\n"})
    rc, out, data = run("--root", str(tmp), "--json")
    verdicts = {t["path"]: t["verdict"] for t in data["tools"]} if data else {}
    check("import + test -> OK", verdicts.get("scripts/lonely.py") == "OK", str(verdicts))
    check("the importer itself has nothing leading to it -> ORPHAN (imports do not flow upward)",
          verdicts.get("scripts/caller.py") == "ORPHAN", str(verdicts))

    # underscore helper is not a tool
    make_tree(tmp, scripts={"_helper.py": "X = 1\n", "tool.py": "from _helper import X\n"},
              readme="`scripts/tool.py`\n", tests={"test_tool.py": "# tool.py\n"})
    rc, out, data = run("--root", str(tmp), "--json")
    paths = [t["path"] for t in data["tools"]] if data else []
    check("_helper.py is skipped as a tool", "scripts/_helper.py" not in paths, str(paths))
    check("tool.py that imports the helper is OK", rc == 0, out[-300:])

    # prose stem without .py must not count as reachable
    make_tree(tmp, readme="the hplc parser is great\n", scripts={"hplc_parser.py": "pass\n"})
    rc, out, data = run("--root", str(tmp), "--json")
    check("'hplc parser' prose (no .py) does NOT make hplc_parser.py reachable",
          data and data["orphans"] == ["scripts/hplc_parser.py"], out[-300:])

    # ledger wired-by: dangling vs existing
    make_tree(tmp, readme="`scripts/t.py`\n", scripts={"t.py": "pass\n"},
              tests={"test_t.py": "# t.py\n"},
              ledger="## unit\n\nwired-by: tests/test_t.py\nwired-by: `tests/does_not_exist.py`\n")
    rc, out, data = run("--root", str(tmp), "--json")
    check("dangling wired-by path -> exit 1 and named",
          rc == 1 and data and data["dangling_ledger_paths"] == ["tests/does_not_exist.py"], out[-300:])
    check("existing wired-by path counted", data and data["ledger_wired_by_count"] == 2)

    # empty tree: no tools at all is a PASS, not a crash
    make_tree(tmp)
    for p in (tmp / "scripts").glob("*.py"):
        p.unlink()
    rc, out, data = run("--root", str(tmp), "--json")
    check("empty tree -> PASS, 0 tools", rc == 0 and data and data["tool_count"] == 0, out[-300:])

    # human table mentions RESULT line (doctor greps it)
    make_tree(tmp, scripts={"lonely.py": "pass\n"})
    rc, out, _ = run("--root", str(tmp))
    check("human output ends with RESULT: FAIL for an orphan", "RESULT: FAIL" in out, out[-200:])


# --------------------------------------------------------------------------
n_fail = sum(1 for ok, _ in _results if not ok)
print(f"\nSUMMARY: {len(_results) - n_fail} passed, {n_fail} failed")
sys.exit(1 if n_fail else 0)
