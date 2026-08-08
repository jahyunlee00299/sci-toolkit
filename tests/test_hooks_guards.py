#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hooks/ 안전가드 양방향 회귀 테스트.

훅은 "설치했다"가 아니라 "실제로 발동한다"를 증명해야 한다. 배선만 하고
발동을 재지 않으면, 조용히 죽은 가드를 켜져 있다고 믿게 된다.

양방향인 이유:
  MUST BLOCK 만 검사하면 과차단(정상 작업을 막는 가드)을 놓친다. 그리고
  과차단되는 가드는 사용자가 꺼버리므로, 결국 아무것도 지키지 못한다.
  그래서 "막아야 할 것"과 "통과시켜야 할 것"을 같은 무게로 검사한다.

계약:
  exit 0 = allow, exit 2 = block (다른 코드는 계약 위반)
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
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOKS = ROOT / "hooks"

_fail = 0
_pass = 0
_skip = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global _fail, _pass
    if cond:
        _pass += 1
    else:
        _fail += 1
        print(f"  FAIL  {name}" + (f"  — {detail}" if detail else ""))


def run_guard(guard: str, command: str, cwd: Path | None = None) -> int:
    """가드에 Bash 툴콜 payload 를 주고 exit code 를 받는다."""
    payload = json.dumps({
        "tool_name": "Bash",
        "tool_input": {"command": command},
    })
    proc = subprocess.run(
        ["sh", str(HOOKS / guard)],
        input=payload, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        cwd=str(cwd) if cwd else None, timeout=60,
    )
    return proc.returncode


# (설명, 명령, 기대 exit)  — 2=차단, 0=통과
GIT_CASES = [
    # 반드시 차단
    ("force push",            "git push --force origin main", 2),
    ("force push -f",         "git push -f origin feature", 2),
    ("reset --hard",          "git reset --hard HEAD~3", 2),
    ("config --global",       "git config --global user.email a@b.c", 2),
    ("branch -D",             "git branch -D old-feature", 2),
    ("hook bypass no-verify", "git commit --no-verify -m 'skip checks'", 2),
    ("hook bypass hooksPath", "git -c core.hooksPath=/dev/null commit -m x", 2),
    # 반드시 통과 — 일상적인 git 작업
    ("status",                "git status", 0),
    ("normal push",           "git push origin feature/my-work", 0),
    ("commit",                "git commit -m 'fix: correct the unit label'", 0),
    ("pull",                  "git pull --ff-only", 0),
    ("diff",                  "git diff --stat", 0),
    ("branch create",         "git checkout -b feature/new", 0),
    ("log",                   "git log --oneline -10", 0),
    ("soft reset",            "git reset --soft HEAD~1", 0),
    ("add",                   "git add specific_file.py", 0),
    # --- 큰따옴표 절단 회귀 (2026-08-08 실측) --------------------------------
    # 가드가 payload 를 grep '"command"...:"[^"]*"' 로 뽑던 시절, 명령 안의
    # 큰따옴표는 JSON 에서 \" 로 이스케이프되므로 추출이 거기서 잘렸다.
    # 즉 따옴표 뒤의 위험한 부분이 아예 검사되지 않았다. 아래 셋은 그때
    # 전부 통과(exit 0)했던 실제 형태다 — 커밋 메시지에 따옴표를 쓰는 것은
    # 예외가 아니라 기본이라, 가장 흔한 형태가 곧 우회 형태였다.
    # 기존 케이스가 이걸 놓친 이유는 전부 홑따옴표를 썼기 때문이다(JSON 은
    # 홑따옴표를 이스케이프하지 않아 절단이 일어나지 않는다).
    ("force push, 따옴표 뒤",  'git commit -m "wip" && git push --force origin main', 2),
    ("reset --hard, 따옴표 뒤", 'git commit -m "save" && git reset --hard HEAD~3', 2),
    ("config --global, 따옴표 뒤",
     'git commit -m "x" && git config --global user.email a@b.c', 2),
    ("큰따옴표 커밋 (정상 통과)", 'git commit -m "fix: correct the unit label"', 0),
]

