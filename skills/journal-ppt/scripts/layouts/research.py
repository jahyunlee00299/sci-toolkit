"""Research family: eight layouts whose composition is taken from real research / report templates.

  chapter_tracker   UCSD defense  repeated "Chapters" slide, current chapter lit, others dimmed (+ chapter_footer helper)
  paper_card        k105-blue     paper metadata card: journal / year / IF text / keyword pills / DOI / presenter strip
  figure_card       k105-blue     figure in a thin bordered card, "Fig N." caption + source, narrow takeaway bar
  claim_evidence    yctrrr        action-title claim, 2-4 evidence boxes with arrows, number callout; or finding/boundary/next
  donut_stat_band   SlidesCarnival market-research: 2-4 donut percentages in a tinted band
  matrix_2x2        SlidesCarnival McKinsey deck: 2x2 matrix, axis labels, up to 4 labelled items
  diverging_bar     SlidesCarnival McKinsey deck: horizontal diverging bars around a zero line, honest scale
  bw_divider_quote  SlidesMania black-and-white: hard dark / light field with a big statement, number or bordered quote

Only layout ideas and measured proportions were taken; no image, text, logo or font of any template is reused
(see references/layouts_research.md for the per-layout credit and the honest list of what is lost).

Rules kept (references/style_spec.md, layouts/__init__.py):
  * colours come only from the active Theme; text on a panel sits in that panel's own filled rectangle so qc_deck
    sees the real background; the colour is picked by WCAG contrast (>= 4.5:1, or 3:1 for >= 18 pt bold);
  * sizes/spacings come only from ROLES (stat_big 54 pt is declared via extra_sizes); line spacing only from the
    closed list {1.0, 1.15, 2.0};
  * every autoshape gets word_wrap + disable_autofit, decoration is named 'deco:*';
  * content is measured before placement and StyleError is raised when it cannot fit; nothing shrinks the type.
"""
from __future__ import annotations

import math

from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt
from lxml import etree

import deck_builder as _db
from deck_builder import (BOX_PAD, FOOTER_TOP, LINE_HEIGHT_FACTOR, LINE_SPACING, MARGIN, MIN_FIG_H, ROLES,
                          SLIDE_H, SLIDE_W, SPACE_AFTER, STAT_BIG_PT, Y_FLOOR, StyleError, contrast_ratio,
                          disable_autofit, required_contrast)
from layouts import register

try:                                         # bold-aware width for wrap checks (falls back to fit_check)
    from qc_layout import text_width_pt as _text_width_pt
except ImportError:                          # pragma: no cover
    _text_width_pt = None

EMU = 914400.0
__all__ = ["chapter_footer"]


# ----------------------------------------------------------------------------------------------
# small helpers: geometry, shapes, colour, measuring
# ----------------------------------------------------------------------------------------------
def _in(x) -> int:
    return int(Inches(x))


def _shape(slide, kind, left, top, width, height, fill, name, line=None, line_pt=1.0, adj=None):
    """Autoshape with the same word_wrap + disable_autofit treatment as Deck._autoshape.
    fill=None -> outline only (or nothing when line is None too)."""
    shp = slide.shapes.add_shape(kind, int(left), int(top), int(width), int(height))
    if fill is None:
        shp.fill.background()
    else:
        shp.fill.solid()
        shp.fill.fore_color.rgb = fill
    if line is None:
        shp.line.fill.background()
    else:
        shp.line.color.rgb = line
        shp.line.width = Pt(line_pt)
    shp.shadow.inherit = False
    shp.text_frame.word_wrap = True
    disable_autofit(shp.text_frame)
    if adj is not None:
        for i, a in enumerate(adj if isinstance(adj, (list, tuple)) else [adj]):
            shp.adjustments[i] = a
    shp.name = name
    return shp


def _rect(slide, left, top, width, height, fill, name, **kw):
    return _shape(slide, MSO_SHAPE.RECTANGLE, left, top, width, height, fill, name, **kw)


def _set_bg(slide, rgb):
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = rgb


def _candidates(deck):
    """Text colours a theme sanctions (all inside Theme.allowed_hex)."""
    p = deck.theme.palette
    seen, out = set(), []
    for c in (p["body"], p["title_main"], deck.theme.bg, p["table_hdr_text"], p["title_bar_text"],
              p["subtitle"], p["accent"], p["stat"], p["caption"]):
        if str(c) not in seen:
            seen.add(str(c))
            out.append(c)
    return out


def _text_on(deck, fill, pt, bold):
    """Best sanctioned text colour on `fill`; None when nothing reaches the required contrast."""
    best = max(_candidates(deck), key=lambda c: contrast_ratio(c, fill))
    return best if contrast_ratio(best, fill) >= required_contrast(pt, bold) else None


def _strong(deck):
    """(fill, text) pair the theme guarantees legible for 12 pt bold, hence for everything larger."""
    p = deck.theme.palette
    return p["table_hdr_bg"], p["table_hdr_text"]


def _emph(deck, pt=12, bold=True):
    """(fill, text) for a solid emphasis block: the strong fill, unless it barely stands out from the background
    (dark themes: 2A3541 on 11161C) -- then the accent chip."""
    strong, on_strong = _strong(deck)
    if contrast_ratio(strong, deck.theme.bg) >= 3.0:
        return strong, on_strong
    try:
        return _accent_pair(deck, pt, bold)
    except StyleError:
        return strong, on_strong


def _accent_pair(deck, pt, bold):
    """(fill, text) for a highlighted chip: the accent when text on it is legible, else a safe fallback."""
    p = deck.theme.palette
    for fill in (p["accent"], p["subtitle"], p["table_hdr_bg"]):
        col = _text_on(deck, fill, pt, bold)
        if col is not None:
            return fill, col
    raise StyleError(f"theme {deck.theme.name}: no legible highlight chip colour")


def _graphic(deck, bg, exclude=(), floor=3.0):
    """First sanctioned graphic colour with >= `floor` contrast against `bg` (bars, rings, arrows)."""
    p = deck.theme.palette
    for c in (p["accent"], p["subtitle"], p["title_main"], p["table_hdr_bg"], p["body"], p["stat"]):
        if str(c) in {str(e) for e in exclude}:
            continue
        if contrast_ratio(c, bg) >= floor:
            return c
    raise StyleError(f"theme {deck.theme.name}: no graphic colour reaches {floor}:1 on #{bg}")


def _muted(deck, bg):
    """Dimmed-but-legible text colour (>= 4.5:1) for 'not the current item'."""
    p = deck.theme.palette
    for c in (p["caption"], p["footer"], p["subtitle"], p["body"]):
        if contrast_ratio(c, bg) >= 4.5:
            return c
    raise StyleError("no muted text colour reaches 4.5:1")


def _lines(deck, text: str, role: str, width_in: float) -> int:
    """Wrapped line count: Deck.fit_check (regular metrics) maxed with a bold-aware greedy wrap."""
    n = deck.fit_check(text, role, width_in)["lines"]
    if _text_width_pt is None:
        return n
    spec = ROLES[role]
    limit = width_in * 72.0 * 0.97
    cur, count = "", 1
    for w in text.split():
        trial = (cur + " " + w).strip()
        if _text_width_pt(trial, deck.theme.font, spec["bold"], spec["pt"]) <= limit or not cur:
            cur = trial
        else:
            count += 1
            cur = w
    return max(n, count)


def _pitch_in(role: str, ls=None) -> float:
    return ROLES[role]["pt"] * LINE_HEIGHT_FACTOR * (LINE_SPACING[role] if ls is None else ls) / 72.0


def _need_text(value, what):
    if not isinstance(value, str) or not value.strip():
        raise StyleError(f"{what} must be a non-empty string")
    return value.strip()


def _need_list(value, what, lo, hi):
    if not isinstance(value, (list, tuple)) or not lo <= len(value) <= hi:
        raise StyleError(f"{what}: {lo}-{hi} items required (an empty list is rejected)")
    return list(value)


def _text_w_in(deck, text, role) -> float:
    spec = ROLES[role]
    if _text_width_pt is None:
        return len(text) * spec["pt"] * 0.52 / 72.0
    return _text_width_pt(text, deck.theme.font, spec["bold"], spec["pt"]) / 72.0


