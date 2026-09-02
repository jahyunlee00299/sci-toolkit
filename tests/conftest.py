"""pytest wiring — two kinds of file live in this folder, and each gets its own collector.

1. **Script-style checks** (the majority, historical). A `test_*.py` runs its
   checks at module level and reports the verdict with `sys.exit()`. pytest's
   default collector *imports* such a file, the check runs during collection,
   and the `sys.exit()` surfaces as INTERNALERROR (measured 2026-08-08). So
   these are run **as a subprocess** — the same way `doctor.py` runs them.

2. **pytest-style tests** (the conversion target since 2026-09-02). A file
   that defines `def test_...` functions is handed to pytest's normal Module
   collector, so `-k`, markers and per-test reporting work. `doctor.py`
   applies the same sniff (`doctor_lib/selftests.py::_selftest_command`):
   a pytest-style file listed in SELF_TEST_SCRIPTS is run under
   `python -m pytest <file>`, never as a bare script — a bare `python
   test_x.py` on a pytest-style file defines the functions and exits 0
   without running anything, which is a silent no-op, the exact failure
   this repo exists to prevent.

`pytest.ini` keeps the default `python_files` pattern pointed at a name that
never matches, so the default collector stays out of the way and this hook
is the only thing that decides. Delete that line and script-style files get
imported again and blow up immediately.

Why the runner isn't a separate `test_*.py` file of its own: the file count
under tests/ is the SSOT for the "N regression tests" number quoted in the
README (test_doc_counts.py), and there's a separate rule that every
test_*.py must be run by doctor. conftest is a pytest-only file, so it's
excluded from either count.

Offline runs: set `SCI_TOOLKIT_OFFLINE=1` (or run `doctor.py --offline`) and
every network probe in the script-style checks reports SKIP with that reason
instead of touching the network; pytest-style tests marked `network` are
deselected the same way.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

import pytest

_PYTEST_STYLE = re.compile(r"^\s*(?:async\s+)?def\s+test_\w+\s*\(", re.MULTILINE)


def is_pytest_style(path) -> bool:
    try:
        return _PYTEST_STYLE.search(path.read_text(encoding="utf-8", errors="replace")) is not None
    except OSError:
        return False


class SelfCheckItem(pytest.Item):
    """Run a single script-style self-check as a subprocess."""

    def __init__(self, *, name, parent, script):
        super().__init__(name, parent)
        self.script = script

    def runtest(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(self.script)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(self.script.parent.parent), timeout=600, env=dict(os.environ),
        )
        if proc.returncode != 0:
            detail = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
            raise AssertionError(
                f"{self.script.name} exited {proc.returncode}\n{detail[-3000:]}")

    def repr_failure(self, excinfo, style=None):
        # The script has already printed its failure in human-readable form.
        # Layering pytest's own Python traceback on top just buries the part
        # that actually needs reading.
        if isinstance(excinfo.value, AssertionError):
            return str(excinfo.value)
        return super().repr_failure(excinfo, style)

    def reportinfo(self):
        return self.script, 0, f"self-check: {self.script.name}"


class SelfCheckFile(pytest.File):
    def collect(self):
        yield SelfCheckItem.from_parent(
            self, name=self.path.name, script=self.path)


def pytest_collect_file(parent, file_path):
    if file_path.suffix != ".py" or not file_path.name.startswith("test_"):
        return None
    if is_pytest_style(file_path):
        # A file named explicitly on the command line is collected by pytest's
        # built-in python plugin regardless of `python_files` (it bypasses the
        # pattern for init paths). Returning a Module here as well collected
        # every test twice, and a parametrized case whose fixture list is
        # consumed in place failed on the second pass (measured 2026-09-03:
        # "IndexError: pop from empty list"). So hand explicit files to the
        # built-in and collect pytest-style files ourselves only during a
        # directory walk, where the never-matching pattern keeps the built-in out.
        if parent.session.isinitpath(file_path):
            return None
        return pytest.Module.from_parent(parent, path=file_path)
    return SelfCheckFile.from_parent(parent, path=file_path)


def pytest_collection_modifyitems(config, items):
    if os.environ.get("SCI_TOOLKIT_OFFLINE") == "1":
        skip = pytest.mark.skip(reason="network tests disabled by SCI_TOOLKIT_OFFLINE=1")
        for item in items:
            if "network" in item.keywords:
                item.add_marker(skip)
