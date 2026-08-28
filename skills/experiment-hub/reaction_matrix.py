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

# Windows' default console is cp949 and dies on Korean/symbol output. Force UTF-8.
# Use reconfigure: wrapping in TextIOWrapper would take ownership of the
# underlying stream, so once this module is imported and the wrapper gets
# GC'd, it closes the caller's stdout too (measured).
import sys as _sys
for _s in (_sys.stdout, _sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

import json
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
        dc(ws, r, ci[f'{e}_uL'] - 1, f'{e} total (x1.1):', B, LT)
        fml(ws, r, ci[f'{e}_uL'], f'=ROUND(SUM({ecol}{fd}:{ecol}{ld})*1.1,2)').font = B

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
    dc(ws2, r, 1, 'MM-A: Buffer + Cofactors (all conditions)', S, LT)
    r += 1
    n_rxns = len(conditions) + 3  # margin
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
        fml(ws2, r, 5, f'=ROUND(D{r}*{n_rxns},2)')
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

    vol_cols = ['#', 'MM-A'] + sub_names + ['DW'] + enz_names + ['Total']
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

    # Report
    total_without = len(conditions) * (len(sub_names) + len(buf_names) + len(enz_names) + 1)  # +1 for DW
    grouped_saves = sum(sm['count'] * len(sm['components']) for sm in sub_mixes)
    print(f'Generated: {output_path}')
    print(f'Sheets: {len(wb.sheetnames)}')
    print(f'Conditions: {len(conditions)}')
    print(f'Master mix groups: MM-A ({len(buf_names)} components) + {len(sub_mixes)} sub-mixes')
    print(f'Pipetting: ~{total_without - grouped_saves} (saved ~{grouped_saves} vs {total_without} ungrouped)')
    return str(output_path)


def main():
    if len(sys.argv) < 2:
        print('Usage: python reaction_matrix.py config.json [output.xlsx]')
        sys.exit(1)

    config_path = Path(sys.argv[1])
    with open(config_path, encoding='utf-8') as f:
        config = json.load(f)

    output = sys.argv[2] if len(sys.argv) > 2 else str(config_path.with_suffix('.xlsx'))
    generate_excel(config, output)


if __name__ == '__main__':
    main()
