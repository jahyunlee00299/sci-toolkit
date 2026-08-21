#!/usr/bin/env python3
"""spec-first / test-first 스킬이 **문서로만 존재하지 않게** 붙들어 둔다.

이 두 스킬은 스크립트가 아니라 규율이다. 실행되는 코드가 없으므로, 망가져도
어떤 테스트도 빨간불을 내지 않는다 — 파일이 지워지거나, §0 라우팅에서 빠지거나,
승인 게이트 문장이 편집으로 사라져도 doctor 는 초록불이다. 그것이 "배선 없는
기능"의 전형적인 죽는 방식이라, 여기서 배선과 핵심 규칙 문장을 실측한다.

검사 항목 (각각 한 번은 실제로 깨져 본 축이다):

1. 두 스킬 폴더와 SKILL.md 가 실존한다.
2. front matter 에 name·description·license 가 있고, name 이 폴더명과 같다.
   (name 이 어긋나면 에이전트가 부르는 이름과 설치되는 이름이 갈라진다)
3. AGENTS.md §0 라우팅 표가 두 스킬을 모두 가리킨다. §0 은 에이전트의 진입점
   이라, 여기 없으면 스킬은 설치돼 있어도 호출되지 않는다.
4. config/catalog.json 에 등록돼 있다 (미등록 = 설치기가 배포하지 않음).
5. **채택의 핵심 규칙이 본문에 남아 있다.** 상류(obra/superpowers)에서 가져온
   이유가 바로 이 문장들이다 — 승인 게이트, iron law, 플레이스홀더 금지,
   red 확인 의무. 요약하다가 이것들이 빠지면 스킬은 톤만 남고 규율은 사라진다.
6. 상류 출처가 NOTICE.md 에 기록돼 있다 (MIT 귀속 의무).

실행:
    python tests/test_development_discipline.py     # exit 0 = 통과
"""
from __future__ import annotations

import json
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
SKILLS = ("spec-first-development", "test-first-development")
UPSTREAM = "github.com/obra/superpowers"

# 스킬별로 "이 문장이 사라지면 채택이 무의미해지는" 규칙들.
# 정규식은 서식(굵게·줄바꿈)에 둔감하도록 느슨하게 두되, 규칙의 **뜻**을 담은
# 낱말은 반드시 요구한다. 문구를 다듬는 것은 자유지만, 규칙을 지우는 것은 아니다.
REQUIRED_RULES: dict[str, list[tuple[str, str]]] = {
    "spec-first-development": [
        ("승인 게이트 (코드 전 승인 필수)",
         r"no implementation code until.{0,80}approved|"
         r"until you have told the requester.{0,120}said yes"),
        ("3경로 분류 (spike/bounded/architectural)",
         r"spike.{0,400}bounded.{0,400}architectural"),
        ("래칫 단방향 (경로는 올라가기만)",
         r"ratchet is one-way|step \*?up\*? a path|nothing ever steps\s*\n?\s*down"),
        ("플레이스홀더 금지",
         r"no placeholders|TBD.{0,60}TODO"),
        ("스펙/계획 자체검토",
         r"self-review"),
    ],
    "test-first-development": [
        ("iron law (테스트 없이 구현 코드 금지)",
         r"no implementation code without a failing test first"),
        ("RED 확인 의무 (실패를 눈으로 볼 것)",
         r"watch it fail|verify red"),
        ("먼저 쓴 코드는 삭제",
         r"delete means delete"),
        ("최소 구현 (GREEN)",
         r"minimal code|minimal implementation"),
        ("테스트를 약화시켜 통과시키지 말 것",
         r"weaken|fix the code, not the test"),
        ("수치 연구코드용 테스트 종류",
         r"known-answer"),
    ],
}


def front_matter(text: str) -> dict[str, str]:
    """--- ... --- 블록의 최상위 key: value 만 얕게 읽는다 (YAML 의존 없이)."""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if not m:
        return {}
    out: dict[str, str] = {}
    for line in m.group(1).splitlines():
        km = re.match(r"^([a-z_]+):\s*(.*)$", line)
        if km:
            out[km.group(1)] = km.group(2).strip()
    return out


def main() -> int:
    failures: list[str] = []
    checked = 0

    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    m = re.search(r"^## 0\. Routing.*?(?=^## 1\.)", agents, re.S | re.M)
    routing = m.group(0) if m else ""
    if not routing:
        failures.append("AGENTS.md 에 '## 0. Routing' 섹션이 없다")

    try:
        catalog = json.loads(
            (ROOT / "config" / "catalog.json").read_text(encoding="utf-8"))
        cat_skills = catalog.get("skills", {})
    except (OSError, ValueError) as exc:
        cat_skills = {}
        failures.append(f"config/catalog.json 을 읽을 수 없다 — {exc}")

    for skill in SKILLS:
        path = ROOT / "skills" / skill / "SKILL.md"

        checked += 1
        if not path.is_file():
            failures.append(f"{skill}: SKILL.md 가 없다 — {path}")
            continue
        text = path.read_text(encoding="utf-8")

        fm = front_matter(text)
        for key in ("name", "description", "license"):
            checked += 1
            if not fm.get(key):
                failures.append(f"{skill}: front matter 에 '{key}' 가 없다")
        checked += 1
        if fm.get("name") and fm["name"] != skill:
            failures.append(
                f"{skill}: front matter name='{fm['name']}' 이 폴더명과 다르다 "
                "— 에이전트가 부르는 이름과 설치되는 이름이 갈라진다")

        checked += 1
        if f"`{skill}`" not in routing:
            failures.append(
                f"{skill}: AGENTS.md §0 라우팅 표가 가리키지 않는다 "
                "— §0 은 진입점이라, 여기 없으면 설치돼 있어도 호출되지 않는다")

        checked += 1
        if skill not in cat_skills:
            failures.append(
                f"{skill}: config/catalog.json 의 skills 에 없다 "
                "— 설치기가 배포하지 않는다")

        low = text.lower()
        for label, pattern in REQUIRED_RULES[skill]:
            checked += 1
            if not re.search(pattern, low, re.S):
                failures.append(
                    f"{skill}: 핵심 규칙이 본문에서 사라졌다 — {label}")

    checked += 1
    notice = (ROOT / "NOTICE.md").read_text(encoding="utf-8")
    if UPSTREAM not in notice:
        failures.append(
            f"NOTICE.md 에 상류 출처({UPSTREAM})가 없다 — MIT 귀속 의무")
    checked += 1
    if not all(s in notice for s in SKILLS):
        failures.append(
            "NOTICE.md 가 두 스킬을 상류 파생물로 명시하지 않는다")

    if failures:
        print(f"FAIL — 개발 규율 스킬 배선/규칙 {len(failures)}건 이상")
        for f in failures:
            print(f"  - {f}")
        return 1

    print(f"ALL PASS — 개발 규율 스킬 {len(SKILLS)}종, 검사 {checked}건 "
          "(배선 · front matter · 핵심 규칙 · 귀속)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
