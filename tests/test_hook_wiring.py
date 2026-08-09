#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hooks/ 폴더의 가드 스크립트 ↔ _run_hooks_chained.sh DEFAULT_GUARDS 배선 정합성.

_run_hooks_chained.sh 는 실행할 가드 목록을 셸 변수(DEFAULT_GUARDS)에 하드코딩
한다. hooks/ 에 새 *_guard.sh 를 추가해도 그 목록에 이름을 넣지 않으면 파일은
존재하되 절대 호출되지 않는다 — doctor.py 의 check_hooks_config() 는 hooks.json
이 유효한 JSON인지만 보고, 체인 내부의 이 배선까지는 보지 않는다. 반대 방향도
같은 무게로 잰다: DEFAULT_GUARDS 가 존재하지 않는 파일을 가리키면 체인러너가
매 호출마다 "guard not found" 경고를 내면서 그 가드는 아무것도 막지 못한다
(_run_hooks_chained.sh 자체는 누락 파일을 조용히 건너뛰도록 설계돼 있어, 이
정적 검사가 없으면 이 gap 은 실행해봐야만 드러난다).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

ROOT = Path(__file__).resolve().parent.parent
HOOKS = ROOT / "hooks"
CHAIN = HOOKS / "_run_hooks_chained.sh"

# 체인러너 자신과 payload 파싱 헬퍼는 "가드"가 아니다 — DEFAULT_GUARDS 에 절대
# 나열되지 않는 것이 맞으므로 정합성 비교 대상에서 뺀다.
NON_GUARD_FILES = {"_run_hooks_chained.sh", "_payload_fields.sh"}


def declared_guards(chain_text: str) -> set[str]:
    m = re.search(r'DEFAULT_GUARDS="([^"]*)"', chain_text)
    if not m:
        return set()
    return set(m.group(1).split())


def actual_guard_files() -> set[str]:
    return {p.name for p in HOOKS.glob("*_guard.sh")} - NON_GUARD_FILES


def main() -> int:
    if not CHAIN.is_file():
        print("SKIP — hooks/_run_hooks_chained.sh 없음")
        return 0

    chain_text = CHAIN.read_text(encoding="utf-8")
    declared = declared_guards(chain_text)
    actual = actual_guard_files()

    if not declared:
        print("FAIL — _run_hooks_chained.sh 에서 DEFAULT_GUARDS 를 못 찾음"
              " (변수명이 바뀌었거나 형식이 달라짐 — 이 테스트를 갱신할 것)")
        return 1

    orphaned = actual - declared  # 파일은 있는데 체인이 절대 안 부름
    dangling = declared - actual  # 체인이 부르는데 파일이 없음

    fail = 0
    print(f"확인 대상: hooks/*_guard.sh {len(actual)}개 ↔ DEFAULT_GUARDS {len(declared)}개")

    if orphaned:
        fail += 1
        print(f"  FAIL  hooks/ 에 있지만 DEFAULT_GUARDS 에 없음(절대 실행 안 됨): "
              f"{', '.join(sorted(orphaned))}")
    if dangling:
        fail += 1
        print(f"  FAIL  DEFAULT_GUARDS 가 가리키지만 파일이 없음: "
              f"{', '.join(sorted(dangling))}")

    if not fail:
        print("  OK    모든 가드 파일이 배선돼 있고, 배선된 이름이 전부 존재함")

    print("=" * 60)
    print(f"통과 {1 if not fail else 0} / 실패 {fail}")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
