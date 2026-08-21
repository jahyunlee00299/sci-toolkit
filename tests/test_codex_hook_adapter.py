#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hooks/_codex_json_adapter.sh — exit-2 계약 → Codex JSON 계약 변환 회귀 테스트.

왜 이 테스트가 있어야 하나
--------------------------
2026-08-21 실측(issue #5, Codex CLI 0.147.0): Codex 는 PreToolUse 훅을
Claude Code 와 **같은 stdin 페이로드**로 발화시키지만, **exit code 계약은
지원하지 않는다.** 훅이 exit 2 + stderr 사유를 내도 명령은 그대로 실행된다.
Codex 가 실제로 차단하는 유일한 경로는 stdout 에

    {"decision":"block","reason":"..."}

를 내고 exit 0 하는 것이다.

이 폴더의 가드는 전부 exit 2 로 말한다. 그래서 어댑터가 없으면 가드는
"돌긴 도는데 차단은 안 되는" 상태가 된다 — 검사되지 않은 명령에 파란불을
주므로 가드가 아예 없는 것보다 나쁘다. 이슈 #5 가 열린 이유가 그것이다.

그러므로 이 테스트가 지키는 것은 어댑터의 코드가 아니라 **차단이 실제로
차단으로 번역되는가** 이다. 판정 기준을 "stdout 이 비어있지 않다" 가 아니라
"stdout 이 JSON 으로 파싱되고 decision 이 block 이다" 로 둔 이유: 사유 문자열에는
따옴표·백슬래시(Windows 경로)·줄바꿈이 일상적으로 들어가는데, 이스케이프가
깨지면 JSON 이 망가지고 Codex 는 decision 을 읽지 못한 채 **조용히 통과**시킨다.
즉 이스케이프 버그의 증상이 정확히 "차단이 허용으로 퇴화"다.
(실제로 개발 중 두 번 났다: ① 줄바꿈 sentinel 이 문자열 끝에 제어문자로 남음
 ② sed 패턴의 \001 이 octal escape 로 해석되지 않아 여러 줄이 붙어버림.)

Codex 없이 오프라인으로 돈다 — 어댑터는 순수 셸 스크립트이고, 가짜 가드로
세 가지 종료코드를 모두 재현할 수 있다.

계약:
  가드 exit 2  → stdout = {"decision":"block","reason":<가드 stderr>}, 어댑터 exit 0
  가드 exit 0  → block JSON 없음,                                      어댑터 exit 0
  그 외        → 허용(permissive) + stderr 경고,                        어댑터 exit 0
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
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ADAPTER = ROOT / "hooks" / "_codex_json_adapter.sh"

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


# Codex 가 실제로 넘기는 페이로드 형태 그대로(issue #5 캡처본에서 발췌).
# 어댑터는 이 내용을 해석하지 않고 가드에게 그대로 넘기기만 하면 된다.
PAYLOAD = json.dumps({
    "session_id": "01a02489-0000-0000-0000-000000000000",
    "turn_id": "01a02489-1111-1111-1111-111111111111",
    "transcript_path": "C:\\Users\\Example\\.codex\\sessions\\rollout.jsonl",
    "cwd": "C:\\Users\\Example\\project",
    "hook_event_name": "PreToolUse",
    "model": "gpt-5.6-sol",
    "permission_mode": "bypassPermissions",
    "tool_name": "Bash",
    "tool_input": {"command": "echo hooktest"},
    "tool_use_id": "exec-0001",
})

# 사유 문자열에 JSON 메타문자를 일부러 전부 넣는다: 큰따옴표, 백슬래시(Windows
# 경로), 비ASCII(가드들이 실제로 쓰는 em dash), 그리고 여러 줄.
TRICKY_REASON = (
    'BLOCK: fake_guard \u2014 refused: cmd "quoted arg" and C:\\Users\\x\n'
    "  second line of the reason"
)

FAKE_GUARDS = {
    "g_allow.sh": "#!/usr/bin/env sh\ncat > /dev/null\nexit 0\n",
    "g_block.sh": (
        "#!/usr/bin/env sh\n"
        "cat > /dev/null\n"
        'cat "$GUARD_REASON_FILE" >&2\n'
        "exit 2\n"
    ),
    "g_block_silent.sh": "#!/usr/bin/env sh\ncat > /dev/null\nexit 2\n",
    "g_crash.sh": (
        "#!/usr/bin/env sh\n"
        "cat > /dev/null\n"
        'echo "guard exploded" >&2\n'
        "exit 7\n"
    ),
}


def run_adapter(tmp: Path, guard: str,
                payload: str = PAYLOAD) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["GUARD_REASON_FILE"] = str(tmp / "reason.txt")
    return subprocess.run(
        ["sh", str(ADAPTER), str(tmp / guard)],
        input=payload, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=60, env=env,
    )


def parse_decision(stdout: str):
    """stdout 을 JSON 으로 읽는다. 실패하면 None — 그것이 곧 결함이다."""
    if not stdout.strip():
        return None
    try:
        return json.loads(stdout)
    except Exception:
        return None


def main() -> int:
    if not ADAPTER.is_file():
        print(f"FAIL — 어댑터 없음: {ADAPTER}")
        return 1
    if shutil.which("sh") is None:
        print("SKIP — sh 없음 (POSIX 셸이 없는 환경)")
        return 0

    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        for name, script in FAKE_GUARDS.items():
            p = tmpdir / name
            p.write_text(script, encoding="utf-8", newline="\n")
            p.chmod(0o755)
        (tmpdir / "reason.txt").write_text(TRICKY_REASON, encoding="utf-8",
                                           newline="\n")

        print("exit 2 (사유 있음) → Codex block JSON 으로 번역되는가")
        r = run_adapter(tmpdir, "g_block.sh")
        check("어댑터가 exit 0 으로 끝난다 (exit 2 를 그대로 전파하면 Codex 는 무시한다)",
              r.returncode == 0, f"exit={r.returncode}")
        d = parse_decision(r.stdout)
        check("stdout 이 유효한 JSON 이다 (깨지면 Codex 가 못 읽고 조용히 통과시킨다)",
              d is not None, f"stdout={r.stdout!r}")
        if d is not None:
            check('decision == "block"', d.get("decision") == "block",
                  f"got {d.get('decision')!r}")
            reason = d.get("reason", "")
            check("reason 이 비어있지 않다", bool(reason.strip()))
            check("reason 이 가드 stderr 를 담고 있다 (fake_guard)",
                  "fake_guard" in reason, f"reason={reason!r}")
            check("큰따옴표가 살아남는다", '"quoted arg"' in reason,
                  f"reason={reason!r}")
            check("백슬래시 경로가 살아남는다", "C:\\Users\\x" in reason,
                  f"reason={reason!r}")
            check("비ASCII(em dash)가 살아남는다", "\u2014" in reason,
                  f"reason={reason!r}")
            check("여러 줄 사유의 둘째 줄이 살아남는다",
                  "second line of the reason" in reason, f"reason={reason!r}")

        print("exit 2 (사유 없음) → 그래도 block 이어야 한다")
        r = run_adapter(tmpdir, "g_block_silent.sh")
        check("어댑터 exit 0", r.returncode == 0, f"exit={r.returncode}")
        d = parse_decision(r.stdout)
        check("stdout 이 유효한 JSON", d is not None, f"stdout={r.stdout!r}")
        if d is not None:
            check('사유가 없어도 decision == "block" (차단이 사유 부재로 무너지면 안 된다)',
                  d.get("decision") == "block", f"got {d.get('decision')!r}")
            check("대체 사유가 채워진다", bool(d.get("reason", "").strip()))

        print("exit 0 → block JSON 이 나오면 안 된다 (과차단 검사)")
        r = run_adapter(tmpdir, "g_allow.sh")
        check("어댑터 exit 0", r.returncode == 0, f"exit={r.returncode}")
        d = parse_decision(r.stdout)
        check("block 결정이 없다",
              d is None or d.get("decision") != "block", f"stdout={r.stdout!r}")

        print("그 외 종료코드 → 허용하되 조용하지 않게")
        r = run_adapter(tmpdir, "g_crash.sh")
        check("어댑터 exit 0 (깨진 가드가 모든 툴콜을 벽돌로 만들면 안 된다)",
              r.returncode == 0, f"exit={r.returncode}")
        d = parse_decision(r.stdout)
        check("block 결정이 없다",
              d is None or d.get("decision") != "block", f"stdout={r.stdout!r}")
        check("stderr 로 경고한다 (조용히 죽은 가드가 통과한 가드로 위장하면 안 된다)",
              "WARN" in r.stderr, f"stderr={r.stderr!r}")

        print("없는 가드 → 허용 + 경고 (부분 설치 트리를 벽돌로 만들지 않는다)")
        r = run_adapter(tmpdir, "g_does_not_exist.sh")
        check("어댑터 exit 0", r.returncode == 0, f"exit={r.returncode}")
        check("stderr 로 경고한다", "WARN" in r.stderr, f"stderr={r.stderr!r}")

    print("실제 가드와의 종단간 연결 (가짜가 아니라 동봉된 가드로)")
    real = ROOT / "hooks" / "git_safety_guard.sh"
    if real.is_file():
        # 이 문자열을 소스에 통째로 적으면 개발 머신의 세션 가드가 이 파일을
        # 다루는 것 자체를 막는다. 조각으로 조립한다.
        forbidden = "git " + "push --" + "force origin main"
        r = subprocess.run(
            ["sh", str(ADAPTER), str(real)],
            input=json.dumps({"tool_name": "Bash",
                              "tool_input": {"command": forbidden}}),
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=60,
        )
        check("실제 가드: 어댑터 exit 0", r.returncode == 0,
              f"exit={r.returncode}")
        d = parse_decision(r.stdout)
        check("실제 가드: stdout 이 유효한 JSON", d is not None,
              f"stdout={r.stdout!r}")
        if d is not None:
            check('실제 가드: decision == "block"',
                  d.get("decision") == "block", f"got {d!r}")
            check("실제 가드: reason 에 가드 이름이 들어있다",
                  "git_safety_guard" in d.get("reason", ""),
                  f"reason={d.get('reason')!r}")
    else:
        print("  SKIP  hooks/git_safety_guard.sh 없음")

    print("체인러너와의 연결 (통과해야 할 명령은 통과시킨다)")
    chain = ROOT / "hooks" / "_run_hooks_chained.sh"
    if chain.is_file():
        r = subprocess.run(
            ["sh", str(ADAPTER), str(chain)],
            input=json.dumps({"tool_name": "Bash",
                              "tool_input": {"command": "echo hello world"}}),
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=120,
        )
        check("체인러너: 어댑터 exit 0", r.returncode == 0,
              f"exit={r.returncode}")
        d = parse_decision(r.stdout)
        check("체인러너: 무해한 명령에 block 이 없다",
              d is None or d.get("decision") != "block", f"stdout={r.stdout!r}")
    else:
        print("  SKIP  hooks/_run_hooks_chained.sh 없음")

    print("=" * 60)
    print(f"통과 {_pass} / 실패 {_fail}")
    if _fail:
        print("\nexit-2 → JSON 번역이 깨지면 Codex 아래에서 가드는 "
              "'돌지만 차단하지 않는' 상태가 된다 (issue #5).")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
