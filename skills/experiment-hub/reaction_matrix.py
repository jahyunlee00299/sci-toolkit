"""
Reaction Matrix Generator — experiment-hub Mode 10
Generates optimized experiment Excel files with master mix grouping and pipetting guides.

Usage:
    python reaction_matrix.py config.json [output.xlsx]

Config JSON format:
{
    "title": "Experiment Title",
    "date": "YYMMDD",
    "total_volume_uL": 25,
    "temperature_C": 30,
    "timepoints": ["30 min", "1.5 h", "3 h"],
    "stocks": {
        "Substrate": {"conc_mM": 1000, "type": "substrate"},
        "Cofactor": {"conc_mM": 100, "type": "cofactor"},
        "Buffer pH 7.0": {"conc_mM": 1000, "type": "buffer", "final_mM": 200},
        "MgCl2": {"conc_mM": 1000, "type": "buffer", "final_mM": 20}
    },
    "enzymes": {
        "EnzymeA": {"batch": "YYMMDD", "stock_gL": 0.0, "rxn_gL": {"1x": 2, "2x": 2}},
        "EnzymeB": {"batch": "YYMMDD", "stock_gL": 0.0, "rxn_gL": {"1x": 0.2, "2x": 0.4}},
        "EnzymeC": {"batch": "YYMMDD", "stock_gL": 0.0, "rxn_gL": {"1x": 0.1, "2x": 0.2}}
    },
    "conditions": [
        {"num": 1, "group": "Exp 1A", "label": "Baseline", "substrates": {"Substrate": 100, "Cofactor": 1.0}, "enzymes": {"EnzymeA": "1x", "EnzymeB": "1x", "EnzymeC": "1x"}, "note": "Control"}
    ],
    "fed_diagnosis": {
        "source_condition": 2,
        "feeds": [
            {"id": "F1", "component": "Fresh EnzymeB", "amount": "2x loading"},
            {"id": "F2", "component": "Cofactor", "amount": "100 mM replenish"}
        ],
        "timepoints": ["+30 min", "+1 h"]
    },
    "sampling": {
        "volume_uL": 5,
        "dilution": "20x",
        "quench": "Heat 95C 5 min",
        "analysis": "HPLC",
        "targets": ["Substrate", "Intermediate", "Product"]
    }
}
"""

import json
import re
import sys
from pathlib import Path
from collections import defaultdict

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# ── Styles ──
B = Font(name='Arial', bold=True, size=10)
N = Font(name='Arial', size=10)
T = Font(name='Arial', bold=True, size=12)
S = Font(name='Arial', bold=True, size=10, color='2F5496')
NOTE = Font(name='Arial', size=9, italic=True, color='808080')
HF = PatternFill('solid', fgColor='4472C4')
HN = Font(name='Arial', bold=True, size=10, color='FFFFFF')
SF = PatternFill('solid', fgColor='D9E2F3')
YF = PatternFill('solid', fgColor='FFF2CC')
GF = PatternFill('solid', fgColor='E2EFDA')
RF = PatternFill('solid', fgColor='FCE4EC')
TB = Border(left=Side('thin'), right=Side('thin'), top=Side('thin'), bottom=Side('thin'))
CT = Alignment(horizontal='center', vertical='center')
CW = Alignment(horizontal='center', vertical='center', wrap_text=True)
LT = Alignment(horizontal='left', vertical='center')


def hdr(ws, row, n):
    for c in range(1, n + 1):
        cl = ws.cell(row=row, column=c)
        cl.font, cl.fill, cl.alignment, cl.border = HN, HF, CW, TB


def dc(ws, r, c, v, f=None, a=None, fill=None):
    cl = ws.cell(row=r, column=c, value=v)
    cl.font = f or N
    cl.alignment = a or CT
    cl.border = TB
    if fill:
        cl.fill = fill
    return cl


def fml(ws, r, c, formula):
    cl = ws.cell(row=r, column=c, value=formula)
    cl.font, cl.alignment, cl.border = N, CT, TB
    return cl


def sec(ws, r, ncols, text):
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=ncols)
    ws.cell(row=r, column=1, value=text).font = S
    ws.cell(row=r, column=1).alignment = LT
    for c in range(1, ncols + 1):
        ws.cell(row=r, column=c).fill = SF
        ws.cell(row=r, column=c).border = TB


def analyze_master_mixes(config):
    """Analyze conditions to find optimal master mix grouping."""
    conditions = config['conditions']
    buffer_stocks = {k: v for k, v in config['stocks'].items() if v['type'] == 'buffer'}

    # MM-A: buffer components (same for all)
    mm_a = {}
    for name, info in buffer_stocks.items():
        mm_a[name] = {'stock_mM': info['conc_mM'], 'final_mM': info['final_mM']}

    # Group conditions by substrate+cofactor fingerprint
    groups = defaultdict(list)
    for cond in conditions:
        subs = cond['substrates']
        key = tuple(sorted(subs.items()))
        groups[key].append(cond['num'])

    sub_mixes = []
    for key, nums in groups.items():
        if len(nums) > 1:
            sub_mixes.append({'components': dict(key), 'conditions': nums, 'count': len(nums)})

    return mm_a, sub_mixes, groups


def surplus_note(extra_rxns=3):
    return (f'Surplus convention (one everywhere): MM-A premix = n tubes + {extra_rxns} reactions; stock totals, '
            f'sub-mixes and cocktails x1.2; +10 uL dead volume per intermediate vessel (working stock, cocktail).')


SURPLUS_NOTE = surplus_note()   # default margin (config "premix": {"extra_rxns": 3})
MIN_ADDITION_UL = 0.5    # legacy names kept for importers; the limits now live in pipette_count.limits()
WARN_ADDITION_UL = 1.0   # (config "pipettes": {"floor_uL", "comfort_uL", "resolution_uL"})
WAIVER_FLAGS = ('allow_small_volume', 'allow_variable_volume')
VOL_REL_TOL, VOL_ABS_TOL = 0.005, 0.005   # two volumes within 0.5 % or 0.005 uL are the same volume (R2)


def _waiver(einfo, flag):
    """(state, text): state 'none' (flag absent or exactly false), 'ok' (flag is exactly the boolean true AND
    '<flag>_reason' is a non-empty string; text = reason) or 'malformed' (anything else; text = problem)."""
    if flag not in einfo or einfo[flag] is False:
        return 'none', None
    val, reason = einfo[flag], einfo.get(f'{flag}_reason')
    if val is not True:
        return 'malformed', f'"{flag}" must be the boolean true (or false), got {val!r}'
    if not isinstance(reason, str) or not reason.strip():
        return 'malformed', f'"{flag}": true needs a non-empty string "{flag}_reason", got {reason!r}'
    return 'ok', reason.strip()


def _same_volume(a, b):
    return abs(a - b) <= max(VOL_ABS_TOL, VOL_REL_TOL * max(abs(a), abs(b)))


def _volume_clusters(vols):
    """{representative uL: [tube]} with volumes within tolerance merged (4.0 and 4.0001 are one volume)."""
    out = []
    for v, ts in sorted(vols.items()):
        if out and _same_volume(out[-1][0], v):
            out[-1][1].extend(ts)
        else:
            out.append([v, list(ts)])
    return {v: sorted(ts) for v, ts in out}


def _norm_batch(batch):
    """Batch label as a comparable key: strip + casefold, ints and integral floats as their digits
    (100001, 100001.0, '100001 ' and '100001' are one batch). None / '' / booleans -> None."""
    if batch is None or isinstance(batch, bool):
        return None
    if isinstance(batch, float) and batch.is_integer():
        batch = int(batch)
    s = str(batch).strip().casefold()
    return s or None


_DILUTION_SUFFIX = re.compile(r'(?:[\s_\-.]*(?:\[[^\]]*\]|\(.*?\)|diluted|dilution|dil|working|ws|\d+(?:\.\d+)?x))+$',
                              re.I)


