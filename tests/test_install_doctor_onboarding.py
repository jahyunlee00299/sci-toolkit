#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Verifies that install.py --apply automatically runs doctor.py right after install.

Background: doctor.py is the only gate that checks "does this environment
actually work on a new machine" (shell presence, hook wiring, sentinel scan,
etc.), but until now a person had to separately remember to run
`python doctor.py` after install finished -- forget it, and you see only the
"install succeeded" output while the environment's hooks are actually dead.
The contract this test enforces:
  1. Once --apply finishes a real install, install.py auto-invokes doctor.py.
  2. A preview run without --apply does NOT invoke doctor.py (nothing has
     been installed yet, so there is nothing to check).
  3. On a distribution without doctor.py (an older version, etc.), this is
     silently skipped and the install itself does not fail.
"""
from __future__ import annotations

import sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALLER = ROOT / "install" / "install.py"

_fail = 0
_pass = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global _fail, _pass
    if cond:
        _pass += 1
        print(f"  OK    {name}")
    else:
        _fail += 1
        print(f"  FAIL  {name}" + (f"  — {detail}" if detail else ""))


def run_installer(dest: Path, *extra: str) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(INSTALLER), "--skills", "code-quality",
           "--dest", str(dest), *extra]
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=180)


def main() -> int:
    if not INSTALLER.exists():
        print(f"[error] Could not find the installer: {INSTALLER}")
        return 1

    # NOTE: must stay byte-identical to the marker install.py actually prints
    # (install/install.py, outside this file's lane) -- do not translate.
    marker = "설치 후 자동 점검 (doctor.py)"

    with tempfile.TemporaryDirectory(prefix="sci-toolkit-doctor-onboard-") as tmp:
        dest_apply = Path(tmp) / "apply_dest"
        proc_apply = run_installer(dest_apply, "--apply")
        out_apply = proc_apply.stdout + proc_apply.stderr
        check("doctor.py auto-run message is printed after --apply install",
              marker in out_apply,
              f"returncode={proc_apply.returncode}, tail={out_apply[-400:]!r}")

        dest_preview = Path(tmp) / "preview_dest"
        proc_preview = run_installer(dest_preview)  # no --apply = preview
        out_preview = proc_preview.stdout + proc_preview.stderr
        check("doctor.py is NOT run on a preview without --apply",
              marker not in out_preview,
              f"tail={out_preview[-400:]!r}")

    print("=" * 60)
    print(f"PASS {_pass} / FAIL {_fail}")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
