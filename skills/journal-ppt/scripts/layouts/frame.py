"""Frame family: six layouts that change the *frame* of a slide, not only its colors.

  slate_header        G2   Metropolis slate header bar + thin progress line + section label
  block_boxes         G5   Frankfurt/Beamer titled blocks (definition/result/alert/example/question)
  statement_slide     G13  one huge sentence (Takahashi style), optional attribution
  corner_wedge_title  G15  institutional corner wedge as neutral geometry (no logo), title slide
  band_title          G3/G14  color field over a hairline band, hero figure cropped into a strip
  split_panel_figure  G6/G17  rounded card on a tinted canvas: figure one side, 2-3 takeaways the other

Rules kept (see references/style_spec.md and layouts/__init__.py):
  * colors come only from the active Theme (palette, bg, extra_hex); text colors are picked by WCAG
    contrast against the fill they sit on, so every one of the THEMES works;
  * sizes/spacings come only from ROLES (statement_slide declares the one extra size, stat_big 54 pt);
  * every text box goes through Deck.add_textbox / Deck.bullets (word_wrap + disable_autofit + Arial);
    every autoshape built here gets the same word_wrap + disable_autofit; decoration is named 'deco:*';
  * content is measured before it is placed (Deck.fit_check plus a bold-aware width check) and
    StyleError is raised when it cannot fit; nothing shrinks the type.
"""
from __future__ import annotations

from pathlib import Path

from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

from deck_builder import (BOX_PAD, CAPTION_GAP, LINE_HEIGHT_FACTOR, LINE_SPACING, MARGIN, MIN_FIG_H,
                          ROLES, SLIDE_H, SLIDE_W, SPACE_AFTER, STAT_BIG_PT, Y_FLOOR, StyleError,
                          contrast_ratio, disable_autofit, required_contrast)
from layouts import register

try:                                         # bold-aware width for wrap checks (falls back to fit_check)
    from qc_layout import text_width_pt as _text_width_pt
except ImportError:                          # pragma: no cover
    _text_width_pt = None

EMU = 914400.0
KO_FREE = "English slide text only; Korean goes to speaker notes via Deck.notes"   # doc marker, not used
SLATE_BODY_TOP = Inches(1.2)                 # first usable y under the slate bar (public: other layouts may sit in the frame)
BLOCK_KINDS = ("definition", "result", "alert", "example", "question")


# ----------------------------------------------------------------------------------------------
# small helpers (shapes, color, measuring)
# ----------------------------------------------------------------------------------------------
def _in(x) -> int:
    return int(Inches(x))


def _shape(deck, slide, kind, left, top, width, height, fill, name, line=None, line_pt=1.0,
           adj=None, flip_v=False, flip_h=False):
    """Autoshape with the same word_wrap + disable_autofit treatment as Deck._autoshape.
    fill=None -> outline only.  Colors are RGBColor values taken from the theme by the caller."""
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
        shp.adjustments[0] = adj
    if flip_v or flip_h:
        xfrm = shp._element.spPr.find("{http://schemas.openxmlformats.org/drawingml/2006/main}xfrm")
        if flip_v:
            xfrm.set("flipV", "1")
        if flip_h:
            xfrm.set("flipH", "1")
    shp.name = name
    return shp


def _rect(deck, slide, left, top, width, height, fill, name, **kw):
    return _shape(deck, slide, MSO_SHAPE.RECTANGLE, left, top, width, height, fill, name, **kw)


def _recolor(shape, rgb):
    for p in shape.text_frame.paragraphs:
        for r in p.runs:
            r.font.color.rgb = rgb


def _shape_text(deck, shp, text, role, color, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE,
                inset=(0.0, 0.0)):
    """Write `text` into an autoshape's own frame with the role's font, spacing and a color.
    inset = (left/right, top/bottom) in inches.  Used for badges and for every text that sits on a band."""
    spec = deck._spec(role)
    tf = shp.text_frame
    tf.margin_left = tf.margin_right = _in(inset[0])
    tf.margin_top = tf.margin_bottom = _in(inset[1])
    tf.vertical_anchor = anchor
    p = tf.paragraphs[0]
    p.alignment = align
    p.line_spacing = LINE_SPACING[role]
    p.space_after = Pt(SPACE_AFTER.get(role, 0))
    r = p.add_run()
    r.text = text
    r.font.name = deck.theme.font
    r.font.size = Pt(spec["pt"])
    r.font.bold = spec["bold"]
    r.font.italic = spec["italic"]
    r.font.color.rgb = color
    return shp


