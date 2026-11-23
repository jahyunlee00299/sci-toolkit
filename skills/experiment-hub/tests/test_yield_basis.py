"""Yield denominator resolution.

`yield_substrate` was once looked up only in the per-condition `substrates` dict, with
`.get(name, 100)` -- so a name that did not resolve silently became a denominator of 100.
A component held at one level in every tube is a `stocks` entry with `final_mM` (the MM-A
convention), not a per-condition substrate, and its yield column was right only when that
final happened to BE 100 mM. A reactant charged as a weighed SOLID has no concentration
anywhere in the config, so naming it could never work at all.

Three behaviours are pinned here:
  1. `yield_basis_mM` wins outright -- the only way to report on a reactant that sits
     outside the volume closure.
  2. `yield_substrate` resolves against `stocks[...]['final_mM']` as well as `substrates`.
  3. An unresolvable `yield_substrate` RAISES instead of quietly using 100.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import openpyxl
import pytest

SK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SK))

CFG = SK / "tests" / "fixtures" / "pipette_rules" / "synthetic_serial_x8.json"


def _cfg(**over):
    c = json.loads(CFG.read_text(encoding="utf-8"))
    c.update(over)
    return c


def _generate(tmp_path, cfg):
    p, out = tmp_path / "c.json", tmp_path / "w.xlsx"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    r = subprocess.run([sys.executable, str(SK / "reaction_matrix.py"), str(p), str(out), "--no-publish"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r, out


def _denominators(xlsx):
    """Every distinct denominator the Data sheet's yield formulas divide by."""
    ws = openpyxl.load_workbook(xlsx)["Data"]
    found = set()
    for row in ws.iter_rows():
        for c in row:
            if isinstance(c.value, str) and c.value.startswith("=IF("):
                m = re.search(r"/(\d+(?:\.\d+)?)\*100", c.value)
                if m:
                    found.add(float(m.group(1)))
    return found


def test_yield_basis_mM_wins(tmp_path):
    """A weighed solid has no concentration in the config; the explicit basis carries it."""
    r, out = _generate(tmp_path, _cfg(yield_basis_mM=50))
    assert r.returncode == 0, r.stdout + r.stderr
    assert _denominators(out) == {50.0}


def test_yield_basis_mM_beats_yield_substrate(tmp_path):
    r, out = _generate(tmp_path, _cfg(yield_basis_mM=50, yield_substrate="Substrate-S"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert _denominators(out) == {50.0}


def test_yield_substrate_resolves_against_stock_final_mM(tmp_path):
    """The named component is an MM-A stock, not a substrate."""
    cfg = _cfg()
    name, conc = "YieldBasisProbe", 77.0
    cfg["stocks"][name] = {"conc_mM": 1000, "type": "buffer", "final_mM": conc}
    cfg["yield_substrate"] = name
    for c in cfg["conditions"]:
        assert name not in c["substrates"]
    r, out = _generate(tmp_path, cfg)
    assert r.returncode == 0, r.stdout + r.stderr
    assert _denominators(out) == {conc}


def test_unresolvable_yield_substrate_raises_instead_of_defaulting_to_100(tmp_path):
    r, _ = _generate(tmp_path, _cfg(yield_substrate="Solid-T-weighed"))
    assert r.returncode != 0, "an unresolvable yield_substrate must not generate a workbook"
    msg = r.stdout + r.stderr
    assert "yield_basis_mM" in msg, msg
    assert "Solid-T-weighed" in msg, msg


def test_per_condition_yield_basis_overrides_the_global(tmp_path):
    """One arm is charged a weighed solid at 50 mM, another at 80 mM. One global basis would
    print the second arm 1.6x high."""
    cfg = _cfg(yield_basis_mM=50)
    cfg["conditions"][-1]["yield_basis_mM"] = 80
    r, out = _generate(tmp_path, cfg)
    assert r.returncode == 0, r.stdout + r.stderr
    assert _denominators(out) == {50.0, 80.0}


def test_per_condition_yield_substrate_overrides_the_global(tmp_path):
    cfg = _cfg(yield_substrate="Substrate-S")
    name, conc = "AnchorProbe", 40.0
    cfg["stocks"][name] = {"conc_mM": 1000, "type": "buffer", "final_mM": conc}
    cfg["conditions"][-1]["yield_substrate"] = name
    r, out = _generate(tmp_path, cfg)
    assert r.returncode == 0, r.stdout + r.stderr
    assert conc in _denominators(out)
