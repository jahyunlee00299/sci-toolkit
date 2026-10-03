"""Regression tests for an independent adversarial review of the R1/R2 enforcement (D1-D7) and the
instrument facts (smallest pipette 2.5 uL: floor 0.5 uL hard, comfort 1.0 uL; same volume in every tube;
volumes rounded to 0.1 uL). The attack configs are the reviewer's, reused as fixtures; the larger designs
are the SYNTHETIC ones in synthetic_fixtures.py.
"""
import json
import subprocess
import sys
from pathlib import Path

import openpyxl
import pytest

HERE = Path(__file__).resolve().parent
SK = HERE.parent
sys.path.insert(0, str(SK))
sys.path.insert(0, str(HERE))
import equal_volume as ev  # noqa: E402
import pipette_count as pc  # noqa: E402
import reaction_matrix as rm  # noqa: E402
import synthetic_fixtures as sf  # noqa: E402

SYNTH = {"pooled": sf.pooled_config, "ev_spec": sf.ev_spec, "neat": sf.neat_config}
load = lambda name: SYNTH[name]()


def fails(rep):
    return [l for l in rep if l.startswith("FAIL")]


def warns(rep):
    return [l for l in rep if l.startswith("WARN") and "canon-gate" not in l]


# ---------------------------------------------------------------- the verifier's attack configs
def base():
    return {"total_volume_uL": 50, "stocks": {"Tris": {"conc_mM": 1000, "type": "buffer", "final_mM": 100},
                                              "S": {"conc_mM": 1000, "type": "substrate"}},
            "enzymes": {"E": {"batch": "x", "stock_gL": 10.0, "rxn_gL": {"1x": 0.2, "0x": 0}}},
            "conditions": [{"num": 1, "label": "a", "substrates": {"S": 100}, "enzymes": {"E": "1x"}},
                           {"num": 2, "label": "b", "substrates": {"S": 100}, "enzymes": {"E": "1x"}}]}


def attack(row):
    c = base()
    e = c["enzymes"]["E"]
    if row == "1 vol 0.99":
        e["rxn_gL"]["1x"] = 0.198
    elif row == "2 vol 1.00":
        pass
    elif row == "2b vol 0.99999":
        e["rxn_gL"]["1x"] = 0.199999
    elif row in ("3 two vols diff 4e-6", "3b two vols 4.0 vs 4.0001"):
        e["rxn_gL"] = {"1x": 0.8, "1xb": 0.800001 if row.startswith("3 ") else 0.80002, "0x": 0}
        c["conditions"][1]["enzymes"]["E"] = "1xb"
    elif row == "4 waiver no reason":
        e["rxn_gL"]["1x"] = 0.1
        e["allow_small_volume"] = True
    elif row == "5 waiver empty reason":
        e["rxn_gL"]["1x"] = 0.1
        e.update(allow_small_volume=True, allow_small_volume_reason="")
    elif row == "5b waiver reason null":
        e["rxn_gL"]["1x"] = 0.1
        e.update(allow_small_volume=True, allow_small_volume_reason=None)
    elif row == "5c waiver flag 'false'":
        e["rxn_gL"]["1x"] = 0.1
        e.update(allow_small_volume="false", allow_small_volume_reason="x")
    elif row == "6 only 0x/1x":
        c["conditions"][1]["enzymes"]["E"] = "0x"
    elif row == "7 no buffer stocks":
        del c["stocks"]["Tris"]
    elif row == "8 empty config":
        return {}
    elif row == "8b no conditions":
        c["conditions"] = []
    elif row == "9 tube exactly full":
        e["rxn_gL"]["1x"] = 8.0
    elif row == "9' overfill (adv_attack2)":
        e["rxn_gL"]["1x"] = 9.0
        c["conditions"][1]["enzymes"]["E"] = "0x"
    elif row == "10 alias bypass":
        c["enzymes"] = {"E_lo": {"batch": "x", "stock_gL": 10.0, "rxn_gL": {"1x": 0.4, "0x": 0}},
                        "E_hi": {"batch": "x", "stock_gL": 10.0, "rxn_gL": {"4x": 1.6, "0x": 0}}}
        c["conditions"][0]["enzymes"] = {"E_lo": "1x", "E_hi": "0x"}
        c["conditions"][1]["enzymes"] = {"E_lo": "0x", "E_hi": "4x"}
    elif row == "11 variable volume, no waiver":
        e["rxn_gL"] = {"1x": 0.4, "4x": 1.6, "0x": 0}
        c["conditions"][1]["enzymes"]["E"] = "4x"
    elif row == "12 non-enzyme sub-uL":
        c["stocks"]["G"] = {"conc_mM": 10, "type": "buffer", "final_mM": 0.015}
        c["stocks"]["S2"] = {"conc_mM": 1000, "type": "substrate"}
        c["conditions"][0]["substrates"]["S2"] = 6
        c["conditions"][1]["substrates"]["S2"] = 3
    else:
        raise KeyError(row)
    return c


