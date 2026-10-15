# Workbook generation: hand-built designs and publishing

Moved out of SKILL.md (Mode 1a) to keep SKILL.md under the size cap; SKILL.md keeps the summary.

## Design outside the config shape

**When the design does not fit `reaction_matrix.py`'s config shape** (e.g., a saturated-stock-blend
design like splitting a common mix into "additive-saturated" and "plain" halves and recombining at
different ratios — `reaction_matrix.py` has no concept of that) — hand-building formulas is still
sometimes necessary, but the same three checks are then **mandatory to run manually** in a
throwaway Python script before presenting the workbook as done: read every literal Params value
with openpyxl, independently recompute (in plain Python, not by re-reading the formula string) what
every derived cell *should* evaluate to, and diff against what the workbook's formula claims. Do not
declare a hand-built pipetting workbook finished on the strength of "the formula looks right" —
that is exactly the self-review that missed that bug. For anything that will actually be
pipetted at the bench (not just discussed), additionally have it checked independently (a labmate, or a fresh agent session given only
the config and the workbook) — self-review by the same reasoning that produced the bug does not
reliably catch that bug.

## Publishing

**Publishing (optional, per computer)**: if a Methods folder is configured (env `LAB_METHODS_DIR`, or
`"methods_dir_glob"` relative to the home folder in `~/.config/experiment-hub.json`, e.g.
`"OneDrive*/Lab/Methods"`), `reaction_matrix.py` copies every generated workbook there right after generation; a
different file of the same name is kept as `NAME.BACKUP-YYMMDD-HHMM.xlsx` first. Nothing configured = skipped
with a note; configured but missing or the copy does not match = exit 3 (NOT published, say so). `--no-publish`
skips it for scratch runs; the tests point `LAB_METHODS_DIR` at a temporary folder (`tests/conftest.py`).
