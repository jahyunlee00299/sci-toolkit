#!/usr/bin/env python3
"""
Expression Analyzer
====================
Analyzes a CDS sequence for E. coli expression optimization.

Analysis items:
  - GC content, molecular weight, CAI (Codon Adaptation Index)
  - E. coli K12 rare codon frequency and cluster detection
  - Signal peptide prediction (rule-based)
  - N-terminal MAP (Methionine Aminopeptidase) removal prediction
  - Expression host strain recommendation (BL21 / Rosetta / Rosetta 2)
"""

from __future__ import annotations

import math
import re

# ── Genetic code (standard) ─────────────────────────────────────────────────

_CODON_TABLE = {
    "TTT": "F", "TTC": "F", "TTA": "L", "TTG": "L",
    "CTT": "L", "CTC": "L", "CTA": "L", "CTG": "L",
    "ATT": "I", "ATC": "I", "ATA": "I", "ATG": "M",
    "GTT": "V", "GTC": "V", "GTA": "V", "GTG": "V",
    "TCT": "S", "TCC": "S", "TCA": "S", "TCG": "S",
    "CCT": "P", "CCC": "P", "CCA": "P", "CCG": "P",
    "ACT": "T", "ACC": "T", "ACA": "T", "ACG": "T",
    "GCT": "A", "GCC": "A", "GCA": "A", "GCG": "A",
    "TAT": "Y", "TAC": "Y", "TAA": "*", "TAG": "*",
    "CAT": "H", "CAC": "H", "CAA": "Q", "CAG": "Q",
    "AAT": "N", "AAC": "N", "AAA": "K", "AAG": "K",
    "GAT": "D", "GAC": "D", "GAA": "E", "GAG": "E",
    "TGT": "C", "TGC": "C", "TGA": "*", "TGG": "W",
    "CGT": "R", "CGC": "R", "CGA": "R", "CGG": "R",
    "AGT": "S", "AGC": "S", "AGA": "R", "AGG": "R",
    "GGT": "G", "GGC": "G", "GGA": "G", "GGG": "G",
}


def _translate(dna: str) -> str:
    """DNA -> amino acid string (standard code). Stop = '*'."""
    aa = []
    for i in range(0, len(dna) - 2, 3):
        codon = dna[i:i + 3].upper()
        aa.append(_CODON_TABLE.get(codon, "?"))
    return "".join(aa)


# ── E. coli K12 Rare Codons ─────────────────────────────────────────────────

ECOLI_RARE_CODONS = {
    "AGG": {"aa": "Arg", "freq_per_1000": 1.2,  "prare": True,  "prare2": True},
    "AGA": {"aa": "Arg", "freq_per_1000": 2.1,  "prare": True,  "prare2": True},
    "CGA": {"aa": "Arg", "freq_per_1000": 3.1,  "prare": False, "prare2": True},
    "CUA": {"aa": "Leu", "freq_per_1000": 3.9,  "prare": True,  "prare2": True},
    "AUA": {"aa": "Ile", "freq_per_1000": 4.1,  "prare": True,  "prare2": True},
    "CCC": {"aa": "Pro", "freq_per_1000": 4.3,  "prare": True,  "prare2": True},
    "GGA": {"aa": "Gly", "freq_per_1000": 8.0,  "prare": True,  "prare2": True},
    "CGG": {"aa": "Arg", "freq_per_1000": 5.4,  "prare": False, "prare2": True},
}

# ── E. coli K12 Codon Usage (relative adaptiveness w_i for CAI) ─────────────
# Source: Kazusa codon usage database — E. coli K12
# w_i = freq / max_freq for that amino acid (pre-computed)

