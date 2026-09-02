#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""doctor.py must tell "our verification tool is broken" from "their server is down".

Why this exists
---------------
Measured 2026-09-02: Europe PMC answered HTTP 500, tests/test_si_institutional.py
failed only its [network]-tagged cases, and doctor reported
"[FAIL] Toolkit self-tests — a verification tool is broken". Nothing was
broken. A fresh-clone user reading that line chases a non-bug; a maintainer
learns to ignore red, which is worse.

What is pinned
--------------
  _classify_selftest_failure   pure verdict on captured output
  check_toolkit_selftests      end-to-end on a throwaway root with fake
                               self-test scripts (SELF_TEST_SCRIPTS patched
                               in-process): outage -> WARN, broken -> FAIL,
                               mixed -> FAIL, all green -> OK
  _run_test_script             summary is the script's last stdout line
                               (the Korean matcher it replaced matched nothing
                               after the 2026-08-28 translation)
  _run_python                  one helper, raises on timeout instead of hanging

Run: python tests/test_doctor_selftest_verdicts.py
"""
from __future__ import annotations

import importlib.util
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

spec = importlib.util.spec_from_file_location("doctor", str(ROOT / "doctor.py"))
doctor = importlib.util.module_from_spec(spec)
sys.modules["doctor"] = doctor  # dataclasses resolve annotations via sys.modules[cls.__module__]
spec.loader.exec_module(doctor)

_results: list[tuple[bool, str]] = []


def check(name: str, cond: bool, note: str = "") -> None:
    _results.append((cond, name))
    tag = "[OK]  " if cond else "[FAIL]"
    print(f"  {tag} {name}" + (f"  {note}" if note and not cond else ""))


def section(title: str) -> None:
    print(f"\n== {title}")


# --------------------------------------------------------------------------
section("_classify_selftest_failure: pure verdicts")

C = doctor._classify_selftest_failure
check("only [network] FAILs + HTTP 500 -> external",
      C("  [OK] offline case\n  [FAIL] [network] PMC -> found  got=error note=lookup failed: HTTP 500\n") == "external")
check("only [network] FAILs + URLError -> external",
      C("[FAIL] [network] x  URLError: <urlopen error timed out>") == "external")
check("only [network] FAILs + HTTP 429 (rate limited) -> external",
      C("[FAIL] [network] x  HTTP 429") == "external")
check("[network] FAIL without an outage marker -> broken (a wrong answer from a live API is a real bug)",
      C("[FAIL] [network] valid DOI -> OK  got=HALLUCINATED") == "broken")
check("mixed offline + network FAILs -> broken",
      C("[FAIL] offline parser case\n[FAIL] [network] x HTTP 500") == "broken")
check("nonzero exit with no FAIL line (crash/traceback) -> broken",
      C("Traceback (most recent call last):\n  ...\nHTTP 500 in message") == "broken")
check("empty output -> broken", C("") == "broken")


# --------------------------------------------------------------------------
section("check_toolkit_selftests: end-to-end on a throwaway root")


def fake_root(scripts: dict[str, str]) -> Path:
    tmp = Path(tempfile.mkdtemp())
    (tmp / "tests").mkdir()
    for name, body in scripts.items():
        (tmp / "tests" / name).write_text(body, encoding="utf-8")
    return tmp


OUTAGE = ("import sys\n"
          "print('  [OK] offline case')\n"
          "print('  [FAIL] [network] PMC paper -> status=found  got=error note=Europe PMC lookup failed: HTTP 500')\n"
          "sys.exit(1)\n")
BROKEN = ("import sys\n"
          "print('  [FAIL] parser returns 0 peaks  expected=2')\n"
          "sys.exit(1)\n")
GREEN = "print('  [OK] fine')\nprint('ALL PASS')\n"

saved = doctor.SELF_TEST_SCRIPTS
try:
    doctor.SELF_TEST_SCRIPTS = [("tests/t_outage.py", "outage-only")]
    r = doctor.check_toolkit_selftests(fake_root({"t_outage.py": OUTAGE}))
    check("outage-only script -> WARN, not FAIL", r.status == doctor.STATUS_WARN, f"{r.status} {r.message}")
    check("message says 'upstream outage' and names the script",
          "upstream outage" in r.message and any("t_outage.py" in d for d in r.details), f"{r.message} {r.details}")
    check("message does NOT say 'broken'", "broken" not in r.message, r.message)

    doctor.SELF_TEST_SCRIPTS = [("tests/t_broken.py", "broken")]
    r = doctor.check_toolkit_selftests(fake_root({"t_broken.py": BROKEN}))
    check("broken script -> FAIL", r.status == doctor.STATUS_FAIL, f"{r.status} {r.message}")
    check("details carry the expected/actual line",
          any("expected=2" in d for d in r.details), str(r.details))

    doctor.SELF_TEST_SCRIPTS = [("tests/t_outage.py", "outage"), ("tests/t_broken.py", "broken")]
    r = doctor.check_toolkit_selftests(fake_root({"t_outage.py": OUTAGE, "t_broken.py": BROKEN}))
    check("outage + broken -> FAIL (the outage never hides a real break)",
          r.status == doctor.STATUS_FAIL and "1 of 2" in r.message, f"{r.status} {r.message}")
    check("the outage still appears in details for the record",
          any("upstream outage" in d for d in r.details), str(r.details))

    doctor.SELF_TEST_SCRIPTS = [("tests/t_green.py", "green"), ("tests/t_outage.py", "outage")]
    r = doctor.check_toolkit_selftests(fake_root({"t_green.py": GREEN, "t_outage.py": OUTAGE}))
    check("green + outage -> WARN with '1 of 2 self-test(s) passing'",
          r.status == doctor.STATUS_WARN and "1 of 2" in r.message, f"{r.status} {r.message}")

    doctor.SELF_TEST_SCRIPTS = [("tests/t_green.py", "green")]
    r = doctor.check_toolkit_selftests(fake_root({"t_green.py": GREEN}))
    check("all green -> OK", r.status == doctor.STATUS_OK, f"{r.status} {r.message}")

    doctor.SELF_TEST_SCRIPTS = [("tests/does_not_exist.py", "missing")]
    r = doctor.check_toolkit_selftests(fake_root({}))
    check("no registered script present -> WARN 'skipped', not a crash",
          r.status == doctor.STATUS_WARN and "skipped" in r.message, f"{r.status} {r.message}")
finally:
    doctor.SELF_TEST_SCRIPTS = saved


# --------------------------------------------------------------------------
section("_run_test_script: summary is the script's own last line")

root = fake_root({"t_sum.py": "print('  [OK] a')\nprint('Checked 5 reference(s)')\nprint('ALL PASS — every reference exists')\n"})
r = doctor._run_test_script(root, "tests/t_sum.py", "sum", "fallback ok", "fallback fail")
check("OK message is the last stdout line, not the fallback",
      r.status == doctor.STATUS_OK and r.message == "ALL PASS — every reference exists", f"{r.status} {r.message!r}")
root = fake_root({"t_fail.py": "import sys\nprint('  [FAIL] x')\nsys.exit(1)\n"})
r = doctor._run_test_script(root, "tests/t_fail.py", "f", "ok", "the gate failed")
check("nonzero exit -> FAIL with fail_msg and indented detail lines",
      r.status == doctor.STATUS_FAIL and r.message == "the gate failed" and r.details == ["  [FAIL] x"],
      f"{r.status} {r.message!r} {r.details}")


# --------------------------------------------------------------------------
section("_run_python: one helper, timeout raises")

rc, out, err = doctor._run_python(ROOT, ["-c", "print('hi'); import sys; sys.exit(3)"], timeout=30)
check("returns (rc, stdout, stderr)", rc == 3 and out.strip() == "hi" and err == "", f"{rc} {out!r} {err!r}")
try:
    doctor._run_python(ROOT, ["-c", "import time; time.sleep(5)"], timeout=1)
    check("timeout raises TimeoutExpired", False, "no exception")
except subprocess.TimeoutExpired:
    check("timeout raises TimeoutExpired", True)
src = (ROOT / "doctor.py").read_text(encoding="utf-8")
check("doctor.py has exactly one subprocess.run call (inside _run_python)",
      src.count("subprocess.run(") == 1, f"count={src.count('subprocess.run(')}")
check("the dead Korean summary matcher is gone", "대조 대상" not in src)


# --------------------------------------------------------------------------
n_fail = sum(1 for ok, _ in _results if not ok)
print(f"\nSUMMARY: {len(_results) - n_fail} passed, {n_fail} failed")
sys.exit(1 if n_fail else 0)
