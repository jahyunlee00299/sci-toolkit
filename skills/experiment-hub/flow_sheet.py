"""FLOW sheet for reaction_matrix.py workbooks (experiment-hub): the bench sheet.

The per-tube tables of the Pipetting Guide answer "what does tube n get?"; at the bench the question is "what do I
do next, and how much of each stock do I have to take out?". FLOW answers that in dispensing order:

  title / one-sentence sequence -> TAKE OUT (total uL of every stock for the whole run) -> PREP blocks
  (MM-A, substrate mixes, enzyme cocktail, working stocks) -> RUN (numbered steps, tubes grouped by identical
  volume) -> sampling -> a closing check.

Every number comes from pipette_count.build_plan / rounded_plan (and reaction_matrix.lab_stock_totals for the
enzyme stocks, the same function the Pipetting Guide block A uses); nothing is retyped. The sheet holds static
values only (no formulas), so it prints and reads the same everywhere.

  build_flow(plan, rplan)      -> plain dict (testable, no openpyxl)
  write_flow_sheet(wb, plan, rplan, config)  -> the 'FLOW' worksheet (first and active sheet)
"""
from __future__ import annotations

import math
import re
from collections import Counter, OrderedDict, defaultdict

import pipette_count as pc

SHEET_NAME = 'FLOW'
STAGE_WEIGH, STAGE_MM, STAGE_SUB, STAGE_DW, STAGE_WIP, STAGE_CK, STAGE_ENZ = 0, 1, 2, 3, 4, 5, 6


def tube_ranges(nums) -> str:
    """[1,2,3,28,29] -> '#1-3, #28-29'."""
    ns = sorted(set(nums))
    if not ns:
        return ''
    out, start, prev = [], ns[0], ns[0]
    for x in ns[1:] + [None]:
        if x is None or x != prev + 1:
            out.append(f'#{start}' if start == prev else f'#{start}-{prev}')
            start = x
        prev = x if x is not None else prev
    return ', '.join(out)


def _decimals(res: float) -> int:
    s = f'{res:.10f}'.rstrip('0')
    return len(s.split('.')[1]) if '.' in s else 0


def _fmt(v: float, res: float) -> str:
    return f'{v:.{_decimals(res)}f}'


def _group_token(cond: dict) -> str:
    txt = (cond.get('group') or cond.get('label') or '').strip()
    return txt.split()[0] if txt else ''


def _enzyme_entry(cfg: dict, real: str) -> dict:
    return next((v for k, v in cfg['enzymes'].items() if pc.real_name(k, v) == real), {})


def _batch(cfg: dict, source: str, real: str | None = None) -> str:
    e = cfg['enzymes'].get(source) or (_enzyme_entry(cfg, real) if real else {})
    return str(e.get('batch', 'n/a')) if e else ''