ECOLI_CODON_W = {
    # Phe
    "TTT": 0.58, "TTC": 1.00,
    # Leu
    "TTA": 0.13, "TTG": 0.13, "CTT": 0.10, "CTC": 0.10, "CTA": 0.04, "CTG": 1.00,
    # Ile
    "ATT": 0.49, "ATC": 1.00, "ATA": 0.07,
    # Met
    "ATG": 1.00,
    # Val
    "GTT": 1.00, "GTC": 0.42, "GTA": 0.50, "GTG": 0.37,
    # Ser
    "TCT": 1.00, "TCC": 0.74, "TCA": 0.12, "TCG": 0.15, "AGT": 0.16, "AGC": 0.76,
    # Pro
    "CCT": 0.16, "CCC": 0.12, "CCA": 0.19, "CCG": 1.00,
    # Thr
    "ACT": 0.50, "ACC": 1.00, "ACA": 0.14, "ACG": 0.36,
    # Ala
    "GCT": 1.00, "GCC": 0.63, "GCA": 0.59, "GCG": 0.50,
    # Tyr
    "TAT": 0.59, "TAC": 1.00,
    # Stop
    "TAA": 1.00, "TAG": 0.08, "TGA": 0.30,
    # His
    "CAT": 0.57, "CAC": 1.00,
    # Gln
    "CAA": 0.34, "CAG": 1.00,
    # Asn
    "AAT": 0.49, "AAC": 1.00,
    # Lys
    "AAA": 0.77, "AAG": 1.00,
    # Asp
    "GAT": 0.63, "GAC": 1.00,
    # Glu
    "GAA": 1.00, "GAG": 0.29,
    # Cys
    "TGT": 0.46, "TGC": 1.00,
    # Trp
    "TGG": 1.00,
    # Arg
    "CGT": 1.00, "CGC": 0.60, "CGA": 0.07, "CGG": 0.10, "AGA": 0.04, "AGG": 0.02,
    # Gly
    "GGT": 1.00, "GGC": 0.77, "GGA": 0.11, "GGG": 0.15,
}

# ── Amino acid molecular weights (average) ──────────────────────────────────

_AA_MW = {
    "A": 89.1, "R": 174.2, "N": 132.1, "D": 133.1, "C": 121.2,
    "E": 147.1, "Q": 146.2, "G": 75.0, "H": 155.2, "I": 131.2,
    "L": 131.2, "K": 146.2, "M": 149.2, "F": 165.2, "P": 115.1,
    "S": 105.1, "T": 119.1, "W": 204.2, "Y": 181.2, "V": 117.1,
}
_WATER_MW = 18.02

# ── MAP (Methionine Aminopeptidase) removal rules ───────────────────────────
# E. coli MAP removes N-terminal Met when the second amino acid is small
# (radius of gyration <= 1.29 A)

MAP_REMOVABLE_AA = {"A", "C", "G", "P", "S", "T", "V"}


# ── ExpressionAnalyzer ──────────────────────────────────────────────────────

