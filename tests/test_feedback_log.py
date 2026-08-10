#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
피드백 기록 채널 회귀 테스트.

이 도구의 계약에서 가장 중요한 것은 **설정 없이 동작한다**는 점이다.
토큰·계정·네트워크를 요구하는 순간 아무도 기록하지 않기 때문에, 그 성질이
깨졌는지를 여기서 지킨다.

계약:
  1. 필수 인자는 "무엇이 불편한가" 하나. 나머지 없이도 기록된다.
  2. 환경 정보(OS/Python)는 묻지 않고 자동으로 채워진다.
  3. 기록은 JSONL 한 줄 = 한 건. 한 줄이 깨져도 나머지는 읽힌다.
  4. 이슈 본문에는 출처(기록 ID·시각)가 반드시 들어간다 — 재현할 수 있어야 한다.
  5. export 는 --write 없이 아무것도 올리지 않는다(§9 draft-first).
"""
from __future__ import annotations

import sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

import argparse
import importlib.util
import json
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "feedback_log", ROOT / "scripts" / "feedback_log.py")
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules["feedback_log"] = _mod
_spec.loader.exec_module(_mod)

_fail = 0
_pass = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global _fail, _pass
    if cond:
        _pass += 1
        print(f"  PASS  {name}")
    else:
        _fail += 1
        print(f"  FAIL  {name}" + (f" — {detail}" if detail else ""))


def main() -> int:
    print("피드백 기록 채널 검증")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as td:
        # 실제 out/feedback.jsonl 을 건드리지 않도록 경로를 갈아끼운다.
        _mod.LOG_PATH = Path(td) / "feedback.jsonl"

        # ── 1. 최소 입력으로 기록 ───────────────────────────────────────
        print("\n[최소 입력] 설정 없이 한 줄만으로 기록")
        e = _mod.add_entry("표 편집이 자꾸 실패해요")
        check("기록이 만들어짐", bool(e.get("id")))
        check("파일에 쓰임", _mod.LOG_PATH.exists())
        check("환경이 자동으로 채워짐",
              bool(e["env"].get("os")) and bool(e["env"].get("python")),
              f"env={e['env']}")
        check("선택 항목은 비어 있어도 됨", e["skill"] is None and e["expected"] is None)

        # ── 2. 전체 입력 ────────────────────────────────────────────────
        print("\n[전체 입력] 아는 것을 모두 담았을 때")
        e2 = _mod.add_entry("셀 안에서 치환이 안 됨", kind="bug", skill="docx",
                            expected="셀 값이 바뀜", actual="무한루프")
        check("kind 가 반영됨", e2["kind"] == "bug")
        check("skill 이 반영됨", e2["skill"] == "docx")

        # ── 3. 읽기 ─────────────────────────────────────────────────────
        print("\n[읽기] JSONL 파싱")
        entries = _mod.read_entries()
        check("두 건 모두 읽힘", len(entries) == 2, f"len={len(entries)}")

        # 깨진 줄을 섞어도 나머지는 살아야 한다
        with _mod.LOG_PATH.open("a", encoding="utf-8") as f:
            f.write("{ 깨진 줄 아님 json\n")
        entries = _mod.read_entries()
        check("깨진 줄이 있어도 나머지는 읽힘", len(entries) == 2, f"len={len(entries)}")

        # ── 4. 이슈 본문 ────────────────────────────────────────────────
        print("\n[이슈 변환] 출처가 반드시 들어간다")
        title, body = _mod.to_issue(e2)
        check("제목에 스킬 스코프가 붙음", title.startswith("[docx]"), title)
        check("본문에 기록 ID 포함", e2["id"] in body)
        check("본문에 기대/실제 포함",
              "셀 값이 바뀜" in body and "무한루프" in body)
        check("본문에 환경 포함", "Python" in body)

        # 선택 항목이 없는 기록도 본문이 만들어져야 한다
        title1, body1 = _mod.to_issue(e)
        check("최소 기록도 본문 생성됨", bool(title1) and e["id"] in body1)

        # ── 5. exported 표시 ────────────────────────────────────────────
        print("\n[승격 표시] 올린 것은 다시 올리지 않는다")
        _mod.mark_exported({e2["id"]})
        after = {x["id"]: x for x in _mod.read_entries()}
        check("올린 건은 exported=True", after[e2["id"]]["exported"] is True)
        check("안 올린 건은 그대로", after[e["id"]]["exported"] is False)

        # ── 6. JSONL 형식 ───────────────────────────────────────────────
        print("\n[형식] 한 줄 = 한 건")
        lines = [l for l in _mod.LOG_PATH.read_text(encoding="utf-8").splitlines()
                 if l.strip()]
        parsed = 0
        for line in lines:
            try:
                json.loads(line)
                parsed += 1
            except json.JSONDecodeError:
                pass
        check("유효한 JSON 줄이 2건", parsed == 2, f"parsed={parsed}/{len(lines)}")

        # ── 7. 담당자 = 발견자 (mock, 실제 네트워크 없음) ─────────────────
        print("\n[담당자] 이슈는 발견자에게 할당된다 — 관리자에게 몰지 않는다")

        def _run_export(no_assignee=False, assignee=None, fail_lookup=None):
            # fail_lookup: None(성공) / "exception"(일반 예외) /
            # "systemexit"(실제 github_connector.http()가 실패 시 내는
            # 방식 — sys.exit() 는 BaseException 서브클래스라 일반
            # except Exception 으로는 안 잡힌다. 적대검증 260810에서
            # 발견된 실제 실패 경로를 그대로 재현한다).
            calls = []

            def fake_http(method, url, token, data=None):
                calls.append((method, url, data))
                if url.endswith("/user"):
                    if fail_lookup == "exception":
                        raise RuntimeError("network down")
                    if fail_lookup == "systemexit":
                        sys.exit("[오류] 네트워크 연결을 확인하세요: mocked offline")
                    return {"login": "finder-account"}
                return {"number": 1}

            mock_gh = mock.MagicMock()
            mock_gh.http = fake_http
            mock_gh.API_ROOT = "https://api.github.com"
            mock_cred = mock.MagicMock()
            mock_cred.get = lambda *a: "fake-token"

            with mock.patch.dict(sys.modules,
                                  {"github_connector": mock_gh, "_credentials": mock_cred}):
                args = argparse.Namespace(
                    github=True, repo="owner/name", label=None,
                    assignee=assignee, no_assignee=no_assignee, write=True, approve=False)
                _mod.cmd_export(args)
            issue_calls = [c for c in calls if c[1].endswith("/issues")]
            return calls, issue_calls

        # 기본값: 지정하지 않으면 /user 로 조회한 본인 계정에 할당
        # (이전 섹션의 미출력 기록도 함께 올라갈 수 있으므로 "전부"를 검사한다 —
        #  개수가 아니라 모든 이슈가 같은 담당자를 받았는지가 계약이다.)
        e3 = _mod.add_entry("담당자 테스트 — 기본값")
        calls, issue_calls = _run_export()
        check("기본값: /user 조회 호출됨", any(c[1].endswith("/user") for c in calls))
        check("기본값: 올라간 이슈 전부가 발견자(본인)에게 할당됨",
              len(issue_calls) >= 1 and
              all(c[2].get("assignees") == ["finder-account"] for c in issue_calls),
              f"issue_calls={issue_calls}")

        # --no-assignee: 아무에게도 할당하지 않음, /user 호출도 생략(불필요한 API 호출 방지)
        e4 = _mod.add_entry("담당자 테스트 — no-assignee")
        calls, issue_calls = _run_export(no_assignee=True)
        check("--no-assignee: /user 호출 생략", not any(c[1].endswith("/user") for c in calls))
        check("--no-assignee: assignees 필드가 아예 없음",
              len(issue_calls) == 1 and "assignees" not in issue_calls[0][2])

        # --assignee 명시: 그 값을 그대로 쓰고, 본인 조회는 하지 않음
        e5 = _mod.add_entry("담당자 테스트 — 명시적 지정")
        calls, issue_calls = _run_export(assignee="someone-else")
        check("--assignee 명시: /user 조회 생략", not any(c[1].endswith("/user") for c in calls))
        check("--assignee 명시: 지정한 사람으로 할당",
              len(issue_calls) == 1 and issue_calls[0][2].get("assignees") == ["someone-else"])

        # /user 조회가 실패해도(오프라인 등) 이슈 생성 자체는 죽지 않아야 한다
        e6 = _mod.add_entry("담당자 테스트 — 조회 실패(일반 예외)")
        calls, issue_calls = _run_export(fail_lookup="exception")
        check("일반 예외: /user 조회 실패해도 이슈는 만들어짐(할당 없이)",
              len(issue_calls) == 1 and "assignees" not in issue_calls[0][2])

        # 실제 github_connector.http() 가 쓰는 실패 방식(sys.exit → SystemExit)도
        # 같은 계약을 지켜야 한다 — 이게 260810 적대검증에서 실제로 뚫려 있던 경로.
        e7 = _mod.add_entry("담당자 테스트 — 조회 실패(SystemExit, 실제 실패 경로)")
        calls, issue_calls = _run_export(fail_lookup="systemexit")
        check("SystemExit: /user 조회 실패해도 이슈는 만들어짐(할당 없이), export가 죽지 않음",
              len(issue_calls) == 1 and "assignees" not in issue_calls[0][2],
              f"issue_calls={issue_calls}")

    print("=" * 60)
    print(f"통과 {_pass} / 실패 {_fail}")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