# row -> (outcome after the fix, a substring that must appear in the report)
#   blocked = validate_config ok False; WARN = ok True with a WARN line; passed = ok True, no WARN line
ATTACK_TABLE = [
    ("1 vol 0.99", "WARN", "0.99 uL is below 1.0 uL"),          # floor 0.5 hard / comfort 1.0 (researcher)
    ("2 vol 1.00", "passed", "PASS pipette floor"),
    ("2b vol 0.99999", "passed", "PASS pipette floor"),      # 0.99999 is 1.0 uL within tolerance
    ("3 two vols diff 4e-6", "passed", "PASS R2"),
    ("3b two vols 4.0 vs 4.0001", "passed", "PASS R2"),           # D3 tolerance
    ("4 waiver no reason", "blocked", "malformed waiver"),          # D2
    ("5 waiver empty reason", "blocked", "malformed waiver"),
    ("5b waiver reason null", "blocked", "malformed waiver"),
    ("5c waiver flag 'false'", "blocked", "malformed waiver"),
    ("6 only 0x/1x", "passed", "water in place of enzymes in #2"),
    ("7 no buffer stocks", "passed", "SKIP R1 (no buffer stocks)"),  # D4
    ("8 empty config", "blocked", "missing required key"),          # D4
    ("8b no conditions", "blocked", "no conditions"),               # D4
    ("9 tube exactly full", "WARN", "SKIP R1: common water is 0 uL"),   # WARN = DW 0 headroom
    ("9' overfill (adv_attack2)", "blocked", "SKIP R1: a tube is over-filled"),
    ("10 alias bypass", "blocked", "[config entries: E_lo, E_hi]"),  # D3
    ("11 variable volume, no waiver", "blocked", "one enzyme pipetted at 2 different volumes"),
    ("12 non-enzyme sub-uL", "blocked", "MM-A' <- G: 0.375 uL < pipette floor 0.5 uL"),
]


@pytest.mark.parametrize("row,outcome,marker", ATTACK_TABLE, ids=[r[0] for r in ATTACK_TABLE])
def test_verifier_attack_table(row, outcome, marker):
    ok, rep = rm.validate_config(attack(row))
    got = "blocked" if not ok else ("WARN" if warns(rep) else "passed")
    assert got == outcome, (got, rep)
    assert any(marker in l for l in rep), rep
    if row.startswith("9'"):                                        # D4: R1 never PASSes on an over-filled tube
        assert not any(l.startswith("PASS R1") for l in rep)


# ---------------------------------------------------------------- D1 pooled enzymes = cocktail volume
def test_d1_designs_with_pooled_sub_microlitre_enzymes():
    ok, rep = rm.validate_config(load("pooled"))                      # EnzF 0.357 uL pooled in the cocktail
    assert ok, fails(rep)
    assert any("pooled enzymes checked as common cocktail 1.607 uL/tube" in l for l in rep)
    m7 = load("ev_spec")
    bmin = ev.expand(pc.to_equal_volume_spec(m7, only_varied=True))   # EnzD 0.25 / EnzB 0.714 uL neat, pooled
    ok, rep = rm.validate_config(bmin)
    assert ok, fails(rep)
    # neat stocks: the pooled EnzD/EnzB do not fail; EnzF is added per tube (3 levels) and keeps the hard rule
    ok, rep = rm.validate_config(load("neat"))
    assert not ok
    assert not any("EnzD" in l or "EnzB" in l for l in fails(rep))
    assert any("per-tube enzyme EnzF" in l and "0.3571 uL < pipette floor" in l for l in fails(rep))


