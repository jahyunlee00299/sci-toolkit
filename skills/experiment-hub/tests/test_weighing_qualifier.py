"""The Pipetting Guide must not drop a note's qualifier on HOW a solid is weighed.

`pipette_count.weighings()` keeps only (tube, NAME, mg) out of a condition note, and the Guide line then
asserted "one per tube". For a 5 mM solid in 100 uL that is 0.068 mg -- 0.68 of a division on a 0.1 mg
balance -- and the note for the same tube said to weigh the three replicates as ONE group. Guide and
Reaction Matrix contradicted each other, and the Guide is what the operator mixes from.
"""
import copy
import json
import sys
from pathlib import Path

import openpyxl

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import pipette_count as pc  # noqa: E402
import reaction_matrix as rm  # noqa: E402

CFG = json.loads((HERE / "fixtures" / "pipette_rules" / "synthetic_serial_x8.json").read_text(encoding="utf-8"))
GROUP = ("TOO SMALL to weigh per tube on a 0.1 mg balance: weigh the 3 replicates as ONE group "
         "(0.236 mg into 350 uL of the dispensed mix).")


def _with_notes(group_tubes=(1, 2)):
    cfg = copy.deepcopy(CFG)
    for cond in cfg["conditions"]:
        mM, mg = (5, 0.068) if cond["num"] in group_tubes else (25, 0.338)
        cond["note"] = f"SolidT {mM} mM = {mg} mg solid per tube, weighed FIRST into the empty tube."
        if cond["num"] in group_tubes:
            cond["note"] += " " + GROUP
    return cfg


def _guide_text(cfg, tmp_path):
    out = tmp_path / "w.xlsx"
    rm.generate_excel(pc.normalize(cfg), str(out))
    ws = openpyxl.load_workbook(out)["Pipetting Guide"]
    return [str(c.value) for row in ws.iter_rows() for c in row if c.value]


def test_group_weighing_qualifier_reaches_the_guide(tmp_path):
    cells = _guide_text(_with_notes(), tmp_path)
    assert any("0.068 mg" in c for c in cells), "per-tube masses still listed"
    qual = [c for c in cells if "ONE group" in c]
    assert qual, "the group-weighing sentence was dropped from the Pipetting Guide"
    assert "#1" in qual[0] and "#2" in qual[0], qual[0]        # carries the tubes it applies to
    assert "350 uL" in qual[0]


def test_guide_does_not_claim_per_tube_unconditionally(tmp_path):
    cells = _guide_text(_with_notes(), tmp_path)
    head = [c for c in cells if c.startswith("Weigh first")]
    assert head and "one per tube (solid" not in head[0], head


def test_no_qualifier_line_when_no_note_qualifies(tmp_path):
    cells = _guide_text(_with_notes(group_tubes=()), tmp_path)
    assert any("0.338 mg" in c for c in cells)
    assert not [c for c in cells if "ONE group" in c]
