"""SYNTHETIC fixtures for the experiment-hub pipetting tests. No real lab data: every name, stock, batch
label and concentration here is invented, chosen only so the configs exercise the same behaviours as a real
multi-enzyme design:

  ev_spec()       11 tubes, five fixed components in the MM-A premix, seven enzymes as an equal-volume spec
                  (two of them at three levels), a no-enzyme control, a solid weighed per tube. Expanded it
                  passes; two small premix draws (CofactorX, CofactorY) give rounding WARNs at the default
                  MM-A margin and none at premix.extra_rxns = 5.
  neat_config()   the same design with every enzyme pipetted from its undiluted stock: blocked (EnzF added
                  per tube below the 0.5 uL floor and at three volumes) while the pooled small enzymes pass.
  pooled_config() 10 tubes, two enzymes at one level pooled in a common cocktail (EnzF alone would be
                  0.357 uL per tube): passes because the cocktail volume is what is pipetted.
  canon_config()  neat_config() with working-stock salts, for canon_gate (agrees with the example registry).
  write_params_xlsx(path)  a Params sheet that contradicts the example registry (CofactorX written in uM).

The example registry these agree / disagree with is ../canonical_constants.example.toml.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

V = 50
SOLID_NOTE = "SolidT 200 mM = 1.121 mg solid per tube, added first"

#            lab stock g/L, batch,   rxn g/L per level,                     equal volume uL
ENZYMES = {"EnzA": (12.0, "100001", {"1x": 1.0}, 5),
           "EnzB": (14.0, "100002", {"1x": 0.2}, 2),
           "EnzC": (3.0, "100003", {"1x": 0.1}, 2),
           "EnzD": (40.0, "100004", {"1x": 0.2}, 2),
           "EnzE": (3.5, "100005", {"1x": 0.2}, 3),
           "EnzF": (70.0, "100006", {"1x": 0.5, "2x": 1.0, "4x": 2.0}, 2),
           "EnzG": (40.0, "100007", {"1x": 1.0, "2x": 2.0, "4x": 4.0}, 5.5)}

# tube -> (EnzF level, EnzG level); every other enzyme at 1x; tube 11 = no-enzyme control
LEVELS = {1: ("1x", "1x"), 2: ("1x", "1x"), 3: ("4x", "1x"), 4: ("4x", "1x"), 5: ("1x", "4x"), 6: ("1x", "4x"),
          7: ("4x", "4x"), 8: ("4x", "4x"), 9: ("2x", "2x"), 10: ("2x", "2x"), 11: None}

PREMIX = {"Tris": {"conc_mM": 1000, "type": "buffer", "final_mM": 200},
          "SaltM": {"conc_mM": 1000, "type": "buffer", "final_mM": 5},
          "SaltC": {"conc_mM": 100, "type": "buffer", "final_mM": 1},
          "CofactorY": {"conc_mM": 100, "type": "buffer", "final_mM": 0.25},
          "CofactorX": {"conc_mM": 10, "type": "buffer", "final_mM": 0.015}}
SUBSTRATES = {"SubA": {"conc_mM": 1000, "type": "substrate"}, "SubB": {"conc_mM": 1800, "type": "substrate"}}


def _conditions():
    out = []
    for t, lv in LEVELS.items():
        enz = {n: "0x" for n in ENZYMES} if lv is None else {n: "1x" for n in ENZYMES}
        if lv:
            enz["EnzF"], enz["EnzG"] = lv
        out.append({"num": t, "group": "control" if lv is None else "series", "label": f"tube {t}",
                    "substrates": {"SubA": 100, "SubB": 200}, "enzymes": enz, "note": SOLID_NOTE})
    return out


def _base(title):
    return {"title": title, "date": "000000", "total_volume_uL": V, "temperature_C": 30,
            "timepoints": ["1 h", "2 h", "4 h", "8 h", "24 h", "48 h"],
            "stocks": {**copy.deepcopy(PREMIX), **copy.deepcopy(SUBSTRATES)},
            "sampling": {"volume_uL": 5, "dilution": "20x", "quench": "acid", "analysis": "HPLC",
                         "targets": ["Product"]},
            "conditions": _conditions()}


def ev_spec() -> dict:
    c = _base("synthetic equal-volume design")
    c["enzymes"] = {n: {"batch": b, "stock_gL": s, "equal_volume_uL": ev, "rxn_gL": dict(r)}
                    for n, (s, b, r, ev) in ENZYMES.items()}
    return c


def neat_config() -> dict:
    c = _base("synthetic neat-stock design")
    c["enzymes"] = {n: {"batch": b, "stock_gL": s, "rxn_gL": {**r, "0x": 0}} for n, (s, b, r, _) in ENZYMES.items()}
    return c


def canon_config() -> dict:
    c = neat_config()
    st = c["stocks"]
    st["SaltM (working)"] = {"conc_mM": 100, "type": "buffer", "final_mM": 5}
    st["SaltC (working)"] = {"conc_mM": 20, "type": "buffer", "final_mM": 1}
    del st["SaltM"], st["SaltC"]
    st["CofactorY"]["conc_mM"] = 10
    return c


def pooled_config() -> dict:
    stocks = {"Tris": {"conc_mM": 1000, "type": "buffer", "final_mM": 200},
              "CofactorX": {"conc_mM": 10, "type": "buffer", "final_mM": 0.015},
              "SubR": {"conc_mM": 100, "type": "substrate"},
              "SaltM (working)": {"conc_mM": 100, "type": "substrate"},
              "SaltC (working)": {"conc_mM": 20, "type": "substrate"},
              "AdditiveP": {"conc_mM": 500, "type": "substrate"},
              "AdditiveQ": {"conc_mM": 20, "type": "substrate"}}
    rows = [(0, 0), (10.8, 0), (21.6, 0), (43.2, 0), (0, 0.66), (0, 1.33), (0, 2.66), (21.6, 1.33)]
    conds = []
    for i, (p, q) in enumerate(rows, 1):
        conds.append({"num": i, "substrates": {"SubR": 10, "SaltM (working)": 5, "SaltC (working)": 1,
                                               "AdditiveP": p, "AdditiveQ": q},
                      "enzymes": {"EnzF": "1x", "EnzG": "1x"}})
    conds.append({"num": 9, "substrates": {"SubR": 10, "SaltM (working)": 0, "SaltC (working)": 0, "AdditiveP": 0,
                                           "AdditiveQ": 0}, "enzymes": {"EnzF": "1x", "EnzG": "1x"}})
    conds.append({"num": 10, "substrates": {"SubR": 10, "SaltM (working)": 5, "SaltC (working)": 1, "AdditiveP": 0,
                                            "AdditiveQ": 0}, "enzymes": {"EnzF": "0x", "EnzG": "0x"}})
    return {"title": "synthetic pooled-cocktail design", "date": "000000", "total_volume_uL": V,
            "temperature_C": 30, "timepoints": ["1.5 h", "3 h"], "stocks": stocks,
            "enzymes": {"EnzF": {"batch": "100006", "stock_gL": 70.0, "rxn_gL": {"1x": 0.5, "0x": 0}},
                        "EnzG": {"batch": "100007", "stock_gL": 40.0, "rxn_gL": {"1x": 1.0, "0x": 0}}},
            "conditions": conds}


def dump(cfg: dict, path: Path) -> Path:
    Path(path).write_text(json.dumps(cfg, indent=1), encoding="utf-8")
    return Path(path)


def write_params_xlsx(path: Path) -> Path:
    """A workbook whose Params sheet writes CofactorX in uM (10 uM stock, 0.015 uM final) -- the superseded
    values of the example registry -- plus agreeing enzyme stocks and a differing SaltM working stock."""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Params"
    rows = [["synthetic Params sheet", None, None, None],
            ["Component", "Stock conc", "Unit", "Note"],
            ["Tris", 1000, "mM", "1 M stock"],
            ["SaltM", 1000, "mM", "1 M stock"],
            ["CofactorY", 100, "mM", None],
            ["EnzA", 12.0, "g/L", "batch 100001"],
            ["EnzB", 14.0, "g/L", None],
            ["Component", "Final", "Unit", "Memo"],
            ["Tris", 200, "mM", None],
            ["SaltM", 5, "mM", None],
            ["Setting", "Value", "Unit", "Memo"],
            ["CofactorX_EXISTING_STOCK", 10, "uM", "older note"],
            ["CofactorX_WORKING_STOCK", 1, "uM", "derived dilution, ignored by the gate"],
            ["CofactorX_FINAL", 0.015, "uM", None],
            ["RXN_VOL", 100, "uL", None]]
    for r in rows:
        ws.append(r)
    wb.create_sheet("Reaction_Mix")
    wb.properties.creator = "synthetic-fixture"
    wb.properties.lastModifiedBy = "synthetic-fixture"
    wb.save(path)
    return Path(path)
