# Figure Reconstruction — Verification Protocol

> Compiled: 2026-05-23 | publication-figures skill, Route 5
> Scope: how to verify a figure rebuilt from rawdata actually matches the
> published version — in **data** and in **design**, with numbers, not eyeballing.

This reference exists because of a concrete failure mode (see §7). An autonomous
agent rebuilt 16 figures and reported every one as "match" from visual inspection.
A later quantitative pass found real design gaps it had missed. Verification must
be measured.

---

## 1. Two checks, independent

A reconstructed figure has two ways to be wrong, and they fail independently:

| | What it means | How it fails silently |
|---|---|---|
| **Data integrity** | plotted series == rawdata values | wrong sheet block, 1-column offset, unit confusion (s vs h), recompute error |
| **Design similarity** | looks like the published figure | missing broken-axis, box vs L-frame, panel-label size, legend overlap |

A figure can pass one and fail the other. SSIM 0.99 with the wrong column is still
wrong. Correct numbers with a continuous axis where the original was broken is still
a mismatch a reviewer will notice. **Run both.**

Data integrity is the one that matters for correctness. Design similarity is what
gets a figure accepted without a revision request.

---

## 2. Data-integrity check

Goal: prove `data.csv` equals the rawdata, and the figure plots `data.csv`.

1. **Re-read the source independently.** Open the rawdata sheet a second time (fresh
   openpyxl read, explicit cell coordinates) and assert the extracted values match.
   - direct copies → relative tolerance ~1e-6
   - recomputed quantities (yield, ee, ratios) → ~1e-3, and document the formula
2. **Anchor points vs the embedded image.** Pick 2-3 points whose value is readable
   off the published figure's axes (a curve endpoint, a bar height, a peak). Confirm
   `data.csv` agrees within reading precision.
3. **Sanity bounds.** Concentrations ≥ 0, yields ≤ 100 %, monotonic where the
   chemistry requires it, mass balance where it applies.
4. **Row/point count.** N time points, N bars, N panels — matches the figure.

If any of these fail, the figure is wrong regardless of how good it looks.

### Multi-stage sheet trap

Lab xlsx sheets stage data: raw instrument output → standard-curve conversion →
intermediate calc → **final plot block**. The final block is often far down the
sheet or in a separate column group, and an extractor written against the first
block it finds will silently pull pre-conversion numbers. Always locate the block
that holds the *final plotted values* — read headers row-by-row, do not assume.

Column-offset-by-one is the single most common silent error. Verify every column
index against the sheet header, not against a draft script.

---

## 3. Design-similarity check

Goal: quantify how close the rebuild looks to the published figure.

Tool: `scripts/figure_compare.py` — SSIM (grayscale structural similarity) +
normalized pixel MAE. Requires `numpy`, `Pillow`, `scikit-image`
(`pip install scikit-image`).

```bash
python scripts/figure_compare.py recon.png reference.png      # one pair
python scripts/figure_compare.py --batch /path/to/figures     # F_* unit folders
python scripts/figure_compare.py --batch /path/to/figures --json out.json
```

The single-pair output now also prints the **source sizes and aspect ratios** of
both inputs and flags **AR mismatch** when the ratio differs by >10 %. If you see
that flag, a low SSIM may reflect stretch-during-resize rather than a real design
difference — re-save the rebuild at the reference's `figsize`.

The `--json` option (verified 2026-05-23) writes a machine-readable summary
suitable for auto-generating `REBUILD_REPORT.md`: per-figure
`{figure, status, ssim, mae, verdict, ar_ratio, ar_warn, src_recon, src_ref}` plus
top-level `mean_ssim` and `n_below_0.70`.

### SSIM interpretation (empirical, biocatalysis 2D plots)

| SSIM | Band | Action |
|---|---|---|
| ≥ 0.85 | high | near-indistinguishable; done |
| 0.70–0.85 | good | minor cosmetic drift (marker size, label spacing); usually fine |
| 0.55–0.70 | moderate | **inspect** — usually a real design gap, see §4 checklist |
| < 0.55 | low | 2D plot → genuine mismatch, fix it. 3D surface → expected, see below |

