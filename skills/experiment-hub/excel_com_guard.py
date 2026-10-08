"""Windows-only Excel COM safety wrapper for pipetting-workbook final checks.

WHY THIS EXISTS: an in-process win32com call that hits a modal dialog (e.g. a
"file already open" or "keep current format?" prompt Excel raises despite
DisplayAlerts=False, or a leftover dialog from a prior crashed instance) blocks
forever — there is no COM-level timeout, because the call is synchronous and
the dialog is waiting on user input that will never come from an unattended
script. Measured once: EXCEL.EXE sat Not-Responding for 44+ minutes
until it was taskkill'd by hand, and the forced kill rolled the workbook back
to its last saved state (unsaved edits since then were lost).

The fix is NOT a smarter in-process retry (word_com_ops.py's _open_word()
retry loop handles transient COM startup races, a different failure mode — a
hang after the app is already up is not something the hung process can detect
about itself). The fix is an EXTERNAL watchdog: run the actual COM work in a
child process, wait on it with subprocess timeout, and if it doesn't return in
time, kill the process tree by PID (Windows offers no SIGALRM/signal-based
timeout for a hung STA COM call) rather than requiring a human to eyeball
`tasklist` and taskkill it manually.

This module only runs on Windows (win32com.client is imported lazily inside
the worker function, never at module import time) so pure-logic pieces
(timeout plumbing, exit-code contract) can be unit-tested with a mocked
subprocess on any platform, including Linux/WSL where win32com
is not installed and Excel does not exist.

ENTRY POINTS:
    recalc_and_scan(xlsx_path, timeout_sec=300) -> dict
        Spawn a child process running _com_worker_main as __main__, which
        opens the workbook via Excel COM, forces a full recalculation
        (Application.CalculateFullRebuild), saves, closes, quits, and scans
        every cell for Excel error strings. Returns a JSON-shaped dict; on
        timeout, kills the child (and best-effort any EXCEL.EXE it spawned)
        and returns {"status": "timeout", ...} instead of hanging the caller.

Run directly for a quick CLI check:
    python excel_com_guard.py <path.xlsx> [timeout_sec]
"""
from __future__ import annotations

import json
import platform
import subprocess
import sys
import time
from pathlib import Path

EXCEL_ERROR_STRINGS = ("#VALUE!", "#DIV/0!", "#REF!", "#NAME?", "#NULL!", "#NUM!", "#N/A")
# Over COM an error cell's .Value is an int CVErr code, not the "#N/A" text, so a
# string-only check never fired (found 261002). Map both forms to the display text.
EXCEL_CVERR_CODES = {-2146826281: "#DIV/0!", -2146826246: "#N/A", -2146826259: "#NAME?",
                     -2146826288: "#NULL!", -2146826252: "#NUM!", -2146826265: "#REF!",
                     -2146826273: "#VALUE!"}


def _error_text(v):
    """Return the Excel error text for a COM cell value, or None."""
    if isinstance(v, int) and not isinstance(v, bool):
        if v >= 2**31:  # the same HRESULT delivered unsigned by another binding
            v -= 2**32
        if v in EXCEL_CVERR_CODES:
            return EXCEL_CVERR_CODES[v]
    if isinstance(v, str):
        for err in EXCEL_ERROR_STRINGS:
            if err in v:
                return err
    return None


def _col_letters(n: int) -> str:
    out = ""
    while n:
        n, r = divmod(n - 1, 26)
        out = chr(65 + r) + out
    return out


def _scan_values(sheet_name: str, vals, top_row: int, left_col: int) -> list[tuple[str, str]]:
    """Pure part of the sheet scan: [(error_text, "Sheet!A1"), ...] in row-major order.

    vals is UsedRange.Value: a 2D tuple, or a bare scalar when the range is one cell.
    Kept free of COM so the offset and single-cell paths run in a test without Excel.
    """
    if not isinstance(vals, tuple):
        vals = ((vals,),)
    hits = []
    for i, row in enumerate(vals):
        for j, v in enumerate(row):
            err = _error_text(v)
            if err:
                hits.append((err, f"{sheet_name}!{_col_letters(left_col + j)}{top_row + i}"))
    return hits


def _com_retry(fn, tries: int = 20, wait: float = 0.5):
    """Retry a COM call Excel rejects while busy (RPC_E_CALL_REJECTED / SERVERCALL_RETRYLATER)."""
    for i in range(tries):
        try:
            return fn()
        except Exception as e:  # pywintypes.com_error is not importable off-Windows
            code = getattr(e, "args", [None])[0]
            if code in (-2147418111, -2147417846) and i < tries - 1:
                time.sleep(wait)
                continue
            raise

_WORKER_MARKER = "--_com-worker"


