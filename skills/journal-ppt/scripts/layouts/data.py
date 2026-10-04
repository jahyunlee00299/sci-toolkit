"""Data-family layouts for journal-ppt: bento KPI board, giant numeral, highlight chips,
comparison cards and a metric strip.

Sources (layout grammar notes):
  bento_kpi        G8  Bento tile board (Rostu Design / Ashan, dribbble 02 and 10)
  giant_number     G9  Swiss giant numeral + two-tone headline (One Week Wonders, dribbble 10)
  highlight_chips  G12 Dark "highlight chip" slide (sli.dev gallery)
  comparison_cards     marketing-deck pricing-style comparison cards (ppt_marketing_styles s.4, item 8)
  metric_strip         thin KPI strip above a figure (Beautiful.ai "Data & Chart" family)

Rules kept by every layout here
  * colors come only from the active theme (palette / bg / header_bg); each text color is CHOSEN from
    that set by measured WCAG contrast against the fill it sits on, so all 27 themes work;
  * text roles come from deck_builder.ROLES; the only extra size is stat_big (54 pt), declared via
    extra_sizes where used. stat_number (20 pt) is NOT used: it is not in the base size list;
  * text is measured with the same Arial metrics qc_layout uses; content that cannot fit raises
    StyleError at build time instead of overflowing;
  * every autoshape gets word_wrap + disable_autofit and is named 'deco:<what>'; pictures are placed
    with aspect ratio kept and refused when their longer side would be below 3 in.
"""
from __future__ import annotations

import re
from pathlib import Path

from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

from deck_builder import (MIN_FIG_H, ROLES, STAT_BIG_PT, StyleError, Y_FLOOR,  # noqa: E402
                          contrast_ratio, disable_autofit, required_contrast, PILImage)
from qc_layout import text_width_pt  # same Arial metrics as the layout QC  # noqa: E402

from . import register

# --------------------------------------------------------------------------- geometry (inches)
SLIDE_W_IN = 13.333
X0, X1 = 0.3, 13.033           # side margins
CONTENT_TOP = 1.45             # first row under any header style
CONTENT_BOTTOM = 6.95          # Y floor is 7.0
MIN_FIG_IN = MIN_FIG_H / 914400.0
INK_PAD_X, INK_PAD_Y = 0.1, 0.05   # python-pptx default text insets
LINE_H = 1.2                   # Arial single line pitch / pt, same constant as qc_layout
SLACK = 0.03


# --------------------------------------------------------------------------- color helpers
def _hex(c: RGBColor) -> str:
    return str(c)


class _Ink:
    """Chooses legible, on-palette colors for the active theme."""

    def __init__(self, theme):
        self.t = theme
        self.p = theme.palette
        seen, cands = set(), []
        for c in list(self.p.values()) + [theme.bg] + ([theme.header_bg] if theme.header_bg is not None else []):
            if _hex(c) not in seen:
                seen.add(_hex(c))
                cands.append(c)
        self.cands = cands

    @staticmethod
    def ratio(a, b) -> float:
        return contrast_ratio(a, b)

    def text_on(self, fill, pt: float, bold: bool, prefer=()):
        """First preferred color that reaches the required contrast on `fill`, else the best candidate;
        None when nothing in the palette is legible."""
        need = required_contrast(pt, bold)
        for c in prefer:
            if c is not None and self.ratio(c, fill) >= need:
                return c
        best = max(self.cands, key=lambda c: self.ratio(c, fill))
        return best if self.ratio(best, fill) >= need else None

    def pick_fill(self, prefs, pt: float, bold: bool, vs=None, min_vs: float = 1.0, text_prefs=()):
        """(fill, text) for the first fill in `prefs` that is legible with some text color and (when
        `vs` is given) differs from it by at least `min_vs` contrast. None if no fill qualifies."""
        for f in prefs:
            if f is None:
                continue
            if vs is not None and self.ratio(f, vs) < min_vs:
                continue
            tx = self.text_on(f, pt, bold, text_prefs)
            if tx is not None:
                return f, tx
        return None

    # -- named styles --------------------------------------------------------------------------
    def style(self, kind: str) -> dict:
        """fill / line / main text color / value-color preferences for a tile style."""
        p, bg = self.p, self.t.bg
        if kind == "accent":
            f = p["accent"]
            tx = self.text_on(f, 12, True)
            if tx is not None:
                return dict(fill=f, line=None, main=tx, vprefs=(tx,))
            kind = "strong"
        if kind == "strong":
            f = p["table_hdr_bg"]
            tx = self.text_on(f, 12, True, (p["table_hdr_text"],))
            if tx is None:
                raise StyleError(f"theme {self.t.name}: no legible text colour on table_hdr_bg")
            return dict(fill=f, line=None, main=tx, vprefs=(p["accent"], p["stat"], tx))
        if kind in ("soft", "soft2"):
            f = p["highlight_bg"] if kind == "soft" else p["zebra"]
            if self.ratio(f, bg) < 1.03:                 # invisible against the slide: fall back to outline
                return self.style("outline")
            tx = self.text_on(f, 12, False, (p["body"],))
            if tx is None:
                return self.style("outline")
            line = p["caption"] if self.ratio(f, bg) < 1.2 else None
            return dict(fill=f, line=line, main=tx, vprefs=(p["stat"], p["accent"], p["subtitle"], tx))
        # outline
        tx = self.text_on(bg, 12, False, (p["body"],))
        if tx is None:
            raise StyleError(f"theme {self.t.name}: no legible text colour on the slide background")
        return dict(fill=bg, line=p["caption"], main=tx, vprefs=(p["stat"], p["accent"], p["subtitle"], tx))

    def band(self, bg_need: float = 2.0):
        """A fill that clearly contrasts with the slide background (dark band on light themes, a
        light/accent band on dark themes) plus a legible text color for body and chip text."""
        p = self.p
        prefs = [p["table_hdr_bg"], self.t.header_bg, p["subtitle"], p["accent"], p["stat"], p["title_main"], p["body"]]
        for f in prefs:
            if f is None or self.ratio(f, self.t.bg) < bg_need:
                continue
            tx = self.text_on(f, 16, False)
            if tx is None:
                continue
            chip = self.pick_fill([p["accent"], p["stat"], self.t.bg, p["highlight_bg"], p["table_hdr_bg"],
                                   p["subtitle"], p["body"]], 18, True, vs=f, min_vs=1.8)
            if chip is not None:
                return dict(fill=f, text=tx, chip_fill=chip[0], chip_text=chip[1])
        raise StyleError(f"theme {self.t.name}: no contrasting band fill with legible text")


