#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scripts/env_detect.py 회귀 테스트.

이 검사 자체가 "이 컴퓨터에서 훅이 실제로 도는가"를 판정하므로, 실제 머신
상태(예: 이 노트북은 Git Bash가 PATH에 있음)에만 의존하면 다른 상태(WSL 스텁,
Git Bash 없음, known-location에만 존재)를 아무도 확인 못 한 채로 남는다.
platform.system/shutil.which/Path.is_file/환경변수를 주입해 6가지 분기를
전부 실행한다.

실행: python tests/test_env_detect.py   (exit 0 = 통과)
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest import mock

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"

spec = importlib.util.spec_from_file_location("env_detect", str(SCRIPTS / "env_detect.py"))
env_detect = importlib.util.module_from_spec(spec)
sys.modules["env_detect"] = env_detect
spec.loader.exec_module(env_detect)

_fail = 0
_pass = 0


def check(label: str, cond: bool, extra: str = "") -> None:
    global _fail, _pass
    if cond:
        _pass += 1
        print(f"  PASS  {label}")
    else:
        _fail += 1
        print(f"  FAIL  {label}  {extra}")


def case(label, *, system, which_map, env=None, isfile_map=None):
    """Run detect() with platform/shutil/Path/env patched, return the result dict."""
    env = env or {}
    isfile_map = isfile_map or {}

    def fake_which(name):
        return which_map.get(name)

    def fake_is_file(self):
        return isfile_map.get(str(self), False)

    with mock.patch("env_detect.platform.system", return_value=system), \
         mock.patch("env_detect.shutil.which", side_effect=fake_which), \
         mock.patch("env_detect.Path.is_file", fake_is_file), \
         mock.patch.dict("env_detect.os.environ", env, clear=True):
        return env_detect.detect()


def main() -> int:
    # 1) macOS/Linux, sh 존재 -> OK
    r = case("mac ok", system="Darwin", which_map={"sh": "/bin/sh"})
    check("macOS: sh found on PATH -> shell_ok", r["shell_ok"] and r["shell_source"] == "PATH")

    # 2) macOS/Linux, 아무것도 없음 -> FAIL (이례적이지만 대비)
    r = case("linux missing", system="Linux", which_map={})
    check("Linux: nothing on PATH -> not shell_ok", not r["shell_ok"])
    check("Linux: advice non-empty when missing", len(r["advice"]) > 0)

    # 3) Windows, CLAUDE_CODE_GIT_BASH_PATH 가 실존 파일 -> OK
    gb = r"C:\Program Files\Git\bin\bash.exe"
    r = case("win env var", system="Windows", which_map={},
             env={"CLAUDE_CODE_GIT_BASH_PATH": gb}, isfile_map={gb: True})
    check("Windows: valid env var wins -> shell_ok",
          r["shell_ok"] and r["shell_source"].startswith("env:"))

    # 4) Windows, env var 가 가리키는 파일이 없음 -> env var 무시하고 다음 단계로
    r = case("win env var broken", system="Windows", which_map={},
             env={"CLAUDE_CODE_GIT_BASH_PATH": gb}, isfile_map={gb: False})
    check("Windows: env var pointing at missing file is not trusted", not (
        r["shell_ok"] and r["shell_source"].startswith("env:")))

    # 5) Windows, 실제 Git Bash가 PATH에 있음 -> OK
    r = case("win path bash", system="Windows",
             which_map={"bash": r"C:\Program Files\Git\bin\bash.exe"})
    check("Windows: real Git Bash on PATH -> shell_ok", r["shell_ok"] and r["shell_source"] == "PATH")

    # 6) Windows, PATH의 bash가 WSL 런처(System32) -> FAIL + WSL 안내
    r = case("win wsl stub", system="Windows",
             which_map={"bash": r"C:\Windows\System32\bash.exe"})
    check("Windows: WSL System32 stub -> not shell_ok", not r["shell_ok"])
    check("Windows: WSL stub -> source flagged", r["shell_source"] == "wsl_stub")

    # 7) Windows, PATH엔 없지만 known location에 있음 -> FAIL(조치 필요) + 정확한 안내
    r = case("win known location", system="Windows", which_map={},
             isfile_map={r"C:\Program Files\Git\bin\bash.exe": True})
    check("Windows: known-location-only is NOT auto-OK (needs env var set)",
          not r["shell_ok"])
    check("Windows: known-location advice names the env var",
          any("CLAUDE_CODE_GIT_BASH_PATH" in a for a in r["advice"]))

    # 8) Windows, 아무것도 없음 -> FAIL + Git for Windows 안내
    r = case("win nothing", system="Windows", which_map={})
    check("Windows: nothing found -> not shell_ok", not r["shell_ok"])
    check("Windows: nothing found -> advice mentions Git", any("Git" in a for a in r["advice"]))

    print(f"\n{_pass} passed, {_fail} failed")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
