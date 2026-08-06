# Figure Aesthetics Rules — graphic composition SSOT

> Compiled: 2026-06-26 | publication-figures skill
> Scope: the **layout / composition** rules for scientific figures — what to draw and
> what NOT to draw inside the axes. This is the single source of truth for the R1–R4
> rules that were previously scattered as post-hoc checklists across four skills
> (publication-figures, cascade-scheme-renderer, journal-presentation-maker).
>
> This file governs **graphic composition**. It is a separate axis from:
> - **Color / font / axis-line / palette tokens** → `plot_style_tokens.json` +
>   `plot_style_sigmaplot_prism.md` (the RC_RECOMMENDED / RC_PRISM / RC_SIGMAPLOT presets).
> - **Caption *text* rules** (species italic, units, kinetics symbols) → academic-term-rules §7.
> - **Data ↔ figure verification** (SSIM, data integrity) → `figure_verification.md`.
>
> If a rule here conflicts with matching the *published reference* during a Route 5
> rebuild, **match the reference** — these are house defaults for new figures, not a
> mandate to override a journal's existing style (see `figure_verification.md` §4).

---

## Why this file exists

Color and font had a token SSOT; **layout did not**. The composition rules lived only
as "things to check against the reference" in `figure_verification.md` §4 and as scattered
patterns in `patterns_260527.md`. Nothing said, as a house rule, "do not put a title on
the graph." The result was drift: figures in the same manuscript disagreed on whether to
use `set_title`, whether to call a layout manager, whether the legend frame is on.

Concrete violation patterns measured at compile time across a multi-panel figure set:
- `ax.set_title("<enzyme/sample name>")` on a data panel = **R2 violation** (graph title).
- layout manager (`tight_layout`/`constrained_layout`) present in some render scripts
  only and **absent** in others = **R4 inconsistency**.
- one panel uses `frameon=True` while sibling panels don't = **R1 inconsistency**.

---

## R0 — Enforcement (mandatory, checked before "figure done")

The rules below are not advisory. The measured root cause of "rules get ignored"
(260626 audit: 11 raw `ax.legend`, ~37 hardcoded hex across 6 figures) was that the
rules + helpers existed but **nothing forced a render script to use them** — they were
opt-in, re-derived per file. R0 closes that gap by making the lint a gate.

**A figure render script is NOT done until `python scripts/figure_lint.py render_figN.py`
reports 0 high-severity findings.** The lint enforces, by code:

- **No raw `ax.legend(loc=...)` / `plt.legend(...)`.** Legends go through `smart_legend(ax)`
  ONLY — it measures the rendered legend bbox and picks a corner that clears the data, or
  expands the y-limit in small steps. A literal `loc=` bypasses corner-selection and is the
  direct cause of legend-over-data overlap. (`raw_legend_calls` MUST be 0.)
- **No external / center legend.** `bbox_to_anchor` outside the axes or `loc='center*'`
  desyncs panel widths — forbidden. Shrink slices/ncol to fit a corner instead.
- **No literal `#RRGGBB`** in a render script. Every color comes from `series_color(name)`
  (entity colors), `OKABE_ITO[key]` (palette), `NEUTRAL_PAIR` (system/condition comparison
  grays), or `C_ANNOT`/`C_ANNOT_SOFT` (annotation text) — even if a literal happens to equal
  the SSOT value. (`hardcoded_hex` MUST be 0; the SSOT-defining line in the theme module is
  exempt.)
- **No literal `fontsize=<number>`.** Use `FS_AXIS`/`FS_TICK`/`FS_LEGEND`/`FS_ANNOT`/
  `FS_ANNOT_SM`. A bare `fontsize=6.8` is a violation even when it equals a constant.
