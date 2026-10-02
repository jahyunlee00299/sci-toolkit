---
name: experiment-hub
description: Integrated skill for experiment protocol management, condition optimization, experiment proposal, history recording, experiment comparison, and pipetting/reaction-matrix workbook generation (stock/final/volume calculations, master-mix grouping, sampling & dead-volume checks). Use when planning, recording, or reviewing lab experiments, or generating a pipetting sheet / reaction matrix / 파이펫팅 시트. For analyzing data from completed experiments use lab-data-analysis; for statistical testing of results use stats-workflow; for primer/cloning design use primer-design.
license: MIT
---

# Experiment Hub

Records (protocol versions, run logs, discussion, decisions) are kept by `lab-record` — this skill designs and analyses; `lab-record` stores and links. Citation style: APA 7th with DOI (see lab-record §Citations).

Integrated skill for experiment protocol management, condition optimization, experiment proposal, history recording, data visualization, pattern analysis, and experiment comparison.

## Mode Detection -> Execution

Determine the mode from the user request and execute the corresponding procedure.

| Mode | Trigger Example | Core Procedure |
|------|----------|----------|
| **1. Protocol** | "Create a protocol" | Confirm purpose -> Search method references (auto-call research-search) -> Write template -> Enter conditions |
| **2. Optimization** | "How to increase conversion rate?" | Current data -> Select objective/variables -> Choose strategy (OFAT/DoE/RSM) -> Generate experiment matrix |
| **3. Proposal** | "What should I do next?" | Gap analysis -> Literature reference -> Prioritized experiment proposals -> Link to Mode 1 upon acceptance |
| **4. Record** | "Record the results" | Structure conditions/results -> Detect outliers -> If same protocol exists, propose comparison |
| **5. Visualization** | "Draw a graph" | Data -> generate graph / Image -> extract data + auto-fit trendline |
| **6. Pattern Analysis** | "Why these results?" | Variable-result mapping -> Pattern classification -> Quantitative trendline analysis -> Per-variable interpretation -> Causality assessment |
| **7. Comparison** | "Compare with previous experiment" | Identify changed variables -> Result comparison table -> Calculate delta values -> Trend graph -> Analyze cause of difference |
| **10. Reaction Matrix** | "Generate a pipetting sheet/workbook", "reaction matrix 만들어줘", multi-condition stock/final/volume table needed | Config JSON (stocks+enzymes+conditions+sampling+timepoints) -> `reaction_matrix.py` -> `validate_config()` (volume closure + concentration + sampling/dead-volume, blocks on FAIL) -> 4-sheet xlsx (Reaction Matrix, Pipetting Guide, Sampling & Fed, Data). See Mode 1a below — this is the default path for ANY pipetting-calculation workbook; do not hand-write openpyxl formulas for this. |

**Auto-chain**: Record(4) -> Comparison(7) -> Pattern Analysis(6) -> Visualization(5) -> Optimization(2)

🔴 **260928**: Mode 10 existed as a working script (`reaction_matrix.py`, self-labeled "Mode 10" in its own docstring) but was never added to this table — an agent reading this file top-to-bottom (as the file's own first line instructs) had no way to discover it, and one didn't: a pipetting workbook got hand-built with raw openpyxl instead, which is how the 260928 ~4% concentration bug (see Mode 1a) got in. Numbering gap (8, 9 unused) kept as-is rather than renumbered, since renumbering risks breaking any other doc/reference to "Mode 10" that already exists elsewhere (e.g. Asana, other skill files) — not worth the silent-breakage risk to close a cosmetic gap.

> **Branching criteria**: Data/statistics = here (M6/M7), Mechanism/context/literature = lab-record (DISC M1/M2). Mode 1 output is saved as a `lab-record` PROT; Mode 4 output as a `lab-record` EXP.

---

## Mode 1: Protocol -- Auto-search Method References

When writing a protocol, automatically search 3 categories to establish condition rationale:

| Category | Search Target | Applied Items |
|---------|----------|----------|
| Paper methods | Experimental methods from similar reaction papers | Reaction conditions, time, concentration |
| Analytical protocols | HPLC/GC/UV analysis conditions, kit manuals | Mobile phase, column, detection wavelength |
| Manufacturer datasheets | Enzyme/reagent optimal conditions | Optimal temperature/pH, activity units |

- Search results are **suggested defaults**, not forced
- If user selects different conditions, note as "changed from reference"
- Record source in protocol (for future citation)

Protocol format: ID (PROT-{N}), version, reference methods, materials, methods (step-by-step), analysis, safety/disposal, change history.

### Mode 1a: Generating a pipetting-calculation workbook -- mandatory verification (260928)

🔴 **Do not hand-write openpyxl formulas for a multi-component reaction matrix from scratch.** Use
`reaction_matrix.py` (Mode-10-style config JSON -> xlsx) as the default generator for any
protocol whose deliverable includes a stock/final/volume pipetting table. It computes every
component's volume from ONE consistent basis (the declared total reaction volume) and defines DW
as the residual, which makes the "wrong reference volume" bug class structurally impossible.

**Why this exists**: on 260928, a pipetting xlsx was hand-built with openpyxl instead of using this
script. A later "fix" pass for an unrelated issue accidentally changed the reference volume in a
buffer-component formula, silently putting 4 reagents ~4% off target across all 90 planned samples.
It was caught only because someone separately asked for an independent verification pass — not
because anything in this skill checked it. `reaction_matrix.py` now calls `validate_config()`
automatically before writing any file, and refuses to generate (exit 1, no xlsx written) if a hard
check fails — so the class of error that happened is no longer possible to ship silently:

1. **Volume closure** — per condition, recompute every component's volume independently from
   stock/final/total (never trust a cached formula result) and confirm DW (the residual) is not
   negative. A negative DW means the recipe physically cannot fit in the declared reaction volume.
2. **Concentration re-derivation** — independently recompute each achieved concentration from
   stock x volume / total, not read back from the formula that produced it.
3. **Sampling / dead-volume headroom** — given `timepoints` and `sampling.volume_uL` (+ optional
   `sampling.dead_volume_uL`, default = max(10% of total volume, 5 uL)), confirm
   `n_timepoints x aliquot_volume + dead_volume <= total_volume`. This is the check that was
   previously completely missing — `timepoints`/`sampling` were recorded in the output sheet but
   never actually checked against the tube volume, so a design could ask for more sample than the
   tube physically holds and nothing would flag it. Also checks `fed_diagnosis` feeds against the
   source condition's *remaining* volume after its own timepoints (a second, easy-to-miss overdraw
   point).