class ExpressionAnalyzer:
    """Analyzer for a CDS sequence's E. coli expression optimization."""

    def analyze(
        self,
        cds_seq: str,
        organism_source: str = "",
    ) -> dict:
        """Comprehensive analysis of a CDS sequence.

        Parameters
        ----------
        cds_seq : str
            CDS DNA sequence (ATG through the stop codon, inclusive)
        organism_source : str
            source organism (e.g. "Agrobacterium tumefaciens"). Informational note only.

        Returns
        -------
        dict
            analysis results (basic_info, rare_codons, clusters, cai, signal_peptide, etc.)
        """
        warnings: list[str] = []
        recommendations: list[str] = []

        # 1. Clean input
        seq = cds_seq.upper().replace(" ", "").replace("\n", "").replace("\r", "")
        invalid = set(seq) - {"A", "T", "G", "C"}
        if invalid:
            warnings.append(
                f"Non-standard characters in CDS: {', '.join(sorted(invalid))}"
            )
            seq = re.sub(r"[^ATGC]", "", seq)

        # 2. Start codon check
        has_start = seq[:3] == "ATG"
        if not has_start:
            warnings.append(
                f"CDS does not start with ATG (found: {seq[:3]})"
            )

        # 3. Translate to protein
        protein = _translate(seq)
        # Strip terminal stop
        if protein.endswith("*"):
            protein_no_stop = protein[:-1]
        else:
            protein_no_stop = protein
            warnings.append("CDS does not end with a stop codon")

        # 4. Basic info
        cds_length_bp = len(seq)
        protein_length_aa = len(protein_no_stop)
        gc_count = seq.count("G") + seq.count("C")
        gc_content = gc_count / cds_length_bp if cds_length_bp > 0 else 0.0

        # Molecular weight (sum of aa MW - (n-1)*water)
        mw_sum = sum(_AA_MW.get(aa, 0.0) for aa in protein_no_stop)
        if protein_length_aa > 1:
            mw_sum -= (protein_length_aa - 1) * _WATER_MW
        molecular_weight_kda = mw_sum / 1000.0

        # 5. Rare codon analysis
        codons = [seq[i:i + 3] for i in range(0, len(seq) - 2, 3)]
        total_codons = len(codons)

        rare_codon_counts: dict[str, int] = {}
        rare_codon_positions: dict[str, list[int]] = {}
        total_rare = 0
        prare_count = 0
        prare2_count = 0

        for idx, codon in enumerate(codons):
            if codon in ECOLI_RARE_CODONS:
                info = ECOLI_RARE_CODONS[codon]
                total_rare += 1
                rare_codon_counts[codon] = rare_codon_counts.get(codon, 0) + 1
                if codon not in rare_codon_positions:
                    rare_codon_positions[codon] = []
                rare_codon_positions[codon].append(idx + 1)  # 1-indexed
                if info["prare"]:
                    prare_count += 1
                if info["prare2"]:
                    prare2_count += 1

        rare_codon_pct = (total_rare / total_codons * 100) if total_codons > 0 else 0.0

        rare_codon_detail = []
        for codon in sorted(rare_codon_counts.keys()):
            info = ECOLI_RARE_CODONS[codon]
            rare_codon_detail.append({
                "codon": codon,
                "amino_acid": info["aa"],
                "count": rare_codon_counts[codon],
                "freq_per_1000": info["freq_per_1000"],
                "positions": rare_codon_positions[codon],
                "prare": info["prare"],
                "prare2": info["prare2"],
            })

        # 6. Rare codon cluster detection (sliding window of 5 codons)
        cluster_windows: list[tuple[int, int]] = []
        for i in range(len(codons) - 4):
            window = codons[i:i + 5]
            rare_in_window = sum(1 for c in window if c in ECOLI_RARE_CODONS)
            if rare_in_window >= 2:
                cluster_windows.append((i + 1, i + 5))  # 1-indexed

        # Merge overlapping clusters
        merged_clusters: list[dict] = []
        if cluster_windows:
            current_start, current_end = cluster_windows[0]
            for start, end in cluster_windows[1:]:
                if start <= current_end:
                    current_end = max(current_end, end)
                else:
                    # Collect rare codons in this merged cluster
                    cluster_rare = []
                    for pos_idx in range(current_start - 1, current_end):
                        if pos_idx < len(codons) and codons[pos_idx] in ECOLI_RARE_CODONS:
                            cluster_rare.append({
                                "codon": codons[pos_idx],
                                "position": pos_idx + 1,
                            })
                    merged_clusters.append({
                        "start": current_start,
                        "end": current_end,
                        "rare_codons": cluster_rare,
                    })
                    current_start, current_end = start, end
            # Final cluster
            cluster_rare = []
            for pos_idx in range(current_start - 1, current_end):
                if pos_idx < len(codons) and codons[pos_idx] in ECOLI_RARE_CODONS:
                    cluster_rare.append({
                        "codon": codons[pos_idx],
                        "position": pos_idx + 1,
                    })
            merged_clusters.append({
                "start": current_start,
                "end": current_end,
                "rare_codons": cluster_rare,
            })

        # 7. CAI calculation
        cai = self.compute_cai(seq)

        # 8. Signal peptide check
        signal_peptide = self.check_signal_peptide(protein_no_stop)

        # 9. MAP removal prediction
        map_removal = False
        map_note = ""
        if protein_length_aa >= 2:
            second_aa = protein_no_stop[1]
            if second_aa in MAP_REMOVABLE_AA:
                map_removal = True
                map_note = (
                    f"N-terminal Met likely removed by MAP "
                    f"(second residue: {second_aa}). "
                    f"Mature protein starts at {second_aa} (position 2)."
                )
            else:
                map_note = (
                    f"N-terminal Met likely retained "
                    f"(second residue: {second_aa}, not small enough for MAP)."
                )

        # Adjusted MW for MAP removal
        mature_mw_kda = molecular_weight_kda
        if map_removal:
            mature_mw_kda = (mw_sum - _AA_MW.get("M", 0.0) + _WATER_MW) / 1000.0

        # 10. Recommendations and warnings
        if rare_codon_pct > 8:
            recommendations.append(
                "High rare codon content (>8%): strongly recommend codon optimization "
                "or use Rosetta 2(DE3)"
            )
        elif rare_codon_pct > 3:
            recommendations.append(
                "Moderate rare codon content (3-8%): Rosetta(DE3) recommended"
            )

        if merged_clusters:
            recommendations.append(
                f"{len(merged_clusters)} rare codon cluster(s) detected: "
                f"may cause ribosomal stalling. Consider codon optimization "
                f"in clustered regions."
            )

        if cai < 0.2:
            recommendations.append(
                "Very low CAI (<0.2): expression likely very poor. "
                "Codon optimization strongly recommended."
            )
        elif cai < 0.4:
            recommendations.append(
                "Low CAI (<0.4): expression may be poor. "
                "Consider codon optimization."
            )

        if signal_peptide["has_signal_peptide"]:
            recommendations.append(
                "Potential signal peptide detected: may cause secretion or "
                "membrane targeting. Consider removing for cytoplasmic expression."
            )

        if gc_content > 0.65:
            warnings.append(
                f"High GC content ({gc_content:.1%}): may form secondary structures "
                f"affecting translation"
            )
        elif gc_content < 0.35:
            warnings.append(
                f"Low GC content ({gc_content:.1%}): mRNA may be unstable in E. coli"
            )

        # Strain recommendation
        strain_rec = self.recommend_strain({
            "rare_codon_pct": rare_codon_pct,
            "rare_codon_clusters": merged_clusters,
            "cai": cai,
            "signal_peptide": signal_peptide,
        })

        return {
            "organism_source": organism_source,
            "basic_info": {
                "cds_length_bp": cds_length_bp,
                "protein_length_aa": protein_length_aa,
                "gc_content": round(gc_content, 4),
                "molecular_weight_kda": round(molecular_weight_kda, 2),
                "mature_mw_kda": round(mature_mw_kda, 2),
                "has_start_codon": has_start,
                "protein_sequence": protein_no_stop,
            },
            "rare_codons": {
                "total_rare": total_rare,
                "total_codons": total_codons,
                "rare_codon_pct": round(rare_codon_pct, 2),
                "prare_count": prare_count,
                "prare2_count": prare2_count,
                "detail": rare_codon_detail,
            },
            "rare_codon_clusters": merged_clusters,
            "cai": round(cai, 4),
            "signal_peptide": signal_peptide,
            "map_removal": {
                "will_be_removed": map_removal,
                "note": map_note,
            },
            "strain_recommendation": strain_rec,
            "recommendations": recommendations,
            "warnings": warnings,
        }

    def recommend_strain(self, analysis: dict) -> dict:
        """Recommend an expression host strain.

        Parameters
        ----------
        analysis : dict
            an analyze() result, or a dict containing the rare_codon_pct, cai,
            rare_codon_clusters, and signal_peptide keys.

        Returns
        -------
        dict
            primary_strain, alternative_strain, codon_optimization_needed,
            optimization_priority, rationale
        """
        rare_pct = analysis.get("rare_codon_pct", 0.0)
        clusters = analysis.get("rare_codon_clusters", [])
        cai = analysis.get("cai", 1.0)
        signal = analysis.get("signal_peptide", {})

        rationale: list[str] = []
        primary = "BL21(DE3)"
        alternative: str | None = None
        codon_opt = False
        priority = "low"

        # Rare codon percentage thresholds
        if rare_pct > 8:
            primary = "Rosetta 2(DE3)"
            alternative = "Rosetta(DE3)"
            codon_opt = True
            priority = "high"
            rationale.append(
                f"Rare codon content ({rare_pct:.1f}%) exceeds 8%: "
                f"Rosetta 2(DE3) supplies all rare tRNAs"
            )
        elif rare_pct > 3:
            primary = "Rosetta(DE3)"
            alternative = "BL21(DE3)"
            priority = "medium"
            rationale.append(
                f"Moderate rare codon content ({rare_pct:.1f}%): "
                f"Rosetta(DE3) recommended for supplemental rare tRNAs"
            )
        else:
            rationale.append(
                f"Low rare codon content ({rare_pct:.1f}%): "
                f"BL21(DE3) sufficient"
            )

        # Rare codon clusters override
        if clusters:
            if primary == "BL21(DE3)":
                primary = "Rosetta(DE3)"
                alternative = "BL21(DE3)"
            if priority == "low":
                priority = "medium"
            codon_opt = True
            rationale.append(
                f"{len(clusters)} rare codon cluster(s) detected: "
                f"Rosetta strain mandatory or codon optimization required"
            )

        # CAI threshold
        if cai < 0.4:
            codon_opt = True
            if priority != "high":
                priority = "high"
            rationale.append(
                f"Low CAI ({cai:.3f}): codon optimization strongly recommended"
            )
        elif cai < 0.6:
            if not codon_opt:
                codon_opt = False
            rationale.append(
                f"Moderate CAI ({cai:.3f}): acceptable but optimization may improve yield"
            )

        # Signal peptide
        if signal.get("has_signal_peptide", False):
            rationale.append(
                "Signal peptide detected: consider removal for cytoplasmic expression"
            )

        return {
            "primary_strain": primary,
            "alternative_strain": alternative,
            "codon_optimization_needed": codon_opt,
            "optimization_priority": priority,
            "rationale": rationale,
        }

    def check_signal_peptide(self, protein_seq: str) -> dict:
        """Rule-based signal peptide detection.

        Parameters
        ----------
        protein_seq : str
            Amino acid sequence (single-letter, no stop)

        Returns
        -------
        dict
            has_signal_peptide, confidence, hydrophobic_pct,
            n_region_positive, cleavage_site_estimate, notes
        """
        notes: list[str] = []
        hydrophobic_aa = {"L", "I", "V", "F", "A", "W", "M"}
        positive_aa = {"K", "R"}
        small_aa = {"A", "G", "S", "T"}

        if len(protein_seq) < 15:
            return {
                "has_signal_peptide": False,
                "confidence": "none",
                "hydrophobic_pct": 0.0,
                "n_region_positive": 0,
                "cleavage_site_estimate": None,
                "notes": ["Protein too short for signal peptide analysis"],
            }

        # 1. Overall hydrophobic content in first 25 aa
        n_check = min(25, len(protein_seq))
        first_25 = protein_seq[:n_check]
        hydrophobic_count = sum(1 for aa in first_25 if aa in hydrophobic_aa)
        hydrophobic_pct = hydrophobic_count / n_check

        # 2. N-region: positively charged residues (K, R) in first 5 aa
        n_region = protein_seq[:min(5, len(protein_seq))]
        n_region_positive = sum(1 for aa in n_region if aa in positive_aa)

        # 3. H-region: hydrophobic core (positions 5-15)
        h_region_start = 5
        h_region_end = min(15, len(protein_seq))
        h_region = protein_seq[h_region_start:h_region_end]
        h_hydrophobic = sum(1 for aa in h_region if aa in hydrophobic_aa) if h_region else 0
        h_hydrophobic_pct = h_hydrophobic / len(h_region) if h_region else 0.0

        # 4. C-region: small amino acids near cleavage site (positions 15-25)
        cleavage_site: int | None = None
        c_region_start = min(15, len(protein_seq))
        c_region_end = min(25, len(protein_seq))
        c_region = protein_seq[c_region_start:c_region_end]

        # Look for small amino acids (A, G, S, T) that could be cleavage site
        for i in range(len(c_region) - 1, -1, -1):
            if c_region[i] in small_aa:
                cleavage_site = c_region_start + i + 1  # 1-indexed, after the small aa
                break

        # Scoring
        score = 0

        if hydrophobic_pct > 0.40:
            score += 2
            notes.append(
                f"High hydrophobic content in first {n_check} aa: "
                f"{hydrophobic_pct:.0%}"
            )
        elif hydrophobic_pct > 0.30:
            score += 1
            notes.append(
                f"Moderate hydrophobic content in first {n_check} aa: "
                f"{hydrophobic_pct:.0%}"
            )

        if n_region_positive >= 2:
            score += 2
            notes.append(
                f"Positively charged N-region: {n_region_positive} K/R in first 5 aa"
            )
        elif n_region_positive >= 1:
            score += 1
            notes.append(
                f"Weakly positive N-region: {n_region_positive} K/R in first 5 aa"
            )

        if h_hydrophobic_pct > 0.60:
            score += 2
            notes.append(
                f"Strong hydrophobic H-region (pos 5-15): {h_hydrophobic_pct:.0%}"
            )
        elif h_hydrophobic_pct > 0.40:
            score += 1
            notes.append(
                f"Moderate hydrophobic H-region (pos 5-15): {h_hydrophobic_pct:.0%}"
            )

        if cleavage_site is not None:
            score += 1
            notes.append(
                f"Potential cleavage site near position {cleavage_site} "
                f"(small amino acid)"
            )

        # Confidence assignment
        # Require both high overall hydrophobicity AND h-region for medium+
        has_n_and_h = (hydrophobic_pct > 0.40) and (h_hydrophobic_pct > 0.50)
        if score >= 5 and has_n_and_h:
            confidence = "high"
            has_signal = True
        elif score >= 4 and has_n_and_h:
            confidence = "medium"
            has_signal = True
        elif score >= 3:
            confidence = "low"
            has_signal = False
            notes.append("Some signal peptide features but below threshold")
        else:
            confidence = "none"
            has_signal = False

        return {
            "has_signal_peptide": has_signal,
            "confidence": confidence,
            "hydrophobic_pct": round(hydrophobic_pct, 4),
            "n_region_positive": n_region_positive,
            "cleavage_site_estimate": cleavage_site if has_signal else None,
            "notes": notes,
        }

    def compute_cai(self, cds_seq: str) -> float:
        """Codon Adaptation Index (CAI) for E. coli K12.

        CAI = exp( (1/n) * sum(ln(w_i)) )

        Parameters
        ----------
        cds_seq : str
            CDS DNA sequence

        Returns
        -------
        float
            CAI value (0 to 1). Closer to 1 means more optimized for E. coli.
        """
        seq = cds_seq.upper().replace(" ", "").replace("\n", "").replace("\r", "")
        codons = [seq[i:i + 3] for i in range(0, len(seq) - 2, 3)]

        log_sum = 0.0
        n = 0
        for codon in codons:
            w = ECOLI_CODON_W.get(codon)
            if w is None:
                continue
            # Skip stop codons for CAI calculation
            if _CODON_TABLE.get(codon) == "*":
                continue
            if w <= 0:
                continue
            log_sum += math.log(w)
            n += 1

        if n == 0:
            return 0.0

        return math.exp(log_sum / n)
