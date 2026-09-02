"""Result model + shared subprocess/status-classification primitives for doctor.py.

STATUS_OK/WARN/FAIL, CheckResult, the one subprocess-shelling helper
(_run_python) every check goes through, and the outage-vs-broken classifier
for self-test failures.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

STATUS_OK = "OK"
STATUS_WARN = "WARN"
STATUS_FAIL = "FAIL"

_STATUS_RANK = {STATUS_OK: 0, STATUS_WARN: 1, STATUS_FAIL: 2}


@dataclass
class CheckResult:
    name: str
    status: str
    message: str
    details: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "details": self.details,
        }


def _run_python(root: Path, argv: list[str], timeout: int) -> tuple[int, str, str]:
    """Run a Python subprocess from the toolkit root and return (rc, stdout, stderr).

    The one place that knows the encoding/cwd/timeout conventions; every check
    that shells out goes through it. Raises OSError / subprocess.SubprocessError
    (TimeoutExpired included) so the caller decides whether that is WARN or FAIL.
    """
    return _run_command(root, [sys.executable, *argv], timeout)


def _run_command(root: Path, argv: list[str], timeout: int) -> tuple[int, str, str]:
    """The ONE subprocess call in doctor, for any executable (gitleaks included).

    Same contract as _run_python: returns (rc, stdout, stderr), raises OSError /
    subprocess.SubprocessError so the caller decides WARN vs FAIL.
    """
    proc = subprocess.run(
        argv, cwd=str(root),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout)
    return proc.returncode, proc.stdout or "", proc.stderr or ""


# Output fragments that mean "the other side is down", not "our tool is broken".
# A self-test whose only failing cases are [network]-tagged AND whose output
# carries one of these is reported as blocked by an upstream outage (WARN),
# never as a broken verification tool (FAIL). Measured 2026-09-02: Europe PMC
# returned HTTP 500 and doctor told a fresh-clone user "a verification tool is
# broken" — a non-bug that costs an afternoon to chase.
_UPSTREAM_OUTAGE_MARKERS = (
    "HTTP 500", "HTTP 502", "HTTP 503", "HTTP 504", "HTTP 429",
    "URLError", "timed out", "Connection reset", "RemoteDisconnected",
    "upstream", "Temporary failure in name resolution", "getaddrinfo failed",
)


def _classify_selftest_failure(out: str) -> str:
    """'external' when every FAIL line is [network]-tagged and an outage marker
    is present; otherwise 'broken'."""
    fail_lines = [ln for ln in out.splitlines() if "[FAIL]" in ln]
    if not fail_lines:
        return "broken"  # exited nonzero without a FAIL line: a crash, not an outage
    if not all("[network]" in ln for ln in fail_lines):
        return "broken"
    if not any(m in out for m in _UPSTREAM_OUTAGE_MARKERS):
        return "broken"
    return "external"


def overall_status(results: list[CheckResult]) -> str:
    worst = max((r.status for r in results), key=lambda s: _STATUS_RANK[s], default=STATUS_OK)
    return worst
