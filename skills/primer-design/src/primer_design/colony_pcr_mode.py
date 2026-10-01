#!/usr/bin/env python3
"""
Colony PCR Primer Designer
===========================
Recommends colony PCR primers based on universal primers, and designs
internal insert primers.

Colony PCR is Taq-polymerase-based, so:
  - Annealing temp = min(F_tm, R_tm) - 5.0
  - No Q5/Phusion correction

The universal primer DB follows the Macrogen Standard Primer list.
"""

from __future__ import annotations

from dataclasses import dataclass

from Bio.Seq import Seq

from .subst_primer_mode import iPCRDesignerBase
from .vector_registry import get_vector, EXPRESSION_VECTORS
from .snapgene_parser import parse_snapgene


# ── UniversalPrimer dataclass ──────────────────────────────────────────────

@dataclass
class UniversalPrimer:
    """Standard primer info, e.g. from Macrogen."""
    name: str
    sequence: str       # 5'->3'
    direction: str      # "forward" or "reverse"
    catalog: str        # e.g., "Macrogen #51"


# ── Universal Primer DB (Macrogen Standard Primers) ────────────────────────

UNIVERSAL_PRIMERS = {
    "T7promoter":     UniversalPrimer("T7promoter",     "TAATACGACTCACTATAGGG",    "forward",  "Macrogen #51"),
    "T7terminator":   UniversalPrimer("T7terminator",   "GCTAGTTATTGCTCAGCGG",     "reverse",  "Macrogen #50"),
    "T7":             UniversalPrimer("T7",             "AATACGACTCACTATAG",       "forward",  "Macrogen #49"),
    "pET_RP":         UniversalPrimer("pET-RP",         "CTAGTTATTGCTCAGCGG",      "reverse",  "Macrogen #14"),
    "pET_24a":        UniversalPrimer("pET-24a",        "GGGTTATGCTAGTTATTGCTCAG", "reverse",  "Macrogen #13"),
    "pET_upstream":   UniversalPrimer("pET-upstream",   "ATGCGTCCGGCGTAGAGG",      "forward",  "Macrogen #90"),
    "pMalE":          UniversalPrimer("pMalE",          "TCAGACTGTCGATGAAGC",      "forward",  "Macrogen #15"),
    "DuetDown1":      UniversalPrimer("DuetDown1",      "GATTATGCGGCCGTGTACAA",    "reverse",  "Macrogen #88"),
    "DuetUP2":        UniversalPrimer("DuetUP2",        "TTGTACACGGCCGCATAATC",    "forward",  "Macrogen #89"),
    "STag":           UniversalPrimer("STag 18mer",     "GAACGCCAGCACATGGAC",      "forward",  "Macrogen #34"),
    "BGH_R":          UniversalPrimer("BGH-R",          "TAGAAGGCACAGTCGAGG",      "reverse",  "Macrogen #64"),
}


# ── Vector → Primer Pair Mapping ──────────────────────────────────────────

VECTOR_PRIMER_MAP: dict[str, tuple[str, str]] = {
    "pET-21a(+)":       ("T7promoter",    "T7terminator"),
    "pET-28a(+)":       ("T7promoter",    "T7terminator"),
    "pETDuet-1:MCS1":   ("pET_upstream",  "T7terminator"),
    "pETDuet-1:MCS2":   ("DuetUP2",       "T7terminator"),
    "pACYCDuet-1:MCS1": ("pET_upstream",  "T7terminator"),
    "pACYCDuet-1:MCS2": ("DuetUP2",       "DuetDown1"),
    "pMAL-c6T":         ("pMalE",         "pET_RP"),
}


# ── Vector Flanking Defaults ──────────────────────────────────────────────
# (upstream_bp from primer to insert start, downstream_bp from insert end to primer)
# The value is the approximate distance from each vector's universal-primer
# binding site to its MCS.

