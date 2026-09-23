#!/usr/bin/env python3
"""
deck_builder.py -- role-based python-pptx helper library for the journal-ppt skill.

This module makes the closed-list type scale, line-spacing rules, spacing rules,
color palette, and geometry constants in ../references/style_spec.md the path of
least resistance: callers pick a *role* (title / body / bullet / caption / ...)
rather than picking a raw pt value, so off-scale sizes are structurally hard to
introduce. `disable_autofit()` is wired into every text-adding helper so line
spacing can never be silently dropped (the single most common defect measured
in the 2026-08-23 session that this skill was built to fix).

Usage:
    from deck_builder import Deck

    deck = Deck()
    deck.title_slide("Paper Title", "Authors et al.", "Journal Year", "DOI: ...",
                      presenter="J. Lee", date="2026-08-23")
    s = deck.content_slide("Background & Motivation")
    deck.bullets(s, ["Point one.", "Point two."], role="body")
    deck.notes(s, "Korean speaker notes go here.")
    deck.save("out.pptx")
"""
from __future__ import annotations

import re
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.oxml.ns import qn
from lxml import etree

try:
    from PIL import Image as PILImage
except ImportError:  # pragma: no cover - PIL is a hard dependency in practice
    PILImage = None


# ============================================================================
# Closed-list constants (mirrors references/style_spec.md -- do not hand-edit
# a value here without updating the spec, and vice versa)
# ============================================================================

SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)

# --- Colors (style_spec.md §5) --------------------------------------------
HEADER_BG = RGBColor(0x1A, 0x35, 0x5E)   # dark navy
ACCENT = RGBColor(0xE8, 0x6A, 0x1A)      # orange
BODY_TEXT = RGBColor(0x33, 0x33, 0x33)   # dark gray
SUBTITLE = RGBColor(0x2E, 0x5E, 0x9B)    # medium blue
CAPTION_COLOR = RGBColor(0x88, 0x88, 0x88)  # light gray
HIGHLIGHT_BG = RGBColor(0xDB, 0xE8, 0xF7)   # light blue box fill
WARNING_BG = RGBColor(0xFD, 0xE8, 0xE8)     # light red box fill
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
TABLE_HDR_BG = HEADER_BG
TABLE_HDR_TEXT = WHITE
TABLE_ZEBRA = HIGHLIGHT_BG

ALLOWED_HEX = {"1A355E", "E86A1A", "333333", "2E5E9B", "888888",
               "DBE8F7", "FDE8E8", "FFFFFF"}

# --- Type scale (style_spec.md §2) -- role -> (pt, bold, italic, color) ----
# 9 base roles + conditional {20} stat-tile role for research-mode decks.
ROLES = {
    "title_bar":        dict(pt=26,  bold=True,  italic=False, color=WHITE),       # header bar title
    "title_main":       dict(pt=30,  bold=True,  italic=False, color=HEADER_BG),   # title-slide main title
    "subtitle":         dict(pt=18,  bold=True,  italic=False, color=SUBTITLE),    # section subtitle / TOC / stat label
    "body":             dict(pt=16,  bold=False, italic=False, color=BODY_TEXT),   # text-only-slide bullets
    "sidebar_bullet":   dict(pt=14,  bold=False, italic=False, color=BODY_TEXT),   # figure-slide sidebar bullets
    "fig_subtitle":     dict(pt=14,  bold=True,  italic=True,  color=SUBTITLE),    # figure-slide subtitle
    "table_header":     dict(pt=12,  bold=True,  italic=False, color=WHITE),       # table header row
    "table_cell":       dict(pt=12,  bold=False, italic=False, color=BODY_TEXT),   # table cell / annotation
    "reference":        dict(pt=11,  bold=False, italic=False, color=BODY_TEXT),   # references-slide entry
    "presenter":        dict(pt=11,  bold=False, italic=False, color=BODY_TEXT),   # title-slide presenter/date
    "caption":          dict(pt=9.5, bold=False, italic=True,  color=CAPTION_COLOR),  # figure caption
    "footer":           dict(pt=9,   bold=False, italic=False, color=CAPTION_COLOR),  # footer / page number
    "stat_number":      dict(pt=20,  bold=True,  italic=False, color=ACCENT),      # conditional, research-mode KPI tiles
}
ALLOWED_FONT_SIZES = {9, 9.5, 11, 12, 14, 16, 18, 26, 30, 20}

