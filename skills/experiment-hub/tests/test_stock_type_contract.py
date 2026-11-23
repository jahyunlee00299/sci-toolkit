"""The stock `type` contract: 'buffer' = common to every tube, 'substrate' = per condition.

Moving a cofactor off the MM-A premix so it could differ between two arms means dropping its
`final_mM`; doing that to make a buffer vary crashed `validate_config` with a bare `KeyError: 'final_mM'` at the volume
closure check -- no FAIL line, no indication of which stock or what the fix was.

The two types are a convention rather than a label, and the error has to say so: a component
whose level varies belongs in each condition's `substrates` with `type: 'substrate'`.
"""
import json
import subprocess
import sys
from pathlib import Path

SK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SK))

CFG = SK / "tests" / "fixtures" / "pipette_rules" / "synthetic_serial_x8.json"


def _run(tmp_path, cfg):
    p, out = tmp_path / "c.json", tmp_path / "w.xlsx"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    return subprocess.run([sys.executable, str(SK / "reaction_matrix.py"), str(p), str(out),
                           "--no-publish"],
                          capture_output=True, text=True, encoding="utf-8", errors="replace"), out


def _buffer_name(cfg):
    return next(k for k, v in cfg["stocks"].items() if v["type"] == "buffer")


def test_buffer_stock_without_final_mM_fails_with_an_explanation(tmp_path):
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    name = _buffer_name(cfg)
    cfg["stocks"][name].pop("final_mM")
    r, out = _run(tmp_path, cfg)
    msg = r.stdout + r.stderr
    assert r.returncode != 0, msg
    assert "KeyError" not in msg, "a config error must not surface as a traceback: " + msg
    assert name in msg and "final_mM" in msg, msg
    assert "substrate" in msg, "the message must name the type that DOES vary per condition: " + msg
    assert not out.exists(), "no workbook may be written when a hard check fails"


def test_buffer_stock_with_final_mM_none_is_also_caught(tmp_path):
    """An explicit null is the same defect as a missing key, not a value of 'no concentration'."""
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    name = _buffer_name(cfg)
    cfg["stocks"][name]["final_mM"] = None
    r, _ = _run(tmp_path, cfg)
    assert r.returncode != 0, r.stdout + r.stderr
    assert name in r.stdout + r.stderr
