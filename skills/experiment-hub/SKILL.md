---
name: experiment-hub
description: Integrated skill for experiment protocol management, condition optimization, experiment proposal, history recording, experiment comparison, and pipetting/reaction-matrix workbook generation (stock/final/volume calculations, master-mix grouping, sampling & dead-volume checks) and one-off dilution / top-up / C1V1 arithmetic via `reaction_matrix.py calc` (희석배수, 더 넣어야 하는 양). Use when planning, recording, or reviewing lab experiments, or generating a pipetting sheet / reaction matrix / 파이펫팅 시트. For analyzing data from completed experiments use lab-data-analysis; for statistical testing of results use stats-workflow; for primer/cloning design use primer-design.
license: MIT
---

# Experiment Hub

> **HARD RULES - pipetting workbooks (enforced by `reaction_matrix.py validate_config`)**
> Rationale: **accuracy first, step count second** - and a beginner must be able to follow the sheet.
> The tag after each rule names the check that enforces it: `check a`-`f` = the letters in
> `reaction_matrix._check_pipetting_rules`, `check 4` = canon-gate in `validate_config`; `(doc)` = not machine-checked.
>
> - **Pipette limits** (defaults = a lab whose smallest pipette is 2.5 uL). Any single pipetting action below
>   **floor 0.5 uL = FAIL, no xlsx**; 0.5-1.0 uL = WARN (comfort 1.0 uL). Config `"pipettes": {"floor_uL",
>   "comfort_uL", "resolution_uL", "max_settings_per_tube"}`. [check b]
> - **Same volume in every tube, as few distinct volumes as possible.** WARN when a component (incl. the DW
>   top-up) is added at more than one volume across tubes or a tube needs > 4 volume settings; the no-enzyme
>   control gets WATER in place of the enzyme additions (identical volumes, different liquid);
>   `"control_water_in_place": false` -> WARN (that control's single DW top-up is an odd volume). [check d]
> - **Volumes are shown rounded to 0.1 uL** (`pipettes.resolution_uL`); DW re-closes every tube; the
>   concentration deviation from rounding is reported (WARN > 2 %, FAIL > 5 %). [check e]
> - **No DW top-up between 0 and the floor.** Such a top-up cannot be pipetted and is never dropped silently:
>   the common water in MM-A is lowered (by the floor) so every top-up is 0 or >= 0.5 uL and every tube still
>   closes to the total; a rounding residual of the same kind lowers the per-tube MM-A volume in 0.1 uL steps
>   (its buffer deviation is reported by the rounding check). [check e; generator + `pipette_count.py`]
> - **What is checked = what is actually pipetted.** Premix and sub-mix component draws, working-stock draws,
>   per-tube additions. **Cocktail exception:** enzymes pooled into a common cocktail (same level in every enzyme
>   tube, classified by `pipette_count.route_enzymes`) are checked by the cocktail volume per tube and their batch
>   draws, never by their per-tube share; enzymes added individually per tube keep the floor rule. [check b]
> - **MM-A margin** = n tubes + `"premix": {"extra_rxns": N}` (default 3). A larger N (e.g. 5) can put small
>   premix draws on the 0.1 uL grid and remove their rounding WARN. [check e reports the effect]
> - **R1 Common water in MM-A.** The MM-A premix carries the water every tube needs, sized so the tightest
>   tube closes with 0 uL top-up, or lowered by the rule above (`"common_water_in_mm_a": false` -> WARN; SKIP
>   when there is no MM-A). [check f]
> - **R2 Equal-volume working stocks (only where a level varies).** A diluted working stock exists ONLY for an
>   enzyme whose level differs between tubes (1x/2x/4x...). An enzyme held at the SAME level in every enzyme
>   tube goes into the common cocktail straight from its NEAT lab stock: no working stock, no dilution step, and
>   a per-tube share below the 2.5 uL pipette is fine because the cocktail volume per tube and the pooled batch
>   draws are what get pipetted and checked (do not put `equal_volume_uL` on such an enzyme). For the enzymes that
>   DO vary: **dilute with WATER**, not storage buffer - and every tube gets the SAME volume of its level's stock. One
>   physical enzyme at more than one volume = **FAIL** (0.5 % / 0.005 uL tolerance). "One physical enzyme" =
>   same `enzyme` alias, or same batch + same lab stock (`source_stock_gL`, else `stock_gL` x `dilution_x`), or
>   same batch + same name stem (`EnzX` / `EnzX_dil`); batch labels are compared stripped, case-folded, and
>   with `100001` == `"100001"`. Config `"equal_volume_uL"`; `reaction_matrix.py` expands such a spec itself. [check c]
> - **R2b Levels are made by SERIAL dilution (default).** Make the HIGHEST level once from lab stock + water, then each
>   lower level = a transfer from the next higher one + water, so no transfer is a tiny lab-stock draw. Make volumes
>   are computed bottom-up (what the tubes of that level draw + the transfer for the next lower level + dead volume);
>   every transfer and lab-stock draw should be >= 2.5 uL. Config `"serial_dilution"`: omitted or `"auto"` = every
>   enzyme with >= 2 working-stock levels; a list of enzyme names limits it to those; `[]` = independent draws.
>   Typo = WARN, wrong type = FAIL, a draw < 2.5 uL = WARN, < 0.5 uL = FAIL, a non-2-fold step = INFO. The recipe is
>   written into the Pipetting Guide blocks 'TUBES TO PREPARE' and 'ENZYME PREPARATION' (A lab stocks with batch and
>   total draw, B common cocktail, C working-stock / serial levels); `Enzyme Additions` marks the superseded
>   independent-draw rows. Known gap: `pipette_count` still prices independent draws, so its enzyme lab-stock total
>   differs slightly from the serial recipe; the Guide block is the bench truth.
> - **Surplus margins (lab convention).** No percentage overage: stock totals, sub-mixes and cocktails are made for
>   exactly the tubes that draw from them (`SURPLUS = 1.0`), plus a dead volume per intermediate vessel
>   (`"dead_volume_uL"` for working stocks, default 5; `"cocktail_dead_volume_uL"`, default = `dead_volume_uL`; raise to
>   7-9 uL if 5 runs short). MM-A is made for n tubes + `premix.extra_rxns` (default 3).
> - **Waivers** `"allow_small_volume"` / `"allow_variable_volume"` must be exactly `true` plus a non-empty
>   `"..._reason"` string (on every entry of that enzyme); anything else is a FAIL ("malformed waiver"). [check a]
>   `allow_small_volume` waives only the sub-floor volume rule (and turns a 2-5 % rounding deviation of that
>   enzyme into a waived WARN); a rounding deviation > 5 % stays a FAIL. [checks b, e]
> - **Canonical constants** must agree with the registry (contradiction = FAIL). [check 4]
> - **Count the pipetting.** `python pipette_count.py config.json [--compare]`. Verdict for the bundled
>   synthetic 11-tube design (`tests/synthetic_fixtures.py`, `ev_spec()`; every comparison below reads
>   **A vs B**, A first): R2 does NOT reduce pipetting steps: **74 vs 88** (A neat stocks vs B equal volume;
>   with the no-enzyme water-in-place default both get +2: 76 vs 90). The break-even is **about 28-36 tubes
>   depending on how replicates are added (31 with one-tube increments)**; never when enzyme levels do not
>   change. The sign flips when working stocks are reused across experiments (prep amortised, run phase only,
>   A vs B: **61 vs 53**; 63 vs 55 with water-in-place) and for Bmin with each dilution counted as 1 step
>   (A vs Bmin: **74 vs 72**). What B buys is accuracy, not fewer steps: additions below 1 uL 6 -> 0 and
>   run-phase volume settings 13 -> 5 in that design. Run `--compare` before claiming "less pipetting". (doc)
> - **Not finished** until the Pipetting Guide has (a) 'TUBES TO PREPARE' (empty tubes to label), (b) 'ENZYME
>   PREPARATION' (A lab stocks with batch and total draw, B common-cocktail recipe, C working-stock / serial-dilution
>   recipe) and (c) the per-tube additions (cocktail uL, which working-stock level and uL), written in the real bench
>   order: MM-A and the varied reagents first, any reagent that must go in late kept separate, enzymes LAST.
>   `reaction_matrix.py` writes all of these; a hand-built sheet must have them too. The rounding-check and
>   pipette-count results are printed by the generator: report them in the reply. (doc)
>
> **Reference format**: `reaction_matrix.py` output IS the lab format (5 sheets: Reaction Matrix, Pipetting Guide,
> Enzyme Additions, Sampling & Fed, Data). Do not restyle it or build a "simpler" sheet by hand; if a copy made
> elsewhere looks different (e.g. a Pipetting Guide that stops after the per-tube table, without the TUBES TO
> PREPARE / ENZYME PREPARATION blocks), that copy is an older toolkit version: `git pull` and regenerate.

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
| **10. Reaction Matrix** | "Generate a pipetting sheet/workbook", "reaction matrix 만들어줘", multi-condition stock/final/volume table needed | Config JSON (stocks+enzymes+conditions+sampling+timepoints) -> `reaction_matrix.py` -> `validate_config()` (volume closure + concentration + sampling/dead-volume + R1/R2 pipetting rules + canon-gate registry check, blocks on FAIL) -> 5-sheet xlsx (Reaction Matrix, Pipetting Guide, Enzyme Additions, Sampling & Fed, Data) + pipette count. See Mode 1a below — this is the default path for ANY pipetting-calculation workbook; do not hand-write openpyxl formulas for this. |

