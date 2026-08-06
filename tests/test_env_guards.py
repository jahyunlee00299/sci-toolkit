#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
환경 불일치 가드 양방향 회귀 테스트.

세 가드가 막는 것은 전부 Windows + git-bash 조합에서 반복되는 실패다:
  · conda_multiline_guard   — `conda run ... python -c "여러\\n줄"` 은 줄바꿈이 깨진다
  · inline_multiline_guard  — 인라인 멀티라인 스크립트는 따옴표/한글이 깨진다
  · bash_env_mismatch_guard — PowerShell 구문을 bash 도구에 그대로 넣는 실수

양방향인 이유는 다른 가드 테스트와 같다: 과차단되는 가드는 꺼지고,
꺼진 가드는 없는 것과 같다. "막아야 할 것"과 "통과시켜야 할 것"을 같이 잰다.

주의: 케이스 문자열을 셸을 거쳐 전달하지 말 것. 개발자 자신의 세션 훅이
그것을 진짜 명령으로 오인해 차단한다(2026-08-07 실측). payload 는 반드시
파이썬 안에서 조립해 stdin 으로만 넘긴다.
"""
from __future__ import annotations

import sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOKS = ROOT / "hooks"

_fail = 0
_pass = 0
_skip = 0

NL = "\n"  # 케이스 안에서 줄바꿈을 만들 때 사용


def run_guard(guard: str, command: str) -> int:
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    proc = subprocess.run(
        ["sh", str(HOOKS / guard)],
        input=payload, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=60,
    )
    return proc.returncode


CASES: dict[str, list[tuple[str, str, int]]] = {
    "conda_multiline_guard.sh": [
        ("conda + 멀티라인 -c",
         'conda run -n myenv python -c "import os' + NL + 'print(os.getcwd())"', 2),
        ("conda + 단일라인 -c",
         'conda run -n myenv python -c "print(1)"', 0),
        ("conda + 파일 실행",
         'conda run -n myenv python analysis.py --input data.csv', 0),
        ("conda 무관 명령", 'ls -la', 0),
    ],
    # 이 가드가 잡는 것은 `python -c` 가 아니라 **셸 변수에 인라인으로 박은
    # 멀티라인 스크립트**다. 260807 이식 시 원본과 동작이 일치함을 실측 확인
    # (python -c 멀티라인은 원본도 통과시킨다 — 범위 밖).
    "inline_multiline_guard.sh": [
        ("변수에 인라인 멀티라인",
         "content='''line1" + NL + "line2" + NL + "line3'''", 2),
        # 이 가드의 `python -c` 판정은 **비ASCII 가 있을 때만** 차단한다.
        # 순수 ASCII 멀티라인은 git-bash 에서 실제로 정상 동작하므로(260801 실측)
        # 막으면 결과가 같은 왕복만 늘어나는 순수 마찰이 된다.
        ("한글 든 멀티라인 -c",
         'python -c "d={\'한글\':1}' + NL + 'print(d)"', 2),
        ("ASCII 멀티라인 -c 는 통과",
         'python -c "a=1' + NL + 'b=2"', 0),
        ("heredoc 로 파일 쓰기는 권장 패턴",
         "cat > /tmp/x.py << 'EOF'" + NL + "print(1)" + NL + "EOF", 0),
        ("단일라인 python", 'python -c "print(42)"', 0),
        ("스크립트 실행", 'python scripts/analyze.py --flag', 0),
        ("일반 명령", 'git status', 0),
    ],
    "bash_env_mismatch_guard.sh": [
        ("PowerShell cmdlet in bash", 'Get-Item "C:/Users/Public"', 2),
        ("$env: 변수 in bash", 'ls "$env:USERPROFILE/Documents"', 2),
        ("powershell.exe 래핑은 정상",
         'powershell.exe -NoProfile -Command "Get-Item C:/Users/Public"', 0),
        ("평범한 bash", 'ls -la /tmp', 0),
        ("python 실행", 'python --version', 0),
    ],
}


def run_chain(command: str) -> int:
    """체인러너를 통해 실행 — 개별 훅이 아니라 실제 배선 경로를 잰다."""
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    proc = subprocess.run(
        ["sh", str(HOOKS / "_run_hooks_chained.sh")],
        input=payload, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=120,
    )
    return proc.returncode


def main() -> int:
    global _fail, _pass, _skip
    print("환경 불일치 가드 양방향 검증")
    print("=" * 60)

    for guard, cases in CASES.items():
        if not (HOOKS / guard).is_file():
            print(f"\n[{guard}] SKIP — 파일 없음")
            _skip += 1
            continue
        print(f"\n[{guard}]")
        for label, cmd, want in cases:
            got = run_guard(guard, cmd)
            verb = "차단" if want == 2 else "통과"
            if got == want:
                _pass += 1
            else:
                _fail += 1
                print(f"  FAIL  {verb}: {label} — 기대 exit={want}, 실제 exit={got}")

    # ── 체인러너 경유 ────────────────────────────────────────────────────
    # 개별 훅이 통과해도 체인에 등록되지 않았으면 실제로는 아무것도 막지 못한다.
    # 배선이 살아 있는지는 실제 경로로 재야 안다(C-58: 배선까지가 기능).
    if (HOOKS / "_run_hooks_chained.sh").is_file():
        print("\n[_run_hooks_chained.sh] 실제 배선 경로")
        chain_cases = [
            ("conda 멀티라인",
             'conda run -n e python -c "import os' + NL + 'print(1)"', 2),
            ("PowerShell cmdlet", 'Get-Item "C:/Users/Public"', 2),
            ("변수 인라인 멀티라인", "content='''a" + NL + "b'''", 2),
            ("force push", 'git push --force origin main', 2),
            ("정상 명령", 'git status', 0),
            ("정상 실행", 'python scripts/run.py', 0),
        ]
        for label, cmd, want in chain_cases:
            got = run_chain(cmd)
            verb = "차단" if want == 2 else "통과"
            if got == want:
                _pass += 1
            else:
                _fail += 1
                print(f"  FAIL  {verb}: {label} — 기대 exit={want}, 실제 exit={got}")
    else:
        print("\n[_run_hooks_chained.sh] SKIP — 없음")
        _skip += 1

    print("=" * 60)
    print(f"통과 {_pass} / 실패 {_fail}" + (f" / 스킵 {_skip}" if _skip else ""))
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
