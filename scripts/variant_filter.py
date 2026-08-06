#!/usr/bin/env python3
"""변이체 통합 pass/fail 매트릭스 생성기 - 여러 QC 체크를 단일 결정 매트릭스로 결합.

사용법:
    python variant_filter.py --ddg ddg.csv --primer-qc primer.csv
    python variant_filter.py --ddg ddg.csv --primer-qc primer.csv --expression expr.csv --output matrix.csv

임포트:
    from variant_filter import build_matrix
    matrix = build_matrix(ddg_file="ddg.csv", primer_qc_file="primer.csv")

입력 파일 형식:
    ddg CSV: variant, ddG_fold, pass_fail (ddg_screen.py 출력)
    primer QC CSV: variant, pass (True/False) 또는 pass_fail (PASS/FAIL)
    expression CSV: variant, expression_pass 또는 pass (True/False)
"""
import argparse
import csv
import sys
from collections import Counter
from pathlib import Path
from typing import Optional


def _normalize_pass(value: str) -> Optional[bool]:
    """다양한 표현의 pass 값을 bool로 정규화."""
    if value is None:
        return None
    v = str(value).strip().upper()
    if v in ("PASS", "TRUE", "1", "YES", "T"):
        return True
    if v in ("FAIL", "FALSE", "0", "NO", "F"):
        return False
    return None


def _read_csv_as_dict(path: str, key_col: str = "variant") -> dict[str, dict]:
    """CSV를 key_col 기준 딕셔너리로 읽는다."""
    result = {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = row.get(key_col, "").strip()
            if key:
                result[key] = {k: v.strip() for k, v in row.items()}
    return result


def _extract_pass(row: dict, candidates: list[str]) -> Optional[bool]:
    """우선순위 컬럼 후보에서 pass 값을 추출한다."""
    for col in candidates:
        if col in row:
            return _normalize_pass(row[col])
    return None


def build_matrix(
    ddg_file: Optional[str] = None,
    primer_qc_file: Optional[str] = None,
    expression_file: Optional[str] = None,
) -> list[dict]:
    """여러 QC 소스를 통합해 변이체별 pass/fail 매트릭스를 생성한다.

    Args:
        ddg_file: ddg_screen.py 출력 CSV 경로
        primer_qc_file: primer QC 결과 CSV 경로
        expression_file: 발현 예측 CSV 경로

    Returns:
        [{"variant", "ddg_pass", "primer_pass", "expression_pass",
          "overall_pass", "notes"}, ...] 목록
    """
    ddg_data: dict[str, dict] = {}
    primer_data: dict[str, dict] = {}
    expr_data: dict[str, dict] = {}

    if ddg_file:
        ddg_data = _read_csv_as_dict(ddg_file)
    if primer_qc_file:
        primer_data = _read_csv_as_dict(primer_qc_file)
    if expression_file:
        expr_data = _read_csv_as_dict(expression_file)

    # 모든 소스에서 변이체 목록 수집
    all_variants = sorted(
        set(ddg_data) | set(primer_data) | set(expr_data)
    )

    if not all_variants:
        return []

    matrix = []
    for variant in all_variants:
        ddg_pass: Optional[bool] = None
        primer_pass: Optional[bool] = None
        expr_pass: Optional[bool] = None
        fail_reasons = []

        if ddg_data and variant in ddg_data:
            ddg_pass = _extract_pass(
                ddg_data[variant], ["pass_fail", "pass", "ddg_pass"]
            )
        elif ddg_file:
            # ddg 파일이 제공됐지만 이 변이체가 없으면 데이터 누락
            ddg_pass = None

        if primer_data and variant in primer_data:
            primer_pass = _extract_pass(
                primer_data[variant], ["pass", "pass_fail", "primer_pass"]
            )
        elif primer_qc_file:
            primer_pass = None

        if expr_data and variant in expr_data:
            expr_pass = _extract_pass(
                expr_data[variant], ["expression_pass", "pass", "pass_fail"]
            )
        elif expression_file:
            expr_pass = None

        # overall_pass: 제공된 체크 모두 PASS여야 함 (None은 미평가 = 통과로 간주하지 않음)
        checks = []
        if ddg_file:
            checks.append(("ddG", ddg_pass))
        if primer_qc_file:
            checks.append(("primer", primer_pass))
        if expression_file:
            checks.append(("expression", expr_pass))

        overall_pass = True
        for name, val in checks:
            if val is False:
                overall_pass = False
                fail_reasons.append(f"{name}_fail")
            elif val is None:
                overall_pass = False
                fail_reasons.append(f"{name}_missing")

        notes = "; ".join(fail_reasons) if fail_reasons else ""

        matrix.append({
            "variant": variant,
            "ddg_pass": "" if ddg_pass is None else ("PASS" if ddg_pass else "FAIL"),
            "primer_pass": "" if primer_pass is None else ("PASS" if primer_pass else "FAIL"),
            "expression_pass": "" if expr_pass is None else ("PASS" if expr_pass else "FAIL"),
            "overall_pass": "PASS" if overall_pass else "FAIL",
            "notes": notes,
        })

    return matrix


def _print_summary(matrix: list[dict]) -> None:
    """요약 통계를 stderr에 출력한다."""
    total = len(matrix)
    pass_count = sum(1 for r in matrix if r["overall_pass"] == "PASS")
    fail_count = total - pass_count

    print(f"\n=== 변이체 필터 요약 ===", file=sys.stderr)
    print(f"전체: {total}개", file=sys.stderr)
    print(f"PASS: {pass_count}개 ({pass_count/total*100:.1f}%)" if total else "PASS: 0개", file=sys.stderr)
    print(f"FAIL: {fail_count}개 ({fail_count/total*100:.1f}%)" if total else "FAIL: 0개", file=sys.stderr)

    # 실패 원인 분석
    fail_notes = [r["notes"] for r in matrix if r["overall_pass"] == "FAIL" and r["notes"]]
    if fail_notes:
        reason_counter: Counter = Counter()
        for note in fail_notes:
            for reason in note.split("; "):
                if reason:
                    reason_counter[reason] += 1
        print("\n실패 원인 분류:", file=sys.stderr)
        for reason, count in reason_counter.most_common():
            print(f"  {reason}: {count}개", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="여러 QC 체크를 통합해 변이체별 pass/fail 매트릭스를 생성한다."
    )
    parser.add_argument("--ddg", default=None, metavar="FILE",
                        help="ddG 결과 CSV (ddg_screen.py 출력)")
    parser.add_argument("--primer-qc", default=None, metavar="FILE",
                        help="primer QC 결과 CSV")
    parser.add_argument("--expression", default=None, metavar="FILE",
                        help="발현 예측 CSV")
    parser.add_argument("--output", "-o", default=None,
                        help="출력 매트릭스 CSV 경로 (기본값: variant_matrix.csv)")
    args = parser.parse_args()

    if not any([args.ddg, args.primer_qc, args.expression]):
        parser.error("--ddg, --primer-qc, --expression 중 하나 이상을 지정해야 합니다.")

    matrix = build_matrix(
        ddg_file=args.ddg,
        primer_qc_file=args.primer_qc,
        expression_file=args.expression,
    )

    if not matrix:
        print("처리할 변이체가 없습니다.", file=sys.stderr)
        sys.exit(1)

    output_path = args.output or "variant_matrix.csv"
    fieldnames = ["variant", "ddg_pass", "primer_pass", "expression_pass", "overall_pass", "notes"]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(matrix)

    _print_summary(matrix)
    print(f"\n결과를 {output_path}에 저장했습니다.", file=sys.stderr)


if __name__ == "__main__":
    main()