def _put(deck, slide, x, y, w, h, text, role, color=None, align=PP_ALIGN.LEFT, anchor=None, ls=None,
         fill=None, max_lines=None, what="text", name=None, shape_kind=None, line=None, line_pt=1.0, adj=None):
    """Role-styled text with a fit proof.  fill=None -> plain Deck text box (colour = role colour unless given);
    fill=RGB -> the text lives inside a rectangle (or `shape_kind`) of that colour so qc sees the real background,
    colour defaults to the best sanctioned one for that fill.  Raises StyleError when the text cannot fit."""
    inner = w / EMU - 0.2
    n = _lines(deck, text, role, inner)
    need = n * _pitch_in(role, ls) + BOX_PAD / EMU
    if (max_lines is not None and n > max_lines) or need > h / EMU + 0.01:
        raise StyleError(f"{what}: {n} line(s) of {role} text need {need:.2f} in but the box offers "
                         f"{h / EMU:.2f} in (max_lines={max_lines}); shorten the text, the type scale is closed")
    if fill is None:
        tb = deck.add_textbox(slide, int(x), int(y), int(w), int(h), text, role=role, align=align, line_spacing=ls)
        if color is not None:
            for p in tb.text_frame.paragraphs:
                for r in p.runs:
                    r.font.color.rgb = color
        if anchor is not None:
            tb.text_frame.vertical_anchor = anchor
        if name:
            tb.name = name
        return tb
    spec = deck._spec(role)
    col = color if color is not None else _text_on(deck, fill, spec["pt"], spec["bold"])
    if col is None:
        raise StyleError(f"{what}: no sanctioned text colour is legible on the fill")
    shp = _shape(slide, shape_kind or MSO_SHAPE.RECTANGLE, x, y, w, h, fill, name or "text-panel",
                 line=line, line_pt=line_pt, adj=adj)
    tf = shp.text_frame
    tf.margin_left = tf.margin_right = _in(0.1)
    tf.margin_top = tf.margin_bottom = _in(0.05)
    tf.vertical_anchor = anchor or MSO_ANCHOR.TOP
    p = tf.paragraphs[0]
    p.alignment = align
    p.line_spacing = LINE_SPACING[role] if ls is None else ls
    p.space_after = Pt(SPACE_AFTER.get(role, 0))
    r = p.add_run()
    r.text = text
    r.font.name = deck.theme.font
    r.font.size = Pt(spec["pt"])
    r.font.bold = spec["bold"]
    r.font.italic = spec["italic"]
    r.font.color.rgb = col
    return shp


def _footer(deck, slide, on_fill=None, chapter=None):
    """Page number (and footer_right).  Plain Deck footer on the default background; on another field the same
    boxes are drawn as filled shapes in a legible colour.  With `chapter`: the running chapter footer."""
    if chapter is not None:
        chapter_footer(deck, slide, chapter, on_fill=on_fill)
        return
    num = deck._next_num()
    if on_fill is None:
        deck._footer(slide, num)
        return
    col = _text_on(deck, on_fill, 9, False)
    if col is None:
        raise StyleError("no sanctioned footer colour reaches 4.5:1 on the field")
    _put(deck, slide, MARGIN, FOOTER_TOP, _in(1.0), _in(0.3), str(num), "footer", col, fill=on_fill, name="footer-num")
    if deck.footer_right:
        _put(deck, slide, SLIDE_W - _in(5.0), FOOTER_TOP, _in(4.7), _in(0.3), deck.footer_right, "footer", col,
             align=PP_ALIGN.RIGHT, fill=on_fill, name="footer-right")


def chapter_footer(deck, slide, chapter: str, on_fill=None):
    """Running footer in the UCSD style: a hairline in the accent colour, the current chapter title bottom-left and
    the page number (with the deck's footer_right text) bottom-right.  Use it INSTEAD of Deck._footer on any slide
    of a chapter-structured talk; claim_evidence and figure_card accept chapter=... and call it for you.
    The chapter title must fit one footer line (StyleError otherwise)."""
    chapter = _need_text(chapter, "chapter")
    num = deck._next_num()
    bg = on_fill if on_fill is not None else deck.theme.bg
    col = _text_on(deck, bg, 9, False)
    if col is None:
        raise StyleError("no sanctioned footer colour reaches 4.5:1 on the field")
    _rect(slide, MARGIN, _in(7.06), SLIDE_W - 2 * MARGIN, _in(0.02), deck.theme.palette["accent"], "deco:footer-rule")
    left_w = _in(9.4)
    right = f"{deck.footer_right}   {num}" if deck.footer_right else str(num)
    fill = on_fill
    _put(deck, slide, MARGIN, FOOTER_TOP, left_w, _in(0.3), chapter, "footer", col if fill is not None else None,
         fill=fill, max_lines=1, what="chapter_footer chapter title", name="footer-chapter")
    _put(deck, slide, SLIDE_W - MARGIN - _in(3.4), FOOTER_TOP, _in(3.4), _in(0.3), right, "footer",
         col if fill is not None else None, align=PP_ALIGN.RIGHT, fill=fill, max_lines=1, name="footer-page")


def _title(deck, slide, text, y=0.3, marker=True, x=0.6, w=12.13):
    """Page heading in the k105 manner: small triangle marker, one-line bold title, hairline underneath."""
    th = deck.theme
    text = _need_text(text, "title")
    off = 0.0
    if marker:
        tri = _shape(slide, MSO_SHAPE.ISOSCELES_TRIANGLE, _in(x), _in(y + 0.2), _in(0.26), _in(0.26),
                     th.palette["accent"], "deco:marker")
        tri.rotation = 90
        off = 0.38
    _put(deck, slide, _in(x + off), _in(y), _in(w - off), _in(0.7), text, "title_bar", th.palette["title_main"],
         anchor=MSO_ANCHOR.MIDDLE, max_lines=1, what="title")
    rule = th.rule_color if th.rule_color is not None else th.palette["subtitle"]
    _rect(slide, _in(x), _in(y + 0.74), _in(w), _in(0.025), rule, "deco:title-rule")


def _fit_picture(deck, slide, path, bx, by, bw, bh, name):
    """Place the picture inside the box, aspect ratio kept, centred; the figure must stay >= 3 in tall (or >= 9 in
    wide for panoramic strips).  Returns (x, y, w, h) in EMU."""
    if _db.PILImage is None:                 # pragma: no cover
        raise RuntimeError("Pillow is required")
    with _db.PILImage.open(path) as im:
        iw, ih = im.size
    s = min(bw / iw, bh / ih)
    w, h = int(iw * s), int(ih * s)
    if h < MIN_FIG_H and w < _db.MIN_FIG_W_FULL:
        raise StyleError(f"figure would be only {w / EMU:.1f} x {h / EMU:.1f} in; it must stay >= 3 in tall "
                         f"(or >= 9 in wide): give it more room or a cropped version")
    x, y = int(bx + (bw - w) / 2), int(by + (bh - h) / 2)
    pic = slide.shapes.add_picture(path, x, y, w, h)
    pic.name = name
    return x, y, w, h


def _arrow(slide, x1, y1, x2, y2, color, width_pt=1.5, name="deco:axis"):
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, int(x1), int(y1), int(x2), int(y2))
    c.line.color.rgb = color
    c.line.width = Pt(width_pt)
    ln = c.line._get_or_add_ln()
    tail = etree.SubElement(ln, qn("a:tailEnd"))
    tail.set("type", "triangle")
    c.name = name
    return c


def _fmt_num(v: float, signed=False) -> str:
    s = f"{abs(v):g}"
    sign = "−" if v < 0 else ("+" if signed and v > 0 else "")
    return sign + s


# ----------------------------------------------------------------------------------------------
# 1. chapter_tracker
# ----------------------------------------------------------------------------------------------
@register("chapter_tracker", kind="agenda",
          summary="Repeated 'Chapters' slide: numbered list, the current chapter lit (accent badge, bold, tinted row), "
                  "the others dimmed; optional right-hand brace groups; pairs with chapter_footer()",
          source="gh_ucsd_defense (MIT, x3zou/UCSD_Defense_Template): chapters slide repeated as a progress tracker; "
                 "structure only, no logo/photo/text copied")