### 3D surfaces score low — that is normal

3D surface/wireframe plots (`plot_surface`, RSM, response landscapes) render
differently between matplotlib and Origin/Excel/SigmaPlot: viewing azimuth and
elevation, grid line weight, colorbar placement all differ. SSIM 0.45–0.55 is
expected and is **not** by itself a defect. For 3D figures, lean on the
data-integrity check (§2) and a structural panel-count check instead.

### Vector references (EMF/WMF/SVG/EPS/PDF)

`.emf` (Windows metafile, common output from Excel charts embedded in Word) and
other vector formats cannot be rasterized by PIL/skimage. `figure_compare.py`
detects them by extension and refuses with an explicit message — it no longer
crashes silently.

**This user's WSL has no working EMF rasterizer.** Verified 2026-05-23:
`libreoffice`, `inkscape`, ImageMagick `convert/magick` are all absent. Don't
recommend a command-line conversion on this machine; it will fail. Two paths
that actually work:

1. **Skip SSIM, rely on data-integrity + structural check** (panel count, axis
   labels, series count). State this explicitly in `REBUILD_REPORT.md`.
2. **Extract the chart on the Windows side.** Open the parent `.docx` in Word
   (or the source `.xlsx` in Excel), right-click the chart → "Save as Picture
   → PNG". Drop that PNG next to the reconstruction and run `figure_compare.py`
   normally.

If a future cycle installs `libreoffice` on this WSL, the headless conversion
becomes available — re-verify before recommending it.

### Image-size and aspect-ratio considerations

- `figure_compare.py` resizes both inputs to a common width = `min(recon.w, ref.w, 1000)` px
  and projects to recon's aspect ratio (LANCZOS). The 1000-px cap caps runtime and
  reduces SSIM noise from tiny pixel jitter.
- For panorama refs (>4000 px wide composites — multi-panel graphical abstracts,
  thesis figures) the cap loses fine text detail and can push SSIM down by ~0.03–0.05.
  This is acceptable for a similarity *signal*; if a panorama lands in the moderate
  band, treat it as inconclusive and inspect manually rather than chasing the score.
- The AR-mismatch warning catches the common case where the rebuild was saved
  at a generic 7×5" figsize but the published figure is 3×3" or 10×3". Fix the
  `figsize=` argument and re-render before deciding the design has drifted.
- The script also refuses tiny inputs (resized to <7 px each side) with a clear
  message — figures should be saved at publication size (≥300 px wide minimum).

---

## 4. Common design-drift items

When SSIM lands in the moderate band, check these against the reference before
calling a figure done. Match the *reference*, not a generic house style.

- **Broken / discontinuous axis** — reference splits the y-range (e.g. 0–0.5 then
  1.5–1.75); a continuous-axis rebuild looks very different. Use `brokenaxes` or
  two stacked axes.
- **Spine style** — 4-side box vs L-frame (top/right hidden). The skill default is
  L-frame, but if the published figure uses a full box, match the box.