def _text(deck, slide, left, top, width, height, text, role, color=None, align=PP_ALIGN.LEFT,
          anchor=None, line_spacing=None, fill=None):
    """Role-styled text.  Without `fill`: a plain Deck text box.  With `fill`: a rectangle of that color
    carrying the text itself (like the header bar of Deck.content_slide), so qc_deck's per-shape contrast
    check (QC-18) sees the real background instead of the slide color."""
    if fill is None:
        tb = deck.add_textbox(slide, int(left), int(top), int(width), int(height), text, role=role,
                              align=align, line_spacing=line_spacing)
        if color is not None:
            _recolor(tb, color)
        if anchor is not None:
            tb.text_frame.vertical_anchor = anchor
        return tb
    shp = _rect(deck, slide, left, top, width, height, fill, "band-text")
    return _shape_text(deck, shp, text, role, color if color is not None else deck._spec(role)["color"],
                       align=align, anchor=anchor or MSO_ANCHOR.TOP, inset=(0.1, 0.05))


def _candidates(deck):
    """Text colors a theme sanctions (all inside Theme.allowed_hex)."""
    p = deck.theme.palette
    seen, out = set(), []
    for c in (p["body"], p["title_main"], deck.theme.bg, p["table_hdr_text"], p["title_bar_text"],
              p["subtitle"], p["accent"], p["stat"], p["caption"]):
        if str(c) not in seen:
            seen.add(str(c))
            out.append(c)
    return out


def _text_on(deck, fill, pt, bold):
    """Best sanctioned text color on `fill`; None when nothing reaches the required contrast."""
    best = max(_candidates(deck), key=lambda c: contrast_ratio(c, fill))
    return best if contrast_ratio(best, fill) >= required_contrast(pt, bold) else None


def _strong(deck):
    """(fill, text) pair the theme guarantees to be legible for 12 pt bold, hence for everything bigger."""
    p = deck.theme.palette
    return p["table_hdr_bg"], p["table_hdr_text"]


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


def _line_pitch_in(role: str) -> float:
    return ROLES[role]["pt"] * LINE_HEIGHT_FACTOR * LINE_SPACING[role] / 72.0


def _box_in(width_emu) -> float:
    """Inner text width of a default text box (0.1 in inset each side)."""
    return width_emu / EMU - 0.2


def _require_fit(deck, text, role, box_w_emu, box_h_emu, what, max_lines=None):
    n = _lines(deck, text, role, _box_in(box_w_emu))
    need = n * _line_pitch_in(role) + BOX_PAD / EMU
    if (max_lines is not None and n > max_lines) or need > box_h_emu / EMU + 0.01:
        raise StyleError(f"{what}: {n} line(s) of {role} text need {need:.2f} in but the box offers "
                         f"{box_h_emu / EMU:.2f} in (max_lines={max_lines}); shorten the text, the type "
                         f"scale is closed")
    return n


def _bullets_h_in(deck, items, role, box_w_emu) -> float:
    w = _box_in(box_w_emu)
    total = sum(_lines(deck, "• " + t, role, w) * _line_pitch_in(role) for t in items)
    return total + SPACE_AFTER[role] / 72.0 * max(0, len(items) - 1) + BOX_PAD / EMU


def _need_text(value, what):
    if not isinstance(value, str) or not value.strip():
        raise StyleError(f"{what} must be a non-empty string")
    return value.strip()


def _footer(deck, slide, on_fill=None):
    """Page number (and footer_right).  On the default background this is Deck._footer; on another fill
    (tinted canvas) the same two boxes are drawn as filled shapes in a color legible on that fill."""
    num = deck._next_num()
    if on_fill is None:
        deck._footer(slide, num)
        return
    col = _text_on(deck, on_fill, 9, False)
    if col is None:
        raise StyleError("no sanctioned footer color reaches 4.5:1 on the canvas fill")
    from deck_builder import FOOTER_TOP
    _text(deck, slide, MARGIN, FOOTER_TOP, _in(1.0), _in(0.3), str(num), "footer", col, fill=on_fill)
    if deck.footer_right:
        _text(deck, slide, SLIDE_W - _in(5.0), FOOTER_TOP, _in(4.7), _in(0.3), deck.footer_right, "footer",
              col, align=PP_ALIGN.RIGHT, fill=on_fill)


def _cover_crop(pic, img_w, img_h, box_w, box_h, focus=0.5):
    """Crop (never stretch) so the visible part of the image has exactly the box aspect ratio."""
    a_img, a_box = img_w / img_h, box_w / box_h
    focus = min(max(focus, 0.0), 1.0)
    if a_img > a_box:                         # too wide -> trim left/right
        extra = 1.0 - a_box / a_img
        pic.crop_left, pic.crop_right = extra * focus, extra * (1 - focus)
    else:                                     # too tall -> trim top/bottom
        extra = 1.0 - a_img / a_box
        pic.crop_top, pic.crop_bottom = extra * focus, extra * (1 - focus)