# --------------------------------------------------------------------------- text measuring
def _wrap_lines(segs, width_in: float) -> int:
    """Greedy word wrap of [(text, pt, bold)] into width_in inches; returns the line count.
    Raises StyleError for a single token wider than the line."""
    avail = width_in * 72.0
    lines, cw, pend = 1, 0.0, 0.0
    for text, pt, bold in segs:
        for piece in re.split(r"(\s+)", text):
            if piece == "":
                continue
            w = text_width_pt(piece, "arial", bold, pt)
            if piece.isspace():
                pend += w
                continue
            if w > avail:
                raise StyleError(f"token {piece[:24]!r} is wider than its {width_in:.2f} in box")
            if cw > 0 and cw + pend + w > avail:
                lines += 1
                cw = w
            else:
                cw += (pend if cw > 0 else 0.0) + w
            pend = 0.0
    return lines


def _roles_ls(role: str) -> float:
    from deck_builder import LINE_SPACING
    return LINE_SPACING[role]


def _measure(deck, text: str, role: str, width_in: float, extra=()):
    """(lines, ink_height_in) of `text` in `role` (+ extra runs [(text, role)]) at ink width width_in."""
    spec = ROLES[role]
    segs = [(text, spec["pt"], spec["bold"])]
    for t2, r2 in extra:
        segs.append((t2, ROLES[r2]["pt"], ROLES[r2]["bold"]))
    n = _wrap_lines(segs, width_in)
    if len(segs) == 1 and not spec["bold"]:
        n = max(n, deck.fit_check(text, role, width_in)["lines"])      # cross-check with Deck.fit_check
    max_pt = max(s[1] for s in segs)
    return n, n * max_pt * LINE_H * _roles_ls(role) / 72.0


def _tb(deck, slide, x, y, w, h, text, role, color, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
        extra=(), name=None, max_lines=None):
    """Textbox whose INK area is (x, y, w, h) in inches; raises StyleError if the text cannot fit.
    extra = [(text, role, color)] further runs on the same paragraph."""
    n, need = _measure(deck, text, role, w, [(t, r) for t, r, _ in extra])
    if max_lines is not None and n > max_lines:
        raise StyleError(f"text needs {n} lines (max {max_lines}) in {w:.2f} in: {text[:40]!r}")
    if need > h + SLACK:
        raise StyleError(f"text needs {need:.2f} in but only {h:.2f} in is available: {text[:40]!r}")
    box = deck.add_textbox(slide, Inches(x - INK_PAD_X), Inches(y - INK_PAD_Y), Inches(w + 2 * INK_PAD_X),
                           Inches(h + 2 * INK_PAD_Y), text, role, align=align)
    para = box.text_frame.paragraphs[0]
    para.runs[0].font.color.rgb = color
    box.text_frame.vertical_anchor = anchor
    for t2, r2, c2 in extra:
        spec = ROLES[r2]
        run = para.add_run()
        run.text = t2
        run.font.name = deck.theme.font
        run.font.size = Pt(spec["pt"])
        run.font.bold = spec["bold"]
        run.font.italic = spec["italic"]
        run.font.color.rgb = c2
    if name:
        box.name = name
    return box


