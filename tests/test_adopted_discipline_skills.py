#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""도입한 '개발 규율' 스킬이 규율의 알맹이를 실제로 담고 있는지 검사한다.

실행: python tests/test_adopted_discipline_skills.py   (exit 0 = 통과)

왜 이 파일이 필요한가
---------------------
`test_skill_references.py` 는 참조가 실존하는지, `test_doc_counts.py` 는 개수가
맞는지 본다. 둘 다 통과하면서도 스킬 본문이 **빈 껍데기**가 될 수 있다 — 제목과
frontmatter 만 남기고 규율 조항을 지워도 두 검사는 초록불이다.

이 저장소가 도입한 규율 스킬은 각각 "에이전트가 반복적으로 저지르는 실패 하나"를
막으려고 존재한다. 그 실패를 막는 문장이 사라지면 스킬은 이름만 남는다. 그래서
여기서는 **각 스킬이 존재 이유가 되는 조항을 실제로 담고 있는가**를 본다.

조항을 문서에서 빼려면 이 검사도 함께 고쳐야 한다 — 그 강제가 목적이다.
검사를 약화시켜 통과시키는 것은 규율을 지우는 것과 같다(AGENTS.md §0 규칙 2).

각 항목은 (설명, 그 조항을 나타내는 표현들) 이고, 표현 중 **하나라도** 있으면
통과다. 표현을 여러 개 두는 것은 문장을 다듬을 여지를 남기기 위함이지, 검사를
느슨하게 하려는 것이 아니다 — 조항 자체가 사라지면 전부 사라진다.
"""
from __future__ import annotations

import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"

# 스킬 이름 -> [(조항 설명, [표현 후보...]), ...]
REQUIRED_SUBSTANCE: dict[str, list[tuple[str, list[str]]]] = {
    "debugging-loop": [
        ("가설보다 재현 루프가 먼저라는 순서 규정",
         ["before you form", "before forming any theory",
          "before a red-capable command exists",
          "before** proposing a cause", "loop first, a theory second"]),
        ("루프가 '죽지 않음'이 아니라 사용자가 말한 증상을 검증해야 한다",
         ["red-capable", "asserts the *symptom", "symptom the\nuser described",
          "not a signal"]),
        ("가설은 3~5개, 각각 반증가능해야 한다",
         ["3–5 ranked hypotheses", "3-5 ranked hypotheses", "falsifiable"]),
        ("디버그 출력에 태그를 붙여 회수 가능하게 한다",
         ["[DBG-", "[DEBUG-", "Tag every debug"]),
        ("최소화한 재현이 아니라 원본 시나리오로 다시 확인한다",
         ["un-minimised", "un-minimized", "original (un-minimis"]),
        ("회귀 테스트를 걸 올바른 seam 이 없으면 그 사실 자체가 발견이다",
         ["no correct seam exists, that is itself the finding",
          "no correct seam exists, that itself is the finding"]),
    ],
    "test-quality": [
        ("기대값을 구현과 같은 방식으로 재계산하면 안 된다는 조항",
         ["recomputed the way the code computes it",
          "passes by construction"]),
        ("기대값의 정당한 출처를 명시한다(손계산·계측기·문헌 등 독립 출처)",
         ["come from outside the implementation",
          "hand-worked example", "independent source"]),
        ("내부 결합 테스트의 판별 기준 — 리팩토링에서 깨지는가",
         ["breaks when you refactor", "coupled to internal",
          "Coupling to internals"]),
        ("테스트를 일괄 선작성하면 상상한 동작을 검증하게 된다",
         ["imagined", "vertical slices"]),
        ("seam 을 먼저 합의하고 가장 높은 seam 을 고른다",
         ["Agree the seams before", "highest seam"]),
        ("탐지력 판정 질문 — 그럴듯한 오답에도 통과하는가",
         ["plausible wrong answer"]),
        ("수렴한 fit 은 통과한 테스트가 아니다 (합성 ground truth 로 파라미터 회수)",
         ["converged fit is not a passing test", "known synthetic ground truth",
          "synthetic ground truth"]),
    ],
    "code-quality": [
        ("리뷰는 Standards / Spec 2축을 분리해서 본다",
         ["Review two axes separately", "two axes separately"]),
        ("축을 가로질러 findings 를 재정렬하지 않는다",
         ["do not\nrerank findings across the axes",
          "rerank findings across the axes"]),
        ("Spec 축은 누락·요청하지 않은 범위 확대·틀린 구현을 구분해 보고한다",
         ["scope creep"]),
        ("비교 기준점을 먼저 고정하고 diff 가 비어있지 않은지 확인한다",
         ["pin the comparison point", "diff is non-empty"]),
        ("Spec 이 없으면 없다고 말하고 임의로 대체하지 않는다",
         ["report the Spec axis as unavailable",
          "no written spec"]),
    ],
}

# 스킬이 반드시 가져야 할 frontmatter 필드
REQUIRED_FRONTMATTER = ("name:", "description:")


def check_skill(name: str, clauses: list[tuple[str, list[str]]]) -> list[str]:
    problems: list[str] = []
    path = SKILLS / name / "SKILL.md"
    if not path.is_file():
        return [f"{name}: SKILL.md 가 없다 — {path.relative_to(ROOT)}"]

    text = path.read_text(encoding="utf-8")

    if not text.startswith("---"):
        problems.append(f"{name}: frontmatter 가 없다 (--- 로 시작해야 한다)")
    else:
        head = text.split("---", 2)[1]
        for field in REQUIRED_FRONTMATTER:
            if field not in head:
                problems.append(f"{name}: frontmatter 에 {field} 가 없다")
        # 이름이 폴더명과 다르면 스킬이 로드되어도 다른 이름으로 잡힌다
        if f"name: {name}" not in head:
            problems.append(
                f"{name}: frontmatter 의 name 이 폴더명과 다르다")

    for label, candidates in clauses:
        if not any(c in text for c in candidates):
            problems.append(
                f"{name}: '{label}' 조항이 본문에서 사라졌다 "
                f"(찾은 표현 없음: {candidates[0]!r} 등 {len(candidates)}종)")
    return problems


def main() -> int:
    problems: list[str] = []
    checked = 0
    for name, clauses in REQUIRED_SUBSTANCE.items():
        problems += check_skill(name, clauses)
        checked += len(clauses) + len(REQUIRED_FRONTMATTER)

    if problems:
        print(f"FAIL — 도입 스킬의 규율 조항 누락 {len(problems)}건")
        for p in problems:
            print(f"  - {p}")
        print("\n조항을 의도적으로 바꿨다면 이 검사도 함께 고칠 것. "
              "검사만 지우면 스킬은 이름만 남는다.")
        return 1

    print(f"ALL PASS — 도입 스킬 {len(REQUIRED_SUBSTANCE)}종 · "
          f"조항 {checked}건이 본문에 실존한다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
