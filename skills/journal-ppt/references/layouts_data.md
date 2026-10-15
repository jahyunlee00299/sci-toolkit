# Data-family layouts (`scripts/layouts/data.py`)

All five are registered with `kind="data"` and built through `Deck.layout(name, **content)`. Colors come only
from the active theme; each text color is picked from the theme palette by measured contrast on the fill it
sits on, so every one of the 27 themes passes qc_deck and qc_layout. Text is measured with the qc_layout Arial
metrics; content that cannot fit raises `StyleError` at build time. `stat_big` (54 pt) is declared by
`bento_kpi`, `giant_number` and `comparison_cards`; `stat_number` (20 pt) is never used (not in the base size list).

| layout | source grammar | content keywords |
|---|---|---|
| `bento_kpi` | G8 bento tile board | `title`, `tiles=[{label, value, unit?, delta?, note?, span?}]` (3-7; 3-4 with a figure), `figure?`, `figure_label?`, `figure_note?` |
| `giant_number` | G9 Swiss giant numeral | `number`, `unit?`, `headline_a`, `headline_b?` (accent color), `context?` (<= 4 lines, under the numeral), `source_note?`, `kicker?` |
| `highlight_chips` | G12 dark highlight chip | `title`, `claims=[{chip, text}]` (3-5; text <= 2 lines) |
| `comparison_cards` | marketing pricing-style cards | `title`, `cards=[{heading, metric, metric_label?, rows: 3 x (label, value), recommended?, badge?}]` (2-4, at most one recommended), `badge="Recommended"` |
| `metric_strip` | KPI strip above a chart | `title`, `metrics=[{value, label}]` (3-5), `figure` (path), `caption?` |

Notes
* `bento_kpi` grid is 12 columns x 2 rows with fixed templates for 3-7 tiles. `span` (1-3) ranks tiles: the
  highest-ranked tile gets the biggest slot and the strong (table header) fill; if no tile sets `span` the first
  one is featured. Value size steps down stat_big -> title_main -> title_bar -> subtitle until the value (plus unit)
  fits one line. A figure takes the biggest (two-row) slot.
* Figures (`bento_kpi`, `metric_strip`) keep their aspect ratio and must stay >= 3 in on the longer side
  (bento: `StyleError` otherwise; strip: `Deck.add_figure`, which also enforces the caption reservation).
* `giant_number` has no header bar (the headline is the title); the color panel is a top-bleed `deco:` shape that
  stops at the 6.9 in line so the footer stays on the slide background.
* `highlight_chips` / `giant_number` pick a band/panel fill that contrasts with the slide background (dark band on
  light themes; a light or accent band on dark themes).
* Write units with a space and `s⁻¹`-style superscripts in the content you pass (academic-term-rules).

Demo: build one deck per theme and export JPEGs through PowerPoint COM to look at every slide.