def _text_w(text: str, role: str) -> float:
    spec = ROLES[role]
    return text_width_pt(text, "arial", spec["bold"], spec["pt"]) / 72.0


# --------------------------------------------------------------------------- shapes
def _shape(slide, kind, x, y, w, h, fill, name, radius_in=None, line=None, line_pt=0.75):
    if not name.startswith("deco:"):
        raise ValueError("decorative shapes must be named 'deco:<what>'")
    shp = slide.shapes.add_shape(kind, Inches(x), Inches(y), Inches(w), Inches(h))
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
    if kind == MSO_SHAPE.ROUNDED_RECTANGLE and radius_in is not None:
        shp.adjustments[0] = min(0.5, radius_in / max(min(w, h), 0.01))
    shp.name = name
    return shp


def _rrect(slide, x, y, w, h, fill, name, radius=0.12, line=None):
    return _shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h, fill, name, radius, line)


def _pill(deck, slide, x, y, h, text, role, fill, ink, name, min_w=0.0, align_right=False, fixed_w=None):
    """Pill-shaped chip sized to its text (or exactly fixed_w, in which case the text must fit one
    line); returns (left, width). x is the left edge (right edge if align_right)."""
    w = fixed_w if fixed_w is not None else max(min_w, _text_w(text, role) + 0.4)
    left = x - w if align_right else x
    _shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, left, y, w, h, fill, name, radius_in=h / 2)
    _tb(deck, slide, left + 0.15, y + (h - ROLES[role]["pt"] * LINE_H / 72.0) / 2, w - 0.3,
        ROLES[role]["pt"] * LINE_H / 72.0, text, role, ink, align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE, max_lines=1)
    return left, w


def _picture(slide, path, bx, by, bw, bh, name_prefix="fig"):
    """Place a picture inside the box (inches), aspect ratio kept, centered; its longer side must be
    >= 3 in or StyleError is raised. Returns (left, top, w, h) in inches."""
    if PILImage is None:
        raise RuntimeError("Pillow is required for pictures")
    with PILImage.open(path) as im:
        iw, ih = im.size
    s = min(bw / iw, bh / ih)
    w, h = iw * s, ih * s
    if max(w, h) < MIN_FIG_IN - 1e-6:
        raise StyleError(f"figure {Path(path).name} would be {w:.2f} x {h:.2f} in (< 3 in): give it a bigger "
                         f"tile or fewer tiles")
    left, top = bx + (bw - w) / 2, by + (bh - h) / 2
    pic = slide.shapes.add_picture(str(path), Inches(left), Inches(top), Inches(w), Inches(h))
    pic.name = f"{name_prefix}:{Path(path).stem}"
    return left, top, w, h


def _require_list(name: str, items, lo: int, hi: int):
    if not isinstance(items, (list, tuple)) or not items:
        raise StyleError(f"{name} must be a non-empty list")
    if not lo <= len(items) <= hi:
        raise StyleError(f"{name} takes {lo}-{hi} entries, got {len(items)}")


def _need_str(d: dict, key: str, ctx: str, optional: bool = False) -> str:
    v = d.get(key)
    if v is None or (isinstance(v, str) and not v.strip()):
        if optional:
            return ""
        raise StyleError(f"{ctx}: '{key}' is required")
    return str(v)


def _plain_slide(deck):
    """Header-less slide (title carried by the layout itself) with page number footer."""
    slide = deck.new_slide()
    deck._footer(slide, deck._next_num())
    return slide


# =========================================================================== G8 bento_kpi
_GUT = 0.15
_COL_W = (X1 - X0 - 11 * _GUT) / 12.0
_ROW_H = (CONTENT_BOTTOM - CONTENT_TOP - _GUT) / 2.0
# (col, row, colspan, rowspan) on a 12 x 2 grid; index 0 is the largest slot of every template
_TEMPLATES = {
    3: [(0, 0, 6, 2), (6, 0, 6, 1), (6, 1, 6, 1)],
    4: [(0, 0, 5, 2), (5, 0, 4, 1), (9, 0, 3, 1), (5, 1, 7, 1)],
    5: [(0, 0, 4, 2), (4, 0, 5, 1), (9, 0, 3, 1), (4, 1, 3, 1), (7, 1, 5, 1)],
    6: [(0, 0, 6, 1), (6, 0, 3, 1), (9, 0, 3, 1), (0, 1, 3, 1), (3, 1, 3, 1), (6, 1, 6, 1)],
    7: [(0, 0, 3, 2), (3, 0, 3, 1), (6, 0, 3, 1), (9, 0, 3, 1), (3, 1, 3, 1), (6, 1, 3, 1), (9, 1, 3, 1)],
}
_STYLE_CYCLE = ["soft", "accent", "outline", "soft2", "soft", "accent"]
_VALUE_LADDER = ["stat_big", "title_main", "title_bar", "subtitle"]


