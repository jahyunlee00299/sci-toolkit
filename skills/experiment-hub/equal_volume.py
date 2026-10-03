"""Expand an 'equal-volume enzyme' config into a plain reaction_matrix.py config.

Convention: enzyme levels (1x, 2x, 4x ...) are NOT made by pipetting different
volumes of one stock. Each level gets its own DILUTED WORKING STOCK (the lab stock diluted with plain
WATER, not the enzyme storage buffer), and every tube receives the SAME volume of it (no sub-microlitre
additions, few pipette volume settings). pipette_count.py measures what this costs in steps: the run phase
gets shorter (with the common water in MM-A only the tubes missing an enzyme need a DW top-up) but every
working stock adds 2 steps + 1 mix of prep, so for a small design the TOTAL step count is higher. A level's working-stock concentration is
    working_gL = rxn_gL * total_volume_uL / equal_volume_uL
and must not exceed the undiluted lab stock (you cannot concentrate a stock).

Spec (in the config 'enzymes' block): {"batch", "stock_gL" (undiluted lab stock), "equal_volume_uL",
"rxn_gL": {"1x": .., "4x": ..}}.  The expander replaces each enzyme by one pseudo-enzyme per level that
is used by some condition: stock_gL = working_gL, source_stock_gL = undiluted stock, enzyme = real name
(for canon_gate), dilution_x = undiluted / working, diluent = "water". Conditions keep their {enzyme: level} entries.
allow_small_volume / allow_variable_volume (+ *_reason) are carried over to every pseudo-enzyme.

CLI: python equal_volume.py spec.json expanded.json
"""
from __future__ import annotations

import copy
import json
import sys


def expand(cfg: dict) -> dict:
    out = copy.deepcopy(cfg)
    total = float(cfg["total_volume_uL"])
    new_enz: dict = {}
    for name, info in cfg["enzymes"].items():
        vol = info.get("equal_volume_uL")
        if vol is None:                       # plain enzyme: keep as is
            new_enz[name] = info
            continue
        used = {c["enzymes"].get(name) for c in cfg["conditions"]} - {None}
        for level in sorted(used, key=lambda s: (s != "0x", s)):
            if level == "0x":
                continue
            rxn = float(info["rxn_gL"][level])
            work = rxn * total / float(vol)
            if work > float(info["stock_gL"]) * 1.0000001:
                raise ValueError(f"{name} {level}: working stock {work:.3f} g/L exceeds the lab stock "
                                 f"{info['stock_gL']} g/L at {vol} uL per tube; raise equal_volume_uL")
            key = f"{name} [{level}]"
            new_enz[key] = {"batch": info.get("batch"), "enzyme": name,
                            "stock_gL": round(work, 6), "source_stock_gL": info["stock_gL"],
                            "dilution_x": round(float(info["stock_gL"]) / work, 4),
                            "equal_volume_uL": vol, "level": level, "diluent": "water",
                            "rxn_gL": {level: rxn, "0x": 0}}
            for k in ("allow_small_volume", "allow_small_volume_reason",
                      "allow_variable_volume", "allow_variable_volume_reason"):
                if k in info:
                    new_enz[key][k] = info[k]
    out["enzymes"] = new_enz
    for cond in out["conditions"]:
        enz = {}
        for ename, lvl in cond["enzymes"].items():
            spec = cfg["enzymes"][ename]
            if spec.get("equal_volume_uL") is None:
                enz[ename] = lvl
        for key, e in new_enz.items():
            if "level" in e:
                enz[key] = e["level"] if cond["enzymes"].get(e["enzyme"]) == e["level"] else "0x"
        cond["enzymes"] = enz
    return out


if __name__ == "__main__":
    src, dst = sys.argv[1], sys.argv[2]
    with open(src, encoding="utf-8") as f:
        spec = json.load(f)
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(expand(spec), f, ensure_ascii=False, indent=2)
    print("expanded ->", dst)
