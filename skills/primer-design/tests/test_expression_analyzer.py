"""Tests for ExpressionAnalyzer (converted from expression_analyzer._run_tests)."""
import math

import pytest

from primer_design.expression_analyzer import ExpressionAnalyzer

# E. coli-optimized GFP: CAI should be > 0.7 with few rare codons.
ECOLI_GFP = (
    "ATGAGTAAAGGCGAAGAACTGTTTACCGGCGTGGTGCCGATCCTGGTGGAACTGGATGGCGATGTGAAC"
    "GGCCACAAATTTAGCGTGCGCGGCGAAGGCGAAGGCGATGCGACCAACGGCAAACTGACCCTGAAATTTATC"
    "TGCACCACCGGCAAACTGCCGGTGCCGTGGCCGACCCTGGTGACCACCCTGACCTATGGCGTGCAGTGCTTC"
    "GCGCGCTATCCGGATCACATGAAACGCCACGATTTCTTTAAATCCGCGATGCCGGAAGGCTATGTGCAGGAA"
    "CGCACCATCTTTTTCAAAGACGATGGCACCTACAAAACCCGCGCGGAAGTGAAATTTGAAGGCGATACCCTGG"
    "TGAACCGCATCGAACTGAAAGGCATCGATTTTAAAGAAGATGGCAACATCCTGGGCCACAAACTGGAATACAA"
    "CTTTAACTCCCACAACGTGTACATCACCGCGGACAAACAAAAAAACGGCATCAAAGCGAACTTCAAAATCCGCC"
    "ACAACGTGGAAGATGGCAGCGTGCAGCTGGCGGATCATTATCAGCAGAACACCCCGATCGGCGATGGCCCGGTG"
    "CTGCTGCCGGATAACCACTACCTGTCGACCCAGAGCAAACTGTCGAAAGATCCGAACGAAAAACGCGATCAC"
    "ATGGTGCTGCTGGAATTTGTGACCGCGGCGGGCATCACCCTGGGCATGGATGAACTGTATAAATAA"
)

# Plant-origin CDS: should carry many rare codons for E. coli.
PLANT_CDS = (
    "ATGAGAAGATCTTCTTCAAGAAGAATCGCTTCTTCAAGATCCTCAGGATCCTCATCCTCAAGAGGATCTTCA"
    "TCGGATTCTCAAGAGGAAGAATCTCATCCTCAAGATCCGGACGATCTTCAAGATCCTCAGGATCCTCATCCTC"
    "AAGAGGATCTTCATCGGATTCTCAAGATAA"
)


@pytest.fixture(scope="module")
def analyzer():
    return ExpressionAnalyzer()


def _strain_input(rare_pct, clusters, cai):
    return {
        "rare_codon_pct": rare_pct,
        "rare_codon_clusters": clusters,
        "cai": cai,
        "signal_peptide": {"has_signal_peptide": False},
    }


def test_ecoli_optimized_gfp_high_cai_few_rare_codons(analyzer):
    result = analyzer.analyze(ECOLI_GFP, organism_source="synthetic (E. coli optimized)")
    assert result["cai"] > 0.7, "CAI > 0.7"
    assert result["rare_codons"]["rare_codon_pct"] < 5.0, "rare codon pct < 5%"
    assert result["basic_info"]["has_start_codon"] is True, "has start codon"


def test_plant_cds_has_rare_codons(analyzer):
    result = analyzer.analyze(PLANT_CDS, organism_source="Arabidopsis thaliana")
    assert result["rare_codons"]["total_rare"] > 0


def test_strain_low_rare_codons_selects_bl21(analyzer):
    rec = analyzer.recommend_strain(_strain_input(1.5, [], 0.75))
    assert rec["primary_strain"] == "BL21(DE3)"
    assert rec["codon_optimization_needed"] is False


def test_strain_mid_rare_codons_selects_rosetta(analyzer):
    rec = analyzer.recommend_strain(_strain_input(5.0, [], 0.55))
    assert rec["primary_strain"] == "Rosetta(DE3)"


def test_strain_high_rare_codons_selects_rosetta2_with_high_priority(analyzer):
    rec = analyzer.recommend_strain(_strain_input(12.0, [], 0.30))
    assert rec["primary_strain"] == "Rosetta 2(DE3)"
    assert rec["codon_optimization_needed"] is True
    assert rec["optimization_priority"] == "high"


def test_strain_rare_codon_cluster_forces_rosetta(analyzer):
    rec = analyzer.recommend_strain(
        _strain_input(2.0, [{"start": 10, "end": 14, "rare_codons": []}], 0.65))
    assert rec["primary_strain"] == "Rosetta(DE3)"
    assert rec["codon_optimization_needed"] is True


def test_cai_matches_geometric_mean_of_codon_weights(analyzer):
    # M K A F L * -> ATG(1.0) AAA(0.77) GCG(0.50) TTT(0.58) CTG(1.0); stop excluded.
    expected = math.exp(
        (math.log(1.0) + math.log(0.77) + math.log(0.50) + math.log(0.58) + math.log(1.0)) / 5
    )
    assert analyzer.compute_cai("ATGAAAGCGTTTCTGTAA") == pytest.approx(expected, abs=0.001)


def test_cai_worst_codons_is_low(analyzer):
    # AGG(0.02) CTA(0.04) ATA(0.07) CCC(0.12) GGA(0.11)
    assert analyzer.compute_cai("ATGAGGCTAATACCCGGATAA") < 0.15


def test_cai_of_ecoli_gfp_is_high(analyzer):
    assert analyzer.compute_cai(ECOLI_GFP) > 0.7


def test_signal_peptide_detected_for_male_like_sequence(analyzer):
    protein = "MKYLLPTAAAGLLLLAAQPAMA" + "DIVLTQSPASLAVSLGQRATIS"
    sp = analyzer.check_signal_peptide(protein)
    assert sp["has_signal_peptide"] is True
    assert sp["confidence"] in ("high", "medium")


def test_no_strong_signal_peptide_for_cytoplasmic_protein(analyzer):
    sp = analyzer.check_signal_peptide("MSKGEELFTGVVPILVELDGDVNGHKFSVR")
    assert sp["confidence"] in ("none", "low")


def test_rare_codon_cluster_detected_with_expected_codons(analyzer):
    # 3 rare codons in a 5-codon window: AGG, AGA (Arg), ATG (Met, ok), CCC (Pro), GCT (Ala, ok)
    cluster_cds = "ATG" + "AGG" "AGA" "ATG" "CCC" "GCT" + "AAA" * 10 + "TAA"
    result = analyzer.analyze(cluster_cds)
    clusters = result["rare_codon_clusters"]
    assert len(clusters) >= 1, "cluster detected"
    codons = {rc["codon"] for rc in clusters[0]["rare_codons"]}
    assert "AGG" in codons
    assert "AGA" in codons
    assert "CCC" in codons


def test_map_removes_met_when_second_residue_is_small(analyzer):
    result = analyzer.analyze("ATGGCGAAATAA")  # M A K *
    assert result["map_removal"]["will_be_removed"] is True


def test_map_retains_met_when_second_residue_is_not_small(analyzer):
    result = analyzer.analyze("ATGGATAAATAA")  # M D K *
    assert result["map_removal"]["will_be_removed"] is False
