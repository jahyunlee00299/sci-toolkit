"""Regenerate tests/golden/re_pair.json (only for an INTENDED, reviewed change).

    python skills/primer-design/tests/golden/regen_re_pair_golden.py

A pure refactor must never need this: the golden file was produced from the
unsplit recommend_re_pair and stays byte-identical.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import characterization_re_pair as cre  # noqa: E402

if __name__ == "__main__":
    data = cre.build_all()
    with open(HERE / "re_pair.json", "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    print("wrote re_pair.json")
