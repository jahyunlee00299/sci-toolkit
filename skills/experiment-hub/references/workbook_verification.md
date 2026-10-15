# Pipetting workbook verification (win32com-hang-safe)

Moved out of SKILL.md to keep SKILL.md under the size cap; SKILL.md keeps the summary.
Paths like `tests/...` are relative to the skill folder.

For repeated validation/editing of pipetting-protocol xlsx files (e.g. one
numbered workbook series), do NOT re-open Excel via win32com for every check — a COM
call that hits a modal dialog blocks forever with no in-process timeout
(measured: 44+ min Not-Responding, required manual taskkill, which also
rolled the file back to its last save). Use the two-stage split instead:

1. **Pure-calculation checks** (`pipetting_checks.py`) — volume closure,
   concentration re-derivation, sampling headroom, and the leading-`=`
   text-cell guard. openpyxl only, no Excel opened, works on any platform.
2. **Final COM pass** (`excel_com_guard.py`, Windows only) — exactly one
   Excel-COM round trip (full recalculation + error-cell scan), run in a
   child process under an external `subprocess` timeout so a modal-dialog
   hang is force-killed instead of freezing the session.

Driver CLI: `verify_pipetting_workbook.py CONFIG.json [--recalc] [--timeout SEC]`
— runs stage 1 always, stage 2 only with `--recalc`. See that file's
docstring for the CONFIG.json shape. Tests: `tests/test_pipetting_checks.py`,
`tests/test_excel_com_guard.py` (`python -m pytest tests/ -v`).

For general xlsx formula recalculation outside this pipetting-specific use
case (LibreOffice-based, cross-platform, no COM), use `Skill(xlsx)`'s
recalc script instead — this module's COM path exists specifically
because the pipetting workbooks are edited live in Windows Excel and need
Excel's own calculation engine, not LibreOffice's.

## Four rules for editing a pipetting workbook

🔴 Measured on one workbook series: three consecutive "verification passed" reports were all false, and an
independent reviewer refuted each one. The failure was the same every time — **the fix was confirmed by the
action taken, not by the result produced.** Self-review by the same reasoning that wrote the bug does not catch it.

**1. Change the input, then prove a downstream cell moved.** Setting a scale cell to 36 and logging "fixed" meant
nothing: no formula referenced that cell, and the volumes below it were still `=ROUND(D7*13,2)`. The sheet then
actively mis-instructed, because a note told the reader to change a cell that drives nothing. After any parameter
edit, **copy the file, change the parameter again, recalculate, and check the dependent totals followed.** An
n=3 → n=4 → n=5 sweep is the standard form of this test.

**2. An openpyxl save voids every prior COM-recalculation claim.** `wb.save()` strips `calcChain.xml` and empties
every cached `<v>`. A "COM recalculation: 0 errors" line written before a later openpyxl save is simply false, and
every openpyxl-based check downstream then reads `None`. Fixed order: **edit → copy to the final location → COM
recalculate → verify → and do NOT kill Excel afterwards.** `excel_com_guard.py` does call `wb.Save()`, but a
forced kill of Excel issued in the same breath truncates the flush (measured: the file shrank by about a quarter,
with zero caches).

**3. Never write a note into a cell as text starting with `=`.** openpyxl stores it as a FORMULA.
`= 100/1000 x 50e-3 x 112.09` made a workbook refuse to open entirely (`x` is not an operator; spaces are
intersection operators), and it passed `leading_equals_guard` with 0 findings because that guard looks for the
opposite defect. Put the unit note in the Note column, or prefix the string with `'`.

**4. Distinguish the record from the working copy, and back up the record.** The verified artefact is the one Excel
recalculated (calcChain present, caches filled); a scratch twin with identical cells is not interchangeable with it.
Name backups after the verified file's md5 (`..._VERIFIED-YYMMDD-<md5>.xlsx`) — a backup taken from the working
copy rolls back to the unverified state.

## Structural guards in `pipetting_checks.py`

Run them **before** the numeric checks — `volume_closure_check` reports "uncomputed formula cell(s) — run a COM
recalc first" when caches are empty, which is a confusing proxy for "nobody recalculated";
`cache_freshness_guard` says that directly.

```
cache_freshness_guard → formula_validity_guard → constant_formula_guard →
dead_input_cell_guard → volume_closure_check → concentration_rederivation_check →
sampling_headroom_check
```

| Guard | Catches | Severity |
| --- | --- | --- |
| `cache_freshness_guard` | nobody recalculated (missing calcChain / empty caches) | blocking |
| `formula_validity_guard` | a note saved as a formula; non-operator tokens | blocking |
| `constant_formula_guard` | `'=9'`, `'=27'` — a constant disguised as a formula | blocking |
| `dead_input_cell_guard` | a labelled input cell no formula references | advisory |

`leading_equals_guard` and `formula_validity_guard`/`constant_formula_guard` are a **pair**: the first finds text
that looks like a formula, the others find a formula where text or a constant belonged. Each is blind to the
other's case. Tests: `tests/test_structural_guards.py`.

🔴 Do not try to catch this defect class with a regex over formula text. Two attempts did: one matched `=` plus
`' x '` and missed `'=9'`; the next matched formula text and produced 23 false positives on perfectly good
formulas. All of these are structural properties — check structure. A magic-number guard was prototyped and
deliberately NOT added: it fires dozens of times on a workbook whose literals have not been parameterised yet, so it
is noise until that is done.
