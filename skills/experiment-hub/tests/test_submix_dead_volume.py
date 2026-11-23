"""Sub-mix dead volume, printed sub-mix recipes and per-row enzyme totals.

Three defects that no validate_config check flagged (0 FAIL):

  1. A sub-mix was made for exactly n_tubes x per_tube with no dead volume, so after
     rounding the LAST tube of every arm came up 0.1-0.2 uL short. Real vessel/tip
     residue (1-5 uL) was not modelled at all.
  2. The workbook never printed a sub-mix RECIPE: the grouping table gave final
     concentrations only, so 11 of the 23 counted prep steps had no bench instruction.
  3. The Reaction Matrix enzyme-total row wrote each label at `ci[e_uL] - 1`. Enzyme
     columns are contiguous, so every label overwrote the previous enzyme's formula and
     6 of 7 totals silently vanished.
"""
import json
import subprocess
import sys
from pathlib import Path

import openpyxl
import pytest

SK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SK))

import pipette_count as pc  # noqa: E402

CFG = SK / "tests" / "fixtures" / "pipette_rules" / "synthetic_serial_x8.json"


def _cfg(**over):
    c = json.loads(CFG.read_text(encoding="utf-8"))
    c.update(over)
    return c


def _build(**over):
    return pc.build_plan(_cfg(**over))


