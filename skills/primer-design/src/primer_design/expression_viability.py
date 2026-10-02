"""Expression viability check for a designed RE-cloning construct.

Pure logic (no MCP, no I/O): given the insert and the design result of
`RestrictionCloningDesigner.design`, report the fusion protein, reading frame,
internal restriction sites, premature stops and insert quality, with an overall
PASS / WARNING / FAIL verdict. Used by `mcp_cloning_tools.design_re_cloning_primers`.
"""

from __future__ import annotations

from ._mcp_common import _expression_analyzer

# ── Vector expression context lookup ─────────────────────────────────────────

_VECTOR_EXPRESSION_INFO: dict[str, dict] = {
    "pET-21a(+)": {
        "promoter": "T7/lac",
        "inducer": "IPTG",
        "rbs": "vector-provided (T7 gene 10 leader)",
        "host_requirement": "BL21(DE3) or DE3 lysogen",
        "expression_type": "cytoplasmic, high-level",
        "notes": "C-terminal His-tag only (no N-terminal tag)",
    },
    "pET-28a(+)": {
        "promoter": "T7/lac",
        "inducer": "IPTG",
        "rbs": "vector-provided (T7 gene 10 leader)",
        "host_requirement": "BL21(DE3) or DE3 lysogen",
        "expression_type": "cytoplasmic, high-level",
        "notes": "N-terminal His6 + thrombin + T7-tag; optional C-terminal His6",
    },
    "pMAL-c6T": {
        "promoter": "Ptac",
        "inducer": "IPTG",
        "rbs": "malE translation initiation signals",
        "host_requirement": "any E. coli strain",
        "expression_type": "cytoplasmic, MBP fusion",
        "notes": "MBP-TEV-insert fusion; amylose resin purification",
    },
    "pETDuet-1:MCS1": {
        "promoter": "T7/lac (MCS1)",
        "inducer": "IPTG",
        "rbs": "vector-provided",
        "host_requirement": "BL21(DE3) or DE3 lysogen",
        "expression_type": "cytoplasmic, co-expression",
        "notes": "Duet vector MCS1; N-terminal His6; co-expression with MCS2",
    },
    "pETDuet-1:MCS2": {
        "promoter": "T7/lac (MCS2)",
        "inducer": "IPTG",
        "rbs": "vector-provided",
        "host_requirement": "BL21(DE3) or DE3 lysogen",
        "expression_type": "cytoplasmic, co-expression",
        "notes": "Duet vector MCS2; optional S-tag; co-expression with MCS1",
    },
    "pACYCDuet-1:MCS1": {
        "promoter": "T7/lac (MCS1)",
        "inducer": "IPTG",
        "rbs": "vector-provided",
        "host_requirement": "BL21(DE3) or DE3 lysogen",
        "expression_type": "cytoplasmic, co-expression",
        "notes": "CmR; compatible with pET/pETDuet (ColA ori); N-terminal His6",
    },
    "pACYCDuet-1:MCS2": {
        "promoter": "T7/lac (MCS2)",
        "inducer": "IPTG",
        "rbs": "vector-provided",
        "host_requirement": "BL21(DE3) or DE3 lysogen",
        "expression_type": "cytoplasmic, co-expression",
        "notes": "CmR; compatible with pET/pETDuet (ColA ori); optional S-tag",
    },
}


def _normalize_vector_name(name: str) -> str:
    return (name.lower().replace(" ", "").replace("-", "")
            .replace("(", "").replace(")", "").replace("+", ""))


def _get_vector_expression_context(vector_name: str) -> dict:
    """Return expression context info for a vector."""
    if not vector_name:
        return {"promoter": "unknown", "notes": "No vector specified"}

    # Direct match
    info = _VECTOR_EXPRESSION_INFO.get(vector_name)
    if info:
        return info

    # Fuzzy match
    vn = _normalize_vector_name(vector_name)
    for name, data in _VECTOR_EXPRESSION_INFO.items():
        if vn == _normalize_vector_name(name):
            return data

    return {"promoter": "unknown", "notes": f"Vector '{vector_name}' not in expression database"}


# ── Building blocks of the check ──────────────────────────────────────────────

_CODON_TABLE = {
    "TTT": "F", "TTC": "F", "TTA": "L", "TTG": "L", "CTT": "L", "CTC": "L",
    "CTA": "L", "CTG": "L", "ATT": "I", "ATC": "I", "ATA": "I", "ATG": "M",
    "GTT": "V", "GTC": "V", "GTA": "V", "GTG": "V", "TCT": "S", "TCC": "S",
    "TCA": "S", "TCG": "S", "CCT": "P", "CCC": "P", "CCA": "P", "CCG": "P",
    "ACT": "T", "ACC": "T", "ACA": "T", "ACG": "T", "GCT": "A", "GCC": "A",
    "GCA": "A", "GCG": "A", "TAT": "Y", "TAC": "Y", "TAA": "*", "TAG": "*",
    "CAT": "H", "CAC": "H", "CAA": "Q", "CAG": "Q", "AAT": "N", "AAC": "N",
    "AAA": "K", "AAG": "K", "GAT": "D", "GAC": "D", "GAA": "E", "GAG": "E",
    "TGT": "C", "TGC": "C", "TGA": "*", "TGG": "W", "CGT": "R", "CGC": "R",
    "CGA": "R", "CGG": "R", "AGT": "S", "AGC": "S", "AGA": "R", "AGG": "R",
    "GGT": "G", "GGC": "G", "GGA": "G", "GGG": "G",
}
_STOP_CODONS = {"TAA", "TAG", "TGA"}
_N_TERMINAL_TAGS = ["N-His6", "N-His8", "Thrombin", "T7-tag", "MBP", "Factor Xa", "S-tag", "TEV"]
_C_TERMINAL_TAGS = ["C-His6", "C-His8", "S-tag"]