def _slot_rect(slot):
    c, r, cs, rs = slot
    x = X0 + c * (_COL_W + _GUT)
    y = CONTENT_TOP + r * (_ROW_H + _GUT)
    return x, y, cs * _COL_W + (cs - 1) * _GUT, rs * _ROW_H + (rs - 1) * _GUT


def _kpi_tile(deck, slide, ink: _Ink, rect, tile: dict, style_name: str, idx: int):
    x, y, w, h = rect
    st = ink.style(style_name)
    _rrect(slide, x, y, w, h, st["fill"], f"deco:tile{idx}", radius=0.14, line=st["line"])
    pad = 0.2
    ix, iw = x + pad, w - 2 * pad
    label = _need_str(tile, "label", f"tile {idx}")
    value = _need_str(tile, "value", f"tile {idx}")
    unit = _need_str(tile, "unit", f"tile {idx}", optional=True)
    delta = _need_str(tile, "delta", f"tile {idx}", optional=True)
    note = _need_str(tile, "note", f"tile {idx}", optional=True)

    lab_n, lab_h = _measure(deck, label, "table_header", iw)
    if lab_n > 2:
        raise StyleError(f"tile {idx}: label needs {lab_n} lines (max 2)")
    top_y = y + pad
    bot_y = y + h - pad
    if note:
        note_n, note_h = _measure(deck, note, "table_cell", iw)
        if note_n > 3:
            raise StyleError(f"tile {idx}: note needs {note_n} lines (max 3)")
        note_top = bot_y - note_h
    else:
        note_h, note_top = 0.0, bot_y
    pill_h = 0.34
    if delta and _text_w(delta, "table_header") + 0.4 > iw:
        raise StyleError(f"tile {idx}: delta {delta!r} is wider than the tile")

    mid_top = top_y + lab_h + 0.1
    mid_bot = note_top - (0.1 if note else 0.0)
    large = w >= 3.8 and h >= 2.5
    ladder = _VALUE_LADDER if large else _VALUE_LADDER[1:]
    chosen = None
    for role in ladder:
        try:
            n, vh = _measure(deck, value, role, iw, [(" " + unit, "subtitle")] if unit else [])
        except StyleError:
            continue
        block = vh + ((0.12 + pill_h) if delta else 0.0)
        if n == 1 and block <= mid_bot - mid_top + SLACK:
            chosen = (role, vh, block)
            break
    if chosen is None:
        raise StyleError(f"tile {idx}: value {value!r} {unit} (+delta) does not fit the tile")
    role, vh, block = chosen

    # colors
    vcol = ink.text_on(st["fill"], ROLES[role]["pt"], True, st["vprefs"])
    _tb(deck, slide, ix, top_y, iw, lab_h, label, "table_header", st["main"], name=f"label{idx}")
    vy = mid_top + (mid_bot - mid_top - block) / 2.0
    extra = [(" " + unit, "subtitle", st["main"])] if unit else []
    _tb(deck, slide, ix, vy, iw, vh, value, role, vcol, extra=extra, name=f"value{idx}", max_lines=1)
    if delta:
        pf = ink.pick_fill([ink.p["accent"], ink.p["stat"], ink.p["subtitle"], ink.t.bg, ink.p["highlight_bg"],
                            ink.p["table_hdr_bg"]], 12, True, vs=st["fill"], min_vs=1.6)
        py = vy + vh + 0.12
        if pf is not None:
            _pill(deck, slide, ix, py, pill_h, delta, "table_header", pf[0], pf[1], f"deco:delta{idx}")
        else:
            _tb(deck, slide, ix, py, iw, pill_h, delta, "table_header", st["main"], anchor=MSO_ANCHOR.MIDDLE,
                max_lines=1)
    if note:
        _tb(deck, slide, ix, note_top, iw, note_h, note, "table_cell", st["main"], name=f"note{idx}")


