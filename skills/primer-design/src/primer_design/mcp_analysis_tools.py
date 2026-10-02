"""MCP tool functions for analysis, catalogues and order sheets.

analyze_expression, list_vectors, list_restriction_enzymes and
generate_macrogen_order. Plain callables; `mcp_server` registers them.
"""

from __future__ import annotations

from pathlib import Path

from ._mcp_common import _expression_analyzer, logger
from .order_sheet import PrimerOrderSheet
from .vector_registry import EXPRESSION_VECTORS, RESTRICTION_ENZYMES


def analyze_expression(cds_seq: str) -> dict:
    """Analyze a CDS sequence for E. coli expression optimization.

    Performs comprehensive analysis including:
    - Protein info (length, MW, GC content)
    - Rare codon frequency and cluster detection (E. coli K12)
    - CAI (Codon Adaptation Index)
    - Signal peptide prediction (rule-based)
    - MAP (Met aminopeptidase) removal prediction
    - Expression strain recommendation (BL21/Rosetta/Rosetta 2)

    Args:
        cds_seq: CDS DNA sequence (ATG to stop codon, inclusive).

    Returns:
        dict with basic_info, rare_codons, cai, signal_peptide,
        strain_recommendation, and warnings.
    """
    logger.info(
        "analyze_expression: cds=%d bp",
        len(cds_seq.replace(" ", "").replace("\n", "")),
    )
    return _expression_analyzer.analyze(cds_seq=cds_seq)


def list_vectors() -> list[dict]:
    """List all available expression vectors and their RE sites.

    Returns:
        List of vectors, each with name, RE sites, tag info, and aliases.
    """
    vectors = []
    for name, data in EXPRESSION_VECTORS.items():
        tags = {}
        for tag_name, tag_info in data.get("tags", {}).items():
            tags[tag_name] = tag_info["type"]

        vectors.append({
            "name": name,
            "re_sites": list(data["re_sites"].keys()),
            "tags": tags,
            "aliases": data.get("aliases", []),
            "notes": data.get("notes", ""),
        })
    return vectors


def list_restriction_enzymes() -> list[dict]:
    """List all available restriction enzymes with recognition sites and cut info.

    Returns:
        List of enzymes, each with name, recognition site, overhang type,
        overhang length, and cut positions.
    """
    enzymes = []
    for name, info in sorted(RESTRICTION_ENZYMES.items()):
        enzymes.append({
            "name": name,
            "recognition": info["recognition"],
            "overhang": info["overhang"],
            "overhang_len": info["overhang_len"],
            "cut_top": info["cut_top"],
            "cut_bottom": info["cut_bottom"],
        })
    return enzymes


def generate_macrogen_order(
    primers: list[dict],
    project_name: str = "primer_order",
    output_dir: str | None = None,
) -> dict:
    """Generate a Macrogen-compatible primer order sheet (XLSX).

    Creates an XLSX file with Macrogen Oligo Order format
    (No., Oligo Name, Sequence, Amount, Purification).

    Args:
        primers: List of primer dicts, each with "name" (str) and "sequence" (str).
            Example: [{"name": "gudD_BamHI_F", "sequence": "GCGCGGATCC..."}]
        project_name: Project name for the output file (default "primer_order").
        output_dir: Output directory path. Defaults to current working directory.

    Returns:
        dict with the generated file path and order summary.
    """
    logger.info(
        "generate_macrogen_order: %d primers, project=%s",
        len(primers), project_name,
    )
    sheet = PrimerOrderSheet(project_name=project_name)

    for p in primers:
        sheet.add_custom_primer(
            name=p["name"],
            sequence=p["sequence"],
        )

    out_dir = Path(output_dir) if output_dir else Path.cwd()
    xlsx_path = sheet.to_macrogen_oligo(output_path=None)

    # If output_dir specified, move to that directory
    if output_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / xlsx_path.name
        xlsx_path.rename(target)
        xlsx_path = target

    summary = sheet.summary()

    return {
        "file_path": str(xlsx_path),
        "total_primers": summary["total_primers"],
        "total_length_nt": summary["total_length_nt"],
        "estimated_cost_krw": summary["estimated_cost_krw"],
    }

