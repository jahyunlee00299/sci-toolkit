#!/usr/bin/env python3
"""
Restriction Cloning Primer Designer
=====================================
Designs primers for RE (restriction enzyme) cloning by subclassing iPCRDesignerBase.

Design principle (RE cloning):
  Forward: 5'-[protection 4-6bp]-[RE5 recognition]-[spacer_5prime]-[insert 5' annealing ~20bp]-3'
  Reverse: 5'-[protection 4-6bp]-[RE3 recognition]-[spacer_3prime]-[RC(stop codon)?]-[insert 3' RC annealing ~20bp]-3'

  Tm calculation: annealing portion only (the RE tail does not bind the template, so it does not contribute to Tm).

Special cases:
  NdeI/NcoI: recognition site contains ATG -> with include_start_codon, the RE site itself supplies the ATG
  Compatible overhang: e.g. BamHI+BglII -> warns of non-directional insertion
  Blunt-end: EcoRV -> warns of no directionality

Data sources:
  NEB (New England Biolabs) enzyme buffer compatibility
  NEB minimum protection bases guidelines
"""

from __future__ import annotations

from Bio.Seq import Seq

from .subst_primer_mode import iPCRDesignerBase
from .vector_registry import (
    RESTRICTION_ENZYMES,
    check_reading_frame,
    format_frame_report,
    get_vector,
)


# ── NEB Buffer Compatibility ──────────────────────────────────────────────────

RE_BUFFER_INFO: dict[str, dict] = {
    "BamHI-HF":   {"buffer": "CutSmart", "activity_cutsmart": 100, "hf": True},
    "BamHI":      {"buffer": "NEBuffer 3.1", "activity_cutsmart": 75, "hf": False},
    "XhoI":       {"buffer": "CutSmart", "activity_cutsmart": 100, "hf": False},
    "NheI-HF":    {"buffer": "CutSmart", "activity_cutsmart": 100, "hf": True},
    "NotI-HF":    {"buffer": "CutSmart", "activity_cutsmart": 100, "hf": True},
    "NdeI":       {"buffer": "CutSmart", "activity_cutsmart": 100, "hf": False},
    "EcoRI-HF":   {"buffer": "CutSmart", "activity_cutsmart": 100, "hf": True},
    "HindIII-HF": {"buffer": "CutSmart", "activity_cutsmart": 100, "hf": True},
    "SalI-HF":    {"buffer": "CutSmart", "activity_cutsmart": 100, "hf": True},
    "KpnI-HF":    {"buffer": "CutSmart", "activity_cutsmart": 100, "hf": True},
    "PstI-HF":    {"buffer": "CutSmart", "activity_cutsmart": 100, "hf": True},
    "NcoI-HF":    {"buffer": "CutSmart", "activity_cutsmart": 100, "hf": True},
    "NcoI":       {"buffer": "NEBuffer 3.1", "activity_cutsmart": 50, "hf": False},
    "BglII":      {"buffer": "NEBuffer 3.1", "activity_cutsmart": 50, "hf": False},
    "EcoRV-HF":   {"buffer": "CutSmart", "activity_cutsmart": 100, "hf": True},
    "EcoRV":      {"buffer": "NEBuffer 3.1", "activity_cutsmart": 50, "hf": False},
    "MfeI-HF":    {"buffer": "CutSmart", "activity_cutsmart": 100, "hf": True},
    "SacI-HF":    {"buffer": "CutSmart", "activity_cutsmart": 100, "hf": True},
    "AvrII":      {"buffer": "CutSmart", "activity_cutsmart": 100, "hf": False},
    "FseI":       {"buffer": "NEBuffer 4", "activity_cutsmart": 10, "hf": False},
    "AscI":       {"buffer": "CutSmart", "activity_cutsmart": 100, "hf": False},
    "PacI":       {"buffer": "CutSmart", "activity_cutsmart": 100, "hf": False},
}

# ── Minimum Protection Bases (NEB guidelines) ─────────────────────────────────

RE_MIN_PROTECTION: dict[int, int] = {
    6: 4,   # 6-cutter: 4 bp protection
    8: 6,   # 8-cutter: 6 bp protection
}

# ── Compatible Overhang Pairs ──────────────────────────────────────────────────

