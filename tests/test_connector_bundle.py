"""Connectors must keep working after they are copied out of the repo.

scripts/connectors/*.py import `_stdio` and `sci_http` from the PARENT folder.
A copy of scripts/connectors/ alone therefore breaks at import time. The helper
list is declared once in config/catalog.json (connectors._shared_files); the
installer (`install.py --connectors-dest`) ships it, and this test proves it:

1. install the bundle into a temp folder with the real installer code and
   import every connector from there in a fresh interpreter, with the repo
   NOT on sys.path (so a silent fallback to the repo copy is impossible);
2. negative controls: leave a helper out and the importers that need it must
   fail, so the check cannot pass vacuously.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONN = ROOT / "scripts" / "connectors"
sys.path.insert(0, str(ROOT / "install"))
import install as installer  # noqa: E402

MODULES = sorted(
    p.stem for p in CONN.glob("*.py")
    if p.stem != "__init__"
)
# connectors that import sci_http, directly or through _google_auth
NEEDS_SCI_HTTP = {"asana_connector", "github_connector", "notion_connector",
                  "notion_db_connector", "_google_auth", "calendar_connector",
                  "sheets_connector"}

PROBE = (
    "import importlib, sys\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "m = importlib.import_module(sys.argv[2])\n"
    "print(m.__file__)\n"
)


def _import(scripts_dir: Path, module: str) -> subprocess.CompletedProcess:
    # -I: ignore PYTHONPATH/cwd/user site, so only the temp copy can satisfy imports
    return subprocess.run(
        [sys.executable, "-I", "-c", PROBE, str(scripts_dir / "connectors"), module],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(scripts_dir.parent), timeout=120)


def test_catalog_declares_shared_helpers():
    cat = json.loads((ROOT / "config" / "catalog.json").read_text(encoding="utf-8"))
    bundle = installer.connector_bundle(cat)
    assert bundle[0] == "scripts/connectors"
    assert {"scripts/sci_http.py", "scripts/_stdio.py"} <= set(bundle)


def test_every_parent_import_is_declared():
    """A new `import <helper>` of a parent-folder module must be added to the catalog."""
    import re
    shipped = {Path(p).stem for p in installer.connector_bundle(installer.load_catalog())}
    parent_mods = {p.stem for p in (ROOT / "scripts").glob("*.py")}
    used = set()
    for f in CONN.glob("*.py"):
        for m in re.finditer(r"^(?:import|from)\s+(\w+)", f.read_text(encoding="utf-8"), re.M):
            if m.group(1) in parent_mods:
                used.add(m.group(1))
    assert used <= shipped, f"connectors import unshipped parent helpers: {used - shipped}"


@pytest.fixture()
def installed(tmp_path):
    installer.install_connectors(tmp_path, apply=True)
    return tmp_path / "scripts"


@pytest.mark.parametrize("module", MODULES)
def test_connector_imports_from_installed_copy(installed, module):
    r = _import(installed, module)
    assert r.returncode == 0, r.stderr[-800:]
    assert Path(r.stdout.strip()).is_relative_to(installed)


@pytest.mark.parametrize("missing,expect_fail", [
    ("sci_http.py", NEEDS_SCI_HTTP),
    ("_stdio.py", set(MODULES)),
])
def test_omitting_a_helper_breaks_importers(installed, missing, expect_fail):
    (installed / missing).unlink()
    for module in MODULES:
        failed = _import(installed, module).returncode != 0
        assert failed == (module in expect_fail), f"{module}: failed={failed} without {missing}"


def test_plain_copy_of_connectors_alone_is_broken(tmp_path):
    """The documented pitfall: copying scripts/connectors/ without the helpers."""
    shutil.copytree(CONN, tmp_path / "scripts" / "connectors")
    assert _import(tmp_path / "scripts", "github_connector").returncode != 0
