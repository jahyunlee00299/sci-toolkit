#!/usr/bin/env python3
"""
Primer Design MCP Server
=========================
A local MCP server built on FastMCP.
Exposes primer design functionality — RE cloning, colony PCR, expression
analysis, order sheets, etc. — as tools callable directly from Claude Code.

IMPORTANT: uses stdio transport — print() to stdout is absolutely forbidden.
           All logging must go to stderr only.

Layout: this module owns the FastMCP instance and the tool registry (names and
order). The tool bodies live in tool-group modules, each a set of plain
functions that can be called without the MCP transport:

    mcp_cloning_tools.py    design_re_cloning_primers, recommend_re_pair,
                            suggest_colony_pcr, check_reading_frame_tool
    mcp_analysis_tools.py   analyze_expression, list_vectors,
                            list_restriction_enzymes, generate_macrogen_order
    mcp_gene_tools.py       fetch_gene_sequence (+ NCBI helpers)
    expression_viability.py construct viability check used by the design tool
    _mcp_common.py         stderr logging + shared designer singletons

Every name the single-file server exposed is re-exported here, so
`from primer_design.mcp_server import fetch_gene_sequence` keeps working.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ._mcp_common import (  # noqa: F401  (re-exported)
    _colony_designer,
    _expression_analyzer,
    _re_designer,
    logger,
)
from .expression_viability import (  # noqa: F401  (re-exported)
    _VECTOR_EXPRESSION_INFO,
    _check_expression_viability,
    _get_vector_expression_context,
)
from .mcp_analysis_tools import (
    analyze_expression,
    generate_macrogen_order,
    list_restriction_enzymes,
    list_vectors,
)
from .mcp_cloning_tools import (
    check_reading_frame_tool,
    design_re_cloning_primers,
    recommend_re_pair,
    suggest_colony_pcr,
)
from .mcp_gene_tools import (  # noqa: F401  (private helpers re-exported)
    _ECOLI_BEST_CODON,
    _codon_optimize_for_ecoli,
    _fetch_cds_from_gene_id,
    _search_ncbi_gene,
    fetch_gene_sequence,
)

# ── FastMCP Server ────────────────────────────────────────────────────────────

mcp = FastMCP("primer-design")

# Registration order = the order clients see in the tool list.
for _tool in (
    design_re_cloning_primers,
    recommend_re_pair,
    suggest_colony_pcr,
    analyze_expression,
    check_reading_frame_tool,
    list_vectors,
    list_restriction_enzymes,
    generate_macrogen_order,
    fetch_gene_sequence,
):
    mcp.tool()(_tool)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("Starting primer-design MCP server (stdio transport)")
    mcp.run()
