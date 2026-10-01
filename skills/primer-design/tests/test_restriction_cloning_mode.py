"""Tests for RestrictionCloningDesigner (converted from restriction_cloning_mode._run_tests)."""
import pytest

from primer_design.restriction_cloning_mode import RestrictionCloningDesigner

# Insert CDS (no stop codon until the trailing TAA).
TEST_INSERT = (
    "ATGAAAGCTGCCATTGTTCTGAGCGAATCCGGTGTGCACGAATGTCCGAAAGAATCCAAACTG"
    "GTTCCGGCACTGAACGGTCTGGAAATCGAAGATGAAGGCGTTATCCCGGAATTCTTCAAGGGC"
    "AAACTGGATCGCGGCTTCAAAGCGATCCTGAACAATGCGAAAGATTGGAGCCGCGTGGAAAAC"
    "TACCAGCCGGATCTGATCAACGAACTGAAAGCGAAAGCGACCGATGTGGAATAA"
)

# Insert that already contains a BamHI site (GGATCC).
INSERT_WITH_BAMHI = (
    "ATGAAAGCTGCCATTGTTCTGAGCGAATCCGGATCCGCACGAATGTCCGAAAGAATCCAAAC"
    "TGGTTCCGGCACTGAACGGTCTGGAAATCGAAGATGAAGGCGTTATCCCGGAATTCTTCAAG"
)


@pytest.fixture(scope="module")
def designer():
    return RestrictionCloningDesigner()


@pytest.fixture(scope="module")
def bamhi_xhoi_pet28a(designer):
    return designer.design(
        insert_seq=TEST_INSERT, re_5prime="BamHI", re_3prime="XhoI",
        vector_name="pET-28a(+)", target_tm=62.0,
        include_start_codon=True, include_stop_codon=False,
    )


def test_bamhi_xhoi_pet28a_sites_and_primer_layout(bamhi_xhoi_pet28a):
    r1 = bamhi_xhoi_pet28a
    assert r1["re_5prime"] == "BamHI"
    assert r1["re_3prime"] == "XhoI"
    assert r1["re_5prime_site"] == "GGATCC"
    assert r1["re_3prime_site"] == "CTCGAG"
    assert r1["f_full"].startswith(r1["protection_5"] + "GGATCC"), \
        "F primer starts with protection + RE"
    assert r1["r_full"].startswith(r1["protection_3"] + "CTCGAG"), \
        "R primer starts with protection + RE"


def test_bamhi_xhoi_pet28a_frame_check_passes(bamhi_xhoi_pet28a):
    r1 = bamhi_xhoi_pet28a
    assert "frame_check" in r1
    assert r1["frame_check"]["in_frame_5prime"] is True
    assert r1["frame_check"]["in_frame_3prime"] is True


def test_nhei_noti_pet21a_with_stop_codon(designer):
    r2 = designer.design(
        insert_seq=TEST_INSERT, re_5prime="NheI", re_3prime="NotI",
        vector_name="pET-21a(+)", target_tm=62.0,
        include_start_codon=True, include_stop_codon=True, stop_codon="TAA",
    )
    assert r2["include_stop_codon"] is True
    assert "TTA" in r2["r_tail"], "R tail contains RC(stop)"
    assert "frame_check" in r2
    assert any("C-terminal tag will NOT" in w for w in r2["frame_check"]["warnings"]), \
        "stop warning present"


def test_internal_re_site_is_detected_and_warned(designer):
    r3 = designer.design(insert_seq=INSERT_WITH_BAMHI, re_5prime="BamHI",
                         re_3prime="XhoI", target_tm=62.0)
    assert len(r3["internal_re_sites_5"]) > 0
    assert any("may be cut" in w for w in r3["warnings"])


def test_custom_protection_bases_literal_and_length(designer):
    r4a = designer.design(
        insert_seq=TEST_INSERT, re_5prime="BamHI", re_3prime="XhoI",
        protection_bases_5="AATTCC", protection_bases_3=6,
    )
    assert r4a["protection_5"] == "AATTCC"
    assert len(r4a["protection_3"]) == 6
    assert r4a["f_tail"].startswith("AATTCC")


def test_auto_protection_length_depends_on_cutter_size(designer):
    r4b = designer.design(
        insert_seq=TEST_INSERT, re_5prime="NotI", re_3prime="XhoI",
        protection_bases_5=None,  # auto: 8-cutter -> 6 bp
        protection_bases_3=None,  # auto: 6-cutter -> 4 bp
    )
    assert len(r4b["protection_5"]) == 6, "NotI auto protection = 6 bp"
    assert len(r4b["protection_3"]) == 4, "XhoI auto protection = 4 bp"


def test_recommend_re_pair_is_non_empty_and_best_first(designer):
    recs = designer.recommend_re_pair(
        insert_seq=TEST_INSERT, vector_name="pET-28a(+)", prefer_hf=True)
    assert len(recs) > 0
    assert all(recs[0]["score"] >= r["score"] for r in recs), \
        "top recommendation has highest score"


def test_ndei_atg_warning(designer):
    r6 = designer.design(insert_seq=TEST_INSERT, re_5prime="NdeI", re_3prime="XhoI",
                         vector_name="pET-28a(+)", include_start_codon=True)
    assert any("contains ATG" in w for w in r6["warnings"])


def test_ecorv_blunt_end_warning(designer):
    r7 = designer.design(insert_seq=TEST_INSERT, re_5prime="EcoRV", re_3prime="XhoI")
    assert any("blunt end" in w.lower() for w in r7["warnings"])


def test_bamhi_bglii_compatible_overhang_warning(designer):
    r8 = designer.design(insert_seq=TEST_INSERT, re_5prime="BamHI", re_3prime="BglII")
    assert any("BOTH orientations" in w for w in r8["warnings"])