def test_d1_separate_enzyme_keeps_hard_rule_and_pooled_cocktail_is_checked():
    c = base()
    c["enzymes"]["E"]["rxn_gL"]["1x"] = 0.098                       # 0.49 uL added per tube, alone -> FAIL
    ok, rep = rm.validate_config(c)
    assert not ok and any("per-tube enzyme E" in l and "0.49 uL < pipette floor 0.5 uL" in l for l in fails(rep))
    c = base()                                                        # two tiny enzymes pooled: 0.2 + 0.2 uL
    c["enzymes"] = {"E1": {"batch": "a", "stock_gL": 10.0, "rxn_gL": {"1x": 0.04}},
                    "E2": {"batch": "b", "stock_gL": 20.0, "rxn_gL": {"1x": 0.08}}}
    for cond in c["conditions"]:
        cond["enzymes"] = {"E1": "1x", "E2": "1x"}
    ok, rep = rm.validate_config(c)
    assert not ok and any("per-tube cocktail_add common cocktail" in l and "0.4 uL < pipette floor" in l
                          for l in fails(rep))
    assert not any("per-tube enzyme" in l for l in rep)               # never the per-tube share
    route = pc.route_enzymes(pc.normalize(c), "common")
    assert route["cocktails"][0]["members"] == [1, 2] and not any(route["separate"].values())


def test_d1_cocktail_batch_draw_below_floor_fails():
    c = base()
    c["conditions"].append({"num": 3, "label": "c", "substrates": {"S": 100}, "enzymes": {"E": "1x", "T": "1x"}})
    for cond in c["conditions"]:
        cond["enzymes"] = {"E": "1x", "T": "1x"}
    c["enzymes"]["E"]["rxn_gL"]["1x"] = 1.6                          # 8 uL per tube
    c["enzymes"]["T"] = {"batch": "t", "stock_gL": 100.0, "rxn_gL": {"1x": 0.002}}   # 0.001 uL share
    ok, rep = rm.validate_config(c)
    assert not ok and any("prep cocktail 'common cocktail' <- T" in l and "pipette floor" in l for l in fails(rep))


# ---------------------------------------------------------------- D2 waivers
@pytest.mark.parametrize("flag,reason,state", [
    (True, "tested P2 pipette", "ok"), (True, None, "malformed"), (True, "", "malformed"), (True, "   ", "malformed"),
    (True, 5, "malformed"), ("false", "x", "malformed"), ("true", "x", "malformed"), (0, "x", "malformed"),
    (1, "x", "malformed"), (None, "x", "malformed"), (False, None, "none")])
def test_d2_waiver_must_be_exact(flag, reason, state):
    e = {"allow_small_volume": flag, "allow_small_volume_reason": reason}
    assert rm._waiver(e, "allow_small_volume")[0] == state
    assert rm._waiver({}, "allow_small_volume")[0] == "none"


def test_d2_valid_waiver_still_waives():
    c = base()
    c["enzymes"]["E"]["rxn_gL"]["1x"] = 0.04                         # 0.2 uL
    c["enzymes"]["E"].update(allow_small_volume=True, allow_small_volume_reason="positive-displacement pipette")
    ok, rep = rm.validate_config(c)
    assert ok, fails(rep)
    assert any("WAIVED (allow_small_volume: positive-displacement pipette)" in l for l in rep)


# ---------------------------------------------------------------- D3 one physical enzyme
def test_d3_alias_grouping_and_waiver_on_every_entry():
    c = attack("10 alias bypass")
    c["enzymes"]["E_hi"].update(allow_variable_volume=True, allow_variable_volume_reason="dose series")
    ok, rep = rm.validate_config(c)                                   # waiver on one alias only -> still FAIL
    assert not ok and any(l.startswith("FAIL E_hi/E_lo") for l in rep)
    c["enzymes"]["E_lo"].update(allow_variable_volume=True, allow_variable_volume_reason="dose series")
    ok, rep = rm.validate_config(c)
    assert ok and any("WAIVED (allow_variable_volume" in l for l in rep)
    c = attack("10 alias bypass")                                     # different batch, same alias -> grouped too
    c["enzymes"]["E_hi"].update(batch="y", enzyme="E")
    c["enzymes"]["E_lo"]["enzyme"] = "E"
    ok, rep = rm.validate_config(c)
    assert not ok and any(l.startswith("FAIL E:") for l in rep)


def test_d3_volume_tolerance():
    assert rm._same_volume(4.0, 4.0001) and rm._same_volume(4.0, 4.019) and not rm._same_volume(4.0, 4.03)
    assert rm._same_volume(0.5, 0.504) and not rm._same_volume(0.5, 0.506)