VECTOR_FLANKING_DEFAULTS: dict[str, tuple[int, int]] = {
    "pET-21a(+)":       (200, 150),
    "pET-28a(+)":       (200, 150),
    "pETDuet-1:MCS1":   (150, 150),
    "pETDuet-1:MCS2":   (150, 150),
    "pACYCDuet-1:MCS1": (150, 150),
    "pACYCDuet-1:MCS2": (150, 150),
    "pMAL-c6T":         (200, 100),
}

# MCS gap: approximate length of the MCS region between universal primers
# in the empty vector (no insert)
_MCS_GAP_DEFAULTS: dict[str, int] = {
    "pET-21a(+)":       100,
    "pET-28a(+)":       160,
    "pETDuet-1:MCS1":   90,
    "pETDuet-1:MCS2":   130,
    "pACYCDuet-1:MCS1": 90,
    "pACYCDuet-1:MCS2": 130,
    "pMAL-c6T":         65,
}


# ── ColonyPCRDesigner ─────────────────────────────────────────────────────

class ColonyPCRDesigner(iPCRDesignerBase):
    """Colony PCR primer recommendation (Taq-based).

    Recommends colony PCR conditions based on universal primers, and
    designs internal insert primers when needed.
    """

    def _resolve_canonical_name(self, vector_name: str) -> str:
        """Convert a vector name to its canonical name.

        get_vector() returns a data dict, so find the same dict object in
        EXPRESSION_VECTORS and return its canonical key.
        """
        vec_data = get_vector(vector_name)
        for canonical, data in EXPRESSION_VECTORS.items():
            if data is vec_data:
                return canonical
        return vector_name

    def suggest(
        self,
        vector_name: str,
        insert_length_bp: int,
        vector_flanking_bp: int | tuple[int, int] | None = None,
    ) -> dict:
        """Recommend colony PCR conditions based on universal primers.

        Parameters
        ----------
        vector_name : str
            Vector name (supports fuzzy matching, e.g. "pET28a")
        insert_length_bp : int
            Insert length (bp)
        vector_flanking_bp : int or tuple[int, int] or None
            Flanking distance between primer and insert.
            int: same on both sides, tuple: (upstream, downstream), None: use defaults.

        Returns
        -------
        dict
            f_name, f_seq, f_tm, r_name, r_seq, r_tm,
            expected_band_with_insert, expected_band_empty,
            anneal_temp, flanking_upstream, flanking_downstream, notes
        """
        # 1. Resolve vector
        get_vector(vector_name)  # validate
        canonical = self._resolve_canonical_name(vector_name)
        notes: list[str] = []

        # 2. Primer pair lookup
        if canonical not in VECTOR_PRIMER_MAP:
            available = ", ".join(VECTOR_PRIMER_MAP.keys())
            raise ValueError(
                f"No colony PCR primers mapped for {canonical!r}. "
                f"Available: {available}. Use register_primer_pair() to add."
            )

        f_key, r_key = VECTOR_PRIMER_MAP[canonical]
        f_primer = UNIVERSAL_PRIMERS[f_key]
        r_primer = UNIVERSAL_PRIMERS[r_key]

        # 3. Flanking distances
        if vector_flanking_bp is None:
            flanking = VECTOR_FLANKING_DEFAULTS.get(canonical, (200, 150))
            notes.append(f"Flanking distances: default for {canonical}")
        elif isinstance(vector_flanking_bp, int):
            flanking = (vector_flanking_bp, vector_flanking_bp)
        else:
            flanking = vector_flanking_bp

        flanking_up, flanking_dn = flanking

        # 4. Expected band sizes
        expected_with_insert = flanking_up + insert_length_bp + flanking_dn
        mcs_gap = _MCS_GAP_DEFAULTS.get(canonical, 100)
        expected_empty = flanking_up + mcs_gap + flanking_dn

        # 5. Tm calculation
        f_tm = self.calc_tm(f_primer.sequence)
        r_tm = self.calc_tm(r_primer.sequence)

        # 6. Annealing temp (Taq-based: min Tm - 5)
        anneal_temp = min(f_tm, r_tm) - 5.0

        # 7. Notes
        if abs(f_tm - r_tm) > 5.0:
            notes.append(
                f"Tm difference {abs(f_tm - r_tm):.1f}C between F/R; "
                f"consider touchdown PCR"
            )
        if insert_length_bp > 3000:
            notes.append(
                f"Insert {insert_length_bp} bp is large for Taq colony PCR; "
                f"consider extension time >= {insert_length_bp // 1000 + 1} min"
            )

        return {
            "vector_name": canonical,
            "f_name": f_primer.name,
            "f_seq": f_primer.sequence,
            "f_tm": round(f_tm, 1),
            "r_name": r_primer.name,
            "r_seq": r_primer.sequence,
            "r_tm": round(r_tm, 1),
            "expected_band_with_insert": expected_with_insert,
            "expected_band_empty": expected_empty,
            "anneal_temp": round(anneal_temp, 1),
            "flanking_upstream": flanking_up,
            "flanking_downstream": flanking_dn,
            "notes": notes,
        }

    def suggest_with_internal(
        self,
        vector_name: str,
        insert_seq: str,
        target_tm: float = 58.0,
        target_product_range: tuple[int, int] = (300, 1200),
    ) -> dict:
        """Recommend a universal primer pair together with internal insert primers.

        When the insert is long, universal primers alone can give a band
        that is too large or hard to distinguish, so also design a primer
        pair that anneals inside the insert.

        Parameters
        ----------
        vector_name : str
            Vector name
        insert_seq : str
            Full insert sequence (DNA)
        target_tm : float
            Target Tm for the internal primers (Taq-based, default 58C)
        target_product_range : tuple[int, int]
            Target product size range for the internal primer pair (bp)

        Returns
        -------
        dict
            universal: the suggest() result,
            internal_f_seq, internal_f_tm,
            internal_r_seq, internal_r_tm,
            internal_product_size, internal_notes
        """
        insert_len = len(insert_seq)

        # 1. Recommend the universal primer
        universal = self.suggest(vector_name, insert_len)

        # 2. Internal forward primer: ~100bp from start
        internal_notes: list[str] = []
        f_start = min(100, insert_len // 4)
        int_f_seq, int_f_tm = self._pick_internal_primer(
            insert_seq, f_start, "+", target_tm,
        )

        # 3. Internal reverse primer: ~100bp from end
        r_anchor = max(insert_len - 100, insert_len * 3 // 4)
        int_r_seq, int_r_tm = self._pick_internal_primer(
            insert_seq, r_anchor, "-", target_tm,
        )

        # 4. Product size check
        if int_f_seq is not None and int_r_seq is not None:
            # Forward primer starts at f_start, reverse primer ends at r_anchor
            internal_product = r_anchor - f_start
            min_prod, max_prod = target_product_range

            if internal_product < min_prod:
                internal_notes.append(
                    f"Internal product {internal_product} bp < target min {min_prod} bp; "
                    f"insert may be too short for internal primers"
                )
            elif internal_product > max_prod:
                internal_notes.append(
                    f"Internal product {internal_product} bp > target max {max_prod} bp; "
                    f"consider adjusting primer positions"
                )
        else:
            internal_product = None
            internal_notes.append(
                "Internal primer design failed; insert may be too short"
            )

        return {
            "universal": universal,
            "internal_f_seq": int_f_seq,
            "internal_f_tm": round(int_f_tm, 1) if int_f_tm is not None else None,
            "internal_r_seq": int_r_seq,
            "internal_r_tm": round(int_r_tm, 1) if int_r_tm is not None else None,
            "internal_product_size": internal_product,
            "internal_notes": internal_notes,
        }

    def suggest_from_snapgene(
        self,
        snapgene_path: str,
        vector_name: str,
        cds_feature_name: str | None = None,
    ) -> dict:
        """Find a CDS feature in a SnapGene .dna file and call suggest().

        Parameters
        ----------
        snapgene_path : str
            Path to the SnapGene .dna file
        vector_name : str
            Vector name
        cds_feature_name : str or None
            CDS feature name. If None, uses the first CDS.

        Returns
        -------
        dict
            the suggest() result + snapgene_info
        """
        sequence, is_circular, features = parse_snapgene(snapgene_path)

        # Find the CDS feature
        cds_features = [f for f in features if f["type"] == "CDS"]
        if not cds_features:
            # If there's no CDS, also try the gene type
            cds_features = [f for f in features if f["type"] in ("CDS", "gene")]

        if not cds_features:
            raise ValueError(
                f"No CDS features found in {snapgene_path}. "
                f"Available features: {[f['name'] for f in features]}"
            )

        if cds_feature_name is not None:
            matched = [f for f in cds_features if f["name"] == cds_feature_name]
            if not matched:
                available_names = [f["name"] for f in cds_features]
                raise ValueError(
                    f"CDS feature {cds_feature_name!r} not found. "
                    f"Available CDS features: {available_names}"
                )
            cds = matched[0]
        else:
            cds = cds_features[0]

        insert_length = cds["end"] - cds["start"]

        result = self.suggest(vector_name, insert_length)
        result["snapgene_info"] = {
            "file": snapgene_path,
            "cds_name": cds["name"],
            "cds_start": cds["start"],
            "cds_end": cds["end"],
            "insert_length_bp": insert_length,
            "is_circular": is_circular,
            "total_sequence_length": len(sequence) if sequence else 0,
        }
        return result

    @classmethod
    def register_primer_pair(
        cls, vector_name: str, forward: str, reverse: str,
    ) -> None:
        """Register/overwrite a primer pair in VECTOR_PRIMER_MAP.

        Parameters
        ----------
        vector_name : str
            Vector canonical name (a key in EXPRESSION_VECTORS)
        forward : str
            Forward primer key (a key in UNIVERSAL_PRIMERS)
        reverse : str
            Reverse primer key (a key in UNIVERSAL_PRIMERS)
        """
        if forward not in UNIVERSAL_PRIMERS:
            raise ValueError(
                f"Forward primer {forward!r} not in UNIVERSAL_PRIMERS. "
                f"Available: {', '.join(UNIVERSAL_PRIMERS.keys())}"
            )
        if reverse not in UNIVERSAL_PRIMERS:
            raise ValueError(
                f"Reverse primer {reverse!r} not in UNIVERSAL_PRIMERS. "
                f"Available: {', '.join(UNIVERSAL_PRIMERS.keys())}"
            )
        VECTOR_PRIMER_MAP[vector_name] = (forward, reverse)

    # ── Internal helper ────────────────────────────────────────────────────

    def _pick_internal_primer(
        self,
        seq: str,
        anchor: int,
        direction: str,
        target_tm: float,
        min_len: int = 18,
        max_len: int = 28,
    ) -> tuple[str | None, float | None]:
        """Select the primer within the insert sequence closest to the target Tm.

        Parameters
        ----------
        seq : str
            Insert sequence
        anchor : int
            Primer start position (0-indexed)
        direction : str
            "+" (forward) or "-" (reverse)
        target_tm : float
            Target Tm
        min_len, max_len : int
            Primer length range

        Returns
        -------
        tuple : (primer_seq, tm) or (None, None)
        """
        best_seq = None
        best_tm = None
        best_diff = float("inf")

        for length in range(min_len, max_len + 1):
            if direction == "+":
                if anchor + length > len(seq):
                    break
                candidate = seq[anchor:anchor + length]
            else:
                start = anchor - length
                if start < 0:
                    continue
                candidate = str(Seq(seq[start:anchor]).reverse_complement())

            tm = self.calc_tm(candidate)
            diff = abs(tm - target_tm)

            if diff < best_diff:
                best_diff = diff
                best_seq = candidate
                best_tm = tm

            # No need to go longer once Tm has been reached
            if tm >= target_tm:
                break

        return best_seq, best_tm
