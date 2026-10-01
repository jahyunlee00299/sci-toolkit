"""CLI: verify a pipetting-protocol workbook without opening Excel for every check.

Two-stage split (see pipetting_checks.py and excel_com_guard.py docstrings for
the why): stage 1 runs every pure-calculation check via openpyxl only; stage 2,
opt-in via --recalc, does exactly one Excel-COM round trip (full recalculation
+ error-cell scan) guarded by an external process timeout so a modal-dialog
hang cannot freeze the caller.

Usage:
    python verify_pipetting_workbook.py CONFIG.json [--recalc] [--timeout SEC]

CONFIG.json shape — see pipetting_checks.py function signatures for field
meaning; this file only wires them together:
{
    "xlsx_path": "<YOUR_WORKBOOK>.xlsx",
    "leading_equals_sheets": ["Reaction Matrix", "Pipetting Guide"],
    "volume_closure": {
        "sheet": "Reaction Matrix", "component_cols": ["C","D","E","F"],
        "total_col": "G", "row_range": [10, 25], "target_volume": 25.0
    },
    "concentration_rederivation": {
        "sheet": "Reaction Matrix",
        "checks": [{"row": 10, "stock_col": "B", "vol_col": "C", "final_col": "D", "total_volume_uL": 25.0}]
    },
    "sampling_headroom": {
        "sheet": "Sampling & Fed", "total_volume_uL": 25.0, "sample_volume_uL": 5.0,
        "n_timepoints_col": "C", "row_range": [10, 25], "min_headroom_uL": 0.0
    }
}
Any of the four check blocks may be omitted to skip that check.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from pipetting_checks import (
    CheckReport,
    concentration_rederivation_check,
    leading_equals_guard,
    sampling_headroom_check,
    volume_closure_check,
)


def run_stage1(config: dict) -> CheckReport:
    xlsx_path = Path(config["xlsx_path"])
    report = CheckReport()

    if "leading_equals_sheets" in config:
        report.merge(leading_equals_guard(xlsx_path, config["leading_equals_sheets"]))

    if "volume_closure" in config:
        vc = config["volume_closure"]
        report.merge(
            volume_closure_check(
                xlsx_path,
                sheet=vc["sheet"],
                component_cols=vc["component_cols"],
                total_col=vc["total_col"],
                row_range=tuple(vc["row_range"]),
                target_volume=vc["target_volume"],
                tolerance=vc.get("tolerance", 1e-6),
            )
        )

    if "concentration_rederivation" in config:
        cr = config["concentration_rederivation"]
        report.merge(
            concentration_rederivation_check(
                xlsx_path,
                sheet=cr["sheet"],
                checks=cr["checks"],
                tolerance_rel=cr.get("tolerance_rel", 1e-3),
            )
        )

    if "sampling_headroom" in config:
        sh = config["sampling_headroom"]
        report.merge(
            sampling_headroom_check(
                xlsx_path,
                sheet=sh["sheet"],
                total_volume_uL=sh["total_volume_uL"],
                sample_volume_uL=sh["sample_volume_uL"],
                n_timepoints_col=sh["n_timepoints_col"],
                row_range=tuple(sh["row_range"]),
                min_headroom_uL=sh.get("min_headroom_uL", 0.0),
            )
        )

    return report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("config", type=Path)
    ap.add_argument("--recalc", action="store_true", help="also run the Excel-COM recalc+error-scan stage (Windows only)")
    ap.add_argument("--timeout", type=int, default=300, help="seconds before the COM stage is force-killed (default 300)")
    args = ap.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))

    stage1 = run_stage1(config)
    result = {"stage1": stage1.to_dict()}

    if args.recalc:
        import excel_com_guard

        result["stage2_com_recalc"] = excel_com_guard.recalc_and_scan(config["xlsx_path"], timeout_sec=args.timeout)

    print(json.dumps(result, indent=2))

    stage2_failed = args.recalc and result.get("stage2_com_recalc", {}).get("status") not in ("success",)
    sys.exit(0 if stage1.ok and not stage2_failed else 2)


if __name__ == "__main__":
    main()
