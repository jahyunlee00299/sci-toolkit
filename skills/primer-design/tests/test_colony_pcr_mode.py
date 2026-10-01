"""Tests for ColonyPCRDesigner (converted from colony_pcr_mode._run_tests)."""
import pytest

from primer_design.colony_pcr_mode import ColonyPCRDesigner, VECTOR_PRIMER_MAP


@pytest.fixture
def designer():
    return ColonyPCRDesigner()


@pytest.fixture
def restore_primer_map():
    """register_primer_pair mutates module state; put it back whatever happens."""
    snapshot = dict(VECTOR_PRIMER_MAP)
    yield
    VECTOR_PRIMER_MAP.clear()
    VECTOR_PRIMER_MAP.update(snapshot)


def test_pet28a_primer_mapping(designer):
    r1 = designer.suggest("pET-28a(+)", insert_length_bp=900)
    assert r1["f_name"] == "T7promoter"
    assert r1["r_name"] == "T7terminator"
    assert r1["expected_band_with_insert"] == 1250, "band with insert = 200+900+150"


def test_petduet_mcs1_primer_mapping(designer):
    r2 = designer.suggest("pETDuet-1:MCS1", insert_length_bp=1200)
    assert r2["f_name"] == "pET-upstream"
    assert r2["r_name"] == "T7terminator"


def test_band_size_with_known_flanking(designer):
    r3 = designer.suggest("pET-21a(+)", insert_length_bp=750,
                          vector_flanking_bp=(180, 120))
    assert r3["expected_band_with_insert"] == 180 + 750 + 120
    assert r3["flanking_upstream"] == 180
    assert r3["flanking_downstream"] == 120


def test_fuzzy_vector_name(designer):
    r4 = designer.suggest("pET28a", insert_length_bp=600)
    assert r4["vector_name"] == "pET-28a(+)"
    assert r4["f_name"] == "T7promoter"


# An 800 bp-class mock insert sequence (ORF ending in a stop codon).
INSERT_SEQ = (
    "ATGCGTAACCTGGCGATCAAGCTGTTCGACGGTACCGATATCCTGCAGAAATTTGCGCCG"
    "GATCTGAACGAATGGCTGCACATCGGTCCTGCGATTGGCACCGATTTCAATCGCCTGATG"
    "CAGTTCGATGCATCGACCGGCTATCTGAACTCCGTCAAGGCGATGGACAAACTGCGCGGC"
    "GATACCGTGGAAATCGCGCAGCAGCTGGGCGATGAAGTGATCATCGATGCGTCCGGCAAA"
    "ATCGCGTTCAAAGGCACCGATACCGTGATGCTGAGCTATCCGGGCACGCCGGTCGATCCG"
    "GCGCTGACCGGCTGGCGCCTGTTTGAAACCGACAATGTCGATCTGGCAGTCAAAGCGCTG"
    "GGCCTGGATCACATCACCGGCGACTTTGCGGACTACCGCGATCTGACCAAACTGGATCTG"
    "GCGTCGATCTTCAACATCGCGAAAGAAGCGGGCATCCACGACGATACGCTGAGCGCAGTG"
    "ACCGATTTCTCCGGTCTGAACGATGCGACCAACGGCAACATCGCGCTGGCCCAGTTCATC"
    "GACACCAAAGACGGCACCGCGATCCTGACCAACGGCTCGCAGGGCAACAAGCTGACCGAT"
    "GCGATCATCAACGGCAAGACCATTCCGCTGAACGATCTGAACCTGACCGAAGCGGCGCAG"
    "GCGTTTGCGGAAGTGCTGAAAGGCGTCGATCCGGAAACCATCACCCTGGAAGCGATCCGC"
    "GACGGCAAGATCAACCTGCAGGATCGCGTGATCGCGATGGGCGATACCCTGCAGGGCAAC"
    "GCGTCGATCACCGCGTAA"
)


def test_suggest_with_internal(designer):
    r5 = designer.suggest_with_internal("pET-28a(+)", INSERT_SEQ)
    assert r5["internal_f_seq"] is not None
    assert r5["internal_r_seq"] is not None
    assert r5["internal_product_size"] is not None and r5["internal_product_size"] > 0


def test_register_primer_pair_updates_and_restores(designer, restore_primer_map):
    orig_f, _orig_r = VECTOR_PRIMER_MAP["pET-21a(+)"]
    assert orig_f == "T7promoter", "original forward"

    ColonyPCRDesigner.register_primer_pair("pET-21a(+)", "pET_upstream", "pET_RP")
    new_f, new_r = VECTOR_PRIMER_MAP["pET-21a(+)"]
    assert new_f == "pET_upstream", "updated forward"
    assert new_r == "pET_RP", "updated reverse"

    r6 = designer.suggest("pET-21a(+)", insert_length_bp=500)
    assert r6["f_name"] == "pET-upstream", "suggest uses updated mapping"

    ColonyPCRDesigner.register_primer_pair("pET-21a(+)", "T7promoter", "T7terminator")
    restored_f, _ = VECTOR_PRIMER_MAP["pET-21a(+)"]
    assert restored_f == "T7promoter", "restored forward"


def test_register_primer_pair_rejects_invalid_key(restore_primer_map):
    with pytest.raises(ValueError):
        ColonyPCRDesigner.register_primer_pair("pET-21a(+)", "INVALID", "T7terminator")
