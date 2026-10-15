"""Regenerate tests/golden/cloning_report.json (only for an INTENDED, reviewed change).

    python skills/primer-design/tests/golden/regen_report_golden.py

A pure refactor must never need this: the golden file was produced from the
unsplit generate_cloning_report drawing functions and stays byte-identical.
"""
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import characterization_report as chrep  # noqa: E402

if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as td:
        data = chrep.build_all(Path(td))
    with open(HERE / "cloning_report.json", "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    print("wrote cloning_report.json")