- **A layout manager is present** (`constrained_layout=True` or `tight_layout()`) — manual
  `subplots_adjust`/GridSpec margins alone FAIL (they break when data changes = "layout looks
  weird"). One manager, identical across the whole manuscript set.
- **Every `savefig` passes `dpi=300`, `bbox_inches='tight'`, `facecolor='white'`.**
- **No descriptive `set_title`** (R2). Only the bare panel letter via `panel_label`.

The named-entity color rule is now executable: `#009E73` (green) is RESERVED for
D-Gal/D-galactose and must not label any other entity; `series_color(name)` raises on an
unknown entity so you register it instead of inventing a literal. Variants of one entity →
`lighten()`/`darken()` of its hue; system/condition comparison → `NEUTRAL_PAIR`.

Start every new figure by copying `scripts/make_fig_template.py` (it pre-wires the helper
imports, `constrained_layout=True`, per-panel `panel_label`+`smart_legend`, and the correct
`savefig`) — never author a render script from a blank file. The template is the
rule-injection point; the lint is the gate.

---

## Priority order (user-stated, 2026-06-26)

When trade-offs collide, resolve in this order:

1. **Legibility first** — font face + font size readability. Arial (DejaVu Sans fallback).
   Axis labels ≥ 8 pt, tick numbers ≥ 7 pt, panel letter ~14 pt bold. Never shrink text
   below readable size to fit a layout; resize the figure instead.
2. **No graph title** (R2) — title lives in the caption, never on the axes.
3. **Abbreviation rules follow the manuscript definition** — every abbreviation on a figure
   (enzyme names, sugar descriptors, cofactors, species) matches the manuscript's own
   definition list, not a generic house style. Enzyme origin-prefix italic (e.g. an enzyme
   named with a two-letter organism prefix renders that prefix italic, the rest roman);
   D-/L- stereodescriptors **roman/upright**; NAD⁺/NADP⁺ superscript; species italic;
   spell common names consistently (full form, not a casual contraction). (Authoritative
   source: the manuscript's own definition list + the academic-term-rules skill.)
   **Abbreviation consistency within a figure**: do NOT mix an abbreviation with a full
   name for sibling entities. The classic miss is a legend reading "D-Gal" (abbrev) next to
   "Glucose" (full) — sugars must match in style: **D-Gal + D-Glc**, or *D-galactose +
   D-glucose*, never one of each. Define the abbreviations at first mention in the caption
   ("D-Gal, D-galactose; D-Glc, D-glucose"). Run `check_abbrev_consistency(labels)` from
   `aesthetic_helpers.py` on the legend label list before saving. (academic-term-rules §2.)
4. **Legend placement** — prefer the **corners (가생이), never center**. Preference order:
   **upper-right → lower-right → lower-left → upper-left**. Pick the first corner that
   clears the data. `frameon=False`.
5. **No overlaps** — significance markers (`*`/`**`/`***` + brackets) spaced so they don't
   collide with each other, with data, or with error bars; **symbols (markers) must not
   overlap** each other either. Adjust spacing / jitter / offset.
6. **Line weight & color** — `thick` (line width) neither too thin nor too heavy (≈1.2–2.0 pt
   body lines); color combinations from the colorblind-safe Okabe-Ito palette with the
   manuscript's fixed series mapping (e.g. a product and the enzyme that makes it share one
   color such as blue `#0072B2`; a second product/enzyme pair takes vermillion `#D55E00`).
7. **Cross-figure design uniformity** — all figures of one manuscript must agree on font,
   sizes, palette, series-color mapping, legend convention, spine style, and layout manager.
   This is its own verification axis — see "Uniformity check" below.

### Additional house rules (user-confirmed 2026-06-26)

- **No legend title.** Do not put a title on the legend (e.g. "Temperature"). The series
  labels carry the meaning; the axis label and caption give the rest. (`smart_legend`
  drops any `title=` passed to it.)
- **No bold by default — including panel letters.** Panel letters `(a) (b)` are normal
  weight, not bold. Bold may be used only when the target journal's style requires it, and
  that is a per-submission decision the user confirms (set `PANEL_WEIGHT="bold"` then).
  Do not bold axis labels either unless the journal demands it.
- **Error bars match the symbol/series color, not black.** A black error bar on a colored
  marker reads as a separate object and breaks the design. Use the series color (slightly
  darkened ~0.78 for legibility on light fills), not a fixed `#333`/`#000`.
- **Bars: no edge.** Bar charts use `edgecolor="none"`, `linewidth=0` — flat filled bars,
  no black outline, unless a specific journal figure requires outlined bars.
- **Bars must not touch the y-axis.** A 'tight' x-axis (`margins(x=0)`) glues the first bar
  onto the y-axis (and the last onto the right spine), which reads as a layout bug. Give the
  x-axis a half-category + a small pad on both ends — use `bar_xlim_pad(ax, n_groups)`
  (`set_xlim(-0.5 - pad, n-1 + 0.5 + pad)`), called AFTER the bars and after any tight-axis
  styling. ~0.7 pad for simple bars, ~0.55 for grouped/dodged bars.
- **Error-bar color = the bar's own fill** (per-bar when bars are multi-colored), darkened
  only slightly (~0.82) for legibility. A bar and its error bar in visibly different colors
  reads as two objects — match them.
- **Font sizes uniform across the figure set.** Every text element of the same kind uses
  the same pt across all figures (tick labels = FS_TICK everywhere, etc.). Do not hardcode
  a smaller size for one panel's category labels — pull from the theme constants. (This is
  what made Fig5a's species labels read smaller than Fig2 before the fix.)
- **Caption sync.** On-figure values and the caption must come from the same rawdata so they
  never drift (see `feedback_manuscript_ssot_workflow_260626`); the figure script should
  emit the caption text alongside the PNG rather than hand-typing it.

---

## The four rules (R1–R4)

### R1 — No overlap (legend / label / object)
No legend, text label, panel letter, or annotation may overlap data points, error bars,
fit lines, or another object.

- **Legend**: `frameon=False` always (matches `plot_style_tokens.json`). Place to clear
  the data — inside in empty quadrant, or above the axes with `bbox_to_anchor`. Do not
  let `loc='best'` silently sit on top of points in a dense plot; verify the placement.
- **Legend frame fully disabled**: all legend background patches are off —
  `frameon=False` AND no `facecolor='white'` on the legend. A white background patch
  on a `frameon=False` legend is still a visible white box that occludes data.
  `smart_legend` enforces this; never pass `facecolor` to it. (260629)
- **Legend frame consistency**: every panel of a multi-panel figure uses the *same*
  `frameon` setting. No mixed `frameon=True`/`False` across siblings (the fig3 `ax_d` bug).
- **External legend — donut/pie exception (260629)**: the standard rule forbids
  `bbox_to_anchor` outside the axes. Exception: **donut and pie charts** may place
  the legend to the right of the axes (`bbox_to_anchor=(1.02, 0.5), loc='center left'`)
  because a circle has no empty corners that can contain a readable legend. The lint
  R0 donut-chart exception must be registered: if `chart_type == 'donut'`, external
  legend does NOT raise a high-severity finding. Do NOT use external placement for
  any non-circular chart type.
- **Legend deduplication (260629)**: if the panel title, an `ax.text` annotation, or a
  sibling panel already clearly labels an entity, remove that entity from the legend to
  avoid repetition. If sibling panels (c) and (d) need the *same* legend, add it
  explicitly to *both* panels — do not assume inheritance. `smart_legend` does not
  deduplicate automatically; the render script must pass a filtered `labels` list.
- **Text labels** (scatter point names): offset with a per-item `(dx, dy, ha)` map, spread
  across 4 directions — see `patterns_260527.md` Pattern 4. fontsize 7.5–8.5 pt.
- **Panel letter** never sits on data — place at `loc='left'` above the axes or in a
  cleared corner.

### R2 — No graph title (no `suptitle`, no axes `set_title` text)
Multi-panel manuscript figures **do not carry a descriptive title on the graph**. The
title belongs in the caption, not painted onto the axes.

- ❌ `ax.set_title("Enzyme activity vs pH")` — descriptive title.
- ❌ `fig.suptitle(...)` — figure-level title.
- ✅ Panel letter only: `ax.set_title("a", fontsize=11, fontweight="bold", loc="left")`.
  (This is the one sanctioned use of `set_title` — a bare panel letter, left-aligned.)
- **Enzyme / sample names** that label *which panel is which* go in the caption, or as an
  in-axes `ax.text(...)` annotation positioned to clear the data — **not** as `set_title`.
  (Common miss: the intent is a sample label, but `set_title` renders it as a graph title
  and trips R2. Convert to `ax.text` in a cleared corner, or move to the caption.)

Rationale: a graph title duplicates the caption (R3) and steals vertical space that
pushes panels together (R4). Journals strip them in production anyway.

### R3 — No redundant on-figure explanation (user-reinforced 2026-06-26)
Anything the caption says, the figure does not repeat. The user has repeatedly asked for
**no table titles, no graph titles, no stray condition/description text** on the figure —
it kept creeping back in, so this is now an explicit allow/forbid list and is lint-checked.

**ALLOWED on-figure text (only these):**
- axis labels + units; tick labels
- data-series legend (series names that the legend needs)
- the panel letter `(a)` `(b)` via `panel_label`
- significance markers (`ns`, `*`, `P < 0.05`) — italic per "Significance notation"
- a **bare panel-identifying entity name** when it tells you *which panel is which* and is
  not otherwise obvious — e.g. two related enzymes labelled by name alone. Keep it to the
  entity name; do NOT append the condition.

**FORBIDDEN on-figure text (move to the caption):**
- **Any title** — no `ax.set_title("descriptive")`, no `fig.suptitle`, no table title.
- **Condition / scenario / method labels** painted on the axes: e.g. a process-mode label
  like `"Fermentor (deterministic)"`, an `"<enzyme> flask"` / `"<enzyme> variants"` tag, a
  biomass loading `"8 g DCW/L"`, `"pH 7.0"`, `"30 °C"`, growth medium, replicate count
  `n = 3`, "Figure shows…". These describe the panel = caption material. (If a bare entity
  name is needed for panel ID, strip the condition: `"<enzyme> flask"` → keep the enzyme
  name only, put "flask" in the caption.)
- restating what a curve/bar is when the legend already says it.

So an enzyme name alone may stay (panel ID); `"<enzyme> flask"` / `"<enzyme> variants"` must
lose the condition word. When in doubt: if the text is a sentence fragment describing the
experiment, it belongs in the caption, not on the axes.

**Caption — no experimental result (260629)**: a figure caption describes the experimental
setup and measured quantities; it does **not** state the result or draw conclusions.
Example violation: `"; peak at pH 7 in sodium phosphate buffer"` or `"; maximum activity
observed at 55 °C"` — these are results and belong in the Results text, not the caption.
Caption template: `"[Entity] [measurement] as a function of [variable]. [Conditions]. Error
bars, [SEM/SD], n=[N]."` Any clause that reads as "we found that …" or "the enzyme showed …"
must be moved to the Results body.

- Detailed description (what each curve is, conditions, n) → **caption** (academic-term §7).
- Significance: `*P<0.05`, `**P<0.01`, `***P<0.001` with bracket — these stay on-figure.
  **Statistical abbreviations/variables are *italic*** — see "Significance notation" below.

### R4 — Controlled layout (no clipped/overlapping panels)
Every figure uses a layout manager so panels, labels, and colorbars don't collide or clip,
and the choice is **consistent across all `make_figN` scripts of one manuscript**.

- Use `constrained_layout=True` (preferred for colorbar-bearing / tight grids) **or**
  `fig.tight_layout()` — pick one convention per manuscript and apply it to *every* panel
  figure. Do not leave some figures with neither (the fig1/2/4/6 gap).
- Colorbar spacing: explicit `pad`/`shrink` rather than default crowding — see
  `patterns_260527.md` Pattern 2 (`pad=0.10, shrink=0.55, aspect=18`).
- `figsize` matches the journal column width (Nature single ≈ 3.5", double ≈ 7.2");
  AR mismatch with the reference is flagged by `figure_verification.md` §3.
- Save with `bbox_inches='tight'` so stray margins are trimmed.

---

## Significance notation (statistics on-figure) — italic rule

This was the **missing rule** that let `ns` render upright in a Fig3 review (260626):
the aesthetics SSOT covered *placement* of significance markers but not their *typography*.

**Statistical variables and abbreviations are set in *italic*; operators, digits, and
asterisks are roman.** This is the standard across Nature / ACS / most journals.

| Token | Style | mathtext |
|---|---|---|
| `ns` (not significant) | *italic* | `$\it{ns}$` |
| `P` (P-value, prefer capital `P`) | *italic* | `$\it{P}$` |
| `n` (sample size), `t`, `F`, `r`, `R`, `df` | *italic* | `$\it{n}$` … |
| `*` `**` `***` (significance stars) | roman | `*` (no wrap) |
| `<` `=` `>`, digits, `0.05` | roman | as-is |

So `P < 0.05` renders as *P* < 0.05 (only the `P` italic); `ns` renders as *ns*;
`P = 0.03 (n = 3)` italicizes `P` and `n` only.

**Never hand-write `ax.text(x, y, 'ns')`** — a plain string renders upright and silently
violates the rule (exactly the Fig3 miss). Use the helper:

```python
from aesthetic_helpers import stat_annot, significance_italic
stat_annot(ax, x, y, 'ns')            # auto-italicizes ns / P / n …
stat_annot(ax, x, y, 'P < 0.05')      # → *P* < 0.05
label = significance_italic('P = 0.03 (n = 3)')   # if you need the string only
```

`stat_annot` wraps `ax.text` and applies `significance_italic()` to the text first.
It honors the figure's annotation font size (`FS_ANNOT`) by default. Stars (`***`) pass
through unchanged. If the string already contains `$…$` mathtext, it is left untouched.

**Bracket geometry** (placement, priority #5): the significance bracket and its label
must clear both bars' error bars and not collide with neighbors — raise the bracket above
`max(bar+err)` of the compared pair, and raise the y-limit if the bracket would clip.

**Measurement conditions** (e.g. "8 g DCW/L") are not significance markers — keep them
out of the data area. Put them in the caption, or as an `xlabel`/cleared-corner annotation,
never floating where `bbox_inches='tight'` can clip them against a bar (Fig3 (d) miss 260626).

---

## Uniformity check (cross-figure, priority #7)

A manuscript with N figures must be checked *as a set*, not one at a time. Extract these
attributes from every `make_figN.py` / rendered PNG and assert they agree:

| Attribute | Must match across all figures |
|---|---|
| Font family | same (Arial) |
| Axis-label / tick / panel-letter sizes | same pt values |
| Palette | same Okabe-Ito hex set |
| Series → color mapping | same named-entity→color everywhere the series appears |
| Legend convention | same `frameon`, same corner-preference logic |
| Spine style | same (L-frame vs box) |
| Panel-letter style | same case/weight/position (`(a)` bold, upper-left) |
| Layout manager | same (`constrained_layout` OR `tight_layout`) |
| Error-bar style | same capsize / elinewidth / ecolor |
| DPI / save | same 300 DPI, `bbox_inches='tight'` |

Report any attribute that differs between figures as a uniformity defect — this is where
the fig3 `frameon` mismatch and the fig1/2/4/6 layout gap are caught.

**A named entity keeps ONE color across the whole figure set.** Any chemical species,
enzyme, or condition that appears in more than one figure must use the same color
everywhere — pull it from a single fixed `SERIES_COLORS` map, never re-pick per figure.
Two real misses caught in review: "Formate" was sky-blue in one figure and orange in
another (and that orange meant a *different* species elsewhere); a green used for one
panel's "dual-cell" collided with the green that meant "D-galactose" in another figure.
When a panel compares *systems/conditions* rather than the named entities (e.g. dual vs
single cell), pick neutral colors (a gray light/dark pair) that don't collide with any
entity color. For two variants of the same entity (e.g. an enzyme's 5-day vs 7-day run),
keep the entity's hue and vary lightness (`lighten()` / `darken()`) plus marker/line
style — do not switch to an unrelated hue.

---

## Quick checklist (run before calling a figure done)

```
R1  legend frameon=False, not over data; frameon consistent across panels;
    text labels offset, no overlap; panel letter clears data.
R2  no ax.set_title with descriptive text; no fig.suptitle;
    only sanctioned set_title = bare panel letter loc='left'.
R3  no methods/conditions sentences inside axes; detail lives in caption.
    significance tokens italic (ns/P/n via stat_annot, never plain ax.text);
    measurement conditions out of data area (caption/xlabel, not clippable).
R4  a layout manager is called (constrained_layout OR tight_layout),
    consistently across all make_figN of this manuscript; colorbar pad set;
    figsize = journal column; bbox_inches='tight' on save.
```

The grep/AST lint that enforces R0–R4 (`raw ax.legend`, hardcoded hex/fontsize,
descriptive `set_title`, missing layout manager, savefig flags) is now **built and
mandatory** — `scripts/figure_lint.py`. It is no longer an optional follow-up: a figure is
not done until `python figure_lint.py render_figN.py` reports **0 high-severity findings**.
See "## R0 — Enforcement" at the top of this file. (Originally deferred under the
"규칙 SSOT 신설 (A)" scope; that deferral was the measured root cause of rules being
ignored — 260626 audit — so it was promoted to mandatory.)

---

## Pareto optimization figures (260629)

When a figure shows a Pareto front from multi-objective optimization **and** the same plot
includes at least one experimental validation point (wet-lab confirmation of a model-predicted
optimum), connect each predicted–experimental pair with a dashed connector line. This visually
communicates the prediction → verification gap and is now the standard pattern.

```python
# Standard pattern: connect Pareto-predicted point to its experimental validation
# pred_t, pred_y = model-predicted coordinates
# exp_t, exp_y   = experimentally measured coordinates
ax.plot([pred_t, exp_t], [pred_y, exp_y],
        '--', color=C_ANNOT, lw=0.8, zorder=1)
# or, for a true directional arrow:
ax.annotate('', xy=(exp_t, exp_y), xytext=(pred_t, pred_y),
            arrowprops=dict(arrowstyle='->', color=C_ANNOT, lw=0.8),
            zorder=1)
```

Rules:
- Use `C_ANNOT` (annotation gray) for the connector — do NOT use the series color or a
  literal hex.
- `lw=0.8` (thinner than data lines) so the connector is subordinate to the data.
- `zorder=1` — render below data markers.
- Label the experimental point distinctly from the Pareto scatter (e.g. star marker `*`,
  or a separate `series_color('exp_validation')` entry).
- If multiple Pareto solutions were experimentally tested, draw one connector per pair.

---

## Species / entity italic in tick labels (260629)

When the x-axis (or any categorical axis) lists **biological species names**, the genus and
species parts must be typeset italic in the tick labels. Use mathtext italic, not a font
style parameter, because matplotlib's tick-label renderer does not respect `fontstyle='italic'`
reliably.

```python
# Biological species — mathtext italic for genus + species epithet:
species_labels = [
    r"$\it{Gracilariopsis}$ chorda",      # one-word genus, common name roman
    r"$\it{Kappaphycus}$ alvarezii",
    r"$\it{Gelidium}$ elegans",
    r"$\it{Pyropia}$ yezoensis",
]
ax.set_xticklabels(species_labels)
```

Rules:
- **Genus + species epithet → italic** (`$\it{Genus}$ epithet`). Subspecies/variety
  descriptors also italic. Authority names (e.g. "Ag.") roman.
- **Chemical species (D-Gal, D-Glc, NAD⁺) → roman** — do NOT italicize sugar
  descriptors or cofactor names even when they appear next to species names on the same axis.
- D-/L- stereodescriptors are always roman (separate rule, academic-term-rules §2).
- **Abbreviation consistency**: if both a full species name and a code name appear on the
  same figure, the full name uses italic per this rule; the code (e.g. "Ko", "Py") stays
  roman.
- Apply `check_abbrev_consistency(labels)` from `aesthetic_helpers.py` after constructing
  the label list to catch mixed styles.

---

## Cross-references

- `plot_style_sigmaplot_prism.md` + `plot_style_tokens.json` — color/font/axis tokens (separate axis).
- `figure_verification.md` §4 — design-drift checklist for *reference matching* (Route 5).
- `patterns_260527.md` Pattern 2 (colorbar pad / R4), Pattern 4 (label collision / R1),
  Pattern 7 (panel-letter-only title / R2·R3).
- `academic-term-rules` §7 — caption *text* rules (the complementary axis to this file).
- SKILL.md Route 3 — multi-panel standards (palette, panel labels, significance bars).

> Memory provenance: `feedback_manuscript_ssot_workflow_260626` §52–56 diagnosed the
> R1–R4 SSOT gap and the measured violations this file consolidates.
