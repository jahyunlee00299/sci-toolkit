#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
install.py --apply 가 설치 직후 doctor.py 를 자동 실행하는지 검증한다.

배경: doctor.py 는 "새 컴퓨터에서 이 환경이 실제로 돌아가는가"(셸 유무,
훅 배선, sentinel 스캔 등)를 점검하는 유일한 게이트인데, 지금까지는 설치가
끝난 뒤 사람이 따로 `python doctor.py` 를 떠올려 실행해야 했다 — 잊으면
"설치 성공" 출력만 보고 환경이 실제로는 훅이 죽어 있는 상태로 넘어간다.
이 테스트가 지키는 계약:
  1. --apply 로 실제 설치가 끝나면 install.py 는 doctor.py 를 자동 호출한다.
  2. --apply 를 안 준 미리보기 실행에서는 doctor.py 를 호출하지 않는다
     (아직 아무것도 설치되지 않았으므로 점검할 대상이 없다).
  3. doctor.py 가 없는 배포(구버전 등)에서는 조용히 넘어가고 설치 자체는
     실패하지 않는다.
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
        print(f"[오류] 설치기를 찾을 수 없습니다: {INSTALLER}")
        return 1

    marker = "설치 후 자동 점검 (doctor.py)"

    with tempfile.TemporaryDirectory(prefix="sci-toolkit-doctor-onboard-") as tmp:
        dest_apply = Path(tmp) / "apply_dest"
        proc_apply = run_installer(dest_apply, "--apply")
        out_apply = proc_apply.stdout + proc_apply.stderr
        check("--apply 설치 후 doctor.py 자동 실행 문구가 출력됨",
              marker in out_apply,
              f"returncode={proc_apply.returncode}, tail={out_apply[-400:]!r}")

        dest_preview = Path(tmp) / "preview_dest"
        proc_preview = run_installer(dest_preview)  # --apply 없음 = 미리보기
        out_preview = proc_preview.stdout + proc_preview.stderr
        check("--apply 없는 미리보기에서는 doctor.py 를 실행하지 않음",
              marker not in out_preview,
              f"tail={out_preview[-400:]!r}")

    print("=" * 60)
    print(f"통과 {_pass} / 실패 {_fail}")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