def _name_stem(name):
    """Enzyme name without a dilution / level suffix: 'EnzX_dil', 'EnzX working', 'EnzX [1x]' -> 'enzx'."""
    stem = _DILUTION_SUFFIX.sub('', str(name)).strip()
    return re.sub(r'[^a-z0-9]+', '', (stem or str(name)).casefold())


def _lab_stock(e):
    """Undiluted lab-stock g/L of a config entry: source_stock_gL; else stock_gL x dilution_x for a dilution
    entry that declares its dilution but not its source; else stock_gL. None when unreadable."""
    try:
        if e.get('source_stock_gL') is not None:
            return round(float(e['source_stock_gL']), 6)
        if e.get('dilution_x') is not None:
            return round(float(e['stock_gL']) * float(e['dilution_x']), 6)
        return round(float(e.get('stock_gL')), 6)
    except (TypeError, ValueError):
        return None


def _physical_enzymes(enzymes):
    """Group config entries that are the same physical enzyme. Two entries are grouped when they share
      * the 'enzyme' alias, OR
      * the normalised batch (_norm_batch) + the undiluted lab stock (_lab_stock), OR
      * the normalised batch + the name stem (_name_stem), which catches a dilution entry that declares no
        source_stock_gL (e.g. 'EnzX' 10 g/L and 'EnzX_dil' 2.5 g/L, both batch 'b1').
    Returns [(label, [entry names])]."""
    parent = {n: n for n in enzymes}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    seen = {}
    for n, e in enzymes.items():
        keys = [('alias', e.get('enzyme', n))]
        batch = _norm_batch(e.get('batch'))
        lab = _lab_stock(e)
        if batch is not None and lab:
            keys.append(('stock', batch, lab))
        if batch is not None:
            keys.append(('stem', batch, _name_stem(e.get('enzyme', n))))
        for k in keys:
            if k in seen:
                parent[find(n)] = find(seen[k])
            else:
                seen[k] = n
    groups = defaultdict(list)
    for n in enzymes:
        groups[find(n)].append(n)
    out = []
    for names in groups.values():
        aliases = sorted({enzymes[n].get('enzyme', n) for n in names})
        out.append(('/'.join(aliases), names))
    return out


def _step_enzyme(step, enzymes):
    """Config entry names whose liquid this pipetting step moves (for the small-volume waiver), else []."""
    if step.source in enzymes:
        return [step.source]
    if step.target.startswith('WS ') and step.target[3:] in enzymes:
        return [step.target[3:]]
    if step.source.endswith(' (lab stock)'):
        real = step.source[:-len(' (lab stock)')]
        return [n for n, e in enzymes.items() if e.get('enzyme', n) == real]
    return []


def _describe(step, tubes):
    if step.phase == 'prep':
        return f"prep {step.kind} '{step.target}' <- {step.source}"
    return f"per-tube {step.kind} {step.source} (#{',#'.join(map(str, tubes))})"


