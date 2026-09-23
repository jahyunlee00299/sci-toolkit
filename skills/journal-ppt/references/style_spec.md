# Journal/Research PPT Style Spec (implementable, closed-list)

Consolidates every styling authority on this machine into one mechanical spec a
python-pptx builder agent can follow without eyeballing. Resolves all conflicts found
across sources. Canvas: 13.333in x 7.5in (widescreen 16:9), Arial throughout.

---

## 1. Source inventory

| # | Path | Authority |
|---|------|-----------|
| 1 | `~/.claude/commands/journal-ppt-team.md` | **HIGHEST** — the actual 6-agent build pipeline used to make the two decks under audit. Carries the current color scheme (#1A355E/#E86A1A), Figure-First layout rules, font-size table for content slides, QC enforcement thresholds (Agent 4/6), slide-language rule. Most recently authored, explicitly overrides the template's old colors (line 486-488). |
| 2 | `~/.claude/skills/journal-presentation-maker/SKILL.md` | HIGH — parent skill invoked by the command. Sole source for **line_spacing** and **disable_autofit** rules (§Line Spacing Rules, mandatory). Also carries academic notation rules and QC checklist (redundant with #1 on notation, kept for cross-check). |
| 3 | `~/.claude/skills/journal-presentation-maker/references/pptx_generation.md` | HIGH — the only source with an actual **measured pt table for 13.33x7.5in widescreen** (header 26pt, body bullets 16pt, table 12pt, caption 9.5pt, footer 9-10pt) plus a full figure-slide layout template with exact Inches() coordinates. |
| 4 | `~/.claude/skills/journal-presentation-maker/references/styling_guide.md` | MEDIUM — CSS/HTML at 960x540px, a *different unit system* for an *earlier* generation stage (HTML mockup before pptx conversion). Gives line-height intent (1.2/1.3/1.4/1.6) that #2 does not spell out numerically — used only for that. Colors/px sizes here are superseded by #1. |
| 5 | `~/.claude/skills/journal-presentation-maker/references/api_reference.md` | No styling content — paper-search API reference only. |
| 6 | `~/.claude/skills/journal-presentation-maker/STRUCTURE.md`, `FILE_CREATION_GUIDE.md` | No styling content — code architecture/docstring conventions for the skill's own Python templates. |
| 7 | `~/.claude/skills/pptx/SKILL.md` | LOW for this use case — generic pptx skill. Its "Typography/Color Palettes" section (line ~139-220) is written for **general business/pitch decks** ("pick an interesting font pairing," "don't default to Arial," "NEVER use accent lines under titles") and directly **conflicts** with academic conventions mandated by #1/#2 (Arial required, header bar IS an accent element). Ruling: journal-club decks are a specialized deliverable governed by #1/#2; this generic guidance does not apply here. Its QA section (markitdown text-check + subagent visual-check prompt) is reusable and folded into §9 below. |
| 8 | `~/.claude/skills/pptx/editing.md`, `pptxgenjs.md` | No line_spacing/space_after/font-size authority found (grepped, zero hits) — mechanical python-pptx/pptxgenjs API usage only, no style values. |
| 9 | `~/.claude/scripts/create_research_template.py` | LOW/superseded — base helper library (`add_textbox`, `add_rect`, `build_title_slide`, `build_table_slide`, etc.) still usable for its **functions**, but its color constants (`COLOR_PRIMARY #1F4E79`) are the OLD scheme explicitly overridden by #1. Its own internal font sizes (18/16/14/13/12pt in various builders) are pre-#1 and not binding once #1's table applies. |
| 10 | `~/.claude/skills/academic-term-rules/SKILL.md` | HIGH for nomenclature — species/gene italics, sub/superscripts, units, dashes, statistics symbols, E-factor notation. Governs slide *text content*, not layout/type-scale. |
| 11 | a project-local `FIGURE_STYLE.md` (matplotlib figure style guide, if your project has one) | Reference only, **not directly applicable** — this is the matplotlib figure-rendering style guide (rcParams, Arial 11pt body / 10pt axis / 9pt legend, 600 DPI PNG, project-specific color hexes for the data series). It governs *images pasted into slides*, not slide text/layout. Its type scale (11/10/9pt) is for print figures at 6.5in width, not slide text — do not reuse those pt values for slide body text. Its principle worth echoing on slides: consistent Arial family, no markers/borders clutter, muted 9pt-class captions — already satisfied independently by #1/#3. |

**Conflict rulings:**
- **Colors**: #1 (`journal-ppt-team.md`) wins over #9 (`create_research_template.py`). Rationale: #1 is the newer, deck-specific authority that explicitly instructs "Do NOT import colors from the template — use the color scheme above" (journal-ppt-team.md:486-488). #9's `COLOR_PRIMARY #1F4E79` is legacy.
- **Body font size**: #1 says content-slide body text is "Arial 14pt, #333333" (journal-ppt-team.md:664); #3 (`pptx_generation.md`) says main-slide body bullets are **Pt(16)**. These are reconciled, not merged as ambiguity: #3's 16pt is for the **figure-slide bullet template's sibling case** ("Body bullets (main slides)" row) — i.e. slides with NO figure, full-width text. #1's 14pt is specifically for the **figure-adjacent sidebar text** under Figure-First Layout (measured: journal-ppt-team.md:565 "3 bullets (14pt...)" and :664 general content body). Ruling: **use 16pt for text-only slides' bullets, 14pt for figure-slide sidebar/key-point bullets** — both kept as two distinct roles in the type scale below rather than collapsed to one number, because the two decks under audit are ~90% figure-adjacent slides (hence 14pt dominates observed output) but pure-text slides (Background, Discussion, Strengths/Limitations) should read at 16pt per #3's explicit "Body bullets (main slides)" row.
- **Line spacing**: silent in #1/#3/#9. #2 is the only source with a rule (mandatory, with code). Followed exactly — see §3.

---

## 2. Type scale — CLOSED LIST (7 sizes total)

No font size outside this list may appear on a slide (footer/slide-number excepted only insofar as they use the Footer role already in this list).

| pt | Role | Bold | Color role |
|----|------|------|------------|
| **26** | Slide title (header bar text, all content/figure slides) | Yes | White on header bg |
| **30** | Title-slide main title only (no header bar on title slide) | Yes | Header-bg color, on white |
| **18** | Section subtitle / TOC section text / stat number | Yes (subtitle), No (stat number 20 — see note) | Accent or body |
| **16** | Body bullets — text-only slides (Background, Discussion, Strengths/Limitations, Questions) | No | Body text |
| **14** | Figure-slide sidebar/key-point bullets, figure-slide subtitle (bold+italic), journal citation line on title slide | No (bullets), Yes+italic (subtitle) | Body text / Subtitle color |
| **12** | Table cell text, table header text (bold), slide-condition/annotation text | Table header = bold | Body text (cell), white (header) |
| **11** | References-slide entries, presenter/date on title slide | No | Body text |
| **9.5** | Figure captions (italic) | No (bold only on the "et al." source line) | Caption color |
| **9** | Footer text (page number, "Author et al., Journal Year") | No | Caption color |

**[CHOSEN] Collapsing to a strict 6-8 total**: the list above is 8 distinct values (30, 26, 18, 16, 14, 12, 11, 9.5, 9 — actually 9). Measured decks used 16-19 values; this is a >50% cut and every one of the 9 has a named, non-overlapping role, so no further merge is forced. If a stricter 7-value budget is required, merge 11pt (references) into 12pt (table cell) — both are already visually similar secondary-text sizes — leaving 8. Do not merge 9 and 9.5 (caption vs footer must stay visually distinct per source #3) or 14 and 16 (see conflict ruling above — these are different roles, not the same role measured twice).

Stat-number tiles (used in figure-first layouts for "85% yield" style call-outs): **20pt bold**, not in the base 9 — flagged as a **10th, conditional** size used only when a research-mode slide has a KPI tile (journal-ppt-team.md does not have this element type in journal mode; carried from `pptx` skill's generic stat-tile convention). Add to the QC allow-list as `{20}` only for research-mode decks.

---

## 3. Line spacing — CLOSED LIST

Source #2 (`journal-presentation-maker/SKILL.md`) is the sole authority; #1/#3/#9 are silent. python-pptx `paragraph.line_spacing` accepts a float multiplier directly — no unit conversion needed, unlike font size.

| Role | `paragraph.line_spacing` | Rationale |
|------|---------------------------|-----------|
| Body bullets (any bullet list, 16pt or 14pt) | **1.5** | #2 mandatory rule, "Body bullets (add_bullet_body)" row |
| General textbox, non-italic | **1.5** | #2, "General textbox... auto-applied when italic=False" |
| Caption / italic / source-attribution text (9.5pt) | **1.0** | #2, "Caption/italic/source text" row |
| References slide entries | **1.15** `[CHOSEN]` | #2 gives a range "1.0-1.2" without picking a value; chosen midpoint balances the CSS guide's `line-height: 1.5` intent for `p, li` (styling_guide.md, `.references-slide` inherits body but is denser in practice) against #2's own explicit range ceiling. |
| Slide title (26/30pt, 1-2 lines in header bar) | **1.0** `[CHOSEN]` | Not covered by #2 (titles are single short strings, not bulleted). Titles rarely wrap to 2 lines; when they do, PowerPoint's default single-spacing keeps the header bar height (Inches(1.1)) from being visually broken. Converting CSS h1 `line-height:1.2` would recommend 1.2, but the header bar's fixed 1.1in height was measured against 1.0 spacing in the existing builder (`pptx_generation.md`'s `make_figure_slide`) — keep 1.0 to match the geometry it was designed against. |
| Table cells | **1.0** `[CHOSEN]` | Tables are dense grids; CSS guide gives no table line-height (only `font-size: var(--text-sm)`), and 1.5 spacing on 12pt cell text would blow out row height across an 8-row table. |

**CSS → python-pptx conversion note (styling_guide.md's h1/h2/h3/body line-height intent):** the CSS values (1.2 h1, 1.3 h2, 1.4 h3, 1.6 body) are unitless `line-height` multipliers exactly like `paragraph.line_spacing` — **no numeric conversion is needed between the two systems**, only a *role* mapping, because both are relative-to-font-size multipliers, not absolute measurements. The CSS guide's `1.6` body value is **not** used above; #2's explicit `1.5` for body bullets overrides it (#2 is pptx-specific and mandatory; the CSS guide predates the pptx conversion step and was never validated against `disable_autofit`). **Korean-free English text does not change the recommendation** — line-height multipliers are language-agnostic; only glyph-height and ascender/descender proportions differ across scripts, which python-pptx does not expose as a separate control anyway.

**Line spacing is never a caller-chosen float — it is looked up from `LINE_SPACING[role]`
in `deck_builder.py` and never passed in by hand.** `Deck.add_textbox()`/`bullets()` accept an
explicit `line_spacing=` override only as an escape hatch (validated against
`ALLOWED_LINE_SPACING` before use); ordinary slide construction never sets it. This is what
kept the closed 3-value list from drifting on every deck the `Deck` class actually built — the
2026-09-12 IRED-paper deck that still showed 1.0/1.15/1.2/1.25/1.3 line spacing scattered
across slides was hand-written python-pptx from *before* this skill existed, not built
through `Deck` — the fix there was a one-off repair script, not evidence the role-lookup
mechanism itself needs changing. `qc_deck.py` QC-3 (line 210+) still asserts the closed set
independently, so a hand-written deck fed through QC gets caught even if it never touched
`Deck`.

**MANDATORY wiring** (from #2, verbatim requirement — do not skip): `disable_autofit(text_frame)` must run on every text frame *before* `set_line_spacing()` is applied, or PowerPoint silently ignores the spacing:

```python
def disable_autofit(text_frame):
    from pptx.oxml.ns import qn as _qn
    bodyPr = text_frame._txBody.find(_qn('a:bodyPr'))
    if bodyPr is not None:
        for child in bodyPr.findall(_qn('a:spAutoFit')):
            bodyPr.remove(child)
        for child in bodyPr.findall(_qn('a:normAutofit')):
            bodyPr.remove(child)
        from lxml import etree
        etree.SubElement(bodyPr, _qn('a:noAutofit'))

def set_line_spacing(paragraph, spacing):
    paragraph.line_spacing = spacing  # float multiplier; do NOT hand-write spcPct XML
```

---

## 4. Paragraph spacing (`space_after`) — CLOSED LIST

No source gives this explicitly for pptx; #9's scattered `p.space_before = Pt(4/6)` calls are the only precedent (measured decks had 14-15 distinct 0-20pt values — clearly ad hoc). `[CHOSEN]` throughout, derived from the CSS guide's `--spacing-*` scale (8/12/20/32/48px) converted at the 72px/in canvas ratio (960px canvas / 13.333in = 72 px/in, i.e. 1px = 1pt at this specific canvas mapping — see §Geometry conversion factor):

| Role | `space_after` | Basis |
|------|---------------|-------|
| Heading → first body line (title to first bullet) | **12pt** | CSS `--spacing-md: 20px` scaled down for pptx's tighter vertical budget (header bar already reserves 1.1in) |
| Between bullets (same list) | **6pt** | CSS `--spacing-sm: 12px` halved — 1.5x line_spacing already provides most of the visual gap; adding the full 12pt double-counts |
| Between blocks (bullet list → next textbox/figure) | **16pt** | CSS `--spacing-lg: 32px` halved |
| Last paragraph in any text frame | **0pt** | Standard practice — trailing space_after on the final paragraph pushes box-bottom padding for no visual reason and is the single most common cause of "ends too low" in QC |
| Table row → row (cell-internal) | **0pt** | Row height is controlled by the table geometry, not paragraph spacing |
| Caption line → source-attribution line (multi-line caption) | **2pt** | Tight — these are visually one unit (caption block), matching the existing `pptx_generation.md` caption-loop pattern which adds no explicit space_before/after between caption lines |

---

## 5. Colors — resolved palette (RGB hex)

Source: `journal-ppt-team.md:474-482` (wins over `create_research_template.py`'s `#1F4E79` scheme per §1 ruling).

| Role | Hex | RGBColor |
|------|-----|----------|
| Header bar background | `#1A355E` dark navy | `RGBColor(0x1A, 0x35, 0x5E)` |
| Accent (dividers, highlights, "Thank You" line) | `#E86A1A` orange | `RGBColor(0xE8, 0x6A, 0x1A)` |
| Body text | `#333333` dark gray | `RGBColor(0x33, 0x33, 0x33)` |
| Subtitle / figure-slide subtitle | `#2E5E9B` medium blue | `RGBColor(0x2E, 0x5E, 0x9B)` |
| Caption / footer text | `#888888` light gray | `RGBColor(0x88, 0x88, 0x88)` |
| Highlight box fill (key findings) | `#DBE8F7` light blue | `RGBColor(0xDB, 0xE8, 0xF7)` |
| Warning box fill (limitations/caveats) | `#FDE8E8` light red | `RGBColor(0xFD, 0xE8, 0xE8)` |
| White (header text, title-slide bg accents) | `#FFFFFF` | `RGBColor(0xFF, 0xFF, 0xFF)` |
| Table header background | same as Header bar `#1A355E` | `RGBColor(0x1A, 0x35, 0x5E)` |
| Table header text | White | `RGBColor(0xFF, 0xFF, 0xFF)` |
| Table zebra-stripe alt row | light blue tint, `[CHOSEN]` reuse Highlight box `#DBE8F7` at reduced visual role | `RGBColor(0xDB, 0xE8, 0xF7)` |

Deprecated / do not use: `#1F4E79` (COLOR_PRIMARY), `#2E75B6` (COLOR_ACCENT), `#F2F7FC` (COLOR_LIGHT_BG), `#262626` (COLOR_TEXT_DARK), `#808080` (COLOR_GRAY) — all from `create_research_template.py`, superseded.

### Sanctioned derived colors `[ADDED]`

Found as false positives when `qc_deck.py` was run against a real deck (`journal_club_2026-08-23_PHBO.pptx`) — these are legitimate, deliberate design colors that the base 8-color list above never named. Rather than leave the palette check either silently non-enforcing (never checking font colors) or permanently noisy (flagging real, intentional colors on every run), these three are named explicitly and the check stays CRITICAL-eligible for anything still outside the now-11-color set:

| Role | Hex | RGBColor | Why it exists |
|------|-----|----------|----------------|
| Header-bar subtitle text | `#C5D5EA` light blue-gray | `RGBColor(0xC5, 0xD5, 0xEA)` | Body text `#333333` would be near-invisible against the `#1A355E` navy header bar; needs a light tint for contrast. |
| Strengths heading (Strengths & Limitations slide) | `#2C6E3F` dark green | `RGBColor(0x2C, 0x6E, 0x3F)` | Paired with the existing `#DBE8F7` "key findings" box fill's positive-framing counterpart — Strengths heading uses a green that reads as affirmative, matching the two-column Strengths/Limitations layout already specified in the pipeline. |
| Limitations heading (Strengths & Limitations slide) | `#A53636` dark red | `RGBColor(0xA5, 0x36, 0x36)` | Paired with the existing `#FDE8E8` "warning" box fill — Limitations heading uses a red that reads as cautionary, consistent with the warning-box color already in the base palette. |

`ALLOWED_HEX` in `qc_deck.py` includes these 3 alongside the base 8. Choice made explicitly here (per team-lead direction, option (a) over weakening the check to WARNING-only for font colors): **naming the colors keeps the palette check strict** rather than permanently downgrading a real check to avoid documenting three legitimate colors.

---

## 6. Geometry

**Conversion factor (styling_guide.md's 960x540px @16:9 → 13.333x7.5in @16:9):** 960px / 13.333in = **72 px/in** exactly (and 540/7.5 = 72, confirms consistency). This is coincidentally the same as the CSS reference pixel-to-point ratio (96px/in webscreen standard is NOT what's used here — this guide's 960x540 canvas is a *slide-dimension* mapping, not a web-DPI mapping). **Do not use the web-standard 1px=0.75pt formula** — that assumes 96 DPI; this guide's own canvas gives 72 px/in, i.e. **1px in the CSS guide = 1pt on the actual slide** at this specific 960x540 authoring size. (Sanity check: CSS `--text-base: 20px` body → 20pt would be oversized against #3's measured 16pt real-deck body; this confirms the CSS guide's font sizes were never the ones actually implemented — #1/#3's pt values, not a mechanical px→pt conversion of #4, are authoritative for font size. The 1px=1pt factor is used ONLY for spacing/margin conversion in §4, not font size, since #1/#3 already give font sizes directly in pt.)

| Parameter | Value |
|-----------|-------|
| Slide size | 13.333in x 7.5in (16:9 widescreen) |
| Header bar height (content/figure slides) | Inches(1.1) |
| Header bar margin-left / margin-top (title text inside bar) | Inches(0.4) / Inches(0.12) — `pptx_generation.md`; journal-ppt-team.md's own content-slide spec says title at left=0.5",top=0.15" for the **non-figure-template** header — use **0.4/0.12 as the figure-slide-template default, 0.5/0.15 for plain content slides** (both sources kept, distinguished by slide type, not merged into one number since they come from two different concrete templates already in use) |
| Body/content top edge (no figure) | Inches(1.4) from top (journal-ppt-team.md:663) |
| Figure-slide subtitle position | top Inches(1.15), height Inches(0.5) |
| Figure-slide key-point start | top Inches(1.7), height Inches(1.3) for 3 bullets |
| Left/right margin | Inches(0.3) minimum from edge (both left and right) |
| Footer band | y = Inches(7.1) to Inches(7.4) (footer text at 7.1, nothing may cross into it) |
| **Y-coordinate nothing may cross** | **Inches(7.0)** — hard floor for any content shape (figure, textbox, table); footer zone begins at 7.2 per `journal-ppt-team.md` overlap-prevention rule ("Figure must not extend below Y = 7.0"; QC re-states "No shape should extend below Y = slide_height - 0.5" = 7.0) |
| Figure-area fraction — single figure | 55-65% of slide area |
| Figure-area fraction — full-width/multi-panel | 60-70% of slide (bottom band) |
| Figure-area fraction — two figures side-by-side | 50% each |
| Minimum figure width | >= 5.5in (right-side placement) or >= 9in (full-width) |
| Minimum figure height | >= 3.0in |
| Figure-to-text gap | >= 0.3in on all sides (overlap-prevention rule) |
| Caption box height | Inches(0.75), starting Inches(0.06) below figure bottom |

**Authors-slide geometry** (`Deck.authors_slide()` / `_logo_row()`, added 260912): logo row
top = Inches(4.75), band height = Inches(1.2), each logo centered within a `slot_w * 0.82`
wide by `band_h` tall bounding box (constrain by whichever of width/height binds first,
preserving aspect ratio) so wordmarks with very different native aspect ratios (a 7:1 wide
company wordmark next to a near-square university crest) still align on one visual row
instead of the widest one shrinking to a sliver. Caption label per logo sits
Inches(0.16) below the band, `footer` role, center-aligned within that logo's slot.

---

## 7. Text-fit policy

1. **`disable_autofit()` is mandatory on every text frame** (see §3) — `MSO_AUTO_SIZE` is explicitly NOT the mechanism used for line-spacing correctness; PowerPoint's native autofit and this skill's manual line_spacing are mutually exclusive, and this spec always chooses manual.
2. `word_wrap = True` on every textbox (both `journal-ppt-team.md`'s Agent 6 checklist and `pptx` skill's generic QA agree).
3. **When to shrink vs. cut** — priority order per `journal-ppt-team.md`'s Figure-First Layout decision tree (§2 "Layout decision tree" + "Text reduction rules"):
   - First: reduce bullet count (max 3 for figure-sidebar slides, single line each)
   - Second: move detail to speaker notes (never delete content — relocate it)
   - Third (only if figure is self-explanatory): drop to caption-only, zero bullets
   - Font-size shrinking is **not** in the approved toolkit for body/bullet text — the type scale in §2 is closed; an agent must not invent a 13pt or 15pt to "make it fit." Only the caption/footer sizes (9-9.5pt) are treated as a fixed floor, never shrunk further (`pptx_generation.md`'s Agent 6 QC: "Zero fonts < 10pt excluding footer" — footer/caption are the sanctioned exception already inside the type scale).
4. **Overflow estimation before rendering** (English text, no CJK metrics needed): use PIL `ImageFont.getbbox` or a simple char-count heuristic — `journal-ppt-team.md` gives the operative per-slide word budget instead of a pixel estimator: **max 40-50 words per slide** (excluding title/caption), **max 6-8 bullets**, **each figure-sidebar bullet <= 1 line**. Treat "1 line" as ~45-55 characters at 14pt in a ~5.5in-wide sidebar (Inches(5.5) at 14pt Arial ~ 9-10 chars/inch) — if a bullet string exceeds ~50 characters, shorten it at write time rather than letting PowerPoint wrap it to 2 lines.
5. Picture minimum-size enforcement (Agent 6, `journal-ppt-team.md`): every inserted picture >= 3in in at least one dimension; if smaller, scale up via `Inches(5) / max(shape.width, shape.height)` maintaining aspect ratio — never stretch non-uniformly. **Exception: attribution logos** (`Deck.authors_slide()`'s institution/company logo row) are a different content class from a results/scheme figure and are exempt from this floor — a 4-6-logo row at legible badge size (style_spec.md §Authors-slide geometry below) would blow past the slide width if each logo were forced to 3in. `Deck._logo_row()` marks every logo picture's `shape.name` as `"logo:<stem>"` and `qc_deck.py`'s QC-11 reads that marker to apply the exemption — never rename a logo picture shape away from that prefix, or QC-11 will (correctly) flag it as an undersized figure.

---

## 8. Nomenclature carried into slides (from `academic-term-rules` SKILL.md, filtered to slide-relevant rules)

- **Species names**: always italic — *Escherichia coli*, first mention full then *E. coli* thereafter. Never roman.
- **Gene names**: italic lowercase — *xylA*, *gldA*. **Protein/enzyme names**: roman, capitalized/all-caps — XylA, GDH (no italics).
- **Origin-prefix italics on engineered-enzyme labels**: only the 2-letter genus prefix is italic, the rest roman — *Ec*Adh, *Bs*Ldh, *Sc*GRE3 (single mathtext/run block, not two separate runs — matches the matplotlib `enz()` helper convention in `academic-term-rules` §20 and a project `FIGURE_STYLE.md` §4, kept consistent between figure and slide text). Do **not** italicize the whole token (`$Sc$GRE3` wrong) and do **not** bold the suffix.
- **D-/L- sugar stereodescriptors are roman, never italic** — D-glucose, L-arabinose (common confusion with the genus-prefix italic rule above; these are a different category).
- **Sub/superscripts**: NAD⁺, NADP⁺, H₂O₂, CO₂, Mg²⁺, Km (K subscript m, K itself italic), kcat (k subscript cat, k italic), Vmax (V subscript max, V italic). Never plain-text `NAD+`, `H2O2`, `Km`, `kcat`.
- **Units**: always a space between number and unit — 5 μM not 5uM, 30 °C not 30°C (space before ° too), 50 mM not 50mM. μ not u/µ-lookalike ASCII.
- **Statistics**: italic *p*, *n* — "*p* < 0.05", "*n* = 3". Error format "mean ± SD".
- **En dash for ranges**: pH 3–5, 25–45 °C — never a hyphen.
- **No em-dash enumeration in body text** — matches manuscript rule (`academic-term-rules` §18b: "Em-dash list — replace with complete sentence"); slides should use short bullet fragments instead of em-dash-joined clauses.
- **No bare reaction arrows in prose** (`academic-term-rules` §17: "본문 반응 화살처 X → Y 기호 금지 → -to- 자연어") — Scheme/equation graphics may use →, but slide bullet *text* should read "X-to-Y" or a verb phrase, not a bare arrow glyph, except where the arrow is inside an inserted scheme image.
- **American spelling** throughout (optimize not optimise, characterize not characterise, etc. — §15 full table).
- **E-factor notation**: italicize only the *E* — "*E*-factor", not "E-factor" or fully-italic "*E-factor*". sEF/cEF stay roman (labels, not variables).
- **Citation-number placement** (RSC/Green Chemistry numeric-superscript style, if slide citations use superscript numerals): number goes AFTER terminal punctuation — "cascade.¹" not "cascade¹."

---

## 9. Machine-checkable QC list

Each rule below is a python-pptx assertion runnable by a QC agent against the finished `.pptx`. All font sizes/spacings are compared via `run.font.size.pt` / `paragraph.line_spacing` / `paragraph.space_after.pt`.

```python
from pptx import Presentation
from pptx.util import Pt

ALLOWED_FONT_SIZES = {9, 9.5, 11, 12, 14, 16, 18, 26, 30}       # + {20} if research-mode stat tiles present
ALLOWED_LINE_SPACING = {1.0, 1.15, 1.5}                          # body=1.5, caption/title/table=1.0, refs=1.15
ALLOWED_SPACE_AFTER_PT = {0, 2, 6, 12, 16}
REQUIRED_FONT = "Arial"
HANGUL_RE = r'[\uAC00-\uD7A3\u3130-\u318F]'   # 가-힣 + 자모 (㄰-㆏ range)

prs = Presentation(pptx_path)

for i, slide in enumerate(prs.slides, start=1):
    for shape in slide.shapes:
        if not shape.has_text_frame:
            continue
        tf = shape.text_frame
        # QC-1: word_wrap must be True
        assert tf.word_wrap is True, f"Slide {i}: word_wrap not set on {shape.shape_id}"
        # QC-2: autofit must be noAutofit (disable_autofit was applied)
        from pptx.oxml.ns import qn
        bodyPr = tf._txBody.find(qn('a:bodyPr'))
        has_noautofit = bodyPr is not None and bodyPr.find(qn('a:noAutofit')) is not None
        assert has_noautofit, f"Slide {i}: disable_autofit() not applied on shape {shape.shape_id}"

        for para in tf.paragraphs:
            # QC-3: line_spacing must be one of the allowed multipliers (skip empty paragraphs)
            if para.runs and para.line_spacing is not None:
                assert para.line_spacing in ALLOWED_LINE_SPACING, \
                    f"Slide {i}: line_spacing={para.line_spacing} not in {ALLOWED_LINE_SPACING}"
            # QC-4: space_after must be a closed-list value (None == inherits, treat as 0-equivalent, skip)
            if para.space_after is not None:
                assert round(para.space_after.pt, 1) in ALLOWED_SPACE_AFTER_PT, \
                    f"Slide {i}: space_after={para.space_after.pt}pt not allowed"
            for run in para.runs:
                # QC-5: font must be Arial (notes_slide exempt — Korean text may need a different fallback)
                if shape != slide.notes_slide if slide.has_notes_slide else True:
                    assert run.font.name in (None, REQUIRED_FONT), \
                        f"Slide {i}: font {run.font.name} != Arial"
                # QC-6: font size must be in the closed type scale
                if run.font.size is not None:
                    assert round(run.font.size.pt, 1) in ALLOWED_FONT_SIZES, \
                        f"Slide {i}: font size {run.font.size.pt}pt not in {ALLOWED_FONT_SIZES}"
                # QC-7: no font below 9pt (footer/caption floor)
                if run.font.size is not None:
                    assert run.font.size.pt >= 9, f"Slide {i}: font {run.font.size.pt}pt below 9pt floor"
                # QC-8: no Hangul outside speaker notes
                import re
                is_notes = False  # set True when iterating slide.notes_slide separately
                if not is_notes and re.search(HANGUL_RE, run.text):
                    raise AssertionError(f"Slide {i}: Hangul found in slide body: {run.text!r}")

    # QC-9: geometry — nothing may cross Y = Inches(7.0)
    from pptx.util import Inches
    for shape in slide.shapes:
        assert shape.top + shape.height <= Inches(7.0) + Emu(1000), \
            f"Slide {i}: shape {shape.shape_id} extends below Y=7.0in floor"
        assert shape.left >= Inches(0.3) - Emu(1000), f"Slide {i}: shape breaches left margin"
        assert shape.left + shape.width <= Inches(13.033), f"Slide {i}: shape breaches right margin"

    # QC-10: every content slide must have speaker notes, Korean, >= 4 sentences (proxy: >=100 chars)
    if slide.has_notes_slide:
        notes = slide.notes_slide.notes_text_frame.text
        assert len(notes) >= 100, f"Slide {i}: speaker notes too short ({len(notes)} chars)"
        assert re.search(HANGUL_RE, notes), f"Slide {i}: speaker notes contain no Korean"
    else:
        raise AssertionError(f"Slide {i}: missing speaker notes entirely")

    # QC-11: pictures >= 3in in at least one dimension
    for shape in slide.shapes:
        if shape.shape_type == 13:  # MSO_SHAPE_TYPE.PICTURE
            assert max(shape.width, shape.height) >= Inches(3), \
                f"Slide {i}: picture below 3in minimum dimension"

    # QC-12: colors — every solid fill / font color must be from the resolved palette (§5)
    ALLOWED_HEX = {"1A355E", "E86A1A", "333333", "2E5E9B", "888888",
                   "DBE8F7", "FDE8E8", "FFFFFF"}
    # walk run.font.color.rgb and shape.fill.fore_color.rgb where color_type == MSO_THEME_COLOR.NONE
    # (implementation: wrap in try/except — not all shapes have an explicit solid fill)
```

Additional non-pptx-native checks (run separately, not python-pptx assertions):
- **QC-13** (word budget): count words per slide body (excluding title/caption) — flag > 50.
- **QC-14** (bullet count): count bullet paragraphs per slide — flag > 8 (text-only) or > 3 (figure-sidebar).
- **QC-15** (nomenclature, implemented `qc_deck.py`): two independent passes.
  (a) regex-scan all run text against `academic-term-rules` §12 `TYPO_PATTERNS` (uM→μM,
  NAD+→NAD⁺, etc.) and §11 sub/superscript table; every hit is CRITICAL per that skill's own
  severity classification. **Not yet wired into `qc_deck.py`** — TYPO_PATTERNS are 1:1 text
  substitutions authored for manuscript body text; wiring them here still needs the same
  boundary-aware anchoring pipeline.md Phase 2 Step 5b already requires (a blind
  `str.replace` corrupts ordinary words), so this sub-check is tracked as a deferred unit,
  not silently dropped.
  (b) origin-prefix italic candidate scan (`ORIGIN_PREFIX_CANDIDATE_RE`, added 260912):
  academic-term-rules §2's named 8-prefix table (Bs/Ec/Ps/Pf/Gc/Ao/Sc/Lp/Ag) is not
  exhaustive — the IRED-deck build hit `AspRedAm` (3-letter prefix, not on that list). A
  shape-based heuristic (`<CapLetter><1-3 lowercase><CapLetter><rest>`) catches the general
  pattern instead of a fixed list, with a small allowlist (RedAm, IREDs, NADPH, NADH) for
  measured false positives. **WARNING-only, never CRITICAL** — the heuristic cannot
  distinguish a genuine genus-prefix label from a coincidental CamelCase token, so it flags
  for human/Academic-QC-agent confirmation rather than asserting a verdict.
- **QC-16** (markitdown content pass, from `pptx` skill QA): `python -m markitdown output.pptx | grep -iE "xxxx|lorem|ipsum|this.*(page|slide).*layout"` — any hit is a leftover-placeholder defect.
- **QC-17** (visual, subagent-based, from `pptx` skill QA): render each slide to PNG (`scripts/thumbnail.py` or PowerPoint COM `Slide.Export`) and have a fresh-eyes subagent check overlap, overflow, low-contrast, uneven-gap issues per the `pptx` skill's visual-QA prompt template.

---

## Summary of conflicts arbitrated

1. **Colors**: `journal-ppt-team.md` (#1A355E/#E86A1A/#333333/#2E5E9B/#888888) wins over `create_research_template.py` (#1F4E79 scheme) — the newer source explicitly instructs overriding the template's colors.
2. **Body bullet size 14 vs 16pt**: not merged — kept as two roles (figure-sidebar=14pt, text-only-slide body=16pt), since both are independently attested by name in different sources for genuinely different layout contexts.
3. **Line spacing values**: `journal-presentation-maker/SKILL.md` is the sole source (others are silent) — followed exactly (1.5 body / 1.0 caption / 1.0-1.2 references, midpoint 1.15 chosen).
4. **CSS px sizes vs pt sizes**: the CSS `styling_guide.md` font-size scale (14-48px) is NOT used for font sizing — it predates the pptx conversion and was never validated against the actual measured pt table in `pptx_generation.md`; only its *line-height ratios* (1.2-1.6) and *spacing scale* (8-48px, used at 1px=1pt for space_after) are carried forward.
5. **Generic `pptx` skill's design guidance** (font pairing beyond Arial, no accent lines under titles) is ruled inapplicable — that skill targets general pitch decks and directly contradicts the academic-deck mandates (Arial-only, header bar as an intentional accent element) in the higher-authority sources.
