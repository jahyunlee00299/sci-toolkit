#!/usr/bin/env python3
"""채택 스킬(외부 저장소에서 적응해 가져온 것)의 계약을 고정한다.

`analysis-code-testing` · `data-quality-checks` 는 wshobson/agents(MIT)의 유닛을
**베껴온 게 아니라 적응해서** 들여온 것이다. 적응이라는 말이 지켜지려면 세 가지가
사실이어야 하고, 셋 다 조용히 깨질 수 있는 종류다:

  1. **귀속** — MIT 는 저작권 고지 유지를 요구한다. NOTICE.md 의 표와 SKILL.md
     front matter 의 `upstream:` 둘 다 살아 있어야 한다. 스킬을 리팩터링하다
     front matter 를 갈아끼우면 라이선스 결함이 되는데, 아무 검사도 안 보고 있었다.
  2. **모델 중립** — 상류 유닛은 `model: sonnet` 같은 라우팅 필드를 달고 있다.
     이 저장소의 스킬은 모델 중립이라 그 필드가 넘어오면 안 된다. 다음에 상류에서
     뭔가 더 가져올 때 통째로 복사하면 딸려 들어오는 게 바로 이 필드다.
  3. **상류 잔재 없음** — 웹서비스/데이터웨어하우스 전용 도구(Great Expectations,
     dbt, freezegun, Airflow…)를 덜어내는 게 적응의 핵심이었다. 그 이름이 다시
     등장하면 "적응"이 "벤더링"으로 되돌아간 것이다.

실행:
    python tests/test_adopted_skills.py     # exit 0 = 통과
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

# 스킬 -> 상류 유닛 경로(NOTICE.md 표·front matter 와 대조할 값)
ADOPTED = {
    "analysis-code-testing":
        "plugins/python-development/skills/python-testing-patterns",
    "data-quality-checks":
        "plugins/data-engineering/skills/data-quality-frameworks",
}
UPSTREAM_REPO = "https://github.com/wshobson/agents"

# 상류에는 있었지만 여기로 넘어오면 안 되는 도구들. 덜어냈다는 사실을 고정한다.
#
# 이름의 **언급**이 아니라 **사용**을 잡는다. "상류는 Great Expectations 를 쓰지만
# 우리는 안 쓴다" 는 문장은 적응 내역을 남기는 것이라 남아 있어야 하고, 그것까지
# 실패로 치면 검사를 통과시키려고 유용한 문장을 지우게 된다(게이트를 약화시키는
# 전형적 경로). 그래서 import/설치/호출 형태만 잡는다 — 그것만이 의존이다.
VENDOR_USAGE = [
    (r"^\s*import\s+great_expectations", "import great_expectations"),
    (r"^\s*import\s+(dbt|airflow)\b", "import dbt/airflow"),
    (r"\bfrom\s+freezegun\s+import", "from freezegun import"),
    (r"@freeze_time\b", "@freeze_time 데코레이터"),
    (r"\bgx\.get_context\s*\(", "gx.get_context()"),
    (r"\bpip\s+install\s+(great_expectations|dbt-|apache-airflow|freezegun)",
     "pip install (웨어하우스/웹 전용 의존)"),
    (r"^\s*great_expectations\s+\w+", "great_expectations CLI 호출"),
]

# 모델/에이전트 라우팅 필드 — front matter 에 있으면 안 된다.
MODEL_FIELDS = ("model:", "agent-type:", "agent_type:", "subagent_type:")

_fail = 0
_pass = 0


def check(ok: bool, label: str, detail: str = "") -> None:
    global _fail, _pass
    if ok:
        _pass += 1
    else:
        _fail += 1
        print(f"  FAIL  {label}" + (f"\n        {detail}" if detail else ""))


def front_matter(text: str) -> str:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    return m.group(1) if m else ""


def main() -> int:
    print("채택 스킬 계약 검사 (귀속 · 모델 중립 · 상류 잔재)")
    print("=" * 60)

    notice = (ROOT / "NOTICE.md").read_text(encoding="utf-8")
    check(UPSTREAM_REPO in notice,
          "NOTICE.md 가 상류 저장소를 밝힌다",
          f"{UPSTREAM_REPO} 가 NOTICE.md 에 없다 — MIT 고지 요건")
    check("Seth Hobson" in notice,
          "NOTICE.md 가 상류 저작권자를 밝힌다",
          "MIT 는 저작권 고지 유지를 요구한다")

    for skill, upstream_path in ADOPTED.items():
        print(f"\n[{skill}]")
        d = ROOT / "skills" / skill
        f = d / "SKILL.md"
        if not f.is_file():
            check(False, "SKILL.md 존재", f"{f} 가 없다")
            continue
        check(True, "SKILL.md 존재")

        text = f.read_text(encoding="utf-8")
        fm = front_matter(text)

        check(fm.strip() != "", "front matter 가 있다")
        check(f"name: {skill}" in fm,
              "front matter name 이 폴더명과 같다",
              f"폴더={skill}, front matter 에 'name: {skill}' 없음")
        check("description:" in fm, "description 이 있다")

        # 1. 귀속
        check(UPSTREAM_REPO in fm,
              "front matter 가 상류를 밝힌다",
              "upstream: 줄이 사라졌다 — 적응 출처 추적 불가")
        check(upstream_path in fm,
              "front matter 가 상류 유닛 경로를 밝힌다",
              f"'{upstream_path}' 가 front matter 에 없다")
        check(upstream_path in notice,
              "NOTICE.md 표가 이 스킬의 상류 유닛을 적는다",
              f"'{upstream_path}' 가 NOTICE.md 에 없다")
        check(skill in notice,
              "NOTICE.md 표가 이 스킬 이름을 적는다")
        check("license:" in fm, "license 가 선언돼 있다",
              "NOTICE.md 는 SKILL.md 의 license 선언이 우선한다고 못박는다")

        # 2. 모델 중립
        for field in MODEL_FIELDS:
            check(field not in fm,
                  f"front matter 에 '{field}' 가 없다 (모델 중립)",
                  f"상류 라우팅 필드 '{field}' 가 딸려 들어왔다")

        # 3. 상류 잔재 — 사용(import/호출/설치)만 잡는다
        for pattern, label in VENDOR_USAGE:
            hit = re.search(pattern, text, re.M)
            check(hit is None,
                  f"상류 전용 의존을 쓰지 않는다: {label}",
                  f"'{hit.group(0).strip()}' 등장 — 적응이 아니라 벤더링으로 "
                  f"되돌아갔다" if hit else "")

        # 라우팅 배선: §0 이 이 스킬을 실제로 가리켜야 쓰인다
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        sec = re.search(r"^## 0\. Routing.*?(?=^## 1\.)", agents, re.S | re.M)
        check(sec is not None and f"`{skill}`" in sec.group(0),
              "AGENTS.md §0 라우팅 표가 이 스킬을 가리킨다",
              "표에 없으면 에이전트가 이 스킬을 고를 경로가 없다")

    print("\n" + "=" * 60)
    if _fail:
        print(f"FAIL — 통과 {_pass} / 실패 {_fail}")
        return 1
    print(f"ALL PASS — 검사 {_pass}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