def _check_pipetting_rules(config, report):
    """Pipetting rules (R1/R2 and the pipette limits). Returns ok (False if any hard check failed).

    a. waivers: allow_small_volume / allow_variable_volume must be exactly true + a non-empty string reason;
       anything else is a FAIL ('malformed waiver'), never a silent waiver.
    b. pipette floor / comfort (config "pipettes", defaults 0.5 / 1.0 uL = the lab's real pipettes): checked on
       EVERY single pipetting action of the plan pipette_count.build_plan() would execute - premix and sub-mix
       component draws, cocktail component draws, working-stock draws (lab stock and water), per-tube additions.
       An enzyme pooled into a cocktail (pipette_count.route_enzymes) is checked as the cocktail per-tube volume
       and as its batch draw, never as its per-tube share. < floor = FAIL (enzyme waiver: allow_small_volume),
       < comfort = WARN. A DW top-up is water: its rounding/drop is handled by check e.
    c. R2: one physical enzyme (alias, or batch + undiluted stock) pipetted at more than one volume across tubes
       (0.5 % / 0.005 uL tolerance) = FAIL; waiver allow_variable_volume on EVERY entry of that enzyme.
    d. beginner-proofing (WARN): a non-enzyme component (incl. DW top-up) at more than one volume across tubes;
       a tube needing more than pipettes.max_settings_per_tube (4) distinct volume settings;
       "control_water_in_place": false while a no-enzyme tube exists (its single DW top-up is an odd volume).
    e. rounding to pipettes.resolution_uL (0.1): tubes re-closed with DW (never a DW top-up between 0 and the
       floor: the common water / MM-A volume is lowered instead); concentration deviation > 2 % WARN, > 5 % FAIL.
       allow_small_volume turns a 2-5 % deviation of that enzyme into a waived WARN; > 5 % stays a FAIL.
    f. R1 common water in MM-A (WARN if off; SKIP when there is no MM-A, no water headroom, or a tube overfills)."""
    import pipette_count as pc
    ok = True
    enzymes = config['enzymes']
    try:
        lim = pc.limits(config)
    except (TypeError, ValueError) as exc:
        report.append(f'FAIL pipettes: {exc}')
        return False
    floor, comfort = lim['floor_uL'], lim['comfort_uL']

    # ---- a. waivers ---------------------------------------------------------
    waiver = {}
    for n, e in enzymes.items():
        for flag in WAIVER_FLAGS:
            state, text = _waiver(e, flag)
            waiver[(n, flag)] = (state, text)
            if state == 'malformed':
                report.append(f'FAIL {n}: malformed waiver -- {text}')
                ok = False

    def waived(names, flag):
        st = [waiver.get((n, flag), ('none', None)) for n in names]
        if names and all(s == 'ok' for s, _ in st):
            return '; '.join(sorted({t for _, t in st}))
        return None

    try:
        plan = pc.build_plan(config)
    except Exception as exc:  # the count model must never silently skip
        report.append(f'FAIL pipetting plan could not be built: {type(exc).__name__}: {exc}')
        return False

    # ---- b. floor / comfort on every pipetting action ------------------------
    grouped = defaultdict(list)
    for s in plan['steps']:
        if s.kind == 'dw' or s.volume_uL <= pc.EPS_UL:
            continue
        key = (s.phase, s.kind, s.target if s.phase == 'prep' else '', s.source, round(s.volume_uL, 4))
        grouped[key].append(s)
    n_fail = n_warn = 0
    for (phase, kind, _, src, v), ss in grouped.items():
        tubes = [int(x.target[1:]) for x in ss if x.target.startswith('#')]
        desc = _describe(ss[0], tubes)
        names = _step_enzyme(ss[0], enzymes)
        if v < floor:
            why = waived(names, 'allow_small_volume') if names else None
            if why:
                report.append(f'WARN {desc}: {v} uL < pipette floor {floor} uL, WAIVED (allow_small_volume: {why})')
                n_warn += 1
                continue
            if kind == 'cocktail':
                fix = 'make a larger cocktail batch or pre-dilute that enzyme with WATER'
            elif names:
                fix = 'make a diluted working stock (lab stock + WATER) and add a fixed volume (equal_volume_uL)'
            else:
                fix = 'make a larger batch or a diluted stock so the draw is >= the floor'
            report.append(f"FAIL {desc}: {v} uL < pipette floor {floor} uL (cannot be pipetted with the lab's "
                          f"smallest pipette) -- {fix}")
            ok = False
            n_fail += 1
        elif v < comfort:
            report.append(f'WARN {desc}: {v} uL is below {comfort} uL (pipettable, poor accuracy)')
            n_warn += 1
    cocktails = plan['route']['cocktails']
    pooled = ', '.join(f"{c['name']} {round(c['per_tube'], 3)} uL/tube ({len(c['comps'])} enzymes)" for c in cocktails)
    if not n_fail and not n_warn:
        report.append(f'PASS pipette floor: every pipetting action >= {comfort} uL (floor {floor} uL)'
                      + (f'; pooled enzymes checked as {pooled} and their batch draws' if pooled else ''))
    elif not n_fail:
        report.append(f'PASS pipette floor: no pipetting action < {floor} uL ({n_warn} WARN line(s) between floor '
                      f'and comfort)' + (f'; pooled enzymes checked as {pooled}' if pooled else ''))

    # ---- c. R2: one physical enzyme, one volume -------------------------------
    adds = plan['route']['adds']
    any_enzyme = False
    r2_bad = False
    for label, names in _physical_enzymes(enzymes):
        vols = defaultdict(list)
        for t, al in adds.items():
            for a in al:
                if a['source'] in names:
                    vols[round(a['vol'], 4)].append(t)
        if not vols:
            continue
        any_enzyme = True
        cl = _volume_clusters(vols)
        if len(cl) <= 1:
            continue
        desc = ', '.join(f'{v} uL (#{",#".join(map(str, ts))})' for v, ts in cl.items())
        entries = f" [config entries: {', '.join(names)}]" if len(names) > 1 else ''
        why = waived(names, 'allow_variable_volume')
        if why:
            report.append(f'WARN {label}: pipetted at {len(cl)} different volumes, WAIVED '
                          f'(allow_variable_volume: {why}) -- {desc}{entries}')
        else:
            report.append(f'FAIL {label}: one enzyme pipetted at {len(cl)} different volumes -- {desc}{entries}. '
                          f'Rule R2: one diluted working stock per level (lab stock + WATER), the SAME volume in '
                          f'every tube ("equal_volume_uL" + equal_volume.py)')
            ok = False
            r2_bad = True
    if any_enzyme and not r2_bad:
        report.append('PASS R2: each physical enzyme is added at one volume in every tube')

    # ---- d/e. rounding + beginner-proofing ------------------------------------
    if not plan['feasible']:
        report.append('SKIP rounding / volume settings: a tube is over-filled -- fix the volume closure FAIL first')
        _check_r1(config, report, pc)
        return ok
    rp = pc.rounded_plan(plan)
    vs = pc.volume_settings(rp)
    for comp, vols in sorted(vs['multi_volume_components'].items()):
        if comp in enzymes:
            continue                       # enzymes: R2 above
        desc = ', '.join(f'{v} uL (#{",#".join(map(str, ts))})' for v, ts in sorted(vols.items()))
        report.append(f'WARN uniformity: {comp} is added at {len(vols)} different volumes across tubes -- {desc}')
    crowded = {t: n for t, n in vs['settings_per_tube'].items() if n > lim['max_settings_per_tube']}
    if crowded:
        report.append(f"WARN uniformity: {len(crowded)} tube(s) need more than {lim['max_settings_per_tube']} "
                      f"distinct volume settings -- " + ', '.join(f'#{t}: {n}' for t, n in crowded.items()))
    wip = plan['water_in_place']
    report.append(f"INFO volume settings (rounded to {rp['res']} uL): per tube "
                  f"{min(vs['settings_per_tube'].values())}-{vs['settings_per_tube_max']}, run phase "
                  f"{vs['settings_run']}; identical volume sequence in every tube: "
                  f"{'yes' if vs['identical_sequence'] else 'no'}"
                  + (f"; water in place of enzymes in #{',#'.join(map(str, sorted(wip)))}" if wip else ''))
    if plan['water_common_uL'] < plan['water_common_max_uL'] - pc.EPS_UL:
        report.append(f"INFO R1: common water in MM-A lowered from {plan['water_common_max_uL']} to "
                      f"{plan['water_common_uL']} uL/rxn so every DW top-up is 0 or >= the floor {floor} uL "
                      f"(a smaller top-up could not be pipetted)")
    for t, d in rp['dropped'].items():
        report.append(f'WARN rounding: #{t} DW top-up {round(d, 4)} uL < floor {floor} uL is skipped -- tube ends '
                      f'at {round(float(config["total_volume_uL"]) - d, 4)} uL')
    # control_water_in_place: false -> the no-enzyme control closes with ONE DW top-up equal to the enzyme
    # volume it lacks: a volume (and a pipetting sequence) no enzyme tube uses
    if not bool(config.get('control_water_in_place', True)) and plan['route']['enz_tubes']:
        for t in sorted(t for t, al in plan['route']['adds'].items() if not al):
            d = rp['dw'].get(t, 0.0)
            if d <= pc.EPS_UL:
                continue
            shared = sorted(t2 for t2, d2 in rp['dw'].items() if t2 != t and abs(d2 - d) <= 1e-9)
            what = (f'a volume no other tube uses' if not shared
                    else f'shared only with #{",#".join(map(str, shared))}')
            report.append(f'WARN uniformity: "control_water_in_place": false -- no-enzyme tube #{t} gets one DW '
                          f'top-up of {d} uL ({what}) instead of WATER in the volumes of the enzyme additions; '
                          f'remove the key (default true) so every tube follows the same volume sequence')
    bad = False
    for comp, (absd, rel, t) in sorted(rp['deviation'].items(), key=lambda kv: -kv[1][0]):
        entries = [n for n, e in enzymes.items() if e.get('enzyme', n) == comp]
        why = waived(entries, 'allow_small_volume') if entries else None
        # allow_small_volume waives the sub-floor VOLUME rule only; a rounding deviation > DEV_FAIL is never waived
        if absd > pc.DEV_FAIL:
            report.append(f'FAIL rounding: {comp} deviates {rel * 100:+.2f} % from target in #{t} after rounding '
                          f'to {rp["res"]} uL (> {pc.DEV_FAIL * 100:g} %) -- use larger volumes / a diluted stock'
                          + (' (allow_small_volume does not waive this)' if why else ''))
            ok = False
            bad = True
        elif absd > pc.DEV_WARN and why:
            report.append(f'WARN rounding: {comp} deviates {rel * 100:+.2f} % from target in #{t} after rounding '
                          f'to {rp["res"]} uL, WAIVED (allow_small_volume: {why}; pipette it unrounded)')
            bad = True
        elif absd > pc.DEV_WARN:
            report.append(f'WARN rounding: {comp} deviates {rel * 100:+.2f} % from target in #{t} after rounding '
                          f'to {rp["res"]} uL (> {pc.DEV_WARN * 100:g} %)')
            bad = True
    if not bad:
        worst = max((v[0] for v in rp['deviation'].values()), default=0.0)
        report.append(f'PASS rounding: volumes rounded to {rp["res"]} uL, every tube closes, max concentration '
                      f'deviation {worst * 100:.2f} %')

    _check_r1(config, report, pc)
    return ok


def _check_r1(config, report, pc):
    """f. R1 common water in MM-A: PASS / WARN (off) / SKIP (no MM-A, no water headroom, over-filled tube)."""
    try:
        cw = bool(config.get('common_water_in_mm_a', True))
        p1 = pc.build_plan(config, cocktail='none', common_water=True)
        with_r1 = sum(1 for v in p1['topup'].values() if v > 0)
        without = sum(1 for v in p1['topup_no_r1'].values() if v > 0)
        has_mm = any(v.get('type') == 'buffer' for v in config['stocks'].values())
        if not has_mm:
            report.append('SKIP R1 (no buffer stocks): there is no MM-A premix to carry the common water')
        elif not p1['feasible']:
            report.append(f"SKIP R1: a tube is over-filled by {-p1['min_residual_uL']:.4f} uL (negative common "
                          f"water) -- fix the volume closure FAIL first")
        elif p1['water_common_uL'] <= pc.EPS_UL:
            report.append('SKIP R1: common water is 0 uL (the tightest tube has no water headroom)')
        elif cw:
            tight = ('tightest tube top-up 0' if p1['water_common_uL'] >= p1['water_common_max_uL'] - pc.EPS_UL
                     else f"lowered from {p1['water_common_max_uL']} so no top-up is below the pipette floor")
            report.append(f"PASS R1: MM-A carries the common water ({p1['water_common_uL']} uL/rxn; {tight}) -> "
                          f"{with_r1} tube DW top-up(s) instead of {without}")
        else:
            report.append(f"WARN R1: \"common_water_in_mm_a\": false -- {without} tube DW pipettings; putting "
                          f"{p1['water_common_uL']} uL/rxn of water into MM-A would leave {with_r1}")
    except Exception as exc:  # the count model must never silently skip
        report.append(f'WARN R1 check could not run: {type(exc).__name__}: {exc}')