def _translate_insert(seq: str) -> str:
    """Translate the insert up to (excluding) its first stop codon; unknown codons -> X."""
    protein = ""
    for i in range(0, len(seq) - 2, 3):
        aa = _CODON_TABLE.get(seq[i:i + 3], "X")
        if aa == "*":
            break
        protein += aa
    return protein


def _fusion_protein(insert_protein: str, linker_5_aa: str, linker_3_aa: str,
                    in_frame_5, in_frame_3, has_stop: bool) -> str:
    """Insert protein with the in-frame vector linkers attached."""
    fusion = linker_5_aa + insert_protein if (linker_5_aa and in_frame_5) else insert_protein
    if not has_stop and linker_3_aa and in_frame_3:
        fusion += linker_3_aa
    return fusion


def _fusion_mw_kda(fusion_protein: str) -> float:
    avg_aa_mw = 110.0
    water = 18.015
    if not fusion_protein:
        return 0.0
    return (len(fusion_protein) * avg_aa_mw
            - (len(fusion_protein) - 1) * water + water) / 1000.0


def _start_codon_source(seq: str, linker_5_aa: str, warnings: list[str]) -> str:
    """Who provides the ATG: the vector N-terminal region, the insert, or nobody (warns)."""
    if linker_5_aa:
        return "vector"
    if seq[:3] == "ATG":
        return "insert"
    warnings.append(
        "No ATG start codon found at insert start, "
        "and no vector N-terminal fusion detected"
    )
    return "unknown"


def _reading_frame_warnings(in_frame_5, in_frame_3, has_stop: bool,
                            re_5prime: str, re_3prime: str, warnings: list[str]) -> None:
    if in_frame_5 is False:
        warnings.append(
            f"5' reading frame MISMATCH: insert is NOT in-frame with "
            f"vector N-terminal tags through {re_5prime}"
        )
    if not has_stop and in_frame_3 is False:
        warnings.append(
            f"3' reading frame MISMATCH: insert is NOT in-frame with "
            f"vector C-terminal tags through {re_3prime}"
        )


def _active_tags(topology: str, linker_5_aa: str, linker_3_aa: str,
                 in_frame_5, in_frame_3, has_stop: bool) -> list[dict]:
    tags = []
    if linker_5_aa and in_frame_5:
        tags += [{"name": t, "position": "N-terminal"} for t in _N_TERMINAL_TAGS if t in topology]
    if not has_stop and linker_3_aa and in_frame_3:
        tags += [{"name": t, "position": "C-terminal"} for t in _C_TERMINAL_TAGS if t in topology]
    return tags


def _site_positions(seq: str, site: str) -> list[int]:
    """1-based start of every (overlapping) occurrence of `site` in `seq`."""
    positions = []
    start = 0
    while True:
        idx = seq.find(site, start)
        if idx == -1:
            return positions
        positions.append(idx + 1)
        start = idx + 1


def _internal_re_sites(seq: str, enzyme_sites: list[tuple[str, str]],
                       warnings: list[str]) -> list[dict]:
    """Cuts of the two cloning enzymes inside the insert (both strands, as designed).

    `count` is the non-overlapping `str.count`, `positions_bp` lists every
    overlapping hit; the two agree for the non-self-overlapping sites in use.
    """
    from Bio.Seq import Seq

    cuts = []
    for re_name, re_site in enzyme_sites:
        if not re_site:
            continue
        for check_site, label in [
            (re_site, re_site),
            (str(Seq(re_site).reverse_complement()), f"RC({re_site})"),
        ]:
            count = seq.count(check_site)
            if count == 0:
                continue
            positions = _site_positions(seq, check_site)
            cuts.append({
                "enzyme": re_name,
                "site": label,
                "count": count,
                "positions_bp": positions,
            })
            warnings.append(
                f"CRITICAL: {re_name} ({label}) cuts within the insert "
                f"at {count} position(s): bp {positions}"
            )
    return cuts


def _premature_stops(seq: str, warnings: list[str]) -> list[dict]:
    """In-frame stop codons before the last codon."""
    stops = []
    for i in range(0, len(seq) - 5, 3):  # exclude last codon
        codon = seq[i:i + 3]
        if codon in _STOP_CODONS:
            stops.append({
                "codon": codon,
                "position_codon": i // 3 + 1,
                "position_bp": i + 1,
            })
    if stops:
        warnings.append(
            f"Premature stop codon(s) at codon position(s): "
            f"{[s['position_codon'] for s in stops]}. "
            f"Protein will be truncated!"
        )
    return stops


