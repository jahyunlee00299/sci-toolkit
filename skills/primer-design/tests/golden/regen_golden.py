"""Regenerate the golden snapshots used by tests/test_characterization.py.

Run only when a behaviour change is INTENDED and reviewed:

    python skills/primer-design/tests/golden/regen_golden.py

A pure refactor must never need this: the whole point of the golden files is that
they were produced from the code before the split and stay byte-identical.
"""
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import characterization as ch  # noqa: E402


def _write(name: str, data) -> None:
    # newline="\n": the repo stores LF; the Windows default would write CRLF.
    with open(HERE / name, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    print("wrote", name)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _write("order_sheet.json", ch.snapshot_order_sheet(tmp))
        _write("construct_maps.json", ch.snapshot_construct_maps(tmp))
    _write("restriction_design.json", ch.snapshot_designs())
