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

import importlib.util
import json
import tempfile
from pathlib import Path

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

    print("=" * 60)
    print(f"통과 {_pass} / 실패 {_fail}")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