Run it directly: `python reaction_matrix.py config.json output.xlsx` — validation output
prints before generation; a FAIL blocks the file from being written at all.

**When the design does not fit `reaction_matrix.py`'s config shape** (e.g., a saturated-stock-blend
design like splitting a common mix into "additive-saturated" and "plain" halves and recombining at
different ratios — `reaction_matrix.py` has no concept of that) — hand-building formulas is still
sometimes necessary, but the same three checks are then **mandatory to run manually** in a
throwaway Python script before presenting the workbook as done: read every literal Params value
with openpyxl, independently recompute (in plain Python, not by re-reading the formula string) what
every derived cell *should* evaluate to, and diff against what the workbook's formula claims. Do not
declare a hand-built pipetting workbook finished on the strength of "the formula looks right" —
that is exactly the self-review that missed the 260928 bug. For anything that will actually be
pipetted at the bench (not just discussed), additionally have it checked independently (a labmate, or a fresh agent session given only
the config and the workbook) — self-review by the same reasoning that produced the bug does not
reliably catch that bug.


**Suggested workbook convention**: put every fixed-concentration component (buffer, salts, fixed cofactors) into ONE premix: mark them `"type":"buffer"` in the config, never `cofactor`. Only the varied reagents change per tube; DW is the per-tube residual. Enzymes = one stock-only cocktail (n x 1.2), added LAST in a fixed staggered order; solids weighed per tube go in first. Every downstream formula must reference the total-volume cell, never a literal volume. After editing, recalculate with the timeout-guarded `excel_com_guard.py` (see "Pipetting Workbook Verification" below; never a bare win32com call that can hang on a dialog) and compare with an independent Python calculation.

---

## Mode 2: Optimization Strategy Selection Criteria

| Condition | Strategy |
|------|------|
| 1-2 variables, clear bottleneck | OFAT |
| 3-4 variables, interaction suspected | Full/Fractional Factorial DoE |
| 3+ variables, optimum search | RSM / Central Composite Design |

Output: optimization variables (range/current value), experiment matrix (conditions per run + objective), estimated experiment count/duration.

**DoE mode defers to `doe-and-replication`.** For a factorial / fractional / Plackett-Burman / CCD design, a seeded run table, run-order and 96-well plate randomization, or "how many replicates" (technical vs biological, pseudoreplication), generate the matrix there first; then bring the run table back here for the pipetting workbook (Mode 10). This mode keeps only the OFAT-vs-DoE-vs-RSM choice above.

---

## Mode 5: Trendline Auto-selection Rules

| Data Pattern | Trendline Type |
|------------|-----------|
| Monotone increase/decrease | Linear regression (y = ax + b) |
| Saturation/plateau curve | Nonlinear (Michaelis-Menten etc.) |
| Optimum point exists | Quadratic polynomial |
| Exponential change | Exponential fit |
| Points < 3 or R-squared < 0.5 | No trendline |

Required output: equation, R-squared, key points (maximum/saturation/inflection point).

---

## Mode 6: Pattern Classification Criteria

- **Increase** (positive correlation): linear / diminishing returns
- **Decrease** (negative correlation): linear / threshold collapse
- **Optimum**: left-right symmetric/asymmetric
- **Plateau/Saturation**: saturation reached vs reaction-limited
- **Outlier**: experimental error vs new phenomenon

Causality strength: 5 stars (dose-response + mechanism + reproducibility) to 1 star (insufficient data)

---

## Pipetting Workbook Verification (win32com-hang-safe)

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

## Skill Integration

- Mode 1 protocol -> `lab-record` PROT (`new prot`; method change = new version)
- Mode 4 record -> `lab-record` EXP (`new exp --protocol PROT-xxx@vN`)
- exp:log -> `lab-record` DISC M1 interpretation
- exp:pattern -> `lab-record` DISC M2 comparison
- `lab-record` DEC.next kind protocol -> protocol generation (Mode 1)
- experiment proposal (M3) -> research-search for literature (M1)
- exp:result/viz -> manuscript-pipeline Results/Figure
- ms:revision -> additional experiment protocol (M1) trigger
- cloning/mutagenesis needed -> primer-design (design the primers)
- sequencing result came back, or "is this variant saved anywhere" -> sequence-verification
  (read residues out of the maps, build the expected-sequence reference, check that the
  sequencing primer reaches the mutated position before ordering)

## Biotechnology Experiment Specialization

- **Enzyme reactions**: Substrate preparation -> enzyme addition -> reaction -> sampling -> analysis
- **Multi-enzyme cascade**: Optimal condition matrix per enzyme
- **Whole-cell catalysis**: Includes OD, permeabilization, aeration conditions

## Notes

- Optimization proposals are statistical suggestions; experimental validation is mandatory
- Always note that trendline extrapolation has low reliability
- Graph-to-number extraction is approximate; consulting original data is recommended

User request: $ARGUMENTS
