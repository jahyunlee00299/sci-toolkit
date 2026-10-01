"""Prove + Refute for pipetting_checks.py: synthetic xlsx, no Excel required.

Run: python -m pytest tests/test_pipetting_checks.py -v
  or: python tests/test_pipetting_checks.py   (falls back to a manual runner)
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from openpyxl import Workbook

from pipetting_checks import (
    concentration_rederivation_check,
    leading_equals_guard,
    sampling_headroom_check,
    volume_closure_check,
)


def _make_workbook(tmp_path: Path) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "Reaction Matrix"
    # row 10: a clean, closed recipe -- uL components (C,E,F) sum exactly to 25.0
    ws["B10"] = 1000  # stock mM
    ws["C10"] = 2.5   # substrate uL
    ws["D10"] = 100.0  # sheet-stated final mM (not a volume -- excluded from closure cols)
    ws["E10"] = 5.0    # buffer uL
    ws["F10"] = 17.5   # DW uL
    ws["G10"] = "=SUM(C10:F10)"
    # row 11: broken closure -- uL components sum to 24.0, not 25.0
    ws["B11"] = 1000
    ws["C11"] = 2.5
    ws["D11"] = 100.0
    ws["E11"] = 5.0
    ws["F11"] = 16.5
    ws["G11"] = "=SUM(C11:F11)"

    ws2 = wb.create_sheet("Sampling & Fed")
    ws2["C10"] = 3  # 3 timepoints, 5 uL each -> headroom = 25 - 15 = 10
    ws2["C11"] = 6  # 6 timepoints -> headroom = 25 - 30 = -5 (violates min 0)

    wb.save(tmp_path)
    return tmp_path


def _make_leading_equals_workbook(tmp_path: Path) -> Path:
    """openpyxl always writes a value starting with '=' as a live formula
    (data_type 'f') -- it cannot itself produce the defect this guard exists
    to catch. The real defect (Excel storing a formula-looking string as text
    because the cell was Text-formatted when typed) is a raw-XML difference:
    <c t="str"><v>=B2*2</v></c> instead of <c><f>B2*2</f><v>...</v></c>. Patch
    the sheet XML directly after saving so the fixture matches what actually
    ships from Excel, not what openpyxl would ever write on its own.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "S1"
    ws["A1"] = "=B1*2"  # real formula -- must survive untouched
    ws["A2"] = "=B2*2"  # placeholder; XML-patched into a text cell below
    wb.save(tmp_path)

    with zipfile.ZipFile(tmp_path) as zin:
        data = {n: zin.read(n) for n in zin.namelist()}
    sheet_xml = data["xl/worksheets/sheet1.xml"].decode("utf-8")
    patched = sheet_xml.replace(
        "<c r=\"A2\"><f>B2*2</f><v></v></c>",
        "<c r=\"A2\" t=\"str\"><v>=B2*2</v></c>",
    )
    assert patched != sheet_xml, "fixture XML shape changed -- update this patch string"
    data["xl/worksheets/sheet1.xml"] = patched.encode("utf-8")
    with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, content in data.items():
            zout.writestr(name, content)
    return tmp_path


def test_volume_closure_flags_only_broken_row(tmp_path):
    path = _make_workbook(tmp_path / "wb.xlsx")
    # C,E,F are the uL components (substrate, buffer, DW); D holds the
    # sheet-stated mM concentration and is deliberately excluded -- a real
    # config would only ever list volume columns here.
    report = volume_closure_check(
        path, sheet="Reaction Matrix", component_cols=["C", "E", "F"],
        total_col="G", row_range=(10, 11), target_volume=25.0,
    )
    assert not report.ok
    cells = {f.cell for f in report.findings}
    assert "G11" in cells
    assert "G10" not in cells


def test_volume_closure_uncomputed_cell_is_reported_not_treated_as_zero(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.title = "S"
    ws["A1"] = "=1+1"  # formula, never opened in Excel -> cached value is None
    p = tmp_path / "uncomputed.xlsx"
    wb.save(p)
    report = volume_closure_check(
        p, sheet="S", component_cols=["A"], total_col="B", row_range=(1, 1), target_volume=2.0,
    )
    assert not report.ok
    assert any("uncomputed" in f.message for f in report.findings)


def test_concentration_rederivation_matches_and_mismatches(tmp_path):
    path = _make_workbook(tmp_path / "wb.xlsx")
    checks = [
        {"row": 10, "stock_col": "B", "vol_col": "C", "final_col": "D", "total_volume_uL": 25.0},
    ]
    report = concentration_rederivation_check(path, sheet="Reaction Matrix", checks=checks)
    assert report.ok  # 1000*2.5/25 == 100, matches D10 exactly

    wb = Workbook()
    ws = wb.active
    ws.title = "S"
    ws["B1"], ws["C1"], ws["D1"] = 1000, 2.5, 999.0  # sheet says 999, re-derivation says 100
    p = tmp_path / "mismatch.xlsx"
    wb.save(p)
    bad_report = concentration_rederivation_check(
        p, sheet="S", checks=[{"row": 1, "stock_col": "B", "vol_col": "C", "final_col": "D", "total_volume_uL": 25.0}],
    )
    assert not bad_report.ok


def test_sampling_headroom_flags_only_overdrawn_row(tmp_path):
    path = _make_workbook(tmp_path / "wb.xlsx")
    report = sampling_headroom_check(
        path, sheet="Sampling & Fed", total_volume_uL=25.0, sample_volume_uL=5.0,
        n_timepoints_col="C", row_range=(10, 11), min_headroom_uL=0.0,
    )
    assert not report.ok
    cells = {f.cell for f in report.findings}
    assert "C11" in cells
    assert "C10" not in cells


def test_leading_equals_guard_flags_text_formula_not_real_formula(tmp_path):
    path = _make_leading_equals_workbook(tmp_path / "leq.xlsx")
    report = leading_equals_guard(path, ["S1"])
    cells = {f.cell for f in report.findings}
    # A1 is a real formula (data_type 'f') -> must NOT be flagged.
    # A2's data_type falls back to openpyxl's default for a plain string
    # ('s') because it was never explicitly marked as a formula cell --
    # this is exactly the corruption pattern this guard exists to catch.
    assert "A2" in cells
    assert "A1" not in cells


def test_missing_sheet_is_reported_not_raised(tmp_path):
    path = _make_workbook(tmp_path / "wb.xlsx")
    report = volume_closure_check(
        path, sheet="Nonexistent", component_cols=["A"], total_col="B", row_range=(1, 1), target_volume=1.0,
    )
    assert not report.ok
    assert any("not found" in f.message for f in report.findings)


if __name__ == "__main__":
    import tempfile

    passed, failed = 0, 0
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        with tempfile.TemporaryDirectory() as d:
            try:
                t(Path(d))
                print(f"PASS {t.__name__}")
                passed += 1
            except AssertionError as e:
                print(f"FAIL {t.__name__}: {e}")
                failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
