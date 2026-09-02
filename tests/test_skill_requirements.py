#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""config/skill-requirements.toml must match what the scripts import; missing packages are reported.

Why this exists
---------------
docs/06 told beginners what to install in prose that nothing checked. Now
scripts/skill_requirements.py derives the declaration from the scripts and
doctor reports which declared packages do not import here (WARN). This test
keeps both halves honest:

  repo   — `--check` exits 0 (the committed TOML equals a fresh scan) and
           `--missing --json` parses.
  synth  — on a throwaway skill tree: a lazy import inside a function IS
           declared; an import inside `try: ... except ImportError` is NOT;
           stdlib and skill-local modules are never declared; the pip-name
           map is applied (fitz -> pymupdf); `--check` exits 1 when a script
           gains an import the TOML lacks; `--missing` names a package whose
           import cannot resolve and skips a Windows-only one off Windows.

Run: python tests/test_skill_requirements.py
"""
from __future__ import annotations

import json
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
SCRIPT = ROOT / "scripts" / "skill_requirements.py"

_results: list[tuple[bool, str]] = []


def check(name: str, cond: bool, note: str = "") -> None:
    _results.append((cond, name))
    tag = "[OK]  " if cond else "[FAIL]"
    print(f"  {tag} {name}" + (f"  {note}" if note and not cond else ""))


def run(*args: str) -> tuple[int, str]:
    p = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=120, cwd=str(ROOT))
    return p.returncode, (p.stdout or "") + (p.stderr or "")


# --------------------------------------------------------------------------
print("== repo")
rc, out = run("--check")
check("committed TOML matches a fresh scan (--check exit 0)", rc == 0, out[-400:])
rc, out = run("--missing", "--json")
try:
    data = json.loads(out)
    check("--missing --json parses and carries 'missing'", isinstance(data.get("missing"), dict))
    if data.get("missing"):
        print("  [INFO] packages not installed here: " + "; ".join(f"{k}: {v}" for k, v in data["missing"].items()))
except json.JSONDecodeError:
    check("--missing --json parses", False, out[-300:])

# --------------------------------------------------------------------------
print("\n== synth")


def tree(tmp: Path, scripts: dict[str, dict[str, str]]) -> Path:
    root = tmp / "root"
    for skill, files in scripts.items():
        for rel, body in files.items():
            p = root / "skills" / skill / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body, encoding="utf-8")
    (root / "config").mkdir(parents=True, exist_ok=True)
    return root


with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    root = tree(tmp, {
        "alpha": {"scripts/a.py": (
            "import json\n"                       # stdlib: never declared
            "import fitz\n"                       # -> pymupdf (map)
            "from helper import x\n"              # skill-local: never declared
            "def f():\n    import openpyxl\n"     # lazy but required: declared
            "try:\n    import cairosvg\nexcept ImportError:\n    cairosvg = None\n"  # optional: NOT declared
        ), "scripts/helper.py": "x = 1\n"},
        "beta": {"scripts/b.py": "import numpy\n"},
        "gamma": {"SKILL.md": "no scripts here\n"},
    })
    rc, out = run("scan", "--root", str(root))
    toml = (root / "config" / "skill-requirements.toml").read_text(encoding="utf-8")
    check("scan writes the TOML", rc == 0 and "[alpha]" in toml, out[-200:])
    check("fitz declared as pymupdf", '"pymupdf"' in toml, toml)
    check("lazy in-function import (openpyxl) declared", '"openpyxl"' in toml, toml)
    check("optional try/except ImportError import (cairosvg) NOT declared", "cairosvg" not in toml, toml)
    check("stdlib json and skill-local helper NOT declared", '"json"' not in toml and "helper" not in toml, toml)
    check("skill without scripts has no entry", "[gamma]" not in toml, toml)
    rc, out = run("--check", "--root", str(root))
    check("--check right after scan -> exit 0", rc == 0, out[-200:])

    (root / "skills" / "beta" / "scripts" / "b.py").write_text("import numpy\nimport pandas\n", encoding="utf-8")
    rc, out = run("--check", "--root", str(root))
    check("script gained an import the TOML lacks -> --check exit 1 and names it",
          rc == 1 and "beta" in out and "pandas" in out, out[-300:])

    (root / "config" / "skill-requirements.toml").write_text(
        '[alpha]\npackages = ["definitely_not_installed_pkg_xyz", "json"]\n'
        '[beta]\npackages = ["pywin32"]\n', encoding="utf-8")
    rc, out = run("--missing", "--json", "--root", str(root))
    data = json.loads(out)
    check("--missing names the unresolvable package", data["missing"].get("alpha") == ["definitely_not_installed_pkg_xyz"], out[-300:])
    if sys.platform != "win32":
        check("Windows-only pywin32 skipped off Windows", "beta" not in data["missing"], str(data))
    else:
        print("  [SKIP] Windows-only skip rule (running on Windows)")

    (root / "config" / "skill-requirements.toml").unlink()
    rc, out = run("--check", "--root", str(root))
    check("missing TOML -> --check exit 1 with the scan command", rc == 1 and "scan" in out, out[-200:])

# --------------------------------------------------------------------------
n_fail = sum(1 for ok, _ in _results if not ok)
print(f"\nSUMMARY: {len(_results) - n_fail} passed, {n_fail} failed")
sys.exit(1 if n_fail else 0)
