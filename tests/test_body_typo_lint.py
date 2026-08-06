#!/usr/bin/env python3
"""body_typo_lint.py 회귀 테스트 — MUST FLAG / MUST NOT FLAG 양방향.

실행: python tests/test_body_typo_lint.py   (exit 0 = 통과)

`skills/academic-term-rules/SKILL.md` §12/§12a/§12b 의 규칙을 먼저 읽고
"이 규칙이면 이건 잡혀야/잡히면 안 된다"로 케이스를 구성했다. 구현에 맞춰
케이스를 짜지 않는다 — 구현이 SKILL.md 와 어긋나면 구현 쪽을 고친다.

이 파일은 body_typo_lint.py 의 --self-test 로직을 정식 pytest 스타일 없이도
CI/수동 실행에서 exit code 로 판단할 수 있게 감싼 얇은 러너다. 실제 케이스와
판정 로직은 스크립트 자신의 self_test() 안에 있다(단일 소스 — 케이스를
이 파일과 스크립트 양쪽에 중복 유지하지 않기 위함).
"""
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "skills" / "manuscript-pipeline" / "scripts" / "body_typo_lint.py"

# body_typo_lint.py 자신이 import 시점에 UTF-8 stdout/stderr 가드를 거는 것에
# 맡긴다(모듈을 여기서 다시 감싸면 이중 래핑으로 이전 TextIOWrapper 가 닫혀
# "I/O operation on closed file" 이 나는 문제가 실측됨).
spec = importlib.util.spec_from_file_location("body_typo_lint", str(SCRIPT_PATH))
body_typo_lint = importlib.util.module_from_spec(spec)
sys.modules["body_typo_lint"] = body_typo_lint
spec.loader.exec_module(body_typo_lint)


def test_lint_text_directly() -> int:
    """self_test() 와 별개로, lint_text()/apply_auto_fix() 를 직접 두들겨서
    AUTO-FIXABLE 과 REVIEW-ONLY 가 서로 오염되지 않는지, --fix 가 REVIEW-ONLY
    를 절대 건드리지 않는지 추가로 검증한다 (SKILL.md §12a/§12b: FLAG-ONLY,
    자동 치환 절대 금지 — 이 계약을 코드 레벨에서 재확인)."""
    fails = 0

    # 1) REVIEW-ONLY 대상은 apply_auto_fix 이후에도 원문 그대로 남아 있어야 함
    text = "The result after conversion.Here was clear."
    fixed = body_typo_lint.apply_auto_fix(text)
    if "conversion.Here" not in fixed:
        print("FAIL  apply_auto_fix 가 REVIEW-ONLY(§12a) 대상을 건드림 — 절대 금지 위반")
        fails += 1
    else:
        print("PASS  apply_auto_fix 는 REVIEW-ONLY(§12a) 대상을 그대로 둔다")

    # 2) 코드펜스 내부는 AUTO-FIXABLE 대상이라도 apply_auto_fix 가 건드리면 안 됨
    text = "```\n50 ul in the fence\n```\n"
    fixed = body_typo_lint.apply_auto_fix(text)
    if "50 ul in the fence" not in fixed:
        print("FAIL  apply_auto_fix 가 코드펜스 내부를 건드림")
        fails += 1
    else:
        print("PASS  apply_auto_fix 는 코드펜스 내부를 건드리지 않는다")

    # 3) 화이트리스트로 걸러진 건수가 조용히 사라지지 않고 카운트됨
    # ("data.Rmd"의 확장자 dot 이 PUNCT_SPACE_FLAGS 후보로 매치되지만
    # §12a 파일명 화이트리스트에 걸려 REVIEW-ONLY 로 보고되지 않아야 하고,
    # 그 사실이 whitelisted_count 에는 남아 있어야 한다 — 조용히 숨기지 않기).
    text = "Raw file was data.Rmd for this run."
    result = body_typo_lint.lint_text(text)
    if result.whitelisted_count < 1:
        print("FAIL  화이트리스트로 걸러진 건수가 표시되지 않음(조용히 숨김 금지 위반)")
        fails += 1
    else:
        print(f"PASS  화이트리스트로 걸러진 REVIEW-ONLY 후보가 카운트됨 "
              f"({result.whitelisted_count}건)")

    return fails


def main() -> int:
    print("=== body_typo_lint.self_test() (SKILL.md §12/12a/12b 규칙 기반 MUST FLAG / MUST NOT FLAG) ===")
    ok = body_typo_lint.self_test()

    print("\n=== 추가 계약 검증 (apply_auto_fix 는 REVIEW-ONLY 를 절대 건드리지 않음 등) ===")
    extra_fails = test_lint_text_directly()

    all_ok = ok and extra_fails == 0
    print()
    print("전체 결과:", "ALL PASS" if all_ok else "SOME FAILURES")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