# --- Line spacing (style_spec.md §3) -- role -> multiplier ----------------
LINE_SPACING = {
    "title_bar": 1.0, "title_main": 1.0,
    "subtitle": 1.0, "fig_subtitle": 1.0,
    "body": 1.5, "sidebar_bullet": 1.5,
    "caption": 1.0, "footer": 1.0,
    "reference": 1.15,
    "table_header": 1.0, "table_cell": 1.0,
    "presenter": 1.5, "stat_number": 1.0,
}
ALLOWED_LINE_SPACING = {1.0, 1.15, 1.5}

# --- space_after (style_spec.md §4) -- role -> pt -------------------------
SPACE_AFTER = {
    "body": 6, "sidebar_bullet": 6,
    "title_bar": 0, "title_main": 12,
    "subtitle": 12, "fig_subtitle": 12,
    "caption": 2, "footer": 0,
    "reference": 6, "presenter": 0,
    "table_header": 0, "table_cell": 0,
    "stat_number": 0,
}
ALLOWED_SPACE_AFTER_PT = {0, 2, 6, 12, 16}

# --- Geometry (style_spec.md §6) -------------------------------------------
HEADER_BAR_H = Inches(1.1)
HEADER_TITLE_LEFT_FIG = Inches(0.4)     # figure-slide-template header title inset
HEADER_TITLE_TOP_FIG = Inches(0.12)
HEADER_TITLE_LEFT_PLAIN = Inches(0.5)   # plain content-slide header title inset
HEADER_TITLE_TOP_PLAIN = Inches(0.15)
BODY_TOP_NO_FIGURE = Inches(1.4)
FIG_SUBTITLE_TOP = Inches(1.15)
FIG_SUBTITLE_H = Inches(0.5)
KEY_POINT_TOP = Inches(1.7)
KEY_POINT_H = Inches(1.3)
MARGIN = Inches(0.3)
FOOTER_TOP = Inches(7.1)
FOOTER_BOTTOM = Inches(7.4)
Y_FLOOR = Inches(7.0)          # nothing may cross this
CAPTION_H = Inches(0.75)
CAPTION_GAP = Inches(0.06)
MIN_FIG_W_SIDE = Inches(5.5)
MIN_FIG_W_FULL = Inches(9.0)
MIN_FIG_H = Inches(3.0)
FIG_TEXT_GAP = Inches(0.3)

REQUIRED_FONT = "Arial"
HANGUL_RE = re.compile(r'[\uAC00-\uD7A3\u3130-\u318F]')


class StyleError(ValueError):
    """Raised when a caller requests an off-scale size/spacing -- the spec is a
    closed list, so this is a hard rejection, not a warning."""


# ============================================================================
# Mandatory wiring: disable_autofit + set_line_spacing (style_spec.md §3)
# ============================================================================

def disable_autofit(text_frame) -> None:
    """Disable spAutoFit/normAutofit so PowerPoint honors manual line spacing.
    MUST run before set_line_spacing() on the same text frame, or PowerPoint
    silently ignores the spacing (measured defect, both 2026-08-23 decks)."""
    bodyPr = text_frame._txBody.find(qn('a:bodyPr'))
    if bodyPr is not None:
        for child in bodyPr.findall(qn('a:spAutoFit')):
            bodyPr.remove(child)
        for child in bodyPr.findall(qn('a:normAutofit')):
            bodyPr.remove(child)
        # idempotent: don't add a second noAutofit if already present
        if bodyPr.find(qn('a:noAutofit')) is None:
            etree.SubElement(bodyPr, qn('a:noAutofit'))


def set_line_spacing(paragraph, spacing: float) -> None:
    """paragraph.line_spacing accepts a float multiplier directly."""
    paragraph.line_spacing = spacing


