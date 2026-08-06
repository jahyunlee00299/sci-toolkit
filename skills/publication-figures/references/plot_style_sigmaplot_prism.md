# SigmaPlot / GraphPad Prism style — figure conventions

> Compiled: 2026-05-18  |  Project: publication-figures / [C] Data figures sub-project
> Scope: Apply SigmaPlot (Systat/Inpixon) and GraphPad Prism default plot aesthetics to
> matplotlib-generated lab figures (kinetic time courses, HPLC chromatograms, BO surfaces,
> bar+error, dose-response). Targets: biochemistry / pharmacology / enzyme cascade venues.

---

## 1. Compared with matplotlib default

| Element                  | matplotlib default | SigmaPlot default | GraphPad Prism default | Recommendation (this pipeline) |
|--------------------------|--------------------|-------------------|------------------------|-----------------------------------|
| Font family              | DejaVu Sans        | Arial             | Arial                  | **Arial**                         |
| Body / axis-label pt     | 10                 | 9–10              | 10–12 (bold default in ggprism mimic) | **9** (10 for posters)        |
| Tick-label pt            | 10                 | 8                 | 8–10                   | **8**                             |
| Title pt                 | 12                 | 10–12             | 12 (bold)              | **10**                            |
| Font weight (axis title) | normal             | normal            | **bold** (ggprism)     | normal (we keep body weight)      |
| Axis line width (pt)     | 0.8                | 1.0               | 1.5                    | **1.0** (1.5 for posters)         |
| Tick length (pt)         | 3.5                | 4                 | 5                      | **4**                             |
| Tick width (pt)          | 0.8                | 1.0               | 1.5                    | **1.0**                           |
| Tick direction           | out                | out               | **in** (Prism default)     | **out** (more readable in print)  |
| Top / right spine        | shown              | hidden (L-frame)  | hidden (L-frame)       | **hidden** (open frame)           |
| Frame box                | none               | none (L-shape)    | none (L-shape)         | **none** (L-shape)                |
| Default marker           | filled circle (o)  | open square       | filled circle          | **filled circle, size 5 pt**      |
| Marker size (pt)         | 6                  | 5                 | 6                      | **5**                             |
| Default line width (pt)  | 1.5                | 1.5               | 2.0                    | **1.5**                           |
| Fit curve style          | solid              | solid             | solid                  | **solid** (dashed only for extrap.) |
| Error bar cap width (pt) | 0 (none)           | 3                 | 4                      | **3** (visible but unobtrusive)   |
| Error bar line width (pt)| 1.0                | 1.0               | 1.5                    | **1.0**                           |
| Color scheme             | tab10              | manual / 9-color  | "Colors" (20 hues)     | **Wong / Okabe-Ito** (colorblind-safe) |
| Legend frame             | yes (rounded box)  | no                | no                     | **no** (`frameon=False`)          |
| Legend location          | upper right (in)   | top / floating    | top / floating         | **upper right inside or top, no frame** |
| Significance markers     | none               | none (manual)     | `*`/`**`/`***` w/ bracket | **bracket + stars** when present  |
| Gridlines                | none               | none (optional)   | none                   | **none** (faint y-grid OK for bar) |
| Background               | white              | white             | white                  | **white**                         |

Source notes for the columns:

- matplotlib defaults: `matplotlib.rcParamsDefault` (v3.9, 2024).
- SigmaPlot defaults: Inpixon/Grafiti "Graph properties" panel (SigmaPlot 14.5/15 user guide) — symbols/lines/bars panels and tutorial PDF (Alfasoft 2021).
- Prism defaults: GraphPad official guides (axis numbering, font, colors), and the `ggprism` R package which reproduces Prism defaults from the developer's reverse-engineering. `ggprism::theme_prism()` uses `base_size = 14` and bold text by default; downscaled here to journal sizes.

---

## 2. SigmaPlot specifics

Default behaviour (per SigmaPlot 14.5 user guide and Graph Style Gallery):