def chapter_tracker(deck, chapters, current, title="Chapters", groups=None):
    """chapters: 2-7 chapter titles (str); current: 0-based index of the chapter being entered, or None for the
    opening overview where nothing is dimmed; title: slide heading; groups: optional list of up to 3
    (first, last, label) with 0-based inclusive indices, drawn as a brace + label on the right.
    The current row = accent badge + bold 18 pt title + tinted row; other rows = muted 4.5:1 text (never lighter)."""
    chapters = [_need_text(c, "chapter title") for c in _need_list(chapters, "chapters", 2, 7)]
    if current is not None and not (isinstance(current, int) and not isinstance(current, bool)
                                    and 0 <= current < len(chapters)):
        raise StyleError("current must be None or a 0-based index into chapters")
    title = _need_text(title, "title")
    groups = [] if groups is None else _need_list(groups, "groups", 1, 3)
    for g in groups:
        if not (isinstance(g, (tuple, list)) and len(g) == 3 and isinstance(g[0], int) and isinstance(g[1], int)):
            raise StyleError("each group is (first, last, label)")
        if not (0 <= g[0] <= g[1] < len(chapters)):
            raise StyleError("group indices must satisfy 0 <= first <= last < len(chapters)")
        _need_text(g[2], "group label")
    th, pal = deck.theme, deck.theme.palette
    muted = _muted(deck, th.bg)
    chip_fill, chip_text = _accent_pair(deck, 12, True)
    soft_fill = pal["highlight_bg"]
    soft_text = _text_on(deck, soft_fill, 12, True)
    if soft_text is None:
        raise StyleError("no legible number colour on the badge tint")

    slide = deck.new_slide()
    _put(deck, slide, _in(0.6), _in(0.35), _in(9.0), _in(0.75), title, "title_bar", pal["title_main"],
         anchor=MSO_ANCHOR.MIDDLE, max_lines=1, what="chapter_tracker title")
    _rect(slide, _in(0.7), _in(1.12), _in(1.6), _in(0.07), pal["accent"], "deco:title-underline")

    n = len(chapters)
    list_x, list_top, list_bot = _in(0.6), _in(1.5), _in(6.8)
    text_x = _in(1.45)
    text_w = _in(9.9 if groups else 11.2)
    inner = text_w / EMU - 0.2
    # row heights: wrapped lines of the (larger) current style bound every row so the list does not jump
    heights = []
    for i, c in enumerate(chapters):
        role = "subtitle" if i == current else "body"
        ls = None if i == current else 1.15
        k = _lines(deck, c, role, inner)
        if k > 3:
            raise StyleError(f"chapter {i + 1} wraps to {k} lines; keep chapter titles <= 3 lines")
        heights.append(max(0.62, k * _pitch_in(role, ls) + BOX_PAD / EMU + 0.1))
    gap = 0.08
    total = sum(heights) + gap * (n - 1)
    if total > (list_bot - list_top) / EMU + 0.01:
        raise StyleError(f"chapter list needs {total:.2f} in but {(list_bot - list_top) / EMU:.2f} in are free; "
                         f"shorten the chapter titles or use fewer chapters")
    y = list_top + (list_bot - list_top - _in(total)) // 3
    row_tops = []
    for i, c in enumerate(chapters):
        h = _in(heights[i])
        row_tops.append((y, h))
        is_cur = i == current
        if is_cur:
            _rect(slide, list_x, y, _in(12.05 if not groups else 10.85), h, soft_fill, "deco:current-row")
        bsz = _in(0.44)
        by = y + (h - bsz) // 2
        _put(deck, slide, list_x + _in(0.12), by, bsz, bsz, str(i + 1), "table_header",
             chip_text if is_cur else soft_text, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE,
             fill=chip_fill if is_cur else soft_fill, what="chapter badge", name="badge")
        if is_cur:
            _put(deck, slide, text_x, y, text_w, h, c, "subtitle", _text_on(deck, soft_fill, 18, True),
                 anchor=MSO_ANCHOR.MIDDLE, fill=soft_fill, what=f"chapter {i + 1}", name="chapter-current")
        else:
            col = muted if current is not None else pal["body"]
            _put(deck, slide, text_x, y, text_w, h, c, "body", col, anchor=MSO_ANCHOR.MIDDLE, ls=1.15,
                 what=f"chapter {i + 1}", name="chapter")
        y += h + _in(gap)
    # brace groups (UCSD: bracket + label at the right edge)
    for first, last, label in groups:
        top = row_tops[first][0]
        bot = row_tops[last][0] + row_tops[last][1]
        _shape(slide, MSO_SHAPE.RIGHT_BRACE, _in(11.45), top + _in(0.04), _in(0.22), bot - top - _in(0.08), None,
               "deco:group-brace", line=pal["subtitle"], line_pt=1.5)
        _put(deck, slide, _in(11.72), top, _in(1.3), bot - top, label, "table_header", pal["title_main"],
             anchor=MSO_ANCHOR.MIDDLE, max_lines=max(1, int((bot - top) / EMU / _pitch_in("table_header"))),
             what=f"group label {label!r}", name="group-label")
    _footer(deck, slide)
    return slide


# ----------------------------------------------------------------------------------------------
# 2. paper_card
# ----------------------------------------------------------------------------------------------
def _pills(deck, slide, items, x, y, w, max_rows, fill, line):
    """Keyword pills wrapped into rows inside width w (EMU); returns the bottom y (EMU)."""
    txt = _text_on(deck, fill, 12, False)
    if txt is None:
        raise StyleError("no legible pill text colour")
    h, gap_x, gap_y = _in(0.36), _in(0.14), _in(0.12)
    cx, cy, rows = x, y, 1
    for k in items:
        pw = _in(_text_w_in(deck, k, "table_cell") + 0.4)
        if pw > w:
            raise StyleError(f"keyword {k!r} is wider than the pill column")
        if cx + pw > x + w:
            cx, cy, rows = x, cy + h + gap_y, rows + 1
            if rows > max_rows:
                raise StyleError(f"keywords need more than {max_rows} pill rows; use fewer or shorter keywords")
        _put(deck, slide, cx, cy, pw, h, k, "table_cell", txt, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE,
             fill=fill, shape_kind=MSO_SHAPE.ROUNDED_RECTANGLE, line=line, line_pt=1.0, adj=0.5, max_lines=1,
             what=f"keyword {k!r}", name="pill")
        cx += pw + gap_x
    return cy + h


@register("paper_card", kind="title",
          summary="First slide of a journal club: bordered paper card (title, authors), metadata rows (journal, year, "
                  "impact-factor text, DOI), keyword pills, main-point bar and a full-width presenter strip",
          source="gh_k105_reference (MIT, SciToolsmith/journal-club-ppt, design origin unstated): paper-metadata card "
                 "with keyword pills and presenter line; structure only")
def paper_card(deck, title, journal, year, presenter, date, authors=None, impact_factor=None, doi=None,
               keywords=None, summary=None, venue=None):
    """title: paper title (<= 3 lines at 26 pt); journal; year (int/str); impact_factor: free text such as
    'IF 15.7 (JCR 2024)'; doi: free text; keywords: 1-6 strings; summary: one-sentence main point (<= 2 lines at
    16 pt); authors: one line; presenter + date + optional venue fill the bottom strip."""
    title = _need_text(title, "paper title")
    journal = _need_text(journal, "journal")
    year = _need_text(str(year), "year")
    presenter, date = _need_text(presenter, "presenter"), _need_text(date, "date")
    kws = None if keywords is None else [_need_text(k, "keyword") for k in _need_list(keywords, "keywords", 1, 6)]
    th, pal = deck.theme, deck.theme.palette
    strong, on_strong = _strong(deck)
    card_fill = pal["highlight_bg"]
    ink = _text_on(deck, card_fill, 26, True)
    if ink is None:
        raise StyleError("no legible title colour on the card tint")

    slide = deck.new_slide()
    # -- paper card (bordered, tinted, accent edge)
    cx, cy, cw, ch = _in(0.6), _in(0.45), _in(12.13), _in(2.05)
    _rect(slide, cx, cy, cw, ch, card_fill, "deco:card", line=pal["subtitle"], line_pt=1.0)
    _rect(slide, cx, cy, _in(0.14), ch, strong, "deco:card-edge")
    _put(deck, slide, cx + _in(0.3), cy + _in(0.1), cw - _in(0.5), _in(1.4), title, "title_bar", ink, fill=card_fill,
         max_lines=3, what="paper title", name="paper-title")
    if authors:
        _put(deck, slide, cx + _in(0.3), cy + _in(1.5), cw - _in(0.5), _in(0.4), _need_text(authors, "authors"),
             "sidebar_bullet", _text_on(deck, card_fill, 14, False), fill=card_fill, ls=1.0, max_lines=1,
             what="authors", name="authors")
    # -- metadata rows (left)
    rows = [("Journal", journal), ("Year", year)]
    if impact_factor:
        rows.append(("Impact factor", _need_text(impact_factor, "impact_factor")))
    if doi:
        rows.append(("DOI", _need_text(doi, "doi")))
    mx, my, mw, rh = _in(0.6), _in(2.8), _in(5.9), _in(0.5)
    label_w = _in(1.6)
    for i, (lab, val) in enumerate(rows):
        y = my + i * rh
        _put(deck, slide, mx, y, label_w, rh, lab, "table_header", pal["subtitle"], anchor=MSO_ANCHOR.MIDDLE,
             max_lines=1, what=f"label {lab}", name="meta-label")
        _put(deck, slide, mx + label_w, y, mw - label_w, rh, val, "sidebar_bullet", pal["body"], ls=1.0,
             anchor=MSO_ANCHOR.MIDDLE, max_lines=1, what=f"{lab} value", name="meta-value")
        _rect(slide, mx, y + rh - _in(0.01), mw, _in(0.012), pal["caption"], "deco:meta-rule")
    # -- keyword pills (right)
    px, pw = _in(7.0), _in(5.73)
    if kws:
        _put(deck, slide, px, my, pw, rh, "Keywords", "table_header", pal["subtitle"], anchor=MSO_ANCHOR.MIDDLE,
             max_lines=1, name="keywords-label")
        _pills(deck, slide, kws, px, my + _in(0.58), pw, 3, pal["highlight_bg"], pal["subtitle"])
    # -- main point bar
    if summary:
        sy, sh = _in(4.95), _in(1.3)
        tab_w = _in(1.9)
        e_fill, e_text = _emph(deck, 18, True)
        _put(deck, slide, _in(0.6), sy, tab_w, sh, "Main point", "subtitle", e_text, align=PP_ALIGN.CENTER,
             anchor=MSO_ANCHOR.MIDDLE, fill=e_fill, max_lines=2, name="main-point-tab")
        _put(deck, slide, _in(0.6) + tab_w, sy, _in(12.13) - tab_w, sh, _need_text(summary, "summary"), "body",
             _text_on(deck, pal["highlight_bg"], 16, False), anchor=MSO_ANCHOR.MIDDLE, fill=pal["highlight_bg"],
             ls=1.15, max_lines=3, what="summary", name="main-point")
    # -- presenter strip
    parts = [f"Presenter: {presenter}", date] + ([_need_text(venue, "venue")] if venue else [])
    e_fill, e_text = _emph(deck, 12, True)
    _put(deck, slide, _in(0.6), _in(6.4), _in(12.13), _in(0.5), "    |    ".join(parts), "table_header", e_text,
         anchor=MSO_ANCHOR.MIDDLE, fill=e_fill, max_lines=1, what="presenter strip", name="presenter-strip")
    _footer(deck, slide)
    return slide