def _emphasize(shape, phrase, rgb):
    """Color `phrase` inside the single run of a one-paragraph box (copy of the run's font)."""
    p = shape.text_frame.paragraphs[0]
    r0 = p.runs[0]
    text = r0.text
    i = text.find(phrase)
    if i < 0:
        raise StyleError(f"emphasis {phrase!r} is not part of the statement")
    parts = [(text[:i], None), (phrase, rgb), (text[i + len(phrase):], None)]
    base = (r0.font.name, r0.font.size, r0.font.bold, r0.font.italic, r0.font.color.rgb)
    r0.text = parts[0][0]
    for txt, col in parts[1:]:
        r = p.add_run()
        r.text = txt
        r.font.name, r.font.size, r.font.bold, r.font.italic = base[0], base[1], base[2], base[3]
        r.font.color.rgb = col if col is not None else base[4]


def _caption_box(deck, slide, left, top, width, lines):
    """Caption (+ source) lines in the caption role, 1.0 spacing, limited to one column.
    Same look as Deck.caption(): italic caption colour, bold body colour on an 'et al.' line."""
    spec = deck._spec("caption")
    box = slide.shapes.add_textbox(int(left), int(top), int(width), int(deck.theme.caption_h))
    tf = box.text_frame
    tf.word_wrap = True
    disable_autofit(tf)
    from deck_builder import set_line_spacing, SPACE_AFTER as SA
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        set_line_spacing(p, LINE_SPACING["caption"])
        p.space_after = Pt(SA["caption"] if i < len(lines) - 1 else 0)
        r = p.add_run()
        r.text = line
        r.font.name = deck.theme.font
        r.font.size = Pt(spec["pt"])
        r.font.italic = True
        r.font.color.rgb = spec["color"]
        if "et al." in line:
            r.font.bold = True
            r.font.color.rgb = deck.theme.palette["body"]
    return box


# ----------------------------------------------------------------------------------------------
# 1. slate_header (G2)
# ----------------------------------------------------------------------------------------------
def slate_frame(deck, title: str, section: str, progress):
    """The G2 frame itself: progress line, slate bar with title (left) and section label (right).
    Returns the slide; content may be placed from SLATE_BODY_TOP down to Y_FLOOR.  Public so that other
    layouts can sit inside the same frame.  Does NOT draw the footer (the caller does, once)."""
    title = _need_text(title, "title")
    section = _need_text(section, "section")
    try:
        i, n = progress
        i, n = int(i), int(n)
    except (TypeError, ValueError):
        raise StyleError("progress must be a (i, n) pair of integers") from None
    if not (n >= 1 and 1 <= i <= n):
        raise StyleError(f"progress=(i, n) needs 1 <= i <= n, got ({i}, {n})")
    slide = deck.new_slide()
    pal = deck.theme.palette
    strong, on_strong = _strong(deck)
    track_h, bar_h = _in(0.08), _in(0.70)
    _rect(deck, slide, 0, 0, SLIDE_W, track_h, pal["highlight_bg"], "deco:progress-track")
    _rect(deck, slide, 0, 0, int(SLIDE_W * i / n), track_h, pal["accent"], "deco:progress-fill")
    _rect(deck, slide, 0, track_h, SLIDE_W, bar_h, strong, "deco:slate-bar")
    title_w = _in(8.9)
    _require_fit(deck, title, "subtitle", title_w, bar_h, "slate_header title", max_lines=1)
    _text(deck, slide, _in(0.5), track_h, title_w, bar_h, title, "subtitle", on_strong,
          anchor=MSO_ANCHOR.MIDDLE, fill=strong)
    label = f"{section}  ·  {i} / {n}"
    label_w = _in(3.2)
    _require_fit(deck, label, "table_header", label_w, bar_h, "slate_header section label", max_lines=1)
    _text(deck, slide, SLIDE_W - label_w - _in(0.3), track_h, label_w, bar_h, label, "table_header",
          on_strong, align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE, fill=strong)
    return slide


@register("slate_header", kind="content",
          summary="Slim slate header bar with title left, section label + i/n right, a thin top progress line; "
                  "body = up to 5 bullets or one captioned figure",
          source="G2 Metropolis slate header bar (matze/mtheme; slate bar + progress hairline + section tag)")
def slate_header(deck, title, section, progress, bullets=None, fig_path=None, caption=None, source=None):
    """content: title (1 line), section (label), progress=(i, n); body is EITHER bullets (list[str], 1-5,
    role body) OR a figure (fig_path + caption, optional source line).  Raises StyleError otherwise."""
    if (bullets is None) == (fig_path is None):
        raise StyleError("slate_header takes exactly one body: bullets=[...] or fig_path=...")
    if bullets is not None:
        if not isinstance(bullets, (list, tuple)) or not 1 <= len(bullets) <= 5:
            raise StyleError("slate_header bullets: 1-5 items required (empty list rejected)")
        bullets = [_need_text(b, "bullet") for b in bullets]
    else:
        caption = _need_text(caption, "figure caption")
    slide = slate_frame(deck, title, section, progress)
    top = int(SLATE_BODY_TOP)
    if bullets is not None:
        left, width = _in(0.8), _in(11.7)
        height = Y_FLOOR - top
        need = _bullets_h_in(deck, bullets, "body", width)
        if need > height / EMU:
            raise StyleError(f"slate_header bullets need {need:.2f} in but only {height / EMU:.2f} in "
                             f"are free; cut bullets or words (type scale is closed)")
        tb = deck.bullets(slide, bullets, role="body", left=left, top=top, width=width, height=height)
        tb.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
    else:
        lines = [caption] + ([source.strip()] if source and source.strip() else [])
        n_lines = sum(_lines(deck, ln, "caption", (SLIDE_W - 2 * MARGIN) / EMU - 0.2) for ln in lines)
        if n_lines > (3 if deck.theme.caption_h > _in(0.5) else 2):
            raise StyleError("slate_header caption + source exceed the caption box; shorten them")
        anchor = deck.add_figure(slide, fig_path, top=top)
        _caption_box(deck, slide, MARGIN, anchor[1] + anchor[3] + CAPTION_GAP, SLIDE_W - 2 * MARGIN, lines)
    _footer(deck, slide)
    return slide