# ---------------------------------------------------------------- data layer
def build_flow(plan: dict, rplan: dict) -> dict:
    import reaction_matrix as rm
    cfg = plan['config']
    V = float(cfg['total_volume_uL'])
    res = rplan['res']
    rq = lambda x: pc._rnd(x, res)
    conds = cfg['conditions']
    tubes = [c['num'] for c in conds]
    route = plan['route']
    short = {rec['name']: f'S{i}' for i, rec in enumerate(plan['submixes'], 1)}
    gtok = {c['num']: _group_token(c) for c in conds}
    flow: dict = {'res': res, 'V': V, 'tubes': tubes, 'short': short}

    # ---- header -------------------------------------------------------------------------------------------
    flow['title'] = cfg.get('title', 'Reaction Matrix')
    flow['date'] = cfg.get('date', '')
    flow['info'] = (f"{len(tubes)} tubes | {V:g} uL per tube | "
                    + (f"{cfg['temperature_C']:g} C" if cfg.get('temperature_C') is not None else 'temperature: see protocol'))

    # ---- TAKE OUT -------------------------------------------------------------------------------------------
    tot = rm.lab_stock_totals(plan)
    take = []
    for n in tot['names']:
        e = _enzyme_entry(cfg, n)
        used = [lbl for key, lbl in (('cocktail', 'enzyme cocktail'), ('working', 'working stocks'),
                                     ('direct', 'direct to tubes')) if n in tot[key]]
        total = tot['cocktail'].get(n, 0) + tot['working'].get(n, 0) + tot['direct'].get(n, 0)
        take.append({'stock': n, 'batch': e.get('batch', 'n/a'), 'conc': f"{pc.lab_stock_of(e):.2f} g/L" if e else '',
                     'total_uL': rq(total), 'used_in': ', '.join(used), 'kind': 'enzyme'})
    sm_use = defaultdict(list)
    for rec in plan['submixes']:
        for s in rec['draws']:
            if s != 'water':
                sm_use[s].append(short[rec['name']])
    direct_use = defaultdict(int)
    for s in plan['steps']:
        if s.phase == 'run' and s.kind == 'substrate' and s.source in cfg['stocks']:
            direct_use[s.source] += 1
    mm_use = {s.source for s in plan['steps'] if s.phase == 'prep' and s.kind == 'mm_a'}
    enz_names = {pc.real_name(k, v) for k, v in cfg['enzymes'].items()}
    for stock, info in cfg['stocks'].items():
        if stock in enz_names or stock not in plan['lab_uL']:
            continue
        used = []
        if stock in mm_use:
            used.append('MM-A')
        if sm_use.get(stock):
            used.append(f"substrate mixes {', '.join(sm_use[stock])}")
        if direct_use.get(stock):
            used.append('direct to tubes')
        take.append({'stock': stock, 'batch': '', 'conc': f"{float(info['conc_mM']):g} mM",
                     'total_uL': rq(plan['lab_uL'][stock]), 'used_in': '; '.join(used),
                     'kind': 'buffer' if info['type'] == 'buffer' else 'substrate'})
    take.sort(key=lambda r: {'enzyme': 0, 'substrate': 1, 'buffer': 2}[r['kind']])   # stable: frozen tubes first
    flow['take_out'] = take

    # ---- PREP: MM-A -----------------------------------------------------------------------------------------
    mm_rows, n_mm = [], plan['mm_a_rxns']
    mm_steps = [s for s in plan['steps'] if s.phase == 'prep' and s.kind == 'mm_a' and s.target == 'MM-A']
    for s in mm_steps:
        common = s.source.startswith('water')
        st = cfg['stocks'].get(s.source, {})
        mm_rows.append({'component': 'DW (common water)' if common else s.source,
                        'stock_mM': None if common else st.get('conc_mM'),
                        'final_mM': None if common else st.get('final_mM'),
                        'per_rxn': round(s.volume_uL / n_mm, 4), 'total_uL': rq(s.volume_uL)})
    flow['mm_a'] = ({'n_rxns': n_mm, 'rows': mm_rows, 'per_rxn_total': round(sum(r['per_rxn'] for r in mm_rows), 4),
                     'total_uL': round(sum(r['total_uL'] for r in mm_rows), 4)} if mm_rows else None)

    # ---- PREP: substrate mixes ---------------------------------------------------------------------------
    mixes, comp_cols = [], []
    for rec in plan['submixes']:
        draws = {k: rq(v) for k, v in rec['draws'].items()}
        for k in draws:
            if k != 'water' and k not in comp_cols:
                comp_cols.append(k)
        spare_txt = (f"{rec['spare_tubes']:g} spare tube(s) = {rec['dead_uL']:.1f} uL"
                     if cfg.get('submix_dead_volume_uL') is None else f"{rec['dead_uL']:g} uL dead (fixed)")
        mixes.append({'mix': short[rec['name']], 'sm': rec['name'], 'tubes': tube_ranges(rec['conditions']),
                      'groups': ', '.join(OrderedDict.fromkeys(gtok[t] for t in rec['conditions'] if gtok[t])),
                      'n': len(rec['conditions']), 'draws': draws, 'water': draws.get('water', 0.0),
                      'total_uL': round(sum(draws.values()), 4), 'per_tube': rq(rec['per_tube']),
                      'spare': spare_txt})
    flow['mixes'] = {'columns': comp_cols, 'rows': mixes}

    # ---- PREP: cocktails, working stocks -----------------------------------------------------------------
    einfo = cfg['enzymes']

    def is_ws(src):
        e = einfo.get(src)
        return bool(e) and pc.lab_stock_of(e) / float(e['stock_gL']) > pc.NEAT_TOL

    cks = []
    for ck in route['cocktails']:
        rows = []
        for src, v in ck['comps'].items():
            a = route['src_info'].get(src)
            real = a['enzyme'] if a else src.replace(' (lab stock)', '')
            if is_ws(src):
                rows.append({'component': f'{src} (working stock)', 'batch': _batch(cfg, src),
                             'gL': float(einfo[src]['stock_gL']), 'uL': rq(v * ck['scale'])})
            else:
                e = _enzyme_entry(cfg, real)
                rows.append({'component': real, 'batch': e.get('batch', 'n/a'),
                             'gL': pc.lab_stock_of(e) if e else None, 'uL': rq(v * ck['scale'])})
        if ck['water_per_tube'] > pc.EPS_UL:
            rows.append({'component': 'water', 'batch': '', 'gL': None, 'uL': rq(ck['water_per_tube'] * ck['scale'])})
        cks.append({'name': ck['name'], 'rows': rows, 'total_uL': round(sum(r['uL'] for r in rows), 4),
                    'per_tube': rq(ck['per_tube']), 'tubes': tube_ranges(ck['members'])})
    flow['cocktails'] = cks

    lines = []
    serial = tot['serial']
    for enz, rows_ in serial.items():
        for x in rows_:
            take_uL = rq(x['src_uL'])
            lines.append({'stock': x['stock'], 'gL': x['working_gL'], 'per_tube': rq(x['per_tube']),
                          'how': f"{take_uL:g} uL {x['src']} + {rq(x['make_uL'] - take_uL):g} uL water -> "
                                 f"{x['make_uL']:g} uL; mix"})
    for wk in plan['working']:
        if wk['enzyme'] in serial:
            continue
        lab = rq(wk['lab_stock_uL'])
        w_uL = rq(wk['water_uL'])
        lines.append({'stock': wk['working_stock'], 'gL': wk['working_gL'], 'per_tube': rq(wk['uL_per_tube']),
                      'how': (f"{lab:g} uL {wk['enzyme']} lab stock + {w_uL:g} uL water -> {wk['make_uL']:g} uL; mix"
                              if w_uL else f"{wk['enzyme']} lab stock used as is ({lab:g} uL)")})
    flow['working'] = lines

    # ---- RUN -------------------------------------------------------------------------------------------------
    tube_entries: dict[int, list] = {}
    for t in tubes:
        ents, wip = [], []
        for kind, src, _exact, rd in rplan['tubes'][t]:
            if kind == 'water_in_place':
                wip.append(rd)
                continue
            if wip:
                ents.append(((STAGE_WIP,), 'Water in place of the enzymes (no-enzyme control)', tuple(wip)))
                wip = []
            if kind == 'mm_a':
                ents.append(((STAGE_MM,), 'MM-A', (rd,)))
            elif kind == 'substrate':
                if src in short:
                    ents.append(((STAGE_SUB, 0), f'Substrate mix {short[src]}', (rd,)))
                else:
                    ents.append(((STAGE_SUB, 1, src), f'{src} (stock)', (rd,)))
            elif kind == 'dw':
                ents.append(((STAGE_DW,), 'Water (DW top-up)', (rd,)))
            elif kind == 'cocktail_add':
                ents.append(((STAGE_CK, src), 'Enzyme cocktail' if src == 'common cocktail' else f'Enzyme cocktail ({src})', (rd,)))
            else:
                real = pc.real_name(src, einfo[src]) if src in einfo else src
                ents.append(((STAGE_ENZ, real), src, (rd,)))
        if wip:
            ents.append(((STAGE_WIP,), 'Water in place of the enzymes (no-enzyme control)', tuple(wip)))
        tube_entries[t] = ents
    # a "water in place" row sits before the enzymes in every tube; keep that order for a sequence that
    # starts with it (rounded_plan appends those rows after the cocktail/enzyme rows of an enzyme tube)
    steps = OrderedDict()                  # stage key -> {'order', 'first', 'alts': OrderedDict}
    for t in tubes:
        for key, label, vols in tube_entries[t]:
            st = steps.setdefault(key, {'order': key, 'first': len(steps), 'alts': OrderedDict()})
            st['alts'].setdefault((label, vols), []).append(t)
    weigh = OrderedDict()
    for t, solid, mg in plan['weighings']:
        weigh.setdefault((solid, mg), []).append(t)
    run, no = [], 0
    if weigh:
        no += 1
        for (solid, mg), ts in weigh.items():
            run.append({'step': no, 'what': f'Weigh {solid} (solid) into the empty tube', 'volume': f'{mg:g} mg',
                        'tubes': tube_ranges(ts), 'tube_list': sorted(ts), 'stage': 'weigh'})
    last_enz = None
    for key, st in sorted(steps.items(), key=lambda kv: (kv[1]['order'][0], kv[1]['first'])):
        no += 1
        for (label, vols), ts in st['alts'].items():
            vtxt = (f'{_fmt(sum(vols), res)} uL' if len(vols) == 1 else
                    f"{' + '.join(_fmt(v, res) for v in vols)} uL (= {_fmt(sum(vols), res)} uL)")
            run.append({'step': no, 'what': label, 'volume': vtxt,
                        'tubes': f'all tubes ({tube_ranges(ts)})' if sorted(ts) == tubes else tube_ranges(ts),
                        'tube_list': sorted(ts), 'stage': key[0]})
    flow['run'] = run

    # ---- sequence sentence + check -----------------------------------------------------------------------
    seqs = {t: tuple(r[3] for r in rplan['tubes'][t]) for t in tubes}
    cnt = Counter(seqs.values())
    modal_vols, modal_n = cnt.most_common(1)[0]
    t0 = next(t for t in tubes if seqs[t] == modal_vols)
    parts = []
    for key, label, vols in tube_entries[t0]:
        st = key[0]
        if st == STAGE_MM:
            nm = 'MM-A'
        elif st == STAGE_SUB:
            nm = 'substrate mix' if key[1] == 0 else key[2]
        elif st == STAGE_DW:
            nm = 'DW'
        elif st == STAGE_WIP:
            nm = 'water'
        elif st == STAGE_CK:
            nm = 'enzyme cocktail'
        else:
            nm = key[1]
        parts.append(f"{nm} {_fmt(sum(vols), res)}")
    seq = ' -> '.join(parts)
    n_dw = sum(1 for t in tubes if rplan['dw'].get(t, 0) > 0)
    sent = (f'Every tube gets the same volumes in this order: {seq} uL.' if len(cnt) == 1 else
            f'{modal_n} of {len(tubes)} tubes get, in this order: {seq} uL; the other tubes differ (see RUN).')
    if plan.get('submix_water') and n_dw == 0:
        sent += ' No separate water top-up: the water is inside each substrate mix.'
    elif n_dw:
        sent += f' {n_dw} tube(s) still need a separate water top-up (see RUN).'
    flow['sentence'] = sent
    flow['n_sequences'] = len(cnt)

    pats, bad = OrderedDict(), []
    for t in tubes:
        tot_t = round(sum(seqs[t]), 6)
        pats.setdefault(seqs[t], []).append(t)
        if abs(tot_t - V) > 1e-6:
            bad.append((t, tot_t))
    flow['check'] = {'patterns': [{'vols': v, 'sum': round(sum(v), 6), 'tubes': tube_ranges(ts), 'tube_list': ts}
                                  for v, ts in pats.items()], 'bad': bad, 'ok': not bad}
    # ---- sampling ----------------------------------------------------------------------------------------------
    smp = cfg.get('sampling') or {}
    rows = []
    if smp or cfg.get('timepoints'):
        # a condition may carry its own "timepoints" (a subset of the run's): a time-course arm next to
        # end-point arms is then one row per schedule, so the bench sees which tubes are sampled when
        sched: dict[tuple, list] = {}
        for c in cfg['conditions']:
            sched.setdefault(tuple(c.get('timepoints') or cfg.get('timepoints', [])), []).append(c)
        if len(sched) > 1:
            tp_rows = [(f"Timepoints {tube_ranges([c['num'] for c in cs])} "
                        f"({', '.join(dict.fromkeys(_group_token(c) for c in cs))})",
                        f"{', '.join(tps)}  ({len(tps)} samples per tube)") for tps, cs in sched.items()]
        else:
            tp_rows = [('Timepoints', ', '.join(cfg.get('timepoints', [])))]
        rows = [('Sample volume', f"{smp.get('volume_uL', 5)} uL"), ('Dilution', str(smp.get('dilution', '20x'))),
                *tp_rows,
                ('Quench', str(smp.get('quench', 'Heat 95C 5 min'))), ('Analysis', str(smp.get('analysis', 'HPLC'))),
                ('Targets', ', '.join(smp.get('targets', [])))]
    flow['sampling'] = rows
    return flow


