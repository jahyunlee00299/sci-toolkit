#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""skill_requirements — which third-party packages each skill's scripts actually import.

Why this exists
---------------
docs/06_기능별_준비물.md tells a beginner, in prose, what to install for each
feature. Nothing checks that prose against the scripts, and doctor could only
say "python is new enough", never "the skill you just installed needs
pymupdf and you don't have it". Upstream (K-Dense-AI/scientific-agent-skills)
keeps this in ``tests/skill-requirements.toml`` and builds one environment per
skill from it; this repo keeps the declaration and the check, not the
environments.

What it does
------------
``scan``     walk skills/*/scripts/*.py, collect every third-party import the
             script needs (module level or inside a function) EXCEPT those in
             a try: block that catches ImportError — the author marked those
             optional — map import names to pip names, and write
             config/skill-requirements.toml.
``--check``  exit 1 when the committed TOML no longer matches a fresh scan —
             a script gained or lost a dependency and the declaration lags.
``--missing`` JSON: per skill, the declared packages whose import does not
             resolve in THIS interpreter. doctor reports it as WARN (a missing
             optional package is not a broken toolkit).

Import-name -> pip-name mapping lives in IMPORT_TO_PIP; unknown names fall
through unchanged, which is right far more often than not.
"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import sys
import tomllib
from pathlib import Path

if sys.platform == "win32":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

ROOT = Path(__file__).resolve().parent.parent
TOML_PATH = ROOT / "config" / "skill-requirements.toml"

IMPORT_TO_PIP = {
    "PIL": "pillow", "fitz": "pymupdf", "docx": "python-docx", "bs4": "beautifulsoup4",
    "skimage": "scikit-image", "yaml": "pyyaml", "cv2": "opencv-python", "sklearn": "scikit-learn",
    "win32com": "pywin32", "pythoncom": "pywin32", "pywintypes": "pywin32", "PyPDF2": "PyPDF2",
    "pypdf": "pypdf", "habanero": "habanero", "selectolax": "selectolax", "trafilatura": "trafilatura",
    "webdriver_manager": "webdriver-manager", "Bio": "biopython", "dateutil": "python-dateutil",
    "markitdown": "markitdown", "openpyxl": "openpyxl", "pdfplumber": "pdfplumber",
}
#: Windows-only packages: their absence on Linux/macOS is expected, not missing.
WINDOWS_ONLY = {"pywin32"}


def _stdlib() -> set[str]:
    return set(getattr(sys, "stdlib_module_names", ()))


def _local_modules(skill_dir: Path) -> set[str]:
    return {p.stem for p in skill_dir.rglob("*.py")} | {p.name for p in skill_dir.rglob("*") if p.is_dir()}


_OPTIONAL_HANDLERS = {"ImportError", "ModuleNotFoundError", "Exception", "BaseException"}


def _names(node: ast.AST) -> set[str]:
    if isinstance(node, ast.Import):
        return {a.name.split(".")[0] for a in node.names}
    if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
        return {node.module.split(".")[0]}
    return set()


def _required_imports(py: Path) -> set[str]:
    """Imports the script needs to do its job.

    Every import counts — module level or inside a function (a lazy import is
    still a hard need for that code path; measured 2026-09-03: paper-extract
    imports pymupdf/pdfplumber/openpyxl only inside functions and would have
    been declared dependency-free) — EXCEPT an import inside a ``try:`` whose
    handler catches ImportError/ModuleNotFoundError/Exception: that is the
    author saying "optional", so it is not declared.
    """
    try:
        tree = ast.parse(py.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return set()
    optional: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            caught = set()
            for h in node.handlers:
                t = h.type
                if t is None:
                    caught.add("BaseException")
                elif isinstance(t, ast.Name):
                    caught.add(t.id)
                elif isinstance(t, ast.Tuple):
                    caught |= {e.id for e in t.elts if isinstance(e, ast.Name)}
            if caught & _OPTIONAL_HANDLERS:
                for inner in node.body:
                    for sub in ast.walk(inner):
                        optional |= _names(sub)
    names: set[str] = set()
    for node in ast.walk(tree):
        names |= _names(node)
    return names - optional


def scan(root: Path) -> dict[str, dict]:
    """{skill: {"packages": [pip names], "imports": {pip: [import names]}}} for skills with scripts."""
    std = _stdlib()
    out: dict[str, dict] = {}
    for skill_dir in sorted(p for p in (root / "skills").iterdir() if p.is_dir()):
        scripts = sorted(skill_dir.glob("scripts/*.py"))
        if not scripts:
            continue
        local = _local_modules(skill_dir)
        pip_to_imports: dict[str, set[str]] = {}
        for py in scripts:
            for mod in _required_imports(py):
                if mod in std or mod in local or mod.startswith("_"):
                    continue
                pip_to_imports.setdefault(IMPORT_TO_PIP.get(mod, mod), set()).add(mod)
        out[skill_dir.name] = {
            "packages": sorted(pip_to_imports),
            "imports": {k: sorted(v) for k, v in sorted(pip_to_imports.items())},
        }
    return out


def render_toml(data: dict[str, dict]) -> str:
    lines = [
        "# Third-party packages each skill's scripts import at module level.",
        "# GENERATED by scripts/skill_requirements.py scan — do not edit by hand;",
        "# tests/test_skill_requirements.py fails when this file lags the scripts.",
        "# Skills without scripts/ have no entry. Windows-only packages: pywin32.",
        "",
    ]
    for skill, info in data.items():
        lines.append(f"[{skill}]")
        lines.append("packages = [" + ", ".join(f'"{p}"' for p in info["packages"]) + "]")
        for pip, mods in info["imports"].items():
            if mods != [pip]:
                lines.append(f'# {pip}: import {", ".join(mods)}')
        lines.append("")
    return "\n".join(lines)


def load_toml(path: Path) -> dict[str, list[str]]:
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    return {k: list(v.get("packages", [])) for k, v in data.items() if isinstance(v, dict)}


def _pip_importable(pip: str, imports_by_pip: dict[str, list[str]]) -> bool:
    for mod in imports_by_pip.get(pip, [pip]):
        try:
            if importlib.util.find_spec(mod) is None:
                return False
        except (ImportError, ValueError):
            return False
    return True


def missing(root: Path) -> dict[str, list[str]]:
    """Per skill: declared packages that do not import here (Windows-only ones skipped off Windows)."""
    declared = load_toml(root / "config" / "skill-requirements.toml")
    fresh = scan(root)
    out: dict[str, list[str]] = {}
    for skill, pkgs in declared.items():
        imports = fresh.get(skill, {}).get("imports", {})
        miss = [p for p in pkgs
                if not (p in WINDOWS_ONLY and sys.platform != "win32")
                and not _pip_importable(p, imports)]
        if miss:
            out[skill] = miss
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", nargs="?", default="scan", choices=["scan"],
                    help="scan (default): (re)write config/skill-requirements.toml")
    ap.add_argument("--check", action="store_true", help="exit 1 if the TOML lags a fresh scan (no write)")
    ap.add_argument("--missing", action="store_true", help="report declared packages that do not import here")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--root", type=Path, default=ROOT)
    args = ap.parse_args(argv)
    root = args.root.resolve()

    if args.missing:
        m = missing(root)
        if args.json:
            print(json.dumps({"missing": m, "platform": sys.platform}, ensure_ascii=False, indent=1))
        else:
            if not m:
                print("every declared package imports here")
            for skill, pkgs in m.items():
                print(f"{skill}: missing {', '.join(pkgs)}   ->  pip install {' '.join(pkgs)}")
        return 0

    fresh = scan(root)
    if args.check:
        path = root / "config" / "skill-requirements.toml"
        if not path.is_file():
            print(f"missing {path.relative_to(root)} — run: python scripts/skill_requirements.py scan")
            return 1
        declared = load_toml(path)
        want = {k: v["packages"] for k, v in fresh.items()}
        if declared != want:
            for k in sorted(set(declared) | set(want)):
                if declared.get(k) != want.get(k):
                    print(f"{k}: declared {declared.get(k)} != scripts import {want.get(k)}")
            print("STALE — run: python scripts/skill_requirements.py scan")
            return 1
        print(f"config/skill-requirements.toml matches the scripts ({len(want)} skills)")
        return 0

    text = render_toml(fresh)
    (root / "config" / "skill-requirements.toml").write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote config/skill-requirements.toml — {len(fresh)} skill(s) with scripts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