def _validate_role(role: str) -> dict:
    if role not in ROLES:
        raise StyleError(
            f"Unknown role {role!r}. Off-scale sizes are not permitted -- "
            f"choose one of {sorted(ROLES)} or extend ROLES in deck_builder.py "
            f"AND references/style_spec.md together."
        )
    return ROLES[role]


# ============================================================================
# Deck class
# ============================================================================

class Deck:
    """Owns the Presentation object, slide numbering, and footer text."""

    def __init__(self, footer_right: str = ""):
        self.prs = Presentation()
        self.prs.slide_width = SLIDE_W
        self.prs.slide_height = SLIDE_H
        self._slide_num = 0
        self.footer_right = footer_right

    # -- low level -----------------------------------------------------

    def _blank(self):
        return self.prs.slide_layouts[6]

    def new_slide(self):
        return self.prs.slides.add_slide(self._blank())

    def _next_num(self) -> int:
        self._slide_num += 1
        return self._slide_num

    # -- text primitives -------------------------------------------------

    def add_textbox(self, slide, left, top, width, height, text: str, role: str,
                     align=PP_ALIGN.LEFT, word_wrap: bool = True,
                     line_spacing: float | None = None,
                     space_after: float | None = None):
        """Add a single-paragraph textbox styled entirely from `role`.
        Returns the textbox shape. This is the core building block every
        higher-level helper (bullets/caption/table_cell/...) funnels through,
        so disable_autofit() + set_line_spacing() can never be forgotten."""
        spec = _validate_role(role)
        txb = slide.shapes.add_textbox(left, top, width, height)
        tf = txb.text_frame
        tf.word_wrap = word_wrap
        disable_autofit(tf)

        p = tf.paragraphs[0]
        p.alignment = align
        ls = LINE_SPACING[role] if line_spacing is None else line_spacing
        if ls not in ALLOWED_LINE_SPACING:
            raise StyleError(f"line_spacing={ls} not in {ALLOWED_LINE_SPACING}")
        set_line_spacing(p, ls)
        sa = SPACE_AFTER.get(role, 0) if space_after is None else space_after
        if sa not in ALLOWED_SPACE_AFTER_PT:
            raise StyleError(f"space_after={sa} not in {ALLOWED_SPACE_AFTER_PT}")
        p.space_after = Pt(sa)

        run = p.add_run()
        run.text = text
        run.font.name = REQUIRED_FONT
        run.font.size = Pt(spec["pt"])
        run.font.bold = spec["bold"]
        run.font.italic = spec["italic"]
        run.font.color.rgb = spec["color"]
        return txb

    def bullets(self, slide, items: list[str], role: str = "body",
                left=None, top=None, width=None, height=None,
                bullet_char: str = "\u2022 ", last_space_after: float = 0):
        """Add a multi-paragraph bulleted textbox. role must be 'body' or
        'sidebar_bullet' (or any role present in LINE_SPACING/SPACE_AFTER)."""
        spec = _validate_role(role)
        if left is None:
            left = MARGIN
        if top is None:
            top = BODY_TOP_NO_FIGURE
        if width is None:
            width = SLIDE_W - 2 * MARGIN
        if height is None:
            height = Y_FLOOR - top

        txb = slide.shapes.add_textbox(left, top, width, height)
        tf = txb.text_frame
        tf.word_wrap = True
        disable_autofit(tf)

        ls = LINE_SPACING[role]
        sa = SPACE_AFTER.get(role, 6)
        for i, text in enumerate(items):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.alignment = PP_ALIGN.LEFT
            set_line_spacing(p, ls)
            is_last = (i == len(items) - 1)
            p.space_after = Pt(last_space_after if is_last else sa)
            run = p.add_run()
            run.text = bullet_char + text
            run.font.name = REQUIRED_FONT
            run.font.size = Pt(spec["pt"])
            run.font.bold = spec["bold"]
            run.font.italic = spec["italic"]
            run.font.color.rgb = spec["color"]
        return txb

    # -- slide-level helpers ----------------------------------------------

    def title_slide(self, title: str, citation: str, journal_line: str,
                     presenter: str, date: str):
        """No header bar; large centered title + accent line + citation."""
        slide = self.new_slide()
        bg = slide.background
        bg.fill.solid()
        bg.fill.fore_color.rgb = WHITE

        self.add_textbox(slide, Inches(1.0), Inches(2.0), SLIDE_W - Inches(2.0),
                          Inches(1.6), title, role="title_main",
                          align=PP_ALIGN.CENTER)

        # accent divider (a pure decoration -- python-pptx still creates an
        # implicit text_frame on any autoshape, so it must get the same
        # disable_autofit()/word_wrap treatment or QC-2 flags it)
        line = slide.shapes.add_shape(1, Inches(4.665), Inches(3.65),
                                       Inches(4.0), Pt(2.5))
        line.fill.solid()
        line.fill.fore_color.rgb = ACCENT
        line.line.fill.background()
        line.text_frame.word_wrap = True
        disable_autofit(line.text_frame)

        self.add_textbox(slide, Inches(1.0), Inches(3.85), SLIDE_W - Inches(2.0),
                          Inches(0.5), citation, role="fig_subtitle",
                          align=PP_ALIGN.CENTER)
        self.add_textbox(slide, Inches(1.0), Inches(4.4), SLIDE_W - Inches(2.0),
                          Inches(0.4), journal_line, role="presenter",
                          align=PP_ALIGN.CENTER)
        self.add_textbox(slide, Inches(1.0), Inches(5.2), SLIDE_W - Inches(2.0),
                          Inches(0.4), f"Presenter: {presenter}    |    {date}",
                          role="presenter", align=PP_ALIGN.CENTER)
        self._next_num()
        return slide

    def content_slide(self, title: str, plain: bool = True):
        """Standard header-bar content slide (no figure)."""
        slide = self.new_slide()
        bg = slide.background
        bg.fill.solid()
        bg.fill.fore_color.rgb = WHITE

        bar = slide.shapes.add_shape(1, Inches(0), Inches(0), SLIDE_W, HEADER_BAR_H)
        bar.fill.solid()
        bar.fill.fore_color.rgb = HEADER_BG
        bar.line.fill.background()
        tf = bar.text_frame
        tf.word_wrap = True
        disable_autofit(tf)
        left_in = HEADER_TITLE_LEFT_PLAIN if plain else HEADER_TITLE_LEFT_FIG
        top_in = HEADER_TITLE_TOP_PLAIN if plain else HEADER_TITLE_TOP_FIG
        tf.margin_left = left_in
        tf.margin_top = top_in
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.LEFT
        set_line_spacing(p, LINE_SPACING["title_bar"])
        p.space_after = Pt(SPACE_AFTER["title_bar"])
        run = p.add_run()
        run.text = title
        spec = ROLES["title_bar"]
        run.font.name = REQUIRED_FONT
        run.font.size = Pt(spec["pt"])
        run.font.bold = spec["bold"]
        run.font.color.rgb = spec["color"]

        num = self._next_num()
        self._footer(slide, num)
        return slide

    def figure_slide(self, title: str, subtitle: str, key_points: list[str],
                      fig_path: str, caption_text: str):
        """Figure-first slide following the Figure-First Layout rules."""
        slide = self.content_slide(title, plain=False)
        num = self._slide_num  # already incremented by content_slide

        if subtitle:
            self.add_textbox(slide, HEADER_TITLE_LEFT_FIG, FIG_SUBTITLE_TOP,
                              SLIDE_W - 2 * HEADER_TITLE_LEFT_FIG, FIG_SUBTITLE_H,
                              subtitle, role="fig_subtitle")

        if key_points:
            self.bullets(slide, key_points[:3], role="sidebar_bullet",
                         left=HEADER_TITLE_LEFT_FIG, top=KEY_POINT_TOP,
                         width=SLIDE_W - 2 * HEADER_TITLE_LEFT_FIG,
                         height=KEY_POINT_H)

        anchor = self.add_figure(slide, fig_path, top=Inches(3.1))
        if caption_text:
            self.caption(slide, caption_text, anchor)
        return slide

    def add_figure(self, slide, fig_path: str, top=Inches(3.1),
                    left=None, max_width=None, max_height=None):
        """Insert a picture centered horizontally, preserving aspect ratio,
        enforcing the >=3in minimum dimension (upscaling if needed), and
        staying above Y_FLOOR. Returns (fig_left, fig_top, fig_w, fig_h) so
        the caller can anchor a caption box below it."""
        if PILImage is None:
            raise RuntimeError("Pillow is required for add_figure()")
        with PILImage.open(fig_path) as img:
            orig_w, orig_h = img.size

        if max_width is None:
            max_width = SLIDE_W - Inches(0.6)
        if max_height is None:
            max_height = Y_FLOOR - CAPTION_H - CAPTION_GAP - top

        scale = min(max_width / orig_w, max_height / orig_h)
        fig_w = int(orig_w * scale)
        fig_h = int(orig_h * scale)

        # enforce >=3in minimum in at least one dimension (upscale if smaller,
        # never distorting aspect ratio)
        if max(fig_w, fig_h) < MIN_FIG_H:
            up = MIN_FIG_H / max(fig_w, fig_h)
            fig_w = int(fig_w * up)
            fig_h = int(fig_h * up)

        if left is None:
            left = (SLIDE_W - fig_w) // 2
        pic = slide.shapes.add_picture(fig_path, left, top, fig_w, fig_h)
        return (left, top, fig_w, fig_h)

    def caption(self, slide, text: str, anchor):
        """anchor = (left, top, w, h) tuple from add_figure()."""
        left, top, w, h = anchor
        cap_top = top + h + CAPTION_GAP
        lines = text.split("\n")
        cap_box = slide.shapes.add_textbox(MARGIN, cap_top,
                                            SLIDE_W - 2 * MARGIN, CAPTION_H)
        tf = cap_box.text_frame
        tf.word_wrap = True
        disable_autofit(tf)
        spec = ROLES["caption"]
        for i, line in enumerate(lines):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            set_line_spacing(p, LINE_SPACING["caption"])
            p.space_after = Pt(SPACE_AFTER["caption"] if i < len(lines) - 1 else 0)
            run = p.add_run()
            run.text = line
            run.font.name = REQUIRED_FONT
            run.font.size = Pt(spec["pt"])
            run.font.italic = True
            run.font.color.rgb = spec["color"]
            if "et al." in line:
                run.font.bold = True
                run.font.color.rgb = BODY_TEXT
        return cap_box

    def authors_slide(self, authors_line: str, affiliations: list[tuple[str, str]],
                       logos: list[tuple[str, str]] | None = None,
                       corresponding: str | None = None):
        """Authors & Affiliations slide (journal mode).

        authors_line: full author list as one string (e.g. co-first authors
            marked inline, corresponding author flagged) -- one paragraph.
        affiliations: list of (institution_text, member_names_text) pairs,
            rendered as one bullet each: "<institution> -- <members>".
        logos: optional list of (png_path, caption_label) tuples, up to 4-6,
            laid out in an evenly-spaced row with a COMMON bounding band so
            very different aspect ratios (a square university crest next to
            a wide wordmark) still read as one consistent row. Pass finished
            PNG paths -- fetch and rasterize them before calling this, and
            keep one download path rather than repeating it per slide.
        corresponding: optional "Name (email)" line, rendered dimmer below
            the affiliation bullets.

        Layout follows the same header-bar / eyebrow-label language as
        content_slide() (style_spec.md, BACKGROUND-eyebrow content slides),
        so this slide reads as part of the deck rather than a bolted-on
        extra. Place it right after title_slide() in the paper-mode slide
        order (style_spec.md / pipeline.md Phase 3 slide order should list
        it as "Title -> Authors & Affiliations -> Background -> ...").
        """
        slide = self.content_slide("Authors & affiliations", plain=True)

        body_top = BODY_TOP_NO_FIGURE
        body = self.bullets(slide, [authors_line], role="body",
                             top=body_top, height=Inches(0.9))
        # re-flow: authors_line is one paragraph at body role, not a bullet list
        for para in body.text_frame.paragraphs:
            for run in para.runs:
                if run.text.startswith("• "):
                    run.text = run.text[2:]

        aff_lines = [f"{inst} — {members}" for inst, members in affiliations]
        if corresponding:
            aff_lines.append(corresponding)
        self.bullets(slide, aff_lines, role="sidebar_bullet",
                     top=body_top + Inches(1.0), height=Inches(1.6))

        if logos:
            self._logo_row(slide, logos, band_top=Inches(4.75), band_h=Inches(1.2))

        return slide

    def _logo_row(self, slide, logos: list[tuple[str, str]], band_top, band_h):
        """Lay out logos evenly across the slide width, each centered within
        a COMMON bounding box (band_h tall, ~82% of its column wide) so
        aspect-ratio outliers (a 7:1 wordmark next to a near-square crest)
        still align on one visual row instead of producing wildly different
        logo heights. Adds a caption label under each logo at 'footer' role
        color (light gray) so the row reads as attribution, not decoration.

        This is the exact pattern validated on the IRED journal-club deck
        (260912): naive equal-HEIGHT scaling made the widest wordmark (7:1
        aspect) shrink to ~0.3in tall next to a 1:1 crest at ~1in -- fitting
        every logo into the same bounding BOX instead (constrain by both max
        width and max height, take whichever binds) fixes that.
        """
        if PILImage is None:
            raise RuntimeError("Pillow is required for _logo_row()")
        n = len(logos)
        margin = MARGIN
        usable_w = SLIDE_W - 2 * margin
        slot_w = int(usable_w / n)

        for i, (path, label) in enumerate(logos):
            with PILImage.open(path) as im:
                iw, ih = im.size
            aspect = iw / ih
            max_w = int(slot_w * 0.82)
            max_h = band_h
            w_c = max_w
            h_c = int(w_c / aspect)
            if h_c > max_h:
                h_c = max_h
                w_c = int(h_c * aspect)

            slot_left = margin + i * slot_w
            pic_left = int(slot_left + (slot_w - w_c) / 2)
            pic_top = int(band_top + (band_h - h_c) / 2)
            pic = slide.shapes.add_picture(path, pic_left, pic_top, w_c, h_c)
            # Marker consumed by qc_deck.py's QC-11 exemption: a small
            # institution/company logo is deliberately NOT held to the same
            # >=3in minimum-dimension rule as a results figure (style_spec.md
            # §7.5's 3in floor exists so a data figure stays legible; a
            # word-mark badge in an evenly-spaced attribution row is a
            # different content class entirely).
            pic.name = "logo:" + Path(path).stem

            if label:
                self.add_textbox(slide, slot_left, band_top + band_h + Inches(0.16),
                                  slot_w, Inches(0.3), label, role="footer",
                                  align=PP_ALIGN.CENTER)

    def table_slide(self, title: str, headers: list[str], rows: list[list[str]]):
        slide = self.content_slide(title, plain=True)
        n_cols = len(headers)
        n_rows = len(rows) + 1
        top = BODY_TOP_NO_FIGURE
        avail_h = min(Y_FLOOR - top, Inches(0.4) * n_rows + Inches(0.3))
        table = slide.shapes.add_table(n_rows, n_cols, MARGIN, top,
                                        SLIDE_W - 2 * MARGIN, avail_h).table
        col_w = int((SLIDE_W - 2 * MARGIN) / n_cols)
        for ci in range(n_cols):
            table.columns[ci].width = col_w

        hdr_spec = ROLES["table_header"]
        for ci, hdr in enumerate(headers):
            cell = table.cell(0, ci)
            cell.fill.solid()
            cell.fill.fore_color.rgb = TABLE_HDR_BG
            tf = cell.text_frame
            disable_autofit(tf)
            p = tf.paragraphs[0]
            p.alignment = PP_ALIGN.CENTER
            set_line_spacing(p, LINE_SPACING["table_header"])
            p.space_after = Pt(SPACE_AFTER["table_header"])
            run = p.add_run()
            run.text = hdr
            run.font.name = REQUIRED_FONT
            run.font.size = Pt(hdr_spec["pt"])
            run.font.bold = True
            run.font.color.rgb = TABLE_HDR_TEXT

        cell_spec = ROLES["table_cell"]
        for ri, row in enumerate(rows):
            zebra = TABLE_ZEBRA if ri % 2 == 0 else WHITE
            for ci, val in enumerate(row):
                cell = table.cell(ri + 1, ci)
                cell.fill.solid()
                cell.fill.fore_color.rgb = zebra
                tf = cell.text_frame
                disable_autofit(tf)
                p = tf.paragraphs[0]
                p.alignment = PP_ALIGN.LEFT
                set_line_spacing(p, LINE_SPACING["table_cell"])
                p.space_after = Pt(SPACE_AFTER["table_cell"])
                run = p.add_run()
                run.text = str(val)
                run.font.name = REQUIRED_FONT
                run.font.size = Pt(cell_spec["pt"])
                run.font.color.rgb = cell_spec["color"]
        return slide

    def references_slide(self, refs: list[str], highlight_index: int | None = None):
        slide = self.content_slide("References", plain=True)
        txb = slide.shapes.add_textbox(MARGIN, BODY_TOP_NO_FIGURE,
                                        SLIDE_W - 2 * MARGIN, Y_FLOOR - BODY_TOP_NO_FIGURE)
        tf = txb.text_frame
        tf.word_wrap = True
        disable_autofit(tf)
        spec = ROLES["reference"]
        for i, ref in enumerate(refs):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            set_line_spacing(p, LINE_SPACING["reference"])
            p.space_after = Pt(SPACE_AFTER["reference"] if i < len(refs) - 1 else 0)
            run = p.add_run()
            run.text = f"[{i + 1}] {ref}"
            run.font.name = REQUIRED_FONT
            run.font.size = Pt(spec["pt"])
            run.font.bold = (i == highlight_index)
            run.font.color.rgb = spec["color"]
        return slide

    def _footer(self, slide, num: int):
        self.add_textbox(slide, MARGIN, FOOTER_TOP, Inches(1.0), Inches(0.3),
                          str(num), role="footer")
        if self.footer_right:
            self.add_textbox(slide, SLIDE_W - Inches(5.0), FOOTER_TOP, Inches(4.7),
                              Inches(0.3), self.footer_right, role="footer",
                              align=PP_ALIGN.RIGHT)

    def notes(self, slide, text: str):
        """Set Korean speaker notes on a slide (any language accepted here --
        the QC scan is what enforces Korean-only, this helper is agnostic)."""
        ns = slide.notes_slide
        ns.notes_text_frame.text = text

    def fit_check(self, text: str, role: str, width_in: float,
                  font_path: str = r"C:\Windows\Fonts\arial.ttf") -> dict:
        """Measure wrapped text height using real Arial metrics (PIL ImageFont)
        and report whether it fits typical sidebar/body allotments. Returns
        {'lines': N, 'height_in': H, 'width_in': width_in}. Does not raise by
        itself -- callers compare height_in against their box height and decide
        whether to shorten text (font-size shrinking is not in the approved
        toolkit per style_spec.md §7)."""
        if PILImage is None:
            raise RuntimeError("Pillow is required for fit_check()")
        from PIL import ImageFont
        spec = _validate_role(role)
        pt = spec["pt"]
        # PIL uses pixel-based fonts; approximate 1pt = 1.333px at 96dpi calc,
        # but since we only need relative wrapping, use a fixed dpi assumption
        # consistent with python-pptx EMU math: 1in = 96px for layout estimate.
        px_size = int(pt * 96 / 72)
        font = ImageFont.truetype(font_path, px_size)
        width_px = width_in * 96

        words = text.split()
        lines = []
        cur = ""
        for w in words:
            trial = (cur + " " + w).strip()
            bbox = font.getbbox(trial)
            if bbox[2] - bbox[0] <= width_px or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)

        line_h_pt = pt * LINE_SPACING.get(role, 1.0)
        n_lines = max(1, len(lines))
        height_in = (n_lines * line_h_pt) / 72.0
        return {"lines": n_lines, "height_in": height_in, "width_in": width_in}

    def save(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.prs.save(path)
        return path