def validate_config(config, source='<config>'):
    """Independent, from-scratch re-verification of a reaction-matrix config, run BEFORE
    generate_excel(). Recomputes every volume in plain Python from the config's own stock/final
    values (never trusts a formula string or a previously-cached result), so it catches config
    errors that would otherwise only surface as a subtly wrong number in the finished xlsx.

    Historical motivation: a hand-built pipetting xlsx (not made with this script) had a
    formula edited during an unrelated fix, which silently changed the reference volume used for
    four reagents and put every one of 90 planned samples ~4% off target. This script exists so
    that class of error is caught automatically, every time, rather than only when someone
    separately asks for an adversarial review.

    Returns (ok: bool, report: list[str]) — 'ok' is False if ANY hard check fails. Print report
    lines regardless of ok, so a passing run still shows what was checked.
    """
    report = []
    ok = True
    # ---- Check 0: structure (clean messages instead of a KeyError / a vacuous PASS) ----
    if not isinstance(config, dict):
        return False, [f'FAIL config: expected a JSON object, got {type(config).__name__}']
    missing = [k for k in ('total_volume_uL', 'stocks', 'enzymes', 'conditions') if k not in config]
    if missing:
        return False, [f'FAIL config: missing required key(s) {", ".join(missing)} -- nothing to validate']
    if not config['conditions']:
        return False, ['FAIL config: no conditions -- there is nothing to pipette (a config without tubes '
                       'never passes)']
    import pipette_count
    if pipette_count.is_spec(config):
        spec = sorted(n for n, e in config['enzymes'].items() if e.get('equal_volume_uL') is not None)
        return False, [f'FAIL config: this is an UNEXPANDED equal-volume spec (equal_volume_uL already set on '
                       f'{", ".join(spec)}); expand it first with equal_volume.expand() / '
                       f'"python equal_volume.py spec.json expanded.json" -- reaction_matrix.py does this '
                       f'automatically']
    vol = config['total_volume_uL']
    stocks = config['stocks']
    enzymes = config['enzymes']
    conditions = config['conditions']
    buffer_stocks = {k: v for k, v in stocks.items() if v['type'] == 'buffer'}

    # ---- Check 1: per-condition volume closure (would DW go negative?) ----
    # DW = vol - sum(all component uL). generate_excel() defines DW as this exact residual, so the
    # printed "Total" column always equals vol by construction -- the real failure mode is DW < 0,
    # which Excel will happily print as a negative pipetting volume unless caught here first.
    for cond in conditions:
        used = 0.0
        detail = []
        for sname, sconc in cond['substrates'].items():
            stock_mM = stocks[sname]['conc_mM']
            if stock_mM <= 0:
                report.append(f"FAIL cond#{cond['num']}: {sname} stock_mM={stock_mM} <= 0 (div-by-zero / not set)")
                ok = False
                continue
            v = sconc * vol / stock_mM
            used += v
            detail.append(f'{sname}={v:.3f}uL')
        for bname, binfo in buffer_stocks.items():
            stock_mM = binfo['conc_mM']
            final_mM = binfo['final_mM']
            if stock_mM <= 0:
                report.append(f"FAIL cond#{cond['num']}: {bname} stock_mM={stock_mM} <= 0")
                ok = False
                continue
            v = final_mM * vol / stock_mM
            used += v
            detail.append(f'{bname}={v:.3f}uL')
        for ename, level in cond['enzymes'].items():
            einfo = enzymes[ename]
            stock_gL = einfo['stock_gL']
            rxn_gL = einfo['rxn_gL'].get(level)
            if rxn_gL is None:
                report.append(f"FAIL cond#{cond['num']}: enzyme {ename} has no rxn_gL entry for level '{level}'")
                ok = False
                continue
            if stock_gL <= 0:
                report.append(f"FAIL cond#{cond['num']}: {ename} stock_gL={stock_gL} <= 0")
                ok = False
                continue
            v = rxn_gL * vol / stock_gL
            used += v
            detail.append(f'{ename}={v:.3f}uL')

        dw = vol - used
        if dw < -1e-9:
            report.append(f"FAIL cond#{cond['num']}: components sum to {used:.3f} uL > total {vol} uL "
                           f"(DW would be negative: {dw:.3f} uL) -- {', '.join(detail)}")
            ok = False
        elif dw < 0.5:
            report.append(f"WARN cond#{cond['num']}: DW={dw:.3f} uL, almost no dilution headroom left "
                           f"-- {', '.join(detail)}")
        else:
            report.append(f"PASS cond#{cond['num']}: components={used:.3f}uL, DW={dw:.3f}uL, "
                           f"total={used+dw:.3f}uL (target {vol}uL)")

    # ---- Check 2: concentration re-derivation (independent of the volume formula) ----
    # For this script's construction, achieved_conc = stock * (target*vol/stock) / vol = target
    # algebraically -- so this check is really "did the config typo a stock/final pair such that
    # division blows up or produces something absurd", not a live formula-vs-formula comparison.
    # A hand-built workbook (formulas written cell-by-cell, e.g. a stock-blend design) does NOT get this guarantee for free -- see SKILL.md Mode 1 note: for anything
    # that doesn't fit this script's config shape, the same recomputation must be done manually,
    # in a throwaway script, against every sheet/condition, not just spot-checked.
    for sname, sinfo in stocks.items():
        if sinfo['type'] == 'buffer':
            achieved = sinfo['conc_mM'] * (sinfo['final_mM'] * vol / sinfo['conc_mM']) / vol
            if abs(achieved - sinfo['final_mM']) > 1e-6:
                report.append(f"FAIL {sname}: recomputed achieved conc {achieved} != declared final_mM {sinfo['final_mM']}")
                ok = False

    # ---- Check 3: sampling / dead-volume headroom (the check that did not exist before) ----
    sampling = config.get('sampling', {})
    timepoints = config.get('timepoints', [])
    if sampling and timepoints:
        n_tp = len(timepoints)
        sample_vol = sampling.get('volume_uL', 0)
        dead_vol = sampling.get('dead_volume_uL', max(0.1 * vol, 5))
        withdrawn = n_tp * sample_vol
        headroom = vol - withdrawn - dead_vol
        if withdrawn > vol:
            report.append(f"FAIL sampling: {n_tp} timepoints x {sample_vol} uL = {withdrawn} uL "
                           f"withdrawn > {vol} uL prepared -- physically impossible")
            ok = False
        elif headroom < 0:
            report.append(f"FAIL sampling: {n_tp} timepoints x {sample_vol} uL = {withdrawn} uL withdrawn, "
                           f"+ dead-volume margin {dead_vol} uL exceeds prepared {vol} uL "
                           f"(short by {-headroom:.2f} uL) -- reduce timepoints/aliquot or scale up volume")
            ok = False
        else:
            report.append(f"PASS sampling: {n_tp} timepoints x {sample_vol} uL = {withdrawn} uL withdrawn, "
                           f"{headroom:.2f} uL headroom left after {dead_vol} uL dead-volume margin (of {vol} uL)")

        # Fed-diagnosis draws from a source condition's REMAINING volume after its own timepoints --
        # check that too, since it is a second, easy-to-miss overdraw point.
        fed = config.get('fed_diagnosis')
        if fed:
            src_num = fed['source_condition']
            src_cond = next((c for c in conditions if c['num'] == src_num), None)
            if src_cond is None:
                report.append(f"FAIL fed_diagnosis: source_condition #{src_num} not found in conditions")
                ok = False
            else:
                remaining_after_main_tp = vol - withdrawn
                n_feeds = len(fed.get('feeds', []))
                # each feed tube needs at least the fed-sampling aliquot volume(s) available
                fed_tp = len(fed.get('timepoints', []))
                per_feed_need = fed_tp * sample_vol if fed_tp else sample_vol
                total_fed_need = n_feeds * per_feed_need
                if total_fed_need > remaining_after_main_tp:
                    report.append(f"FAIL fed_diagnosis: {n_feeds} feeds x {per_feed_need} uL sampling need "
                                   f"= {total_fed_need} uL > {remaining_after_main_tp:.2f} uL remaining in "
                                   f"source condition #{src_num} after its own {n_tp} main timepoints")
                    ok = False
                else:
                    report.append(f"PASS fed_diagnosis: {total_fed_need} uL needed <= "
                                   f"{remaining_after_main_tp:.2f} uL remaining in source condition #{src_num}")
    elif timepoints and not sampling:
        report.append("WARN: timepoints declared but no 'sampling' block -- cannot check dead-volume headroom")

    # ---- Check 5/6/7: standing pipetting rules R1/R2 + pipette limits ----
    ok = _check_pipetting_rules(config, report) and ok

    # ---- Check 4: canonical-constants registry (canon_gate.py) ----
    # A config that contradicts a recorded decision in the registry (a stock or final concentration,
    # a batch label, an enzyme stock) is blocked like a volume-closure failure. WARN = working stock differs from
    # another workbook (undecided, not blocking). BLIND (no registry field) is shown, not a pass.
    try:
        import canon_gate
        gate = canon_gate.check_config(config, source=source)
        for fd in gate.findings:
            if fd.level != 'OK':
                report.append(fd.line().replace(fd.level + ' ', fd.level + ' canon-gate ', 1))
        if gate.blind_reason:
            report.append(f'WARN canon-gate BLIND (exit 2, not a pass): {gate.blind_reason}')
        elif gate.n_fail:
            ok = False
        else:
            report.append(f'PASS canon-gate: {gate.n_ok} registry field(s) agree, {gate.n_warn} WARN')
    except Exception as exc:  # unreadable registry / missing module must be loud, never a silent skip
        report.append(f'FAIL canon-gate could not run: {type(exc).__name__}: {exc}')
        ok = False

    return ok, report


