---
name: publication-figures
description: Unified figure/visualization router for all scientific output. Covers AI-generated schematics, lab routine plots (HPLC/kinetic/BO), publication multi-panel figures with significance annotations, and low-level matplotlib customization. Use for any figure destined for a paper or presentation. For general-purpose photos/artwork use generate-image; for structural/flow diagrams in documents use markdown-mermaid-writing.
---

# Publication Figures — Meta-Skill

One skill covering what used to be four: AI-generated schematics, publication
multi-panel layout, low-level matplotlib control, and lab routine plots
(see **Replaces** at the bottom).

## Trigger

Use when:
- Creating any figure for a manuscript, poster, or presentation
- Generating scientific diagrams or pathway schematics
- Plotting lab data (HPLC, kinetic, BO results)
- Customizing plot aesthetics for journal submission

## Routing

```
Figure request
 ├── Enzymatic cascade / reaction scheme
 │    └── scripts/scheme_render.py — arrows, cofactor arcs, labels
 ├── Pathway / mechanism diagram → [Route 1] AI schematic generation
 ├── HPLC / kinetic / BO data → [Route 2] plot with the style tokens below
 ├── Multi-panel stats figure → [Route 3] publication layout
 ├── Fine-grained control → [Route 4] low-level matplotlib customization
 ├── Rebuild existing figure from rawdata → [Route 5] reconstruction + verification
 └── Architecture / flowchart / timeline / swimlane / ER / quadrant
     (editorial HTML+SVG, presentation/report quality) → [markdown-mermaid-writing or journal-presentation-maker]
```

---

## Identifying a figure file (applies to every route)

**A render's filename is not evidence of which figure it is.** Map a file to a
manuscript slot by its caption sidecar (`<stem>.caption.txt`, line 1 names the
figure) or by opening the picture — never by the name. Filenames in a figure
repo record which script emitted the file, so they stop tracking the manuscript
the moment figures are reordered, and a legacy-naming convention is never
partial: assume every filename in the directory is legacy.

Worked failure: a gallery held `Fig6.png` whose own sidecar caption read
"Fig. 7. ..." — the real Fig. 6 sat in a differently named file. An integration
pass mapped by filename and overwrote the manuscript's correct Fig. 6 with
Fig. 7's chart, leaving the same chart printed twice and Fig. 6's subject
missing entirely. The manuscript had held the right image before the edit.

🔴 **Verification corollary.** Byte-identity and aspect-ratio checks PASS while
the wrong picture sits in the slot — they did, in that case. When verifying a
figure integration, one check must open the image and read the caption it landed
under. See `manuscript-pipeline` §Logging & Provenance for the docx-side gates.

---

## Route 1 — Scientific Schematics (AI-Generated)

For: experimental setups, metabolic pathways, protein mechanisms, workflow diagrams

1. Generate with **Nano Banana 2** image model
2. Auto-review with **Gemini** for scientific accuracy
3. Iterate if quality score < threshold (max 3 rounds)
4. Output: PNG at 300 DPI

**Prompt template:**
```
Scientific schematic of [topic]. Publication quality, white background,
labeled components, clear arrows indicating [process flow].
Style: clean vector-like illustration.
```

---

## Route 2 — Lab Routine Plots

### HPLC Chromatogram
```python
fig, ax = plt.subplots(figsize=(8, 4))
ax.plot(time, absorbance, 'k-', linewidth=1)
ax.fill_between(time, absorbance, alpha=0.1)
# Peak annotation with retention times
```

### Kinetic Progress Curves
```python
# Multi-condition overlay with SEM shading
for condition, df in data.items():
    ax.plot(df['time'], df['mean'], label=condition)
    ax.fill_between(df['time'], df['mean']-df['sem'], df['mean']+df['sem'], alpha=0.2)
```

### Bayesian Optimization Results
- Objective function surface (contour/3D)
- Acquisition function overlay
- Observed points with best highlighted

---

## Route 3 — Publication Multi-Panel Figures

