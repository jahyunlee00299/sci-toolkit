#!/usr/bin/env python3
"""
body_typo_lint.py — 본문 오타/공백 린터 (.md / .txt).

`skills/academic-term-rules/SKILL.md` §12·12a·12b 에 정의된 패턴의
enforcement side 다. 패턴/화이트리스트는 그 문서에서 그대로 옮긴 것이며,
이 스크립트가 임의로 새 규칙을 지어내지 않는다 — 규칙을 바꾸려면 먼저
SKILL.md 쪽을 고치고 그 사실을 함께 보고할 것.

두 등급:
  AUTO-FIXABLE (§12 TYPO_PATTERNS)
      안전한 1:1 기계 치환 (µL, mL, h, rpm, °C 앞 공백, NAD⁺ 등).
      --fix --output <새파일> 로 실제 치환본을 만들 수 있다. 원본은 절대
      덮어쓰지 않는다.
  REVIEW-ONLY (§12a PUNCT_SPACE_FLAGS + §12b COFACTOR_SPACE_FLAGS)
      문장부호/보조인자 기호 뒤 공백 누락. 사람이 확인해야 하며 이 스크립트는
      절대 자동 치환하지 않는다. 화이트리스트로 걸러진 오탐 후보는 조용히
      숨기지 않고 몇 건이 걸러졌는지 요약에 표시한다.

.docx 입력은 다루지 않는다 — 먼저
`skills/docx/scripts/manuscript_text.py --mode accept` 로 텍스트를 뽑으라고
안내만 한다 (그 스크립트가 이미 tracked-changes 를 올바르게 처리한다).

Usage:
    python body_typo_lint.py <file.md|file.txt>
    python body_typo_lint.py <file.md> --fix --output <new_file.md>
    python body_typo_lint.py <file.md> --strict     # REVIEW-ONLY 도 exit 1
    python body_typo_lint.py <file.md> --json
    python body_typo_lint.py --self-test
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Windows 기본 콘솔은 cp949 라서 한글/기호 출력에서 죽는다. UTF-8로 맞춘다.
# TextIOWrapper 대신 reconfigure — 래퍼는 원본 스트림을 소유해서,
# import 후 GC 되면 호출자의 stdout 까지 닫아버린다(실측).
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# 패턴 정의 — SKILL.md §12 / §12a / §12b 에서 그대로 옮김. 새 규칙을 여기서
# 지어내지 말 것. 바꿀 필요가 있으면 SKILL.md 를 먼저 고치고 보고할 것.
# --------------------------------------------------------------------------- #

# §12 TYPO_PATTERNS — AUTO-FIXABLE (안전한 1:1 기계 치환)
TYPO_PATTERNS: list[tuple[str, str]] = [
    (r"\bul\b", "µL"), (r"\buL\b", "µL"), (r"\buM\b", "µM"),
    (r"\bml\b", "mL"), (r"\bhr\b", "h"), (r"\bhrs\b", "h"), (r"\bRPM\b", "rpm"),
    (r"℃", "°C"), (r"(\d)°C", r"\1 °C"), (r"(\d)mM", r"\1 mM"),
    (r"n=(\d)", r"n = \1"), (r"mean ± standard deviation", "mean ± SD"),
    (r"pH (\d)-(\d)", r"pH \1–\2"), (r"(\d+)-(\d+) °C", r"\1–\2 °C"),
    # NADP 를 먼저 — "NAD+" 를 먼저 치환하면 "NADP+" 의 앞부분이 깨진다.
    # 뒤쪽 \b 없음: "+" 는 non-word 문자라, "NAD+ regeneration" 처럼 뒤에
    # 공백·구두점이 오는 실제 문장에서는 경계가 성립하지 않아 규칙이 죽는다
    # (SKILL.md §12 원본의 \bNAD\+\b 가 그랬다 — 실측 후 양쪽 모두 수정).
    (r"\bNADP\+", "NADP⁺"), (r"\bNAD\+(?!P)", "NAD⁺"),
    (r"supertanant", "supernatant"), (r"seperati", "separati"),
]

# §12a PUNCT_SPACE_FLAGS — REVIEW-ONLY (문장부호 뒤 공백 누락)
PUNCT_SPACE_FLAGS: list[tuple[str, str]] = [
    (r"\b([a-z]{2,})\.([A-Z][a-z]{2,})\b", "missing space after period"),
    (r"\b([a-z]{2,}),([A-Za-z]{2,})\b", "missing space after comma"),
    (r"\b([a-z]{2,});([A-Za-z]{2,})\b", "missing space after semicolon"),
    (r"\b([a-z]{2,}):([A-Za-z]{2,})\b", "missing space after colon"),
]

# §12a PUNCT_SPACE_WHITELIST — 겹치면 REVIEW-ONLY 판정에서 제외
PUNCT_SPACE_WHITELIST: list[str] = [
    r"\bn\.a\.", r"\be\.g\.", r"\bi\.e\.", r"\bs\.d\.", r"\bet al\.",
    r"\bvs\.", r"\bcf\.", r"\betc\.", r"\bca\.", r"\bviz\.",
    r"\bU\.S\.A\.", r"\bPh\.D\.", r"\b[A-Z]\.[A-Z]\.",
    r"\borcid\.org", r"\bdoi\.org", r"[a-z]+\.(com|org|net|edu)\b",
    # academic-term-rules SKILL.md §12a 의 같은 목록과 동기화할 것 — 한쪽만
    # 고치면 문서와 구현이 어긋난다.
    r"\.(jpe?g|png|tiff?|docx?|xlsx?|pdf|csv|py|json|[Rr]md|[Rr]proj|ipynb|ya?ml|toml)\b",
    r"\d\.\d",
]

# §12b COFACTOR_SPACE_FLAGS — REVIEW-ONLY (보조인자 기호/토큰 뒤 공백 누락)
COFACTOR_SPACE_FLAGS: list[tuple[str, str]] = [
    (r"\b(NAD\(?P?\)?[+⁺⁻]+)([a-z]{3,})\b", "missing space after cofactor charge symbol"),
    (r"\bNAD(P?H)([a-z]{3,})\b", "missing space after cofactor token"),
]

# §12b COFACTOR_SPACE_WHITELIST
COFACTOR_SPACE_WHITELIST: list[str] = [
    r"\bNAD\(?P?\)?H?[+⁺⁻]*-[a-z]",
]

REVIEW_FLAGS = PUNCT_SPACE_FLAGS + COFACTOR_SPACE_FLAGS
REVIEW_WHITELIST = PUNCT_SPACE_WHITELIST + COFACTOR_SPACE_WHITELIST

_TYPO_COMPILED = [(re.compile(p), repl) for p, repl in TYPO_PATTERNS]
_REVIEW_COMPILED = [(re.compile(p), label) for p, label in REVIEW_FLAGS]
_WHITELIST_COMPILED = [re.compile(p) for p in REVIEW_WHITELIST]


# --------------------------------------------------------------------------- #
# 코드펜스 / 인라인코드 / URL 제외 — 여기 오탐이 나면 아무도 안 쓴다
# --------------------------------------------------------------------------- #

_FENCE_RE = re.compile(r"^```")
_URL_RE = re.compile(r"https?://\S+")


def _mask_excluded_spans(line: str) -> tuple[str, list[tuple[int, int]]]:
    """인라인코드(`...`)와 URL 구간을 공백으로 마스킹한 문자열과, 원래
    (start, end) 스팬 목록을 반환한다. 마스킹은 오프셋을 보존하므로
    열 번호가 그대로 유효하다."""
    spans: list[tuple[int, int]] = []
    masked = list(line)

    for m in re.finditer(r"`[^`]*`", line):
        spans.append(m.span())
    for m in _URL_RE.finditer(line):
        spans.append(m.span())

    for start, end in spans:
        for i in range(start, end):
            masked[i] = " "
    return "".join(masked), spans


def _iter_scan_lines(text: str):
    """코드펜스(``` ... ```) 블록 전체를 건너뛰고, 남은 줄에 대해
    (1-based line number, 검사용으로 마스킹된 줄) 을 yield 한다."""
    in_fence = False
    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        if _FENCE_RE.match(raw_line.strip()):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        masked, _ = _mask_excluded_spans(raw_line)
        yield lineno, raw_line, masked


# --------------------------------------------------------------------------- #
# Finding 자료구조
# --------------------------------------------------------------------------- #

@dataclass
class Finding:
    grade: str          # "AUTO-FIXABLE" | "REVIEW-ONLY"
    line: int
    col: int             # 1-based
    current: str
    suggestion: str
    rule: str


@dataclass
class LintResult:
    findings: list[Finding] = field(default_factory=list)
    whitelisted_count: int = 0  # REVIEW-ONLY 후보 중 화이트리스트로 걸러진 건수


def _is_whitelisted(line: str, start: int, end: int) -> bool:
    """flagged span 이 화이트리스트 매치와 겹치면 True (overlap-check)."""
    for pat in _WHITELIST_COMPILED:
        for wm in pat.finditer(line):
            if wm.start() < end and start < wm.end():
                return True
    return False


def lint_text(text: str) -> LintResult:
    result = LintResult()

    for lineno, raw_line, masked in _iter_scan_lines(text):
        # AUTO-FIXABLE: §12 TYPO_PATTERNS
        for pattern, repl in _TYPO_COMPILED:
            for m in pattern.finditer(masked):
                # m.group(0) 에 pattern 을 재적용하면 \b 등 경계 앵커가 "잘라낸
                # 짧은 문자열" 기준으로 재평가되어 매치가 깨질 수 있다(실측:
                # \bNAD\+\b 는 "NAD+" 라는 4글자만 놓고 보면 끝의 \b 가 문자열
                # 끝에서 성립하지 않아 재매치 실패 -> 치환 안 됨). 대신 원본
                # 매치 스팬에 대해 expand() 로 그룹/백레퍼런스를 안전하게
                # 치환한다(정규식 재평가가 아니라 이미 찾은 매치 객체의 그룹을
                # repl 템플릿에 대입하는 방식이라 경계 문제가 없다).
                suggestion = m.expand(repl)
                result.findings.append(
                    Finding(
                        grade="AUTO-FIXABLE",
                        line=lineno,
                        col=m.start() + 1,
                        current=m.group(0),
                        suggestion=suggestion,
                        rule=f"TYPO_PATTERNS:{pattern.pattern}",
                    )
                )

        # REVIEW-ONLY: §12a + §12b
        for pattern, label in _REVIEW_COMPILED:
            for m in pattern.finditer(masked):
                if _is_whitelisted(masked, m.start(), m.end()):
                    result.whitelisted_count += 1
                    continue
                # 제안: 매치문자열 안에서 마지막 캡처그룹이 시작되는 지점(오프셋
                # 기준, group 텍스트 자체를 문자열로 재조립하지 않음)에 공백을
                # 삽입한다. 그룹 개수·순서가 패턴마다 달라도(§12a 는 2그룹 전체가
                # "부호+다음단어", §12b 토큰 패턴은 group(1)이 NAD 뒤 접미사만
                # 캡처) 항상 안전하게 동작한다.
                last_group_idx = len(m.groups())
                split_at = m.start(last_group_idx) - m.start()
                whole = m.group(0)
                suggestion = whole[:split_at] + " " + whole[split_at:]
                result.findings.append(
                    Finding(
                        grade="REVIEW-ONLY",
                        line=lineno,
                        col=m.start() + 1,
                        current=m.group(0),
                        suggestion=suggestion,
                        rule=label,
                    )
                )

    return result


def apply_auto_fix(text: str) -> str:
    """AUTO-FIXABLE(§12 TYPO_PATTERNS) 만 적용한 새 텍스트를 반환한다.
    코드펜스 블록 내부는 손대지 않는다. REVIEW-ONLY 는 절대 건드리지 않는다."""
    lines = text.splitlines(keepends=True)
    in_fence = False
    out_lines = []

    for raw_line in lines:
        stripped = raw_line.strip("\n").strip("\r")
        if _FENCE_RE.match(stripped.strip()):
            in_fence = not in_fence
            out_lines.append(raw_line)
            continue
        if in_fence:
            out_lines.append(raw_line)
            continue

        # 인라인코드/URL 구간은 원본 그대로 두고, 그 바깥에서만 치환한다.
        # 마스킹된 텍스트(제외구간이 공백으로 치환된 것)에서 매치 위치를 찾고,
        # 원본 문자열 조각을 그 위치에 대해서만 잘라 붙인다. lint_text() 와
        # 동일하게 m.expand(repl) 을 써서 \b 재평가로 매치가 깨지는 문제를
        # 피한다(리터럴 sub 재적용 버그, self-test 로 실측 확인됨).
        content = raw_line[: len(raw_line.rstrip("\n").rstrip("\r"))]
        eol = raw_line[len(content):]

        # 매 패턴 치환마다 오프셋이 바뀌므로, 매치 → 원본 문자열 재구성을
        # 왼쪽부터 순서대로 한 번에 수행한다(패턴 간에는 순차 재적용).
        new_content = content
        for pattern, repl in _TYPO_COMPILED:
            masked, spans = _mask_excluded_spans(new_content)

            def _in_excluded(pos: int) -> bool:
                return any(s <= pos < e for s, e in spans)

            pieces = []
            last_end = 0
            for m in pattern.finditer(masked):
                if _in_excluded(m.start()):
                    continue
                pieces.append(new_content[last_end : m.start()])
                pieces.append(m.expand(repl))
                last_end = m.end()
            pieces.append(new_content[last_end:])
            new_content = "".join(pieces)

        out_lines.append(new_content + eol)

    return "".join(out_lines)


# --------------------------------------------------------------------------- #
# 리포트 출력
# --------------------------------------------------------------------------- #

def _format_findings(findings: list[Finding], source_name: str, whitelisted: int) -> str:
    lines = [f"body_typo_lint report — {source_name}"]
    auto = [f for f in findings if f.grade == "AUTO-FIXABLE"]
    review = [f for f in findings if f.grade == "REVIEW-ONLY"]

    for f in sorted(findings, key=lambda x: (x.line, x.col)):
        lines.append(
            f"{source_name}:{f.line}:{f.col}  [{f.grade}] "
            f"{f.current!r} → {f.suggestion!r}  ({f.rule})"
        )

    lines.append("")
    lines.append(
        f"요약: AUTO-FIXABLE {len(auto)}건 / REVIEW-ONLY {len(review)}건 "
        f"(화이트리스트로 걸러진 REVIEW-ONLY 후보 {whitelisted}건 — 숨기지 않고 표시)"
    )
    if not findings:
        lines.append("문제 없음.")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Self-test — MUST FLAG / MUST NOT FLAG 양방향 (SKILL.md 규칙 기준)
# --------------------------------------------------------------------------- #

def self_test() -> bool:
    must_flag = [
        # \bul\b 는 "ul" 이 독립 토큰일 때만 매치한다(SKILL.md 원본 패턴 그대로).
        # 숫자에 바로 붙은 "50ul" 은 \b 가 성립하지 않아 대상이 아니다 — 실제
        # 동작 확인: re.findall(r'\bul\b', '50ul') == [].
        ("Volume was 50 ul total.", "AUTO-FIXABLE", "§12: ul -> µL (독립 토큰)"),
        ("Incubated at 37°C for 2 h.", "AUTO-FIXABLE", "§12: (digit)°C -> digit 공백°C"),
        ("Reported as n=3 replicates.", "AUTO-FIXABLE", "§12: n=(digit) -> n = digit"),
        # 아래 NAD+ 케이스들은 원래 SKILL.md §12 의 `\bNAD\+\b` 가 **전부 놓치던**
        # 형태다. "+" 는 non-word 문자라 뒤에 공백·구두점이 오면 \b 가 성립하지
        # 않기 때문이다(실측). 뒤쪽 \b 를 제거해 SKILL.md·구현 양쪽을 고쳤으므로,
        # 이 케이스들이 다시 놓쳐지면 그 회귀를 여기서 잡는다.
        ("Cofactor NAD+ was regenerated.", "AUTO-FIXABLE", "§12: NAD+ -> NAD⁺ (뒤에 공백)"),
        ("Measured the NAD+/NADH ratio.", "AUTO-FIXABLE", "§12: NAD+ -> NAD⁺ (뒤에 슬래시)"),
        ("An NAD+-dependent enzyme was used.", "AUTO-FIXABLE", "§12: 하이픈 수식어도 위첨자가 정답(§3)"),
        ("Added NADP+ to the buffer.", "AUTO-FIXABLE", "§12: NADP+ -> NADP⁺ (NAD 보다 먼저 치환)"),
        ("The supertanant was collected.", "AUTO-FIXABLE", "§12: 오타 supertanant"),
        ("After conversion.Here we show yield.", "REVIEW-ONLY", "§12a: 마침표 뒤 공백 누락"),
        ("NAD⁺regeneration was observed.", "REVIEW-ONLY", "§12b: 보조인자 기호 뒤 공백 누락"),
        ("NADHoxidase activity increased.", "REVIEW-ONLY", "§12b: 보조인자 토큰 뒤 공백 누락"),
    ]
    must_not_flag = [
        ("```python\ndf.head()\n```", "코드펜스 내부는 검사 대상 아님"),
        ("See https://a.com/x.Here for details.", "URL 내부는 §12a 대상 아님"),
        ("As shown previously, e.g. in the prior study.", "§12a 화이트리스트: e.g."),
        ("This agrees with et al. reports.", "§12a 화이트리스트: et al."),
        ("The constant was 3.14 in this run.", "§12a 화이트리스트: 소수점(숫자.숫자)"),
        ("Data collected by J.H. Kim in 2024.", "§12a 화이트리스트: 이니셜 X.X."),
        ("Raw file was data.Rmd for this run.", "§12a 화이트리스트: 파일명 확장자"),
        ("The complex is NAD⁺-dependent for activity.", "§12b 화이트리스트: 하이픈 수식어"),
        ("Buffer contained NADPH regeneration mix.", "§12b: 이미 공백 있음 — 매치 자체가 안 됨"),
    ]

    all_pass = True
    print("=== MUST FLAG ===")
    for text, expected_grade, why in must_flag:
        result = lint_text(text)
        got_grades = {f.grade for f in result.findings}
        ok = expected_grade in got_grades
        status = "PASS" if ok else "FAIL"
        if not ok:
            all_pass = False
        print(f"  [{status}] {text[:55]!r}  (기대: {expected_grade} — {why})")
        if not ok:
            print(f"        실제 findings: {[(f.grade, f.current) for f in result.findings]}")

    print("\n=== MUST NOT FLAG ===")
    for text, why in must_not_flag:
        result = lint_text(text)
        ok = len(result.findings) == 0
        status = "PASS" if ok else "FAIL"
        if not ok:
            all_pass = False
        print(f"  [{status}] {text[:55]!r}  ({why})")
        if not ok:
            print(f"        오탐: {[(f.grade, f.current, f.rule) for f in result.findings]}")

    print()
    print("self-test 결과:", "ALL PASS" if all_pass else "SOME FAILURES")
    return all_pass


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "본문 오타/공백 린터 (.md/.txt). "
            "SKILL.md §12/§12a/§12b enforcement side. "
            ".docx 는 skills/docx/scripts/manuscript_text.py --mode accept 로 "
            "먼저 텍스트를 뽑아서 넘길 것 (이 스크립트가 직접 처리하지 않음)."
        )
    )
    parser.add_argument("file", nargs="?", help=".md 또는 .txt 파일 경로")
    parser.add_argument("--fix", action="store_true", help="AUTO-FIXABLE 항목을 실제로 치환")
    parser.add_argument("--output", help="--fix 결과를 쓸 새 파일 경로 (원본 덮어쓰기 금지)")
    parser.add_argument("--strict", action="store_true", help="REVIEW-ONLY 도 exit 1 로 취급")
    parser.add_argument("--json", action="store_true", help="JSON 출력")
    parser.add_argument("--self-test", action="store_true", help="내장 회귀 테스트 실행")
    args = parser.parse_args(argv)

    if args.self_test:
        ok = self_test()
        return 0 if ok else 1

    if not args.file:
        parser.print_help()
        return 0

    path = Path(args.file)
    if not path.exists():
        print(f"ERROR: 파일을 찾을 수 없음: {path}", file=sys.stderr)
        return 2

    if path.suffix.lower() == ".docx":
        print(
            "ERROR: .docx 는 이 스크립트가 직접 처리하지 않습니다.\n"
            "  먼저 다음을 실행해 텍스트를 뽑으세요:\n"
            "    python skills/docx/scripts/manuscript_text.py "
            f"{path} --mode accept\n"
            "  (tracked-changes 를 올바르게 반영한 최종본을 뽑는 SSOT 스크립트입니다.)",
            file=sys.stderr,
        )
        return 2

    text = path.read_text(encoding="utf-8", errors="replace")

    if args.fix:
        if not args.output:
            print("ERROR: --fix 는 --output <새파일> 과 함께 써야 합니다 (원본 덮어쓰기 금지).",
                  file=sys.stderr)
            return 2
        out_path = Path(args.output)
        if out_path.resolve() == path.resolve():
            print("ERROR: --output 은 원본과 다른 경로여야 합니다 (원본 덮어쓰기 금지).",
                  file=sys.stderr)
            return 2
        fixed_text = apply_auto_fix(text)
        out_path.write_text(fixed_text, encoding="utf-8", newline="\n")
        # --fix 이후 잔여 상태를 새 파일 기준으로 다시 보고한다.
        remaining = lint_text(fixed_text)
        remaining_auto = [f for f in remaining.findings if f.grade == "AUTO-FIXABLE"]
        print(f"WROTE {out_path} (원본 {path} 은 변경하지 않음)")
        print(f"적용된 AUTO-FIXABLE: {len([f for f in lint_text(text).findings if f.grade == 'AUTO-FIXABLE'])}건")
        if remaining_auto:
            print(f"경고: --fix 후에도 AUTO-FIXABLE {len(remaining_auto)}건이 남아있음 (겹침/재귀 패턴 확인 필요)")
        if remaining.findings:
            print()
            print(_format_findings(remaining.findings, str(out_path), remaining.whitelisted_count))
        return 0

    result = lint_text(text)
    auto = [f for f in result.findings if f.grade == "AUTO-FIXABLE"]
    review = [f for f in result.findings if f.grade == "REVIEW-ONLY"]

    if args.json:
        payload = {
            "file": str(path),
            "findings": [
                {
                    "grade": f.grade,
                    "line": f.line,
                    "col": f.col,
                    "current": f.current,
                    "suggestion": f.suggestion,
                    "rule": f.rule,
                }
                for f in result.findings
            ],
            "summary": {
                "auto_fixable": len(auto),
                "review_only": len(review),
                "whitelisted_filtered": result.whitelisted_count,
            },
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(_format_findings(result.findings, str(path), result.whitelisted_count))

    if auto:
        return 1
    if review and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