def generate_excel(config, output_path):
    wb = openpyxl.Workbook()
    title = config.get('title', 'Reaction Matrix')
    date = config.get('date', '')
    vol = config['total_volume_uL']

    stocks = config['stocks']
    enzymes = config['enzymes']
    conditions = config['conditions']
    buffer_stocks = {k: v for k, v in stocks.items() if v['type'] == 'buffer'}
    substrate_stocks = {k: v for k, v in stocks.items() if v['type'] in ('substrate', 'cofactor')}

    mm_a, sub_mixes, groups = analyze_master_mixes(config)

    import pipette_count
    common_water = bool(config.get('common_water_in_mm_a', True))
    pc_plan = pipette_count.build_plan(config)
    extra_rxns = pipette_count.mm_a_extra(config)
    note = surplus_note(extra_rxns)
    pc_sum = pipette_count.summarize(pc_plan)
    res = pipette_count.limits(config)['resolution_uL']

    # ═══════════════════════════════════════════
    # SHEET 1: Reaction Matrix
    # ═══════════════════════════════════════════
    ws = wb.active
    ws.title = 'Reaction Matrix'
    ws.sheet_properties.tabColor = '4472C4'

    # Title + Date
    sub_names = sorted(substrate_stocks.keys())
    enz_names = sorted(enzymes.keys())
    buf_names = sorted(buffer_stocks.keys())

    # Build column layout dynamically
    # Fixed: Type, #, [substrate mM cols], [buffer mM cols], [substrate uL cols], [buffer uL cols], [enzyme uL cols], DW, Total, Note
    sub_mM_cols = [f'{s}\n(mM)' for s in sub_names]
    buf_mM_cols = [f'{b}\n(mM)' for b in buf_names]
    sub_uL_cols = [f'{s}\n(uL)' for s in sub_names]
    buf_uL_cols = [f'{b}\n(uL)' for b in buf_names]
    enz_uL_cols = [f'{e}\n(uL)' for e in enz_names]

    all_cols = ['Type', '#'] + sub_mM_cols + buf_mM_cols + sub_uL_cols + buf_uL_cols + enz_uL_cols + ['DW\n(uL)', 'Total\n(uL)', 'Note']
    NC = len(all_cols)

    ws.merge_cells(f'A1:{get_column_letter(NC)}1')
    ws['A1'] = title
    ws['A1'].font = T
    ws.merge_cells(f'A2:{get_column_letter(NC)}2')
    dc(ws, 2, 1, f'Date: {date}', B, LT)

    # Stock info (row 4+)
    stock_rows = {}
    r = 4
    for sname in sub_names:
        dc(ws, r, 1, f'{sname} stock (mM)', B, LT)
        dc(ws, r, 2, stocks[sname]['conc_mM'])
        stock_rows[sname] = r
        r += 1
    for bname in buf_names:
        dc(ws, r, 1, f'{bname} stock (mM)', B, LT)
        dc(ws, r, 2, stocks[bname]['conc_mM'])
        stock_rows[bname] = r
        r += 1

    vol_row = r
    dc(ws, r, 1, 'Total volume (uL)', B, LT)
    dc(ws, r, 2, vol)
    r += 2

    # Enzyme info
    enz_row_start = r
    dc(ws, r, 1, 'Enzyme', B, LT)
    dc(ws, r, 2, 'Stock (g/L)', B)
    levels = set()
    for e in enzymes.values():
        levels.update(e['rxn_gL'].keys())
    level_list = sorted(levels)
    for i, lv in enumerate(level_list):
        dc(ws, r, 3 + i, f'{lv} (g/L)', B)
    r += 1

    enz_rows = {}
    for ename in enz_names:
        einfo = enzymes[ename]
        dc(ws, r, 1, f'{ename} ({einfo["batch"]})', N, LT)
        dc(ws, r, 2, einfo['stock_gL'])
        for i, lv in enumerate(level_list):
            dc(ws, r, 3 + i, einfo['rxn_gL'].get(lv, ''))
        enz_rows[ename] = r
        r += 1

    r += 1

    # Header row
    r0 = r
    for c, h in enumerate(all_cols, 1):
        ws.cell(row=r0, column=c, value=h)
    hdr(ws, r0, NC)
    r = r0 + 1

    # Map column indices
    ci = {}
    ci['type'] = 1
    ci['num'] = 2
    idx = 3
    for s in sub_names:
        ci[f'{s}_mM'] = idx; idx += 1
    for b in buf_names:
        ci[f'{b}_mM'] = idx; idx += 1
    for s in sub_names:
        ci[f'{s}_uL'] = idx; idx += 1
    for b in buf_names:
        ci[f'{b}_uL'] = idx; idx += 1
    for e in enz_names:
        ci[f'{e}_uL'] = idx; idx += 1
    ci['DW'] = idx; idx += 1
    ci['Total'] = idx; idx += 1
    ci['Note'] = idx

    # Data rows
    fd, ld = None, None
    current_group = None
    for cond in conditions:
        grp = cond.get('group', '')
        if grp != current_group:
            sec(ws, r, NC, grp)
            current_group = grp
            r += 1

        if fd is None:
            fd = r
        ld = r

        dc(ws, r, ci['type'], 'Exp')
        dc(ws, r, ci['num'], cond['num'])

        # Substrate mM values
        for s in sub_names:
            dc(ws, r, ci[f'{s}_mM'], cond['substrates'].get(s, 0))

        # Buffer mM values
        for b in buf_names:
            dc(ws, r, ci[f'{b}_mM'], buffer_stocks[b]['final_mM'])

        # Substrate uL formulas
        for s in sub_names:
            mM_col = get_column_letter(ci[f'{s}_mM'])
            sr = stock_rows[s]
            fml(ws, r, ci[f'{s}_uL'], f'=ROUND({mM_col}{r}*$B${vol_row}/$B${sr},4)')

        # Buffer uL formulas
        for b in buf_names:
            mM_col = get_column_letter(ci[f'{b}_mM'])
            sr = stock_rows[b]
            fml(ws, r, ci[f'{b}_uL'], f'=ROUND({mM_col}{r}*$B${vol_row}/$B${sr},4)')

        # Enzyme uL formulas
        for e in enz_names:
            level = cond['enzymes'].get(e, '1x')
            # Find the column in enzyme info that has this level's g/L
            lv_idx = level_list.index(level)
            lv_col = get_column_letter(3 + lv_idx)
            er = enz_rows[e]
            fml(ws, r, ci[f'{e}_uL'], f'=ROUND(${lv_col}${er}*$B${vol_row}/$B${er},4)')

        # DW
        first_uL = ci[f'{sub_names[0]}_uL']
        last_uL = ci[f'{enz_names[-1]}_uL']
        fl = get_column_letter(first_uL)
        ll = get_column_letter(last_uL)
        fml(ws, r, ci['DW'], f'=ROUND($B${vol_row}-SUM({fl}{r}:{ll}{r}),4)')
        ws.cell(row=r, column=ci['DW']).fill = YF

        # Total
        dw_col = get_column_letter(ci['DW'])
        fml(ws, r, ci['Total'], f'=SUM({fl}{r}:{dw_col}{r})')

        dc(ws, r, ci['Note'], cond.get('note', ''), N, LT)
        r += 1

    # Enzyme totals
    r += 1
    for e in enz_names:
        ecol = get_column_letter(ci[f'{e}_uL'])
        dc(ws, r, ci[f'{e}_uL'] - 1, f'{e} total (x{pipette_count.SURPLUS:g}):', B, LT)
        fml(ws, r, ci[f'{e}_uL'], f'=ROUND(SUM({ecol}{fd}:{ecol}{ld})*{pipette_count.SURPLUS},2)').font = B
    r += 1
    dc(ws, r, 1, note, NOTE, LT)

    # Column widths
    for c in range(1, NC + 1):
        ws.column_dimensions[get_column_letter(c)].width = 10
    ws.column_dimensions['A'].width = 8
    ws.column_dimensions[get_column_letter(ci['Note'])].width = 22

    # ═══════════════════════════════════════════
    # SHEET 2: Pipetting Guide
    # ═══════════════════════════════════════════
    ws2 = wb.create_sheet('Pipetting Guide')
    ws2.sheet_properties.tabColor = '70AD47'

    ws2.merge_cells('A1:H1')
    ws2['A1'] = 'Optimized Pipetting Guide'
    ws2['A1'].font = T
    dc(ws2, 2, 1, f'Date: {date}', B, LT)

    r = 4
    dc(ws2, r, 1, 'MM-A: Buffer + Cofactors' + (' + common water' if common_water else '') + ' (all conditions)', S, LT)
    r += 1
    n_rxns = pc_plan['mm_a_rxns']  # n tubes + premix.extra_rxns (default 3)
    dc(ws2, r, 1, '# rxns (with margin)', B, LT)
    dc(ws2, r, 2, n_rxns)
    r += 1

    for c, h in enumerate(['Component', 'Stock (mM)', 'Final (mM)', 'Per rxn (uL)', f'x{n_rxns} (uL)'], 1):
        ws2.cell(row=r, column=c, value=h)
    hdr(ws2, r, 5)
    r += 1

    ma_start = r
    for bname in buf_names:
        binfo = buffer_stocks[bname]
        dc(ws2, r, 1, bname, N, LT)
        dc(ws2, r, 2, binfo['conc_mM'])
        dc(ws2, r, 3, binfo['final_mM'])
        fml(ws2, r, 4, f'=ROUND(C{r}*{vol}/B{r},4)')
        fml(ws2, r, 5, f'=ROUND(D{r}*{n_rxns}/{res},0)*{res}')
        r += 1
    # R1: MM-A carries the common water, sized so the tightest tube closes with no top-up -- or
    # lowered so that no tube is left a DW top-up below the pipette floor (pipette_count._assign_water)
    water_common = 0.0
    if common_water and pc_plan['water_common_uL'] > pipette_count.EPS_UL:
        water_common = pc_plan['water_common_uL']
        label = ('DW (common water, R1: tightest tube needs no top-up)'
                 if water_common >= pc_plan['water_common_max_uL'] - pipette_count.EPS_UL
                 else 'DW (common water, R1: lowered so every DW top-up is 0 or >= the pipette floor)')
        dc(ws2, r, 1, label, N, LT)
        dc(ws2, r, 4, water_common)
        fml(ws2, r, 5, f'=ROUND(D{r}*{n_rxns}/{res},0)*{res}')
        r += 1
    ma_end = r - 1

    dc(ws2, r, 1, 'TOTAL', B, LT)
    fml(ws2, r, 4, f'=SUM(D{ma_start}:D{ma_end})').font = B
    fml(ws2, r, 5, f'=SUM(E{ma_start}:E{ma_end})').font = B
    ma_total = r

    # Sub-mix analysis
    r += 2
    dc(ws2, r, 1, 'SUBSTRATE GROUPING (conditions with identical substrates)', S, LT)
    r += 1
    for c, h in enumerate(['Group', 'Conditions', 'Components', '# tubes'], 1):
        ws2.cell(row=r, column=c, value=h)
    hdr(ws2, r, 4)
    r += 1

    for i, sm in enumerate(sub_mixes):
        comp_str = ', '.join(f'{k}={v}' for k, v in sm['components'].items())
        cond_str = ', '.join(f'#{n}' for n in sm['conditions'])
        dc(ws2, r, 1, f'SM-{i+1}', B)
        dc(ws2, r, 2, cond_str, N, LT)
        dc(ws2, r, 3, comp_str, N, LT)
        dc(ws2, r, 4, sm['count'])
        for c in range(1, 5):
            ws2.cell(row=r, column=c).fill = GF
        r += 1

    # Per-tube volumes
    r += 1
    dc(ws2, r, 1, 'PER-TUBE VOLUME BREAKDOWN', T, LT)
    r += 1
    dc(ws2, r, 1, f'Exact design volumes. PIPETTE the volumes rounded to {res:g} uL in sheet "Enzyme Additions" '
                  f'(DW re-closed after rounding; a no-enzyme control gets WATER in place of the enzyme additions, '
                  f'so its DW below is split into the same volumes as the enzyme tubes).', NOTE, LT)
    r += 1
    dc(ws2, r, 1, note, NOTE, LT)
    r += 1

    vol_cols = ['#', 'MM-A'] + sub_names + ['DW top-up' if common_water else 'DW'] + enz_names + ['Total']
    for c, h in enumerate(vol_cols, 1):
        ws2.cell(row=r, column=c, value=h)
    hdr(ws2, r, len(vol_cols))
    r += 1

    for cond in conditions:
        ci2 = 1
        dc(ws2, r, ci2, f'#{cond["num"]}', B); ci2 += 1
        fml(ws2, r, ci2, f'=$D${ma_total}'); ci2 += 1  # MM-A

        for s in sub_names:
            conc = cond['substrates'].get(s, 0)
            stock = stocks[s]['conc_mM']
            fml(ws2, r, ci2, f'=ROUND({conc}*{vol}/{stock},4)'); ci2 += 1

        # DW column — will fill after enzymes
        dw_ci = ci2; ci2 += 1

        for e in enz_names:
            level = cond['enzymes'].get(e, '1x')
            rxn_gL = enzymes[e]['rxn_gL'][level]
            stock_gL = enzymes[e]['stock_gL']
            fml(ws2, r, ci2, f'=ROUND({rxn_gL}*{vol}/{stock_gL},4)'); ci2 += 1

        # Total col
        total_ci = ci2
        b_col = get_column_letter(2)
        last_col = get_column_letter(ci2 - 1)
        # DW = vol - (MM-A + substrates + enzymes)
        fml(ws2, r, dw_ci, f'=ROUND({vol}-{b_col}{r}-' +
            '-'.join(get_column_letter(3 + i) + str(r) for i in range(len(sub_names))) +
            '-' + '-'.join(get_column_letter(dw_ci + 1 + i) + str(r) for i in range(len(enz_names))) +
            ',4)')
        ws2.cell(row=r, column=dw_ci).fill = YF

        fml(ws2, r, total_ci, f'={b_col}{r}+' +
            '+'.join(get_column_letter(3 + i) + str(r) for i in range(len(sub_names))) +
            f'+{get_column_letter(dw_ci)}{r}+' +
            '+'.join(get_column_letter(dw_ci + 1 + i) + str(r) for i in range(len(enz_names))))
        r += 1

    for c in range(1, len(vol_cols) + 1):
        ws2.column_dimensions[get_column_letter(c)].width = 12
    ws2.column_dimensions['A'].width = 8

    _enzyme_additions_sheet(wb, pc_plan, pc_sum, date)

    # ═══════════════════════════════════════════
    # SHEET 3: Sampling & Fed
    # ═══════════════════════════════════════════
    ws3 = wb.create_sheet('Sampling & Fed')
    ws3.sheet_properties.tabColor = 'FFC000'

    ws3.merge_cells('A1:D1')
    ws3['A1'] = 'Sampling & Fed Diagnosis'
    ws3['A1'].font = T
    dc(ws3, 2, 1, f'Date: {date}', B, LT)

    r = 4
    sampling = config.get('sampling', {})
    if sampling:
        dc(ws3, r, 1, 'SAMPLING', S, LT); r += 1
        for c, h in enumerate(['Parameter', 'Value'], 1):
            ws3.cell(row=r, column=c, value=h)
        hdr(ws3, r, 2); r += 1
        for p, v in [('Sample volume', f'{sampling.get("volume_uL", 5)} uL'),
                     ('Dilution', sampling.get('dilution', '20x')),
                     ('Timepoints', ', '.join(config.get('timepoints', []))),
                     ('Quench', sampling.get('quench', 'Heat 95C 5 min')),
                     ('Analysis', sampling.get('analysis', 'HPLC')),
                     ('Targets', ', '.join(sampling.get('targets', [])))]:
            dc(ws3, r, 1, p, N, LT); dc(ws3, r, 2, v, N, LT); r += 1

    fed = config.get('fed_diagnosis')
    if fed:
        r += 1
        dc(ws3, r, 1, f'FED DIAGNOSIS (from #{fed["source_condition"]} at 3h)', S, LT); r += 1
        for c, h in enumerate(['Fed #', 'Component', 'Amount', 'Purpose'], 1):
            ws3.cell(row=r, column=c, value=h)
        hdr(ws3, r, 4); r += 1
        for feed in fed['feeds']:
            dc(ws3, r, 1, feed['id'], B)
            dc(ws3, r, 2, feed['component'], N, LT)
            dc(ws3, r, 3, feed['amount'], N, LT)
            dc(ws3, r, 4, feed.get('purpose', ''), N, LT)
            r += 1
        r += 1
        dc(ws3, r, 1, f'Fed sampling: {", ".join(fed.get("timepoints", []))}', B, LT)

    for c, w in {1: 20, 2: 28, 3: 18, 4: 20}.items():
        ws3.column_dimensions[get_column_letter(c)].width = w

    # ═══════════════════════════════════════════
    # SHEET 4: Data
    # ═══════════════════════════════════════════
    ws4 = wb.create_sheet('Data')
    ws4.sheet_properties.tabColor = 'ED7D31'

    tps = config.get('timepoints', ['30 min', '1.5 h', '3 h'])
    n_tp = len(tps)
    data_cols = ['#', 'Condition'] + [f'Product (mM)\n{tp}' for tp in tps] + [f'Yield (%)\n{tp}' for tp in tps]

    ws4.merge_cells(f'A1:{get_column_letter(len(data_cols))}1')
    ws4['A1'] = 'Data Recording'
    ws4['A1'].font = T
    dc(ws4, 2, 1, f'Date: {date}    Analyst: ________', N, LT)

    r = 4
    for c, h in enumerate(data_cols, 1):
        ws4.cell(row=r, column=c, value=h)
    hdr(ws4, r, len(data_cols))
    r += 1

    c2_row = None
    for cond in conditions:
        dc(ws4, r, 1, cond['num'])
        dc(ws4, r, 2, cond.get('label', cond.get('note', '')), N, LT)
        # Data entry cells
        for i in range(n_tp):
            dc(ws4, r, 3 + i, None, fill=YF)
        # Yield formulas — use yield_substrate from config, or largest substrate conc
        yield_sub = config.get('yield_substrate')
        if yield_sub:
            denom = cond['substrates'].get(yield_sub, 100)
        else:
            # Pick substrate with highest concentration (exclude cofactors)
            real_subs = {k: v for k, v in cond['substrates'].items()
                        if stocks.get(k, {}).get('type') == 'substrate'}
            if real_subs:
                denom = max(real_subs.values())
            else:
                denom = max(cond['substrates'].values())
        for i in range(n_tp):
            data_col = get_column_letter(3 + i)
            yield_col_idx = 3 + n_tp + i
            cell = ws4.cell(row=r, column=yield_col_idx,
                           value=f'=IF({data_col}{r}="","",ROUND({data_col}{r}/{denom}*100,1))')
            cell.font, cell.alignment, cell.border, cell.number_format = N, CT, TB, '0.0'

        if cond['num'] == config.get('fed_diagnosis', {}).get('source_condition'):
            c2_row = r
        r += 1

    # Fed data section
    if fed and c2_row:
        r += 1
        ws4.merge_cells(f'A{r}:{get_column_letter(len(data_cols))}{r}')
        ws4.cell(row=r, column=1, value=f'Fed Diagnosis (from #{fed["source_condition"]})').font = S
        r += 1
        fed_tps = fed.get('timepoints', ['+30 min', '+1 h'])
        fed_cols = ['Fed #', 'Added'] + [f'Product (mM)\n{tp}' for tp in fed_tps] + ['Delta', 'Resumed?']
        for c, h in enumerate(fed_cols, 1):
            ws4.cell(row=r, column=c, value=h)
        hdr(ws4, r, len(fed_cols))
        r += 1

        for feed in fed['feeds']:
            dc(ws4, r, 1, feed['id'], B)
            dc(ws4, r, 2, feed['component'], N, LT)
            for i in range(len(fed_tps)):
                dc(ws4, r, 3 + i, None, fill=YF)
            # Delta
            last_tp_col = get_column_letter(2 + n_tp)  # last timepoint of main data for source condition
            cell = ws4.cell(row=r, column=3 + len(fed_tps),
                           value=f'=IF(C{r}="","",ROUND(C{r}-{last_tp_col}{c2_row},1))')
            cell.font, cell.alignment, cell.border, cell.number_format = N, CT, TB, '0.0'
            dc(ws4, r, 4 + len(fed_tps), None, fill=YF)
            r += 1

    for c in range(1, len(data_cols) + 1):
        ws4.column_dimensions[get_column_letter(c)].width = 14
    ws4.column_dimensions['A'].width = 6
    ws4.column_dimensions['B'].width = 22

    wb.save(output_path)

    # Report (the legacy 'Pipetting: ~N (saved ...)' estimate counted 0 uL cells and is removed -- the step
    # model below is the only pipetting count)
    print(f'Generated: {output_path}')
    print(f'Sheets: {len(wb.sheetnames)}')
    print(f'Conditions: {len(conditions)}')
    print(f'Master mix groups: MM-A ({len(buf_names)} components) + {len(sub_mixes)} sub-mixes')
    print(pipette_count.summary_line(pc_sum))
    return str(output_path)


