# Frame layouts (scripts/layouts/frame.py)

Six layouts that change the frame of a slide. Colors come only from the active theme; text color is chosen by
WCAG contrast against the fill. Text on a band sits in the band's own filled rectangle so qc_deck QC-18 sees the
real background. Decoration is named `deco:*`. Content is measured first; `StyleError` when it cannot fit.

| layout | grammar | kind | content keywords |
|---|---|---|---|
| `slate_header` | G2 Metropolis | content | `title` (1 line), `section`, `progress=(i, n)`, and exactly one of `bullets` (1-5) or `fig_path` + `caption` (+ `source`) |
| `block_boxes` | G5 Frankfurt | content | `title`, `blocks=[{kind: definition/result/alert/example/question, title, text or items}]` (2-4), `grid` `'1x'`/`'2x'`, optional `sections` + `current` (nav strip) |
| `statement_slide` | G13 Takahashi | divider | `statement` (<= 30 words), optional `emphasis` (accent substring), `attribution`; 54 pt `stat_big` (declared extra size), falls back to 30 pt |
| `corner_wedge_title` | G15 | title | `title`, `presenter`, `date`, optional `venue`, `subtitle`; top-left wedge + diagonal accent stripe, mirrored small wedge bottom-right, no logo |
| `band_title` | G3 + G14 | title | same params + `hero_fig`, `hero_focus` (0-1); hero is cover-cropped into a 12.7 x 1.9 in strip with picture crop, never stretched |
| `split_panel_figure` | G6 + G17 | figure | `title`, `fig_path`, `caption`, `source` (both mandatory), `takeaways` (2-3), `fig_side`; figure box >= 3 in tall |

`slate_frame(deck, title, section, progress)` (public helper) builds only the G2 frame; content may use
`SLATE_BODY_TOP` down to `Y_FLOOR`. `assertion_evidence` (no bullets): `slate_header` accepts a figure only,
`split_panel_figure` raises, `block_boxes` accepts `text=` blocks only.

## Honest limits
* Arial replaces Fira/serif faces; no letter-spacing, no small caps, no soft shadows, no gradients.
* G6 gradient/3D hero and G17 cut-out portrait are not reproduced (picture crop only).
* G3 engraving is 7 hairlines; the logo outline box is deliberately omitted.
* Where the accent fails 4.5:1 as large text (navy_lab orange on white 3.23:1) `statement_slide` still uses it
  (>= 3:1 rule for 18 pt bold); qc_layout reports that as a WARNING, not CRITICAL.
