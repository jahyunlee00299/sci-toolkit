"""MCP tool functions for restriction-enzyme cloning.

design_re_cloning_primers, recommend_re_pair, suggest_colony_pcr and
check_reading_frame_tool. The functions are plain callables; `mcp_server`
registers them on the FastMCP instance (so tool names and order live in one place).
"""

from __future__ import annotations

from pathlib import Path

from ._mcp_common import _colony_designer, _re_designer, logger
from .expression_viability import _check_expression_viability
from .vector_registry import check_reading_frame, format_frame_report


def _output_basename(gene_name: str, vector_name: str | None, re_5prime: str, re_3prime: str) -> str:
    """File stem shared by the .dna construct and the PNG report."""
    safe_name = gene_name.replace(" ", "_")
    if vector_name:
        safe_vec = (vector_name
                    .replace("(", "").replace(")", "")
                    .replace(":", "-").replace(" ", "_"))
        return f"{safe_name}_{safe_vec}_{re_5prime}_{re_3prime}"
    return f"{safe_name}_{re_5prime}_{re_3prime}"


def _suggest_colony_pcr_for_design(result: dict, vector_name: str | None, insert_len: int):
    """Attach the colony-PCR suggestion to `result` (for the .dna annotation); None if skipped."""
    if not vector_name:
        return None
    try:
        colony_pcr_result = _colony_designer.suggest(
            vector_name=vector_name,
            insert_length_bp=insert_len,
        )
    except Exception as exc:
        logger.warning("Colony PCR suggest skipped: %s", exc)
        return None
    result["colony_pcr"] = colony_pcr_result
    logger.info(
        "Colony PCR: %s / %s (band: %d bp)",
        colony_pcr_result["f_name"],
        colony_pcr_result["r_name"],
        colony_pcr_result["expected_band_with_insert"],
    )
    return colony_pcr_result


def _write_construct_file(result: dict, clean_seq: str, out: Path, base: str, vector_name: str | None,
                          gene_name: str, gene_description: str, colony_pcr_result) -> None:
    """Always generate the SnapGene .dna construct file; failures land in result['snapgene_error']."""
    try:
        from .snapgene_writer import write_cloning_construct
        from .vector_dna_config import get_vector_dna_path

        vec_dna = get_vector_dna_path(vector_name) if vector_name else None
        if vec_dna:
            logger.info("Using base vector: %s", vec_dna)
        else:
            logger.info("No vector .dna file found; generating PCR product only")

        dna_path = write_cloning_construct(
            design_result=result,
            insert_seq=clean_seq,
            output_path=out / f"{base}_construct.dna",
            gene_name=gene_name,
            vector_dna_path=vec_dna,
            gene_description=gene_description,
            colony_pcr=colony_pcr_result,
        )
        result["snapgene_path"] = str(dna_path)
        logger.info("SnapGene file: %s", dna_path)
    except Exception as exc:
        logger.error("SnapGene generation failed: %s", exc)
        result["snapgene_error"] = str(exc)


def _write_report_png(result: dict, out: Path, base: str, gene_name: str) -> None:
    """Optional PNG report; failures land in result['report_image_error']."""
    try:
        from .cloning_report import generate_cloning_report

        report_path = generate_cloning_report(
            design_result=result,
            output_path=out / f"{base}_report.png",
            gene_name=gene_name,
        )
        result["report_image_path"] = str(report_path)
        logger.info("Report image: %s", report_path)
    except Exception as exc:
        logger.error("Report generation failed: %s", exc)
        result["report_image_error"] = str(exc)


def _attach_expression_check(result: dict, clean_seq: str, gene_name: str,
                             re_5prime: str, re_3prime: str) -> None:
    try:
        expr_check = _check_expression_viability(
            insert_seq=clean_seq,
            gene_name=gene_name,
            re_5prime=re_5prime,
            re_3prime=re_3prime,
            design_result=result,
        )
        result["expression_check"] = expr_check
        logger.info("Expression check: %s", expr_check.get("verdict", "?"))
    except Exception as exc:
        logger.error("Expression check failed: %s", exc)
        result["expression_check_error"] = str(exc)


