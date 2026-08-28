"""pytest wiring — the checks in this folder are standalone scripts.

Each `test_*.py` is a script meant to run as `python tests/test_x.py`: it
performs its check at module level and reports the verdict via `sys.exit()`.
The real runner is `doctor.py`, which runs each script as a subprocess and
so fits this structure fine.

The problem is `pytest tests/`. It's the first command anyone runs right
after cloning, but pytest **imports** each file during collection, which
means the check runs right then and there, and the module-level `sys.exit()`
blows up as an INTERNALERROR (measured 2026-08-08). The tooling was fine —
it just looked like the repo was broken.

So this file changes how pytest collects: instead of importing the scripts,
it runs them **as a subprocess** — the same way doctor.py does. The upshot
is that `pytest tests/` and `python doctor.py` perform the same checks.

Why the runner isn't a separate `test_*.py` file of its own: the file count
under tests/ is the SSOT for the "N regression tests" number quoted in the
README (test_doc_counts.py), and there's a separate rule that every
test_*.py must be run by doctor. Adding one more wiring file would throw off
both checks at once, and it would put a file that isn't itself a check into
doctor's list. conftest is a pytest-only file, so it's excluded from either
count.
"""
from __future__ import annotations

import subprocess
import sys

import pytest


class SelfCheckItem(pytest.Item):
    """Run a single self-check script as a subprocess."""

    def __init__(self, *, name, parent, script):
        super().__init__(name, parent)
        self.script = script

    def runtest(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(self.script)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(self.script.parent.parent), timeout=600,
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
    if file_path.suffix == ".py" and file_path.name.startswith("test_"):
        return SelfCheckFile.from_parent(parent, path=file_path)
    return None
