#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
축소판 탐지기(capability_diff) 회귀 테스트.

왜 이 도구가 필요한가 (실측 사례):
  2026-06-27 PII 정화 작업이 런타임 스킬을 sanitize 하면서 `update_notion.py` 를
  15.9KB → 7.4KB 로 만들었다. 플레이스홀더로 치환된 게 아니라 **기능의 절반이
  사라진 축소판**이었다(briefing-log upsert, overview 갱신, 중복 정리 로직 소실).
  그런데 파일은 존재했고 exit code 는 0이었다. 그래서 weekly-briefing 자동화가
  4주 연속 무산출인 채로 아무도 몰랐다.

  일반 품질 비교(LLM judge)는 이걸 못 잡는다. 축소판도 "잘 쓰인 문서"로 보이기
  때문이다. 잡히는 유일한 방법은 **원본에 있던 능력이 새 버전에 있는가**를
  구조적으로 대조하는 것이다 — 그게 이 도구다.

계약:
  1. 원본에 있던 섹션(##/###)이 새 버전에서 사라지면 잡는다.
  2. 원본이 참조하던 스크립트/파일 경로가 사라지면 잡는다.
  3. 원본에 있던 코드펜스 명령(python x.py …)이 사라지면 잡는다.
  4. 크기가 임계 이상 줄면 경고한다(기본 30%).
  5. 이름만 바뀐 것(도메인 일반화)은 소실이 아니다 — 개수가 유지되면 통과.
     정화의 목적이 바로 이름 치환이므로, 여기서 오탐이 나면 도구가 쓸모없다.
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
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "capability_diff", ROOT / "scripts" / "capability_diff.py")
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules["capability_diff"] = _mod
_spec.loader.exec_module(_mod)

diff_capabilities = _mod.diff_capabilities

_fail = 0
_pass = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global _fail, _pass
    if cond:
        _pass += 1
        print(f"  PASS  {name}")
    else:
        _fail += 1
        print(f"  FAIL  {name}" + (f"  — {detail}" if detail else ""))


ORIGINAL = """---
name: demo
---
# Demo skill

## Setup
Run `python scripts/setup_env.py --check` first.

## Analysis
See `references/analysis_rules.md` for the decision tree.

```bash
python scripts/analyze.py --input data.csv
```

### Edge cases
Handle empty input.

## Reporting
Produces `out/report.html`.
"""


def main() -> int:
    print("축소판 탐지기 검증")
    print("=" * 60)

    # ── 1. 정상 정화: 이름만 바뀌고 능력은 그대로 ────────────────────────
    print("\n[정상 정화] 도메인 이름만 치환 — 소실 아님")
    sanitized = (ORIGINAL
                 .replace("data.csv", "input.csv")
                 .replace("Handle empty input.", "Handle an empty input file."))
    rep = diff_capabilities(ORIGINAL, sanitized)
    check("소실 0건으로 판정", not rep.lost_sections and not rep.lost_refs
          and not rep.lost_commands,
          f"오탐: sections={rep.lost_sections} refs={rep.lost_refs} cmds={rep.lost_commands}")
    check("축소 경고 없음", not rep.shrank, f"shrink_ratio={rep.shrink_ratio:.2f}")

    # ── 2. 섹션 소실 ────────────────────────────────────────────────────
    print("\n[섹션 소실] ## Reporting 통째 삭제")
    cut = ORIGINAL.split("## Reporting")[0]
    rep = diff_capabilities(ORIGINAL, cut)
    check("사라진 섹션을 잡음", "Reporting" in " ".join(rep.lost_sections),
          f"lost_sections={rep.lost_sections}")

    # ── 3. 참조 경로 소실 ───────────────────────────────────────────────
    print("\n[참조 소실] references/analysis_rules.md 참조 제거")
    noref = ORIGINAL.replace("See `references/analysis_rules.md` for the decision tree.",
                             "See the decision tree.")
    rep = diff_capabilities(ORIGINAL, noref)
    check("사라진 파일 참조를 잡음",
          any("analysis_rules" in r for r in rep.lost_refs),
          f"lost_refs={rep.lost_refs}")

    # ── 4. 실행 명령 소실 ───────────────────────────────────────────────
    print("\n[명령 소실] analyze.py 실행 블록 제거")
    nocmd = ORIGINAL.replace("python scripts/analyze.py --input data.csv", "(생략)")
    rep = diff_capabilities(ORIGINAL, nocmd)
    check("사라진 실행 명령을 잡음",
          any("analyze.py" in c for c in rep.lost_commands),
          f"lost_commands={rep.lost_commands}")

    # ── 5. 260727 유형: 크기 반토막 ─────────────────────────────────────
    print("\n[축소판] 내용 절반 소실 (260727 update_notion.py 유형)")
    half = "\n".join(ORIGINAL.splitlines()[: len(ORIGINAL.splitlines()) // 2])
    rep = diff_capabilities(ORIGINAL, half)
    check("축소를 경고함", rep.shrank, f"shrink_ratio={rep.shrink_ratio:.2f}")
    check("판정이 FAIL", not rep.ok, "축소판인데 ok=True")

    # ── 6. 확장은 문제 아님 ─────────────────────────────────────────────
    print("\n[확장] 내용이 늘어난 경우 — 통과해야 함")
    more = ORIGINAL + "\n## Troubleshooting\nCheck the log first.\n"
    rep = diff_capabilities(ORIGINAL, more)
    check("확장은 소실로 보지 않음", rep.ok,
          f"sections={rep.lost_sections} shrink={rep.shrink_ratio:.2f}")

    print("=" * 60)
    print(f"통과 {_pass} / 실패 {_fail}")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
