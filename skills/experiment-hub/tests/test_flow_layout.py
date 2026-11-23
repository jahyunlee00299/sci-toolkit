"""FLOW layout: water folded into the substrate mix, spare volume in tube units, the FLOW bench sheet,
the layout key, and the matching validate_config lines.

The mini config: 50 uL, MM-A (Tris + MgCl2), two substrates, two neat cocktail enzymes. Group A = tubes 1-3
(SubA 100), group B = tubes 4-6 (SubA 50, needs 2.5 uL more water than A). Tube 3 and 6 lack E2 so that a
group can contain tubes with different top-ups.
"""
import copy
import sys
from pathlib import Path

import openpyxl
import pytest

SK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SK))

import flow_sheet  # noqa: E402
import pipette_count as pc  # noqa: E402
import reaction_matrix as rm  # noqa: E402

BASE = {
    "title": "FLOW test", "date": "000000", "total_volume_uL": 50.0, "temperature_C": 30,
    "timepoints": ["4 h", "24 h"],
    "sampling": {"volume_uL": 3, "dilution": "20x", "quench": "heat", "analysis": "HPLC", "targets": ["P"]},
    "stocks": {
        "Tris": {"conc_mM": 1000, "type": "buffer", "final_mM": 200},
        "MgCl2": {"conc_mM": 1000, "type": "buffer", "final_mM": 5},
        "SubA": {"conc_mM": 1000, "type": "substrate"},
        "SubB": {"conc_mM": 1800, "type": "substrate"},
    },
    "enzymes": {
        "E1": {"batch": "b1", "stock_gL": 10.0, "rxn_gL": {"1x": 1.0, "0x": 0}},
        "E2": {"batch": "b2", "stock_gL": 10.0, "rxn_gL": {"1x": 0.5, "0x": 0}},
    },
}


def _cond(num, xyl, e2=True, group="A"):
    return {"num": num, "group": group, "label": f"{group} R{num}", "substrates": {"SubA": xyl, "SubB": 200},
            "enzymes": {"E1": "1x", "E2": "1x" if e2 else "0x"}, "note": f"cond {num}"}


def mini(a=3, b=3, a_e2_missing=(3,), b_e2_missing=(6,), **over):
    cfg = copy.deepcopy(BASE)
    conds, n = [], 0
    for _ in range(a):
        n += 1
        conds.append(_cond(n, 100, n not in a_e2_missing, "A"))
    for _ in range(b):
        n += 1
        conds.append(_cond(n, 50, n not in b_e2_missing, "B"))
    cfg["conditions"] = conds
    cfg.update(over)
    return cfg


def _dw_tubes(plan):
    return sorted(int(s.target[1:]) for s in plan["steps"] if s.phase == "run" and s.kind == "dw")


def _sm_run_vols(plan, group):
    return {round(s.volume_uL, 6) for s in plan["steps"]
            if s.phase == "run" and s.kind == "substrate" and int(s.target[1:]) in group}


# ---------------------------------------------------------------- A. water folded into the sub-mix
def test_fold_gives_every_tube_of_the_group_the_same_volume_and_no_dw_step():
    plan = pc.build_plan(mini(b=2, b_e2_missing=()))          # group B: tubes 4-5, identical, top-up 2.5 each
    assert plan["submix_water"] == {4: 2.5, 5: 2.5}
    assert 4 not in _dw_tubes(plan) and 5 not in _dw_tubes(plan)
    assert plan["topup"][4] == plan["topup"][5] == 0.0
    sm = next(s for s in plan["submixes"] if s["conditions"] == [4, 5])
    assert sm["water_per_tube"] == 2.5 and sm["draws"]["water"] > 0
    assert sm["per_tube"] == pytest.approx(sm["substrate_per_tube"] + 2.5)
    assert _sm_run_vols(plan, {4, 5}) == {round(sm["per_tube"], 6)}
    assert any(s.phase == "prep" and s.target == sm["name"] and s.source == "water" for s in plan["steps"])
    rp = pc.rounded_plan(plan)
    assert {t: rp["tubes"][t][1][3] for t in (4, 5)} == {4: rp["tubes"][4][1][3], 5: rp["tubes"][4][1][3]}
    assert 4 in rp["submix_closing"] and rp["dw"][4] == 0.0


