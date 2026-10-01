"""Prove + Refute for excel_com_guard.recalc_and_scan's timeout plumbing.

win32com/Excel do not exist on this Linux/WSL session, so these tests replace
the worker subprocess with plain Python scripts that simulate the two
behaviours that actually matter: (1) a hang that must be killed after
timeout_sec, exactly like a modal-dialog-blocked EXCEL.EXE, and (2) a process
that finishes normally, which the timeout wrapper must NOT interfere with.
The actual win32com call sequence (_com_worker_main) cannot be exercised here
-- it requires a live Windows Excel install -- and is deferred to a laptop
verification pass; see the ledger entry for this unit.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import excel_com_guard


_REAL_POPEN = subprocess.Popen


def _run_with_fake_cmd(monkeypatch, fake_cmd: list[str], timeout_sec: int) -> dict:
    """Call recalc_and_scan but substitute the child command it spawns."""
    def fake_popen(cmd, **kwargs):
        # subprocess.run() inside _kill_process_tree goes through Popen too; substituting
        # that call turned `taskkill` into the hang script and cost its own 15 s timeout.
        if cmd and str(cmd[0]).lower().startswith("taskkill"):
            return _REAL_POPEN(cmd, **kwargs)
        return _REAL_POPEN(fake_cmd, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    return excel_com_guard.recalc_and_scan("dummy.xlsx", timeout_sec=timeout_sec)


def test_hang_is_killed_after_timeout(monkeypatch, tmp_path):
    """A child process that never exits (the modal-dialog hang analog) must
    be force-killed and reported as status=timeout within a bounded time,
    not left running or blocking the caller forever."""
    hang_script = tmp_path / "hang.py"
    hang_script.write_text("import time\ntime.sleep(600)\n")

    started = time.monotonic()
    result = _run_with_fake_cmd(monkeypatch, [sys.executable, str(hang_script)], timeout_sec=2)
    elapsed = time.monotonic() - started

    assert result["status"] == "timeout"
    assert elapsed < 10, f"timeout wrapper took {elapsed:.1f}s to return for a 2s timeout"


def test_healthy_process_is_not_disturbed(monkeypatch, tmp_path):
    """A process that finishes well within the timeout must return its real
    result untouched -- the watchdog must be a no-op on the success path,
    which is the refutation the user explicitly asked for: prove the timeout
    wrapper does not interfere with normal completion."""
    ok_script = tmp_path / "ok.py"
    ok_script.write_text(
        'import json\nprint(json.dumps({"status": "success", "total_errors": 0, "error_summary": {}}))\n'
    )

    result = _run_with_fake_cmd(monkeypatch, [sys.executable, str(ok_script)], timeout_sec=30)

    assert result["status"] == "success"
    assert result["total_errors"] == 0
    assert "elapsed_sec" in result


def test_worker_env_error_is_reported_not_raised(monkeypatch, tmp_path):
    """Exit code 3 (the _ensure_env / pywin32-missing convention shared with
    word_com_ops.py) must surface as status=env_error, not propagate as an
    unhandled exception from a platform that plain lacks pywin32/Excel."""
    env_fail_script = tmp_path / "envfail.py"
    env_fail_script.write_text("import sys\nprint('pywin32 not installed', file=sys.stderr)\nsys.exit(3)\n")

    result = _run_with_fake_cmd(monkeypatch, [sys.executable, str(env_fail_script)], timeout_sec=10)

    assert result["status"] == "env_error"


def test_malformed_worker_output_is_reported_not_raised(monkeypatch, tmp_path):
    bad_script = tmp_path / "bad.py"
    bad_script.write_text("print('not json')\n")

    result = _run_with_fake_cmd(monkeypatch, [sys.executable, str(bad_script)], timeout_sec=10)

    assert result["status"] == "bad_output"


def test_errors_found_status_passes_through(monkeypatch, tmp_path):
    err_script = tmp_path / "err.py"
    err_script.write_text(
        'import json\nprint(json.dumps({"status": "errors_found", "total_errors": 2, '
        '"error_summary": {"#REF!": {"count": 2, "locations": ["Sheet1!A1", "Sheet1!B2"]}}}))\n'
    )

    result = _run_with_fake_cmd(monkeypatch, [sys.executable, str(err_script)], timeout_sec=10)

    assert result["status"] == "errors_found"
    assert result["total_errors"] == 2


if __name__ == "__main__":
    print("This test file uses pytest fixtures (monkeypatch, tmp_path) -- run via:")
    print("  python -m pytest tests/test_excel_com_guard.py -v")
    sys.exit(1)