**Auto-chain**: Record(4) -> Comparison(7) -> Pattern Analysis(6) -> Visualization(5) -> Optimization(2)

🔴 **Why Mode 10 is in this table**: it existed as a working script (`reaction_matrix.py`, self-labeled "Mode 10" in its own docstring) but was never added to this table — an agent reading this file top-to-bottom (as the file's own first line instructs) had no way to discover it, and one didn't: a pipetting workbook got hand-built with raw openpyxl instead, which is how the ~4% concentration bug described in Mode 1a got in. Numbering gap (8, 9 unused) kept as-is rather than renumbered, since renumbering risks breaking any other doc/reference to "Mode 10" that already exists elsewhere (e.g. other skill files or task notes) — not worth the silent-breakage risk to close a cosmetic gap.

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

### Mode 1a: Generating a pipetting-calculation workbook -- mandatory verification

🔴 **Do not hand-write openpyxl formulas for a multi-component reaction matrix from scratch.** Use
`reaction_matrix.py` (Mode-10-style config JSON -> xlsx) as the default generator for any
protocol whose deliverable includes a stock/final/volume pipetting table. It computes every
component's volume from ONE consistent basis (the declared total reaction volume) and defines DW
as the residual, which makes the "wrong reference volume" bug class structurally impossible.

**Why this exists**: once, a pipetting xlsx was hand-built with openpyxl instead of using this
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
4. **Canonical constants** -- `canon_gate.py` checks the config against a canonical-constants registry
   (decided stock/final concentrations, batch labels, enzyme stocks); a contradiction is a FAIL that blocks
   like the checks above, a differing per-experiment working stock is only a WARN, and a config that names
   no registry field is BLIND (shown, never a pass). Standalone on any xlsx Params sheet or config:
   `python canon_gate.py FILE...` (exit 0 / 1 / 2, 2 = BLIND). Registry lookup (first hit wins, `--registry`
   overrides): `$LAB_CANON_REGISTRY` -> `canonical_constants.toml` next to the checked file -> one next to
   `canon_gate.py` -> `canonical_constants.example.toml` (synthetic, ships with the skill: copy it and put your
   own decisions in); none found = BLIND, exit 2. A new decision about a constant goes into the registry first.

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
that is exactly the self-review that missed that bug. For anything that will actually be
pipetted at the bench (not just discussed), additionally have it checked independently (a labmate, or a fresh agent session given only
the config and the workbook) — self-review by the same reasoning that produced the bug does not
reliably catch that bug.

**Publishing (optional, per computer)**: if a Methods folder is configured (env `LAB_METHODS_DIR`, or
`"methods_dir_glob"` relative to the home folder in `~/.config/experiment-hub.json`, e.g.
`"OneDrive*/Lab/Methods"`), `reaction_matrix.py` copies every generated workbook there right after generation; a
different file of the same name is kept as `NAME.BACKUP-YYMMDD-HHMM.xlsx` first. Nothing configured = skipped
with a note; configured but missing or the copy does not match = exit 3 (NOT published, say so). `--no-publish`
skips it for scratch runs; the tests point `LAB_METHODS_DIR` at a temporary folder (`tests/conftest.py`).

### Mode 1b: one-off pipetting / dilution arithmetic -- `reaction_matrix.py calc` is the only path

Bench arithmetic done in prose goes wrong in the same two ways again and again: a top-up computed from the plan
instead of from what is already in the tube ("I already added 29.53, so add 1.5 more"), and a dilution factor
that ignores an earlier step (a 2-fold pre-dilution followed by the usual 10-fold is DF 20, not 10). A pipetting
number that someone will act on is never computed in a sentence.

Rule: every volume, top-up, C1V1 or dilution-factor number that goes to the bench or into a calculation comes
from `reaction_matrix.py` (workbook for a design, `calc` for a one-off), and the printed formula line is
quoted in the reply:

```bash
python reaction_matrix.py calc topup --target 31.03 --have 29.53   # add 1.5
python reaction_matrix.py calc df --stages 2 10                    # DF 20
python reaction_matrix.py calc df --sample 10 --total 80           # DF 8
python reaction_matrix.py calc c1v1 --c1 1000 --c2 100 --v2 50     # v1 5, diluent 45
python reaction_matrix.py calc topup-conc --have 0.8 --target 1.0 --vol 100 --stock 100
python reaction_matrix.py calc back --measured 0.17108 --df 20     # 3.4216
```

- Restate the physical state first, in one line, before computing: what is already in the tube (which
  version of the mix), what the target is, which dilution steps really happened. A user's "I already put
  X in" is the input; do not substitute the plan's amounts for it.
- DF = total / sample volume per step, and compound steps multiply. Back-calculated concentrations use
  the DF of THAT tube (a tube with 80 uL instead of 100 uL has DF 8, not 10).
- Exit 2 means the question is impossible as posed (overfilled, diluting upward, under- or
  over-determined): report that to the user instead of picking a number. Exact decimal arithmetic, no float noise.
- A design with many tubes still goes through the config workbook above, not a loop of `calc` calls.


**Suggested workbook convention**: put every fixed-concentration component (buffer, salts, fixed cofactors) into ONE premix (MM-A): mark them `"type":"buffer"` in the config, never `cofactor`. Only the varied reagents change per tube; the water is split into the common water in MM-A and a per-tube DW top-up (R1). Enzymes held at one level in every tube = one common cocktail (n x 1.0; surplus convention everywhere: MM-A n + `premix.extra_rxns` (default 3), stocks/sub-mixes/cocktails x1.0 i.e. no percentage overage, +5 uL dead volume per intermediate vessel, raise `dead_volume_uL` to 7-9 if 5 runs short), added LAST in a fixed staggered order; solids weighed per tube go in first.

**R1/R2 workflow**: the rules, waivers and the pipette-count command are in the HARD RULES box at the top of this file. Config with `"equal_volume_uL"` per enzyme -> `python equal_volume.py spec.json expanded.json` (one pseudo-enzyme per level; `canon_gate` still checks the undiluted `source_stock_gL`; `"diluent": "water"`) -> `python reaction_matrix.py expanded.json out.xlsx` (or pass the spec directly: `reaction_matrix.py` expands it). A level's working stock = `rxn_gL x total_volume / equal_volume_uL` and must not exceed the lab stock; when the top levels of several enzymes need large volumes, the equal volumes can overfill the tube (`pipette_count.py` reports INFEASIBLE) - then use one cocktail per condition from the lab stocks (`--cocktail per_condition_direct`). Worked example: `ev_spec()` in `tests/synthetic_fixtures.py`. Every downstream formula must reference the total-volume cell, never a literal volume. After editing, recalculate with the timeout-guarded `excel_com_guard.py` (see "Pipetting Workbook Verification" below; never a bare win32com call that can hang on a dialog) and compare with an independent Python calculation.

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

### Four rules for editing a pipetting workbook

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

### Structural guards in `pipetting_checks.py`

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
