#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""spec-driven-research-dev 스킬이 4단계 흐름을 실제로 들고 있는지 고정한다.

이 스킬은 스크립트가 아니라 **프롬프트+템플릿**이다. 실행 가능한 코드가 없으니
"돌려보면 안다"가 성립하지 않는다 — 대신 이 흐름을 흐름이게 만드는 구조가
남아 있는지를 검사한다. github/spec-kit 에서 가져온 것이 바로 그 구조이고,
문서를 손대다 한 단계가 빠지면 나머지 세 단계는 조용히 무의미해진다
(plan 은 spec 을 읽고, tasks 는 plan 을 읽고, implement 는 tasks 를 읽는다).

계약:
  1. 4개 단계(specify·plan·tasks·implement)가 SKILL.md 에 전부 있다.
  2. 4개 템플릿 파일이 실존한다 — SKILL.md 가 "복사해서 쓰라"고 지시하므로,
     없으면 사용자는 지시를 따르다 실패한다.
  3. spec 템플릿은 구현 세부를 금지하는 규칙을 들고 있다. 이 규칙이 이 흐름의
     핵심이라(Phase 1 이 기술선택을 배제해야 합의되지 않은 것이 드러난다),
     사라지면 spec 은 그냥 설계문서가 되고 채택할 이유가 없어진다.
  4. tasks 템플릿의 체크리스트 형식([ID] [P] [Story] + 파일경로)이 살아 있다.
     ID 나 파일경로가 빠진 task 는 실행도 체크오프도 정직하게 할 수 없다.
  5. 상류 출처(github/spec-kit)와 라이선스가 NOTICE.md 에 기록돼 있다 —
     MIT 는 재사용을 허용하되 저작자 표시를 조건으로 걸기 때문이다.
  6. AGENTS.md §0 이 이 스킬을 가리킨다. 배선되지 않은 스킬은 존재하지 않는
     것과 같다(라우팅 표가 에이전트의 진입점이다).

실행:
    python tests/test_spec_driven_workflow.py           # exit 0 = 통과
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Windows 기본 콘솔은 cp949 라서 한글/기호 출력에서 죽는다. UTF-8로 맞춘다.
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = ROOT / "skills" / "spec-driven-research-dev"
SKILL_MD = SKILL_DIR / "SKILL.md"
TEMPLATES = SKILL_DIR / "templates"

PHASES = ("specify", "plan", "tasks", "implement")
TEMPLATE_FILES = (
    "spec-template.md",
    "plan-template.md",
    "tasks-template.md",
    "checklist-template.md",
)


def check_skill_md(failures: list[str]) -> str:
    if not SKILL_MD.is_file():
        failures.append(f"SKILL.md 가 없다 — {SKILL_MD.relative_to(ROOT)}")
        return ""
    text = SKILL_MD.read_text(encoding="utf-8")

    # 1) 4단계가 모두 언급되는가
    missing = [p for p in PHASES if p not in text.lower()]
    if missing:
        failures.append(
            f"SKILL.md 에 단계 누락: {missing} — 4단계가 서로를 읽는 구조라 "
            f"한 단계가 빠지면 나머지가 근거를 잃는다")

    # 각 단계가 제목으로 존재하는가 (본문에 단어만 스쳐 지나간 것과 구분)
    headings = re.findall(r"^##+\s*(.+)$", text, re.M)
    joined = " | ".join(headings).lower()
    no_heading = [p for p in PHASES if p not in joined]
    if no_heading:
        failures.append(
            f"SKILL.md 에 단계 제목이 없다: {no_heading} — 단어로만 등장하면 "
            f"에이전트가 그 단계를 수행 단위로 인식하지 못한다")
    return text