def _generate(tmp_path, cfg):
    p, out = tmp_path / "c.json", tmp_path / "w.xlsx"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    r = subprocess.run([sys.executable, str(SK / "reaction_matrix.py"), str(p), str(out), "--no-publish"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stdout[-2000:]
    return openpyxl.load_workbook(out)


# ---------------------------------------------------------------- 1. dead volume

def test_submix_make_volume_covers_every_tube_plus_dead():
    plan = _build()
    sms = plan["submixes"]
    assert sms, "fixture must produce at least one shared sub-mix"
    for sm in sms:
        need = sm["per_tube"] * len(sm["conditions"])
        assert sm["make_uL"] > need, f'{sm["name"]}: make {sm["make_uL"]} <= need {need}'
        assert sm["make_uL"] == pytest.approx(need + sm["dead_uL"])


def test_submix_component_draws_sum_to_the_make_volume():
    for sm in _build()["submixes"]:
        assert sum(sm["draws"].values()) == pytest.approx(sm["make_uL"])


def test_submix_dead_volume_is_configurable_and_defaults_to_dead_volume_uL():
    assert pc.dead_ul({}, "submix") == pc.DEAD_UL
    assert pc.dead_ul({"dead_volume_uL": 9}, "submix") == 9
    assert pc.dead_ul({"dead_volume_uL": 9, "submix_dead_volume_uL": 21}, "submix") == 21
    # the cocktail knob must not leak into sub-mixes, nor the other way round
    assert pc.dead_ul({"cocktail_dead_volume_uL": 40}, "submix") == pc.DEAD_UL
    assert pc.dead_ul({"submix_dead_volume_uL": 40}, "cocktail") == pc.DEAD_UL


def test_raising_submix_dead_volume_raises_every_draw():
    base = {sm["name"]: sm for sm in _build()["submixes"]}
    bigger = {sm["name"]: sm for sm in _build(submix_dead_volume_uL=25)["submixes"]}
    assert set(base) == set(bigger)
    for name, sm in base.items():
        assert bigger[name]["make_uL"] > sm["make_uL"]
        for s, v in sm["draws"].items():
            assert bigger[name]["draws"][s] > v


def test_submix_prep_steps_match_the_recipe_draws():
    plan = _build()
    by_name: dict[str, dict[str, float]] = {}
    for st in plan["steps"]:
        if st.phase == "prep" and st.kind == "submix":
            by_name.setdefault(st.target, {})[st.source] = st.volume_uL
    assert by_name
    for sm in plan["submixes"]:
        assert by_name[sm["name"]] == pytest.approx(sm["draws"])


# ---------------------------------------------------------------- 2. printed recipe

def test_guide_prints_a_recipe_for_every_submix(tmp_path):
    cfg = _cfg()
    plan = pc.build_plan(cfg)
    ws = _generate(tmp_path, cfg)["Pipetting Guide"]
    labels = [str(ws.cell(r, 1).value or "") for r in range(1, ws.max_row + 1)]
    assert any(v.startswith("SUB-MIX RECIPES") for v in labels), "recipe block missing"
    vals = [str(c.value) for row in ws.iter_rows() for c in row if c.value is not None]
    for sm in plan["submixes"]:
        # every component draw and the make total must be readable on the sheet
        for v in list(sm["draws"].values()) + [sm["make_uL"]]:
            assert any(f"{round(v, 1):g}" == f"{c:g}" for c in
                       (x for x in (cc.value for row in ws.iter_rows() for cc in row)
                        if isinstance(x, (int, float)))), f'{sm["name"]}: {v:.1f} uL not printed'
    assert any("total" in v for v in vals)


def test_recipe_block_does_not_reuse_the_working_stock_header(tmp_path):
    """'How to mix' is the working-stock contract (test_guide_readability); the sub-mix
    block must not borrow it, or that rule starts checking the wrong rows."""
    ws = _generate(tmp_path, _cfg())["Pipetting Guide"]
    start = next(r for r in range(1, ws.max_row + 1)
                 if str(ws.cell(r, 1).value or "").startswith("SUB-MIX RECIPES"))
    headers = [str(ws.cell(start + 1, c).value or "") for c in range(1, 5)]
    assert "How to mix" not in headers, headers
    assert "How to make it" in headers, headers


# ------------------------------------------- 2b. sheet 2 is a view of sheet 1 (SSOT)

def _breakdown_rows(ws2):
    start = next(r for r in range(1, ws2.max_row + 1)
                 if str(ws2.cell(r, 1).value or "").startswith("PER-TUBE VOLUME BREAKDOWN"))
    head = next(r for r in range(start, ws2.max_row + 1) if ws2.cell(r, 1).value == "#")
    return [r for r in range(head + 1, ws2.max_row + 1)
            if str(ws2.cell(r, 1).value or "").startswith("#")]


def test_per_tube_breakdown_references_sheet1_not_literals(tmp_path):
    """The defect: every volume was re-derived from literals (=ROUND(100*100/1800,4)), so
    editing a stock or the total volume on sheet 1 left sheet 2 silently disagreeing."""
    wb = _generate(tmp_path, _cfg())
    ws2 = wb["Pipetting Guide"]
    rows = _breakdown_rows(ws2)
    assert rows, "per-tube breakdown has no tube rows"
    seen_ref = 0
    for r in rows:
        for c in range(2, ws2.max_column + 1):
            f = ws2.cell(r, c).value
            if not (isinstance(f, str) and f.startswith("=")):
                continue
            # a cross-sheet reference or a within-sheet one is fine; standalone arithmetic
            # over two literals (stock / volume) is the defect
            if "'Reaction Matrix'!" in f:
                seen_ref += 1
            assert "ROUND(" not in f or "!" in f or any(ch.isalpha() for ch in f.split("ROUND(")[1][:3]), f
    assert seen_ref >= len(rows), f"only {seen_ref} sheet-1 references across {len(rows)} tubes"


def test_changing_total_volume_moves_every_breakdown_formula(tmp_path):
    """Rule 1 of 'Four rules for editing a pipetting workbook': prove a downstream cell
    followed. The DW residual must be driven by sheet 1's total-volume cell, not a literal."""
    wb = _generate(tmp_path, _cfg())
    ws2 = wb["Pipetting Guide"]
    ws1 = wb["Reaction Matrix"]
    vol_row = next(r for r in range(1, ws1.max_row + 1)
                   if str(ws1.cell(r, 1).value or "").startswith("Total volume"))
    for r in _breakdown_rows(ws2):
        dw = [ws2.cell(r, c).value for c in range(2, ws2.max_column + 1)
              if isinstance(ws2.cell(r, c).value, str) and "$B$%d" % vol_row in ws2.cell(r, c).value]
        assert dw, f"tube row {r}: no formula references the total-volume cell B{vol_row}"
        assert all("'Reaction Matrix'!$B$%d" % vol_row in f for f in dw), dw


# ---------------------------------------------------------------- 3. enzyme totals

def test_every_enzyme_keeps_its_total_formula(tmp_path):
    cfg = _cfg()
    # the sheet has one column per EFFECTIVE enzyme entry: an equal-volume spec is expanded
    # into one pseudo-enzyme per level, so normalize() is the roster the workbook uses
    enz = list(pc.normalize(cfg)["enzymes"])
    ws = _generate(tmp_path, cfg)["Reaction Matrix"]
    rows = [r for r in range(1, ws.max_row + 1)
            if "total (x" in str(ws.cell(r, 1).value or "")]
    assert len(rows) == len(enz), f"expected one total row per enzyme, got {len(rows)}"
    named, formulas = set(), 0
    for r in rows:
        label = str(ws.cell(r, 1).value)
        named.add(label.split(" total (x")[0])
        formulas += sum(1 for c in range(1, ws.max_column + 1)
                        if str(ws.cell(r, c).value or "").startswith("=ROUND(SUM("))
    assert named == set(enz), named ^ set(enz)
    assert formulas == len(enz), f"{formulas} surviving formulas for {len(enz)} enzymes"


def test_enzyme_total_labels_do_not_overwrite_a_neighbour_column(tmp_path):
    """The regression itself: a label must never land in a column that holds a formula."""
    ws = _generate(tmp_path, _cfg())["Reaction Matrix"]
    for r in range(1, ws.max_row + 1):
        if "total (x" not in str(ws.cell(r, 1).value or ""):
            continue
        for c in range(2, ws.max_column + 1):
            v = ws.cell(r, c).value
            assert not (isinstance(v, str) and "total (x" in v), f"label leaked into r{r}c{c}: {v}"