def test_remainder_stays_a_valid_dw_step():
    plan = pc.build_plan(mini())                                # tube 6 lacks E2: its top-up is 2.5 uL larger
    floor = pc.limits(plan["config"])["floor_uL"]
    group_b = [4, 5, 6]
    assert plan["submix_water"][4] == plan["submix_water"][6]
    assert _dw_tubes(plan) == [3, 6] or _dw_tubes(plan) == [6, 3]
    for t in _dw_tubes(plan):
        assert plan["topup"][t] >= floor
    assert len(_sm_run_vols(plan, set(group_b))) == 1           # same sub-mix volume in all three tubes
    rp = pc.rounded_plan(plan)
    assert rp["dw"][6] >= floor and rp["dw"][4] == 0.0


def test_fold_water_helper_edge_cases():
    cfg, floor = {}, 0.5
    assert pc._fold_water(cfg, [3.0, 3.0], 10.0, 2, floor) == 3.0
    assert pc._fold_water(cfg, [3.0, 3.2], 10.0, 2, floor) == 2.5     # remainder 0.2 < floor -> w - floor
    assert pc._fold_water(cfg, [0.0, 2.0], 10.0, 2, floor) == 0.0     # nothing to fold
    assert pc._fold_water(cfg, [0.6, 0.8], 10.0, 2, floor) == 0.0     # w - floor draws < floor: not folded
    assert pc._fold_water(cfg, [0.1, 0.1], 10.0, 2, floor) == 0.0     # water draw 0.1 x 3 < floor


def test_water_in_submix_false_is_the_legacy_plan():
    legacy = pc.build_plan(mini(water_in_submix=False, submix_dead_volume_uL=5.0))
    assert legacy["submix_water"] == {}
    assert not any(s.source == "water" and s.kind == "submix" for s in legacy["steps"])
    assert _dw_tubes(legacy) == [t for t, v in legacy["topup"].items() if v > 0]
    assert _dw_tubes(legacy) == [3, 4, 5, 6]                    # B's extra water is a DW step in every B tube
    for sm in legacy["submixes"]:
        assert sm["water_per_tube"] == 0.0
        assert sm["make_uL"] == pytest.approx(sm["per_tube"] * len(sm["conditions"]) + 5.0)
        assert sm["dead_uL"] == 5.0
    # folding off changes nothing but the water placement: the folded plan has the same total per tube
    folded = pc.build_plan(mini(submix_dead_volume_uL=5.0))
    for t in range(1, 7):
        tot = lambda p: sum(s.volume_uL for s in p["steps"] if s.phase == "run" and s.target == f"#{t}"
                            and s.kind != "water_in_place")
        assert tot(legacy) == pytest.approx(tot(folded))


# ---------------------------------------------------------------- B. spare volume in tube units
def test_spare_rule_in_tube_units():
    cfg = mini()
    assert pc.submix_make(cfg, 10.0, 3) == (40.0, 4.0, 10.0, 1.0)
    assert pc.submix_make(cfg, 10.0, 9)[3] == 1.0
    assert pc.submix_make(cfg, 10.0, 10)[3] == 2.0
    make, scale, dead, spare = pc.submix_make(cfg, 10.0, 14)
    assert (make, scale, dead, spare) == (160.0, 16.0, 20.0, 2.0)
    assert pc.submix_make(dict(cfg, submix_spare_tubes=0.5), 10.0, 14)[3] == 0.5
    legacy = pc.submix_make(dict(cfg, submix_dead_volume_uL=6.0), 10.0, 14)
    assert legacy[0] == 146.0 and legacy[2] == 6.0
    with pytest.raises(ValueError):
        pc.submix_make(dict(cfg, submix_spare_tubes=-1), 10.0, 3)


def test_spare_rule_in_the_plan_keys():
    big = pc.build_plan(mini(a=14, b=3, a_e2_missing=(), b_e2_missing=()))
    by_n = {len(s["conditions"]): s for s in big["submixes"]}
    assert by_n[14]["spare_tubes"] == 2.0 and by_n[3]["spare_tubes"] == 1.0
    for sm in big["submixes"]:
        n = len(sm["conditions"])
        assert sm["make_uL"] == pytest.approx(sm["per_tube"] * (n + sm["spare_tubes"]))
        assert sm["dead_uL"] == pytest.approx(sm["per_tube"] * sm["spare_tubes"])
    # enzyme cocktails keep the fixed dead volume (enzyme stock is scarce)
    ck = big["route"]["cocktails"][0]
    assert ck["make_uL"] == pytest.approx(ck["per_tube"] * len(ck["members"]) + pc.dead_ul(big["config"], "cocktail"))