DELETE_CASES = [
    ("rm -rf",        "rm -rf /some/path", 2),
    ("sudo rm",       "sudo rm -r /etc/thing", 2),
    ("ls",            "ls -la", 0),
    ("cat",           "cat README.md", 0),
    # 큰따옴표 절단 회귀 — 공백이 든 Windows 경로는 따옴표가 필수라서,
    # 이 형태가 예외가 아니라 표준이다.
    ("rm -rf, 따옴표 cd 뒤",  'cd "/c/Users/me/My Project" && rm -rf build', 2),
    ("rm -rf 따옴표 경로",     'rm -rf "/c/Users/me/My Project/out"', 2),
    ("큰따옴표 echo (정상 통과)", 'echo "nothing is deleted here"', 0),
]

CLOUD_CASES = [
    ("find on OneDrive", "find ~/OneDrive -name '*.docx'", 2),
    ("ls -R on Dropbox", "ls -R ~/Dropbox/data", 2),
    ("single read",      "cat ~/OneDrive/notes.md", 0),
    ("plain find",       "find ./src -name '*.py'", 0),
    # 큰따옴표 절단 회귀 — 클라우드 폴더 이름에는 공백이 흔하다
    # ("OneDrive - 기관명"), 그래서 따옴표 없이 쓰는 쪽이 오히려 드물다.
    ("find, 따옴표 OneDrive 경로",
     'find "/c/Users/me/OneDrive - Univ/store" -name "*.pdf"', 2),
    ("ls -R, 따옴표 경로", 'ls -R "/c/Users/me/OneDrive - Univ/data"', 2),
    ("따옴표 단일 읽기 (정상 통과)",
     'cat "/c/Users/me/OneDrive - Univ/notes.md"', 0),
]

# 실제 훅이 부르는 것은 개별 가드가 아니라 이 래퍼다. 개별 가드만 검사하면
# 체인이 끊겨도(래퍼가 payload 를 잘못 넘기거나 첫 차단에서 멈추지 못해도)
# 테스트는 계속 통과한다 — 배선을 재지 않은 검사는 발동을 증명하지 못한다.
# 가짜 크리덴셜은 런타임에 조립한다. secret_scan_guard 는 완성된 문자열을
# 받아야 발동하지만, 소스에 연속된 토큰을 적어두면 doctor 의 SENTINEL 스캔이
# 이 파일 자체를 유출로 잡는다(실측). 스캔 예외 목록에 파일을 추가하는 쪽은
# 답이 아니다 — 그러면 이 파일에 들어온 진짜 유출도 영원히 안 잡힌다.
_FAKE_SK_TOKEN = "sk-" + "a1b2c3d4e5" * 3

CHAINED_CASES = [
    ("secret: secrets.json 읽기", "Read",
     {"file_path": "/home/me/.claude/secrets.json"}, 2),
    ("secret: sk- 토큰", "Bash",
     {"command": f"curl -H 'x: {_FAKE_SK_TOKEN}'"}, 2),
    ("secret: 플레이스홀더는 통과", "Bash",
     {"command": "export API_KEY=your_api_key_here"}, 0),
    ("git: force push, 따옴표 뒤", "Bash",
     {"command": 'git commit -m "wip" && git push --force origin main'}, 2),
    ("delete: rm -rf, 따옴표 cd 뒤", "Bash",
     {"command": 'cd "/c/Users/me/My Project" && rm -rf build'}, 2),
    ("cloud: find, 따옴표 OneDrive", "Bash",
     {"command": 'find "/c/Users/me/OneDrive - Univ" -name "*.docx"'}, 2),
    ("정상: git log", "Bash", {"command": "git log --oneline -5"}, 0),
    ("정상: 일반 파일 읽기", "Read", {"file_path": "/home/me/project/README.md"}, 0),
    ("정상: 한 줄 python -c", "Bash",
     {"command": 'python -c "import sys; print(sys.version)"'}, 0),
]