# ----------------------------------------------------------------------------------------------
# 2. block_boxes (G5)
# ----------------------------------------------------------------------------------------------
def _hue(rgb):
    r, g, b = rgb[0], rgb[1], rgb[2]
    if r - max(g, b) > 50:
        return "red"
    if g - max(r, b) > 25:
        return "green"
    return "other"


def _kind_fill(deck, kind: str):
    """Strip fill for a block kind, drawn from palette + sanctioned extras; always legible with the
    returned text color (>= 4.5:1, the strip carries a 12 pt bold tag)."""
    th, pal = deck.theme, deck.theme.palette
    pool = [pal["table_hdr_bg"], pal["subtitle"], pal["title_main"], pal["body"], pal["accent"]]
    if th.header_bg is not None:
        pool.append(th.header_bg)
    pool += [c for c in (deck.theme.palette.values())]
    from deck_builder import _rgb
    pool += [_rgb(h) for h in sorted(th.extra_hex)]
    pref = {
        "definition": [pal["table_hdr_bg"]],
        "result": [c for c in pool if _hue(c) == "green"] + [pal["subtitle"]],
        "alert": [c for c in pool if _hue(c) == "red"] + [pal["accent"]],
        "example": [pal["body"]],
        "question": [pal["subtitle"], pal["accent"]],
    }[kind]
    for fill in pref + [pal["table_hdr_bg"]]:
        text = _text_on(deck, fill, 12, True)
        if text is not None and str(fill) != str(deck.theme.bg):
            return fill, text
    raise StyleError(f"theme {th.name}: no legible strip colour for block kind {kind!r}")


@register("block_boxes", kind="content",
          summary="2-4 titled blocks (definition/result/alert/example/question), each a colored title strip "
                  "over a tinted panel, in a 1x or 2x grid under a thin nav strip",
          source="G5 Frankfurt/Beamer block box (sli.dev Frankfurt: navigation strip + titled block)")