def _verdict(has_critical: bool, cai: float, n_warnings: int) -> tuple[str, str]:
    if has_critical:
        return "FAIL", "Critical issues found - construct will NOT express correctly"
    if cai < 0.2:
        return "WARNING", "Very low CAI - expression may fail"
    if n_warnings > 0:
        return "WARNING", "Minor issues found - review before proceeding"
    return "PASS", "No issues detected - construct should express correctly"


# ── The check ─────────────────────────────────────────────────────────────────

def _check_expression_viability(
    insert_seq: str,
    gene_name: str,
    re_5prime: str,
    re_3prime: str,
    design_result: dict,
) -> dict:
    """Comprehensive expression viability check for the cloned construct.

    Analyzes the full vector context including promoter, RBS, start codon,
    fusion protein topology, and insert quality.

    Checks:
    1. Vector expression context (promoter, RBS, start codon, direction)
    2. Fusion protein topology and reading frame
    3. Full expressed protein sequence and MW
    4. Internal RE sites in the insert
    5. Premature stop codons within the CDS
    6. Insert CDS quality (CAI, rare codons, strain recommendation)
    """
    warnings: list[str] = []
    seq = insert_seq.upper()
    frame_check = design_result.get("frame_check", {})
    vector_name = frame_check.get("vector_name", "")
    vector_context = _get_vector_expression_context(vector_name)

    # Fusion topology from frame_check
    topology = frame_check.get("topology", "")
    in_frame_5 = frame_check.get("in_frame_5prime", None)
    in_frame_3 = frame_check.get("in_frame_3prime", None)
    linker_5_aa = frame_check.get("linker_5prime_aa", "")
    linker_3_aa = frame_check.get("linker_3prime_aa", "")

    # Does the insert's own stop terminate translation?
    insert_has_native_stop = seq[-3:] in _STOP_CODONS
    has_stop = insert_has_native_stop or design_result.get("include_stop_codon", False)

    insert_protein = _translate_insert(seq)
    fusion_protein = _fusion_protein(insert_protein, linker_5_aa, linker_3_aa,
                                     in_frame_5, in_frame_3, has_stop)
    start_codon_source = _start_codon_source(seq, linker_5_aa, warnings)
    _reading_frame_warnings(in_frame_5, in_frame_3, has_stop, re_5prime, re_3prime, warnings)
    active_tags = _active_tags(topology, linker_5_aa, linker_3_aa, in_frame_5, in_frame_3, has_stop)
    c_tag_blocked = bool(has_stop and "C-His" in topology)  # C-terminal tag blocked by stop codon

    internal_cuts = _internal_re_sites(
        seq,
        [(re_5prime, design_result.get("re_5prime_site", "")),
         (re_3prime, design_result.get("re_3prime_site", ""))],
        warnings)
    premature_stops = _premature_stops(seq, warnings)
    if len(seq) % 3 != 0:
        warnings.append(
            f"Insert length ({len(seq)} bp) is not a multiple of 3. "
            f"Reading frame will be disrupted!"
        )

    expr_result = _expression_analyzer.analyze(cds_seq=seq)
    has_critical = (
        bool(internal_cuts)
        or bool(premature_stops)
        or (len(seq) % 3 != 0)
        or in_frame_5 is False
    )
    verdict, verdict_detail = _verdict(has_critical, expr_result.get("cai", 1.0), len(warnings))

    return {
        "verdict": verdict,
        "verdict_detail": verdict_detail,
        # Vector context
        "vector_context": vector_context,
        "start_codon_source": start_codon_source,
        # Fusion protein
        "topology": topology,
        "active_tags": active_tags,
        "c_terminal_tag_blocked": c_tag_blocked,
        "fusion_protein_length_aa": len(fusion_protein),
        "fusion_protein_mw_kda": round(_fusion_mw_kda(fusion_protein), 2),
        "insert_protein_length_aa": len(insert_protein),
        "n_terminal_linker_aa": linker_5_aa,
        "c_terminal_linker_aa": linker_3_aa if not has_stop else "(blocked by stop codon)",
        # Reading frame
        "in_frame_5prime": in_frame_5,
        "in_frame_3prime": in_frame_3,
        "insert_has_native_stop": insert_has_native_stop,
        # Insert quality
        "insert_cds_length_bp": len(seq),
        "cds_length_valid": len(seq) % 3 == 0,
        "gc_content": expr_result["basic_info"]["gc_content"],
        "cai": expr_result["cai"],
        "rare_codon_pct": expr_result["rare_codons"]["rare_codon_pct"],
        "rare_codon_clusters": len(expr_result.get("rare_codon_clusters", [])),
        "strain_recommendation": expr_result["strain_recommendation"]["primary_strain"],
        "map_removal": expr_result["map_removal"]["will_be_removed"],
        # Issues
        "internal_re_sites": internal_cuts,
        "premature_stop_codons": premature_stops,
        "warnings": warnings,
    }
