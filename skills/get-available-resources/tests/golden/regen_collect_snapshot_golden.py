"""Regenerate tests/golden/collect_snapshot.json (only for an INTENDED, reviewed change).

    python skills/get-available-resources/tests/golden/regen_collect_snapshot_golden.py

A pure refactor must never need this: the golden file was produced from the
unsplit collect_snapshot and stays byte-identical. It is separate from
regen_golden.py on purpose: that script rewrites detect_resources.json, whose
subprocess and CLI groups depend on the OS the file was generated on.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import pytest  # noqa: E402

import collect_snapshot_trace as cst  # noqa: E402

if __name__ == "__main__":
    mp = pytest.MonkeyPatch()
    try:
        data = cst.build_all(mp)
    finally:
        mp.undo()
    with open(HERE / "collect_snapshot.json", "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    print("wrote collect_snapshot.json")
