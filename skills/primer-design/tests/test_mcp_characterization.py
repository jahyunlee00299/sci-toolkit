"""Golden tests for the primer-design MCP server (split in refactor batch 3).

tests/characterization_mcp.py drives every tool function directly (no MCP
transport, no network) and dumps the registered tool list with its JSON schemas.
The golden file was produced from the unsplit 1073-line mcp_server.py, so a
behaviour-preserving split leaves it untouched. A changed tool name, argument,
schema, description or returned value fails here.
"""
import json

import pytest

import characterization_mcp as chm

pytest.importorskip("mcp.server.fastmcp")

from primer_design import mcp_server  # noqa: E402

GOLDEN = json.loads((chm.GOLDEN / "mcp_server.json").read_text(encoding="utf-8"))


def test_registered_tools_and_schemas_unchanged():
    assert chm.tool_registry(mcp_server) == GOLDEN["tools"]


def test_registered_tool_order_unchanged():
    assert chm.tool_order(mcp_server) == GOLDEN["order"]


@pytest.fixture(scope="module")
def snapshot(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    try:
        yield chm.snapshot_tools(mcp_server, tmp_path_factory.mktemp("mcp"), mp)
    finally:
        mp.undo()


@pytest.mark.parametrize("group", sorted(GOLDEN["outputs"]))
def test_tool_outputs_match_golden(snapshot, group):
    actual = json.loads(json.dumps(snapshot[group], sort_keys=True, ensure_ascii=False, default=str))
    assert actual == GOLDEN["outputs"][group], f"{group} drifted from the golden snapshot"


def test_tool_functions_remain_importable_from_mcp_server():
    """stress_test_genes.py and callers import tool functions from this module."""
    for name in GOLDEN["order"] + ["_check_expression_viability", "_get_vector_expression_context",
                                   "_codon_optimize_for_ecoli", "_search_ncbi_gene",
                                   "_fetch_cds_from_gene_id", "mcp", "logger"]:
        assert hasattr(mcp_server, name), name
