"""Pipetting Guide 'ENZYME PREPARATION' block (261012): batch (purification date), total lab stock per enzyme,
cocktail recipe, serial dilution, and the configurable cocktail dead volume.

Reference run: synthetic example (EnzX x1/x4/x8, n = 3, 10 tubes, 9 with enzyme).
"""
import copy
import json
import sys
from pathlib import Path

import openpyxl

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import pipette_count as pc  # noqa: E402
import reaction_matrix as rm  # noqa: E402

CFG = json.loads((HERE / "fixtures" / "pipette_rules" / "synthetic_serial_x8.json").read_text(encoding="utf-8"))


def _guide_rows(cfg, tmp_path):
    out = tmp_path / "w.xlsx"
    rm.generate_excel(pc.normalize(cfg), str(out))
    ws = openpyxl.load_workbook(out)["Pipetting Guide"]
    return [[c.value for c in row] for row in ws.iter_rows()]


def _find(rows, prefix):
    return next(i for i, r in enumerate(rows) if str(r[0] or "").startswith(prefix))


def _table(rows, title_prefix):
    i = _find(rows, title_prefix) + 2
    out = []
    while i < len(rows) and rows[i][0] and not str(rows[i][0]).startswith("TOTAL"):
        out.append(rows[i]); i += 1
    return out


def test_block_present_with_batch_and_totals(tmp_path):
    rows = _guide_rows(CFG, tmp_path)
    for head in ("TUBES TO PREPARE", "ENZYME PREPARATION", "A) LAB STOCKS", "B) COMMON COCKTAIL"):
        _find(rows, head)
    stocks = {r[0]: r for r in _table(rows, "A) LAB STOCKS")}
    assert set(stocks) == {"EnzA", "EnzB", "EnzC", "EnzD", "EnzE", "EnzY", "EnzX"}
    assert stocks["EnzE"][1] == "260103" and stocks["EnzX"][1] == "260104"          # purification date shown
    assert all(r[1] for r in stocks.values())                                            # every enzyme has a batch
    plan = pc.build_plan(CFG)
    for name, r in stocks.items():                                                       # total = plan's lab draw
        if name in CFG["serial_dilution"]:   # the pipette-count model still prices independent draws (29.66 uL)
            continue
        assert abs(r[3] - plan["lab_uL"][name]) <= 0.06, name


def test_cocktail_dead_volume_is_configurable_and_additive(tmp_path):
    base = _table(_guide_rows(CFG, tmp_path), "B) COMMON COCKTAIL")
    cfg10 = copy.deepcopy(CFG); cfg10["cocktail_dead_volume_uL"] = 10
    ten = _table(_guide_rows(cfg10, tmp_path), "B) COMMON COCKTAIL")
    d = {r[0]: r[4] - t[4] for r, t in zip(sorted(base), sorted(ten))}
    assert abs(sum(d.values()) - 5.0) <= 0.35                                            # 15 vs 10 uL dead, +rounding
    assert all(v > 0 for v in d.values())
    assert abs(sum(r[4] for r in base) - 117.5) <= 0.4                                  # sum of per-tube draws x 1.0 + 15 uL dead: no % overage


def test_cocktail_order_is_deterministic(tmp_path):
    a = [r[0] for r in _table(_guide_rows(CFG, tmp_path), "B) COMMON COCKTAIL")]
    assert a == sorted(a)


def test_serial_dilution_chain_matches_bench_recipe(tmp_path):
    rows = _guide_rows(CFG, tmp_path)
    chain = _table(rows, "C) EnzX LEVELS")
    assert [(r[0], r[3]) for r in chain] == [("EnzX [8x]", 28), ("EnzX [4x]", 22), ("EnzX [1x]", 17)]   # ceil(12+5), +4.25, +11
    assert chain[0][4] == "lab stock" and chain[1][4] == "EnzX [8x]"
    assert all(r[5] >= 2.5 for r in chain)                                               # every transfer pipettable
    assert abs(chain[0][5] - 28 * 50 / 68) <= 0.05                                       # top level: 28 uL at 50 g/L from a 68 g/L stock


def test_no_serial_option_keeps_independent_working_stocks(tmp_path):
    cfg = copy.deepcopy(CFG); cfg["serial_dilution"] = []   # omitted = auto since 261013
    rows = _guide_rows(cfg, tmp_path)
    _find(rows, "C) WORKING STOCKS")


