"""Regenerate tests/golden/detect_resources.json (only for an INTENDED, reviewed change).

    python skills/get-available-resources/tests/golden/regen_golden.py

A pure refactor must never need this: the golden file was produced from the
unsplit detect_resources.py and stays byte-identical.
"""
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import pytest  # noqa: E402

import host_probe_snapshots as hps  # noqa: E402

if __name__ == "__main__":
    mp = pytest.MonkeyPatch()
    try:
        with tempfile.TemporaryDirectory() as td:
            data = hps.build_all(mp, Path(td))
    finally:
        mp.undo()
    with open(HERE / "detect_resources.json", "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    print("wrote detect_resources.json")
