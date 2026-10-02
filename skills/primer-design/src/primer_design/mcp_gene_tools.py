"""MCP tool and NCBI helpers for fetching a gene's CDS (fetch_gene_sequence).

Network access goes through Bio.Entrez only; tests replace those calls with a
scripted fake. Plain callables; `mcp_server` registers the tool.
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET

from ._mcp_common import logger

# ── E. coli K12 codon usage (best codon per amino acid) ──────────────────────

_ECOLI_BEST_CODON: dict[str, str] = {
    "F": "TTC", "L": "CTG", "I": "ATT", "M": "ATG", "V": "GTG",
    "S": "AGC", "P": "CCG", "T": "ACC", "A": "GCG", "Y": "TAC",
    "H": "CAC", "Q": "CAG", "N": "AAC", "K": "AAA", "D": "GAT",
    "E": "GAA", "C": "TGC", "W": "TGG", "R": "CGC", "G": "GGC",
    "*": "TAA",
}


def _codon_optimize_for_ecoli(protein_seq: str) -> str:
    """Back-translate protein to DNA using E. coli K12 optimal codons."""
    codons = []
    for aa in protein_seq.upper():
        best = _ECOLI_BEST_CODON.get(aa)
        if best is None:
            raise ValueError(f"Unknown amino acid: '{aa}'")
        codons.append(best)
    return "".join(codons)


def _search_ncbi_gene(gene_name: str, organism: str) -> int | None:
    """Search NCBI Gene database and return Gene ID."""
    from Bio import Entrez

    queries = [
        f'{gene_name}[Gene Name] AND "{organism}"[Organism]',
        f'{gene_name}[All Fields] AND "{organism}"[Organism]',
    ]
    for query in queries:
        logger.info("NCBI Gene search: %s", query)
        try:
            handle = Entrez.esearch(db="gene", term=query, retmax=5)
            record = Entrez.read(handle)
            handle.close()
        except Exception as exc:
            logger.warning("Entrez esearch failed: %s", exc)
            time.sleep(0.5)
            continue

        id_list = record.get("IdList", [])
        if id_list:
            gene_id = int(id_list[0])
            logger.info("Found Gene ID: %d (%d results)", gene_id, len(id_list))
            return gene_id
        time.sleep(0.4)
    return None


def _fetch_gene_summary(gene_id: int) -> tuple[str, str]:
    """(official locus name, description) from the Gene XML; blanks when unparsable."""
    from Bio import Entrez

    logger.info("Fetching Gene summary for ID %d", gene_id)
    official_name = ""
    description = ""
    try:
        handle = Entrez.efetch(db="gene", id=str(gene_id), rettype="xml")
        xml_data = handle.read()
        handle.close()
        root = ET.fromstring(xml_data)
        for el in root.iter("Gene-ref_locus"):
            official_name = el.text or ""
            break
        for el in root.iter("Gene-ref_desc"):
            description = el.text or ""
            break
    except Exception as exc:
        logger.warning("Gene XML parse: %s", exc)
    time.sleep(0.4)
    return official_name, description


def _link_gene_to_nucleotides(gene_id: int) -> list[str]:
    """Link Gene -> Nucleotide (RefSeq); first link type that yields ids wins."""
    from Bio import Entrez

    nuc_ids: list[str] = []
    for link_name in ("gene_nuccore_refseqrna", "gene_nuccore_refseqgene", "gene_nuccore"):
        try:
            handle = Entrez.elink(dbfrom="gene", db="nuccore", id=str(gene_id), linkname=link_name)
            link_results = Entrez.read(handle)
            handle.close()
        except Exception as exc:
            logger.warning("Elink %s failed: %s", link_name, exc)
            time.sleep(0.4)
            continue

        for linkset in link_results:
            for link_db in linkset.get("LinkSetDb", []):
                for link in link_db.get("Link", []):
                    nuc_ids.append(link["Id"])
        if nuc_ids:
            logger.info("Found %d nucleotide IDs via %s", len(nuc_ids), link_name)
            break
        time.sleep(0.4)
    return nuc_ids


def _cds_info_from_feature(feature, record, official_name: str, description: str) -> dict | None:
    """Describe a GenBank CDS feature, or None when it is not a usable CDS.

    Usable = starts with ATG/GTG/TTG (alternative starts are common in
    prokaryotes), length a multiple of 3, and a translation (stored or computed).
    """
    feat_gene = feature.qualifiers.get("gene", [""])[0]
    feat_locus = feature.qualifiers.get("locus_tag", [""])[0]
    cds_seq = str(feature.location.extract(record.seq)).upper()

    if cds_seq[:3] not in ("ATG", "GTG", "TTG") or len(cds_seq) % 3 != 0:
        return None

    protein = feature.qualifiers.get("translation", [None])[0]
    if protein is None:
        try:
            protein = str(feature.location.extract(record.seq).translate(to_stop=True))
        except Exception:
            return None

    product = feature.qualifiers.get("product", [""])[0]
    accession = record.id or record.name
    return {
        "cds_seq": cds_seq,
        "protein_seq": protein,
        "source": accession,
        "description": product or description,
        "gene_name_official": feat_gene or official_name,
        "locus_tag": feat_locus,
    }


def _fetch_cds_from_gene_id(gene_id: int, gene_name_hint: str = "") -> dict | None:
    """Fetch CDS nucleotide sequence from NCBI Gene ID."""
    from Bio import Entrez, SeqIO

    official_name, description = _fetch_gene_summary(gene_id)
    nuc_ids = _link_gene_to_nucleotides(gene_id)
    if not nuc_ids:
        logger.warning("No linked nucleotide records for Gene %d", gene_id)
        return None

    # Target names for case-insensitive matching
    target_names: set[str] = set()
    if official_name:
        target_names.add(official_name.lower())
    if gene_name_hint:
        target_names.add(gene_name_hint.lower())

    def _matches_gene(feat_gene: str, feat_locus: str) -> bool:
        """Check if CDS gene/locus_tag matches any target name."""
        if not target_names:
            return False
        return (feat_gene.lower() in target_names
                or feat_locus.lower() in target_names)

    fallback_cds = None  # first valid CDS; only reported, never returned (wrong-gene guard)

    for nuc_id in nuc_ids[:10]:
        time.sleep(0.4)
        try:
            handle = Entrez.efetch(db="nuccore", id=nuc_id, rettype="gb", retmode="text")
            record = SeqIO.read(handle, "genbank")
            handle.close()
        except Exception as exc:
            logger.warning("Nucleotide fetch %s failed: %s", nuc_id, exc)
            continue

        for feature in record.features:
            if feature.type != "CDS":
                continue
            cds_info = _cds_info_from_feature(feature, record, official_name, description)
            if cds_info is None:
                continue
            feat_gene = feature.qualifiers.get("gene", [""])[0]
            feat_locus = feature.qualifiers.get("locus_tag", [""])[0]
            cds_seq, protein = cds_info["cds_seq"], cds_info["protein_seq"]

            # Gene name matching: compare against the gene qualifier or locus_tag
            if _matches_gene(feat_gene, feat_locus):
                logger.info(
                    "Matched CDS by gene/locus '%s'/'%s': %d bp, %d aa",
                    feat_gene, feat_locus, len(cds_seq), len(protein),
                )
                return cds_info

            # Single-CDS record (mRNA/RefSeq) -> use it regardless of gene name
            cds_count = sum(1 for f in record.features if f.type == "CDS")
            if cds_count == 1:
                logger.info(
                    "Single-CDS record: gene=%s, %d bp, %d aa",
                    feat_gene or feat_locus, len(cds_seq), len(protein),
                )
                return cds_info

            if fallback_cds is None:
                fallback_cds = cds_info

    # Do not fall back to it when gene-name matching fails (prevents returning the wrong gene)
    if fallback_cds:
        logger.warning(
            "No CDS matched gene name(s) %s; discarding fallback '%s'",
            target_names, fallback_cds.get("gene_name_official"),
        )
    return None


def _gene_result(cds_result: dict, cds_seq: str, protein_seq: str, gene_name: str,
                 organism: str, gene_id: int, codon_optimize: bool) -> dict:
    """The fetch_gene_sequence success payload."""
    native_start = cds_result["cds_seq"][:3]
    start_codon_note = ""
    if native_start != "ATG":
        start_codon_note = (
            f"Native start codon is {native_start} (not ATG). "
            f"For recombinant expression, the RE cloning primer will "
            f"replace it with ATG automatically."
        )

    result = {
        "gene_name": cds_result.get("gene_name_official") or gene_name,
        "organism": organism,
        "gene_id": gene_id,
        "cds_seq": cds_seq,
        "protein_seq": protein_seq,
        "cds_length_bp": len(cds_seq),
        "protein_length_aa": len(protein_seq),
        "source": cds_result["source"],
        "description": cds_result["description"],
        "codon_optimized": codon_optimize,
        "native_start_codon": native_start,
    }
    if start_codon_note:
        result["start_codon_note"] = start_codon_note
    if cds_result.get("locus_tag"):
        result["locus_tag"] = cds_result["locus_tag"]
    return result


def fetch_gene_sequence(
    gene_name: str,
    organism: str = "Escherichia coli",
    gene_id: int | None = None,
    codon_optimize: bool = False,
) -> dict:
    """Fetch a gene's CDS nucleotide sequence from NCBI for primer design.

    Searches the NCBI Gene database, retrieves the CDS (ATG to stop),
    and returns DNA/protein sequences ready for design_re_cloning_primers.

    Default: returns the native genomic sequence (for gDNA PCR).
    Only back-translates using E. coli K12-optimal codons when codon_optimize=True.

    Args:
        gene_name: Gene name or symbol (e.g. "gudD", "lacZ", "malE").
        organism: Organism name for NCBI search (default "Escherichia coli").
        gene_id: Optional NCBI Gene ID. If provided, skips search step.
        codon_optimize: Back-translate using E. coli K12 optimal codons
            (default False). Only enable when explicitly requested.

    Returns:
        dict with gene_name, organism, gene_id, cds_seq, protein_seq,
        cds_length_bp, protein_length_aa, source, description.
    """
    import os as _os
    from Bio import Entrez
    Entrez.email = _os.environ.get("NCBI_ENTREZ_EMAIL", "your-email@example.com")
    Entrez.tool = "primer-design-mcp"

    logger.info(
        "fetch_gene_sequence: gene=%s, organism=%s, gene_id=%s, optimize=%s",
        gene_name, organism, gene_id, codon_optimize,
    )

    # Step 1: Resolve Gene ID
    if gene_id is None:
        gene_id = _search_ncbi_gene(gene_name, organism)
        if gene_id is None:
            return {
                "error": f"Gene '{gene_name}' not found for '{organism}'. "
                         f"Try a different name or provide gene_id directly.",
                "gene_name": gene_name,
                "organism": organism,
            }

    # Step 2: Fetch CDS
    try:
        cds_result = _fetch_cds_from_gene_id(gene_id, gene_name_hint=gene_name)
    except Exception as exc:
        return {
            "error": f"Failed to fetch CDS for Gene ID {gene_id}: {exc}",
            "gene_name": gene_name, "gene_id": gene_id,
        }

    if cds_result is None:
        return {
            "error": f"No valid CDS for Gene ID {gene_id} ('{gene_name}'). "
                     f"Provide the sequence directly.",
            "gene_name": gene_name, "gene_id": gene_id,
        }

    cds_seq = cds_result["cds_seq"]
    protein_seq = cds_result["protein_seq"]

    # Step 3: Codon optimization (optional, only when explicitly requested)
    if codon_optimize:
        logger.info("Codon-optimizing %d aa for E. coli K12", len(protein_seq))
        try:
            optimized = _codon_optimize_for_ecoli(protein_seq)
            if cds_seq[-3:] in ("TAA", "TAG", "TGA"):
                optimized += _ECOLI_BEST_CODON["*"]
            cds_seq = optimized
        except Exception as exc:
            return {
                "error": f"Codon optimization failed: {exc}",
                "gene_name": gene_name, "gene_id": gene_id,
                "native_cds_seq": cds_result["cds_seq"],
                "protein_seq": protein_seq,
            }

    result = _gene_result(cds_result, cds_seq, protein_seq, gene_name, organism,
                          gene_id, codon_optimize)
    logger.info(
        "fetch_gene_sequence OK: %s, %d bp, %d aa, source=%s",
        result["gene_name"], len(cds_seq), len(protein_seq), result["source"],
    )
    return result
