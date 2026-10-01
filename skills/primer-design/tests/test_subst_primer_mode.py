"""Tests for iPCRSubstDesigner (converted from subst_primer_mode._run_tests).

The inline version could load a private SnapGene template from a hard-coded
home-directory path when present; that environment-dependent branch is dropped
and the fixed built-in template is always used.
"""
import pytest
from Bio.Seq import Seq

from primer_design.subst_primer_mode import iPCRSubstDesigner

TEMPLATE = (
    "ATGCGTAACCTGGCGATCAAGCTGTTCGACGGTACC"
    "GATATCCTGCAGAAATTTGCGCCGGATCTGAACGAA"
    "TGGCTGCACATCGGTCCTGCGATTGGCACCGATTTC"
    "AATCGCCTGATGCAG"
)


@pytest.fixture(scope="module")
def designer():
    return iPCRSubstDesigner()


def test_1bp_substitution(designer):
    pos = 100
    old_base = TEMPLATE[pos]
    new_base = {"A": "C", "T": "G", "G": "T", "C": "A"}[old_base.upper()]
    r = designer.design(seq=TEMPLATE, subst_pos=pos, old_seq=old_base, new_seq=new_base)
    assert r["overlap_verified"]


def test_3bp_substitution(designer):
    old_3 = TEMPLATE[50:53]
    new_3 = str(Seq(old_3).complement())
    r = designer.design(seq=TEMPLATE, subst_pos=50, old_seq=old_3, new_seq=new_3,
                        overlap_len=20)
    assert r["overlap_verified"]


def test_old_seq_mismatch_raises(designer):
    with pytest.raises(ValueError):
        designer.design(seq=TEMPLATE, subst_pos=100, old_seq="X", new_seq="A")