- **Panel label size/weight** — `a` small vs **A** large bold. Match the manuscript.
- **Axis label ↔ first tick collision** — two-row category labels (e.g. "Initial
  substrate" / "Initial cosolvent" under each bar group) easily overlap the axis title.
- **Legend position** — overlapping data points; `bbox_to_anchor` to clear it.
- **Twin-axis** — which series on which axis, and the secondary axis range.
- **Sim-vs-exp overlays** — dashed line for simulation, filled markers for data
  (or whatever the reference uses) — keep the convention consistent across panels.
- **figsize mismatch** — flagged automatically by `figure_compare.py` when the
  aspect ratio of recon and ref differ by >10 %. Read off the reference image's
  width:height ratio, set `figsize=(w_in, h_in)` to match, re-save, re-score.

---

## 5. Figure-type guidance — what verification means for each kind

Verified against a test pool of real manuscript figures:
TIFF/JPEG/PNG/EMF inputs across 7 manuscripts, including time-course, kinetic,
bar+twin-axis, 3D surface, gel SDS-PAGE, HPLC chromatogram, graphical abstract,
ChemDraw schemes, and large panorama composites.

| Figure type | SSIM useful? | Verification strategy |
|---|---|---|
| **Line / scatter / time-course (2D)** | yes (0.70+ expected) | SSIM + anchor-point data check; AR-flag must be clear |
| **Bar (+ twin-axis)** | yes (0.65+ expected) | SSIM, but expect penalty from two-row category labels and twin-axis range; check §4 items |
| **3D surface / RSM** | weak (0.45–0.55 expected) | **skip** SSIM band judgment; data-integrity + structural check only |
| **Heatmap / 2D field** | yes (0.70+ expected) | SSIM, check colormap matches reference (viridis vs jet etc.) |
| **Gel image / SDS-PAGE (photo)** | yes, but as a photo, not a plot | SSIM compares image content; data integrity = densitometry table if available, else N/A. Treat 0.85+ as match; lower = re-cropped or different exposure |
| **HPLC chromatogram** | yes (0.75+ expected for clean traces) | SSIM + check retention-time alignment by reading peak x-positions off both images |
| **Scheme / reaction arrow (ChemDraw, vector)** | no | EMF/SVG → §3 vector handling. SSIM not meaningful on chemical structures; data integrity = "structures match the manuscript" by visual diff only |
| **Graphical abstract / TOC** | sometimes | If a single composite raster: SSIM at 0.70+. If panorama (>4000 px) or vector composite: skip score, inspect panels individually |
| **EMF chart (Excel→Word)** | no (raw) | Extract chart on Windows side ("Save as Picture") → PNG → then compare. Common pattern in chart-heavy manuscript docx |

If your figure type isn't in this table and you're not sure whether SSIM is
informative, run the comparison and inspect — the AR flag, the size printout, and
the verdict band together usually clarify within seconds.

---

## 6. Report format

`REBUILD_REPORT.md` must contain a per-figure table with **measured** results.
The JSON output from `figure_compare.py --batch --json` is the easiest way to
generate this table programmatically.

| Figure | Sheet block | Data integrity | SSIM | AR flag | Design notes |
|---|---|---|---|---|---|
| Fig 1 | r37-46 final block | pass (rel<1e-6) | 0.79 good | yes (1.12×) | rebuild figsize too wide; re-save at 5.1×4.1 in |
| Fig S8 | full sheet | pass | 0.60 moderate | no | ref uses broken y-axis + box spines; rebuild used continuous + L-frame |
| Fig S5 | full sheet | pass | EMF ref — structural only | n/a | 6-panel layout confirmed |

Never write "match" without the number behind it. "match" from eyeballing is the
failure this protocol exists to prevent.

---

## 7. Case study — a multi-figure rebuild

16 manuscript figures rebuilt from one rawdata xlsx by an autonomous agent.

- Agent reported all 16 as "match" by visual inspection.
- Quantitative pass: 2D line/scatter plots SSIM 0.79–0.82 (genuinely fine);
  bar/twin-axis and 3D lower.
- **Real gap found:** one supplementary figure at SSIM 0.60 — the published reference used a
  **broken y-axis** (cofactor panel) and **4-side box spines**; the rebuild used a
  continuous axis and L-frame. The data was correct; the design was not. Eyeballing
  missed it; SSIM flagged it for inspection.
- 3D surfaces scored 0.45–0.55 — expected render-engine
  difference, confirmed correct via data integrity, not treated as defects.
- **AR-flag side observation:** the batch run after adding the
  AR-flag showed 11/14 figures with AR>1.10 between rebuild and reference.
  Part of the moderate-band SSIM penalty traces to figsize choice, not design. A
  follow-up cycle should align rebuild figsize to each reference before scoring.

Takeaway baked into Route 5: **measure both axes of correctness, record the number,
treat 3D low scores as normal, watch the AR flag, and never trust "looks right".**
