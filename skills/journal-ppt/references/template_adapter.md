# Building on a real template (`scripts/template_adapter.py`)

`Deck` draws every slide itself on a blank 13.333 x 7.5 in canvas with the closed type scale. A real template
(university, conference, slide marketplace) brings its own slide size, masters, layouts and look. The adapter reads
such a `.pptx` and fills it by meaning, with the same rule as `Deck`: text that cannot fit is an error, never a
silent overflow. License: private study only; templates stay outside the repository, nothing from one is copied here.

## 1. Look before you build

```
"$PY" scripts/template_adapter.py inspect <template.pptx> [--json] [--out f.json]
"$PY" scripts/template_adapter.py gallery <template.pptx> gallery.pptx   # one labelled slide per layout; render it and look
"$PY" scripts/template_adapter.py theme   <template.pptx> --name my_tpl  # THEMES-entry draft + contrast report
```

`inspect` prints the slide size (and its scale against 13.333 x 7.5), theme colors and fonts, and for every layout:
its name, a **guessed role** (`title`, `section`, `content`, `two_content`, `multi_content`, `picture_text`, `picture`,
`data`, `title_only`, `closing`, `blank`, `vertical`) with the reason, and each placeholder (idx, type, kind, position
in % of the slide, font size, and a **capacity** estimate in characters / lines measured with PIL at the placeholder's
own font size). Layout warnings (`!`) name content the layout draws on every slide: a sample chart or picture, a typed
page number, fixed text. Example slides with their fillable text shapes follow.

**Two kinds of template.** Placeholder templates (ETH, SlidesCarnival) keep the design in layouts: use `add()`.
Pattern templates (the k105 group-meeting deck, the UCSD defense deck) have one plain layout and put the design on
free shapes of the example slides: `inspect` shows "0/N layouts carry content placeholders"; use `add_from_example()`.

## 2. Build

```python
from template_adapter import TemplateDeck, TemplateError
d = TemplateDeck("template.pptx")                 # keep_originals=False: the example slides are removed at save()
d.roles()                                         # {'content': ['Inhalt'], 'picture_text': [...], ...}
d.add("content", title="...", body=["point", (1, "sub-point")], notes=KOREAN_NOTES)
d.add("Inhalt Bild", title="...", picture="fig.png", notes=...)          # layout name, index or role
d.add("picture_text", title="...", body=[...], picture=["a.png", "b.png"], notes=...)
d.add("CUSTOM_2", title="...", fill={3: "caption text", 5: ["a", "b"]}, notes=...)   # slots by placeholder idx
d.add_from_example(5, {0: "1.1 Background", 2: "text", 5: None}, pictures={"fig 3": "scheme.png"},
                   keep=d.numeral_shapes(5), loose=[5], notes=...)
d.save("deck.pptx")
```

`add()` rules (all raise `TemplateError`, a `StyleError`, before anything is written):

* **Fit.** The text is wrapped with real font metrics inside the placeholder (insets, line spacing, paragraph spacing,
  indent, caps taken from layout -> master). If it does not fit at the template's own size, the font may shrink in 5 %
  steps down to `min_scale` (default 0.6, never below 12 pt on a 13.333 in slide, scaled with the slide). Non-title text
  may grow up to the slide-size ratio (`grow`, capped at 1.5) when there is room, so 20 in templates are not left with
  tiny text. `d.log[i]["scales"]` records every change.
* **Pictures** are never stretched. `fit="auto"` crops to the slot only when at most `max_crop` (2 %) would be lost,
  otherwise places the whole picture inside the slot (`contain`); `fit="cover"` that would lose more is refused. A
  picture slot below 3 in x (slide width / 13.333) raises. Text that would run into a placed picture raises.
* **Notes** must be Korean and >= 100 characters (QC-10).
* **Nothing is left empty.** Unfilled placeholders are deleted, so no "Click to add ..." prompt survives. A lone short line
  (tagline, label) in a body slot loses its bullet (`bullets="auto"`).
* **Invisible text.** The color the template gives each text level is resolved (schemeClr, clrMap, overrides) and compared
  with what lies behind the placeholder; below 3:1 raises (a closing layout of the ETH template colors level 2 white on white).
* **Layouts that draw a sample chart** or other sample content cannot be chosen by role; by name they need
  `allow_sample_graphics=True`. A typed page number such as `007` on a layout is turned into a slide-number field.
