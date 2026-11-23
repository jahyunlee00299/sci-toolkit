"""Pipetting Guide readability rules. SKILL.md 'Workbook readability rules' states them; this file
enforces them on a generated workbook so a later layout change cannot quietly undo them."""
import json
import subprocess
import sys
from pathlib import Path

from openpyxl import load_workbook

SK = Path(__file__).resolve().parent.parent
CFG = SK / "tests" / "fixtures" / "pipette_rules" / "synthetic_serial_x8.json"


def _guide(tmp_path):
    out = tmp_path / "g.xlsx"
    r = subprocess.run([sys.executable, str(SK / "reaction_matrix.py"), str(CFG), str(out), "--no-publish"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stdout[-1500:]
    return load_workbook(out)["Pipetting Guide"]


def _row_of(ws, prefix):
    return next(r for r in range(1, ws.max_row + 1) if str(ws.cell(r, 1).value or "").startswith(prefix))


def test_blocks_are_in_bench_order(tmp_path):
    ws = _guide(tmp_path)
    order = [_row_of(ws, p) for p in ("MM-A", "SUBSTRATE GROUPING", "TUBES TO PREPARE", "ENZYME PREPARATION",
                                      "PER-TUBE VOLUME BREAKDOWN")]
    assert order == sorted(order), order


def test_label_column_is_wide_enough(tmp_path):
    ws = _guide(tmp_path)
    assert ws.column_dimensions["A"].width >= 30 and ws.column_dimensions["C"].width >= 24


def test_one_row_per_tube(tmp_path):
    ws = _guide(tmp_path)
    n = len(json.loads(CFG.read_text(encoding="utf-8"))["conditions"])
    head = _row_of(ws, "TUBES TO PREPARE") + 1
    assert [ws.cell(head, c).value for c in range(1, 5)] == ["Tube", "Substrate group", "Condition", "Enzyme"]
    tubes = [ws.cell(head + 1 + i, 1).value for i in range(n)]
    assert tubes == [f"#{i}" for i in range(1, n + 1)]
    assert not any("]" in str(ws.cell(head + 1 + i, 4).value).split("]")[-1] for i in range(n))  # level not repeated


def test_substrate_groups_list_only_nonzero_components(tmp_path):
    ws = _guide(tmp_path)
    r = _row_of(ws, "SUBSTRATE GROUPING") + 2
    while str(ws.cell(r, 1).value or "").startswith("SM-"):
        comp = str(ws.cell(r, 3).value)
        assert "=0" not in comp and not any(part.strip().endswith(" 0") for part in comp.split(","))
        r += 1


def test_every_working_stock_row_says_how_to_mix(tmp_path):
    ws = _guide(tmp_path)
    hits = [(r, c) for r in range(1, ws.max_row + 1) for c in range(1, 12) if ws.cell(r, c).value == "How to mix"]
    assert hits
    for r, c in hits:
        mix = str(ws.cell(r + 1, c).value or "")
        assert " uL " in mix and "water" in mix and "->" in mix, mix
