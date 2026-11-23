"""A serially diluted level must not print independent-draw make/lab-stock/water figures.

When `serial_dilution` is active the
Pipetting Guide's block C holds the real recipe, and the `Enzyme Additions` working-stock table was
still printing the INDEPENDENT-draw figures for the same level, with only a prose
"ignore these columns" line above them.

The two numbers are not merely different, the independent one is SHORT: it sizes the make for that
level's own tubes and knows nothing about the transfer the next lower level draws out of it. With
the two sheets offering 'make 95 uL' and 'make 100 uL' for the same level, making 95 and then giving
5 uL to the serial step leaves 90 uL for 18 tubes x 5.0 uL -- zero dead volume, and the last tube
comes up short of the target concentration.
"""
import json
import sys
from pathlib import Path

import openpyxl
SK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SK))

import reaction_matrix                                                      # noqa: E402

CFG = SK / "tests" / "fixtures" / "pipette_rules" / "synthetic_serial_x8.json"
HEADS = ['Make (uL)', 'Lab stock (uL)', 'water (uL)']


def _build(tmp_path, **over):
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    cfg.update(over)
    out = tmp_path / "w.xlsx"
    reaction_matrix.generate_excel(cfg, str(out))
    return openpyxl.load_workbook(out)["Enzyme Additions"]


def _rows(ws):
    """(working_stock_name, {head: value}) for every row of the working-stock table."""
    hdr = next((r for r in range(1, 60)
                if ws.cell(row=r, column=8).value == 'Make (uL)'), None)
    assert hdr, "working-stock table header not found"
    cols = {ws.cell(row=hdr, column=c).value: c for c in range(1, 12)
            if ws.cell(row=hdr, column=c).value}
    out = []
    for r in range(hdr + 1, hdr + 20):
        name = ws.cell(row=r, column=1).value
        if not name or not isinstance(name, str) or '[' not in name:
            continue
        out.append((name, {h: ws.cell(row=r, column=cols[h]).value for h in HEADS}))
    return out


def test_serial_levels_print_no_independent_make_figures(tmp_path):
    ws = _build(tmp_path, serial_dilution="auto")
    rows = _rows(ws)
    assert rows, "no working-stock rows were written"
    for name, v in rows:
        assert v['Make (uL)'] == 'see Guide block C', (name, v)
        assert v['Lab stock (uL)'] is None, (name, v)
        assert v['water (uL)'] is None, (name, v)


def test_independent_draw_levels_still_print_their_recipe(tmp_path):
    """With serial dilution OFF the independent figures ARE the bench truth: keep printing them."""
    ws = _build(tmp_path, serial_dilution=[])
    rows = _rows(ws)
    assert rows, "no working-stock rows were written"
    for name, v in rows:
        assert isinstance(v['Make (uL)'], (int, float)), (name, v)
        assert isinstance(v['Lab stock (uL)'], (int, float)), (name, v)
        assert isinstance(v['water (uL)'], (int, float)), (name, v)