COMPATIBLE_OVERHANGS: list[tuple[str, str]] = [
    ("BamHI", "BglII"),   # both produce 5'-GATC overhang
    ("EcoRI", "MfeI"),    # both produce 5'-AATT overhang
    ("NheI", "AvrII"),    # both produce 5'-CTAG overhang (SpeI, XbaI too)
    ("SalI", "XhoI"),     # both produce 5'-TCGA overhang
]


def _get_base_enzyme(name: str) -> str:
    """Extract the base enzyme name from an HF variant, etc. 'BamHI-HF' -> 'BamHI'."""
    return name.replace("-HF", "")


def _find_all_occurrences(seq: str, pattern: str) -> list[int]:
    """Return every starting position of pattern within seq."""
    positions = []
    start = 0
    while True:
        idx = seq.upper().find(pattern.upper(), start)
        if idx == -1:
            break
        positions.append(idx)
        start = idx + 1
    return positions


class RestrictionCloningDesigner(iPCRDesignerBase):
    """Designs primers for RE cloning (includes NEB buffer compatibility + reading frame validation)."""

    def design(
        self,
        insert_seq: str,
        re_5prime: str,
        re_3prime: str,
        vector_name: str | None = None,
        target_tm: float = 62.0,
        min_ann_len: int = 18,
        max_ann_len: int = 30,
        include_start_codon: bool = True,
        include_stop_codon: bool = False,
        stop_codon: str = "TAA",
        protection_bases_5: int | str | None = None,
        protection_bases_3: int | str | None = None,
        spacer_5prime: str = "",
        spacer_3prime: str = "",
        auto_frame_check: bool = True,
    ) -> dict:
        """Main method for RE cloning primer design.

        Parameters
        ----------
        insert_seq : str
            the CDS sequence to insert (starting from ATG; with or without a stop codon)
        re_5prime, re_3prime : str
            5'/3' restriction enzyme names
        vector_name : str or None
            vector name (for reading frame validation)
        target_tm : float
            target annealing Tm (degC)
        min_ann_len, max_ann_len : int
            minimum/maximum annealing length
        include_start_codon : bool
            whether to include the start codon (ATG) in the primer
        include_stop_codon : bool
            whether to include a stop codon in the reverse primer
        stop_codon : str
            stop codon sequence (default: TAA)
        protection_bases_5 : int, str, or None
            5' protection bases (None=auto, int=length, str=literal sequence)
        protection_bases_3 : int, str, or None
            3' protection bases (None=auto, int=length, str=literal sequence)
        spacer_5prime, spacer_3prime : str
            spacer sequence to add after the RE site
        auto_frame_check : bool
            whether to run an automatic frame check when vector_name is given

        Returns
        -------
        dict : f_full, r_full, f_ann, r_ann, f_tail, r_tail, QC results, etc.
        """
        insert_seq = insert_seq.upper().replace(" ", "")
        warnings: list[str] = []

        re5_info, re3_info = self._validate_design_inputs(insert_seq, re_5prime, re_3prime)
        re5_site = re5_info["recognition"]
        re3_site = re3_info["recognition"]

        # ── 2. Internal RE site scan ─────────────────────────────────────
        internal_re_sites_5 = _find_all_occurrences(insert_seq, re5_site)
        internal_re_sites_3 = _find_all_occurrences(insert_seq, re3_site)
        for re_name, site, positions in (
            (re_5prime, re5_site, internal_re_sites_5),
            (re_3prime, re3_site, internal_re_sites_3),
        ):
            if positions:
                warnings.append(
                    f"INSERT contains {re_name} site ({site}) at position(s): "
                    f"{positions} - may be cut during digestion!"
                )

        # ── 3. Protection bases determination ────────────────────────────
        protection_5 = self._resolve_protection(protection_bases_5, re5_site)
        protection_3 = self._resolve_protection(protection_bases_3, re3_site)

        # ── 4-5. Start-codon, compatible-overhang, same-RE, blunt-end warnings
        warnings.extend(self._enzyme_pair_warnings(
            re_5prime, re_3prime, re5_info, re3_info, include_start_codon))

        # ── 6. Forward primer assembly ───────────────────────────────────
        # Forward annealing: the RE tail does NOT contribute to Tm.
        f_tail = protection_5 + re5_site + spacer_5prime
        f_ann, f_tm, f_gc, f_ann_len = self._design_end_annealing(
            insert_seq, "Forward", target_tm, min_ann_len, max_ann_len, warnings)

        # ── 7. Reverse primer assembly ───────────────────────────────────
        stop_rc = ""
        if include_stop_codon:
            stop_rc = str(Seq(stop_codon.upper()).reverse_complement())

        r_tail = protection_3 + re3_site + spacer_3prime + stop_rc
        r_ann, r_tm, r_gc, r_ann_len = self._design_end_annealing(
            insert_seq, "Reverse", target_tm, min_ann_len, max_ann_len, warnings)

        # ── 8. 2-pass hairpin avoidance ──────────────────────────────────
        anneal_temp = min(f_tm, r_tm) + 1.0

        f_qc = self.check_primer(f_tail + f_ann, anneal_temp)
        r_qc = self.check_primer(r_tail + r_ann, anneal_temp)

        if f_qc["verdict"] == "FAIL":
            f_ann, f_tm, f_gc, f_ann_len = self._retry_for_hairpin(
                "F", insert_seq, (f_ann, f_tm, f_gc, f_ann_len), target_tm,
                min_ann_len, max_ann_len, anneal_temp, warnings)
        if r_qc["verdict"] == "FAIL":
            r_ann, r_tm, r_gc, r_ann_len = self._retry_for_hairpin(
                "R", insert_seq, (r_ann, r_tm, r_gc, r_ann_len), target_tm,
                min_ann_len, max_ann_len, anneal_temp, warnings)

        # ── 9. Assemble final primers ────────────────────────────────────
        f_full = f_tail + f_ann
        r_full = r_tail + r_ann

        # ── 10. Primer-level warnings ────────────────────────────────────
        warnings.extend(self._primer_level_warnings(f_full, r_full))

        # ── 11. Final QC ─────────────────────────────────────────────────
        anneal_temp = min(f_tm, r_tm) + 1.0
        f_qc = self.check_primer(f_full, anneal_temp)
        r_qc = self.check_primer(r_full, anneal_temp)
        het = self.check_heterodimer(f_full, r_full)

        # ── 12. Reading frame check ──────────────────────────────────────
        frame_check = None
        frame_report = None
        if vector_name is not None and auto_frame_check:
            frame_check, frame_report = self._check_frame(
                vector_name, re_5prime, re_3prime, include_start_codon,
                include_stop_codon, len(insert_seq), warnings)

        # ── 13. Build result ─────────────────────────────────────────────
        result = {
            "f_full": f_full,
            "r_full": r_full,
            "f_ann": f_ann,
            "r_ann": r_ann,
            "f_tail": f_tail,
            "r_tail": r_tail,
            "f_tm": round(f_tm, 1),
            "r_tm": round(r_tm, 1),
            "f_gc": round(f_gc, 1),
            "r_gc": round(r_gc, 1),
            "f_len": len(f_full),
            "r_len": len(r_full),
            "f_ann_len": f_ann_len,
            "r_ann_len": r_ann_len,
            "re_5prime": re_5prime,
            "re_3prime": re_3prime,
            "re_5prime_site": re5_site,
            "re_3prime_site": re3_site,
            "protection_5": protection_5,
            "protection_3": protection_3,
            "spacer_5prime": spacer_5prime,
            "spacer_3prime": spacer_3prime,
            "include_start_codon": include_start_codon,
            "include_stop_codon": include_stop_codon,
            "insert_len": len(insert_seq),
            "anneal_temp": round(anneal_temp, 1),
            "f_qc": f_qc,
            "r_qc": r_qc,
            "het": het,
            "internal_re_sites_5": internal_re_sites_5,
            "internal_re_sites_3": internal_re_sites_3,
            "warnings": warnings,
        }

        if frame_check is not None:
            result["frame_check"] = frame_check
            result["frame_report"] = frame_report

        return result

    # ── design() building blocks ─────────────────────────────────────────

    @staticmethod
    def _validate_design_inputs(insert_seq: str, re_5prime: str, re_3prime: str) -> tuple[dict, dict]:
        """Validate the insert and both enzyme names; return their RESTRICTION_ENZYMES records."""
        if not insert_seq:
            raise ValueError("insert_seq is empty")
        if not all(c in "ATGC" for c in insert_seq):
            raise ValueError("insert_seq contains non-ATGC characters")

        if re_5prime not in RESTRICTION_ENZYMES:
            raise ValueError(
                f"Unknown 5' RE: {re_5prime!r}. "
                f"Available: {', '.join(sorted(RESTRICTION_ENZYMES.keys()))}"
            )
        if re_3prime not in RESTRICTION_ENZYMES:
            raise ValueError(
                f"Unknown 3' RE: {re_3prime!r}. "
                f"Available: {', '.join(sorted(RESTRICTION_ENZYMES.keys()))}"
            )
        return RESTRICTION_ENZYMES[re_5prime], RESTRICTION_ENZYMES[re_3prime]

    @staticmethod
    def _enzyme_pair_warnings(re_5prime: str, re_3prime: str, re5_info: dict, re3_info: dict,
                              include_start_codon: bool) -> list[str]:
        """NdeI/NcoI ATG, compatible overhangs, same enzyme on both sides, blunt ends."""
        warnings: list[str] = []
        re5_site = re5_info["recognition"]

        # NdeI/NcoI special case: ATG in recognition site
        if "ATG" in re5_site and include_start_codon:
            warnings.append(
                f"{re_5prime} recognition site ({re5_site}) contains ATG - "
                f"RE site itself provides start codon"
            )

        # Compatible overhang warning
        base_5 = _get_base_enzyme(re_5prime)
        base_3 = _get_base_enzyme(re_3prime)
        for pair in COMPATIBLE_OVERHANGS:
            if (base_5 in pair and base_3 in pair) and base_5 != base_3:
                warnings.append(
                    f"{re_5prime} and {re_3prime} produce compatible sticky ends - "
                    f"insert can ligate in BOTH orientations (non-directional)!"
                )
                break

        # Same enzyme on both sides
        if base_5 == base_3:
            warnings.append(
                f"Same RE ({re_5prime}/{re_3prime}) on both sides - "
                f"insert can ligate in BOTH orientations (non-directional)!"
            )

        # Blunt-end warning
        if re5_info["overhang"] == "blunt" or re3_info["overhang"] == "blunt":
            blunt_re = re_5prime if re5_info["overhang"] == "blunt" else re_3prime
            warnings.append(
                f"{blunt_re} produces blunt ends - "
                f"no directionality from this side"
            )
        return warnings

    def _design_end_annealing(self, insert_seq: str, label: str, target_tm: float,
                              min_ann_len: int, max_ann_len: int,
                              warnings: list[str]) -> tuple:
        """Annealing part of one primer, with the two AT-rich fallbacks.

        ``label`` is "Forward" (anchored at the insert start, + strand) or
        "Reverse" (anchored at the insert end, - strand). The RE tail does NOT
        contribute to Tm. Fallback 1 extends max length to 35 bp; fallback 2
        relaxes the target Tm by 4 degC with max length 36 (and warns).
        Returns (ann, tm, gc, ann_len) or raises RuntimeError.
        """
        if label == "Forward":
            anchor, direction = 0, "+"
        else:
            anchor, direction = len(insert_seq), "-"

        def attempt(tm_target: float, max_len: int):
            return self._design_annealing(
                template=insert_seq, anchor=anchor, direction=direction,
                target_tm=tm_target, min_len=min_ann_len, max_len=max_len,
                tail_seq="",
            )

        ann, tm, gc, ann_len = attempt(target_tm, max_ann_len)
        if ann is None:
            # Fallback 1: extend max to 35 bp
            ann, tm, gc, ann_len = attempt(target_tm, 35)
        if ann is None:
            # Fallback 2: relax Tm by 4°C with extended range
            ann, tm, gc, ann_len = attempt(target_tm - 4.0, 36)
            if ann is not None:
                warnings.append(
                    f"{label} primer Tm ({tm:.1f}°C) is below target "
                    f"({target_tm}°C) due to AT-rich region"
                )
        if ann is None:
            raise RuntimeError(
                f"{label} primer annealing design failed "
                f"(target Tm={target_tm}C, range={min_ann_len}-{max_ann_len} bp)"
            )
        return ann, tm, gc, ann_len

    def _retry_for_hairpin(self, label: str, insert_seq: str, current: tuple, target_tm: float,
                           min_ann_len: int, max_ann_len: int, anneal_temp: float,
                           warnings: list[str]) -> tuple:
        """Second pass for a primer whose QC verdict is FAIL: redesign at ``anneal_temp``.

        ``label`` is "F" or "R". Keeps ``current`` (ann, tm, gc, ann_len) when the
        redesign finds nothing new; either way a warning records the outcome.
        """
        anchor, direction = (0, "+") if label == "F" else (len(insert_seq), "-")
        alt = self._design_annealing(
            template=insert_seq, anchor=anchor, direction=direction,
            target_tm=target_tm, min_len=min_ann_len, max_len=max_ann_len,
            tail_seq="", anneal_temp=anneal_temp,
        )
        if alt[0] is not None and alt[0] != current[0]:
            warnings.append(
                f"{label} annealing adjusted for hairpin avoidance ({len(alt[0])} bp)"
            )
            return alt
        warnings.append(
            f"{label} hairpin: annealing length adjustment cannot resolve"
        )
        return current

    def _primer_level_warnings(self, f_full: str, r_full: str) -> list[str]:
        """Homopolymer runs, missing 3' G/C clamp and over-long primers."""
        warnings: list[str] = []
        for label, primer in [("F", f_full), ("R", r_full)]:
            hp = self.homopolymer_run(primer)
            if hp:
                warnings.append(f"{label} primer homopolymer: {hp}")
            if not self.gc_clamp_ok(primer):
                warnings.append(f"{label} primer no 3' G/C clamp")
            if len(primer) > 60:
                warnings.append(f"{label} primer length ({len(primer)} nt) > 60 nt")
        return warnings

    @staticmethod
    def _check_frame(vector_name: str, re_5prime: str, re_3prime: str, include_start_codon: bool,
                     include_stop_codon: bool, insert_cds_bp: int,
                     warnings: list[str]) -> tuple[dict | None, str | None]:
        """Reading-frame check against the vector; a ValueError becomes a warning."""
        try:
            frame_check = check_reading_frame(
                vector_name=vector_name,
                re_5prime=re_5prime,
                re_3prime=re_3prime,
                insert_has_atg=include_start_codon,
                insert_has_stop=include_stop_codon,
                insert_cds_bp=insert_cds_bp,
            )
            return frame_check, format_frame_report(frame_check)
        except ValueError as e:
            warnings.append(f"Frame check failed: {e}")
            return None, None

    def recommend_re_pair(
        self,
        insert_seq: str,
        vector_name: str,
        prefer_hf: bool = True,
    ) -> list[dict]:
        """Recommend the best RE pair for the given insert and vector.

        Parameters
        ----------
        insert_seq : str
            the CDS sequence to insert
        vector_name : str
            vector name
        prefer_hf : bool
            whether to prefer HF variants

        Returns
        -------
        list[dict] : a list of recommended RE pairs, sorted by descending score
        """
        insert_seq = insert_seq.upper().replace(" ", "")
        vec = get_vector(vector_name)
        re_sites = vec["re_sites"]

        # RE list present in the vector's MCS (in positional order)
        re_list = sorted(re_sites.items(), key=lambda x: x[1])

        recommendations = []

        for i, (re5_name, re5_pos) in enumerate(re_list):
            for re3_name, re3_pos in re_list[i + 1:]:
                # 5' RE must be upstream of 3' RE
                if re5_pos >= re3_pos:
                    continue

                # fetch RE info
                if re5_name not in RESTRICTION_ENZYMES:
                    continue
                if re3_name not in RESTRICTION_ENZYMES:
                    continue

                re5_rec = RESTRICTION_ENZYMES[re5_name]["recognition"]
                re3_rec = RESTRICTION_ENZYMES[re3_name]["recognition"]

                # skip if the RE site occurs inside the insert
                if _find_all_occurrences(insert_seq, re5_rec):
                    continue
                if _find_all_occurrences(insert_seq, re3_rec):
                    continue

                # Scoring
                score = 0
                reasons = []

                # Double digest compatibility (same buffer >= 75%)
                buf5 = self._get_buffer_info(re5_name)
                buf3 = self._get_buffer_info(re3_name)
                double_digest_ok = False
                buffer_name = None

                if buf5 and buf3:
                    if buf5["buffer"] == buf3["buffer"]:
                        double_digest_ok = True
                        buffer_name = buf5["buffer"]
                        score += 3
                        reasons.append(f"Same buffer ({buffer_name})")
                    elif (buf5["activity_cutsmart"] >= 75
                          and buf3["activity_cutsmart"] >= 75):
                        double_digest_ok = True
                        buffer_name = "CutSmart"
                        score += 3
                        reasons.append("Both >= 75% in CutSmart")
                    else:
                        reasons.append("Sequential digest recommended")

                # CutSmart buffer
                if buf5 and buf3:
                    if (buf5["activity_cutsmart"] == 100
                            and buf3["activity_cutsmart"] == 100):
                        score += 2
                        reasons.append("Both 100% in CutSmart")

                # Reading frame compatibility
                frame_ok = False
                try:
                    fc = check_reading_frame(
                        vector_name=vector_name,
                        re_5prime=re5_name,
                        re_3prime=re3_name,
                        insert_has_atg=True,
                        insert_has_stop=False,
                    )
                    if fc["in_frame_5prime"] and fc["in_frame_3prime"]:
                        frame_ok = True
                        score += 2
                        reasons.append("Reading frame compatible")
                    else:
                        reasons.append("Frame mismatch")
                except ValueError:
                    reasons.append("Frame check N/A")

                # HF version available
                hf_available = False
                if prefer_hf:
                    hf5 = f"{re5_name}-HF" in RE_BUFFER_INFO
                    hf3 = f"{re3_name}-HF" in RE_BUFFER_INFO
                    if hf5 or hf3:
                        hf_available = True
                        score += 1
                        hf_names = []
                        if hf5:
                            hf_names.append(f"{re5_name}-HF")
                        if hf3:
                            hf_names.append(f"{re3_name}-HF")
                        reasons.append(f"HF available: {', '.join(hf_names)}")

                recommendations.append({
                    "re_5prime": re5_name,
                    "re_3prime": re3_name,
                    "buffer": buffer_name,
                    "double_digest_ok": double_digest_ok,
                    "frame_ok": frame_ok,
                    "score": score,
                    "reason": "; ".join(reasons),
                })

        # Sort by score descending
        recommendations.sort(key=lambda x: -x["score"])
        return recommendations

    # ── Internal helpers ─────────────────────────────────────────────────

    @staticmethod
    def _resolve_protection(
        protection: int | str | None,
        recognition: str,
    ) -> str:
        """Determine the protection bases.

        None -> auto-generated from RE_MIN_PROTECTION (GCGC... pattern)
        int  -> auto-generated at that length
        str  -> use the literal sequence as-is
        """
        if isinstance(protection, str):
            return protection.upper()

        rec_len = len(recognition)
        if protection is None:
            # pick the nearest key at or below the cutoff
            n_bases = RE_MIN_PROTECTION.get(rec_len)
            if n_bases is None:
                # fallback: the largest key at or below the recognition length
                applicable = [k for k in RE_MIN_PROTECTION if k <= rec_len]
                if applicable:
                    n_bases = RE_MIN_PROTECTION[max(applicable)]
                else:
                    n_bases = 4  # default
        else:
            n_bases = protection

        # GC-rich protection pattern (NEB recommendation)
        pattern = "GCGC"
        return (pattern * ((n_bases // len(pattern)) + 1))[:n_bases]

    @staticmethod
    def _get_buffer_info(enzyme_name: str) -> dict | None:
        """Look up enzyme info in RE_BUFFER_INFO (HF variant preferred)."""
        hf_name = f"{enzyme_name}-HF"
        if hf_name in RE_BUFFER_INFO:
            return RE_BUFFER_INFO[hf_name]
        if enzyme_name in RE_BUFFER_INFO:
            return RE_BUFFER_INFO[enzyme_name]
        return None