# ---------------------------------------------------------------- D5 unexpanded spec
def test_d5_unexpanded_spec_message_and_cli_autoexpand(tmp_path):
    spec = load("ev_spec")
    ok, rep = rm.validate_config(spec)
    assert not ok and len(rep) == 1 and "UNEXPANDED equal-volume spec" in rep[0]
    assert "different volumes" not in rep[0] and "add a fixed volume" not in rep[0]
    x = tmp_path / "m7.xlsx"
    sp = sf.dump(spec, tmp_path / "spec.json")
    r = subprocess.run([sys.executable, str(SK / "reaction_matrix.py"), str(sp), str(x)],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "equal-volume spec detected: expanded" in r.stdout and x.exists()
    # D7: the legacy estimate is gone from the console report
    assert "Pipetting: ~" not in r.stdout and "TOTAL 90 steps" in r.stdout


# ---------------------------------------------------------------- D6 documentation honesty
def test_d6_skill_md_states_the_verdict_and_the_hard_rules():
    s = (SK / "SKILL.md").read_text(encoding="utf-8")
    for needle in ["74 vs 88", "does NOT reduce", "28-36 tubes", "31 with one-tube", "61 vs 53", "74 vs 72", "A vs B",
                   "below 1 uL 6 -> 0", "volume settings 13 -> 5", "dilute with WATER", "cocktail",
                   "accuracy first, step count second", "floor 0.5 uL", "0.1 uL"]:
        assert needle in s, needle


# ---------------------------------------------------------------- D7 one surplus convention in the workbook
def test_d7_workbook_surplus_labels(tmp_path):
    p, x = tmp_path / "m7.json", tmp_path / "m7.xlsx"
    p.write_text(json.dumps(ev.expand(load("ev_spec"))), encoding="utf-8")
    r = subprocess.run([sys.executable, str(SK / "reaction_matrix.py"), str(p), str(x)],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout
    wb = openpyxl.load_workbook(x)
    flat = {sn: [str(c.value) for row in wb[sn].iter_rows() for c in row if c.value is not None]
            for sn in wb.sheetnames}
    allv = [v for vs in flat.values() for v in vs]
    assert not any("x1.1" in v or "*1.1," in v for v in allv)
    assert any("total (x1.2)" in v for v in flat["Reaction Matrix"])
    for sn in ("Reaction Matrix", "Enzyme Additions"):
        assert rm.SURPLUS_NOTE in flat[sn], sn


# ---------------------------------------------------------------- researcher facts: floor / comfort
def test_floor_applies_to_every_pipetting_action_and_comfort_warns():
    c = attack("12 non-enzyme sub-uL")
    ok, rep = rm.validate_config(c)
    assert not ok
    assert any("per-tube substrate S2 (#1): 0.3 uL < pipette floor" in l for l in fails(rep))
    c = base()
    c["enzymes"]["E"]["rxn_gL"]["1x"] = 0.14                          # 0.7 uL: between floor and comfort
    ok, rep = rm.validate_config(c)
    assert ok and any("0.7 uL is below 1.0 uL (pipettable, poor accuracy)" in l for l in warns(rep))
    c["pipettes"] = {"floor_uL": 0.8, "comfort_uL": 1.5}             # config-level limits
    ok, rep = rm.validate_config(c)
    assert not ok and any("0.7 uL < pipette floor 0.8 uL" in l for l in fails(rep))
    c["pipettes"] = {"floor_uL": 2.0, "comfort_uL": 1.0}             # inconsistent limits are refused
    ok, rep = rm.validate_config(c)
    assert not ok and any(l.startswith("FAIL pipettes:") for l in rep)
    assert pc.limits({}) == {"floor_uL": 0.5, "comfort_uL": 1.0, "resolution_uL": 0.1, "max_settings_per_tube": 4}


def test_equal_volume_design_has_no_addition_below_comfort_and_reports_settings():
    s = pc.count(load("ev_spec"))
    assert (s["below_floor"], s["below_comfort"]) == (0, 0)
    assert s["settings_per_tube"] == {t: 5 for t in range(1, 12)} and s["settings_run"] == 5
    assert s["identical_sequence"]


# ---------------------------------------------------------------- researcher facts: same volume in every tube
def ne_toy():
    c = base()
    c["enzymes"] = {"E1": {"batch": "a", "stock_gL": 10.0, "rxn_gL": {"1x": 0.8, "0x": 0}},
                    "E2": {"batch": "b", "stock_gL": 10.0, "rxn_gL": {"1x": 0.6, "0x": 0}},
                    "E3": {"batch": "c", "stock_gL": 10.0, "rxn_gL": {"1x": 0.4, "0x": 0}}}
    c["conditions"] = [{"num": i, "label": str(i), "substrates": {"S": 100},
                        "enzymes": {"E1": "1x", "E2": "1x", "E3": "1x" if i < 3 else "0x"}} for i in (1, 2)]
    c["conditions"].append({"num": 3, "label": "NE", "substrates": {"S": 100},
                            "enzymes": {"E1": "0x", "E2": "0x", "E3": "0x"}})
    return c


def test_ne_control_gets_water_in_place_with_identical_volumes(tmp_path):
    plan = pc.build_plan(ne_toy())
    ref = [(s.volume_uL) for s in plan["steps"] if s.phase == "run" and s.target == "#1"
           and s.kind in ("enzyme", "cocktail_add")]
    wip = [(s.volume_uL) for s in plan["steps"] if s.phase == "run" and s.target == "#3"]
    assert [v for _, v in plan["water_in_place"][3]] == ref and plan["topup"][3] == 0.0
    assert not any(s.kind == "dw" for s in plan["steps"] if s.target == "#3")
    rp = pc.rounded_plan(plan)
    assert pc.volume_settings(rp)["identical_sequence"]
    assert len(wip) == len(ref) + 2                                   # MM-A, substrate, then the water slots
    off = pc.build_plan(ne_toy(), water_in_place=False)
    assert 3 not in off["water_in_place"] and off["topup"][3] > 0
    p, x = tmp_path / "ne.json", tmp_path / "ne.xlsx"
    p.write_text(json.dumps(ne_toy()), encoding="utf-8")
    r = subprocess.run([sys.executable, str(SK / "reaction_matrix.py"), str(p), str(x)],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout
    ea = [[c.value for c in row] for row in openpyxl.load_workbook(x)["Enzyme Additions"].iter_rows()]
    assert any(row[0] == "#3" and row[1] == "water_in_place" for row in ea)


def test_uniformity_warnings():
    c = base()                                                        # S added at 2 volumes, DW at 2 volumes
    c["conditions"][1]["substrates"]["S"] = 60
    ok, rep = rm.validate_config(c)
    assert ok and any(l.startswith("WARN uniformity: S is added at 2 different volumes") for l in rep)
    assert any(l.startswith("WARN uniformity: DW top-up is added at") or "DW top-up" in l for l in warns(rep)) \
        or pc.rounded_plan(pc.build_plan(c))["dw"][2] > 0
    c = load("ev_spec")                                               # 5 settings per tube > 4
    ok, rep = rm.validate_config(ev.expand(c))
    assert ok and any("11 tube(s) need more than 4 distinct volume settings" in l for l in rep)
    c["pipettes"] = {"max_settings_per_tube": 5}
    ok, rep = rm.validate_config(ev.expand(c))
    assert not any("distinct volume settings --" in l for l in rep)


# ---------------------------------------------------------------- researcher facts: rounding to 0.1 uL
def test_rounding_closes_every_tube():
    for cfg in (ev.expand(load("ev_spec")), load("pooled"), ne_toy()):
        rp = pc.rounded_plan(pc.build_plan(cfg))
        V = float(cfg["total_volume_uL"])
        for t, rows in rp["tubes"].items():
            assert sum(r[3] for r in rows) == pytest.approx(V, abs=1e-9) or t in rp["dropped"]
            assert all(abs(r[3] * 10 - round(r[3] * 10)) < 1e-6 for r in rows)    # multiples of 0.1 uL
    assert pc._rnd(1.05, 0.1) == 1.1 and pc._rnd(0.549, 0.1) == 0.5


@pytest.mark.parametrize("final_mM,level", [(12.0, "PASS"), (21.0, "WARN"), (11.0, "FAIL")])
def test_rounding_deviation_flags(final_mM, level):
    # one tube, substrate added directly: 12 mM -> 0.6 uL exact (0 %), 21 mM -> 1.05 -> 1.1 uL (+4.8 %),
    # 11 mM -> 0.55 -> 0.6 uL (+9.1 %)
    c = base()
    c["conditions"] = [{"num": 1, "label": "a", "substrates": {"S": 100, "X": final_mM}, "enzymes": {"E": "1x"}}]
    c["stocks"]["X"] = {"conc_mM": 1000, "type": "substrate"}
    ok, rep = rm.validate_config(c)
    line = [l for l in rep if "rounding" in l]
    if level == "PASS":
        assert ok and any(l.startswith("PASS rounding") for l in line), line
    elif level == "WARN":
        assert ok and any(l.startswith("WARN rounding: X deviates +4.76 %") for l in line), line
    else:
        assert not ok and any(l.startswith("FAIL rounding: X deviates +9.09 %") for l in line), line