# ----------------------------------------------------------------------------------------------
# 3. figure_card
# ----------------------------------------------------------------------------------------------
@register("figure_card", kind="figure",
          summary="Figure in a thin bordered card with 'Fig N.' caption and source line, optional numbered reading "
                  "notes on the right, and a narrow takeaway bar; aspect ratio kept, figure >= 3 in",
          source="gh_k105_reference (MIT, SciToolsmith/journal-club-ppt): figure framed in a bordered card with "
                 "'Fig' caption and a conclusion bar under it; structure only")
def figure_card(deck, title, fig_path, fig_no, caption, source, takeaway, notes=None, chapter=None):
    """title: heading (1 line); fig_path; fig_no: figure number (int/str, printed as 'Fig 3.'); caption (<= 2 lines at
    9.5 pt); source (one line, e.g. 'Source: Lee et al., Nat Catal 2024'); takeaway: one conclusion sentence (<= 2
    lines at 18 pt bold); notes: optional 1-3 short reading hints placed right of the card (not in assertion-evidence
    themes); chapter: optional running chapter title, switches the footer to chapter_footer()."""
    title = _need_text(title, "title")
    caption, source = _need_text(caption, "caption"), _need_text(source, "source")
    takeaway = _need_text(takeaway, "takeaway")
    fig_no = _need_text(str(fig_no), "fig_no")
    notes = None if notes is None else [_need_text(n, "note") for n in _need_list(notes, "notes", 1, 3)]
    if notes and not deck.theme.allow_bullets:
        raise StyleError(f"theme {deck.theme.name!r} forbids list text; drop notes=")
    th, pal = deck.theme, deck.theme.palette
    strong, on_strong = _strong(deck)
    card_fill = th.plate if th.plate is not None else th.bg
    slide = deck.new_slide()
    _title(deck, slide, title)

    top, bot = _in(1.35), _in(5.9)
    card_w = _in(7.7) if notes else _in(12.13)
    cap_lines = [f"Fig {fig_no}. {caption}", source]
    inner_cap_w = card_w - _in(0.3)
    n_cap = sum(_lines(deck, ln, "caption", inner_cap_w / EMU - 0.2) for ln in cap_lines)
    if n_cap > 3:
        raise StyleError("figure_card caption + source need more than 3 lines; shorten them")
    cap_h = _in(n_cap * _pitch_in("caption") + 0.14)
    pad = _in(0.15)
    box_h = (bot - top) - 2 * pad - cap_h - _in(0.06)
    if box_h / EMU < 3.0:
        raise StyleError("figure_card leaves < 3 in for the figure: shorten caption/source")
    # card width hugs the figure when there are no notes, so a 16:9 figure does not float in a huge frame
    with _db.PILImage.open(fig_path) as im:
        aspect = im.size[0] / im.size[1]
    if not notes:
        card_w = min(card_w, max(_in(7.7), int(box_h * aspect) + 2 * pad))
    cx = _in(0.6) if notes else (SLIDE_W - card_w) // 2
    _rect(slide, cx, top, card_w, bot - top, card_fill, "deco:card", line=pal["subtitle"], line_pt=1.0)
    _fit_picture(deck, slide, fig_path, cx + pad, top + pad, card_w - 2 * pad, box_h, "fig:card")
    cap_col = _text_on(deck, card_fill, 9.5, False)
    if cap_col is None:
        raise StyleError("no legible caption colour on the card")
    cap_y = top + pad + box_h + _in(0.06)
    cap_box = _shape(slide, MSO_SHAPE.RECTANGLE, cx + _in(0.05), cap_y, card_w - _in(0.1), cap_h, card_fill,
                     "caption-panel")
    tf = cap_box.text_frame
    tf.margin_left = tf.margin_right = _in(0.1)
    tf.margin_top = tf.margin_bottom = _in(0.05)
    spec = deck._spec("caption")
    for i, line in enumerate(cap_lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.LEFT
        p.line_spacing = LINE_SPACING["caption"]
        p.space_after = Pt(SPACE_AFTER["caption"] if i < len(cap_lines) - 1 else 0)
        r = p.add_run()
        r.text = line
        r.font.name = th.font
        r.font.size = Pt(spec["pt"])
        r.font.italic = spec["italic"]
        r.font.color.rgb = cap_col
    # reading notes
    if notes:
        nx, nw = cx + card_w + _in(0.35), _in(12.73) - (cx + card_w + _in(0.35))
        heads = []
        for k in notes:
            n_l = _lines(deck, k, "sidebar_bullet", (nw - _in(0.6)) / EMU - 0.2) if False else \
                _lines(deck, k, "sidebar_bullet", (nw - _in(0.6)) / EMU - 0.2)
            heads.append(max(0.7, n_l * _pitch_in("sidebar_bullet", 1.15) + BOX_PAD / EMU + 0.12))
        if sum(heads) + 0.15 * (len(notes) - 1) > (bot - top) / EMU:
            raise StyleError("figure_card notes do not fit beside the card; shorten them")
        ny = top
        for idx, (k, hh) in enumerate(zip(notes, heads)):
            _put(deck, slide, nx, ny + _in(0.05), _in(0.4), _in(0.4), str(idx + 1), "table_header",
                 on_strong, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, fill=strong,
                 shape_kind=MSO_SHAPE.OVAL, what="note number", name="note-badge")
            _put(deck, slide, nx + _in(0.5), ny, nw - _in(0.5), _in(hh), k, "sidebar_bullet", pal["body"], ls=1.15,
                 anchor=MSO_ANCHOR.TOP, what="note", name="note")
            ny += _in(hh + 0.15)
    # takeaway bar
    by, bh = _in(6.05), _in(0.85)
    e_fill, e_text = _emph(deck, 18, True)
    _rect(slide, _in(0.6), by, _in(0.14), bh, pal["accent"] if str(e_fill) != str(pal["accent"]) else strong,
          "deco:takeaway-tick")
    _put(deck, slide, _in(0.74), by, _in(11.99), bh, takeaway, "subtitle", e_text, anchor=MSO_ANCHOR.MIDDLE,
         fill=e_fill, max_lines=2, what="takeaway", name="takeaway")
    _footer(deck, slide, chapter=chapter)
    return slide


# ----------------------------------------------------------------------------------------------
# 4. claim_evidence
# ----------------------------------------------------------------------------------------------
CONCLUSION_KEYS = (("finding", "Finding"), ("boundary", "Boundary"), ("next_step", "Next step"))


@register("claim_evidence", kind="content",
          summary="Action-title claim sentence over 2-4 evidence boxes joined by arrows (+ optional number callout "
                  "card), or a Finding / Boundary / Next step conclusion triple; optional bottom line",
          extra_sizes=(STAT_BIG_PT,),
          source="gh_yctrrr_academic (MIT, yctrrr/academic-ppt-template): claim sentence under the header bar, "
                 "evidence chain with arrows, number callout card, 01/02/03 conclusion cards; structure only")
def claim_evidence(deck, claim, evidence=None, conclusion=None, section="Claim and evidence", note=None,
                   callout=None, bottom_line=None, chapter=None):
    """claim: the action title, a full sentence (<= 2 lines at 26 pt bold); section: label in the header bar;
    note: optional one-line sub-claim.  Body = EITHER evidence=[{head, text}, ...] (2-4 boxes; 3 when a callout is
    given) OR conclusion={finding, boundary, next_step}.  callout={number, label, note} adds a card with a 54 pt
    number (<= 6 chars).  bottom_line: optional one-sentence summary strip.  chapter: running chapter footer."""
    claim = _need_text(claim, "claim")
    section = _need_text(section, "section")
    if (evidence is None) == (conclusion is None):
        raise StyleError("claim_evidence takes exactly one body: evidence=[...] or conclusion={...}")
    th, pal = deck.theme, deck.theme.palette
    strong, on_strong = _strong(deck)
    if evidence is not None:
        evidence = _need_list(evidence, "evidence", 2, 4)
        for e in evidence:
            _need_text(e.get("head"), "evidence head")
            _need_text(e.get("text"), "evidence text")
        if callout is not None and len(evidence) > 3:
            raise StyleError("with a callout card at most 3 evidence boxes fit")
    else:
        if callout is not None:
            raise StyleError("callout is only available with evidence=[...]")
        if not isinstance(conclusion, dict) or set(conclusion) != {k for k, _ in CONCLUSION_KEYS}:
            raise StyleError("conclusion needs exactly the keys finding, boundary, next_step")
        for k, _ in CONCLUSION_KEYS:
            _need_text(conclusion[k], f"conclusion {k}")
    if callout is not None:
        for k in ("number", "label", "note"):
            _need_text(callout.get(k), f"callout {k}")
        if len(callout["number"].strip()) > 6:
            raise StyleError("callout number: at most 6 characters at 54 pt")

    slide = deck.new_slide()
    # header bar with the section label, then the claim in the accent when legible (large bold text)
    _rect(slide, 0, 0, SLIDE_W, _in(0.62), strong, "deco:header-bar")
    _put(deck, slide, _in(0.5), 0, _in(9.0), _in(0.62), section, "subtitle", on_strong, anchor=MSO_ANCHOR.MIDDLE,
         fill=strong, max_lines=1, what="section label", name="section-label")
    claim_col = pal["accent"] if contrast_ratio(pal["accent"], th.bg) >= 4.5 else pal["title_main"]
    _put(deck, slide, _in(0.6), _in(0.78), _in(12.13), _in(1.05), claim, "title_bar", claim_col, max_lines=2,
         what="claim", name="claim")
    if note:
        _put(deck, slide, _in(0.6), _in(1.85), _in(12.13), _in(0.42), _need_text(note, "note"), "sidebar_bullet",
             pal["body"], ls=1.15, max_lines=1, what="note", name="claim-note")
    box_fill = pal["highlight_bg"]
    head_txt = _text_on(deck, box_fill, 18, True)
    if head_txt is None or _text_on(deck, box_fill, 16, False) is None:
        raise StyleError("no legible text colour on the box tint")
    arrow_col = _graphic(deck, th.bg)
    HEAD_BLOCK = 0.75                      # inches reserved above the box text (head row + gap)

    def _text_h(texts, role, w_emu):
        return max(_lines(deck, t, role, w_emu / EMU - 0.2) for t in texts) * _pitch_in(role, 1.15) + BOX_PAD / EMU

    if evidence is not None:
        n = len(evidence)
        total_w = _in(12.13) if callout is None else _in(8.2)
        gap = _in(0.5)
        bw = int((total_w - gap * (n - 1)) / n)
        texts = [e["text"].strip() for e in evidence]
        role = next((r_ for r_ in ("body", "sidebar_bullet") if _text_h(texts, r_, bw - _in(0.2)) <= 2.3), None)
        if role is None:
            raise StyleError("an evidence text needs more than 2.3 in even at 14 pt; shorten it")
        box_txt = _text_on(deck, box_fill, ROLES[role]["pt"], False)
        box_h = max(HEAD_BLOCK + _text_h(texts, role, bw - _in(0.2)) + 0.2, 1.9)
        if callout is not None:
            note_h = _lines(deck, callout["note"].strip(), "sidebar_bullet", _in(3.58) / EMU - 0.4) \
                * _pitch_in("sidebar_bullet", 1.15) + BOX_PAD / EMU
            box_h = max(box_h, 2.1 + note_h + 0.15)
    else:
        gap = _in(0.32)
        cw = int((_in(12.13) - 2 * gap) / 3)
        texts = [conclusion[k].strip() for k, _ in CONCLUSION_KEYS]
        box_h = max(0.95 + _text_h(texts, "body", cw - _in(0.2)) + 0.2, 2.4)
    if box_h > 3.6:
        raise StyleError(f"claim_evidence body needs {box_h:.2f} in (max 3.6); shorten the texts")
    block_h = box_h + (0.3 + 0.8 if bottom_line else 0.0)
    top0 = 2.45 + max(0.0, (6.85 - 2.45 - block_h) / 3)
    y0, y1 = _in(top0), _in(top0 + box_h)

    if evidence is not None:
        for i, e in enumerate(evidence):
            x = _in(0.6) + i * (bw + gap)
            _shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, x, y0, bw, y1 - y0, box_fill, "deco:evidence-box",
                   line=pal["subtitle"], line_pt=1.25, adj=0.06)
            _put(deck, slide, x + _in(0.1), y0 + _in(0.1), bw - _in(0.2), _in(0.55), e["head"].strip(), "subtitle",
                 head_txt, fill=box_fill, anchor=MSO_ANCHOR.MIDDLE, max_lines=1, what=f"evidence {i + 1} head",
                 name="evidence-head")
            _put(deck, slide, x + _in(0.1), y0 + _in(HEAD_BLOCK), bw - _in(0.2), y1 - y0 - _in(HEAD_BLOCK + 0.05),
                 e["text"].strip(), role, box_txt, fill=box_fill, ls=1.15, what=f"evidence {i + 1} text",
                 name="evidence-text")
            if i < n - 1:
                _shape(slide, MSO_SHAPE.RIGHT_ARROW, x + bw + _in(0.07), (y0 + y1) // 2 - _in(0.17), gap - _in(0.14),
                       _in(0.34), arrow_col, "deco:arrow")
        if callout is not None:
            cx, cw = _in(9.15), _in(3.58)
            c_fill, c_text = _emph(deck, 14, False)
            _shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, cx, y0, cw, y1 - y0, c_fill, "deco:callout-card", adj=0.06)
            inner_h = y1 - y0
            _put(deck, slide, cx + _in(0.1), y0 + _in(0.15), cw - _in(0.2), _in(1.05), callout["number"].strip(),
                 "stat_big", c_text, align=PP_ALIGN.CENTER, fill=c_fill, anchor=MSO_ANCHOR.MIDDLE, max_lines=1,
                 what="callout number", name="callout-number")
            _put(deck, slide, cx + _in(0.1), y0 + _in(1.3), cw - _in(0.2), _in(0.7), callout["label"].strip(),
                 "subtitle", c_text, align=PP_ALIGN.CENTER, fill=c_fill, max_lines=2, what="callout label",
                 name="callout-label")
            _put(deck, slide, cx + _in(0.1), y0 + _in(2.1), cw - _in(0.2), inner_h - _in(2.2),
                 callout["note"].strip(), "sidebar_bullet", c_text, align=PP_ALIGN.CENTER, fill=c_fill, ls=1.15,
                 what="callout note", name="callout-note")
    else:
        for i, (key, head) in enumerate(CONCLUSION_KEYS):
            x = _in(0.6) + i * (cw + gap)
            _shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, x, y0, cw, y1 - y0, box_fill, "deco:conclusion-card",
                   line=pal["subtitle"], line_pt=1.25, adj=0.05)
            _put(deck, slide, x + _in(0.2), y0 + _in(0.2), _in(0.55), _in(0.55), f"{i + 1:02d}", "table_header",
                 on_strong, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, fill=strong, shape_kind=MSO_SHAPE.OVAL,
                 name="number-circle")
            _put(deck, slide, x + _in(0.85), y0 + _in(0.2), cw - _in(1.0), _in(0.55), head, "subtitle", head_txt,
                 fill=box_fill, anchor=MSO_ANCHOR.MIDDLE, max_lines=1, name="conclusion-head")
            _put(deck, slide, x + _in(0.1), y0 + _in(0.95), cw - _in(0.2), y1 - y0 - _in(1.0),
                 conclusion[key].strip(), "body", _text_on(deck, box_fill, 16, False), fill=box_fill, ls=1.15,
                 what=f"conclusion {key}", name="conclusion-text")
    if bottom_line:
        _put(deck, slide, _in(0.6), y1 + _in(0.3), _in(12.13), _in(0.8), _need_text(bottom_line, "bottom_line"),
             "subtitle", head_txt, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, fill=box_fill,
             shape_kind=MSO_SHAPE.ROUNDED_RECTANGLE, adj=0.2, max_lines=2, what="bottom_line", name="bottom-line")
    _footer(deck, slide, chapter=chapter)
    return slide


