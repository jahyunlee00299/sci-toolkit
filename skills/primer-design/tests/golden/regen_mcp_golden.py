"""Regenerate tests/golden/mcp_server.json (only for an INTENDED, reviewed change).

    python skills/primer-design/tests/golden/regen_mcp_golden.py

A pure refactor must never need this: the golden file was produced from the
unsplit mcp_server.py and stays byte-identical.
"""
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import characterization_mcp as chm  # noqa: E402


class _MP:
    """Minimal monkeypatch stand-in for use outside pytest."""

    def setattr(self, obj, name, value):
        setattr(obj, name, value)


if __name__ == "__main__":
    from primer_design import mcp_server as mod
    with tempfile.TemporaryDirectory() as td:
        data = {"tools": chm.tool_registry(mod),
                "order": chm.tool_order(mod),
                "outputs": chm.snapshot_tools(mod, Path(td), _MP())}
    with open(HERE / "mcp_server.json", "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    print("wrote mcp_server.json")
