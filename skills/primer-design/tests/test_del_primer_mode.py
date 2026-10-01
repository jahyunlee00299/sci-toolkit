"""Tests for iPCRDelDesigner (converted from del_primer_mode._run_tests)."""
import pytest

from primer_design.del_primer_mode import iPCRDelDesigner

TEST_SEQ = (
    "ATGAAAGCTGCCATTGTTCTGAGCGAATCCGGTGTGCACGAATGTCCGAAAGAATCCAAACTG"
    "GTTCCGGCACTGAACGGTCTGGAAATCGAAGATGAAGGCGTTATCCCGGAATTCTTCAAGGGC"
)


@pytest.fixture(scope="module")
def designer():
    return iPCRDelDesigner()


def test_1bp_deletion_is_frameshift(designer):
    r = designer.design(TEST_SEQ, del_start=30, del_end=31, cds_start=0)
    assert r["frameshift_warning"] and r["overlap_verified"]


def test_3bp_deletion_in_frame(designer):
    r = designer.design(TEST_SEQ, del_start=30, del_end=33, cds_start=0)
    assert not r["frameshift_warning"] and r["overlap_verified"]


def test_6bp_deletion_in_frame_two_codons(designer):
    r = designer.design(TEST_SEQ, del_start=30, del_end=36, cds_start=0)
    assert not r["frameshift_warning"] and r["overlap_verified"]


def test_4bp_deletion_is_frameshift(designer):
    r = designer.design(TEST_SEQ, del_start=30, del_end=34, cds_start=0)
    assert r["frameshift_warning"] and r["overlap_verified"]


def test_1bp_deletion_at_codon_third_position(designer):
    r = designer.design(TEST_SEQ, del_start=32, del_end=33, cds_start=0)
    assert r["frameshift_warning"]
    assert any("3rd position" in w for w in r["warnings"])