# ----------------------------------------------------------------------------------------------
# 5. donut_stat_band
# ----------------------------------------------------------------------------------------------
def _check_pct(v, what):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise StyleError(f"{what}: percentage must be a finite number")
    if not 0 <= v <= 100:
        raise StyleError(f"{what}: percentage {v} is outside 0-100")
    return float(v)


@register("donut_stat_band", kind="data",
          summary="2-4 donut gauges (value arc over a ring, percentage in the hole) in a full-width tinted band, with "
                  "a bold label and a short note under each; native block-arc shapes, sweep = value x 3.6 degrees",
          source="sc_market-research-report-slides (SlidesCarnival CC BY 4.0): three donut percentages in a pale band; "
                 "structure only, credit slidescarnival.com")
def donut_stat_band(deck, title, items, footnote=None):
    """title: heading (1 line); items: 2-4 dicts {value: 0-100 (float/int, from the caller), label: str (<= 2 lines at
    18 pt bold), note: optional str (<= 3 lines at 14 pt)}; footnote: optional one caption line (source / n)."""
    title = _need_text(title, "title")
    items = _need_list(items, "items", 2, 4)
    vals = [_check_pct(it.get("value"), f"item {i + 1}") for i, it in enumerate(items)]
    for it in items:
        _need_text(it.get("label"), "item label")
    th, pal = deck.theme, deck.theme.palette
    band = pal["highlight_bg"]
    track = next((c for c in (th.bg, pal["zebra"], pal["caption"]) if contrast_ratio(c, band) >= 1.12), None)
    if track is None:
        raise StyleError("no ring track colour distinguishable from the band")
    arc = _graphic(deck, band, exclude=[track])
    hole_txt = _text_on(deck, band, 18, True)
    if hole_txt is None:
        raise StyleError("no legible percentage colour on the band")

    slide = deck.new_slide()
    _title(deck, slide, title, marker=False)
    band_y, band_h = _in(1.6), _in(3.15)
    _rect(slide, 0, band_y, SLIDE_W, band_h, band, "deco:band")
    n = len(items)
    D, t = _in(2.2), 0.17
    for i, (it, v) in enumerate(zip(items, vals)):
        slot_w = _in(12.13) / n
        cxm = int(_in(0.6) + slot_w * (i + 0.5))
        x, y = cxm - D // 2, band_y + (band_h - D) // 2
        ring = _shape(slide, MSO_SHAPE.DONUT, x, y, D, D, track, f"donut:track {i + 1}", adj=t)
        if v >= 100:
            _shape(slide, MSO_SHAPE.DONUT, x, y, D, D, arc, f"donut:arc {i + 1} = 100%", adj=t)
        elif v > 0:
            a = _shape(slide, MSO_SHAPE.BLOCK_ARC, x, y, D, D, arc, f"donut:arc {i + 1} = {v:g}%")
            end = (270.0 + 3.6 * v) % 360.0
            a.adjustments[0] = 270.0 * 60000 / 100000          # start at 12 o'clock (angles are 60000ths of a degree)
            a.adjustments[1] = end * 60000 / 100000
            a.adjustments[2] = t                                # ring thickness, same ratio as the track
        hole_d = int(D * (1 - 2 * t) * 0.96)
        hx, hy = cxm - hole_d // 2, band_y + (band_h - hole_d) // 2
        label = f"{v:g}%"
        _put(deck, slide, hx, hy, hole_d, hole_d, label, "subtitle", hole_txt, align=PP_ALIGN.CENTER,
             anchor=MSO_ANCHOR.MIDDLE, fill=band, shape_kind=MSO_SHAPE.OVAL, max_lines=1, what=f"donut {i + 1} value",
             name=f"donut:value {i + 1}")
        lw = int(slot_w - _in(0.4))
        lx = cxm - lw // 2
        _put(deck, slide, lx, _in(4.9), lw, _in(0.75), it["label"].strip(), "subtitle", pal["title_main"],
             align=PP_ALIGN.CENTER, max_lines=2, what=f"item {i + 1} label", name="donut-label")
        if it.get("note"):
            _put(deck, slide, lx, _in(5.65), lw, _in(1.05), _need_text(it["note"], "note"), "sidebar_bullet",
                 pal["body"], align=PP_ALIGN.CENTER, ls=1.15, max_lines=3, what=f"item {i + 1} note",
                 name="donut-note")
    if footnote:
        _put(deck, slide, _in(0.6), _in(6.72), _in(12.13), _in(0.3), _need_text(footnote, "footnote"), "caption",
             pal["caption"], max_lines=1, what="footnote", name="footnote")
    _footer(deck, slide)
    return slide


