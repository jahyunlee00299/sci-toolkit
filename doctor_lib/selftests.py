"""Self-test runner: executes this package's own regression tests as part of
the doctor gate, so a broken verification tool never ships quietly."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from doctor_lib.result import (
    CheckResult, STATUS_FAIL, STATUS_OK, STATUS_WARN,
    _UPSTREAM_OUTAGE_MARKERS, _classify_selftest_failure, _run_python,
)


def _selftest_command(root: Path, rel: str) -> list[str]:
    """Script entries run as `python <file>`; directory entries run under pytest."""
    target = root / rel
    if target.is_dir():
        return [sys.executable, "-m", "pytest", str(target), "-q",
                "-o", "python_files=test_*.py", "-p", "no:cacheprovider"]
    return [sys.executable, str(target)]


def run_selftests(root: Path, scripts: list[tuple[str, str]]) -> CheckResult:
    """Run the regression tests for this package's own verification tools.

    These are the checks that guard manuscripts, numbers and secrets. If one of
    them silently stops working, every artifact it was supposed to gate ships
    unverified — so their tests run as part of doctor rather than on request.

    `scripts` is the (rel_path, label) list to run — callers pass their own
    module-level SELF_TEST_SCRIPTS so tests can monkeypatch it and re-run.
    """
    name = "Toolkit self-tests"
    present = [(rel, label) for rel, label in scripts
               if (root / rel).exists()]
    if not present:
        return CheckResult(name, STATUS_WARN, "no self-test scripts present — skipped")

    failed, errored, external = [], [], []
    # `failed` mixes one header line per script with its detail lines, so its
    # length counts lines, not scripts — reporting it as "N of 16" produced
    # nonsense like "19 of 16". Count the scripts separately.
    n_failed_scripts = 0
    for rel, label in present:
        try:
            rc, stdout, stderr = _run_python(root, _selftest_command(root, rel)[1:], timeout=300)
        except (OSError, subprocess.SubprocessError) as exc:
            errored.append(f"{rel}: could not run ({exc})")
            continue
        if rc != 0:
            out = stdout + stderr
            if _classify_selftest_failure(out) == "external":
                marker = next((m for m in _UPSTREAM_OUTAGE_MARKERS if m in out), "outage")
                external.append(f"{rel} ({label}): blocked by an upstream outage ({marker}) "
                                f"— only [network] cases failed; re-run later, nothing to fix here")
                continue
            # Keep the failing lines AND what follows them. Reporting only the
            # first "FAIL" line throws away the expected/actual values printed
            # underneath it, which is exactly what you need to tell a real
            # regression from an environment difference. A CI log that says only
            # "FAIL <case name>" cannot be diagnosed without re-running locally —
            # and if it reproduces locally you did not need the CI log anyway.
            lines = out.splitlines()
            detail = []
            for i, ln in enumerate(lines):
                if "FAIL" in ln or "Error" in ln or "Traceback" in ln or "attempt " in ln:
                    detail.append(ln.strip()[:160])
                    # the two lines after a failure usually carry the expected/actual values
                    for nxt in lines[i + 1:i + 3]:
                        s = nxt.strip()
                        if s and not s.startswith("PASS"):
                            detail.append(f"    {s[:160]}")
                if len(detail) >= 12:
                    detail.append("    …")
                    break
            failed.append(f"{rel} ({label}) exited {rc}")
            failed.extend(f"    {d}" for d in detail)
            n_failed_scripts += 1

    if failed:
        return CheckResult(name, STATUS_FAIL,
                           f"{n_failed_scripts} of {len(present)} self-test(s) failing — "
                           f"a verification tool is broken",
                           failed + errored + external)
    if errored or external:
        parts = []
        if external:
            parts.append(f"{len(external)} blocked by an upstream outage")
        if errored:
            parts.append(f"{len(errored)} could not run")
        return CheckResult(name, STATUS_WARN,
                           f"{len(present) - len(errored) - len(external)} of {len(present)} "
                           f"self-test(s) passing; " + ", ".join(parts),
                           external + errored)
    return CheckResult(name, STATUS_OK,
                       f"{len(present)} self-test(s) passing "
                       f"({', '.join(label for _, label in present)})")