def _figure_tile(deck, slide, ink: _Ink, rect, path, label: str, note: str, idx: int):
    x, y, w, h = rect
    st = ink.style("outline")
    _rrect(slide, x, y, w, h, st["fill"], f"deco:tile{idx}", radius=0.14, line=st["line"])
    pad = 0.2
    ix, iw = x + pad, w - 2 * pad
    top_y = y + pad
    lab_h = 0.0
    if label:
        lab_n, lab_h = _measure(deck, label, "table_header", iw)
        if lab_n > 2:
            raise StyleError("figure label needs more than 2 lines")
        _tb(deck, slide, ix, top_y, iw, lab_h, label, "table_header", st["main"], name="figlabel")
    note_h = 0.0
    if note:
        n, note_h = _measure(deck, note, "caption", iw)
        if n > 3:
            raise StyleError("figure note needs more than 3 lines")
        _tb(deck, slide, ix, y + h - pad - note_h, iw, note_h, note, "caption", ink.text_on(st["fill"], 9.5, False,
                                                                                         (ink.p["caption"], st["main"])),
            name="fignote")
    by = top_y + lab_h + (0.1 if label else 0.0)
    bh = (y + h - pad - note_h - (0.1 if note else 0.0)) - by
    _picture(slide, path, ix, by, iw, bh)


@register("bento_kpi", kind="data", extra_sizes=(STAT_BIG_PT,),
          summary="Bento tile board: 3-7 KPI tiles of mixed sizes on a 12-column grid, optional figure tile.",
          source="G8 Bento tile board (Rostu Design / Ashan, dribbble 02 and 10)")
def bento_kpi(deck, title, tiles, figure=None, figure_label="", figure_note=""):
    """tiles = [{label, value, unit?, delta?, note?, span?}] (3-7 tiles; 3-4 when a figure tile is added).

    span 1-3 ranks tiles by importance: larger span gets a larger grid slot (ties keep input order; when
    no tile sets span the first one is featured). The largest slot is drawn in the strong style and uses
    stat_big (54 pt) for its value; smaller slots fall back to title_main / title_bar / subtitle.
    figure = path to an image shown in the biggest slot (aspect kept, longer side must stay >= 3 in);
    figure_label / figure_note = tile heading and caption."""
    _require_list("tiles", tiles, 3, 4 if figure else 7)
    n_total = len(tiles) + (1 if figure else 0)
    slots = sorted(_TEMPLATES[n_total], key=lambda s: -(s[2] * s[3]))   # stable: biggest first
    ink = _Ink(deck.theme)
    slide = deck.content_slide(title)
    spans = [t.get("span") for t in tiles]
    if all(s is None for s in spans):
        spans = [3] + [1] * (len(tiles) - 1)
    spans = [1 if s is None else int(s) for s in spans]
    order = sorted(range(len(tiles)), key=lambda i: -spans[i])           # stable
    slot_iter = iter(slots)
    if figure:
        _figure_tile(deck, slide, ink, _slot_rect(next(slot_iter)), figure, figure_label, figure_note, 99)
    for rank, i in enumerate(order):
        style = "strong" if rank == 0 else _STYLE_CYCLE[(rank - 1) % len(_STYLE_CYCLE)]
        _kpi_tile(deck, slide, ink, _slot_rect(next(slot_iter)), tiles[i], style, i)
    return slide


# =========================================================================== G9 giant_number
@register("giant_number", kind="data", extra_sizes=(STAT_BIG_PT,),
          summary="Swiss poster slide: one 54 pt numeral on a color panel, two-tone headline, context line.",
          source="G9 Swiss giant numeral + two-tone headline (One Week Wonders, dribbble 10)")
