"""Tests for vector_registry (converted from vector_registry._run_tests).

The inline version printed `format_frame_report(result)` after every
`check_reading_frame` call. That exercise is kept: `_frame()` renders the report
for each case and requires a non-empty string (a small extra assertion over the
original, which only printed it).
"""
import pytest

from primer_design.vector_registry import (
    check_reading_frame, format_frame_report, get_vector,
)


def _frame(*args, **kwargs):
    result = check_reading_frame(*args, **kwargs)
    report = format_frame_report(result)
    assert isinstance(report, str) and report, "frame report must render"
    return result


def test_pet21a_ecori_noti_c_his6_fusion():
    # EcoRI at 42 (6bp) -> insert starts at 48 -> 48%3=0; NotI at 66, stop at 99 -> 33%3=0
    # 3' linker: GCG GCC GCA CTC GAG CAC x6 = AAALEHHHHHH
    r = _frame("pET-21a(+)", "EcoRI", "NotI", insert_has_atg=True, insert_has_stop=False)
    assert r["in_frame_5prime"] is True
    assert r["in_frame_3prime"] is True
    assert r["linker_3prime_aa"] == "AAALEHHHHHH"
    assert r["insert_start_pos"] == 48


def test_pet28a_bamhi_xhoi_dual_his6_in_frame():
    # BamHI at 96 (6bp) -> 102%3=0; XhoI at 135, stop at 159 -> 24%3=0
    r = _frame("pET-28a(+)", "BamHI", "XhoI", insert_has_atg=False, insert_has_stop=False)
    assert r["in_frame_5prime"] is True
    assert r["in_frame_3prime"] is True


def test_pet21a_insert_with_stop_loses_c_tag():
    r = _frame("pET-21a(+)", "EcoRI", "NotI", insert_has_atg=True, insert_has_stop=True)
    assert any("C-terminal tag will NOT" in w for w in r["warnings"])


def test_insert_length_not_multiple_of_three_warns():
    r = _frame("pET-21a(+)", "EcoRI", "NotI", insert_has_atg=True,
               insert_has_stop=False, insert_cds_bp=901)
    assert any("not a multiple of 3" in w for w in r["warnings"])


@pytest.mark.parametrize("name", [
    "pET21a", "pET-21a", "pet21a", "pET-28a", "pet28a",
    "pMALc6T", "pmal-c6t", "pETDuet1", "petduet-1",
    "pACYCDuet1", "pacycduet1", "pACYCDuet1:MCS2",
])
def test_fuzzy_vector_name_resolves(name):
    v = get_vector(name)  # raises ValueError when the name does not resolve
    assert len(v["mcs_seq"]) > 0


def test_pet28a_ndei_xhoi_n_his6_thrombin():
    # NdeI at 57 (6bp) -> 63%3=0; XhoI at 135, stop at 159 -> 24%3=0
    r = _frame("pET-28a(+)", "NdeI", "XhoI", insert_has_atg=True, insert_has_stop=False)
    assert r["in_frame_5prime"] is True, "5' in-frame (NdeI)"
    assert r["in_frame_3prime"] is True, "3' in-frame (XhoI)"


def test_pmal_c6t_noti_bamhi_mbp_fusion():
    # NotI at 13 (8bp) -> 21%3=0; BamHI at 33, stop at 63 -> 30%3=0
    r = _frame("pMAL-c6T", "NotI", "BamHI", insert_has_atg=False, insert_has_stop=False)
    assert r["in_frame_5prime"] is True
    assert r["in_frame_3prime"] is True
    assert r["insert_start_pos"] == 21


def test_pmal_c6t_ecori_hindiii_compact_linker():
    # EcoRI at 39 (6bp) -> 45%3=0; HindIII at 57, stop at 63 -> 6%3=0
    r = _frame("pMAL-c6T", "EcoRI", "HindIII", insert_has_atg=False, insert_has_stop=False)
    assert r["in_frame_5prime"] is True
    assert r["in_frame_3prime"] is True
    assert r["linker_3prime_aa"] == "KL"


def test_petduet_mcs1_psti_noti_codon_aligned():
    # PstI at 60 (6bp) -> 66%3=0; NotI at 78, stop at 87 -> 9%3=0
    r = _frame("pETDuet-1:MCS1", "PstI", "NotI", insert_has_atg=False, insert_has_stop=False)
    assert r["in_frame_5prime"] is True
    assert r["in_frame_3prime"] is True
    assert r["linker_3prime_aa"] == "AAA"


def test_petduet_mcs1_bamhi_noti_five_prime_out_of_frame():
    # BamHI at 35 (cross-codon): 35+6=41 -> 41%3=2 -> out of frame; NotI in frame
    r = _frame("pETDuet-1:MCS1", "BamHI", "NotI", insert_has_atg=True, insert_has_stop=False)
    assert r["in_frame_5prime"] is False
    assert r["frame_at_insert_start"] == 2
    assert r["in_frame_3prime"] is True


def test_petduet_mcs2_kpni_xhoi_s_tag_fusion():
    # KpnI at 48 (6bp) -> 54%3=0; XhoI at 54, stop at 126 -> 72%3=0
    r = _frame("pETDuet-1:MCS2", "KpnI", "XhoI", insert_has_atg=False, insert_has_stop=False)
    assert r["in_frame_5prime"] is True
    assert r["in_frame_3prime"] is True
    assert "S-tag" in r["topology"]


def test_pacycduet_mcs2_bglii_xhoi_five_prime_out_of_frame():
    # BglII at 5 (cross-codon): 5+6=11 -> 11%3=2 -> out of frame; XhoI in frame
    r = _frame("pACYCDuet-1:MCS2", "BglII", "XhoI", insert_has_atg=True, insert_has_stop=False)
    assert r["in_frame_5prime"] is False
    assert r["frame_at_insert_start"] == 2
    assert r["in_frame_3prime"] is True