def _kill_process_tree(proc: subprocess.Popen) -> None:
    """Best-effort hard kill of proc and its children.

    On Windows, taskkill /T walks the child tree, which a plain proc.kill()
    does not — a hung EXCEL.EXE launched by the worker is a grandchild of
    this function's caller, not a direct child, so it survives a bare kill()
    otherwise. On any other platform (this module's own dev/test environment
    included — win32com does not exist here, but the timeout plumbing around
    it still needs to be provable) taskkill does not exist at all, so fall
    back to a plain kill() on the immediate child; a worker-side leak of a
    grandchild process is a real gap on non-Windows but this module only
    ever ships the child command to Windows in production (see module
    docstring) — this fallback exists purely so the timeout path can be
    exercised and proven in the test suite on Linux/macOS.
    """
    if platform.system() == "Windows":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True,
                timeout=15,
                check=False,
            )
            return
        except Exception:
            pass
    try:
        proc.kill()
    except Exception:
        pass


def recalc_and_scan(xlsx_path: str | Path, timeout_sec: int = 300) -> dict:
    """Run the Excel-COM recalc+scan worker as a child process under an
    external timeout. Never raises on hang or on missing Excel/pywin32 —
    every failure mode is reported in the returned dict's "status" field so a
    calling script can branch on it without a try/except around COM-specific
    exception types it may not even be able to import on this platform.
    """
    xlsx_path = str(Path(xlsx_path).resolve())
    cmd = [sys.executable, str(Path(__file__).resolve()), _WORKER_MARKER, xlsx_path]

    started = time.monotonic()
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace",  # Korean paths: a cp949 decode error made stdout/stderr None
        )
    except OSError as e:
        return {"status": "spawn_error", "error": str(e)}

    try:
        stdout, stderr = proc.communicate(timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        _kill_process_tree(proc)
        try:
            proc.communicate(timeout=10)
        except Exception:
            pass
        return {
            "status": "timeout",
            "error": f"worker exceeded {timeout_sec}s and was force-killed",
            "elapsed_sec": round(time.monotonic() - started, 1),
        }

    elapsed = round(time.monotonic() - started, 1)

    if proc.returncode == 3:
        return {"status": "env_error", "error": (stderr or "").strip() or "pywin32/Excel not available", "elapsed_sec": elapsed}
    if proc.returncode != 0:
        return {"status": "worker_error", "error": (stderr or "").strip(), "returncode": proc.returncode, "elapsed_sec": elapsed}

    try:
        result = json.loads(stdout)
    except json.JSONDecodeError:
        return {"status": "bad_output", "raw_stdout": stdout, "raw_stderr": stderr, "elapsed_sec": elapsed}

    result["elapsed_sec"] = elapsed
    return result


def _com_worker_main(xlsx_path: str) -> dict:
    """Runs INSIDE the child process only. Imports win32com lazily so this
    module stays importable (for unit tests of recalc_and_scan's timeout
    plumbing) on a machine without pywin32/Excel installed."""
    try:
        import win32com.client as win32
    except ImportError:
        print("pywin32 not installed", file=sys.stderr)
        sys.exit(3)

    path = Path(xlsx_path).resolve()
    excel = None
    try:
        excel = win32.gencache.EnsureDispatch("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False
        excel.AskToUpdateLinks = False
        _ = excel.Workbooks.Count  # readiness probe, mirrors word_com_ops._open_word

        wb = excel.Workbooks.Open(str(path), UpdateLinks=0)
        try:
            excel.CalculateFullRebuild()
            wb.Save()
        finally:
            wb.Close(SaveChanges=False)

        errors = {}
        total_errors = 0
        wb2 = excel.Workbooks.Open(str(path), UpdateLinks=0)
        try:
            # Wait until recalculation is done (xlDone = 0), then read each sheet's
            # UsedRange in ONE call -- per-cell COM reads were slow and got rejected
            # while Excel was still busy.
            for _ in range(240):
                if _com_retry(lambda: excel.CalculationState) == 0:
                    break
                time.sleep(0.5)
            for ws in _com_retry(lambda: list(wb2.Worksheets)):
                used = _com_retry(lambda: ws.UsedRange)
                r0 = _com_retry(lambda: used.Row)
                c0 = _com_retry(lambda: used.Column)
                vals = _com_retry(lambda: used.Value)
                name = _com_retry(lambda: ws.Name)
                for err, addr in _scan_values(name, vals, r0, c0):
                    errors.setdefault(err, []).append(addr)
                    total_errors += 1
        finally:
            wb2.Close(SaveChanges=False)

        return {
            "status": "success" if total_errors == 0 else "errors_found",
            "total_errors": total_errors,
            "error_summary": {k: {"count": len(v), "locations": v[:20]} for k, v in errors.items()},
        }
    finally:
        if excel is not None:
            try:
                excel.DisplayAlerts = False
                excel.Quit()
            except Exception:
                pass


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == _WORKER_MARKER:
        # Child-process entry: emit ONLY the JSON result on stdout.
        result = _com_worker_main(sys.argv[2])
        print(json.dumps(result))
        sys.exit(0)

    if len(sys.argv) < 2:
        print("Usage: python excel_com_guard.py <path.xlsx> [timeout_sec]")
        sys.exit(1)

    target = sys.argv[1]
    to = int(sys.argv[2]) if len(sys.argv) > 2 else 300
    print(json.dumps(recalc_and_scan(target, timeout_sec=to), indent=2))