# ----------------------------------------------------------------------------------------------
# 6. matrix_2x2
# ----------------------------------------------------------------------------------------------
QUADS = ("TL", "TR", "BL", "BR")


@register("matrix_2x2", kind="data",
          summary="2x2 matrix with arrowed axes, end labels, optional quadrant names and an emphasised quadrant, up to "
                  "4 numbered items placed at caller coordinates (0-1), optional reading notes at the right",
          source="sc_mckinsey-strategic-planning-slides (SlidesCarnival CC BY 4.0): 2x2 matrix with dark numbered "
                 "markers and X/Y axis labels; structure only, credit slidescarnival.com")
def matrix_2x2(deck, title, x_label, y_label, items, x_low="Low", x_high="High", y_low="Low", y_high="High",
               quadrants=None, emphasis=None, notes=None):
    """title; x_label / y_label: axis titles; x_low/x_high/y_low/y_high: end labels; items: 1-4 dicts
    {label, x, y} with x, y in [0, 1] (0 = low end, 1 = high end of the axis; plotted linearly inside the plot
    area, kept clear of the frame by one marker radius); quadrants: optional 4 names ordered TL, TR, BL, BR;
    emphasis: one of TL/TR/BL/BR (thick outline); notes: optional 1-3 reading hints (not in assertion-evidence)."""
    title = _need_text(title, "title")
    x_label, y_label = _need_text(x_label, "x_label"), _need_text(y_label, "y_label")
    ends = [_need_text(s, "axis end label") for s in (x_low, x_high, y_low, y_high)]
    items = _need_list(items, "items", 1, 4)
    for it in items:
        _need_text(it.get("label"), "item label")
        for k in ("x", "y"):
            v = it.get(k)
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 1:
                raise StyleError(f"item {it.get('label')!r}: {k} must be a number in [0, 1]")
    if quadrants is not None:
        quadrants = [_need_text(q, "quadrant name") for q in _need_list(quadrants, "quadrants", 4, 4)]
    if emphasis is not None and emphasis not in QUADS:
        raise StyleError(f"emphasis must be one of {QUADS}")
    notes = None if notes is None else [_need_text(n, "note") for n in _need_list(notes, "notes", 1, 3)]
    if notes and not deck.theme.allow_bullets:
        raise StyleError(f"theme {deck.theme.name!r} forbids list text; drop notes=")
    th, pal = deck.theme, deck.theme.palette
    strong, on_strong = _strong(deck)
    plate = pal["highlight_bg"]
    plate_txt = _text_on(deck, plate, 14, False)
    if plate_txt is None:
        raise StyleError("no legible text colour on the plot tint")

    slide = deck.new_slide()
    _title(deck, slide, title, marker=False)
    px, py = _in(1.9), _in(1.5)
    pw = _in(7.4) if notes else _in(10.8)
    ph = _in(4.3)
    _rect(slide, px, py, pw, ph, plate, "deco:plot", line=pal["caption"], line_pt=0.75)
    mid_x, mid_y = px + pw // 2, py + ph // 2
    div = pal["caption"]
    _rect(slide, mid_x - _in(0.01), py, _in(0.02), ph, div, "deco:divider-v")
    _rect(slide, px, mid_y - _in(0.01), pw, _in(0.02), div, "deco:divider-h")
    if emphasis:
        ex = px if emphasis in ("TL", "BL") else mid_x
        ey = py if emphasis in ("TL", "TR") else mid_y
        _shape(slide, MSO_SHAPE.RECTANGLE, ex, ey, pw // 2, ph // 2, None, "deco:emphasis", line=pal["subtitle"],
               line_pt=3.0)
    if quadrants:
        for q, name in zip(QUADS, quadrants):
            qx = px if q in ("TL", "BL") else mid_x
            qy = py if q in ("TL", "TR") else mid_y
            _put(deck, slide, qx + _in(0.08), qy + _in(0.06), pw // 2 - _in(0.16), _in(0.36), name, "table_header",
                 _text_on(deck, plate, 12, True), fill=plate, max_lines=1, what=f"quadrant {q}", name=f"quadrant {q}")
    # axes
    ax = _graphic(deck, th.bg)
    _arrow(slide, px - _in(0.14), py + ph, px - _in(0.14), py, ax, name="deco:y-axis")
    _arrow(slide, px, py + ph + _in(0.14), px + pw, py + ph + _in(0.14), ax, name="deco:x-axis")
    lw = _in(1.45)
    lx = _in(0.3)
    _put(deck, slide, lx, py, lw, _in(0.6), ends[3], "table_cell", pal["body"], align=PP_ALIGN.RIGHT, max_lines=2,
         what="y_high", name="y-high")
    _put(deck, slide, lx, py + ph - _in(0.6), lw, _in(0.6), ends[2], "table_cell", pal["body"], align=PP_ALIGN.RIGHT,
         anchor=MSO_ANCHOR.BOTTOM, max_lines=2, what="y_low", name="y-low")
    _put(deck, slide, lx, py + ph // 2 - _in(0.55), lw, _in(1.1), y_label, "table_header", pal["title_main"],
         align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE, max_lines=4, what="y_label", name="y-label")
    ty = py + ph + _in(0.2)
    _put(deck, slide, px, ty, _in(2.4), _in(0.34), ends[0], "table_cell", pal["body"], max_lines=1, what="x_low",
         name="x-low")
    _put(deck, slide, px + pw - _in(2.4), ty, _in(2.4), _in(0.34), ends[1], "table_cell", pal["body"],
         align=PP_ALIGN.RIGHT, max_lines=1, what="x_high", name="x-high")
    _put(deck, slide, px + pw // 2 - _in(2.0), ty, _in(4.0), _in(0.34), x_label, "table_header", pal["title_main"],
         align=PP_ALIGN.CENTER, max_lines=1, what="x_label", name="x-label")
    # items
    r = _in(0.22)
    placed = []
    for k, it in enumerate(items):
        cx = int(px + r + it["x"] * (pw - 2 * r))
        cy = int(py + ph - r - it["y"] * (ph - 2 * r))
        label = it["label"].strip()
        lw_in = min(2.6, _text_w_in(deck, label, "sidebar_bullet") + 0.25)
        n_l = _lines(deck, label, "sidebar_bullet", lw_in - 0.2)
        lh = _in(n_l * _pitch_in("sidebar_bullet", 1.0) + 0.12)
        if n_l > 2:
            raise StyleError(f"item label {label!r} wraps to {n_l} lines; shorten it")
        lwe = _in(lw_in)
        sides = (1, -1) if it["x"] <= 0.62 else (-1, 1)
        spot = None
        for sd in sides:
            lxx = cx + r + _in(0.06) if sd == 1 else cx - r - _in(0.06) - lwe
            lyy = cy - lh // 2
            rect = (lxx, lyy, lxx + lwe, lyy + lh)
            inside = rect[0] >= px + _in(0.04) and rect[2] <= px + pw - _in(0.04) and \
                rect[1] >= py + _in(0.04) and rect[3] <= py + ph - _in(0.04)
            cross_v = rect[0] < mid_x + _in(0.04) and rect[2] > mid_x - _in(0.04)
            cross_h = rect[1] < mid_y + _in(0.04) and rect[3] > mid_y - _in(0.04)
            clash = any(not (rect[2] <= o[0] or rect[0] >= o[2] or rect[3] <= o[1] or rect[1] >= o[3])
                        for o in placed)
            if inside and not cross_v and not cross_h and not clash:
                spot = (sd, lxx, lyy, rect)
                break
        if spot is None:
            raise StyleError(f"item {label!r}: its label would leave the plot, cross a quadrant divider or hit "
                             f"another label; move the item or shorten the label")
        sd, lxx, lyy, rect = spot
        placed.append(rect)
        placed.append((cx - r, cy - r, cx + r, cy + r))
        _put(deck, slide, lxx, lyy, lwe, lh, label, "sidebar_bullet", plate_txt, fill=plate, ls=1.0,
             anchor=MSO_ANCHOR.MIDDLE, align=PP_ALIGN.LEFT if sd == 1 else PP_ALIGN.RIGHT, max_lines=2,
             what=f"item {k + 1} label", name=f"item-label {k + 1}")
        _put(deck, slide, cx - r, cy - r, 2 * r, 2 * r, str(k + 1), "table_header", on_strong, align=PP_ALIGN.CENTER,
             anchor=MSO_ANCHOR.MIDDLE, fill=strong, shape_kind=MSO_SHAPE.OVAL, line=pal["title_main"], line_pt=1.5,
             max_lines=1, name=f"item-marker {k + 1}")
    if notes:
        nx, nw = _in(9.75), _in(2.98)
        _put(deck, slide, nx, py, nw, _in(0.4), "How to read", "table_header", pal["subtitle"], max_lines=1,
             name="notes-head")
        ny = py + _in(0.5)
        for k in notes:
            n_l = _lines(deck, k, "sidebar_bullet", nw / EMU - 0.2)
            hh = _in(n_l * _pitch_in("sidebar_bullet", 1.15) + 0.2)
            if ny + hh > py + ph:
                raise StyleError("matrix_2x2 notes do not fit beside the plot")
            _put(deck, slide, nx, ny, nw, hh, k, "sidebar_bullet", pal["body"], ls=1.15, name="note")
            ny += hh
    _footer(deck, slide)
    return slide