# ---------------------------------------------------------------- closure and deviation
@pytest.mark.parametrize("fold", [True, False])
@pytest.mark.parametrize("cfg_kw", [dict(), dict(b=2, b_e2_missing=()), dict(a=14, b=3, a_e2_missing=(), b_e2_missing=())])
def test_every_tube_closes_and_deviation_is_small(fold, cfg_kw):
    cfg = mini(water_in_submix=fold, **cfg_kw)
    plan = pc.build_plan(cfg)
    rp = pc.rounded_plan(plan)
    V = cfg["total_volume_uL"]
    for t, rows in rp["tubes"].items():
        assert round(sum(r[3] for r in rows), 6) == V, (t, rows)
    assert max(v[0] for v in rp["deviation"].values()) < pc.DEV_FAIL
    ok, report = rm.validate_config(cfg)
    assert ok, [x for x in report if x.startswith("FAIL")]


def test_no_uniformity_warn_for_a_folded_top_up():
    ok, rep = rm.validate_config(mini(b=2, b_e2_missing=(), a=2, a_e2_missing=()))
    assert ok
    assert not any("DW top-up" in x and x.startswith("WARN") for x in rep)
    assert any(x.startswith("INFO flow:") and "4 of 4 tubes receive the identical volume sequence" in x for x in rep)
    ok2, rep2 = rm.validate_config(mini(b=2, b_e2_missing=(), a=2, a_e2_missing=(), water_in_submix=False))
    assert ok2
    r1 = next(x for x in rep2 if "R1" in x)
    assert "carry their remaining water" not in r1
    r1f = next(x for x in rm.validate_config(mini(b=2, b_e2_missing=(), a=2, a_e2_missing=()))[1] if "R1" in x)
    assert "inside a substrate sub-mix" in r1f


def test_invalid_keys_fail_validation():
    for bad in (dict(layout="wide"), dict(water_in_submix="yes"), dict(submix_spare_tubes=-1)):
        ok, rep = rm.validate_config(mini(**bad))
        assert not ok and any(x.startswith("FAIL") for x in rep)


# ---------------------------------------------------------------- C/D. FLOW sheet and layout
def _wb(tmp_path, **over):
    cfg = mini(**over)
    out = tmp_path / "w.xlsx"
    rm.generate_excel(cfg, str(out))
    return cfg, openpyxl.load_workbook(out)


def _section(ws, head):
    rows, on = [], False
    for row in ws.iter_rows(values_only=True):
        first = row[0]
        if isinstance(first, str) and first.startswith(head):
            on = True
            continue
        if on and isinstance(first, str) and first.split(' ')[0] in ("TAKE", "PREP", "RUN", "SAMPLING", "CHECK"):
            break
        if on:
            rows.append(row)
    return rows


def test_flow_sheet_is_first_and_active_and_others_hidden(tmp_path):
    cfg, wb = _wb(tmp_path)
    assert wb.sheetnames[0] == "FLOW" and wb.active.title == "FLOW"
    assert set(wb.sheetnames) == {"FLOW", "Reaction Matrix", "Pipetting Guide", "Enzyme Additions", "Sampling & Fed", "Data"}
    assert wb["FLOW"].sheet_state == "visible"
    assert all(wb[n].sheet_state == "hidden" for n in wb.sheetnames if n != "FLOW")
    assert sum(1 for s in wb.worksheets if s.sheet_view.tabSelected) == 1
    # no formulas on FLOW (static values)
    assert not any(isinstance(c.value, str) and c.value.startswith("=") for r in wb["FLOW"].iter_rows() for c in r)


def test_full_layout_keeps_everything_visible(tmp_path):
    _, wb = _wb(tmp_path, layout="full")
    assert wb.sheetnames[0] == "FLOW"
    assert all(s.sheet_state == "visible" for s in wb.worksheets)