def block_boxes(deck, title, blocks, grid=None, sections=None, current=0):
    """blocks = [dict(kind=<definition|result|alert|example|question>, title=str, text=str | items=[str])].
    grid '1x' (stacked) or '2x' (two columns; odd last block spans the row); default 2x for 4 blocks else 1x.
    sections = optional list of up to 6 nav-strip labels, current = index to highlight.
    Body type is body (16 pt) when every block fits at it, else sidebar_bullet (14 pt), else StyleError."""
    title = _need_text(title, "title")
    if not isinstance(blocks, (list, tuple)) or not 2 <= len(blocks) <= 4:
        raise StyleError("block_boxes needs 2-4 blocks")
    for b in blocks:
        if b.get("kind") not in BLOCK_KINDS:
            raise StyleError(f"block kind must be one of {BLOCK_KINDS}, got {b.get('kind')!r}")
        _need_text(b.get("title"), "block title")
        has_t, has_i = b.get("text") is not None, b.get("items") is not None
        if has_t == has_i:
            raise StyleError("each block needs exactly one of text= or items=")
        if has_t:
            _need_text(b["text"], "block text")
        elif not isinstance(b["items"], (list, tuple)) or not 1 <= len(b["items"]) <= 4:
            raise StyleError("block items: 1-4 entries required (empty list rejected)")
        if has_i and not deck.theme.allow_bullets:
            raise StyleError(f"theme {deck.theme.name!r} forbids bullet lists; use text= blocks")
    n = len(blocks)
    grid = grid or ("2x" if n == 4 else "1x")
    if grid not in ("1x", "2x"):
        raise StyleError("grid must be '1x' or '2x'")
    rows = [[k] for k in range(n)] if grid == "1x" else [list(range(k, min(k + 2, n))) for k in range(0, n, 2)]
    if sections is not None:
        if not isinstance(sections, (list, tuple)) or not 1 <= len(sections) <= 6:
            raise StyleError("sections: 1-6 labels")
        if not 0 <= current < len(sections):
            raise StyleError("current must index sections")

    th, pal = deck.theme, deck.theme.palette
    strong, on_strong = _strong(deck)
    x0, total_w, gap = _in(0.5), _in(12.333), _in(0.28)
    area_top, area_bot = _in(1.45), int(Y_FLOOR) - _in(0.1)
    strip_h, pad_v = _in(0.55), _in(0.12)
    tag_w = _in(1.7)

    def block_w(row):
        return total_w if len(row) == 1 else int((total_w - gap) / 2)

    chosen, needs = None, None
    for role in ("body", "sidebar_bullet"):
        row_need, ok = [], True
        for row in rows:
            w_panel = block_w(row)
            inner = w_panel - _in(0.3)
            best = 0.0
            for k in row:
                b = blocks[k]
                t_h = (_bullets_h_in(deck, b["items"], role, inner) if b.get("items") is not None
                       else _lines(deck, b["text"], role, _box_in(inner)) * _line_pitch_in(role) + BOX_PAD / EMU)
                best = max(best, strip_h / EMU + t_h + 2 * pad_v / EMU)
            row_need.append(best)
        if sum(row_need) + (len(rows) - 1) * gap / EMU <= (area_bot - area_top) / EMU:
            chosen, needs = role, row_need
            break
    if chosen is None:
        raise StyleError("block_boxes: the blocks do not fit at 14 pt body size; cut words or blocks "
                         "(the type scale is closed)")

    slide = deck.new_slide()
    # navigation strip (Frankfurt): thin full-width band, optional section labels, active one inverted
    nav_h = _in(0.36) if sections else _in(0.22)
    _rect(deck, slide, 0, 0, SLIDE_W, nav_h, strong, "deco:nav-strip")
    if sections:
        slot = (SLIDE_W - 2 * _in(0.5)) // len(sections)
        for k, lab in enumerate(sections):
            lab = _need_text(lab, "section label")
            sx = _in(0.5) + k * slot
            _require_fit(deck, lab, "footer", slot, nav_h, "nav label", max_lines=1)
            if k == current:     # active label = an inverted pill (the text box itself carries the fill)
                col = _text_on(deck, th.bg, 9, False)
                _text(deck, slide, sx + _in(0.04), _in(0.04), slot - _in(0.08), nav_h - _in(0.08), lab,
                      "footer", col, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, fill=th.bg)
            else:
                _text(deck, slide, sx, 0, slot, nav_h, lab, "footer", on_strong, align=PP_ALIGN.CENTER,
                      anchor=MSO_ANCHOR.MIDDLE, fill=strong)
    t_top = nav_h + _in(0.12)
    t_w = SLIDE_W - 2 * _in(0.5)
    _require_fit(deck, title, "title_bar", t_w, _in(0.8), "block_boxes title", max_lines=1)
    _text(deck, slide, _in(0.5), t_top, t_w, _in(0.8), title, "title_bar", pal["title_main"],
          anchor=MSO_ANCHOR.MIDDLE)

    extra_each = max(0, (area_bot - area_top) - int(sum(needs) * EMU) - (len(rows) - 1) * gap) // len(rows)
    y = area_top
    for row, need in zip(rows, needs):
        h = int(need * EMU) + min(extra_each, _in(0.9))
        w_panel = block_w(row)
        for c, k in enumerate(row):
            b = blocks[k]
            x = x0 + c * (w_panel + gap)
            fill, ink = _kind_fill(deck, b["kind"])
            panel_fill = pal["warning_bg"] if b["kind"] == "alert" else pal["highlight_bg"]
            _rect(deck, slide, x, y, w_panel, h, panel_fill, "deco:block-panel")
            _rect(deck, slide, x, y, w_panel, strip_h, fill, "deco:block-strip")
            ttl_w = w_panel - tag_w - _in(0.2)
            _require_fit(deck, b["title"], "subtitle", ttl_w, strip_h, f"block {k + 1} title", max_lines=1)
            _text(deck, slide, x + _in(0.1), y, ttl_w, strip_h, b["title"], "subtitle", ink,
                  anchor=MSO_ANCHOR.MIDDLE, fill=fill)
            _text(deck, slide, x + w_panel - tag_w - _in(0.1), y, tag_w, strip_h, b["kind"].upper(),
                  "table_header", ink, align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE, fill=fill)
            body_col = _text_on(deck, panel_fill, ROLES[chosen]["pt"], False)
            if body_col is None:
                raise StyleError("no sanctioned text color is legible on the block panel")
            bx, by = x + _in(0.15), y + strip_h + pad_v
            bw, bh = w_panel - _in(0.3), h - strip_h - 2 * pad_v
            if b.get("items") is not None:
                tb = deck.bullets(slide, list(b["items"]), role=chosen, left=bx, top=by, width=bw, height=bh)
            else:
                tb = deck.add_textbox(slide, bx, by, bw, bh, b["text"], role=chosen)
            _recolor(tb, body_col)
            tb.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
        y += h + gap
    _footer(deck, slide)
    return slide