# ----------------------------------------------------------------------------------------------
# 7. diverging_bar
# ----------------------------------------------------------------------------------------------
def _nice_max(v: float) -> float:
    for k in range(-6, 7):
        for m in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
            c = m * 10.0 ** k
            if c >= v * (1 - 1e-12):
                return c
    raise StyleError("value range too large")


@register("diverging_bar", kind="data",
          summary="Horizontal diverging bars around a zero line, one row per item, bar length = |value| / axis half-range "
                  "(linear, never clipped), signed value labels, ticks and optional side captions",
          source="sc_mckinsey-strategic-planning-slides (SlidesCarnival CC BY 4.0): 'important numbers' horizontal "
                 "diverging bar with a centre line; structure only, credit slidescarnival.com")
def diverging_bar(deck, title, rows, vmax=None, unit="", left_caption=None, right_caption=None, source=None):
    """title; rows: 2-7 dicts {label, value} with signed finite numbers from the caller; vmax: axis half-range
    (default: the next round number above max |value|; must be >= max |value|, so no bar is ever clipped);
    unit: text appended to value labels (e.g. '%', ' mM'); left_caption / right_caption: what negative / positive
    means (e.g. 'Lower titer'); source: optional caption line.  Zero-valued rows draw no bar."""
    title = _need_text(title, "title")
    rows = _need_list(rows, "rows", 2, 7)
    vals = []
    for r_ in rows:
        _need_text(r_.get("label"), "row label")
        v = r_.get("value")
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            raise StyleError(f"row {r_.get('label')!r}: value must be a finite number")
        vals.append(float(v))
    top = max(abs(v) for v in vals)
    if top == 0 and vmax is None:
        raise StyleError("all values are zero: pass vmax to draw an empty axis")
    if vmax is None:
        vmax = _nice_max(top)
    elif isinstance(vmax, bool) or not isinstance(vmax, (int, float)) or vmax <= 0 or vmax < top:
        raise StyleError(f"vmax must be a number >= max |value| ({top:g}); a smaller axis would clip bars")
    vmax = float(vmax)
    unit = unit or ""
    th, pal = deck.theme, deck.theme.palette
    neg_c = _graphic(deck, th.bg)
    try:
        pos_c = _graphic(deck, th.bg, exclude=[neg_c])
    except StyleError:
        pos_c = neg_c                       # sign is still carried by the side of the zero line and the label
    slide = deck.new_slide()
    _title(deck, slide, title, marker=False)

    cx = _in(8.05)
    half = _in(3.3)                              # bar length of |vmax|
    n = len(rows)
    row_h = _in(min(1.0, max(0.6, 4.2 / n)))
    y0 = _in(2.05 + max(0.0, 4.2 - n * row_h / EMU) / 3)
    plot_top, plot_bot = y0 - _in(0.1), y0 + n * row_h + _in(0.05)
    if left_caption:
        _put(deck, slide, cx - half - _in(0.2), _in(1.45), half + _in(0.1), _in(0.4), "← " + left_caption.strip(),
             "table_header", pal["title_main"], align=PP_ALIGN.LEFT, max_lines=1, what="left_caption",
             name="caption-left")
    if right_caption:
        _put(deck, slide, cx + _in(0.1), _in(1.45), half + _in(0.1), _in(0.4), right_caption.strip() + " →",
             "table_header", pal["title_main"], align=PP_ALIGN.RIGHT, max_lines=1, what="right_caption",
             name="caption-right")
    # grid + ticks
    grid = next((c for c in (pal["zebra"], pal["highlight_bg"], pal["warning_bg"])
                 if 1.05 <= contrast_ratio(c, th.bg) <= 2.5), None)
    for f in (-1.0, -0.5, 0.5, 1.0):
        gx = cx + int(f * half)
        if grid is not None:
            _rect(slide, gx - _in(0.006), plot_top, _in(0.012), plot_bot - plot_top, grid, "deco:grid")
        _rect(slide, gx - _in(0.006), plot_bot, _in(0.012), _in(0.08), pal["caption"], "deco:tick-mark")
    for f in (-1.0, -0.5, 0.0, 0.5, 1.0):
        gx = cx + int(f * half)
        tick = _fmt_num(f * vmax, signed=f > 0) if f != 0 else "0"
        _put(deck, slide, gx - _in(0.55), plot_bot + _in(0.05), _in(1.1), _in(0.32), tick, "table_cell",
             pal["caption"], align=PP_ALIGN.CENTER, max_lines=1, name="tick")
    # rows
    bar_h = int(row_h * 0.56)
    lab_x, lab_w = _in(0.5), _in(3.1)
    for i, (r_, v) in enumerate(zip(rows, vals)):
        ry = y0 + i * row_h
        _put(deck, slide, lab_x, ry, lab_w, row_h, r_["label"].strip(), "sidebar_bullet", pal["body"], ls=1.0,
             align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE, max_lines=2, what=f"row {i + 1} label", name="row-label")
        L = int(abs(v) / vmax * half)
        by = ry + (row_h - bar_h) // 2
        txt = f"{_fmt_num(v, signed=True)}{unit}" if v != 0 else f"0{unit}"
        if v > 0:
            _rect(slide, cx, by, max(L, _in(0.01)), bar_h, pos_c, f"bar:{r_['label'].strip()[:20]} {v:g}")
            _put(deck, slide, cx + L + _in(0.04), ry, _in(1.3), row_h, txt, "table_header", pal["title_main"],
                 anchor=MSO_ANCHOR.MIDDLE, max_lines=1, what=f"row {i + 1} value", name="value")
        elif v < 0:
            _rect(slide, cx - L, by, max(L, _in(0.01)), bar_h, neg_c, f"bar:{r_['label'].strip()[:20]} {v:g}")
            _put(deck, slide, cx - L - _in(0.04) - _in(1.3), ry, _in(1.3), row_h, txt, "table_header",
                 pal["title_main"], align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE, max_lines=1,
                 what=f"row {i + 1} value", name="value")
        else:
            _put(deck, slide, cx + _in(0.06), ry, _in(1.3), row_h, txt, "table_header", pal["title_main"],
                 anchor=MSO_ANCHOR.MIDDLE, max_lines=1, name="value")
    _rect(slide, cx - _in(0.015), plot_top, _in(0.03), plot_bot - plot_top, pal["title_main"], "deco:zero-line")
    if source:
        _put(deck, slide, _in(0.6), _in(6.6), _in(12.13), _in(0.32), _need_text(source, "source"), "caption",
             pal["caption"], max_lines=1, what="source", name="source")
    _footer(deck, slide)
    return slide