Standards:
- Colorblind-safe palette (default: Okabe-Ito; `tab10` only if a journal demands it)
- Font: Arial or Helvetica, min 8pt axis labels; **uniform sizes across the whole figure set** (don't hardcode a smaller size for one panel's labels — see Fig5a regression in figure_aesthetics_rules.md)
- Resolution: 300 DPI (raster) or SVG (vector)
- Panel labels: `(a) (b) (c)` — **normal weight by default, not bold**. Bold only when a specific journal requires it (user/per-submission decision). No graph title / suptitle.
- **No legend title** (e.g. "Temperature"); legend in a corner (never center), `frameon=False`; if corners are crowded, raise the y-limit and place upper-right (don't move outside the axes).
  - **Legend frame fully off (260629)**: `frameon=False` AND no `facecolor='white'` patch — a white patch still occludes data even when frame is off.
  - **Donut/pie legend exception (260629)**: donut and pie charts may place the legend outside the axes to the right (`bbox_to_anchor=(1.02, 0.5), loc='center left'`) — a circle has no empty interior corners. Lint R0 must register this chart-type exemption. All non-circular charts: no external legend.
  - **Legend deduplication (260629)**: if an `ax.text` annotation or a sibling panel already labels an entity, remove it from the legend to avoid repetition. When sibling panels (c) and (d) need the same legend, add it explicitly to each — `smart_legend` does not inherit across panels.
- **Error bars in the series color, not black**; for bar charts, upward error only.
- **Bars: no outline** (`edgecolor='none'`).
- Significance bars: `*P<0.05`, `**P<0.01`, `***P<0.001`, spaced so they don't collide with data, error bars, or each other.
- **Significance text is italic**: `ns` / `P` / `n` etc. are *italic* (operators, digits, `*` roman). Never a plain `ax.text(x,y,'ns')` (renders upright) — use `stat_annot(ax, x, y, 'ns')`.
- **Measurement conditions** ("8 g DCW/L") belong in the caption or an `xlabel`/cleared corner — not floating in the data area where a tight bbox can clip them.
- **Caption: no experimental result (260629)**: captions state experimental setup and measured quantities only. Do NOT include result clauses ("peak at pH 7", "maximum at 55 °C", "enzyme showed…") — those belong in the Results body. Template: `"[Entity] [measurement] as a function of [variable]. [Conditions]. Error bars, SEM/SD, n=N."` See R3 in `figure_aesthetics_rules.md`.
- **Species italic in tick labels (260629)**: when an axis lists biological species names, genus + species epithet must be italic via mathtext: `r"$\it{Gracilariopsis}$ chorda"`. Chemical species (D-Gal, D-Glc, NAD⁺) and D-/L- stereodescriptors stay roman. Run `check_abbrev_consistency(labels)` after constructing label lists.
- **Pareto opt: predicted↔experimental connector (260629)**: when a Pareto figure includes wet-lab validation points, connect each predicted–experimental pair with `ax.plot([pred_t, exp_t], [pred_y, exp_y], '--', color=C_ANNOT, lw=0.8, zorder=1)`. See `figure_aesthetics_rules.md § Pareto optimization figures`.
- Full composition rules: `references/figure_aesthetics_rules.md` (see **R0 — Enforcement**). Helpers: `scripts/aesthetic_helpers.py`.

**🔴 R0 enforcement — the rules are a GATE, not advice (added 260626 after an audit found rules were being ignored):**
1. **Start from the template, never a blank file.** Copy `scripts/make_fig_template.py` to begin a new figure — it pre-wires the helper imports, `constrained_layout=True`, per-panel `panel_label`+`smart_legend`, the SSOT color/font accessors, and the correct `savefig`. Authoring a render script from scratch is how the rules get re-derived and forgotten.
2. **A figure is not done until it passes the lint.** After rendering, run `python scripts/figure_lint.py render_figN.py` for EVERY script and confirm **0 high-severity findings** (raw `ax.legend`, hardcoded hex/fontsize, descriptive `set_title`, missing layout manager, savefig flags, external/center legend). Nonzero exit = not done. Surface the lint result in the figure-done report.
3. **Legends only via `smart_legend(ax)`** (it measures the rendered bbox and auto-picks a data-free corner) — never `ax.legend(loc=...)`. Colors only via `series_color(name)`/`OKABE_ITO`/`NEUTRAL_PAIR`/`C_ANNOT` — never a literal `#hex`. Fonts only via `FS_*`.
4. When a **workflow** creates/modifies figures, it must run the lint per script as an automatic post-step (this is exactly the gap the user hit: "rules ignored on workflow modification").

```python
# copy make_fig_template.py first; it already imports these:
from aesthetic_helpers import smart_legend, styled_errorbar, panel_label, bar_no_edge, stat_annot, series_color
fig, axes = plt.subplots(2, 2, figsize=(7.2, 6), constrained_layout=True)  # Nature 7.2"; ONE layout mgr
# ... plot series with color=series_color('ProductA') etc. (no literal hex) ...
panel_label(axes[0,0], "a")          # normal weight
smart_legend(axes[0,0])              # AFTER data+ylim; measures bbox, corner auto, no loc=/center
stat_annot(axes[0,0], 1.0, 55, "ns") # italic ns above a significance bracket
fig.savefig('figure1.pdf', dpi=300, bbox_inches='tight', facecolor='white')
# then: python figure_lint.py make_figN.py  → must report 0 high-severity
```

---

## Route 4 — Matplotlib Fine Control

Use when exact positioning, custom tick formatters, inset axes, or twin axes are needed.

```python
ax2 = ax.twinx()
from mpl_toolkits.axes_grid1.inset_locator import inset_axes
axins = inset_axes(ax, width="40%", height="40%", loc='upper right')
ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f'{x:.1f} min'))
```

---

## Route 5 — Figure Reconstruction & Verification

Use when an existing manuscript figure must be **rebuilt from rawdata** (e.g. tidying a
figures folder, recovering a lost source script, re-rendering at journal resolution).
The deliverable is a reproducible `data.csv` + `script.py` + `figure.svg/png` per figure
that **matches the published version in both data and design**.

Requires: `numpy`, `Pillow`, `scikit-image` for the design-similarity tool. Install
with `pip install scikit-image` if missing.

### Workflow

1. **Inventory & map** — extract embedded images from the manuscript (`.docx` →
   `word/media/`), identify each figure by caption order, map figure ↔ rawdata sheet ↔
   any existing script. Save as `INVENTORY.md`.
2. **Analyze the rawdata sheet, do not guess columns.** Lab xlsx sheets are usually
   multi-stage: raw instrument output → standard-curve conversion → intermediate calc →
   **final plot block**. Open the sheet, read headers row-by-row, locate the block that
   holds the *final plotted values*. Column offsets in a draft extractor are the #1
   source of silent error — verify every one against the sheet.
3. **Extract** `data.csv` with explicit, self-documenting cell coordinates.
4. **Render** `script.py` reading `data.csv`, importing the shared style preset.
   Save with the **reference's figsize** (read it off the embedded image's width:height
   ratio) — otherwise `figure_compare.py` will flag AR mismatch and the SSIM penalty
   will be from stretch, not design.
