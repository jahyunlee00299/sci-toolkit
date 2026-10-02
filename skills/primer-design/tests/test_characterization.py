"""Golden-snapshot tests that pin the three units split in refactor batch 2.

See tests/characterization.py for what is snapshotted and why. The golden files in
tests/golden/ come from the code before the split; a behaviour-preserving
refactor leaves them untouched.
"""
import json

import pytest

import characterization as ch


def _golden(name):
    return json.loads((ch.GOLDEN / name).read_text(encoding="utf-8"))


def _same(actual, expected, label):
    # Compare via JSON round-trip so tuples/lists and int/float spellings agree.
    actual = json.loads(json.dumps(actual, sort_keys=True, ensure_ascii=False, default=str))
    assert actual == expected, f"{label} drifted from the golden snapshot"


def test_order_sheet_outputs_match_golden(tmp_path):
    snap = ch.snapshot_order_sheet(tmp_path)
    expected = _golden("order_sheet.json")
    if snap["macrogen_oligo_xls"] is None or expected["macrogen_oligo_xls"] is None:
        snap.pop("macrogen_oligo_xls")
        expected.pop("macrogen_oligo_xls")
    _same(snap, expected, "order sheet")


def test_vector_construct_map_artists_match_golden(tmp_path):
    _same(ch.snapshot_construct_maps(tmp_path), _golden("construct_maps.json"), "construct map")


def test_restriction_design_results_match_golden():
    _same(ch.snapshot_designs(), _golden("restriction_design.json"), "restriction design")


def test_golden_scenarios_cover_every_design_branch():
    g = _golden("restriction_design.json")
    warnings = [w for r in g["results"].values() for w in r["warnings"]]
    for needle in ("may be cut", "RE site itself provides start codon", "compatible sticky ends",
                   "Same RE", "blunt ends", "Forward primer Tm", "Reverse primer Tm",
                   "F annealing adjusted", "R annealing adjusted", "F hairpin:", "R hairpin:",
                   "homopolymer", "no 3' G/C clamp", "Frame check failed"):
        assert any(needle in w for w in warnings), f"scenario for {needle!r} lost"
    assert g["errors"]["forward_annealing_fails"][0] == "RuntimeError"
    assert "Forward" in g["errors"]["forward_annealing_fails"][1]
    assert g["errors"]["reverse_annealing_fails"][0] == "RuntimeError"
    assert "Reverse" in g["errors"]["reverse_annealing_fails"][1]
    assert all(v is not None for v in g["errors"].values())
    # A primer over 60 nt never reaches the "> 60 nt" warning: primer3 rejects it first.
    assert g["errors"]["long_primer_overflows_primer3"][0] == "RuntimeError"


def test_snapshot_is_sensitive_to_a_cell_change(tmp_path):
    # Refutation of the harness itself: a one-cell change must make the comparison fail.
    s = ch.build_order_sheet()
    s.entries[0].name = s.entries[0].name + "_X"
    snap = ch.dump_xlsx(s.to_xlsx(tmp_path / "x.xlsx"))
    assert snap != _golden("order_sheet.json")["xlsx"]


def test_default_output_paths_use_cwd_and_increment(tmp_path, monkeypatch):
    import re
    monkeypatch.chdir(tmp_path)
    s = ch.build_order_sheet()
    a = s.to_xlsx()
    b = s.to_xlsx()
    assert re.fullmatch(r"char_order_\d{8}_001_order\.xlsx", a.name)
    assert re.fullmatch(r"char_order_\d{8}_002_order\.xlsx", b.name)
    assert s.to_csv().name.endswith("_001_order.csv")
    assert s.to_markdown().name.endswith("_001_order.md")
    assert s.to_macrogen_oligo(tmp_path / "x.xlsx").exists()
    assert s.to_macrogen_seq(ch.SEQ_PAIRS).name.endswith("_003_order.xlsx")
    from primer_design.cloning_report import generate_vector_construct_map
    png = generate_vector_construct_map("pET-28a(+)", gene_name="GeneQ", insert_len=500)
    assert png.name == "GeneQ_pET-28a_construct.png" and png.exists()