# ----------------------------------------------------------------------------------------------
# 8. bw_divider_quote
# ----------------------------------------------------------------------------------------------
def _big_fit(deck, text, w_emu, h_emu, what):
    """Largest sanctioned statement role that fits: stat_big (54 pt) then title_main (30 pt)."""
    for role in ("stat_big", "title_main"):
        n = _lines(deck, text, role, w_emu / EMU - 0.2)
        if n * _pitch_in(role) + BOX_PAD / EMU <= h_emu / EMU:
            return role
    raise StyleError(f"{what} does not fit even at 30 pt; shorten it")


@register("bw_divider_quote", kind="divider",
          summary="Hard dark or light field with an outlined frame: big statement (54 pt, else 30 pt) or giant number "
                  "with label, optional section numeral and a '>' kicker strip; or a bordered quote with attribution",
          extra_sizes=(STAT_BIG_PT,),
          source="sm_black-and-white (SlidesMania, personal-use licence: structure only, nothing reused): hard black / "
                 "off-white alternation, outlined white box, giant number slide, bordered quote")
def bw_divider_quote(deck, statement=None, number=None, quote=None, label=None, attribution=None, section=None,
                     kicker=None, tone="dark"):
    """Exactly one of statement (<= 25 words) / number (<= 12 chars, e.g. '3.2x') / quote (<= 45 words).
    tone 'dark' (strong theme fill, light text) or 'light' (theme background): alternate them down the deck.
    label: line under a number or statement (<= 2 lines at 18 pt); attribution: only with quote ('Name, source');
    section: small numeral/label top-left (e.g. '02'); kicker: text of the bottom strip with its '>' square."""
    given = [k for k, v in (("statement", statement), ("number", number), ("quote", quote)) if v is not None]
    if len(given) != 1:
        raise StyleError("bw_divider_quote takes exactly one of statement= / number= / quote=")
    if tone not in ("dark", "light"):
        raise StyleError("tone must be 'dark' or 'light'")
    if attribution is not None and quote is None:
        raise StyleError("attribution belongs to the quote variant")
    if section is not None and quote is not None:
        raise StyleError("the quote variant carries a quote mark top-left: drop section=")
    th, pal = deck.theme, deck.theme.palette
    strong, on_strong = _strong(deck)
    field, fg = (strong, on_strong) if tone == "dark" else (th.bg, pal["title_main"])
    if contrast_ratio(fg, field) < 4.5:
        raise StyleError("theme gives < 4.5:1 for this tone")
    if statement is not None:
        statement = _need_text(statement, "statement")
        if len(statement.split()) > 25:
            raise StyleError("statement: at most 25 words")
    if number is not None:
        number = _need_text(number, "number")
        if len(number) > 12:
            raise StyleError("number: at most 12 characters")
    if quote is not None:
        quote = _need_text(quote, "quote")
        if len(quote.split()) > 45:
            raise StyleError("quote: at most 45 words")

    slide = deck.new_slide()
    _set_bg(slide, field)
    frame_w = 1.5 if tone == "dark" else 2.25
    _shape(slide, MSO_SHAPE.RECTANGLE, _in(0.6), _in(0.5), _in(12.13), _in(6.35), None, "deco:frame", line=fg,
           line_pt=frame_w)
    if section:
        _put(deck, slide, _in(1.0), _in(0.8), _in(4.0), _in(0.7), _need_text(section, "section"), "title_main", fg,
             max_lines=1, what="section", name="section")
    area_x, area_w = _in(1.0), _in(11.33)
    if quote is not None:
        n_q = _lines(deck, quote, "title_main", area_w / EMU - 0.2)
        if n_q > 6:
            raise StyleError(f"quote wraps to {n_q} lines (max 6 at 30 pt)")
        q_h = n_q * _pitch_in("title_main") + BOX_PAD / EMU
        a_h = 0.85 if attribution else 0.0
        group = 1.0 + q_h + a_h
        top = 0.7 + max(0.0, (5.2 - group) / 2)
        _put(deck, slide, area_x, _in(top), _in(1.5), _in(1.0), "“", "stat_big", fg, max_lines=1, name="quote-mark")
        _put(deck, slide, area_x, _in(top + 1.0), area_w, _in(q_h), quote, "title_main", fg, max_lines=6,
             what="quote", name="quote")
        if attribution:
            _put(deck, slide, area_x, _in(top + 1.0 + q_h + 0.3), area_w, _in(0.55),
                 "— " + _need_text(attribution, "attribution"), "subtitle", fg, align=PP_ALIGN.RIGHT,
                 max_lines=1, what="attribution", name="attribution")
    else:
        text = statement if statement is not None else number
        lab_h = 0.0
        if label:
            label = _need_text(label, "label")
            lab_h = _lines(deck, label, "subtitle", area_w / EMU - 0.2) * _pitch_in("subtitle") + BOX_PAD / EMU
            if lab_h > 0.75:
                raise StyleError("label: at most 2 lines at 18 pt")
        avail = 4.0 - (lab_h + 0.2 if label else 0.0)
        if number is not None:
            role = "stat_big"
            if _lines(deck, text, role, area_w / EMU - 0.2) > 1:
                raise StyleError("number does not fit on one line")
        else:
            role = _big_fit(deck, text, area_w, _in(avail), "statement")
        n_t = _lines(deck, text, role, area_w / EMU - 0.2)
        t_h = n_t * _pitch_in(role) + BOX_PAD / EMU
        group = t_h + (0.2 + lab_h if label else 0.0)
        top = 1.6 + max(0.0, (4.3 - group) / 2)
        _put(deck, slide, area_x, _in(top), area_w, _in(t_h), text, role, fg, max_lines=5,
             what="statement" if statement is not None else "number", name="statement")
        if label:
            _put(deck, slide, area_x, _in(top + t_h + 0.2), area_w, _in(lab_h), label, "subtitle", fg, max_lines=2,
                 what="label", name="label")
    if kicker:
        ky = _in(6.1)
        _shape(slide, MSO_SHAPE.RECTANGLE, area_x, ky, area_w, _in(0.5), None, "deco:kicker-strip", line=fg, line_pt=1.0)
        _put(deck, slide, area_x + _in(0.1), ky, area_w - _in(0.7), _in(0.5), _need_text(kicker, "kicker"),
             "table_header", fg, anchor=MSO_ANCHOR.MIDDLE, max_lines=1, what="kicker", name="kicker")
        _put(deck, slide, area_x + area_w - _in(0.5), ky, _in(0.5), _in(0.5), ">", "table_header", field,
             align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, fill=fg, name="kicker-arrow")
    _footer(deck, slide, on_fill=field if tone == "dark" else None)
    return slide
