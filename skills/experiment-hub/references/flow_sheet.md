# FLOW bench sheet and the layout / sub-mix config keys

Moved out of SKILL.md to keep SKILL.md under the size cap; SKILL.md keeps the rules in one line each.

## What FLOW is

`reaction_matrix.py` writes `FLOW` as the first and active sheet of every workbook (`flow_sheet.py`). It answers
"what do I do next, and how much of each stock do I take out?" in dispensing order. It holds static values only
(no formulas), built from `pipette_count.build_plan` / `rounded_plan` and `reaction_matrix.lab_stock_totals` (the same
function the Pipetting Guide block "A) LAB STOCKS TO TAKE" uses), so the two sheets cannot disagree.

| Block | Content |
|-------|---------|
| title + sentence | tubes, volume per tube, temperature; the volume order every tube follows, e.g. `MM-A 24.4 -> substrate mix 15.6 -> E1 5.0 -> E2 5.0 uL` |
| TAKE OUT | total uL of every stock for the WHOLE run, spare included; enzymes first, then substrates, then buffer components (take frozen stocks out first) |
| PREP | MM-A (components + common water), substrate mixes (water included, tubes served, uL per tube, total made, spare), enzyme cocktail, enzyme working stocks (diluted with WATER, highest level first) |
| RUN | numbered steps in bench order, enzymes LAST; tubes that receive the same volume are listed together (`#1-3, #7-9`), so a step is never one row per tube |
| SAMPLING | sample volume, dilution, quench, analysis, targets and the timepoints; one row per schedule when conditions carry their own `timepoints` |
| CHECK | the rounded volumes of every tube pattern add up to the total volume (`OK: every tube closes to N uL.`) |

## Config keys

| Key | Default | Effect |
|-----|---------|--------|
| `"layout"` | `"flow"` | `"flow"`: FLOW is visible, the five reference sheets (Reaction Matrix, Pipetting Guide, Enzyme Additions, Sampling & Fed, Data) stay in the file but are HIDDEN; `"full"`: all visible. Any other value FAILs validation. |
| `"water_in_submix"` | `true` | For every substrate sub-mix that serves more than one tube, the smallest DW top-up of the group is carried inside the mix, so every tube gets the same few volumes. A tube with a larger top-up keeps the remainder as a DW step. If a remainder lies between 0 and the pipette floor, the fold is reduced by the floor; if that leaves nothing, or the water draw of the mix would be below the floor, the group is not folded. `false` = the per-tube DW top-up of earlier versions. Must be a boolean. |
| `"submix_spare_tubes"` | 1 (2 when the mix serves 10 tubes or more) | A sub-mix is made for n + spare tubes, so the last tube is never short. A fixed 5-8 uL dead volume is less than one tube for a large mix. Non-negative number. |
| `"submix_dead_volume_uL"` | unset | An explicit value keeps the fixed-uL spare of earlier versions (the spare in tube units is then dead / per-tube volume, informational). Enzyme cocktails and working stocks keep `dead_volume_uL` / `cocktail_dead_volume_uL` because enzyme is scarce. |
| per-condition `"timepoints"` | the run's list | A subset of the run's timepoints for that condition; the FLOW sampling block prints one `Timepoints (<groups>)` row per distinct schedule with its tubes and sample count (a time-course arm next to end-point arms). |

SCHEDULE (clock-time) and Run Log sheets are not part of the default output; add them only on request. A run that
starts today still needs a clock-time sheet built from ONE start cell.

`validate_config` prints an `INFO flow:` line (how many tubes receive the identical volume sequence, how many distinct
volume settings the run needs, how many tubes carry their water inside a sub-mix) and the R1 line reports the folded
tubes. A folded top-up is not a uniformity WARN.

## One reaction volume per workbook

Every tube keeps the SAME `total_volume_uL`. Do not vary the volume per tube, and do not add a per-condition volume,
to make a small weighed solid easier to weigh: the per-tube volume sequence on FLOW, the sub-mix recipes and the
closure check all assume one volume. State the mass per level and the balance resolution it needs instead (for
example "0.068 mg per tube is 0.7 of a division on a 0.1 mg balance"). When a note says the replicates are weighed as
one group because the per-tube mass is below the balance, the Pipetting Guide repeats that sentence with the tubes it
applies to (it never asserts "one per tube" against it).

## Related generator rules that came with this port

- **Sub-mix recipes are printed.** The Pipetting Guide block `SUB-MIX RECIPES` lists, per sub-mix, the draw from each
  stock (and "add X uL of water to the SM-n tube"), the total made, the spare, and the tubes it is dispensed into.
- **Per-tube breakdown is a view of the Reaction Matrix.** Its cells reference the Reaction Matrix cells and the
  total-volume cell instead of re-deriving every volume from literals, so changing a stock or the total volume on the
  Reaction Matrix moves the Guide with it. Enzyme totals are one row per enzyme.
- **Stock `type` contract.** `"buffer"` = a component held at ONE level in every tube (rides in MM-A, needs
  `final_mM`); `"substrate"` = read from each condition's `substrates`. A buffer without `final_mM` FAILs validation
  with a message that names the stock and the fix, not a `KeyError`.
- **Yield basis.** `"yield_basis_mM"` (global, or per condition) wins and is the way to report a yield on a reactant
  outside the volume closure (a weighed solid). Otherwise `"yield_substrate"` (global or per condition) is looked up in
  the condition's `substrates`, then in `stocks[...]["final_mM"]`; a name that resolves nowhere raises instead of
  silently dividing by 100.
- **Serially diluted levels.** On `Enzyme Additions` the independent-draw make / lab-stock / water cells of a serial
  level read `see Guide block C` (the independent figures are short for a serial level); with `"serial_dilution": []`
  the independent figures are printed.