# ---------------------------------------------------------------- sheet writer
def write_flow_sheet(wb, plan: dict, rplan: dict, config: dict | None = None):
    import reaction_matrix as rm
    from openpyxl.styles import Alignment
    fl = build_flow(plan, rplan)
    res, V = fl['res'], fl['V']
    ws = wb.create_sheet(SHEET_NAME, 0)
    ws.sheet_properties.tabColor = 'C00000'
    WR = Alignment(horizontal='left', vertical='top', wrap_text=True)
    WC = Alignment(horizontal='center', vertical='top', wrap_text=True)
    widths = {'A': 16, 'B': 40, 'C': 24, 'D': 36, 'E': 18, 'F': 14, 'G': 14, 'H': 14, 'I': 24}
    for col, w in widths.items():
        ws.column_dimensions[col].width = w
    NCOL = 9
    state = {'r': 1}

    def row(values, aligns=None):
        r = state['r']
        for c, v in enumerate(values, 1):
            rm.dc(ws, r, c, v, rm.N, (aligns or {}).get(c, WR))
        state['r'] += 1
        return r

    def merged_text(text, font, height_chars=None):
        r = state['r']
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=NCOL)
        cl = ws.cell(row=r, column=1, value=text)
        cl.font, cl.alignment = font, WR
        total_w = sum(widths.values())
        lines = max(1, math.ceil(len(text) * 1.1 / total_w))
        ws.row_dimensions[r].height = max(15, 14 * lines)
        state['r'] += 1
        return r

    def header(values):
        r = state['r']
        for c, h in enumerate(values, 1):
            ws.cell(row=r, column=c, value=h)
        rm.hdr(ws, r, len(values))
        state['r'] += 1

    def section(text):
        state['r'] += 1
        rm.sec(ws, state['r'], NCOL, text)
        state['r'] += 1

    def fit_row_heights(first, last):
        colw = [widths.get(chr(64 + c), 10) for c in range(1, NCOL + 1)]
        for r in range(first, last + 1):
            if ws.row_dimensions[r].height:
                continue
            lines = 1
            for c in range(1, NCOL + 1):
                v = ws.cell(row=r, column=c).value
                if isinstance(v, str):
                    lines = max(lines, math.ceil(len(v) * 1.15 / max(colw[c - 1], 6)))
            if lines > 1:
                ws.row_dimensions[r].height = 13.5 * lines

    # ---- title ----------------------------------------------------------------------------------------------
    r = merged_text(fl['title'], rm.T)
    merged_text(f"Date: {fl['date']}  |  {fl['info']}", rm.B)
    merged_text(fl['sentence'], rm.N)

    # ---- TAKE OUT -----------------------------------------------------------------------------------------
    section('TAKE OUT - total uL of every stock for the WHOLE run, spare included (enzymes first, then substrates, then buffer components; take frozen stocks out first)')
    first = state['r']
    header(['Stock', 'Batch', 'Conc.', 'Total (uL)', 'Used in'])
    for t in fl['take_out']:
        row([t['stock'], t['batch'], t['conc'], t['total_uL'], t['used_in']], aligns={3: WC, 4: WC})
        ws.cell(row=state['r'] - 1, column=1).font = rm.B
        ws.cell(row=state['r'] - 1, column=4).font = rm.B
    fit_row_heights(first, state['r'] - 1)

    n_prep = 0

    def prep_title(text):
        nonlocal n_prep
        n_prep += 1
        section(f'PREP {n_prep} - {text}')

    # ---- PREP ---------------------------------------------------------------------------------------------
    if fl['mm_a']:
        mm = fl['mm_a']
        prep_title('MM-A (buffer + cofactors + common water), made once for all tubes')
        header(['Component', 'Stock (mM)', 'Final (mM)', f"Per rxn (uL)", f"x{mm['n_rxns']} (uL)"])
        for x in mm['rows']:
            row([x['component'], x['stock_mM'], x['final_mM'], round(x['per_rxn'], 2), x['total_uL']],
                aligns={2: WC, 3: WC, 4: WC, 5: WC})
        r = row(['TOTAL', None, None, round(mm['per_rxn_total'], 2), round(mm['total_uL'], 1)],
                aligns={4: WC, 5: WC})
        for c in range(1, 6):
            ws.cell(row=r, column=c).font = rm.B
    if fl['mixes']['rows']:
        mx = fl['mixes']
        prep_title(f"SUBSTRATE MIXES (water included, one tube each; spare volume stated per mix)")
        header(['Mix', 'Tubes', 'Groups', 'n tubes / uL per tube'] + [f'{c} (uL)' for c in mx['columns']]
               + ['Water (uL)', 'Total made (uL)', 'Spare'])
        first = state['r']
        for m in mx['rows']:
            row([m['mix'], m['tubes'], m['groups'], f"{m['n']} x {_fmt(m['per_tube'], res)}"]
                + [m['draws'].get(c) or None for c in mx['columns']]
                + [m['water'] or None, round(m['total_uL'], 1), m['spare']],
                aligns={4: WC})
            ws.cell(row=state['r'] - 1, column=1).font = rm.B
        fit_row_heights(first, state['r'] - 1)
    for ck in fl['cocktails']:
        prep_title(f"ENZYME {ck['name'].upper()} (combine in ONE tube; add {_fmt(ck['per_tube'], res)} uL to {ck['tubes']})")
        header(['Component', 'Batch', 'Lab stock (g/L)', 'uL to combine'])
        for x in ck['rows']:
            row([x['component'], x['batch'], round(x['gL'], 2) if x['gL'] else None, x['uL']],
                aligns={3: WC, 4: WC})
        r = row(['TOTAL', None, None, round(ck['total_uL'], 1)], aligns={4: WC})
        for c in range(1, 5):
            ws.cell(row=r, column=c).font = rm.B
    if fl['working']:
        prep_title('ENZYME WORKING STOCKS (dilute with WATER, highest first)')
        header(['Working stock', 'How to mix', 'Working (g/L)', 'uL per tube'])
        first = state['r']
        for x in fl['working']:
            row([x['stock'], x['how'], round(x['gL'], 4), x['per_tube']], aligns={3: WC, 4: WC})
        fit_row_heights(first, state['r'] - 1)

    # ---- RUN ------------------------------------------------------------------------------------------------
    section('RUN - in this order (enzymes LAST); tubes with the same volume are listed together')
    first = state['r']
    header(['Step', 'What', 'Volume', 'Tubes'])
    last_no = None
    for x in fl['run']:
        r = row([x['step'] if x['step'] != last_no else None, x['what'], x['volume'], x['tubes']],
                aligns={1: WC, 3: WC})
        ws.cell(row=r, column=1).font = rm.B
        last_no = x['step']
    fit_row_heights(first, state['r'] - 1)

    # ---- sampling -----------------------------------------------------------------------------------------
    if fl['sampling']:
        section('SAMPLING')
        for k, v in fl['sampling']:
            r = state['r']
            rm.dc(ws, r, 1, k, rm.B, WR)
            ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=NCOL)
            cl = ws.cell(row=r, column=2, value=v)
            cl.font, cl.alignment = rm.N, WR
            ws.row_dimensions[r].height = max(15, 14 * math.ceil(len(v) * 1.1 / sum(list(widths.values())[1:])))
            state['r'] += 1

    # ---- check ---------------------------------------------------------------------------------------------
    section('CHECK - the rounded volumes of every tube pattern add up to the total volume')
    ck = fl['check']
    for p in ck['patterns']:
        eq = ' + '.join(_fmt(v, res) for v in p['vols'])
        merged_text(f"{p['tubes']}: {eq} = {_fmt(p['sum'], res)} uL" + ('' if abs(p['sum'] - V) < 1e-6
                                                                     else f"   <-- does NOT close to {V:g} uL"), rm.N)
    merged_text('OK: every tube closes to %g uL.' % V if ck['ok'] else
                'NOT CLOSED: ' + ', '.join(f'#{t} = {s:g} uL' for t, s in ck['bad']), rm.B)

    ws.page_setup.orientation = 'landscape'
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    try:
        from openpyxl.worksheet.properties import PageSetupProperties
        ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    except ImportError:
        pass
    return ws