* Inherited size, line spacing, indents, alignment, insets and anchor are written explicitly on the slide, so
  `qc_layout` (which reads only the slide XML) sees what PowerPoint will draw.

`add_from_example()` clones an example slide (shapes, images, background) and rewrites the text of the shapes you name,
keeping every run/paragraph property; list values become paragraphs. Unnamed text shapes are an error (no leftover
sample text) unless `unassigned="drop"` or listed in `keep=`; `None` removes a shape or picture (logos, sample photos).
Typed page numbers in the bottom band become slide-number fields. Shapes that do not wrap (labels on tabs) keep their
drawn width; `loose=[...]` lets captions grow to the slide margins. Text must fit its box at the shape's own size (or
shrink to `min_scale`); a replacement picture must not cover text; chart/diagram frames cannot be cloned.

Deleting the examples: the sldId list, the relationships, custom shows, section lists and links from masters/layouts to
the removed slides are cleaned, so the package holds only the slides you built (verified by reopening in PowerPoint).

## 3. Palette

`theme_from_template(path)` derives a `Theme`-shaped dict from the theme XML and the master background (clrMap, lumMod
and lumOff resolved): body text from dk1/dk2 by contrast, the most saturated readable accent, a dark header color
(or a lifted background on a dark master), caption/footer gray as the lightest value that still reaches 4.5:1 on the
slide and on the highlight tint, tints for highlight/zebra/warning. `contrast_report` lists every pair with its ratio;
`all_pass` must be true before the draft is pasted into `THEMES` (`theme_entry_source(d, name)` prints the `_theme(...)` call).
The template's fonts are returned separately (`template_fonts`); our themes stay Arial.

## 4. QC on a template deck

```
"$PY" scripts/qc_deck.py deck.pptx --external-template [--source content_analysis.json]
"$PY" scripts/qc_layout.py deck.pptx --external-template
```

Both read the slide size from the file and scale their limits against 13.333 x 7.5 (side margins and widths by
width/13.333; Y floor, footer band by height/7.5; picture minimum 3 in by the smaller ratio). A deck within 0.2 % of the
reference size is checked with the original constants, so decks built by `Deck` behave exactly as before.

`--external-template` switches off what only describes our own themes: the closed palette hex list, Arial-only, the closed
type scale, line-spacing/space-after lists, no-autofit/word-wrap flags, value dispersion and the margin/floor box test (a
text box may extend past the edge with its text inside; only pictures more than 0.1 in outside are warned). It keeps
overflow, overlap, contrast (qc_layout L3, which now also resolves fills that come from `p:style`), notes, Hangul in the
body, the language gate, picture minimums and the number check.

## 5. What was measured (5 templates, 7-slide enzyme-cascade journal club each, rendered with PowerPoint and QC'd)

| template | size | path | works | does not |
|---|---|---|---|---|
| ETH (institutional, restricted) | 13.33 x 7.5 | `add()` | title with color block, content, picture-only, two-column picture+text, long bullet lists, sub-levels | closing layout colors level 2 white on white (refused); title layouts expect a photo (removed if absent) |
| SlidesCarnival minimalist grayscale | 20 x 11.25 | `add()` | big caps-style titles, photo+caption layouts, one-line statement slides; typed page numbers repaired to fields | text-heavy slides (small slots); one layout draws a sample chart picture |
| SlidesCarnival market research | 20 x 11.25 | `add()` | title, bullets, two columns, section | 90 pt title style needs 25-35 % scale; picture slot is 5.4 in wide, so figures are small |
| k105 group-meeting (MIT) | 13.33 x 7.5 | `add_from_example()` | agenda, background card+figure, two-figure result with conclusion bar, three take-aways, critique cards, closing | layouts are plain (design lives on the examples); fixed 4-5 item card counts; sample text is Chinese (replace all) |
| UCSD defense (MIT, branded) | 13.33 x 7.5 | `add_from_example()` | title band, chapter tracker (grays all but the current chapter), figure with running chapter footer, numbered claims | logos and photos must be dropped (`None`); one 6-row tracker, the unused rows stay as faint boxes |

Fonts that are not installed are rendered with a substitute, so capacities are estimates (+7 % width margin for faces
the estimator cannot measure).