def check_templates(failures: list[str]) -> None:
    for name in TEMPLATE_FILES:
        p = TEMPLATES / name
        if not p.is_file():
            failures.append(
                f"템플릿 없음: templates/{name} — SKILL.md 가 복사해서 쓰라고 "
                f"지시하므로, 없으면 지시를 따르다 실패한다")

    spec_t = TEMPLATES / "spec-template.md"
    if spec_t.is_file():
        t = spec_t.read_text(encoding="utf-8")
        # 3) 구현 세부 금지 규칙 — 이 흐름의 핵심 제약
        if not re.search(r"No language, library, file layout", t):
            failures.append(
                "spec 템플릿에서 '구현 세부 금지' 규칙이 사라졌다 — Phase 1 이 "
                "기술선택을 배제해야 합의되지 않은 것이 드러난다. 이 규칙이 없으면 "
                "spec 은 그냥 설계문서이고 이 스킬을 쓸 이유가 없다")
        for section in ("Success Criteria", "Assumptions", "Independent Test"):
            if section not in t:
                failures.append(f"spec 템플릿에 '{section}' 섹션이 없다")

    tasks_t = TEMPLATES / "tasks-template.md"
    if tasks_t.is_file():
        t = tasks_t.read_text(encoding="utf-8")
        # 4) 체크리스트 형식이 살아 있는가
        if not re.search(r"-\s*\[\s*\]\s*T###", t):
            failures.append(
                "tasks 템플릿에 `- [ ] T###` 형식 정의가 없다 — ID 없는 task 는 "
                "실행 순서도 체크오프도 정직하게 관리되지 않는다")
        if "exact path" not in t and "파일 경로" not in t:
            failures.append(
                "tasks 템플릿이 '정확한 파일 경로'를 요구하지 않는다 — 경로 없는 "
                "task 는 실행할 수도 완료를 확인할 수도 없다")
        for marker in ("[P]", "[US#]"):
            if marker not in t:
                failures.append(f"tasks 템플릿에 {marker} 마커 설명이 없다")


def check_attribution(failures: list[str]) -> None:
    notice = ROOT / "NOTICE.md"
    if not notice.is_file():
        failures.append("NOTICE.md 가 없다")
        return
    t = notice.read_text(encoding="utf-8")
    if "github/spec-kit" not in t:
        failures.append(
            "NOTICE.md 에 상류 출처(github/spec-kit)가 없다 — MIT 는 재사용을 "
            "허용하되 저작자 표시를 조건으로 건다. 표시 누락은 라이선스 위반이다")
    # 출처 문단 안에 MIT 표기가 함께 있어야 의미가 있다
    m = re.search(r"github/spec-kit.{0,400}", t, re.S)
    if m and "MIT" not in m.group(0):
        failures.append("NOTICE.md 의 spec-kit 항목에 라이선스(MIT) 표기가 없다")


def check_wiring(failures: list[str]) -> None:
    agents = ROOT / "AGENTS.md"
    if not agents.is_file():
        failures.append("AGENTS.md 가 없다")
        return
    text = agents.read_text(encoding="utf-8")
    m = re.search(r"^## 0\. Routing.*?(?=^## 1\.)", text, re.S | re.M)
    if not m:
        failures.append("AGENTS.md 에 §0 라우팅 섹션이 없다")
        return
    if "spec-driven-research-dev" not in m.group(0):
        failures.append(
            "AGENTS.md §0 라우팅 표가 spec-driven-research-dev 를 가리키지 않는다 — "
            "배선되지 않은 스킬은 존재하지 않는 것과 같다(§0 이 진입점이다)")

    catalog = ROOT / "config" / "catalog.json"
    if catalog.is_file():
        import json
        d = json.loads(catalog.read_text(encoding="utf-8"))
        if "spec-driven-research-dev" not in d.get("skills", {}):
            failures.append(
                "config/catalog.json 에 등록되지 않았다 — 설치기가 이 스킬을 "
                "설치 대상으로 보지 못한다")


def main() -> int:
    failures: list[str] = []
    check_skill_md(failures)
    check_templates(failures)
    check_attribution(failures)
    check_wiring(failures)

    if failures:
        print(f"FAIL — spec-driven-research-dev 계약 위반 {len(failures)}건")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("ALL PASS — 4단계 흐름·템플릿 4종·출처 표시·§0 배선 모두 확인")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