def _enzyme_additions_sheet(wb, plan, summ, date):
    """Sheet 'Enzyme Additions': working-stock dilution table (lab stock + WATER), cocktails, the per-tube
    addition table in pipetting order, and the pipette count. A workbook without these is not finished
    (SKILL.md HARD RULES)."""
    import pipette_count
    ws = wb.create_sheet('Enzyme Additions')
    ws.sheet_properties.tabColor = '7030A0'
    ws['A1'] = 'Enzyme working stocks, cocktails and per-tube additions'
    ws['A1'].font = T
    dc(ws, 2, 1, f'Date: {date}', B, LT)
    r = 4
    res = pipette_count.limits(plan['config'])['resolution_uL']
    rq = lambda x: round(round(x / res) * res, 4)
    dc(ws, 3, 1, surplus_note(pipette_count.mm_a_extra(plan["config"])), NOTE, LT)
    dc(ws, r, 1, 'ENZYME WORKING STOCKS - dilute the lab stock with WATER (same volume of a level\'s stock in every tube)', S, LT)
    r += 1
    heads = ['Working stock', 'Enzyme', 'Lab stock (g/L)', 'Dilution (x)', 'Working (g/L)', 'uL per tube',
             'Needed (uL)', 'Make (uL)', 'Lab stock (uL)', 'water (uL)']
    for c, h in enumerate(heads, 1):
        ws.cell(row=r, column=c, value=h)
    hdr(ws, r, len(heads))
    r += 1
    if not plan['working']:
        dc(ws, r, 1, 'none - every enzyme is taken from its lab stock', N, LT)
        r += 1
    for wk in plan['working']:
        vals = [wk['working_stock'], wk['enzyme'], round(wk['lab_gL'], 4), round(wk['dilution_x'], 4),
                round(wk['working_gL'], 4), rq(wk['uL_per_tube']), round(wk['needed_uL'], 2), wk['make_uL'],
                rq(wk['lab_stock_uL']), rq(wk['water_uL'])]
        for c, v in enumerate(vals, 1):
            dc(ws, r, c, v, N, LT if c <= 2 else CT)
        r += 1
    r += 1
    cocktails = defaultdict(list)
    for s in plan['steps']:
        if s.kind == 'cocktail':
            cocktails[s.target].append(s)
    if cocktails:
        dc(ws, r, 1, f'ENZYME COCKTAILS (n x {pipette_count.SURPLUS} + {pipette_count.DEAD_UL:g} uL dead)', S, LT)
        r += 1
        for c, h in enumerate(['Cocktail', 'Component', 'uL to combine'], 1):
            ws.cell(row=r, column=c, value=h)
        hdr(ws, r, 3)
        r += 1
        for name, ss in cocktails.items():
            for s in ss:
                dc(ws, r, 1, name, N, LT); dc(ws, r, 2, s.source, N, LT); dc(ws, r, 3, rq(s.volume_uL))
                r += 1
        r += 1
    dc(ws, r, 1, 'PER-TUBE ADDITION TABLE (pipetting order; enzymes LAST)', S, LT)
    r += 1
    rp = pipette_count.rounded_plan(plan)
    dc(ws, r, 1, f'Pipette the "uL" column (rounded to {res:g} uL; DW re-closes every tube to the total). '
                 f'A no-enzyme control gets WATER in the same volumes as the enzyme additions (water_in_place).',
       NOTE, LT)
    r += 1
    for c, h in enumerate(['Tube', 'Step', 'Source', 'uL', 'exact uL'], 1):
        ws.cell(row=r, column=c, value=h)
    hdr(ws, r, 5)
    r += 1
    weigh = {t: (solid, mg) for t, solid, mg in plan['weighings']}
    for cond in plan['config']['conditions']:
        t = cond['num']
        tgt = f"#{t}"
        if t in weigh:
            dc(ws, r, 1, tgt, B); dc(ws, r, 2, 'weigh (solid, not pipetting)', N, LT)
            dc(ws, r, 3, weigh[t][0], N, LT); dc(ws, r, 4, f"{weigh[t][1]} mg")
            r += 1
        for kind, src, exact, rounded in rp['tubes'][t]:
            dc(ws, r, 1, tgt, B); dc(ws, r, 2, kind, N, LT); dc(ws, r, 3, src, N, LT)
            dc(ws, r, 4, rounded); dc(ws, r, 5, round(exact, 4))
            r += 1
    r += 1
    dc(ws, r, 1, f'ROUNDING CHECK (resolution {res:g} uL): max concentration deviation per component '
                 f'(WARN > {pipette_count.DEV_WARN * 100:g} %, FAIL > {pipette_count.DEV_FAIL * 100:g} %)', S, LT)
    r += 1
    for c, h in enumerate(['Component', 'deviation (%)', 'worst tube'], 1):
        ws.cell(row=r, column=c, value=h)
    hdr(ws, r, 3)
    r += 1
    for comp, (_, rel, t) in sorted(rp['deviation'].items(), key=lambda kv: -kv[1][0]):
        dc(ws, r, 1, comp, N, LT); dc(ws, r, 2, round(rel * 100, 2)); dc(ws, r, 3, f'#{t}')
        r += 1
    r += 1
    dc(ws, r, 1, 'PIPETTE COUNT (pipette_count.py)', S, LT)
    r += 1
    for k in ['prep_steps', 'prep_mixes', 'prep_dilutions', 'run_steps', 'per_tube_enzyme_steps_max', 'total_steps',
              'total_ops', 'weighings', 'distinct_volumes_run', 'distinct_volumes_all', 'below_1uL', 'below_2uL',
              'dw_steps_with_r1', 'dw_steps_without_r1', 'below_floor', 'below_comfort', 'settings_per_tube_max',
              'settings_run', 'identical_sequence', 'rounding_max_dev_pct', 'enzyme_lab_stock_total_uL']:
        dc(ws, r, 1, k, N, LT); dc(ws, r, 2, summ[k])
        r += 1
    for c, w in {1: 30, 2: 26, 3: 22, 4: 14}.items():
        ws.column_dimensions[get_column_letter(c)].width = w


