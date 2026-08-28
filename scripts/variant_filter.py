#!/usr/bin/env python3
"""Combined variant pass/fail matrix generator - merges several QC checks into a single decision matrix.

Usage:
    python variant_filter.py --ddg ddg.csv --primer-qc primer.csv
    python variant_filter.py --ddg ddg.csv --primer-qc primer.csv --expression expr.csv --output matrix.csv

Import:
    from variant_filter import build_matrix
    matrix = build_matrix(ddg_file="ddg.csv", primer_qc_file="primer.csv")

Input file formats:
    ddg CSV: variant, ddG_fold, pass_fail (ddg_screen.py output)
    primer QC CSV: variant, pass (True/False) or pass_fail (PASS/FAIL)
    expression CSV: variant, expression_pass or pass (True/False)
"""
import argparse
import csv
import sys
from collections import Counter
from pathlib import Path
from typing import Optional


def _normalize_pass(value: str) -> Optional[bool]:
    """Normalize a pass value in various notations to bool."""
    if value is None:
        return None
    v = str(value).strip().upper()
    if v in ("PASS", "TRUE", "1", "YES", "T"):
        return True
    if v in ("FAIL", "FALSE", "0", "NO", "F"):
        return False
    return None


def _read_csv_as_dict(path: str, key_col: str = "variant") -> dict[str, dict]:
    """Read the CSV into a dict keyed by key_col."""
    result = {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = row.get(key_col, "").strip()
            if key:
                result[key] = {k: v.strip() for k, v in row.items()}
    return result


def _extract_pass(row: dict, candidates: list[str]) -> Optional[bool]:
    """Extract the pass value from a prioritized list of candidate columns."""
    for col in candidates:
        if col in row:
            return _normalize_pass(row[col])
    return None


def build_matrix(
    ddg_file: Optional[str] = None,
    primer_qc_file: Optional[str] = None,
    expression_file: Optional[str] = None,
) -> list[dict]:
    """Merge several QC sources into a per-variant pass/fail matrix.

    Args:
        ddg_file: path to the ddg_screen.py output CSV
        primer_qc_file: path to the primer QC result CSV
        expression_file: path to the expression prediction CSV

    Returns:
        a list of [{"variant", "ddg_pass", "primer_pass", "expression_pass",
          "overall_pass", "notes"}, ...]
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

    # collect the variant list from every source
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
            # a ddg file was given but this variant isn't in it — data missing
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

        # overall_pass: every check that was provided must be PASS (None = not evaluated, not treated as a pass)
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
    """Print summary statistics to stderr."""
    total = len(matrix)
    pass_count = sum(1 for r in matrix if r["overall_pass"] == "PASS")
    fail_count = total - pass_count

    print(f"\n=== variant filter summary ===", file=sys.stderr)
    print(f"total: {total}", file=sys.stderr)
    print(f"PASS: {pass_count} ({pass_count/total*100:.1f}%)" if total else "PASS: 0", file=sys.stderr)
    print(f"FAIL: {fail_count} ({fail_count/total*100:.1f}%)" if total else "FAIL: 0", file=sys.stderr)

    # break down failure reasons
    fail_notes = [r["notes"] for r in matrix if r["overall_pass"] == "FAIL" and r["notes"]]
    if fail_notes:
        reason_counter: Counter = Counter()
        for note in fail_notes:
            for reason in note.split("; "):
                if reason:
                    reason_counter[reason] += 1
        print("\nfailure reason breakdown:", file=sys.stderr)
        for reason, count in reason_counter.most_common():
            print(f"  {reason}: {count}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge several QC checks into a per-variant pass/fail matrix."
    )
    parser.add_argument("--ddg", default=None, metavar="FILE",
                        help="ddG result CSV (ddg_screen.py output)")
    parser.add_argument("--primer-qc", default=None, metavar="FILE",
                        help="primer QC result CSV")
    parser.add_argument("--expression", default=None, metavar="FILE",
                        help="expression prediction CSV")
    parser.add_argument("--output", "-o", default=None,
                        help="output matrix CSV path (default: variant_matrix.csv)")
    args = parser.parse_args()

    if not any([args.ddg, args.primer_qc, args.expression]):
        parser.error("at least one of --ddg, --primer-qc, --expression must be specified.")

    matrix = build_matrix(
        ddg_file=args.ddg,
        primer_qc_file=args.primer_qc,
        expression_file=args.expression,
    )

    if not matrix:
        print("No variants to process.", file=sys.stderr)
        sys.exit(1)

    output_path = args.output or "variant_matrix.csv"
    fieldnames = ["variant", "ddg_pass", "primer_pass", "expression_pass", "overall_pass", "notes"]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(matrix)

    _print_summary(matrix)
    print(f"\nSaved results to {output_path}.", file=sys.stderr)


if __name__ == "__main__":
    main()
