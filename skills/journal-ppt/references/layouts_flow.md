# Flow-family layouts (`scripts/layouts/flow.py`)

Four layouts for process / sequence / section structure. All colors come from the active theme palette, all text
sizes from the closed ROLES list (geometric_divider additionally declares stat_big 54 pt). Text fit is computed with
real Arial metrics; content that cannot fit raises `StyleError`. Slide text is English; Korean notes via `Deck.notes`.

## pipeline_rail  (G11, Cell Press graphical-abstract rail)
`deck.layout("pipeline_rail", steps=[...], title=..., cofactor_loop=(from, to, label), takeaway="...")`

* `steps`: 3-7 dicts `{label, sublabel, duration, kind, note}`; `kind` in `enzyme | substrate | product | cofactor`
  (default `enzyme`). 0-based indices everywhere.
* Node style encodes `kind` (and a text tag in the card repeats it, so it survives grayscale / color blindness):
  enzyme = filled disc, substrate = solid ring, product = filled disc in the second theme color, cofactor = dashed ring.
* Arrows are real connectors glued to the ellipse sites (right of node i -> left of node i+1), dashed rail look.
* `cofactor_loop`: curved arrow over the rail from step `from` to step `to`, label above the apex.
* `takeaway`: one line (<= ~90 characters at 18 pt bold) in a band at the bottom.
* Size tiers keep it legible: 3-4 steps use 18/14 pt text, 5-6 steps 14/12 pt, 7 steps 12 pt label + 12 pt body.
  A single word wider than its column (for example "Phosphoglucomutase" at 7 steps) raises `StyleError`: abbreviate.

## walkthrough_highlight  (same rail, one step enlarged)
`deck.layout("walkthrough_highlight", steps=..., active=3, ..., morph=True)` takes the same content plus `active`.
The active node is 1.3-1.5x larger with a wide detail card (tag, label, sublabel, note at larger sizes); the other
steps are dimmed (outlined node, dashed label-only card). The rail center line and card top are computed from both
states, so the rail does not jump vertically between slides.

Morph: every part carries a stable name via `Deck.name_shape`: `!!pr_node_<i>`, `!!pr_card_<i>`, `!!pr_text_<i>`,
`!!pr_pill_<i>`, `!!pr_arrow_<i>`, `!!pr_loop`, `!!pr_looplabel`. A `pipeline_rail` slide followed by a
`walkthrough_highlight` slide of the same content (or two walkthroughs with different `active`) animates with
`Deck.morph`; `morph=True` sets the transition on that slide. Playback itself cannot be tested headless.

## numbered_grid_agenda  (G10, chapter-numbered grid)
`deck.layout("numbered_grid_agenda", items=[("Background", "Why ..."), ...], title="Agenda", current=2)`
4-8 items (strings, `(label, desc)` or `{label, desc}`); grid 2x2 / 3x2 / 4x2 with a centered last row. `current`
fills that square and adds a tinted panel, so the same slide can recur as a section marker.

## geometric_divider  (G7, geometric primitives)
`deck.layout("geometric_divider", title=..., subtitle=..., number=3, variant="circles" | "bars" | "quarter")`
Text left (circles, bars) or right (quarter), the composition covers 30 % or more of the slide and may bleed off
the edge (shapes are named `deco:*`). Overlaps use alpha transparency on a palette color.

## Known limits
* Pictograms of the Cell graphical abstract and the hexagon / molecule corner art of the Slidesgo grid are not
  reproduced (no native shape), see ppt_layout_grammars_261004.md.
* Color is never the only carrier of `kind` (shape style plus text tag).
* With 3 steps the lower third of the rail slide stays empty by design; use a takeaway band or figure there.