def test_run_lists_each_tube_once_per_stage(tmp_path):
    cfg = mini()
    plan = pc.build_plan(cfg)
    rp = pc.rounded_plan(plan)
    fl = flow_sheet.build_flow(plan, rp)
    tubes = [c["num"] for c in cfg["conditions"]]
    by_step = {}
    for r in fl["run"]:
        by_step.setdefault(r["step"], []).extend(r["tube_list"])
    for step, ts in by_step.items():
        assert len(ts) == len(set(ts)), (step, ts)            # a tube appears once in a step
    stages = {r["stage"]: r["step"] for r in fl["run"]}
    assert sorted(by_step[stages[flow_sheet.STAGE_MM]]) == tubes
    assert sorted(by_step[stages[flow_sheet.STAGE_SUB]]) == tubes
    # a row is never a single tube unless that tube is really unique
    for r in fl["run"]:
        if len(r["tube_list"]) == 1 and r["stage"] == flow_sheet.STAGE_MM:
            raise AssertionError("one row per tube")
    # tube ranges are written compactly
    assert flow_sheet.tube_ranges([1, 2, 3, 28, 29, 35]) == "#1-3, #28-29, #35"


def test_take_out_equals_the_plan_lab_stock_totals(tmp_path):
    cfg, wb = _wb(tmp_path, a=14, b=3, a_e2_missing=(), b_e2_missing=())
    plan = pc.build_plan(cfg)
    tot = rm.lab_stock_totals(plan)
    res = pc.limits(cfg)["resolution_uL"]
    want = {n: pc._rnd(tot["cocktail"].get(n, 0) + tot["working"].get(n, 0) + tot["direct"].get(n, 0), res)
            for n in tot["names"]}
    rows = {r[0]: r for r in _section(wb["FLOW"], "TAKE OUT") if r[0] and r[0] != "Stock"}
    for n, v in want.items():
        assert rows[n][3] == pytest.approx(v)
    for stock in ("SubA", "SubB", "Tris", "MgCl2"):
        assert rows[stock][3] == pytest.approx(pc._rnd(plan["lab_uL"][stock], res))
    # and the Pipetting Guide block A shows the same enzyme totals
    pg = wb["Pipetting Guide"]
    guide = {}
    for row in pg.iter_rows(values_only=True):
        if row[0] in want and isinstance(row[3], (int, float)) and row[0] not in guide:
            guide[row[0]] = row[3]
    assert guide and all(guide[n] == pytest.approx(want[n]) for n in guide)


def test_flow_check_line_and_no_water_row_in_guide_text(tmp_path):
    cfg, wb = _wb(tmp_path, a=2, b=2, a_e2_missing=(), b_e2_missing=())
    txt = [r[0] for r in wb["FLOW"].iter_rows(values_only=True) if isinstance(r[0], str)]
    assert any(t.startswith("OK: every tube closes to 50 uL") for t in txt)
    pg = [c.value for r in wb["Pipetting Guide"].iter_rows() for c in r if isinstance(c.value, str)]
    assert any(t.startswith("add ") and t.endswith("uL of water to the SM-2 tube") for t in pg) \
        or any(" uL of water to the SM-" in t for t in pg)
    assert not any("water stock" in t for t in pg)
    assert not any("DW re-closes every tube" in t for t in pg)


def test_legacy_water_option_keeps_a_dw_row_on_flow(tmp_path):
    cfg, wb = _wb(tmp_path, water_in_submix=False, submix_dead_volume_uL=5.0, a=2, b=2, a_e2_missing=(), b_e2_missing=())
    run = _section(wb["FLOW"], "RUN")
    assert any(r[1] == "Water (DW top-up)" for r in run)
    mixes = _section(wb["FLOW"], "PREP")
    assert mixes


def test_sampling_block_groups_tubes_by_their_own_timepoints():
    cfg = mini()
    for c in cfg["conditions"]:
        if c["group"] == "B":
            c["timepoints"] = ["24 h"]
    plan = pc.build_plan(cfg)
    rows = dict(flow_sheet.build_flow(plan, pc.rounded_plan(plan))["sampling"])
    tp = {k: v for k, v in rows.items() if k.startswith("Timepoints")}
    assert len(tp) == 2 and "Timepoints" not in tp
    a = next(v for k, v in tp.items() if "#1-3" in k and "(A)" in k)
    b = next(v for k, v in tp.items() if "#4-6" in k and "(B)" in k)
    assert a.startswith("4 h, 24 h") and "2 samples" in a
    assert b.startswith("24 h") and "1 samples" in b


def test_sampling_block_has_one_timepoints_row_when_every_tube_shares_them():
    plan = pc.build_plan(mini())
    rows = flow_sheet.build_flow(plan, pc.rounded_plan(plan))["sampling"]
    assert [k for k, _ in rows].count("Timepoints") == 1
