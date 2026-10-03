"""Pipette-count model for reaction_matrix.py configs (experiment-hub).

Counts every liquid-handling step a config implies, so "design X needs less pipetting" is a measured
number, not an impression. The model is deliberately explicit and dumpable (``--steps out.csv``) so an
independent reviewer can recount it by hand.

Counting rules
  PREP (done once, before the tubes)
    * enzyme working stock (lab stock diluted with WATER)  = 2 pipetting steps (lab stock, water) + 1 mix
    * MM-A premix = 1 step per buffer component (+1 for the common water, rule R1) + 1 mix
    * substrate sub-mix (reaction_matrix.analyze_master_mixes groups of >1 tube) = 1 step per non-zero component + 1 mix
    * enzyme cocktail = 1 step per component (+1 water when it is volume-equalised) + 1 mix
  RUN (per tube)
    * MM-A 1 step; sub-mix 1 step OR 1 step per non-zero substrate; DW top-up 1 step if > 0;
      enzymes: 1 step per separate addition, a cocktail counts 1
  WEIGHING (a solid weighed per tube) is counted separately and is NOT a pipetting step.
  Mixes are reported separately; "total steps" = pipetting steps, "total ops" = steps + mixes.

Volume margins (parameters, printed with every report)
  MM-A is made for n_tubes + extra reactions (config "premix": {"extra_rxns": N}, default 3, as
  reaction_matrix.generate_excel does; a larger N can make the premix draws land on the 0.1 uL grid); a sub-mix or a
  cocktail for count x SURPLUS (1.2); every intermediate vessel (working stock, cocktail) gets +DEAD uL
  (10) on top, and a working stock is made in whole microlitres (ceil). Lab-stock consumption sums the
  draws from each undiluted lab stock: direct per-tube additions x SURPLUS, plus the draws that build
  premixes, sub-mixes, working stocks and cocktails.

Enzyme cocktail modes (config key "enzyme_cocktail", CLI --cocktail)
  none            every enzyme addition is a separate step
  common          (default) additions that are identical in every
                  enzyme-containing tube are pooled into ONE common cocktail; the rest stay separate
  per_condition   one cocktail per distinct enzyme fingerprint (>= 2 tubes) assembled from the
                  sources the config names (working stocks for an equal-volume design) -> 1 enzyme
                  addition per tube
  per_condition_direct  as per_condition but each cocktail is built from the UNDILUTED lab stocks
                  plus water to a common per-tube volume (no working-stock dilutions at all)

CLI
  python pipette_count.py config.json [--cocktail MODE] [--no-common-water] [--steps out.csv] [--json]
  python pipette_count.py config.json --compare      # designs A / B / C / C-direct side by side
A config with "equal_volume_uL" (equal_volume.py spec) is expanded first.
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import math
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path

SURPLUS = 1.2
DEAD_UL = 10.0
MM_A_EXTRA_RXNS = 3
EPS_UL = 5e-4          # a residual below this is "nothing to pipette"
NEAT_TOL = 1.005       # a "dilution" below 0.5 % (under pipetting accuracy) is used neat, no prep step
COCKTAIL_MODES = ("none", "common", "per_condition", "per_condition_direct")
DEFAULT_FLOOR_UL = 0.5        # lab's smallest pipette is 2.5 uL: below 0.5 uL = cannot be pipetted (HARD FAIL)
DEFAULT_COMFORT_UL = 1.0      # 0.5-1.0 uL = possible but poor accuracy (WARN)
DEFAULT_RESOLUTION_UL = 0.1   # displayed / pipetted volumes are rounded to this
DEFAULT_MAX_SETTINGS = 4      # more distinct volume settings than this in one tube -> WARN (beginner-proof)
DEV_WARN, DEV_FAIL = 0.02, 0.05   # concentration deviation caused by the rounding


@dataclass
class Step:
    phase: str      # prep | run
    kind: str       # dilution | mm_a | submix | cocktail | substrate | dw | enzyme | cocktail_add
    target: str     # vessel receiving the liquid (tube #n, working stock, MM-A ...)
    source: str
    volume_uL: float


# ---------------------------------------------------------------- helpers
def _floor4(x: float) -> float:
    return math.floor(x * 1e4 + 1e-9) / 1e4


def is_spec(cfg: dict) -> bool:
    return any(e.get("equal_volume_uL") is not None and "level" not in e for e in cfg["enzymes"].values())


def normalize(cfg: dict) -> dict:
    """Expand an equal-volume spec; otherwise return a deep copy."""
    if is_spec(cfg):
        import equal_volume
        return equal_volume.expand(cfg)
    return copy.deepcopy(cfg)


def mm_a_extra(cfg: dict) -> int:
    """MM-A premix margin in reactions: config "premix": {"extra_rxns": N} (default MM_A_EXTRA_RXNS = 3).
    MM-A is made for n_tubes + N reactions."""
    raw = (cfg.get("premix") or {}).get("extra_rxns", MM_A_EXTRA_RXNS)
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
        raise ValueError(f"premix.extra_rxns must be a non-negative integer, got {raw!r}")
    return raw


def lab_stock_of(einfo: dict) -> float:
    return float(einfo.get("source_stock_gL", einfo["stock_gL"]))


def real_name(name: str, einfo: dict) -> str:
    return einfo.get("enzyme", name)


def weighings(cfg: dict) -> list[tuple[int, str, float]]:
    """(tube, solid, mg) per weighing event: config 'weighed_solids' or 'NAME ... X mg solid' in a note."""
    out = []
    explicit = cfg.get("weighed_solids")
    for cond in cfg["conditions"]:
        if explicit:
            for s in explicit:
                out.append((cond["num"], s["name"], float(s.get("per_tube_mg", 0))))
            continue
        m = re.search(r"([A-Za-z][\w,\-]*)\s+(?:[\d.]+\s*mM\s*=\s*)?([\d.]+)\s*mg solid", cond.get("note", ""))
        if m:
            out.append((cond["num"], m.group(1), float(m.group(2))))
    return out


# ---------------------------------------------------------------- core model
def enzyme_additions(cfg: dict) -> dict[int, list[dict]]:
    """Per tube: list of {source, enzyme, level, vol} for every non-zero enzyme addition."""
    vol = float(cfg["total_volume_uL"])
    out = {}
    for cond in cfg["conditions"]:
        adds = []
        for ename, level in cond["enzymes"].items():
            e = cfg["enzymes"][ename]
            rxn = float(e["rxn_gL"].get(level, 0) or 0)
            if rxn <= 0:
                continue
            adds.append({"source": ename, "enzyme": real_name(ename, e), "level": level,
                         "vol": rxn * vol / float(e["stock_gL"]), "rxn_gL": rxn,
                         "lab_gL": lab_stock_of(e)})
        out[cond["num"]] = adds
    return out


def cocktail_scale(per_tube: float, n_tubes: int) -> tuple[float, float]:
    """(make_uL, scale) of a cocktail made for n_tubes x SURPLUS + DEAD_UL; a component's batch draw is
    its per-tube uL x scale."""
    make = per_tube * n_tubes * SURPLUS + DEAD_UL
    return make, make / per_tube


def route_enzymes(cfg: dict, cocktail: str) -> dict:
    """Decide how every non-zero enzyme addition reaches the tubes (the single classification used by the
    pipette count AND by reaction_matrix.validate_config's minimum-volume rule).

    cfg must already be normalized (no unexpanded equal-volume spec). Returns
      cocktails: [{name, members, per_tube, comps {source: per-tube uL}, water_per_tube, make_uL, scale}]
                 -> what is pipetted is the cocktail (per_tube into each tube) and comps x scale (batch draws)
      separate:  {tube: [(source, uL)]}   -> pipetted individually into the tube at exactly that volume
      tube_enzyme_vol: {tube: uL of enzyme liquid in the tube}
      adds, src_info, enz_tubes: the raw additions (enzyme_additions) for reuse."""
    if cocktail not in COCKTAIL_MODES:
        raise ValueError(f"enzyme_cocktail must be one of {COCKTAIL_MODES}, got {cocktail!r}")
    V = float(cfg["total_volume_uL"])
    conds = cfg["conditions"]
    adds = enzyme_additions(cfg)
    enz_tubes = [c["num"] for c in conds if adds[c["num"]]]
    tube_enzyme_vol = {c["num"]: sum(a["vol"] for a in adds[c["num"]]) for c in conds}
    src_info = {a["source"]: a for al in adds.values() for a in al}
    cocktails: list[dict] = []
    separate: dict[int, list[tuple[str, float]]] = {c["num"]: [] for c in conds}

    def ck(name, members, per_tube, comps, water_per_tube=0.0):
        make, scale = cocktail_scale(per_tube, len(members))
        cocktails.append({"name": name, "members": list(members), "per_tube": per_tube, "comps": dict(comps),
                          "water_per_tube": water_per_tube, "make_uL": make, "scale": scale})

    if cocktail == "none":
        for t in enz_tubes:
            separate[t] = [(a["source"], a["vol"]) for a in adds[t]]
    elif cocktail == "common":
        sigs = [set((a["source"], round(a["vol"], 6)) for a in adds[t]) for t in enz_tubes]
        common = set.intersection(*sigs) if sigs else set()
        if len(common) >= 2:
            comps = {s: v for s, v in common}
            ck("common cocktail", enz_tubes, sum(comps.values()), comps)
        else:
            common = set()
        for t in enz_tubes:
            separate[t] = [(a["source"], a["vol"]) for a in adds[t]
                           if (a["source"], round(a["vol"], 6)) not in common]
    else:   # per_condition / per_condition_direct
        direct = cocktail == "per_condition_direct"
        fp = defaultdict(list)
        for t in enz_tubes:
            if direct:
                key = tuple(sorted((a["enzyme"], round(a["rxn_gL"], 6)) for a in adds[t]))
            else:
                key = tuple(sorted((a["source"], round(a["vol"], 6)) for a in adds[t]))
            fp[key].append(t)
        if direct:   # neat volumes; equalise every cocktail to the largest per-tube volume
            neat = {t: {a["enzyme"]: a["rxn_gL"] * V / a["lab_gL"] for a in adds[t]} for t in enz_tubes}
            per_tube_eq = max(sum(neat[t].values()) for t in enz_tubes) if enz_tubes else 0.0
            for t in enz_tubes:
                tube_enzyme_vol[t] = per_tube_eq
        for i, (key, members) in enumerate(sorted(fp.items(), key=lambda kv: kv[1][0]), 1):
            t0 = members[0]
            if direct:
                comps = {f"{e} (lab stock)": v for e, v in neat[t0].items()}
                if len(members) >= 2:
                    ck(f"cocktail-{i}", members, per_tube_eq, comps, per_tube_eq - sum(comps.values()))
                else:
                    separate[t0] = list(comps.items())
                    tube_enzyme_vol[t0] = sum(comps.values())
            else:
                comps = {a["source"]: a["vol"] for a in adds[t0]}
                if len(members) >= 2:
                    ck(f"cocktail-{i}", members, sum(comps.values()), comps)
                else:
                    separate[t0] = list(comps.items())
    return {"cocktails": cocktails, "separate": separate, "tube_enzyme_vol": tube_enzyme_vol,
            "adds": adds, "src_info": src_info, "enz_tubes": enz_tubes}


def limits(cfg: dict) -> dict:
    """Instrument limits (config block "pipettes"; defaults = a typical lab set whose smallest pipette is
    2.5 uL -> below 0.5 uL cannot be pipetted, 0.5-1.0 uL possible but poor accuracy).
    Legacy keys min_addition_uL / warn_addition_uL are read as floor / comfort when "pipettes" omits them."""
    p = cfg.get("pipettes") or {}
    floor = float(p.get("floor_uL", cfg.get("min_addition_uL", DEFAULT_FLOOR_UL)))
    comfort = p.get("comfort_uL", cfg.get("warn_addition_uL"))
    out = {"floor_uL": floor,
           "comfort_uL": float(comfort) if comfort is not None else max(DEFAULT_COMFORT_UL, floor),
           "resolution_uL": float(p.get("resolution_uL", DEFAULT_RESOLUTION_UL)),
           "max_settings_per_tube": int(p.get("max_settings_per_tube", DEFAULT_MAX_SETTINGS))}
    if not (0 < out["floor_uL"] <= out["comfort_uL"]) or out["resolution_uL"] <= 0:
        raise ValueError(f"pipettes: need 0 < floor_uL <= comfort_uL and resolution_uL > 0, got {out}")
    return out


def build_plan(cfg_in: dict, cocktail: str | None = None, common_water: bool | None = None,
               water_in_place: bool | None = None) -> dict:
    """Return {'steps': [Step], 'mixes': [...], 'weighings': [...], 'lab_uL': {...}, ...}.

    water_in_place (config "control_water_in_place", default true): a tube without any enzyme (no-enzyme
    control) receives WATER in the same volumes, in the same order, as an enzyme tube receives its enzyme
    additions (identical volume sequence, different liquid), instead of one odd DW top-up.
    The common water in MM-A (R1) is the tightest tube's residual unless that leaves a DW top-up below the
    pipette floor somewhere; then it is lowered so every top-up is 0 or >= floor (_assign_water)."""
    from reaction_matrix import analyze_master_mixes
    cfg = normalize(cfg_in)
    cocktail = cocktail or cfg.get("enzyme_cocktail", "common")
    if cocktail not in COCKTAIL_MODES:
        raise ValueError(f"enzyme_cocktail must be one of {COCKTAIL_MODES}, got {cocktail!r}")
    if common_water is None:
        common_water = bool(cfg.get("common_water_in_mm_a", True))
    if water_in_place is None:
        water_in_place = bool(cfg.get("control_water_in_place", True))
    V = float(cfg["total_volume_uL"])
    conds = cfg["conditions"]
    n = len(conds)
    if not n:
        raise ValueError("config has no conditions: nothing to count")
    stocks = cfg["stocks"]
    buffers = {k: v for k, v in stocks.items() if v["type"] == "buffer"}
    steps: list[Step] = []
    mixes: list[str] = []
    lab = Counter()          # undiluted lab-stock draws, uL

    # ---- MM-A (buffers) -------------------------------------------------
    mm_per = {b: float(i["final_mM"]) * V / float(i["conc_mM"]) for b, i in buffers.items()}
    mm_a_vol = sum(mm_per.values())

    # ---- substrates: reaction_matrix grouping -------------------------------
    _, _, groups = analyze_master_mixes(cfg)
    sub_vol_tube = {}
    tube_sub_steps = {}
    submix_of = {}
    for key, nums in groups.items():
        comps = {s: float(c) * V / float(stocks[s]["conc_mM"]) for s, c in key if float(c) > 0}
        for t in nums:
            sub_vol_tube[t] = sum(comps.values())
        if len(nums) > 1 and comps:
            sm = f"SM[{','.join('#%d' % t for t in nums)}]"
            for s, v in comps.items():
                steps.append(Step("prep", "submix", sm, s, v * len(nums) * SURPLUS))
                lab[s] += v * len(nums) * SURPLUS
            mixes.append(sm)
            for t in nums:
                submix_of[t] = (sm, sum(comps.values()))
        else:
            for t in nums:
                tube_sub_steps[t] = comps

    # ---- enzymes (route_enzymes: the one classification shared with validate_config) -------
    route = route_enzymes(cfg, cocktail)
    adds, enz_tubes, src_info = route["adds"], route["enz_tubes"], route["src_info"]
    tube_enzyme_vol = route["tube_enzyme_vol"]
    need = Counter()          # uL needed from each source vessel (working stock / neat stock)
    tube_enzyme_steps: dict[int, list[tuple[str, float]]] = {c["num"]: [] for c in conds}
    for ckt in route["cocktails"]:
        for s, v in ckt["comps"].items():
            steps.append(Step("prep", "cocktail", ckt["name"], s, v * ckt["scale"]))
            need[s] += v * ckt["scale"]
        if ckt["water_per_tube"] > EPS_UL:
            steps.append(Step("prep", "cocktail", ckt["name"], "water", ckt["water_per_tube"] * ckt["scale"]))
        mixes.append(ckt["name"])
        for t in ckt["members"]:
            tube_enzyme_steps[t].append((ckt["name"], ckt["per_tube"]))
    for t, lst in route["separate"].items():
        for s, v in lst:
            tube_enzyme_steps[t].append((s, v))
            need[s] += v * SURPLUS

    # ---- working stocks (any source more dilute than its lab stock) ---------
    working = []
    for src, uL in sorted(need.items()):
        if src.endswith(" (lab stock)"):
            lab[src.replace(" (lab stock)", "")] += uL
            continue
        a = src_info[src]
        e = cfg["enzymes"][src]
        dil = lab_stock_of(e) / float(e["stock_gL"])
        if dil > NEAT_TOL:
            make = math.ceil(uL + DEAD_UL)
            stock_uL = make / dil
            steps.append(Step("prep", "dilution", f"WS {src}", f"{a['enzyme']} (lab stock)", stock_uL))
            steps.append(Step("prep", "dilution", f"WS {src}", "water", make - stock_uL))
            mixes.append(f"WS {src}")
            lab[a["enzyme"]] += stock_uL
            working.append({"working_stock": src, "enzyme": a["enzyme"], "lab_gL": lab_stock_of(e),
                            "dilution_x": dil, "working_gL": float(e["stock_gL"]),
                            "uL_per_tube": round(a["vol"], 4), "needed_uL": uL, "make_uL": make,
                            "lab_stock_uL": stock_uL, "water_uL": make - stock_uL})
        else:
            lab[a["enzyme"]] += uL

    # ---- DW / common water (R1) -------------------------------------------
    # every component rounded to 4 dp, exactly as the workbook's ROUND(...,4) cells, so the common water
    # computed here closes the workbook's tightest tube to 0.0000 (never -0.0001)
    r4 = lambda x: round(x, 4)
    mm_a_r4 = sum(r4(v) for v in mm_per.values())
    residual = {}
    for c in conds:
        t = c["num"]
        sub_r4 = sum(r4(float(cc) * V / float(stocks[s]["conc_mM"])) for s, cc in c["substrates"].items())
        enz_r4 = (r4(tube_enzyme_vol[t]) if cocktail == "per_condition_direct"
                  else sum(r4(a["vol"]) for a in adds[t]))
        residual[t] = r4(V - mm_a_r4 - sub_r4 - enz_r4)
    min_res = min(residual.values()) if residual else 0.0
    feasible = min_res >= -1e-9
    floor = limits(cfg)["floor_uL"]
    # no MM-A (no buffer component) -> nowhere to carry the common water: every tube keeps its own DW
    water0 = _floor4(max(min_res, 0.0)) if (common_water and mm_per) else 0.0
    water, topup, in_place = _assign_water(residual, water0, floor, feasible, water_in_place, enz_tubes,
                                           tube_enzyme_steps, [c["num"] for c in conds])
    topup_no_r1 = {t: (r if r > EPS_UL else 0.0) for t, r in residual.items()}
    n_mm = n + mm_a_extra(cfg)

    for b, v in mm_per.items():
        steps.append(Step("prep", "mm_a", "MM-A", b, v * n_mm))
        lab[b] += v * n_mm
    if water > EPS_UL:
        steps.append(Step("prep", "mm_a", "MM-A", "water (common)", water * n_mm))
    if mm_per:
        mixes.append("MM-A")

    # ---- run steps per tube ------------------------------------------------
    for c in conds:
        t = c["num"]
        tgt = f"#{t}"
        if mm_per:
            steps.append(Step("run", "mm_a", tgt, "MM-A", mm_a_vol + water))
        if t in submix_of:
            steps.append(Step("run", "substrate", tgt, submix_of[t][0], submix_of[t][1]))
        else:
            for s, v in tube_sub_steps.get(t, {}).items():
                steps.append(Step("run", "substrate", tgt, s, v))
                lab[s] += v * SURPLUS
        if topup[t] > 0:
            steps.append(Step("run", "dw", tgt, "water", topup[t]))
        for src, v in tube_enzyme_steps[t]:
            kind = "cocktail_add" if src.startswith(("cocktail", "common cocktail")) else "enzyme"
            steps.append(Step("run", kind, tgt, src, v))
        for src, v in in_place.get(t, []):
            steps.append(Step("run", "water_in_place", tgt, src, v))

    return {"config": cfg, "cocktail": cocktail, "common_water": common_water, "water_in_place": in_place,
            "route": route, "steps": steps,
            "mixes": mixes, "weighings": weighings(cfg), "lab_uL": dict(lab), "working": working,
            "residual": residual, "water_common_uL": water, "water_common_max_uL": water0,
            "topup": topup, "topup_no_r1": topup_no_r1, "mm_a_rxns": n_mm,
            "feasible": feasible, "min_residual_uL": min_res, "n_tubes": n}


def _topup_ok(v: float, floor: float) -> bool:
    """A DW top-up is pipettable when it is 0 or at least the pipette floor."""
    return v <= EPS_UL or v >= floor - 1e-9


def _assign_water(residual, water0, floor, feasible, water_in_place, enz_tubes, tube_enzyme_steps, tubes):
    """Choose the common water per reaction in MM-A (R1) and the per-tube DW top-ups.

    The largest water (water0 = the tightest tube's residual) is used unless it leaves some tube a DW top-up
    between 0 and the pipette floor; that top-up could not be pipetted and would otherwise be dropped (the
    tube would end short of the total). Lowering the common water by `floor` raises every top-up by the same
    amount, so every top-up becomes >= floor; when water0 < floor the fallback is no common water.
    A no-enzyme tube (water_in_place) receives WATER in the volume sequence of an enzyme tube; the sequence
    chosen leaves a valid top-up (0 or >= floor) when one exists, then closes best, then is the most common.
    Returns (water, topup {tube: uL}, in_place {tube: [(source, uL)]})."""
    seq = {t: tuple(round(v, 4) for _, v in tube_enzyme_steps[t]) for t in enz_tubes}
    freq = Counter(seq.values())

    def attempt(water):
        topup = {t: (r - water if r - water > EPS_UL else 0.0) for t, r in residual.items()}
        in_place = {}
        if not (water_in_place and enz_tubes and feasible):
            return topup, in_place
        for t in tubes:
            if tube_enzyme_steps[t]:
                continue
            need_t = residual[t] - water           # liquid this tube still needs after MM-A + substrates
            best = None
            for t2 in enz_tubes:
                left = need_t - sum(seq[t2])
                if left < -1e-9:
                    continue
                key = (0 if _topup_ok(left, floor) else 1, round(left, 4), -freq[seq[t2]], t2)
                if best is None or key < best:
                    best = key
            if best is None:
                continue
            ref = tube_enzyme_steps[best[3]]
            in_place[t] = [(f"water (in place of {src})", v) for src, v in ref]
            left = need_t - sum(v for _, v in ref)
            topup[t] = left if left > EPS_UL else 0.0
        return topup, in_place

    candidates = [water0]
    if water0 > EPS_UL:
        candidates += [_floor4(water0 - floor)] if water0 - floor > EPS_UL else [0.0]
    for w in candidates:
        topup, in_place = attempt(w)
        if not feasible or all(_topup_ok(v, floor) for v in topup.values()):
            return w, topup, in_place
    topup, in_place = attempt(water0)     # nothing closes cleanly: keep the maximum, rounding reports it
    return water0, topup, in_place


def _rnd(x: float, res: float) -> float:
    """Round half up to the pipette resolution (1.05 -> 1.1 at 0.1 uL, never banker's rounding)."""
    return round(math.floor(x / res + 0.5 + 1e-9) * res, 10)


def _floor_res(x: float, res: float) -> float:
    return round(math.floor(x / res + 1e-9) * res, 10)


def rounded_plan(plan: dict, res: float | None = None) -> dict:
    """Round every pipetting volume to the pipette resolution and re-close every tube.

    Every run addition and every prep draw is rounded to `res` (default limits()["resolution_uL"]); the MM-A
    per-tube volume is the same in all tubes and is capped so no tube's DW goes negative; the DW top-up is
    recomputed as total - (rounded additions), so every tube still closes to the total volume. When a
    recomputed DW top-up would fall between 0 and the pipette floor, the per-tube MM-A volume is lowered in
    resolution steps until every top-up is 0 or >= floor (the buffer deviation this causes is reported); only
    when no such step exists is the top-up dropped (reported in 'dropped', the tube then ends slightly short).
    The concentration of every ultimate component (lab stock) in every tube is recomputed from the rounded
    draws (premix / cocktail / working-stock composition) and the rounded per-tube volumes, and compared with
    the exact design: 'deviation' = {component: (max |rel. deviation|, signed, tube)}.

    Returns {'tubes': {tube: [(kind, source, exact_uL, rounded_uL)]}, 'dw': {tube: uL}, 'mm_a_uL',
             'dropped': {tube: uL}, 'deviation': {...}, 'res'}."""
    cfg = plan["config"]
    lim = limits(cfg)
    res = res or lim["resolution_uL"]
    V = float(cfg["total_volume_uL"])
    enz = cfg["enzymes"]
    steps = plan["steps"]
    draws = defaultdict(list)                 # vessel -> [(source, exact, rounded)]
    for s in steps:
        if s.phase == "prep":
            draws[s.target].append((s.source, s.volume_uL, _rnd(s.volume_uL, res)))

    def vessel(src):
        if src in draws:
            return src
        if f"WS {src}" in draws:
            return f"WS {src}"
        return None

    def comp(src):
        if src.startswith("water"):
            return None
        if src in enz:
            return real_name(src, enz[src])
        return src.replace(" (lab stock)", "")

    memo = {}

    def frac(v, rounded):
        if (v, rounded) in memo:
            return memo[(v, rounded)]
        amt, tot = Counter(), 0.0
        for src, ex, rd in draws[v]:
            vol = rd if rounded else ex
            tot += vol
            sub = vessel(src)
            if sub and sub != v:
                for c, f in frac(sub, rounded).items():
                    amt[c] += vol * f
            elif comp(src):
                amt[comp(src)] += vol
        out = {c: a / tot for c, a in amt.items()} if tot > 0 else {}
        memo[(v, rounded)] = out
        return out

    def content(src, vol, rounded):
        v = vessel(src)
        if v:
            return {c: vol * f for c, f in frac(v, rounded).items()}
        c = comp(src)
        return {c: vol} if c else {}

    tubes = [c["num"] for c in cfg["conditions"]]
    run = {t: [s for s in steps if s.phase == "run" and s.target == f"#{t}"] for t in tubes}
    others = {t: sum(_rnd(s.volume_uL, res) for s in run[t] if s.kind not in ("dw", "mm_a")) for t in tubes}
    mm_ex = next((s.volume_uL for t in tubes for s in run[t] if s.kind == "mm_a"), None)
    mm_r = None
    if mm_ex is not None:
        mm_r = min(_rnd(mm_ex, res), _floor_res(min(V - others[t] for t in tubes), res))
        # a rounding residual between 0 and the floor cannot be pipetted: lower the per-tube MM-A volume in
        # resolution steps (at most one floor's worth) until every re-closed DW is 0 or >= floor; the buffer
        # concentration change this causes is part of the deviation report below
        for k in range(int(math.ceil(lim["floor_uL"] / res - 1e-9)) + 1):
            m = round(mm_r - k * res, 10)
            if m <= 0:
                break
            if all(_topup_ok(round(V - others[t] - m, 10), lim["floor_uL"]) for t in tubes):
                mm_r = m
                break
    out_t, dw, dropped, dev = {}, {}, {}, {}
    for t in tubes:
        rows = []
        for s in run[t]:
            if s.kind == "dw":
                continue
            rows.append((s.kind, s.source, s.volume_uL, mm_r if s.kind == "mm_a" else _rnd(s.volume_uL, res)))
        d = round(V - sum(r[3] for r in rows), 10)
        if 0 < d < lim["floor_uL"] - 1e-9:
            dropped[t], d = d, 0.0
        if d > 1e-9:
            rows.insert(next((i for i, r in enumerate(rows) if r[0] in ("enzyme", "cocktail_add", "water_in_place")),
                             len(rows)), ("dw", "water", plan["topup"].get(t, 0.0), d))
        dw[t] = max(d, 0.0)
        out_t[t] = rows
        total_r = sum(r[3] for r in rows)
        ex_amt, rd_amt = Counter(), Counter()
        for s in run[t]:
            for c, a in content(s.source, s.volume_uL, False).items():
                ex_amt[c] += a
        for kind, src, _, rd in rows:
            for c, a in content(src, rd, True).items():
                rd_amt[c] += a
        for c, a in ex_amt.items():
            if a <= 0:
                continue
            rel = (rd_amt.get(c, 0.0) / total_r) / (a / V) - 1 if total_r > 0 else -1.0
            if c not in dev or abs(rel) > dev[c][0]:
                dev[c] = (abs(rel), rel, t)
    return {"tubes": out_t, "dw": dw, "mm_a_uL": mm_r, "dropped": dropped, "deviation": dev, "res": res}


def volume_settings(rplan: dict) -> dict:
    """Beginner-proofing metrics on the ROUNDED run phase: distinct pipette volume settings per tube and over
    the whole run, components added at more than one volume across tubes (incl. DW top-up), and whether every
    tube receives the identical volume sequence (a no-enzyme control with water in place counts as identical)."""
    per_tube = {t: len({r[3] for r in rows}) for t, rows in rplan["tubes"].items()}
    run_all = {r[3] for rows in rplan["tubes"].values() for r in rows}
    by_comp = defaultdict(lambda: defaultdict(list))
    for t, rows in rplan["tubes"].items():
        for kind, src, _, rd in rows:
            key = "DW top-up" if kind == "dw" else src
            by_comp[key][rd].append(t)
    multi = {k: {v: ts for v, ts in vs.items()} for k, vs in by_comp.items() if len(vs) > 1}
    seqs = {t: tuple(r[3] for r in rows) for t, rows in rplan["tubes"].items()}
    return {"settings_per_tube": per_tube, "settings_per_tube_max": max(per_tube.values()) if per_tube else 0,
            "settings_run": len(run_all), "multi_volume_components": multi,
            "identical_sequence": len(set(seqs.values())) <= 1}


def summarize(plan: dict) -> dict:
    steps = plan["steps"]
    prep = [s for s in steps if s.phase == "prep"]
    run = [s for s in steps if s.phase == "run"]
    per_tube = Counter(s.target for s in run)
    enz_per_tube = Counter(s.target for s in run if s.kind in ("enzyme", "cocktail_add"))
    tubes = [f"#{c['num']}" for c in plan["config"]["conditions"]]
    vset = lambda ss: len({round(s.volume_uL, 2) for s in ss})
    enz_lab = {k: round(v, 2) for k, v in plan["lab_uL"].items()
               if k in {real_name(n, e) for n, e in plan["config"]["enzymes"].items()}}
    lim = limits(plan["config"])
    rp = rounded_plan(plan)
    vs = volume_settings(rp)
    worst = max(rp["deviation"].items(), key=lambda kv: kv[1][0], default=(None, (0.0, 0.0, None)))
    return {
        "floor_uL": lim["floor_uL"], "comfort_uL": lim["comfort_uL"], "resolution_uL": rp["res"],
        "below_floor": sum(1 for s in steps if s.kind != "dw" and s.volume_uL < lim["floor_uL"]),
        "below_comfort": sum(1 for s in steps if s.kind != "dw" and s.volume_uL < lim["comfort_uL"]),
        "settings_per_tube": vs["settings_per_tube"], "settings_per_tube_max": vs["settings_per_tube_max"],
        "settings_run": vs["settings_run"], "identical_sequence": vs["identical_sequence"],
        "multi_volume_components": sorted(vs["multi_volume_components"]),
        "rounding_max_dev_pct": round(100 * worst[1][0], 2), "rounding_max_dev_component": worst[0],
        "water_in_place_tubes": sorted(plan.get("water_in_place", {})),
        "tubes": plan["n_tubes"], "cocktail": plan["cocktail"], "common_water": plan["common_water"],
        "feasible": plan["feasible"], "min_residual_uL": round(plan["min_residual_uL"], 4),
        "prep_steps": len(prep), "prep_mixes": len(plan["mixes"]),
        "prep_dilutions": len(plan["working"]),
        "run_steps": len(run),
        "run_by_kind": dict(Counter(s.kind for s in run)),
        "per_tube_steps_min": min(per_tube[t] for t in tubes), "per_tube_steps_max": max(per_tube[t] for t in tubes),
        "per_tube_enzyme_steps_min": min(enz_per_tube[t] for t in tubes),
        "per_tube_enzyme_steps_max": max(enz_per_tube[t] for t in tubes),
        "total_steps": len(steps), "total_ops": len(steps) + len(plan["mixes"]),
        "weighings": len(plan["weighings"]),
        "distinct_volumes_run": vset(run), "distinct_volumes_all": vset(steps),
        "below_1uL": sum(1 for s in steps if s.volume_uL < 1.0),
        "below_2uL": sum(1 for s in steps if s.volume_uL < 2.0),
        "below_1uL_run": sum(1 for s in run if s.volume_uL < 1.0),
        "below_2uL_run": sum(1 for s in run if s.volume_uL < 2.0),
        "dw_steps_with_r1": sum(1 for v in plan["topup"].values() if v > 0),
        "dw_steps_without_r1": sum(1 for v in plan["topup_no_r1"].values() if v > 0),
        "water_common_uL": plan["water_common_uL"],
        "enzyme_lab_stock_uL": enz_lab,
        "enzyme_lab_stock_total_uL": round(sum(enz_lab.values()), 2),
        "smallest_uL": round(min(s.volume_uL for s in steps), 4) if steps else None,
    }


def count(cfg: dict, cocktail: str | None = None, common_water: bool | None = None) -> dict:
    return summarize(build_plan(cfg, cocktail, common_water))


def summary_line(s: dict) -> str:
    feas = "" if s["feasible"] else f" | INFEASIBLE: a tube overfills by {-s['min_residual_uL']:.3f} uL"
    return (f"Pipette count ({s['cocktail']} cocktail, R1 common water {'on' if s['common_water'] else 'off'}): "
            f"prep {s['prep_steps']} steps + {s['prep_mixes']} mixes ({s['prep_dilutions']} working-stock dilutions), "
            f"run {s['run_steps']} steps (per tube {s['per_tube_steps_min']}-{s['per_tube_steps_max']}, "
            f"enzyme {s['per_tube_enzyme_steps_min']}-{s['per_tube_enzyme_steps_max']}), "
            f"TOTAL {s['total_steps']} steps / {s['total_ops']} ops | weighings {s['weighings']} (not pipetting) | "
            f"distinct volumes run {s['distinct_volumes_run']} / all {s['distinct_volumes_all']} | "
            f"additions <1 uL: {s['below_1uL']} (run {s['below_1uL_run']}), <2 uL: {s['below_2uL']} | "
            f"DW top-ups {s['dw_steps_with_r1']} with R1 vs {s['dw_steps_without_r1']} without | "
            f"below pipette floor {s['floor_uL']} uL: {s['below_floor']}, below comfort {s['comfort_uL']} uL: "
            f"{s['below_comfort']} | volume settings per tube max {s['settings_per_tube_max']}, run "
            f"{s['settings_run']} (rounded to {s['resolution_uL']} uL), identical sequence in every tube: "
            f"{'yes' if s['identical_sequence'] else 'no'} | rounding max deviation {s['rounding_max_dev_pct']} % | "
            f"enzyme lab stock {s['enzyme_lab_stock_total_uL']} uL{feas}")


# ---------------------------------------------------------------- designs A / B / C
def auto_equal_volume(einfo: dict, V: float, min_uL: float = 2.0) -> float:
    """Smallest equal volume that keeps every level >= min_uL: the top level's NEAT volume (so the top
    level needs no dilution), raised to min_uL when that is smaller. Rounded up to 0.01 uL."""
    top = max(float(v) for v in einfo["rxn_gL"].values()) * V / lab_stock_of(einfo)
    return max(min_uL, math.ceil(top * 100 - 1e-6) / 100)


def to_neat(cfg: dict) -> dict:
    """Design A from any config: every enzyme pipetted from its undiluted lab stock."""
    c = normalize(cfg)
    if any("level" in e for e in c["enzymes"].values()):   # collapse pseudo-enzymes back
        src = cfg if is_spec(cfg) else None
        if src is None:
            raise ValueError("an already-expanded config cannot be collapsed; pass the equal-volume spec")
        c = copy.deepcopy(src)
    for e in c["enzymes"].values():
        e["stock_gL"] = lab_stock_of(e)
        for k in ("equal_volume_uL", "source_stock_gL", "dilution_x", "stock_note"):
            e.pop(k, None)
    return c


def used_levels(cfg: dict, name: str) -> set:
    return {c["enzymes"].get(name) for c in cfg["conditions"]} - {None, "0x"}


def to_equal_volume_spec(cfg: dict, min_uL: float = 2.0, only_varied: bool = False) -> dict:
    """Design B spec from any config (keeps an existing equal_volume_uL).
    only_varied=True (design B-min): working stocks only for enzymes used at >1 level; an enzyme held
    at one level everywhere stays neat (it is pooled in the common cocktail, so it is never sub-uL)."""
    c = copy.deepcopy(cfg) if is_spec(cfg) else to_neat(cfg)
    for name, e in c["enzymes"].items():
        if e.get("equal_volume_uL") is None and not is_spec(cfg):
            e["rxn_gL"] = {k: v for k, v in e["rxn_gL"].items() if float(v) > 0}
            e["equal_volume_uL"] = auto_equal_volume(e, float(c["total_volume_uL"]), min_uL)
        if only_varied and len(used_levels(c, name)) <= 1:
            e.pop("equal_volume_uL", None)
            e["rxn_gL"] = dict(e["rxn_gL"], **{"0x": 0})
    return c


def compare(cfg: dict, cocktail: str | None = None) -> dict:
    base = cocktail or cfg.get("enzyme_cocktail", "common")
    spec = to_equal_volume_spec(cfg)
    designs = {"A (neat stock, variable volume)": (to_neat(cfg), base),
               "B (equal-volume working stocks, every enzyme)": (spec, base),
               "Bmin (equal-volume only for enzymes with >1 level)": (to_equal_volume_spec(cfg, only_varied=True), base),
               "C (B + one cocktail per condition)": (spec, "per_condition"),
               "Cdirect (cocktail per condition from lab stocks)": (to_neat(cfg), "per_condition_direct")}
    return {k: count(c, m) for k, (c, m) in designs.items()}


COMPARE_ROWS = ["tubes", "feasible", "prep_steps", "prep_mixes", "prep_dilutions", "run_steps",
                "per_tube_enzyme_steps_max", "dw_steps_with_r1", "total_steps", "total_ops", "weighings",
                "distinct_volumes_run", "distinct_volumes_all", "below_1uL", "below_2uL", "smallest_uL",
                "enzyme_lab_stock_total_uL"]


def format_compare(res: dict) -> str:
    names = list(res)
    w = 22
    lines = ["metric".ljust(28) + "".join(n.split(" (")[0].ljust(10) for n in names)]
    for r in COMPARE_ROWS:
        lines.append(r.ljust(28) + "".join(str(res[n][r]).ljust(10) for n in names))
    lines.append("")
    lines += [f"{n.split(' (')[0]} = {n}" for n in names]
    return "\n".join(lines)


def write_steps(plan: dict, path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["phase", "kind", "target", "source", "volume_uL"])
        w.writeheader()
        for s in plan["steps"]:
            d = asdict(s)
            d["volume_uL"] = round(d["volume_uL"], 4)
            w.writerow(d)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("config")
    ap.add_argument("--cocktail", choices=COCKTAIL_MODES)
    ap.add_argument("--no-common-water", action="store_true")
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--steps", help="write the step list as CSV")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    cfg = json.loads(Path(a.config).read_text(encoding="utf-8"))
    if a.compare:
        res = compare(cfg, a.cocktail)
        print(json.dumps(res, indent=1) if a.json else format_compare(res))
        return 0
    plan = build_plan(cfg, a.cocktail, False if a.no_common_water else None)
    s = summarize(plan)
    if a.steps:
        write_steps(plan, a.steps)
    if a.json:
        print(json.dumps(s, indent=1))
    else:
        print(summary_line(s))
        print(f"  margins: MM-A n+{mm_a_extra(plan['config'])}, sub-mix/cocktail x{SURPLUS}, "
              f"+{DEAD_UL} uL dead per vessel")
        if plan["water_common_uL"] < plan["water_common_max_uL"]:
            print(f"  common water lowered from {plan['water_common_max_uL']} to {plan['water_common_uL']} uL/rxn "
                  f"so every DW top-up is 0 or >= the pipette floor")
        for wk in plan["working"]:
            print(f"  working stock {wk['working_stock']}: {wk['lab_stock_uL']:.2f} uL lab stock + "
                  f"{wk['water_uL']:.2f} uL water = {wk['make_uL']} uL ({wk['dilution_x']:.3f}x, {wk['uL_per_tube']} uL/tube)")
    return 0 if s["feasible"] else 1


if __name__ == "__main__":
    sys.exit(main())