def design_re_cloning_primers(
    insert_seq: str,
    re_5prime: str,
    re_3prime: str,
    vector_name: str | None = None,
    include_start_codon: bool = True,
    include_stop_codon: bool = False,
    target_tm: float = 62.0,
    gene_name: str = "Insert",
    gene_description: str = "",
    output_dir: str | None = None,
    generate_report_png: bool = False,
) -> dict:
    """Design RE cloning primers for inserting a CDS into an expression vector.

    Automatically generates a SnapGene .dna construct file (output_dir or CWD).
    Optionally generates a PNG report when generate_report_png=True.

    Args:
        insert_seq: Insert CDS sequence (DNA, ATG to stop). Spaces are stripped.
        re_5prime: 5' restriction enzyme name (e.g. "BamHI", "NdeI", "NheI").
        re_3prime: 3' restriction enzyme name (e.g. "XhoI", "NotI", "HindIII").
        vector_name: Optional vector name for reading frame check (e.g. "pET-28a(+)").
        include_start_codon: Include ATG start codon in forward primer (default True).
        include_stop_codon: Include stop codon in reverse primer (default False).
        target_tm: Target annealing Tm in Celsius (default 62.0).
        gene_name: Gene name for labeling report and SnapGene features (default "Insert").
        gene_description: Gene product description (e.g. "beta-galactosidase").
            Added as /note qualifier on CDS in SnapGene .dna file.
        output_dir: Output directory for generated files.
            Defaults to current working directory.
        generate_report_png: Generate a visual PNG report (default False).

    Returns:
        dict with F/R primer sequences, Tm, GC%, QC results, frame check, warnings,
        snapgene_path, and optionally report_image_path.
    """
    clean_seq = insert_seq.replace(" ", "")
    logger.info(
        "design_re_cloning_primers: %s/%s, vector=%s, insert=%d bp",
        re_5prime, re_3prime, vector_name, len(clean_seq),
    )
    result = _re_designer.design(
        insert_seq=insert_seq,
        re_5prime=re_5prime,
        re_3prime=re_3prime,
        vector_name=vector_name,
        target_tm=target_tm,
        include_start_codon=include_start_codon,
        include_stop_codon=include_stop_codon,
    )

    # Output directory (files are always generated)
    out = Path(output_dir) if output_dir else Path.cwd()
    out.mkdir(parents=True, exist_ok=True)
    base = _output_basename(gene_name, vector_name, re_5prime, re_3prime)

    colony_pcr_result = _suggest_colony_pcr_for_design(result, vector_name, len(clean_seq))
    _write_construct_file(result, clean_seq, out, base, vector_name, gene_name,
                          gene_description, colony_pcr_result)
    if generate_report_png:
        _write_report_png(result, out, base, gene_name)
    _attach_expression_check(result, clean_seq, gene_name, re_5prime, re_3prime)
    return result


def recommend_re_pair(
    insert_seq: str,
    vector_name: str,
    prefer_hf: bool = True,
) -> list[dict]:
    """Recommend optimal RE pairs for cloning an insert into a vector.

    Scores each RE combination based on buffer compatibility, reading frame,
    and HF variant availability.

    Args:
        insert_seq: Insert CDS sequence (DNA).
        vector_name: Vector name (e.g. "pET-28a(+)", "pET-21a(+)").
        prefer_hf: Prefer HF (High Fidelity) enzyme variants (default True).

    Returns:
        List of RE pair recommendations sorted by score (highest first).
        Each entry has re_5prime, re_3prime, score, buffer, frame_ok, reason.
    """
    logger.info(
        "recommend_re_pair: vector=%s, insert=%d bp",
        vector_name, len(insert_seq.replace(" ", "")),
    )
    return _re_designer.recommend_re_pair(
        insert_seq=insert_seq,
        vector_name=vector_name,
        prefer_hf=prefer_hf,
    )


def suggest_colony_pcr(
    vector_name: str,
    insert_length_bp: int,
) -> dict:
    """Suggest colony PCR primers and expected band sizes for a vector+insert.

    Uses universal primer database (Macrogen standard primers) matched to
    the vector type.

    Args:
        vector_name: Vector name (e.g. "pET-28a(+)", "pETDuet-1:MCS1").
            Fuzzy matching supported (e.g. "pET28a").
        insert_length_bp: Insert length in base pairs.

    Returns:
        dict with F/R primer name, sequence, Tm, expected band sizes
        (with insert and empty vector), and annealing temperature.
    """
    logger.info(
        "suggest_colony_pcr: vector=%s, insert=%d bp",
        vector_name, insert_length_bp,
    )
    return _colony_designer.suggest(
        vector_name=vector_name,
        insert_length_bp=insert_length_bp,
    )


def check_reading_frame_tool(
    vector_name: str,
    re_5prime: str,
    re_3prime: str,
    insert_has_atg: bool = True,
    insert_has_stop: bool = False,
    insert_cds_bp: int | None = None,
) -> dict:
    """Verify reading frame compatibility for an RE cloning strategy.

    Checks whether the insert will be in-frame with the vector's N-terminal
    and C-terminal tags after ligation.

    Args:
        vector_name: Vector name (e.g. "pET-28a(+)").
        re_5prime: 5' restriction enzyme name.
        re_3prime: 3' restriction enzyme name.
        insert_has_atg: Whether the insert has its own start codon (default True).
        insert_has_stop: Whether the insert has its own stop codon (default False).
        insert_cds_bp: Insert CDS length in bp (optional, for length validation).

    Returns:
        dict with in_frame_5prime, in_frame_3prime, topology diagram,
        linker sequences, and warnings. Also includes a human-readable
        frame_report string.
    """
    logger.info(
        "check_reading_frame: %s %s/%s",
        vector_name, re_5prime, re_3prime,
    )
    result = check_reading_frame(
        vector_name=vector_name,
        re_5prime=re_5prime,
        re_3prime=re_3prime,
        insert_has_atg=insert_has_atg,
        insert_has_stop=insert_has_stop,
        insert_cds_bp=insert_cds_bp,
    )
    result["frame_report"] = format_frame_report(result)
    return result