- **Frame style**: L-shape (bottom + left only). Top/right spines hidden by default.
- **Tick direction**: outward (`out`).
- **Tick length** ≈ 0.05 in (~4 pt). Major and minor adjustable separately.
- **Default symbol cycle**: filled circle → open circle → filled triangle (down) → open triangle …
  Note: many published "SigmaPlot figures" use **open squares with thin black lines** because
  it was historically the most contrast-friendly choice on monochrome print.
- **Default line plot**: connect-the-dots polyline with markers ON; markers OFF for fit
  curves overlaid via Regression Wizard.
- **Error bars**: horizontal cap segments; cap width independent of marker size; default
  cap end ≈ 3 pt; visible above/below symbol.
- **Color scheme**: SigmaPlot uses a small built-in named-color picker (16 standard names
  plus user-defined). There is no broad palette concept — color cycling is **manual** when
  you add new curves. This is why monochrome (black) is overwhelmingly common in SigmaPlot
  journal figures.
- **Default font**: Arial 10 pt for axis labels and tick numbers (per Graph Defaults dialog).
- **Document size**: US Letter; default plot area ≈ 3.5 × 2.8 in (single column).

Citations:

- [SigmaPlot 14.5 User's Guide (Alfasoft mirror)](https://www.alfasoft.com/docs/sigmaplot-145-user-guide.pdf)
- [A Walk Through SigmaPlot (Alfasoft tutorial)](https://www.alfasoft.com/docs/sigmaplot-tutorial.pdf)
- [SigmaPlot 5.0 User's Guide (legacy, archived)](http://kfrserver.natur.cuni.cz/obecne/soubory/Sigmaplot/UserGuide.pdf)
- [SigmaPlot graphing features (systatsoftware.com)](https://systatsoftware.com/sigmaplot/graphing-features)
- [Error Bar Directions (Systat tech tip)](http://www.systat.de/TT201507/ErrorBarEN.pdf)

---

## 3. GraphPad Prism specifics

Default behaviour (per Prism 10/11 user guide and the `ggprism` R reproduction):

- **Frame style**: L-shape (bottom + left only). Prism calls this "Plain frame, no offset".
- **Tick direction**: **inward** (Prism's most distinctive aesthetic).
- **Tick length** ≈ 5 pt (longer than SigmaPlot's 4 pt).
- **Axis line width**: 1.5 pt — thicker than SigmaPlot/matplotlib; gives Prism figures
  their characteristic "bold-axis" feel.
- **Default font**: Arial. Default sizes vary by element: axis title 14 pt, axis numbering
  11 pt, legend 11 pt (these are screen defaults; export to 4-inch single-column gives
  ~10/8/8 in the figure when scaled).
- **Default marker**: filled circle, size 6 pt.
- **Error bars**: vertical with prominent caps (~4 pt width), 1.5-pt line. By default Prism
  computes mean ± SEM if you enter replicates, but allows mean ± SD or 95% CI.
- **Fit curve**: solid black line; Prism overlays the best-fit through the markers.
- **Significance markers**: `*` (p<0.05), `**` (p<0.01), `***` (p<0.001), `****` (p<0.0001),
  with bracket spanning compared groups. Asterisk + ns notation is the Prism trademark.
- **Color scheme**: built-in named schemes. Default for new graphs is "Colors" (20 hues).
  Recent additions (Prism 8.1+): Floral, Colorblind Safe, Waves, Starry, Pearl.
  Older built-in: Spring, Mustard, Pastels, Warm Pastels, Prism Dark, Prism Light,
  Floral, Blueprint, Candy Bright, Viridis.

Citations:

- [Prism 11 Format Axes (frame and axes)](https://www.graphpad.com/guides/prism/latest/user-guide/formataxes.htm)
- [Prism 11 Fonts](https://www.graphpad.com/guides/prism/latest/user-guide/fonts.htm)
- [Prism 11 Preferences / Standardizing Prism Preferences (FAQ 1448)](https://www.graphpad.com/support/faq/standardizing-prism-preferences/)
- [Prism new color schemes (FAQ 2151)](https://www.graphpad.com/support/faq/prism-color-schemes/)
- [Prism 11 Colors page](https://www.graphpad.com/guides/prism/latest/user-guide/colors.htm)
- [ggprism: Themes vignette](https://cran.r-project.org/web/packages/ggprism/vignettes/themes.html)
- [ggprism: Colour, Fill, and Shape Palettes](https://csdaw.github.io/ggprism/articles/colours.html)
- [ggprism: prism_colour_pal reference](https://csdaw.github.io/ggprism/reference/prism_colour_pal.html)

---

## 4. Patterns observed in published figures

Selected literature where the methods section explicitly names SigmaPlot or Prism. Used
to validate the defaults above against actual journal output.

| # | Title (short) | Tool noted | Field / journal | Source URL |
|---|---------------|------------|------------------|------------|
| 1 | Prism 11 Curve Fitting Guide — enzyme kinetics worked example (Michaelis–Menten, triplicate, mean+SEM) | Prism | Enzymology tutorial | https://www.graphpad.com/guides/prism/latest/curve-fitting/reg_example_enzyme_kinetics.htm |
| 2 | Prism Step-by-Step Examples — dose-response curve, IC50, with significance brackets | Prism | Pharmacology tutorial | https://holdsworthwiki.robarts.ca/files/graphpad_prism/prismexamples.pdf |
| 3 | Mak et al. 2024 — Enzyme Kinetics Analysis online tool, validation figures using Prism | Prism | Biochem Mol Biol Education | https://iubmb.onlinelibrary.wiley.com/doi/full/10.1002/bmb.21823 |
| 4 | Biochem Lab Prism Kinetics Instructions (USD F21) — standard plotting conventions for student labs | Prism | Teaching biochem | https://home.sandiego.edu/~josephprovost/Biochem%20Lab%20GraphPad%20Prism%20Kinetics%20Instructions%20F21.pdf |
| 5 | SigmaPlot Enzyme Kinetics Module — featured figures (Lineweaver-Burk, Hanes, Eadie-Hofstee) | SigmaPlot | Industry product sheet | https://www.pharmaceuticalonline.com/doc/product-sheet-sigmaplot-mdash-enzyme-kinetics-0001 |
| 6 | "Interactive biocatalysis achieved by driving enzyme cascades inside a porous conducting material" (PMC 2024) — relevant cascade-figure conventions | unspecified (likely Prism) | Nature Comm / PMC | https://pmc.ncbi.nlm.nih.gov/articles/PMC11165005/ |
| 7 | "One-pot chemo- and photo-enzymatic linear cascade processes" Chem Soc Rev 2024 — TOC/cascade scheme conventions | unspecified | RSC Chem Soc Rev | https://pubs.rsc.org/en/content/articlehtml/2024/cs/d3cs00595j |

Common visual patterns extracted from these (and broader Pharmacology/Biochem literature):

- **Markers**: filled circle dominant for Prism-derived plots; open square / open triangle
  common for SigmaPlot-derived plots (legacy monochrome convention).
- **Fit lines**: solid for the model curve through the markers, never dashed unless the
  curve is extrapolation. Dashed/dotted reserved for confidence band edges or extrapolation.
- **Error bars**: SEM almost universal in pharmacology/enzyme papers (Prism users);
  SD slightly more common in chemistry/biocatalysis (SigmaPlot users).
- **Stat brackets**: `*/**/***/****` with horizontal bracket — almost exclusively Prism.
  SigmaPlot figures generally state p-values in legends/captions, no brackets.
- **Axis ticks inside vs outside**: pharmacology figures (Prism) → ticks inside;
  biocatalysis/applied-chem figures (SigmaPlot or in-house matplotlib) → ticks outside.
- **Color use**: monochrome single-curve plots dominate in classic SigmaPlot output;
  multi-color (3–5 hues, Prism "Colors" / "Floral") is the Prism standard.

---

## 5. Color palettes

### 5.1 SigmaPlot (de-facto)

SigmaPlot has no built-in multi-curve palette, so figures typically use 16 named colors
in this rough order (manual selection by users, observed conventions):

```
1. Black           #000000
2. Red             #FF0000   (occasionally darker #C00000)
3. Blue            #0000FF   (occasionally darker #1F4E79)
4. Green           #008000
5. Magenta/Purple  #800080
6. Brown/Orange    #B45F00
7. Gray            #808080
8. Dark cyan       #008080
```

These are the standard Windows 16-color names; SigmaPlot picks them up unchanged.

### 5.2 Prism

Prism's default palette is internally called **"Colors"** (20 hues). The `ggprism`
reproduction gives access to many named palettes. Key sets:

```
floral        : 12 colors, blue/purple/red/green family
pastels       :  9 colors, low saturation
prism_dark    : 10 colors, saturated for white background
prism_light   : 10 colors, lighter complementary set
blueprint     :  9 colors, blue-dominant scientific
candy_bright  :  9 colors, high saturation
colorblind_safe (Prism 8.1+): designed for protan/deutan/tritan accessibility
viridis       :  6 colors (Prism integrated viridis)
```

Exact HEX values for these palettes are stored as binary R data inside ggprism
(`ggprism::ggprism_data$colour_palettes`) and are not published as plain text on
the package documentation site; to retrieve them precisely, install ggprism and call
`prism_colour_pal("floral")(12)` etc.

One verified example from documentation: `prism_colour_pal("starry")(4)` returns
`#000000, #042E3D, #765A22, #44726D`.

### 5.3 Recommended for our biocatalysis pipeline — Wong / Okabe-Ito (Nature Methods 2011)

Colorblind-safe, peer-reviewed, widely accepted in cell-bio / biocatalysis venues.

```
Black           #000000
Orange          #E69F00
Sky Blue        #56B4E9
Bluish Green    #009E73
Yellow          #F0E442
Blue            #0072B2
Vermillion      #D55E00
Reddish Purple  #CC79A7
```

Source: Wong B. *Color blindness*. Nature Methods 8, 441 (2011). DOI: 10.1038/nmeth.1618.
Mirrored in many Python/R packages. See also Krzywinski BC Cancer Genome Centre palette
page: https://mk.bcgsc.ca/colorblind/palettes.mhtml

For our lab `plot_style_tokens.json`, the Wong palette is encoded as the
`recommended.palette` block, and SigmaPlot / Prism palettes are encoded as separate
presets for direct stylistic emulation.

---

## 6. matplotlib `rcParams` snippets

### 6.1 SigmaPlot-emulating preset

```python
RC_SIGMAPLOT = {
    'font.family': 'Arial',
    'font.size': 9,
    'axes.titlesize': 10,
    'axes.labelsize': 9,
    'xtick.labelsize': 8,
    'ytick.labelsize': 8,
    'legend.fontsize': 8,
    'axes.linewidth': 1.0,
    'axes.spines.top': False,
    'axes.spines.right': False,
    'xtick.direction': 'out',
    'ytick.direction': 'out',
    'xtick.major.size': 4.0,
    'ytick.major.size': 4.0,
    'xtick.minor.size': 2.0,
    'ytick.minor.size': 2.0,
    'xtick.major.width': 1.0,
    'ytick.major.width': 1.0,
    'lines.linewidth': 1.5,
    'lines.markersize': 5,
    'lines.markeredgewidth': 1.0,
    'errorbar.capsize': 3.0,
    'legend.frameon': False,
    'legend.loc': 'best',
    'figure.dpi': 150,
    'savefig.dpi': 600,
    'pdf.fonttype': 42,
    'ps.fonttype': 42,
    'axes.prop_cycle': (
        "cycler('color', ['#000000','#FF0000','#0000FF','#008000',"
        "'#800080','#B45F00','#808080','#008080'])"
    ),
}
```

### 6.2 GraphPad Prism-emulating preset

```python
RC_PRISM = {
    'font.family': 'Arial',
    'font.size': 10,
    'axes.titlesize': 12,
    'axes.titleweight': 'bold',
    'axes.labelsize': 10,
    'axes.labelweight': 'bold',
    'xtick.labelsize': 9,
    'ytick.labelsize': 9,
    'legend.fontsize': 9,
    'axes.linewidth': 1.5,
    'axes.spines.top': False,
    'axes.spines.right': False,
    'xtick.direction': 'in',
    'ytick.direction': 'in',
    'xtick.major.size': 5.0,
    'ytick.major.size': 5.0,
    'xtick.minor.size': 3.0,
    'ytick.minor.size': 3.0,
    'xtick.major.width': 1.5,
    'ytick.major.width': 1.5,
    'lines.linewidth': 2.0,
    'lines.markersize': 6,
    'lines.markeredgewidth': 1.5,
    'errorbar.capsize': 4.0,
    'legend.frameon': False,
    'legend.loc': 'best',
    'figure.dpi': 150,
    'savefig.dpi': 600,
    'pdf.fonttype': 42,
    'ps.fonttype': 42,
    'axes.prop_cycle': (
        "cycler('color', ['#1E77B4','#FF7F0E','#2CA02C','#D62728',"
        "'#9467BD','#8C564B','#E377C2','#7F7F7F','#BCBD22','#17BECF'])"
    ),
}
```

(The 10-hue cycler is an approximation of Prism "Colors" using matplotlib's tab10 —
exact Prism hex values are proprietary; this preserves the perceptual feel.)

#### Making matplotlib actually *read* as Prism (beyond rcParams)

The rcParams above set fonts/axes/ticks, but a plot still looks "matplotlib-ish" until you
add the per-artist touches Prism applies by default. Confirmed in practice on a multi-panel
manuscript figure set:

- **Marker edge** — Prism markers have a thin contrasting outline. Set
  `markeredgecolor="white"` (or black on light fills) with `markeredgewidth≈1.3`. Without it,
  overlapping markers smear together and the plot looks flat.
- **Minor ticks** — Prism shows minor ticks by default. Add
  `ax.xaxis.set_minor_locator(AutoMinorLocator(2))` (and y), `tick_params(which="minor",
  direction="in")`. On a categorical (bar) axis, suppress the *category*-axis minor ticks
  (`NullLocator`) and keep them only on the value axis.
- **Longer, heavier ticks** — Prism ticks are ~6 pt and ~1.6 pt wide, noticeably longer than
  matplotlib's default; this is a big part of the "Prism look".
- **Tight value axis** — Prism starts the axis at the data (no stray left margin):
  `ax.margins(x=0)` on the value side. **But not on a categorical (bar) axis** — bars need a
  small symmetric gap so the first/last bar doesn't crowd the spine (`ax.margins(x≈0.04)` or
  an explicit `set_xlim(-0.6, n-0.4)`). Tight-x is for continuous line/scatter axes only.
- **Thicker series lines** (~2.2 pt) and slightly larger markers (~7 pt).

These are wired into `scripts/aesthetic_helpers.py` (`panel_label`, `styled_errorbar`) and the
theme pattern; a bare `RC_PRISM` alone is *not* enough to look like Prism.

### 6.3 Recommended preset (our lab default)

```python
RC_RECOMMENDED = {
    'font.family': 'Arial',
    'font.size': 9,
    'axes.titlesize': 10,
    'axes.labelsize': 9,
    'xtick.labelsize': 8,
    'ytick.labelsize': 8,
    'legend.fontsize': 8,
    'axes.linewidth': 1.0,
    'axes.spines.top': False,
    'axes.spines.right': False,
    'xtick.direction': 'out',
    'ytick.direction': 'out',
    'xtick.major.size': 4.0,
    'ytick.major.size': 4.0,
    'xtick.minor.size': 2.0,
    'ytick.minor.size': 2.0,
    'xtick.major.width': 1.0,
    'ytick.major.width': 1.0,
    'lines.linewidth': 1.5,
    'lines.markersize': 5,
    'lines.markeredgewidth': 1.0,
    'errorbar.capsize': 3.0,
    'legend.frameon': False,
    'legend.loc': 'best',
    'figure.dpi': 150,
    'savefig.dpi': 600,
    'pdf.fonttype': 42,
    'ps.fonttype': 42,
    'axes.unicode_minus': False,
    'axes.prop_cycle': (
        "cycler('color', ['#000000','#E69F00','#56B4E9','#009E73',"
        "'#F0E442','#0072B2','#D55E00','#CC79A7'])"
    ),
}
```

Import these presets directly in your own plotting script as
`from publication_figures.references.plot_style_tokens import RC_PRISM, RC_SIGMAPLOT, RC_RECOMMENDED`
after wiring the JSON file into the Python loader.

`scripts/lab_plot.py` already consumes these presets — pass `preset="prism"`
(or `"sigmaplot"` / `"recommended"`) to any of its plot functions, or run
`python scripts/lab_plot.py --demo --out <dir>` to see every preset side by side.

---

## 7. Decision guide for our pipeline

| Figure type | Preset | Notes |
|-------------|--------|-------|
| Kinetic time course (single enzyme) | RECOMMENDED | Black markers, Wong palette only if multi-cofactor |
| Multi-enzyme cascade time course | RECOMMENDED | Wong palette, filled circles, error bars (SD), solid fit |
| HPLC chromatogram | SIGMAPLOT | Monochrome black trace, no markers, baseline frame |
| Dose-response / pH-rate curve | PRISM (light variant) | Inward ticks, ** brackets for stat comparisons |
| BO surface contour | RECOMMENDED | Viridis colormap (overrides cycler), thin contour 0.5 pt |
| Bar + error bar (replicates) | PRISM | Inward ticks emphasize bar tops; cap 4 pt |
| Pareto front (BO) | RECOMMENDED | Filled circle markers, Wong palette by run, no fit line |

Default for the skill: **RECOMMENDED**. The other two are explicit opt-ins via
`use_preset='prism'` or `use_preset='sigmaplot'`.

---

## 8. Sources (consolidated)

GraphPad Prism (official):

- https://www.graphpad.com/guides/prism/latest/user-guide/fonts.htm
- https://www.graphpad.com/guides/prism/latest/user-guide/using_preferences.htm
- https://www.graphpad.com/guides/prism/latest/user-guide/formataxes.htm
- https://www.graphpad.com/guides/prism/latest/user-guide/axis_numbering.htm
- https://www.graphpad.com/guides/prism/latest/user-guide/colors.htm
- https://www.graphpad.com/guides/prism/latest/user-guide/using_changing_a_graphs_colors.htm
- https://www.graphpad.com/guides/prism/latest/user-guide/prism_magic_apply_style_from_an_example.htm
- https://www.graphpad.com/support/faq/standardizing-prism-preferences/
- https://www.graphpad.com/support/faq/prism-color-schemes/

GraphPad Prism (community / R mimic):

- https://cran.r-project.org/web/packages/ggprism/vignettes/themes.html
- https://csdaw.github.io/ggprism/articles/colours.html
- https://csdaw.github.io/ggprism/reference/prism_colour_pal.html

SigmaPlot (official / mirrored):

- https://www.alfasoft.com/docs/sigmaplot-145-user-guide.pdf
- https://www.alfasoft.com/docs/sigmaplot-tutorial.pdf
- http://kfrserver.natur.cuni.cz/obecne/soubory/Sigmaplot/UserGuide.pdf
- https://systatsoftware.com/sigmaplot/graphing-features
- http://www.systat.de/TT201507/ErrorBarEN.pdf
- https://support.alfasoft.com/hc/en-us/articles/360001311138-SigmaPlot-Tech-Tips-and-Tricks

Colorblind / accessibility:

- Wong B. *Nature Methods* 2011, 8, 441. doi:10.1038/nmeth.1618
- https://mk.bcgsc.ca/colorblind/palettes.mhtml

Reference figures (worked examples / methods conventions):

- https://www.graphpad.com/guides/prism/latest/curve-fitting/reg_example_enzyme_kinetics.htm
- https://holdsworthwiki.robarts.ca/files/graphpad_prism/prismexamples.pdf
- https://iubmb.onlinelibrary.wiley.com/doi/full/10.1002/bmb.21823
- https://home.sandiego.edu/~josephprovost/Biochem%20Lab%20GraphPad%20Prism%20Kinetics%20Instructions%20F21.pdf
- https://www.pharmaceuticalonline.com/doc/product-sheet-sigmaplot-mdash-enzyme-kinetics-0001
- https://pmc.ncbi.nlm.nih.gov/articles/PMC11165005/
- https://pubs.rsc.org/en/content/articlehtml/2024/cs/d3cs00595j