# ---- adversarial review 261012: D1-D4 and the lost guide lines -------------------------------------

def _block_a(rows):
    return {r[0]: r for r in _table(rows, "A) LAB STOCKS")}


def test_per_condition_working_stock_is_not_counted_as_neat(tmp_path):          # D1
    cfg = copy.deepcopy(CFG); cfg["enzyme_cocktail"] = "per_condition"
    rows = _guide_rows(cfg, tmp_path)
    plan = pc.build_plan(cfg)
    a = _block_a(rows)
    assert abs(a["EnzX"][3] - plan["lab_uL"]["EnzX"]) <= 0.7        # serial vs independent draw model + rounding
    comp = [r[0] for r in _table(rows, "B) COCKTAIL-1")]
    assert any("WORKING STOCK" in str(x) for x in comp)


def test_direct_additions_are_in_block_a(tmp_path):                              # D3
    cfg = copy.deepcopy(CFG); cfg["enzyme_cocktail"] = "none"
    rows = _guide_rows(cfg, tmp_path)                                    # generate_excel does not gate on validate
    a = _block_a(rows)
    assert {"EnzA", "EnzB", "EnzC", "EnzD", "EnzE", "EnzY", "EnzX"} <= set(a)
    assert a["EnzA"][6] and a["EnzA"][6] > 35                        # direct column filled (about 9 tubes x 4.3 x 1.0)


def test_serial_dilution_misconfiguration_is_reported():                         # D4
    for bad, expect_ok, token in ((["NoSuchEnz"], True, "WARN serial_dilution"), ("EnzX", False, "FAIL serial_dilution")):
        cfg = copy.deepcopy(CFG); cfg["serial_dilution"] = bad
        ok, rep = rm.validate_config(pc.normalize(cfg))
        assert ok is expect_ok
        assert token in "\n".join(rep)


def test_tube_block_keeps_weighing_and_water_in_place_lines(tmp_path):         # lines lost from the hand edit
    rows = _guide_rows(CFG, tmp_path)
    text = "\n".join(str(r[0]) for r in rows if r[0])
    assert "Weigh first" in text and "0.56 mg" in text
    assert "WATER in the same volumes" in text


def test_serial_row_rounds_half_up(tmp_path):
    chain = _table(_guide_rows(CFG, tmp_path), "C) EnzX LEVELS")
    assert chain[2][5] == 4.3 and chain[2][6] == 12.7   # 4.25 -> 4.3 half-up


def test_enzyme_additions_marks_independent_rows_superseded(tmp_path):         # D2
    out = tmp_path / "w.xlsx"
    rm.generate_excel(pc.normalize(CFG), str(out))
    ws = openpyxl.load_workbook(out)["Enzyme Additions"]
    assert any("SUPERSEDED for EnzX" in str(r[0].value) for r in ws.iter_rows(max_col=1))


def _serial_lines(cfg):
    _ok, rep = rm.validate_config(pc.normalize(cfg), "t")
    return [x for x in rep if "serial_dilution" in x]


def test_serial_transfer_below_floor_fails_and_below_pipette_warns():
    """R2b: every serial transfer / lab-stock draw >= 2.5 uL; < 0.5 uL is below any pipette (FAIL)."""
    base = _serial_lines(CFG)
    assert not any(x.startswith(("FAIL", "WARN")) for x in base)          # shipped chain: min transfer 4.3 uL
    cfg = copy.deepcopy(CFG); cfg["enzymes"]["EnzX"]["stock_gL"] = 2000.0   # top draw 1.0 uL
    assert any(x.startswith("WARN") and "2.5 uL" in x for x in _serial_lines(cfg))
    cfg["enzymes"]["EnzX"]["stock_gL"] = 9000.0                              # top draw 0.22 uL
    lines = _serial_lines(cfg)
    assert any(x.startswith("FAIL") and "pipette floor" in x for x in lines)


def test_serial_non_two_fold_step_is_reported():
    assert any("4.00-fold" in x for x in _serial_lines(CFG))   # x4 -> x1 is a 4-fold step; R2b prefers 2-fold


def test_serial_dilution_is_default_when_omitted(tmp_path):                      
    cfg = copy.deepcopy(CFG); cfg.pop("serial_dilution")
    rows = _guide_rows(cfg, tmp_path)
    assert [r[0] for r in _table(rows, "C) EnzX LEVELS")] == ["EnzX [8x]", "EnzX [4x]", "EnzX [1x]"]