5. **Verify — two independent checks (see below). Never report "match" from eyeballing alone.**
6. Write `figure_meta.json` (provenance) and a `REBUILD_REPORT.md` with the
   verification table.

> Full protocol: `references/figure_verification.md`. Tool: `scripts/figure_compare.py`.

### Verification — data ✕ design, measured

A figure can look right but plot wrong numbers, or plot right numbers but look wrong.
Check both, separately, with numbers — not "looks like it".

**(a) Data integrity** — the reconstructed series must equal the rawdata.
- Re-read the source sheet independently and assert `data.csv` values match
  (tolerance e.g. rel 1e-6 for direct copies, 1e-3 for recomputed quantities).
- Spot-check 2-3 anchor points against the embedded image's readable axis values.
- This is the check that actually matters for correctness. A figure that fails here
  is wrong even at SSIM 0.99.

**(b) Design similarity** — quantify, don't eyeball. Use `scripts/figure_compare.py`:
- SSIM (grayscale structural similarity) + normalized pixel MAE vs the embedded reference.
- Output also prints the **source size + aspect ratio** of both inputs, and flags
  AR mismatch when the ratio differs by >10 % — fix `figsize` and re-render before
  blaming design drift.
- Interpretation (empirical, from biocatalysis 2D plots):
  - **SSIM ≥ 0.85** — high; near-indistinguishable.
  - **0.70–0.85** — good; minor cosmetic drift (marker size, label spacing).
  - **0.55–0.70** — moderate; inspect — usually a real design gap (missing broken-axis,
    box vs L-frame spines, wrong panel-label size, legend overlap).
  - **< 0.55** — low. For **2D plots** this means a genuine mismatch — fix it.
    For **3D surface plots** low SSIM is expected (viewing angle / render engine differ)
    and is *not* by itself a defect — confirm via data integrity instead.
- EMF/WMF/SVG/EPS/PDF references can't be rasterized here — the tool refuses
  with an explicit message. Fall back to data integrity + structural panel-count check,
  or extract the chart on the Windows side (Word/PowerPoint → Save as Picture → PNG). This WSL has no EMF rasterizer installed (verified 2026-05-23 — libreoffice/inkscape/ImageMagick all absent).

