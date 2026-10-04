# Research layouts (scripts/layouts/research.py)

Eight layouts whose composition comes from real research and report templates. Only layout ideas and measured
proportions were taken: no image, text, logo or font of any template is reused. Colours come only from the active
theme (all 30 themes pass `qc_deck` and `qc_layout` with 0 CRITICAL, see `tests/test_layouts_research.py`); text on a
panel sits in that panel's own filled rectangle; content is measured first and `StyleError` is raised when it cannot
fit. Decoration is named `deco:*`. Numbers are always supplied by the caller.

| layout | kind | content keywords |
|---|---|---|
| `chapter_tracker` | agenda | `chapters` (2-7), `current` (0-based or `None`), `title`, `groups=[(first, last, label)]` (<= 3) |
| `paper_card` | title | `title`, `journal`, `year`, `presenter`, `date`; optional `authors`, `impact_factor` (free text), `doi`, `keywords` (1-6), `summary`, `venue` |
| `figure_card` | figure | `title`, `fig_path`, `fig_no`, `caption`, `source`, `takeaway`; optional `notes` (1-3), `chapter` |
| `claim_evidence` | content | `claim`, then exactly one of `evidence=[{head, text}]` (2-4; 3 with a callout) or `conclusion={finding, boundary, next_step}`; optional `section`, `note`, `callout={number, label, note}`, `bottom_line`, `chapter` |
| `donut_stat_band` | data | `title`, `items=[{value 0-100, label, note?}]` (2-4), `footnote` |
| `matrix_2x2` | data | `title`, `x_label`, `y_label`, `items=[{label, x, y}]` (1-4, x/y in 0-1), `x_low/x_high/y_low/y_high`, `quadrants` (TL, TR, BL, BR), `emphasis`, `notes` |
| `diverging_bar` | data | `title`, `rows=[{label, value}]` (2-7), `vmax`, `unit`, `left_caption`, `right_caption`, `source` |
| `bw_divider_quote` | divider | exactly one of `statement` / `number` / `quote`; `tone` `dark`/`light`, `label`, `attribution`, `section`, `kicker` |

`chapter_footer(deck, slide, chapter)` (public helper, also called by `figure_card(chapter=...)` and
`claim_evidence(chapter=...)`) prints the running chapter title bottom-left, the page number bottom-right and a hairline
in the accent colour; use it instead of `Deck._footer` on every slide of a chapter-structured talk.

## Credits and honest comparison with the source

Rating: close = same composition and proportions; partial = recognisable composition, a signature element changed;
weak = only the idea survives.

| layout | inspired by (licence) | rating | what is lost or changed |
|---|---|---|---|
| `chapter_tracker` | gh_ucsd_defense, x3zou/UCSD_Defense_Template (MIT) | close for structure, partial for the dimming | The template greys the other chapters to about 1.5:1; ours keeps them at >= 4.5:1 (still smaller, regular weight, no badge colour), so the "lit vs dim" contrast is weaker. No hyperlinks, no "back to" arrows, no hero photo or logo. Brace groups kept. |
| `paper_card` | gh_k105_reference, SciToolsmith/journal-club-ppt (MIT, design origin unstated) | partial | The template shows a journal-page screenshot or cover image, a drop shadow and gradient card; ours is a flat text card (title, authors), ruled metadata rows, keyword pills, a "Main point" bar and the presenter strip. Impact factor is free text, nothing is looked up. |
| `figure_card` | gh_k105_reference (MIT) | close | One figure per slide (template also shows two or three cards side by side, dotted inner borders, gradient arrow into the conclusion bar). Caption "Fig N." and source are inside the card, takeaway bar below with an accent tick. |
| `claim_evidence` | gh_yctrrr_academic, yctrrr/academic-ppt-template (MIT) | close | Purple bar and red claim colour only exist where the theme's accent reaches 4.5:1 on the background (otherwise the claim is in the title colour). Evidence boxes keep rounded corners, arrows, number callout card (54 pt) and the 01/02/03 Finding / Boundary / Next step cards; no bar chart is drawn next to the callout (put a figure elsewhere). |
| `donut_stat_band` | sc_market-research-report-slides (SlidesCarnival, CC BY 4.0, credit slidescarnival.com) | partial | Band with donuts and labels is kept; the photo, serif face, wave pattern and the arrow marker are not. Donuts are block-arc shapes (sweep = value x 3.6 degrees, starting at 12 o'clock), not chart objects, so the values are not editable as chart data in PowerPoint. |
| `matrix_2x2` | sc_mckinsey-strategic-planning-slides (SlidesCarnival, CC BY 4.0) | partial | Template has coloured quadrants and labels inside black circles; ours has one tinted plate with dividers, optional quadrant names, numbered markers with the label beside them, axis arrows with end labels (no rotated axis title) and a thick outline for the emphasised quadrant. An item label that would cross a divider or another label raises instead of overlapping. |
| `diverging_bar` | sc_mckinsey-strategic-planning-slides (SlidesCarnival, CC BY 4.0) | partial | Template shows paired percentages of 100 with text inside the bars; ours shows signed effect sizes around a zero line, bar length = abs(value) / axis half-range (linear; axis `vmax` must be >= max abs value, so nothing is clipped), signed value labels outside the bars, tick labels and optional side captions. No purple duotone. |
| `bw_divider_quote` | sm_black-and-white (SlidesMania, personal-use licence: structure only, nothing reused) | partial, weak for the giant number | Hard dark / light field, outlined frame, kicker strip with ">" square and bordered quote are kept. The template's giant number is about 110 pt and its quote mark is a large glyph; the closed type scale stops at 54 pt, so the number and the quote mark are visibly smaller. No Poppins face, no photographs, no SLIDESMANIA side text (keep that text if the template itself is ever shipped). |

## Themes added with this family (palettes measured from the templates)

| theme | template (licence) | measured colours | contrast discipline |
|---|---|---|---|
| `ucsd_navy_yellow` | gh_ucsd_defense (MIT) | navy `#182B49`, yellow `#FFCD00`, pale `#E7EEF3`, grey `#A0AAB3` | navy text 14.2:1; yellow only as rule / fill / badge (navy on yellow 9.5:1), never as text; text tints `#2F4B73`, `#566270` and the `#FBEFD2` warning tint are derived for 4.5:1 |
| `k105_navy` | gh_k105_reference (MIT) | slate navy `#32497B`, greys `#D9D9D9` `#F2F2F2` `#E8EAEC`, theme blue `#5B9BD5` | navy 8.8:1 on white; `#5B9BD5` is fill-only (2.96:1); `#FFF2CC` warning tint derived |
| `mono_bw_hard` | sm_black-and-white (personal use: palette idea only) | `#F2F1EC` ground, `#000000`, `#1C1B1A`, `#6C6B68`, `#A5A4A2`, `#CDCCCA`, `#EEEEEE` | caption `#6C6B68` on the ground 4.71:1; black bars with white text 21:1 |

The font of all three is Arial (the templates use Calibri, a Chinese UI face and Poppins respectively).