# ----------------------------------------------------------------------------------------------
# 3. statement_slide (G13)
# ----------------------------------------------------------------------------------------------
@register("statement_slide", kind="divider",
          summary="One sentence, as large as the type scale allows (54 pt, else 30 pt), centered, one word "
                  "may take the accent; optional attribution line",
          extra_sizes=(STAT_BIG_PT,),
          source="G13 single-statement slide (sli.dev Takahashi: one huge line, one accent)")
def statement_slide(deck, statement, emphasis=None, attribution=None):
    """statement: one sentence (<= 30 words).  emphasis: substring drawn in the accent color.
    attribution: optional source / speaker line below the statement (fig_subtitle role)."""
    statement = _need_text(statement, "statement")
    if len(statement.split()) > 30:
        raise StyleError("statement_slide holds one sentence of at most 30 words")
    if emphasis is not None and emphasis not in statement:
        raise StyleError(f"emphasis {emphasis!r} is not part of the statement")
    pal = deck.theme.palette
    box_w, box_h = _in(11.6), _in(4.1)
    role = None
    for cand, max_lines in (("stat_big", 4), ("title_main", 6)):
        if _lines(deck, statement, cand, _box_in(box_w)) <= max_lines and \
                _lines(deck, statement, cand, _box_in(box_w)) * _line_pitch_in(cand) + BOX_PAD / EMU \
                <= box_h / EMU:
            role = cand
            break
    if role is None:
        raise StyleError("statement is too long even at 30 pt; shorten it")
    slide = deck.new_slide()
    tb = _text(deck, slide, (SLIDE_W - box_w) // 2, _in(1.0), box_w, box_h, statement, role,
               pal["title_main"], align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    if emphasis:
        acc = pal["accent"] if contrast_ratio(pal["accent"], deck.theme.bg) >= 3.0 else pal["subtitle"]
        _emphasize(tb, emphasis, acc)
    _rect(deck, slide, (SLIDE_W - _in(1.6)) // 2, _in(5.3), _in(1.6), Pt(4), pal["accent"], "deco:statement-rule")
    if attribution and attribution.strip():
        a_w = _in(10.0)
        _require_fit(deck, attribution.strip(), "fig_subtitle", a_w, _in(0.5), "attribution", max_lines=1)
        _text(deck, slide, (SLIDE_W - a_w) // 2, _in(5.5), a_w, _in(0.5), attribution.strip(), "fig_subtitle",
              align=PP_ALIGN.CENTER)
    _footer(deck, slide)
    return slide


# ----------------------------------------------------------------------------------------------
# title helpers shared by 4 and 5
# ----------------------------------------------------------------------------------------------
def _meta_lines(presenter, date, venue):
    presenter = _need_text(presenter, "presenter")
    date = _need_text(date, "date")
    second = f"{date}  |  {venue.strip()}" if venue and venue.strip() else date
    return [f"Presenter: {presenter}", second]


# ----------------------------------------------------------------------------------------------
# 4. corner_wedge_title (G15)
# ----------------------------------------------------------------------------------------------
@register("corner_wedge_title", kind="title",
          summary="Title slide with a diagonal corner wedge (top-left, accent stripe along the diagonal) and "
                  "a small mirrored wedge bottom-right as neutral geometry; no logo",
          source="G15 corner-wedge crest (Korea Univ / KAIST institutional templates, geometry only)")
def corner_wedge_title(deck, title, presenter, date, venue=None, subtitle=None):
    """title (<= 2 lines at 30 pt), optional subtitle (18 pt, <= 2 lines), presenter, date, optional venue."""
    title = _need_text(title, "title")
    meta = _meta_lines(presenter, date, venue)
    pal = deck.theme.palette
    strong, _on = _strong(deck)
    t_w, t_h = _in(10.6), _in(1.3)
    _require_fit(deck, title, "title_main", t_w, t_h, "corner_wedge_title title", max_lines=2)
    slide = deck.new_slide()
    # wedges first (z-order bottom): stripe = slightly larger accent triangle under the main wedge
    W, H, off = 4.6, 2.6, 0.30
    _shape(deck, slide, MSO_SHAPE.RIGHT_TRIANGLE, 0, 0, _in(W + off * 1.7), _in(H + off), pal["accent"],
           "deco:wedge-stripe", flip_v=True)
    _shape(deck, slide, MSO_SHAPE.RIGHT_TRIANGLE, 0, 0, _in(W), _in(H), strong, "deco:wedge", flip_v=True)
    bw, bh = 2.8, 1.35
    _shape(deck, slide, MSO_SHAPE.RIGHT_TRIANGLE, SLIDE_W - _in(bw + off * 1.7), SLIDE_H - _in(bh + off),
           _in(bw + off * 1.7), _in(bh + off), pal["accent"], "deco:wedge-stripe-br", flip_h=True)
    _shape(deck, slide, MSO_SHAPE.RIGHT_TRIANGLE, SLIDE_W - _in(bw), SLIDE_H - _in(bh), _in(bw), _in(bh),
           strong, "deco:wedge-br", flip_h=True)
    x = (SLIDE_W - t_w) // 2
    _text(deck, slide, x, _in(2.85), t_w, t_h, title, "title_main", pal["title_main"],
          align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.BOTTOM)
    y = 4.25
    if subtitle and subtitle.strip():
        _require_fit(deck, subtitle.strip(), "subtitle", t_w, _in(0.95), "subtitle", max_lines=2)
        _text(deck, slide, x, _in(y), t_w, _in(0.95), subtitle.strip(), "subtitle", align=PP_ALIGN.CENTER)
        y += 1.0
    _rect(deck, slide, (SLIDE_W - _in(1.8)) // 2, _in(y + 0.05), _in(1.8), Pt(3), pal["accent"], "deco:title-rule")
    for k, ln in enumerate(meta):
        _text(deck, slide, x, _in(y + 0.2 + 0.4 * k), t_w, _in(0.45), ln, "presenter", align=PP_ALIGN.CENTER)
    deck._next_num()
    return slide


# ----------------------------------------------------------------------------------------------
# 5. band_title (G3 / G14)
# ----------------------------------------------------------------------------------------------
@register("band_title", kind="title",
          summary="Title slide: saturated color field over a hairline-engraved band; an optional hero figure "
                  "is cover-cropped (never stretched) into a strip straddling the field edge",
          source="G3 mid-century color field over engraved band + G14 photo band over color block")
def band_title(deck, title, presenter, date, venue=None, subtitle=None, hero_fig=None, hero_focus=0.5):
    """title (<= 2 lines), optional subtitle, presenter, date, optional venue; hero_fig = image path cropped
    to a 12.7 x 1.9 in strip by picture-crop geometry (hero_focus 0..1 picks which part of the image stays)."""
    title = _need_text(title, "title")
    meta = _meta_lines(presenter, date, venue)
    pal = deck.theme.palette
    strong, on_strong = _strong(deck)
    t_w, t_h = _in(11.4), _in(1.3)
    _require_fit(deck, title, "title_main", t_w, t_h, "band_title title", max_lines=2)
    sub = subtitle.strip() if subtitle and subtitle.strip() else None
    if sub:
        _require_fit(deck, sub, "subtitle", t_w, _in(0.95), "subtitle", max_lines=2)
    hero = hero_fig is not None
    field_h = _in(5.0) if hero else _in(5.5)
    slide = deck.new_slide()
    _rect(deck, slide, 0, 0, SLIDE_W, field_h, strong, "deco:colour-field")
    # engraved band: hairlines under the field (G3)
    y0 = 6.35 if hero else 6.1
    for k in range(7):
        _rect(deck, slide, 0, _in(y0 + 0.1 * k), SLIDE_W, Pt(0.75), pal["subtitle"], "deco:band-hairline")
    x = _in(0.9)
    cy = 0.5 if hero else 1.45
    _text(deck, slide, x, _in(cy), t_w, _in(0.5), meta[1], "presenter", on_strong, fill=strong)
    _text(deck, slide, x, _in(cy + 0.5), t_w, t_h, title, "title_main", on_strong, anchor=MSO_ANCHOR.TOP,
          fill=strong)
    yy = cy + 0.5 + 1.35
    if sub:
        _text(deck, slide, x, _in(yy), t_w, _in(0.95), sub, "subtitle", on_strong, fill=strong)
        yy += 0.95
    _text(deck, slide, x, _in(yy + 0.05), t_w, _in(0.5), meta[0], "presenter", on_strong, fill=strong)
    if hero:
        from PIL import Image
        with Image.open(hero_fig) as im:
            iw, ih = im.size
        sx, sy, sw, sh = MARGIN, _in(4.15), SLIDE_W - 2 * MARGIN, _in(1.9)
        pic = slide.shapes.add_picture(str(hero_fig), sx, sy, sw, sh)
        _cover_crop(pic, iw, ih, sw, sh, hero_focus)
        pic.line.color.rgb = deck.theme.bg
        pic.line.width = Pt(3)
        pic.name = f"hero:{Path(str(hero_fig)).stem}"
    deck._next_num()
    return slide


# ----------------------------------------------------------------------------------------------
# 6. split_panel_figure (G6 / G17)
# ----------------------------------------------------------------------------------------------
@register("split_panel_figure", kind="figure",
          summary="Rounded card on a tinted canvas: captioned figure (>= 3 in) on one side, 2-3 numbered "
                  "takeaways on the other; caption and source line are mandatory",
          source="G6 split panel hero + G17 rounded card on tinted canvas (Fibrinosa thesis defense)")
def split_panel_figure(deck, title, fig_path, caption, source, takeaways, fig_side="left"):
    """title (1 line), fig_path, caption, source (mandatory), takeaways (2-3 short sentences, sidebar_bullet),
    fig_side 'left' | 'right'.  The figure box is >= 3 in tall; StyleError otherwise."""
    if not deck.theme.allow_bullets:
        raise StyleError(f"theme {deck.theme.name!r} forbids key points (assertion-evidence); "
                         f"use slate_header with a figure instead")
    title = _need_text(title, "title")
    caption = _need_text(caption, "caption")
    source = _need_text(source, "source line")
    if fig_side not in ("left", "right"):
        raise StyleError("fig_side must be 'left' or 'right'")
    if not isinstance(takeaways, (list, tuple)) or not 2 <= len(takeaways) <= 3:
        raise StyleError("split_panel_figure takes 2-3 takeaways")
    takeaways = [_need_text(t, "takeaway") for t in takeaways]
    th, pal = deck.theme, deck.theme.palette
    strong, on_strong = _strong(deck)

    card_l, card_t, card_w, card_h = _in(0.4), _in(0.4), _in(12.533), _in(6.55)
    col_gap, pad = _in(0.4), _in(0.3)
    fig_w = _in(7.3)
    right_w = card_w - 2 * pad - fig_w - col_gap
    fig_x = card_l + pad if fig_side == "left" else card_l + pad + right_w + col_gap
    txt_x = card_l + pad + fig_w + col_gap if fig_side == "left" else card_l + pad

    slide = deck.new_slide()
    _rect(deck, slide, 0, 0, SLIDE_W, SLIDE_H, pal["highlight_bg"], "deco:canvas")
    _shape(deck, slide, MSO_SHAPE.ROUNDED_RECTANGLE, card_l, card_t, card_w, card_h, th.bg, "deco:card", adj=0.035)
    t_w = card_w - 2 * pad
    _require_fit(deck, title, "title_bar", t_w, _in(0.75), "split_panel_figure title", max_lines=1)
    _text(deck, slide, card_l + pad, _in(0.55), t_w, _in(0.75), title, "title_bar", pal["title_main"],
          anchor=MSO_ANCHOR.MIDDLE)
    _rect(deck, slide, card_l + pad + _in(0.1), _in(1.32), _in(1.4), Pt(3), pal["accent"], "deco:title-rule")

    # figure + caption + source
    cap_lines = [caption, source]
    n_cap = sum(_lines(deck, ln, "caption", fig_w / EMU - 0.2) for ln in cap_lines)
    if n_cap > (3 if th.caption_h > _in(0.5) else 2):
        raise StyleError("caption + source exceed the caption box of one column; shorten them")
    top = _in(1.55)
    bottom_limit = card_t + card_h - _in(0.2)
    pad_p = int(_in(0.07)) if th.plate is not None else 0
    max_h = bottom_limit - int(th.caption_h) - CAPTION_GAP - top - 2 * pad_p
    if max_h < MIN_FIG_H:
        raise StyleError(f"figure area is only {max_h / EMU:.2f} in tall (< 3.0 in)")
    anchor = deck.add_figure(slide, fig_path, top=top, left=fig_x + pad_p, max_width=fig_w - 2 * pad_p,
                             max_height=max_h)
    _caption_box(deck, slide, fig_x, anchor[1] + anchor[3] + CAPTION_GAP, fig_w, cap_lines)

    # divider + takeaways
    div_x = (fig_x + fig_w + col_gap // 2) if fig_side == "left" else (txt_x + right_w + col_gap // 2)
    _rect(deck, slide, div_x, top, Pt(1), _in(4.6), pal["highlight_bg"], "deco:divider")
    circ = _in(0.5)
    t_text_w = right_w - circ - _in(0.15)
    y = top + _in(0.1)
    gap_rows = _in(0.3)
    total = 0.0
    heights = []
    for t in takeaways:
        h = _lines(deck, t, "sidebar_bullet", _box_in(t_text_w)) * _line_pitch_in("sidebar_bullet") + BOX_PAD / EMU
        heights.append(h)
        total += h
    total += (len(takeaways) - 1) * gap_rows / EMU
    if total > (bottom_limit - top) / EMU - 0.1:
        raise StyleError(f"takeaways need {total:.2f} in but the column offers "
                         f"{(bottom_limit - top) / EMU - 0.1:.2f} in; shorten them")
    spare = (anchor[3] / EMU - total) / max(1, len(takeaways) - 1)   # spread rows over the figure height
    gap_rows = gap_rows + _in(min(max(spare, 0.0), 0.9))
    for k, (t, h) in enumerate(zip(takeaways, heights)):
        hh = _in(h)
        badge = _shape(deck, slide, MSO_SHAPE.OVAL, txt_x, y + (hh - circ) // 2 if hh > circ else y, circ, circ,
                       strong, "badge")
        _shape_text(deck, badge, str(k + 1), "table_header", on_strong)
        tb = deck.add_textbox(slide, txt_x + circ + _in(0.15), y, t_text_w, hh, t, role="sidebar_bullet")
        tb.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
        y += hh + gap_rows
    _footer(deck, slide, on_fill=pal["highlight_bg"])
    return slide