def main():
    if len(sys.argv) < 2:
        print('Usage: python reaction_matrix.py config.json [output.xlsx]')
        sys.exit(1)

    config_path = Path(sys.argv[1])
    with open(config_path, encoding='utf-8') as f:
        config = json.load(f)

    output = sys.argv[2] if len(sys.argv) > 2 else str(config_path.with_suffix('.xlsx'))

    import pipette_count
    if isinstance(config, dict) and isinstance(config.get('enzymes'), dict) and 'conditions' in config \
            and pipette_count.is_spec(config):
        import equal_volume
        try:
            config = equal_volume.expand(config)
        except (ValueError, KeyError) as exc:
            print(f'=== validate_config: FAILED -- equal-volume spec could not be expanded: {exc} '
                  f'-- xlsx NOT generated. ===')
            sys.exit(1)
        print('=== equal-volume spec detected: expanded with equal_volume.expand() '
              '(one working-stock pseudo-enzyme per level) ===')

    ok, report = validate_config(config, source=str(config_path))
    print('=== validate_config ===')
    for line in report:
        print(line)
    if not ok:
        print('=== validate_config: FAILED -- xlsx NOT generated. Fix the config and re-run. ===')
        sys.exit(1)
    print('=== validate_config: all hard checks passed ===')

    generate_excel(config, output)


if __name__ == '__main__':
    main()
