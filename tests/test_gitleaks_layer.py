#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""doctor's gitleaks layer: absent binary = WARN, clean = OK, findings = FAIL; config is sane.

Why this exists
---------------
SENTINEL is a hand-kept regex set tuned to this repo's own incidents. gitleaks
brings ~150 vendor rules maintained upstream, so doctor runs it as a second
layer when the binary is present (CI always has it). This test pins the
wrapper's three verdicts with a scripted shim on PATH — it does NOT prove
gitleaks itself finds secrets; the real binary runs in CI. The shim is the
only way to exercise the FAIL branch without committing a real-looking
secret to the repo.

Also pinned: .gitleaks.toml parses as TOML, every allowlisted path exists,
and the allowlist covers the same detector/fixture files SENTINEL exempts
(a file exempted by one scanner but not the other would fail one of them
on every run and train people to ignore red).

Run: python tests/test_gitleaks_layer.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
import tomllib
from pathlib import Path

if sys.platform == "win32":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("doctor", str(ROOT / "doctor.py"))
doctor = importlib.util.module_from_spec(spec)
sys.modules["doctor"] = doctor
spec.loader.exec_module(doctor)
from doctor_lib import sentinel  # noqa: E402

_results: list[tuple[bool, str]] = []


def check(name: str, cond: bool, note: str = "") -> None:
    _results.append((cond, name))
    tag = "[OK]  " if cond else "[FAIL]"
    print(f"  {tag} {name}" + (f"  {note}" if note and not cond else ""))


# --------------------------------------------------------------------------
print("== .gitleaks.toml")
cfg_path = ROOT / ".gitleaks.toml"
check(".gitleaks.toml present", cfg_path.is_file())
cfg = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
check("parses as TOML with an [allowlist]", isinstance(cfg.get("allowlist"), dict))
paths = cfg.get("allowlist", {}).get("paths", [])
unanchored = [p for p in paths if not re.fullmatch(r"\^.*\$", p)]
check("every allowlist path regex is anchored (^...$)", not unanchored, str(unanchored))
missing = [p for p in paths if not (ROOT / re.sub(r"^\^|\$$", "", p).replace("\\.", ".")).exists()]
check("every allowlisted path exists in the repo", not missing, str(missing))
exempt = set(sentinel.SENTINEL_SELF_TEST_FILES) | set(sentinel.SENTINEL_DETECTOR_FILES)
covered = {Path(re.sub(r"^\^|\$$", "", p).replace("\\.", ".")).name for p in paths}
check("SENTINEL's exempt files are all allowlisted for gitleaks too",
      exempt <= covered, f"not covered: {sorted(exempt - covered)}")


# --------------------------------------------------------------------------
print("\n== wrapper verdicts with a scripted shim on PATH")


def with_shim(shim_spec: tuple[int, list[dict]] | None, fn):
    """Run fn() with a fake `gitleaks` on PATH (None -> no shim: absent case).

    The shim copies a static payload.json (written here, next to it) to the
    --report-path argument and exits with the given code. A static file is
    used because quoting JSON inside a cmd.exe one-liner broke on the first
    try (measured: the report arrived empty).
    """
    saved = os.environ.get("PATH", "")
    saved_payload = os.environ.get("GITLEAKS_SHIM_PAYLOAD")
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        if shim_spec is not None:
            exit_code, findings = shim_spec
            payload = d / "payload.json"
            payload.write_text(json.dumps(findings), encoding="utf-8")
            # the shim finds its payload through the environment, not %~dp0 —
            # the batch-relative form resolved to nothing under subprocess on
            # this machine ("cannot find the file specified", measured)
            os.environ["GITLEAKS_SHIM_PAYLOAD"] = str(payload)
            if sys.platform == "win32":
                (d / "gitleaks.cmd").write_text(
                    "@echo off\r\nset out=\r\n:loop\r\nif \"%~1\"==\"\" goto done\r\n"
                    "if \"%~1\"==\"--report-path\" set out=%~2\r\nshift\r\ngoto loop\r\n:done\r\n"
                    "if not \"%out%\"==\"\" copy /y \"%GITLEAKS_SHIM_PAYLOAD%\" \"%out%\"\r\n"
                    f"exit /b {exit_code}\r\n", encoding="utf-8")
            else:
                sh = d / "gitleaks"
                sh.write_text(
                    "#!/bin/sh\nout=\"\"\nwhile [ $# -gt 0 ]; do\n"
                    "  if [ \"$1\" = \"--report-path\" ]; then out=\"$2\"; fi\n  shift\ndone\n"
                    "[ -n \"$out\" ] && cp \"$GITLEAKS_SHIM_PAYLOAD\" \"$out\"\n"
                    f"exit {exit_code}\n", encoding="utf-8")
                sh.chmod(0o755)
            os.environ["PATH"] = str(d) + os.pathsep + saved
        else:
            # hide any real gitleaks: only an empty dir on PATH
            os.environ["PATH"] = str(d)
        try:
            return fn()
        finally:
            os.environ["PATH"] = saved
            if saved_payload is None:
                os.environ.pop("GITLEAKS_SHIM_PAYLOAD", None)
            else:
                os.environ["GITLEAKS_SHIM_PAYLOAD"] = saved_payload


def shim(exit_code: int, findings: list[dict] | None = None) -> tuple[int, list[dict]]:
    return exit_code, findings or []


if shutil.which("gitleaks"):
    print("  [INFO] a real gitleaks is on PATH; the shim cases below shadow it")

r = with_shim(None, lambda: doctor.check_gitleaks(ROOT))
check("binary absent -> WARN mentioning SENTINEL still ran", r.status == doctor.STATUS_WARN and "SENTINEL" in r.message, f"{r.status} {r.message}")

r = with_shim(shim(0, []), lambda: doctor.check_gitleaks(ROOT))
check("exit 0 + empty report -> OK", r.status == doctor.STATUS_OK, f"{r.status} {r.message}")

r = with_shim(shim(1, [{"File": "config/x.json", "StartLine": 3, "RuleID": "generic-api-key"}]),
              lambda: doctor.check_gitleaks(ROOT))
check("exit 1 + one finding -> FAIL naming file:line rule", r.status == doctor.STATUS_FAIL
      and any("config/x.json:3 generic-api-key" in d for d in r.details), f"{r.status} {r.message} {r.details}")

r = with_shim(shim(2, []), lambda: doctor.check_gitleaks(ROOT))
check("unexpected exit code -> WARN (tool problem, not a leak verdict)", r.status == doctor.STATUS_WARN, f"{r.status} {r.message}")

with tempfile.TemporaryDirectory() as td:
    r = with_shim(shim(0, []), lambda: doctor.check_gitleaks(Path(td)))
    check("root without .gitleaks.toml -> WARN, gitleaks not invoked as a gate", r.status == doctor.STATUS_WARN and ".gitleaks.toml absent" in r.message, f"{r.status} {r.message}")

# --------------------------------------------------------------------------
n_fail = sum(1 for ok, _ in _results if not ok)
print(f"\nSUMMARY: {len(_results) - n_fail} passed, {n_fail} failed")
sys.exit(1 if n_fail else 0)