def run_chained(tool_name: str, tool_input: dict) -> int:
    """실제 훅 경로(_run_hooks_chained.sh)로 payload 를 통과시킨다."""
    payload = json.dumps({"tool_name": tool_name, "tool_input": tool_input},
                         ensure_ascii=False)
    proc = subprocess.run(
        ["sh", str(HOOKS / "_run_hooks_chained.sh")],
        input=payload, capture_output=True, text=True,
        encoding="utf-8", errors="replace", cwd=str(ROOT), timeout=120,
    )
    return proc.returncode


def chained_section() -> None:
    global _skip
    if not (HOOKS / "_run_hooks_chained.sh").is_file():
        print("\n[체인 실행 경로] SKIP — _run_hooks_chained.sh 없음")
        _skip += 1
        return
    print("\n[체인 실행 경로] _run_hooks_chained.sh (실제 훅이 부르는 진입점)")
    for label, tool, tin, want in CHAINED_CASES:
        got = run_chained(tool, tin)
        verb = "차단" if want == 2 else "통과"
        check(f"{verb}: {label}", got == want,
              f"기대 exit={want}, 실제 exit={got}  payload={tin!r}")


def section(title: str, guard: str, cases: list[tuple[str, str, int]],
            cwd: Path | None = None) -> None:
    global _skip
    if not (HOOKS / guard).is_file():
        print(f"\n[{title}] SKIP — {guard} 없음")
        _skip += 1
        return
    print(f"\n[{title}] {guard}")
    for label, cmd, want in cases:
        got = run_guard(guard, cmd, cwd)
        verb = "차단" if want == 2 else "통과"
        check(f"{verb}: {label}", got == want,
              f"기대 exit={want}, 실제 exit={got}  cmd={cmd!r}")


def main() -> int:
    print("hooks/ 안전가드 양방향 검증")
    print("=" * 60)

    # fork 케이스는 upstream remote 가 있는 저장소에서만 의미가 있다.
    # 임시 저장소를 만들어 실제 remote 를 붙여 재현한다 — 정규식만 보고
    # "잡을 것이다"라고 믿지 않기 위해서다.
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "forked"
        repo.mkdir()
        git_ok = shutil.which("git") is not None
        if git_ok:
            for args in (["init", "-q"],
                         ["remote", "add", "origin", "https://example.invalid/me/fork.git"],
                         ["remote", "add", "upstream", "https://example.invalid/them/orig.git"]):
                subprocess.run(["git", *args], cwd=str(repo),
                               capture_output=True, text=True)

        section("git 안전가드", "git_safety_guard.sh", GIT_CASES)

        if git_ok:
            print("\n[fork 보호] upstream remote 가 있는 저장소에서")
            fork_cases = [
                ("upstream push",        "git push upstream main", 2),
                ("gh pr without --repo", "gh pr create --title x --body y", 2),
                ("origin push (정상)",    "git push origin feature/x", 0),
                ("gh pr with --repo",    "gh pr create --repo me/fork --title x", 0),
            ]
            for label, cmd, want in fork_cases:
                got = run_guard("git_safety_guard.sh", cmd, repo)
                verb = "차단" if want == 2 else "통과"
                check(f"{verb}: {label}", got == want,
                      f"기대 exit={want}, 실제 exit={got}  cmd={cmd!r}")
        else:
            print("\n[fork 보호] SKIP — git 없음")

    section("삭제 안전가드", "destructive_delete_guard.sh", DELETE_CASES)
    section("클라우드 경로 가드", "cloud_path_guard.sh", CLOUD_CASES)
    chained_section()

    print("=" * 60)
    print(f"통과 {_pass} / 실패 {_fail}" + (f" / 스킵 {_skip}" if _skip else ""))
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