def giant_number(deck, number, unit="", headline_a="", headline_b="", context="", source_note="", kicker=""):
    """number (e.g. '98.2'), unit (e.g. '%'), headline_a + headline_b (b is drawn in the accent color),
    context (<= 4 lines, set under the numeral), source_note (micro line), kicker (micro label top-left)."""
    if not str(number).strip():
        raise StyleError("number is required")
    if not headline_a.strip():
        raise StyleError("headline_a is required")
    ink = _Ink(deck.theme)
    p, bg = ink.p, deck.theme.bg
    bnd = ink.band()
    slide = _plain_slide(deck)

    # right color panel (top-bleed, stops above the footer line)
    px = 7.7
    _shape(slide, MSO_SHAPE.RECTANGLE, px, 0.0, SLIDE_W_IN - px, 6.9, bnd["fill"], "deco:panel")
    nx, nw = px + 0.45, SLIDE_W_IN - px - 0.9 - 0.2
    ncol = ink.text_on(bnd["fill"], 54, True, (p["accent"], p["stat"], bnd["text"]))
    _, nh = _measure(deck, number, "stat_big", nw, [(" " + unit, "subtitle")] if unit else [])
    ctx_n, ctx_h = (0, 0.0)
    if context.strip():
        ctx_n, ctx_h = _measure(deck, context, "sidebar_bullet", nw)
        if ctx_n > 4:
            raise StyleError(f"context needs {ctx_n} lines (max 4)")
    block = nh + 0.26 + ((0.2 + ctx_h) if ctx_n else 0.0)
    ny = (6.9 - block) / 2.0
    _tb(deck, slide, nx, ny, nw, nh, str(number), "stat_big", ncol, align=PP_ALIGN.RIGHT,
        extra=[(" " + unit, "subtitle", bnd["text"])] if unit else [], name="numeral", max_lines=1)
    _shape(slide, MSO_SHAPE.RECTANGLE, nx + 0.1, ny + nh + 0.2, nw, 0.06, ncol, "deco:numeral_rule")
    if ctx_n:
        _tb(deck, slide, nx + 0.1, ny + nh + 0.46, nw, ctx_h, context, "sidebar_bullet", bnd["text"], name="context")

    # left column: kicker, hairline, headline, context, source
    lx, lw = 0.7, 6.4
    body_col = ink.text_on(bg, 12, False, (p["body"],))
    if body_col is None:
        raise StyleError(f"theme {deck.theme.name}: no legible text colour on the background")
    if kicker:
        _tb(deck, slide, lx, 0.5, lw, 0.25, kicker, "caption",
            ink.text_on(bg, 9.5, False, (p["caption"], body_col)), name="kicker", max_lines=1)
        _shape(slide, MSO_SHAPE.RECTANGLE, lx, 0.9, lw, 0.02, body_col, "deco:hairline")
    col_a = ink.text_on(bg, 30, True, (p["title_main"], body_col))
    col_b = ink.text_on(bg, 30, True, (p["accent"], p["stat"], p["subtitle"], col_a))
    head = headline_a.strip()
    extra = [(" " + headline_b.strip(), "title_main", col_b)] if headline_b.strip() else []
    n, hh = _measure(deck, head, "title_main", lw, [(e[0], e[1]) for e in extra])
    if n > 4:
        raise StyleError(f"headline needs {n} lines (max 4)")
    src_h = 0.0
    if source_note.strip():
        sn, src_h = _measure(deck, source_note, "caption", lw)
        if sn > 2:
            raise StyleError("source_note needs more than 2 lines")
        _tb(deck, slide, lx, 6.9 - src_h - 0.05, lw, src_h, source_note, "caption",
            ink.text_on(bg, 9.5, False, (p["caption"], body_col)), name="source_note")
    bottom = 6.9 - src_h - (0.2 if src_h else 0.0)
    head_top = bottom - hh
    if head_top < 1.0:
        raise StyleError("headline leaves no room under the kicker")
    _tb(deck, slide, lx, head_top, lw, hh, head, "title_main", col_a, extra=extra, name="headline")
    return slide


# =========================================================================== G12 highlight_chips
@register("highlight_chips", kind="data",
          summary="Color band with pill-shaped key-term chips, each followed by its claim sentence.",
          source="G12 Dark 'highlight chip' slide (sli.dev gallery: The unnamed, Dracula)")
def highlight_chips(deck, title, claims):
    """claims = [{chip, text}] (3-5). chip = key term (one line, 18 pt bold in a pill); text = the claim
    (body 16 pt, or 14 pt when five claims share the band; at most 2 lines)."""
    _require_list("claims", claims, 3, 5)
    ink = _Ink(deck.theme)
    bnd = ink.band()
    slide = deck.content_slide(title)
    band_top, band_bot = CONTENT_TOP - 0.05, CONTENT_BOTTOM - 0.05
    _shape(slide, MSO_SHAPE.RECTANGLE, 0.0, band_top, SLIDE_W_IN, band_bot - band_top, bnd["fill"], "deco:band")
    n = len(claims)
    pad = 0.25
    row_h = (band_bot - band_top - 2 * pad) / n
    chips = [_need_str(c, "chip", f"claim {i}") for i, c in enumerate(claims)]
    texts = [_need_str(c, "text", f"claim {i}") for i, c in enumerate(claims)]
    chip_w = min(4.2, max(2.2, max(_text_w(c, "subtitle") for c in chips) + 0.4))
    cx = 0.7
    tx = cx + chip_w + 0.45
    tw = X1 - 0.1 - tx
    role = None
    for r in ("body", "sidebar_bullet"):
        try:
            ok = all(_measure(deck, t, r, tw)[0] <= 2 and _measure(deck, t, r, tw)[1] <= row_h - 0.08 for t in texts)
        except StyleError:
            ok = False
        if ok:
            role = r
            break
    if role is None:
        raise StyleError("claim texts do not fit (max 2 lines per claim in the band); shorten them")
    chip_h = 0.5
    for i, (chip, text) in enumerate(zip(chips, texts)):
        ry = band_top + pad + i * row_h
        if i:
            _shape(slide, MSO_SHAPE.RECTANGLE, cx, ry, X1 - 0.1 - cx, 0.012, bnd["text"], f"deco:rowline{i}")
        cy = ry + (row_h - chip_h) / 2
        _pill(deck, slide, cx, cy, chip_h, chip, "subtitle", bnd["chip_fill"], bnd["chip_text"], f"deco:chip{i}",
              fixed_w=chip_w)
        # body/sidebar text carries 2.0 line spacing, which adds its leading above the glyphs: lift it
        lift = 0.07
        _tb(deck, slide, tx, ry + 0.04 - lift, tw, row_h - 0.08, text, role, bnd["text"], anchor=MSO_ANCHOR.MIDDLE,
            name=f"claim{i}")
    return slide