> **Lesson (a multi-figure rebuild):** an autonomous agent reported all 16
> figures as "match" by visual inspection. SSIM later showed 2D plots at 0.79–0.82 (fine)
> but one supplementary figure at 0.60 — a real gap: the reference used a **broken y-axis** and **4-side box
> spines**, the rebuild used a continuous axis and L-frame. Eyeballing missed it; SSIM
> caught it. Always run the quantitative check and record the score per figure.

### Common design-drift items to check explicitly

When SSIM lands in the moderate band, these are the usual culprits — verify each against
the reference before calling a figure done:
- broken / discontinuous axis (`brokenaxes`, or two stacked axes)
- spine style: 4-side box vs L-frame (top/right hidden) — match the *reference*, not the
  skill default
- panel label size/weight (`a` vs **A**, small vs large bold)
- axis label ↔ first tick collision (two-row category labels especially)
- legend position overlapping data
- twin-axis range and which series sits on which axis
- marker fill/edge, line dash pattern for simulated-vs-experimental overlays
- **figsize / aspect-ratio** — the tool flags AR>1.10× automatically; align to reference

### Figure-type quick guide

`references/figure_verification.md` §5 has a per-type table (2D line/scatter, bar,
3D surface, gel, HPLC, scheme, EMF chart, graphical abstract) showing when SSIM is
informative and when to lean on data-integrity only. Consult it before scoring an
unusual figure type — the score band's meaning differs.

---

## Journal Size Reference

| Journal | Max width | Format |
|---|---|---|
| Nature / Science | 89 mm (1-col), 183 mm (2-col) | PDF/EPS |
| ACS | 3.25" (1-col), 7" (2-col) | TIFF 300 DPI |
| Elsevier | 90 mm, 190 mm | EPS/PDF |
| Angewandte | 8.3 cm, 17.5 cm | PDF |

---

## Bundled references & scripts

- `references/figure_aesthetics_rules.md` — **graphic composition SSOT** (R1 no-overlap / R2 no graph title / R3 no redundant text / R4 controlled layout); separate axis from color/font tokens and caption-text rules
- `references/plot_style_sigmaplot_prism.md` — SigmaPlot / Prism style presets, palettes
- `references/patterns_260527.md` — 7 recurring multi-panel figure patterns (errorbar zorder split, 3D colorbar pad, label collision, fit-line extrapolation, EF g/g, subplot title)
- `references/figure_verification.md` — **Route 5** rebuild & verification protocol
- `references/style_tokens.json`, `plot_style_tokens.json` — style token presets
- `scripts/figure_advisor.py` — **recommends the chart type AND the panel layout before you plot**. `chart` mode ranks bar / grouped-bar / line / scatter / donut / stacked-bar / contour-3D / box from a small `DataProfile` (x_kind, n_series, n_groups, repeats, is_tradeoff, is_part_of_whole, …) with a score, a one-line rationale, and the gotchas to watch — rule-based and auditable. `layout` mode ranks grid layouts for N panels and renders labeled placeholder previews. Run this FIRST when starting a new figure.
- `scripts/aesthetic_helpers.py` — drop-in helpers enforcing figure_aesthetics_rules.md: `smart_legend` (corner-preference, no title, y-headroom not outside-axes), `styled_errorbar` (series-colored, top-only for bars), `panel_label` (normal weight), `bar_no_edge`, `darken`, **`stat_annot` / `significance_italic`** (italic ns/P/n on-figure significance text — never a plain upright 'ns'), and **`check_abbrev_consistency`** (catches mixing an abbreviation with a full name for sibling sugars, e.g. "D-Gal" next to "Glucose" → use "D-Glc")
- `scripts/lab_plot.py` — HPLC / kinetic / dose-response / BO-surface / Pareto
  routine plots, all preset-aware (`recommended` / `sigmaplot` / `prism`).
  `python scripts/lab_plot.py --demo --out <dir>` renders one of every plot type
  so you can eyeball the presets before committing to one.
- `scripts/figure_compare.py` — **Route 5** SSIM/MAE design-similarity check
- `scripts/scheme_render.py`, `pfd_render.py`, `ga_compose.py` — schematic rendering

## Replaces

- `deprecated/scientific-schematics` — AI schematic generation with iterative review
- `deprecated/scientific-visualization` — publication multi-panel, significance annotations
- `deprecated/matplotlib` — low-level customization
- `deprecated/lab-viz` — HPLC, kinetic, BO routine plots