# =========================================================================== comparison_cards
@register("comparison_cards", kind="data", extra_sizes=(STAT_BIG_PT,),
          summary="2-4 side-by-side comparison cards: heading, one metric, three rows; one card marked recommended.",
          source="Marketing-deck pricing/comparison cards (ppt_marketing_styles_261004 s.4 item 8; Beautiful.ai Comparison)")
def comparison_cards(deck, title, cards, badge="Recommended"):
    """cards = [{heading, metric, metric_label?, rows: [(label, value)] x3 or [{label, value}] x3,
    recommended?: bool, badge?: str}] (2-4 cards, at most one recommended). The recommended card is
    raised, drawn in the strong style and carries a pill badge."""
    _require_list("cards", cards, 2, 4)
    recs = [c for c in cards if c.get("recommended")]
    if len(recs) > 1:
        raise StyleError("at most one card may be recommended")
    ink = _Ink(deck.theme)
    slide = deck.content_slide(title)
    n = len(cards)
    gap = 0.25
    cw = (X1 - X0 - gap * (n - 1)) / n
    base_top, rec_top, bottom = 1.8, 1.5, CONTENT_BOTTOM - 0.05
    pad = 0.25
    iw = cw - 2 * pad

    norm = []
    for i, c in enumerate(cards):
        ctx = f"card {i}"
        rows = c.get("rows")
        if not isinstance(rows, (list, tuple)) or len(rows) != 3:
            raise StyleError(f"{ctx}: exactly 3 rows required")
        rr = []
        for r in rows:
            if isinstance(r, dict):
                rr.append((_need_str(r, "label", ctx), _need_str(r, "value", ctx)))
            else:
                rr.append((str(r[0]), str(r[1])))
        norm.append(dict(heading=_need_str(c, "heading", ctx), metric=_need_str(c, "metric", ctx),
                         metric_label=_need_str(c, "metric_label", ctx, optional=True), rows=rr,
                         rec=bool(c.get("recommended")), badge=c.get("badge", badge)))

    # common typography so the cards line up
    head_lines = max(_measure(deck, c["heading"], "subtitle", iw)[0] for c in norm)
    if head_lines > 2:
        raise StyleError("card headings need more than 2 lines")
    head_h = head_lines * 18 * LINE_H / 72.0
    metric_role = None
    for r in ("stat_big", "title_main", "title_bar"):
        try:
            if all(_measure(deck, c["metric"], r, iw)[0] == 1 for c in norm):
                metric_role = r
                break
        except StyleError:
            continue
    if metric_role is None:
        raise StyleError("metric values are too wide for the cards")
    metric_h = ROLES[metric_role]["pt"] * LINE_H / 72.0
    ml_lines = max((_measure(deck, c["metric_label"], "table_cell", iw)[0] if c["metric_label"] else 0) for c in norm)
    if ml_lines > 2:
        raise StyleError("metric_label needs more than 2 lines")
    ml_h = ml_lines * 12 * LINE_H / 72.0

    y_head = 2.2
    y_metric = y_head + head_h + 0.12
    y_ml = y_metric + metric_h + 0.05
    y_rows = y_ml + ml_h + (0.2 if ml_h else 0.1)
    row_h = min(0.95, (bottom - pad - y_rows) / 3.0)
    if row_h < 0.45:
        raise StyleError("cards are too crowded: shorten headings / metric labels")
    for i, c in enumerate(norm):
        st = ink.style("strong" if c["rec"] else "soft")
        x = X0 + i * (cw + gap)
        top = rec_top if c["rec"] else base_top
        _rrect(slide, x, top, cw, bottom - top, st["fill"], f"deco:card{i}", radius=0.16, line=st["line"])
        ix = x + pad
        if c["rec"]:
            pf = ink.pick_fill([ink.p["accent"], ink.p["stat"], ink.p["subtitle"], ink.t.bg, ink.p["highlight_bg"]],
                               12, True, vs=st["fill"], min_vs=1.6)
            if pf is None:
                raise StyleError("no legible badge color on the recommended card")
            _pill(deck, slide, ix, top + 0.2, 0.34, c["badge"], "table_header", pf[0], pf[1], "deco:badge")
        _tb(deck, slide, ix, y_head, iw, head_h, c["heading"], "subtitle", st["main"], name=f"heading{i}")
        vcol = ink.text_on(st["fill"], ROLES[metric_role]["pt"], True, st["vprefs"])
        _tb(deck, slide, ix, y_metric, iw, metric_h, c["metric"], metric_role, vcol, name=f"metric{i}", max_lines=1)
        if c["metric_label"]:
            _tb(deck, slide, ix, y_ml, iw, ml_h, c["metric_label"], "table_cell", st["main"], name=f"metric_label{i}")
        lw_in = iw * 0.46
        vw_in = iw - lw_in - 0.1
        for k, (lab, val) in enumerate(c["rows"]):
            ry = y_rows + k * row_h
            _shape(slide, MSO_SHAPE.RECTANGLE, ix, ry, iw, 0.012, st["main"], f"deco:rowline{i}_{k}")
            _tb(deck, slide, ix, ry + 0.05, lw_in, row_h - 0.1, lab, "table_cell", st["main"],
                anchor=MSO_ANCHOR.MIDDLE, max_lines=2)
            _tb(deck, slide, ix + lw_in + 0.1, ry + 0.05, vw_in, row_h - 0.1, val, "table_header", st["main"],
                align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE, max_lines=2)
    return slide


# =========================================================================== metric_strip
@register("metric_strip", kind="data",
          summary="Thin strip of 3-5 metrics (value + label) under the headline, above a figure with caption.",
          source="KPI strip above a chart (Beautiful.ai Data & Chart / Big Number family)")
def metric_strip(deck, title, metrics, figure, caption=""):
    """metrics = [{value, label}] (3-5). figure = image path (aspect kept, >= 3 in, placed under the strip);
    caption = optional figure caption (Deck.caption)."""
    _require_list("metrics", metrics, 3, 5)
    ink = _Ink(deck.theme)
    st = ink.style("soft")
    slide = deck.content_slide(title)
    n = len(metrics)
    cw = (X1 - X0) / n
    iw = cw - 0.4
    vals = [_need_str(m, "value", f"metric {i}") for i, m in enumerate(metrics)]
    labs = [_need_str(m, "label", f"metric {i}") for i, m in enumerate(metrics)]
    vrole = None
    for r in ("title_bar", "subtitle"):
        try:
            if all(_measure(deck, v, r, iw)[0] == 1 for v in vals):
                vrole = r
                break
        except StyleError:
            continue
    if vrole is None:
        raise StyleError("metric values are too wide for the strip")
    lab_lines = max(_measure(deck, lab, "table_cell", iw)[0] for lab in labs)
    if lab_lines > 2:
        raise StyleError("metric labels need more than 2 lines")
    vh = ROLES[vrole]["pt"] * LINE_H / 72.0
    lh = lab_lines * 12 * LINE_H / 72.0
    pad = 0.13
    top, sh = 1.3, 2 * pad + vh + lh + 0.04
    _rrect(slide, X0, top, X1 - X0, sh, st["fill"], "deco:strip", radius=0.12, line=st["line"])
    vcol = ink.text_on(st["fill"], ROLES[vrole]["pt"], True, st["vprefs"])
    for i, (v, lab) in enumerate(zip(vals, labs)):
        x = X0 + i * cw + 0.2
        if i:
            _shape(slide, MSO_SHAPE.RECTANGLE, X0 + i * cw - 0.01, top + 0.18, 0.02, sh - 0.36, st["main"],
                   f"deco:divider{i}")
        _tb(deck, slide, x, top + pad, iw, vh, v, vrole, vcol, align=PP_ALIGN.CENTER, name=f"value{i}", max_lines=1)
        _tb(deck, slide, x, top + pad + vh + 0.04, iw, lh, lab, "table_cell", st["main"], align=PP_ALIGN.CENTER,
            name=f"label{i}")
    fig_top = Inches(top + sh + 0.12)
    if caption:
        anchor = deck.add_figure(slide, figure, top=fig_top, name="fig:" + Path(figure).stem)
        deck.caption(slide, caption, anchor)
    else:
        pad_emu = 0
        if deck.theme.plate is not None:
            from deck_builder import PLATE_PAD
            pad_emu = PLATE_PAD
        max_h = Y_FLOOR - fig_top - 2 * pad_emu
        if max_h < MIN_FIG_H:
            raise StyleError("figure area under the strip is below 3 in")
        deck.add_figure(slide, figure, top=fig_top, max_height=max_h, name="fig:" + Path(figure).stem)
    return slide
