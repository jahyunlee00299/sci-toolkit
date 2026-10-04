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

Themes (style_spec.md §10): `Deck(theme="navy_lab")` selects one of five presets
that differ ONLY in palette, header style and a few layout flags. The type
scale, line-spacing and space_after closed lists are shared by every theme
(the single addition is the 54 pt `stat_big` size, allowed only in `mono_one`).

Usage:
    from deck_builder import Deck

    deck = Deck()                       # theme="navy_lab"
    deck.title_slide("Paper Title", "Authors et al.", "Journal Year", "DOI: ...",
                      presenter="J. Lee", date="2026-08-23")
    s = deck.content_slide("Background & Motivation")
    deck.bullets(s, ["Point one.", "Point two."], role="body")
    deck.notes(s, "Korean speaker notes go here.")
    deck.save("out.pptx")
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
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

# --- Colors of the default theme (navy_lab, style_spec.md §5) ---------------
HEADER_BG = RGBColor(0x1A, 0x35, 0x5E)   # dark navy
ACCENT = RGBColor(0xE8, 0x6A, 0x1A)      # orange (large bold text / graphics only)
BODY_TEXT = RGBColor(0x33, 0x33, 0x33)   # dark gray
SUBTITLE = RGBColor(0x2E, 0x5E, 0x9B)    # medium blue
CAPTION_COLOR = RGBColor(0x66, 0x66, 0x66)  # gray, 5.74:1 on white (was #888888 = 3.54:1)
HIGHLIGHT_BG = RGBColor(0xDB, 0xE8, 0xF7)   # light blue box fill
WARNING_BG = RGBColor(0xFD, 0xE8, 0xE8)     # light red box fill
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
TABLE_HDR_BG = HEADER_BG
TABLE_HDR_TEXT = WHITE
TABLE_ZEBRA = HIGHLIGHT_BG


def _rgb(hex6: str) -> RGBColor:
    return RGBColor(int(hex6[0:2], 16), int(hex6[2:4], 16), int(hex6[4:6], 16))


# --- Type scale (style_spec.md §2) -- role -> (pt, bold, italic, color) ----
# 9 base roles + conditional {20} stat-tile role for research-mode decks
# + {54} stat_big (only themes that list it in extra_sizes).  `color` is the navy_lab default; a
# Deck resolves the real color through its Theme (Theme.role_color()).
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
    "stat_big":         dict(pt=54,  bold=True,  italic=False, color=ACCENT),      # mono_one only: one large number
}
ALLOWED_FONT_SIZES = {9, 9.5, 11, 12, 14, 16, 18, 20, 26, 30, 54}
LAYOUT_SUBJECT_PREFIX = "journal-ppt-layouts:"
STAT_BIG_PT = 54   # the single size added by the theme work; allowed only via Theme.extra_sizes
EXTRA_SIZES_DOC = frozenset({STAT_BIG_PT})   # the explicitly documented set a Theme.extra_sizes may draw from

# --- Line spacing (style_spec.md §3) -- role -> multiplier ----------------
# 260930 user decision: body-class text is 2.0 (memory standard S2); 1.5 is retired.
LINE_SPACING = {
    "title_bar": 1.0, "title_main": 1.0,
    "subtitle": 1.0, "fig_subtitle": 1.0,
    "body": 2.0, "sidebar_bullet": 2.0,
    "caption": 1.0, "footer": 1.0,
    "reference": 1.15,
    "table_header": 1.0, "table_cell": 1.0,
    "presenter": 2.0, "stat_number": 1.0, "stat_big": 1.0,
}
ALLOWED_LINE_SPACING = {1.0, 1.15, 2.0}

# --- space_after (style_spec.md §4) -- role -> pt -------------------------
SPACE_AFTER = {
    "body": 6, "sidebar_bullet": 6,
    "title_bar": 0, "title_main": 12,
    "subtitle": 12, "fig_subtitle": 12,
    "caption": 2, "footer": 0,
    "reference": 6, "presenter": 0,
    "table_header": 0, "table_cell": 0,
    "stat_number": 0, "stat_big": 0,
}
ALLOWED_SPACE_AFTER_PT = {0, 2, 6, 12, 16}

# --- Geometry (style_spec.md §6) -------------------------------------------
# Vertical budget re-derived for 2.0 line spacing (style_spec.md §6.1):
#   sidebar 14 pt @2.0 -> one line = 14*1.2*2.0 = 33.6 pt = 0.467 in
#   3 sidebar bullets  -> 3*0.467 + 2*(6 pt) + 0.1 in box padding = 1.67 in -> KEY_POINT_H 1.7
#   body 16 pt @2.0    -> one line = 38.4 pt = 0.533 in; 5 bullets = 3.0 in, 9 lines fit above Y_FLOOR
HEADER_BAR_H = Inches(1.1)
HEADER_TITLE_LEFT_FIG = Inches(0.4)     # figure-slide-template header title inset
HEADER_TITLE_TOP_FIG = Inches(0.12)
HEADER_TITLE_LEFT_PLAIN = Inches(0.5)   # plain content-slide header title inset
HEADER_TITLE_TOP_PLAIN = Inches(0.15)
BODY_TOP_NO_FIGURE = Inches(1.4)
FIG_SUBTITLE_TOP = Inches(1.15)
FIG_SUBTITLE_H = Inches(0.4)            # was 0.5; a 14 pt single line needs 0.33
KEY_POINT_TOP = Inches(1.55)            # was 1.7
KEY_POINT_H = Inches(1.7)               # was 1.3; 3 single-line bullets at 2.0 spacing
FIG_TOP_WITH_POINTS = Inches(3.3)       # was 3.1; KEY_POINT_TOP + KEY_POINT_H + 0.05
FIG_TOP_NO_POINTS = Inches(1.3)         # figure-only slide (assertion-evidence)
MARGIN = Inches(0.3)
CLUB_MARGIN = Inches(0.4)   # journal-club preset: left/right page margin (whitespace brief, 261004)
FOOTER_TOP = Inches(7.1)
FOOTER_BOTTOM = Inches(7.4)
Y_FLOOR = Inches(7.0)          # nothing may cross this
CAPTION_H = Inches(0.5)        # was 0.75; 9.5 pt @1.0, two lines = 0.32 in + 0.1 pad
CAPTION_GAP = Inches(0.06)
MIN_FIG_W_SIDE = Inches(5.5)
MIN_FIG_W_FULL = Inches(9.0)
MIN_FIG_H = Inches(3.0)
FIG_TEXT_GAP = Inches(0.3)
PLATE_PAD = Inches(0.07)
LINE_HEIGHT_FACTOR = 1.2       # Arial single-line height / pt (conservative; real = 1.15)
BOX_PAD = Inches(0.1)          # default textbox top+bottom inset (0.05 + 0.05)

REQUIRED_FONT = "Arial"   # default; a Theme may override via Theme.font
HEADER_STYLES = ("bar", "headline", "rule", "sidebar", "none")
SIDEBAR_W = Inches(0.25)
HANGUL_RE = re.compile(r'[\uAC00-\uD7A3\u3130-\u318F]')

THEME_KEYWORD_PREFIX = "journal-ppt-theme:"
DEFAULT_THEME = "navy_lab"


class StyleError(ValueError):
    """Raised when a caller requests an off-scale size/spacing -- the spec is a
    closed list, so this is a hard rejection, not a warning."""


# ============================================================================
# Contrast helpers (WCAG 2.x relative luminance)
# ============================================================================

def _lin(c: int) -> float:
    s = c / 255.0
    return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4


def relative_luminance(rgb) -> float:
    r, g, b = rgb[0], rgb[1], rgb[2]
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contrast_ratio(fg, bg) -> float:
    l1, l2 = relative_luminance(fg), relative_luminance(bg)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def required_contrast(pt: float, bold: bool) -> float:
    """WCAG 1.4.3 as tightened for this skill: 4.5:1, or 3:1 only for text
    that is >=18 pt AND bold."""
    return 3.0 if (pt >= 18 and bold) else 4.5


# ============================================================================
# Themes (style_spec.md §10)
# ============================================================================

PROVENANCE_KINDS = {
    "own": "our own choice (core themes)",
    "measured": "colors read from the XML of a real downloaded template",
    "official": "hex read from the owner's own guideline page or PDF",
    "third_party": "hex from a third-party page that reverse-engineers a brand (not the owner)",
    "described": "hex chosen by us from a verbal description of the style; no source gives the colors",
    "unverified": "hex from memory or a search snippet; the source page was not read",
}


@dataclass(frozen=True, eq=False)
class Theme:
    """A palette + header style + a few layout flags. Never touches the type
    scale, line spacing or space_after lists (those are shared by all themes)."""
    name: str
    description: str
    header_style: str                  # one of HEADER_STYLES: bar|headline|rule|sidebar|none
    bg: RGBColor                       # slide background
    header_bg: RGBColor | None         # filled bar behind the title (bar/dark), else None
    palette: dict                      # name -> RGBColor, see _PALETTE_KEYS
    rule_color: RGBColor | None = None # thin rule under the title (header_style='rule')
    plate: RGBColor | None = None      # light plate behind figures (dark_seminar)
    allow_bullets: bool = True         # assertion_evidence: False
    caption_h: int = CAPTION_H         # journal_print: long caption box
    extra_sizes: frozenset = field(default_factory=frozenset)   # sizes beyond the shared base
    extra_hex: frozenset = field(default_factory=frozenset)     # sanctioned derived colors
    font: str = REQUIRED_FONT          # optional font override (qc_deck accepts exactly this font)
    family: str = "core"               # grouping for list_themes(): core|editorial|movement|brand|marketing|korean
    flat_note: str = ""                # one line: which decoration of the source style is NOT implemented
    provenance: str = "own"            # where the palette came from, one of PROVENANCE_KINDS

    def __post_init__(self):
        if self.header_style not in HEADER_STYLES:
            raise ValueError(f"theme {self.name}: header_style {self.header_style!r} not in {HEADER_STYLES}")
        if self.provenance not in PROVENANCE_KINDS:
            raise ValueError(f"theme {self.name}: provenance {self.provenance!r} not in {sorted(PROVENANCE_KINDS)}")
        if not self.extra_sizes <= EXTRA_SIZES_DOC:
            raise ValueError(f"theme {self.name}: extra_sizes {sorted(self.extra_sizes)} not within the "
                             f"documented set {sorted(EXTRA_SIZES_DOC)}")

    # -- colors -----------------------------------------------------------
    def role_color(self, role: str) -> RGBColor:
        p = self.palette
        return {
            "title_bar": p["title_bar_text"], "title_main": p["title_main"],
            "subtitle": p["subtitle"], "fig_subtitle": p["subtitle"],
            "body": p["body"], "sidebar_bullet": p["body"], "reference": p["body"],
            "presenter": p["body"], "table_cell": p["body"],
            "table_header": p["table_hdr_text"],
            "caption": p["caption"], "footer": p["footer"],
            "stat_number": p["stat"], "stat_big": p["stat"],
        }[role]

    def role_backgrounds(self, role: str) -> list:
        """Every fill a text role of this theme can sit on."""
        if role == "title_bar":
            # only the 'bar' style puts the title on the header fill; sidebar uses it for the band
            return [self.header_bg if (self.header_style == "bar" and self.header_bg is not None) else self.bg]
        if role == "table_header":
            return [self.palette["table_hdr_bg"]]
        if role == "table_cell":
            return [self.bg, self.palette["zebra"]]
        return [self.bg]

    @property
    def allowed_hex(self) -> frozenset:
        vals = {str(self.bg)} | {str(v) for v in self.palette.values()}
        if self.header_bg is not None:
            vals.add(str(self.header_bg))
        if self.rule_color is not None:
            vals.add(str(self.rule_color))
        if self.plate is not None:
            vals.add(str(self.plate))
        return frozenset(vals) | self.extra_hex

    @property
    def allowed_sizes_extra(self) -> frozenset:
        return self.extra_sizes


_PALETTE_KEYS = ("title_bar_text", "title_main", "subtitle", "body", "caption", "footer",
                 "accent", "stat", "highlight_bg", "warning_bg",
                 "table_hdr_bg", "table_hdr_text", "zebra")


def _theme(name, description, header_style, bg, header_bg, rule_color=None, plate=None,
           allow_bullets=True, caption_h=CAPTION_H, extra_sizes=(), extra_hex=(),
           font=REQUIRED_FONT, family="core", flat_note="", provenance="own", **pal):
    missing = [k for k in _PALETTE_KEYS if k not in pal]
    if missing:
        raise ValueError(f"theme {name}: missing palette keys {missing}")
    return Theme(
        name=name, description=description, header_style=header_style,
        bg=_rgb(bg), header_bg=_rgb(header_bg) if header_bg else None,
        palette={k: _rgb(pal[k]) for k in _PALETTE_KEYS},
        rule_color=_rgb(rule_color) if rule_color else None,
        plate=_rgb(plate) if plate else None,
        allow_bullets=allow_bullets, caption_h=caption_h, font=font,
        extra_sizes=frozenset(extra_sizes), extra_hex=frozenset(extra_hex),
        family=family, flat_note=flat_note, provenance=provenance)


THEMES: dict[str, Theme] = {t.name: t for t in (
    _theme("navy_lab", "Lab default: navy header bar, orange accent, white body.",
           "bar", "FFFFFF", "1A355E",
           title_bar_text="FFFFFF", title_main="1A355E", subtitle="2E5E9B", body="333333",
           caption="666666", footer="666666", accent="E86A1A", stat="E86A1A",
           highlight_bg="DBE8F7", warning_bg="FDE8E8",
           table_hdr_bg="1A355E", table_hdr_text="FFFFFF", zebra="DBE8F7",
           extra_hex=("C5D5EA", "2C6E3F", "A53636")),
    _theme("assertion_evidence",
           "Alley assertion-evidence: full-sentence headline, one figure, no bullets, no header bar.",
           "headline", "FFFFFF", None, allow_bullets=False,
           title_bar_text="1A355E", title_main="1A355E", subtitle="2E5E9B", body="333333",
           caption="595959", footer="595959", accent="E86A1A", stat="E86A1A",
           highlight_bg="DBE8F7", warning_bg="FDE8E8",
           table_hdr_bg="1A355E", table_hdr_text="FFFFFF", zebra="DBE8F7"),
    _theme("journal_print",
           "Print/handout: white, thin red rule under the title, long caption box (0.9 in: figure slides take <=2 key points).",
           "rule", "FFFFFF", None, rule_color="C8102E", caption_h=Inches(0.9),
           title_bar_text="111111", title_main="111111", subtitle="5A5A5A", body="222222",
           caption="444444", footer="595959", accent="C8102E", stat="C8102E",
           highlight_bg="F2F2F2", warning_bg="FBE9EB",
           table_hdr_bg="222222", table_hdr_text="FFFFFF", zebra="F2F2F2"),
    _theme("dark_seminar",
           "Dark room: #11161C background, one amber emphasis, figures on a light plate.",
           "bar", "11161C", "1B232C", plate="F2F4F6",
           title_bar_text="E6EAEE", title_main="E6EAEE", subtitle="9DB4CC", body="E6EAEE",
           caption="A9B4BF", footer="A9B4BF", accent="F2B134", stat="F2B134",
           highlight_bg="1B232C", warning_bg="3A2A2A",
           table_hdr_bg="2A3541", table_hdr_text="E6EAEE", zebra="232D38"),
    _theme("mono_one",
           "Grayscale plus one Okabe-Ito blue (#0072B2); adds the stat_big large-number role.",
           "bar", "FFFFFF", "2B2B2B", extra_sizes=(STAT_BIG_PT,),
           title_bar_text="FFFFFF", title_main="222222", subtitle="0072B2", body="222222",
           caption="595959", footer="595959", accent="0072B2", stat="0072B2",
           highlight_bg="E8E8E8", warning_bg="F2F2F2",
           table_hdr_bg="2B2B2B", table_hdr_text="FFFFFF", zebra="EDEDED"),
    # ---- Family A: editorial / data-journalism (palette echoes, no affiliation with any publisher) ----
    _theme("economist_rule",
           "Newspaper-chart look: white, red rule under a bold headline, blue emphasis; best for result slides in journal club/defense (red = one item per slide).",
           "rule", "FFFFFF", None, rule_color="E3120B", family="editorial", provenance="third_party",
           flat_note="flat variant: full-width red rule only, no short filled tag, no right-hand axis",
           title_bar_text="0D0D0D", title_main="0D0D0D", subtitle="006BA2", body="0D0D0D",
           caption="595959", footer="595959", accent="E3120B", stat="006BA2",
           highlight_bg="E6EEF3", warning_bg="FCE4E2",
           table_hdr_bg="006BA2", table_hdr_text="FFFFFF", zebra="EEF2F5",
           extra_hex=("B7C6CF",)),
    _theme("ft_salmon_paper",
           "Warm salmon paper, ink rule, claret emphasis; narrative journal club or grant pitch (figures sit on a white plate).",
           "rule", "FFF1E5", None, rule_color="33302E", plate="FFFFFF", family="editorial", provenance="third_party",
           flat_note="flat variant: no kicker line, no hairline above captions; Arial replaces the serif headline",
           title_bar_text="33302E", title_main="33302E", subtitle="990F3D", body="33302E",
           caption="66605C", footer="66605C", accent="990F3D", stat="990F3D",
           highlight_bg="F7E3D2", warning_bg="F6D5D9",
           table_hdr_bg="33302E", table_hdr_text="FFFFFF", zebra="F7E3D2",
           extra_hex=("CCC1B7", "0D7680")),
    _theme("nyt_hairline",
           "Restrained white page with a light hairline under the headline and blue emphasis; journal club, defense, review-style seminar.",
           "rule", "FFFFFF", None, rule_color="A6A6A6", family="editorial", provenance="third_party",
           flat_note="flat variant: Arial headline instead of the serif, no spaced uppercase eyebrow, no figure frame",
           title_bar_text="121212", title_main="121212", subtitle="326891", body="121212",
           caption="5A5A5A", footer="5A5A5A", accent="D0021B", stat="326891",
           highlight_bg="F2F2F2", warning_bg="FBE3E5",
           table_hdr_bg="121212", table_hdr_text="FFFFFF", zebra="F2F2F2"),
    _theme("highlight_grey",
           "Gray for context, one saturated color for the claim; headline only, results-heavy seminar or journal club.",
           "headline", "FFFFFF", None, family="editorial", provenance="described",
           flat_note="flat variant: palette and headline only; per-slide figure recolouring is the author's job",
           title_bar_text="1A1A1A", title_main="1A1A1A", subtitle="6B6B6B", body="1A1A1A",
           caption="6B6B6B", footer="6B6B6B", accent="B84F00", stat="0072B2",
           highlight_bg="E8F1F8", warning_bg="F9E8DC",
           table_hdr_bg="1A1A1A", table_hdr_text="FFFFFF", zebra="EFEFEF",
           extra_hex=("0072B2", "D9D9D9")),
    # ---- Family B: design-movement languages ----
    _theme("swiss_grid",
           "International Typographic Style: white, flush-left headline, one red signal, big numerals via stat_big; seminar or defense.",
           "headline", "FFFFFF", None, extra_sizes=(STAT_BIG_PT,), family="movement", provenance="described",
           flat_note="flat variant: no visible 12-column grid or red bar; asymmetry left to the layout",
           title_bar_text="111111", title_main="111111", subtitle="D9261C", body="111111",
           caption="767676", footer="767676", accent="D9261C", stat="D9261C",
           highlight_bg="F2F2F2", warning_bg="FBE4E2",
           table_hdr_bg="111111", table_hdr_text="FFFFFF", zebra="F2F2F2",
           extra_hex=("E6E6E6",)),
    _theme("swiss_night",
           "Swiss grid inverted: near-black ground, white type, one coral signal; dark-hall seminar or industry talk (figures on a light plate).",
           "rule", "111111", None, rule_color="FF5A4D", plate="F5F5F5", family="movement", provenance="described",
           flat_note="flat variant: coral rule only, no grid lines",
           title_bar_text="F5F5F5", title_main="F5F5F5", subtitle="A0A0A0", body="F5F5F5",
           caption="A0A0A0", footer="A0A0A0", accent="FF5A4D", stat="FF5A4D",
           highlight_bg="1E1E1E", warning_bg="3A1F1D",
           table_hdr_bg="333333", table_hdr_text="F5F5F5", zebra="1C1C1C"),
    _theme("bauhaus_primary",
           "Off-white ground, black type, red/blue primaries, red side band; teaching talk or section-heavy seminar (not dense results).",
           "sidebar", "F2EDE0", "C62828", plate="FFFFFF", family="movement", provenance="described",
           flat_note="flat variant: one red side band instead of circle/square/triangle blocks; no section numerals",
           title_bar_text="111111", title_main="111111", subtitle="1D4E89", body="111111",
           caption="5A5A5A", footer="5A5A5A", accent="C62828", stat="C62828",
           highlight_bg="E5DDC8", warning_bg="F2D4CF",
           table_hdr_bg="111111", table_hdr_text="FFFFFF", zebra="E5DDC8",
           extra_hex=("F2B705", "D8D0BC")),
    _theme("memphis_lite",
           "Cream ground, indigo type, magenta/blue accents, blue side band; outreach, mentoring session or industry opener (not dense data).",
           "sidebar", "FFF8E7", "0077B6", plate="FFFFFF", family="movement", provenance="described",
           flat_note="flat variant: no confetti shapes, squiggles or offset shapes (shape duplication skipped)",
           title_bar_text="1B1B3A", title_main="1B1B3A", subtitle="C2185B", body="1B1B3A",
           caption="5C5C7A", footer="5C5C7A", accent="C2185B", stat="C2185B",
           highlight_bg="F5EBD0", warning_bg="F8D9E4",
           table_hdr_bg="1B1B3A", table_hdr_text="FFFFFF", zebra="F5EBD0",
           extra_hex=("FFD60A", "E8E0CC")),
    _theme("neo_brutalist",
           "Warm white, pure black type, black rule, blue emphasis, yellow fill rows; student talks or poster-style lab-meeting decks.",
           "rule", "FFFDF5", None, rule_color="000000", family="movement", provenance="described",
           flat_note="flat variant: no bordered boxes or hard offset shadows (duplicated shapes skipped); yellow is fill-only",
           title_bar_text="000000", title_main="000000", subtitle="2F3EEA", body="000000",
           caption="4A4A4A", footer="4A4A4A", accent="2F3EEA", stat="2F3EEA",
           highlight_bg="FFE14D", warning_bg="FFD6D0",
           table_hdr_bg="000000", table_hdr_text="FFFFFF", zebra="FFE14D",
           extra_hex=("E5E0D0",)),
    _theme("neo_minimal_paper",
           "Quiet bookish off-white, ink green, brick accent, headline only; long seminar or defense with low eye fatigue.",
           "headline", "F7F5F0", None, plate="FFFFFF", family="movement", provenance="described",
           flat_note="flat variant: no small-caps section label",
           title_bar_text="1F2421", title_main="1F2421", subtitle="2F5D50", body="1F2421",
           caption="5E6661", footer="5E6661", accent="B5542B", stat="2F5D50",
           highlight_bg="E6EDE9", warning_bg="F3DFD6",
           table_hdr_bg="2F5D50", table_hdr_text="FFFFFF", zebra="ECE9E0",
           extra_hex=("D9D5CB",)),
    _theme("blueprint",
           "Dark blueprint blue, white linework, cyan subtitles, one amber mark; process/mechanism seminar or cascade-scheme talk (figures on a light plate).",
           "rule", "0B3C5D", None, rule_color="9CC3DB", plate="FFFFFF", family="movement", provenance="unverified",
           flat_note="flat variant: pale underline only, no corner tick marks",
           title_bar_text="FFFFFF", title_main="FFFFFF", subtitle="7FDBFF", body="FFFFFF",
           caption="9CC3DB", footer="9CC3DB", accent="FFD166", stat="FFD166",
           highlight_bg="1F5B84", warning_bg="5A2A2A",
           table_hdr_bg="1F5B84", table_hdr_text="FFFFFF", zebra="0F4A72"),
    # ---- Family C: science / tech brand-guideline echoes (palette only; no logos, no endorsement) ----
    _theme("carbon_light",
           "Engineered neutral: white page, light-gray header band, purple emphasis, figures on a gray tile; methods-heavy seminar or industry talk.",
           "bar", "FFFFFF", "F4F4F4", plate="F4F4F4", family="brand", provenance="official",
           flat_note="flat variant: Arial instead of IBM Plex; categorical series order left to the figure",
           title_bar_text="161616", title_main="161616", subtitle="6929C4", body="161616",
           caption="525252", footer="525252", accent="6929C4", stat="6929C4",
           highlight_bg="E8E0F7", warning_bg="FFE0E1",
           table_hdr_bg="262626", table_hdr_text="FFFFFF", zebra="F4F4F4",
           extra_hex=("002D9C",)),
    _theme("carbon_dark",
           "Control-room dark: #161616 ground, gray header band, cyan/violet data hues; dark-hall seminar (figures on a light plate).",
           "bar", "161616", "262626", plate="F4F4F4", family="brand", provenance="official",
           flat_note="flat variant: Arial instead of IBM Plex",
           title_bar_text="FFFFFF", title_main="FFFFFF", subtitle="1192E8", body="FFFFFF",
           caption="8D8D8D", footer="8D8D8D", accent="A56EFF", stat="A56EFF",
           highlight_bg="262626", warning_bg="3B1E20",
           table_hdr_bg="393939", table_hdr_text="FFFFFF", zebra="262626"),
    _theme("sanger_blue",
           "Genomics-institute look: deep-blue header bar, light-blue figure plate, orange as the only warm mark (fill only); genomics journal club, grant pitch.",
           "bar", "FFFFFF", "2D3A87", plate="B2C9D3", family="brand", provenance="official",
           flat_note="flat variant: no square-pattern artwork; orange and mid-blue are graphics-only (below 4.5:1 as text)",
           title_bar_text="FFFFFF", title_main="232642", subtitle="2D3A87", body="232642",
           caption="4A5170", footer="4A5170", accent="FD8230", stat="2D3A87",
           highlight_bg="E4EDF0", warning_bg="FDE3D0",
           table_hdr_bg="2D3A87", table_hdr_text="FFFFFF", zebra="E4EDF0",
           extra_hex=("597FBA",)),
    _theme("embl_green",
           "Open-science biology: white page, green rule, gray type, blue second accent; journal club, seminar or outreach.",
           "rule", "FFFFFF", None, rule_color="18974C", family="brand", provenance="official",
           flat_note="flat variant: no footer band; EMBL green #18974C is rule/fill only, text uses #007B53",
           title_bar_text="373A36", title_main="373A36", subtitle="007B53", body="373A36",
           caption="707372", footer="707372", accent="18974C", stat="007B53",
           highlight_bg="E6EFD8", warning_bg="F8DCE3",
           table_hdr_bg="007B53", table_hdr_text="FFFFFF", zebra="E6EFD8",
           extra_hex=("3B6FB6", "D0D0CE")),
    _theme("nasa_heritage",
           "Mission-control heritage: white, blue headline with red rule, silver figure plate; instrumentation/engineering talk or grant pitch (hex unverified).",
           "rule", "FFFFFF", None, rule_color="FC3D21", plate="D9DCDE", family="brand", provenance="unverified",
           flat_note="flat variant: red rule instead of a worm logotype; red is shape-only (3.6:1); palette echo, not agency branding",
           title_bar_text="0B3D91", title_main="0B3D91", subtitle="0B3D91", body="1A1A1A",
           caption="58595B", footer="58595B", accent="FC3D21", stat="0B3D91",
           highlight_bg="E4EAF5", warning_bg="FFE0DB",
           table_hdr_bg="0B3D91", table_hdr_text="FFFFFF", zebra="E9EBEC"),
    _theme("ink_violet",
           "Modern product look: pale cool canvas, navy ink, violet emphasis, white figure cards; industry talk or company-minded grant pitch.",
           "headline", "F6F9FC", None, plate="FFFFFF", family="brand", provenance="third_party",
           flat_note="flat variant: no gradient mesh or violet-pink cover strip; pink is shape-only (4.1:1)",
           title_bar_text="0D253D", title_main="0D253D", subtitle="533AFD", body="0D253D",
           caption="5B6B7B", footer="5B6B7B", accent="EA2261", stat="533AFD",
           highlight_bg="E7E3FF", warning_bg="FDE0E8",
           table_hdr_bg="0D253D", table_hdr_text="FFFFFF", zebra="E3E8EE"),
    _theme("consulting_mono",
           "Boardroom mono-hue: white, gray rule, blue/violet only, action-title headline; grant pitch, TEA/economics sections.",
           "rule", "FFFFFF", None, rule_color="C0C5C9", family="brand", provenance="third_party",
           flat_note="flat variant: no tracker label; single-hue chart rule is the author's job",
           title_bar_text="1F2A37", title_main="1F2A37", subtitle="1D3F8C", body="1F2A37",
           caption="5B6670", footer="5B6670", accent="6B4FBB", stat="1D3F8C",
           highlight_bg="E4EAF5", warning_bg="F2EAF8",
           table_hdr_bg="1D3F8C", table_hdr_text="FFFFFF", zebra="EEF1F7"),
    # ---- Family D: marketing-deck vocabulary ----
    _theme("metric_first",
           "Dashboard-like: white, headline, purple big numerals (stat_big 54 pt), gray tiles; result-summary or impact-number slides.",
           "headline", "FFFFFF", None, plate="F4F4F4", extra_sizes=(STAT_BIG_PT,), family="marketing", provenance="described",
           flat_note="flat variant: tile grid and micro-charts are layout work, only the palette and big-number role are in the theme",
           title_bar_text="161616", title_main="161616", subtitle="6929C4", body="161616",
           caption="525252", footer="525252", accent="002D9C", stat="6929C4",
           highlight_bg="F4F4F4", warning_bg="FFE0E1",
           table_hdr_bg="161616", table_hdr_text="FFFFFF", zebra="F4F4F4"),
    # ---- Family E: Korean-market STYLE vocabularies (slide body stays English, Arial) ----
    _theme("korean_gov_report",
           "Formal report-deck style: navy title bar, dark-red emphasis, dense and itemised; agency progress report or evaluation talk.",
           "bar", "FFFFFF", "1F3864", family="korean", provenance="described",
           flat_note="flat variant: no key-message box under the bar, no box-numbered caption; style vocabulary only",
           title_bar_text="FFFFFF", title_main="1F3864", subtitle="1F3864", body="1A1A1A",
           caption="595959", footer="595959", accent="C00000", stat="C00000",
           highlight_bg="E9EDF5", warning_bg="FBE3E3",
           table_hdr_bg="1F3864", table_hdr_text="FFFFFF", zebra="E9EDF5",
           extra_hex=("D9D9D9",)),
    _theme("korea_univ_crimson",
           "University-formal: white, crimson rule and emphasis (approximate hex, not an official CI value); internal seminar or thesis defense.",
           "rule", "FFFFFF", None, rule_color="8B2332", family="korean", provenance="unverified",
           flat_note="flat variant: no affiliation footer text; crimson #8B2332 is a screen approximation",
           title_bar_text="222222", title_main="222222", subtitle="8B2332", body="222222",
           caption="6B6B6B", footer="6B6B6B", accent="8B2332", stat="8B2332",
           highlight_bg="F4EFEA", warning_bg="F6DADD",
           table_hdr_bg="8B2332", table_hdr_text="FFFFFF", zebra="F4EFEA",
           extra_hex=("1F2A44", "E5E1DC")),
    _theme("miri_beige_navy",
           "Soft modern beige and navy with orange rule and teal emphasis; mentoring talk, lab meeting or outreach (figures on a white plate).",
           "rule", "F5F0E6", None, rule_color="C2410C", plate="FFFFFF", family="korean", provenance="described",
           flat_note="flat variant: no numbered section chip, no rounded plates (plain rectangles)",
           title_bar_text="1B2A41", title_main="1B2A41", subtitle="0F766E", body="1B2A41",
           caption="5B6370", footer="5B6370", accent="C2410C", stat="C2410C",
           highlight_bg="E3EEEC", warning_bg="F6DCCF",
           table_hdr_bg="1B2A41", table_hdr_text="FFFFFF", zebra="EBE3D3",
           extra_hex=("D9D2C3",)),
    # ---- Family D: palettes measured from real downloaded templates (study only; no assets copied) ----
    _theme("ucsd_navy_yellow",
           "Palette measured from the MIT-licensed UCSD defense template (gh_ucsd_defense, x3zou/UCSD_Defense_Template): "
           "white page, navy #182B49 type, yellow #FFCD00 rule (fill/rule only, never text), pale #E7EEF3 panels; "
           "thesis defense or chapter-structured seminar.",
           "rule", "FFFFFF", None, rule_color="FFCD00", family="research", provenance="measured",
           flat_note="flat variant: no institutional logos, hero photo or greyed chapter text; navy and yellow measured "
                     "from the template slides, text tints and the #FBEFD2 warning tint are derived for 4.5:1",
           title_bar_text="182B49", title_main="182B49", subtitle="2F4B73", body="1A1A1A",
           caption="566270", footer="566270", accent="FFCD00", stat="182B49",
           highlight_bg="E7EEF3", warning_bg="FBEFD2",
           table_hdr_bg="182B49", table_hdr_text="FFFFFF", zebra="E7EEF3",
           extra_hex=("A0AAB3",)),
    _theme("k105_navy",
           "Palette measured from the MIT-licensed lab group-meeting template k105-blue (gh_k105_reference, "
           "SciToolsmith/journal-club-ppt; origin of the design not stated): white page, slate navy #32497B, grey cards, "
           "steel-blue fill; journal-club decks.",
           "rule", "FFFFFF", None, rule_color="32497B", family="research", provenance="measured",
           flat_note="flat variant: no gradients, drop shadows, triangle title marker art or Chinese-typeface look; "
                     "#5B9BD5 is fill-only (2.96:1 on white), the #FFF2CC warning tint is derived",
           title_bar_text="32497B", title_main="32497B", subtitle="44546A", body="262626",
           caption="595959", footer="595959", accent="5B9BD5", stat="32497B",
           highlight_bg="E8EAEC", warning_bg="FFF2CC",
           table_hdr_bg="32497B", table_hdr_text="FFFFFF", zebra="F5F6F6",
           extra_hex=("D9D9D9",)),
    _theme("mono_bw_hard",
           "Hard black on off-white #F2F1EC, idea taken from the SlidesMania black-and-white template "
           "(sm_black-and-white, personal-use licence: palette idea and structure only, no asset reused): "
           "black title bars, outlined white boxes, grey #6C6B68 secondary; dividers and big-number talks.",
           "bar", "F2F1EC", "000000", plate="FFFFFF", family="research", provenance="measured",
           flat_note="flat variant: no photographs, quote-mark artwork or SLIDESMANIA side text; grays measured from the "
                     "template theme, nothing else added",
           title_bar_text="FFFFFF", title_main="000000", subtitle="1C1B1A", body="1C1B1A",
           caption="6C6B68", footer="6C6B68", accent="6C6B68", stat="000000",
           highlight_bg="FFFFFF", warning_bg="CDCCCA",
           table_hdr_bg="000000", table_hdr_text="FFFFFF", zebra="EEEEEE",
           extra_hex=("A5A4A2", "CDCCCA")),
)}

# Legacy export: the navy_lab palette as a hex set.
ALLOWED_HEX = set(THEMES[DEFAULT_THEME].allowed_hex)


def get_theme(theme) -> Theme:
    if isinstance(theme, Theme):
        return theme
    if theme not in THEMES:
        raise StyleError(f"Unknown theme {theme!r}; choose one of {sorted(THEMES)}")
    return THEMES[theme]


def list_themes() -> list[dict]:
    """[{name, family, provenance, description, header_style}] for every registered theme, registry order."""
    return [dict(name=t.name, family=t.family, provenance=t.provenance, description=t.description,
                 header_style=t.header_style) for t in THEMES.values()]


def contrast_pairs(theme) -> list:
    """[(role, fg_hex, bg_hex, ratio, required, ok)] for every text role x background."""
    th = get_theme(theme)
    out = []
    for role, spec in ROLES.items():
        fg = th.role_color(role)
        for bg in th.role_backgrounds(role):
            ratio = contrast_ratio(fg, bg)
            need = required_contrast(spec["pt"], spec["bold"])
            out.append((role, str(fg), str(bg), ratio, need, ratio >= need))
    return out


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


def _set_cell_borders(cell, rgb: RGBColor, width_pt: float = 1.0) -> None:
    """Explicit 4-side cell border in `rgb` (the table style's default is white, which
    glares on a dark theme). Border elements must precede the fill inside a:tcPr."""
    tcPr = cell._tc.get_or_add_tcPr()
    for tag in ("a:lnL", "a:lnR", "a:lnT", "a:lnB"):
        for old in tcPr.findall(qn(tag)):
            tcPr.remove(old)
    for i, tag in enumerate(("a:lnL", "a:lnR", "a:lnT", "a:lnB")):
        ln = etree.Element(qn(tag), w=str(int(Pt(width_pt))), cap="flat", cmpd="sng", algn="ctr")
        fill = etree.SubElement(ln, qn("a:solidFill"))
        etree.SubElement(fill, qn("a:srgbClr"), val=str(rgb))
        etree.SubElement(ln, qn("a:prstDash"), val="solid")
        tcPr.insert(i, ln)


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

PREFS_DIR = Path(__file__).resolve().parents[1] / "references" / "prefs"
PREFS_KEYWORD_PREFIX = "journal-ppt-prefs:"


def load_prefs(name) -> dict:
    """Presenter preference preset (references/prefs/<name>.json); a dict passes through, None -> {}."""
    if not name:
        return {}
    if isinstance(name, dict):
        return name
    import json
    f = PREFS_DIR / f"{name}.json"
    if not f.exists():
        raise StyleError(f"unknown prefs preset {name!r}; available: {sorted(x.stem for x in PREFS_DIR.glob('*.json'))}")
    return json.loads(f.read_text(encoding="utf-8"))


class Deck:
    """Owns the Presentation object, slide numbering, footer text and theme."""

    def __init__(self, footer_right: str = "", theme="navy_lab", prefs=None):
        self.prefs = load_prefs(prefs)
        self.theme = get_theme(theme)
        self.prs = Presentation()
        self.prs.slide_width = SLIDE_W
        self.prs.slide_height = SLIDE_H
        self.prs.core_properties.keywords = THEME_KEYWORD_PREFIX + self.theme.name
        if self.prefs.get("name"):
            self.prs.core_properties.category = PREFS_KEYWORD_PREFIX + self.prefs["name"]
        self._slide_num = 0
        self.footer_right = footer_right

    # -- low level -----------------------------------------------------

    def _blank(self):
        return self.prs.slide_layouts[6]

    def new_slide(self):
        slide = self.prs.slides.add_slide(self._blank())
        bg = slide.background
        bg.fill.solid()
        bg.fill.fore_color.rgb = self.theme.bg
        return slide

    def _next_num(self) -> int:
        self._slide_num += 1
        return self._slide_num

    def _spec(self, role: str) -> dict:
        """ROLES[role] with the color resolved through the active theme; also
        rejects a role whose size the theme does not allow (stat_big)."""
        spec = dict(_validate_role(role))
        if (spec["pt"] == STAT_BIG_PT and STAT_BIG_PT not in self.theme.extra_sizes
                and STAT_BIG_PT not in getattr(self, "_layout_sizes", ())):
            raise StyleError(f"role {role!r} ({STAT_BIG_PT} pt) is only allowed in themes that declare it in "
                             f"extra_sizes or inside a layout that declares it; active theme: {self.theme.name}")
        spec["color"] = self.theme.role_color(role)
        return spec

    def _autoshape(self, slide, left, top, width, height, rgb, name=None, no_shadow=False):
        """Decoration rectangle. python-pptx still creates an implicit text_frame on
        any autoshape, so it gets the same disable_autofit()/word_wrap treatment
        or QC-2 flags it."""
        shp = slide.shapes.add_shape(1, left, top, width, height)
        shp.fill.solid()
        shp.fill.fore_color.rgb = rgb
        shp.line.fill.background()
        shp.text_frame.word_wrap = True
        disable_autofit(shp.text_frame)
        if no_shadow:
            shp.shadow.inherit = False   # new decoration shapes (rule, plate) carry no theme shadow
        if name:
            shp.name = name
        return shp

    # -- text primitives -------------------------------------------------

    def add_textbox(self, slide, left, top, width, height, text: str, role: str,
                     align=PP_ALIGN.LEFT, word_wrap: bool = True,
                     line_spacing: float | None = None,
                     space_after: float | None = None):
        """Add a single-paragraph textbox styled entirely from `role`.
        Returns the textbox shape. This is the core building block every
        higher-level helper (bullets/caption/table_cell/...) funnels through,
        so disable_autofit() + set_line_spacing() can never be forgotten."""
        spec = self._spec(role)
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
        run.font.name = self.theme.font
        run.font.size = Pt(spec["pt"])
        run.font.bold = spec["bold"]
        run.font.italic = spec["italic"]
        run.font.color.rgb = spec["color"]
        return txb

    def bullets(self, slide, items: list[str], role: str = "body",
                left=None, top=None, width=None, height=None,
                bullet_char: str = "\u2022 ", last_space_after: float = 0):
        """Add a multi-paragraph bulleted textbox. role must be 'body' or
        'sidebar_bullet' (or any role present in LINE_SPACING/SPACE_AFTER).
        Themes with allow_bullets=False (assertion_evidence) reject this call."""
        if not self.theme.allow_bullets:
            raise StyleError(f"theme {self.theme.name!r} forbids bullet lists "
                             f"(assertion-evidence: headline + one figure only)")
        return self._bullets(slide, items, role, left, top, width, height,
                             bullet_char, last_space_after)

    def _bullets(self, slide, items, role="body", left=None, top=None, width=None,
                 height=None, bullet_char="\u2022 ", last_space_after=0):
        spec = self._spec(role)
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
            run.font.name = self.theme.font
            run.font.size = Pt(spec["pt"])
            run.font.bold = spec["bold"]
            run.font.italic = spec["italic"]
            run.font.color.rgb = spec["color"]
        return txb

    # -- slide-level helpers ----------------------------------------------

    def title_slide(self, title: str, citation: str, journal_line: str,
                     presenter: str, date: str, kicker: str | None = None):
        """No header bar; large centered title + accent line + citation. `kicker` (or the prefs
        title_slide.kicker) adds the small top-left label ("JOURNAL CLUB | date") with a hairline."""
        slide = self.new_slide()
        kicker = kicker or (self.prefs.get("title_slide") or {}).get("kicker")
        if kicker:
            self._kicker(slide, kicker.format(date=date))

        self.add_textbox(slide, Inches(1.0), Inches(2.0), SLIDE_W - Inches(2.0),
                          Inches(1.6), title, role="title_main",
                          align=PP_ALIGN.CENTER)

        # accent divider (a pure decoration)
        self._autoshape(slide, Inches(4.665), Inches(3.65), Inches(4.0), Pt(2.5),
                        self.theme.palette["accent"], name="accent_line")

        self.add_textbox(slide, Inches(1.0), Inches(3.85), SLIDE_W - Inches(2.0),
                          Inches(0.5), citation, role="fig_subtitle",
                          align=PP_ALIGN.CENTER)
        self.add_textbox(slide, Inches(1.0), Inches(4.4), SLIDE_W - Inches(2.0),
                          Inches(0.5), journal_line, role="presenter",
                          align=PP_ALIGN.CENTER)
        self.add_textbox(slide, Inches(1.0), Inches(5.2), SLIDE_W - Inches(2.0),
                          Inches(0.5), f"Presenter: {presenter}    |    {date}",
                          role="presenter", align=PP_ALIGN.CENTER)
        self._next_num()
        return slide

    def content_slide(self, title: str, plain: bool = True):
        """Standard content slide; the header depends on the theme's header_style:
        bar/dark = filled bar with white title, headline = sentence title on the
        plain background, rule = title plus a thin accent rule."""
        slide = self.new_slide()
        style = self.theme.header_style
        left_in = HEADER_TITLE_LEFT_PLAIN if plain else HEADER_TITLE_LEFT_FIG
        top_in = HEADER_TITLE_TOP_PLAIN if plain else HEADER_TITLE_TOP_FIG

        if style == "sidebar":
            self._autoshape(slide, 0, 0, SIDEBAR_W, SLIDE_H, self.theme.header_bg,
                            name="deco:sidebar", no_shadow=True)
            self.add_textbox(slide, left_in, Inches(0.15), SLIDE_W - left_in - MARGIN,
                             Inches(0.9), title, role="title_bar")
        elif style == "none":
            pass   # no header at all: the title is not drawn (use for full-bleed figure slides)
        elif style == "bar":
            bar = slide.shapes.add_shape(1, Inches(0), Inches(0), SLIDE_W, HEADER_BAR_H)
            bar.fill.solid()
            bar.fill.fore_color.rgb = self.theme.header_bg
            bar.line.fill.background()
            bar.name = "header_bar"
            tf = bar.text_frame
            tf.word_wrap = True
            disable_autofit(tf)
            tf.margin_left = left_in
            tf.margin_top = top_in
            p = tf.paragraphs[0]
            p.alignment = PP_ALIGN.LEFT
            set_line_spacing(p, LINE_SPACING["title_bar"])
            p.space_after = Pt(SPACE_AFTER["title_bar"])
            run = p.add_run()
            run.text = title
            spec = self._spec("title_bar")
            run.font.name = self.theme.font
            run.font.size = Pt(spec["pt"])
            run.font.bold = spec["bold"]
            run.font.color.rgb = spec["color"]
        else:
            # headline / rule: the title is a plain textbox on the slide background
            tb = self.add_textbox(slide, left_in, Inches(0.15), SLIDE_W - left_in - MARGIN,
                                   Inches(0.9), title, role="title_bar")
            if style == "rule":   # sit the title on its rule
                tb.text_frame.vertical_anchor = MSO_ANCHOR.BOTTOM
            if style == "rule":
                self._autoshape(slide, left_in, Inches(1.08), SLIDE_W - left_in - MARGIN,
                                Pt(2.25), self.theme.rule_color, name="title_rule", no_shadow=True)

        num = self._next_num()
        self._footer(slide, num)
        return slide

    # -- figure geometry -------------------------------------------------

    def key_points_height(self, items: list[str], width_in: float | None = None) -> int:
        """Height (EMU) of a sidebar-bullet box: wrapped lines x line height at the
        active spacing + space_after between items + box padding."""
        if width_in is None:
            width_in = (SLIDE_W - 2 * HEADER_TITLE_LEFT_FIG) / 914400 - 0.2
        total_pt = 0.0
        for text in items:
            n = self.fit_check("\u2022 " + text, "sidebar_bullet", width_in)["lines"]
            total_pt += n * 14 * LINE_HEIGHT_FACTOR * LINE_SPACING["sidebar_bullet"]
        total_pt += SPACE_AFTER["sidebar_bullet"] * max(0, len(items) - 1)
        return int(Pt(total_pt)) + BOX_PAD

    def figure_slide(self, title: str, subtitle: str, key_points: list[str],
                      fig_path: str, caption_text: str):
        """Figure-first slide following the Figure-First Layout rules. The figure
        top is derived from the real wrapped height of the bullets (2.0 spacing)
        and add_figure() refuses a layout that leaves less than MIN_FIG_H."""
        if key_points and not self.theme.allow_bullets:
            raise StyleError(f"theme {self.theme.name!r}: figure_slide takes no key_points "
                             f"(assertion-evidence); put the claim in the headline")
        if self.theme.header_style == "headline" and not self.theme.allow_bullets and len(title.split()) < 4:
            raise StyleError("assertion_evidence headline must be a full sentence (>=4 words): "
                             f"{title!r}")
        slide = self.content_slide(title, plain=False)

        if subtitle:
            self.add_textbox(slide, HEADER_TITLE_LEFT_FIG, FIG_SUBTITLE_TOP,
                              SLIDE_W - 2 * HEADER_TITLE_LEFT_FIG, FIG_SUBTITLE_H,
                              subtitle, role="fig_subtitle")

        if key_points:
            pts = key_points[:3]
            box_h = self.key_points_height(pts)
            self.bullets(slide, pts, role="sidebar_bullet",
                         left=HEADER_TITLE_LEFT_FIG, top=KEY_POINT_TOP,
                         width=SLIDE_W - 2 * HEADER_TITLE_LEFT_FIG,
                         height=box_h)
            fig_top = KEY_POINT_TOP + box_h + Inches(0.05)
        elif subtitle:
            fig_top = FIG_SUBTITLE_TOP + FIG_SUBTITLE_H + Inches(0.05)
        else:
            fig_top = FIG_TOP_NO_POINTS

        anchor = self.add_figure(slide, fig_path, top=fig_top)
        if caption_text:
            self.caption(slide, caption_text, anchor)
        return slide

    def add_figure(self, slide, fig_path: str, top=FIG_TOP_WITH_POINTS,
                    left=None, max_width=None, max_height=None, name: str | None = None):
        """Insert a picture centered horizontally, preserving aspect ratio and
        staying above Y_FLOOR (caption box reserved). With a theme plate the
        picture sits on a light rectangle. Returns the OUTER box
        (left, top, w, h) -- plate if any -- so the caller can anchor a caption."""
        if PILImage is None:
            raise RuntimeError("Pillow is required for add_figure()")
        with PILImage.open(fig_path) as img:
            orig_w, orig_h = img.size

        pad = PLATE_PAD if self.theme.plate is not None else 0
        auto_h = max_height is None
        if max_width is None:
            max_width = SLIDE_W - Inches(0.6) - 2 * pad
        if max_height is None:
            max_height = Y_FLOOR - self.theme.caption_h - CAPTION_GAP - top - 2 * pad
        if auto_h and max_height < MIN_FIG_H:
            raise StyleError(
                f"figure area is only {max_height / 914400:.2f} in tall (< {MIN_FIG_H / 914400:.1f} in): "
                f"reduce key points / subtitle / caption length ({self.theme.name})")

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
        if pad:
            self._autoshape(slide, left - pad, top, fig_w + 2 * pad, fig_h + 2 * pad,
                            self.theme.plate, name="plate", no_shadow=True)
        pic = slide.shapes.add_picture(fig_path, left, top + pad, fig_w, fig_h)
        if name:
            pic.name = name
        return (left - pad, top, fig_w + 2 * pad, fig_h + 2 * pad)

    def add_figure_row(self, slide, fig_paths: list[str], top, name_prefix: str = "fig"):
        """Place 1-3 figures side by side in equal slots (reaction structures, prior-work
        panels). Each is fitted into its slot (aspect preserved), vertically top-aligned.
        Returns the bounding box (left, top, w, h) of the whole row for the caption."""
        n = len(fig_paths)
        if not 1 <= n <= 3:
            raise StyleError("a figure row takes 1-3 figures (each must stay >= 3 in wide)")
        pad = PLATE_PAD if self.theme.plate is not None else 0
        gap = Inches(0.3)
        usable_w = SLIDE_W - 2 * MARGIN
        slot_w = int((usable_w - gap * (n - 1)) / n)
        max_h = Y_FLOOR - self.theme.caption_h - CAPTION_GAP - top - 2 * pad
        if max_h < MIN_FIG_H:
            raise StyleError("figure row: caption box leaves < 3 in for the figures")
        placed = []
        for i, path in enumerate(fig_paths):
            with PILImage.open(path) as im:
                iw, ih = im.size
            s = min((slot_w - 2 * pad) / iw, max_h / ih)
            w, h = int(iw * s), int(ih * s)
            if max(w, h) < MIN_FIG_H:
                raise StyleError(f"figure {Path(path).name} would be < 3 in at slot width "
                                 f"{slot_w / 914400:.1f} in; use fewer figures per row")
            slot_left = MARGIN + i * (slot_w + gap)
            left = int(slot_left + (slot_w - w) / 2)
            if pad:
                self._autoshape(slide, left - pad, top, w + 2 * pad, h + 2 * pad,
                                self.theme.plate, name="plate", no_shadow=True)
            pic = slide.shapes.add_picture(path, left, top + pad, w, h)
            pic.name = f"{name_prefix}:{Path(path).stem}"
            placed.append((left - pad, top, w + 2 * pad, h + 2 * pad))
        x0 = min(b[0] for b in placed)
        x1 = max(b[0] + b[2] for b in placed)
        y1 = max(b[1] + b[3] for b in placed)
        return (x0, top, x1 - x0, y1 - top)

    def caption(self, slide, text: str, anchor):
        """anchor = (left, top, w, h) tuple from add_figure()/add_figure_row().
        With a prefs preset the caption is plain (not italic, not bold), centered, at the preset size."""
        left, top, w, h = anchor
        cap_top = top + h + CAPTION_GAP
        lines = text.split("\n")
        cp = self.prefs.get("caption") or {}
        plain = bool(cp)
        cap_h = Inches(0.62) if (plain and len(lines) > 1) else self.theme.caption_h
        cap_h = min(cap_h, max(Inches(0.3), Y_FLOOR - cap_top))
        cap_box = slide.shapes.add_textbox(MARGIN, cap_top, SLIDE_W - 2 * MARGIN, cap_h)
        tf = cap_box.text_frame
        tf.word_wrap = True
        disable_autofit(tf)
        spec = self._spec("caption")
        for i, line in enumerate(lines):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            set_line_spacing(p, LINE_SPACING["caption"])
            p.space_after = Pt(SPACE_AFTER["caption"] if i < len(lines) - 1 else 0)
            if plain and cp.get("align", "center") == "center":
                p.alignment = PP_ALIGN.CENTER
            run = p.add_run()
            run.text = line
            run.font.name = self.theme.font
            run.font.size = Pt(cp.get("pt", spec["pt"]) if plain else spec["pt"])
            run.font.italic = cp.get("italic", True) if plain else True
            run.font.color.rgb = spec["color"]
            if "et al." in line and not plain:
                run.font.bold = True
                run.font.color.rgb = self.theme.palette["body"]
        return cap_box

    # -- lab-standard slides (memory S3 / S4) -------------------------------

    def reactions_slide(self, title: str, fig_paths: list[str], caption_text: str):
        """S3: reaction structures taken from the paper's own figures (Fig 1 / Scheme 1
        crops), ZERO bullets. Intended directly after Background, before Approach/Methods.
        Pictures are named 'reaction:<stem>' so qc_deck.py can see the slide exists."""
        slide = self.content_slide(title, plain=True)
        anchor = self.add_figure_row(slide, fig_paths, top=BODY_TOP_NO_FIGURE,
                                     name_prefix="reaction")
        if caption_text:
            self.caption(slide, caption_text, anchor)
        return slide

    def prior_work_slide(self, title: str, fig_path: str, caption_text: str,
                         note: str | None = None):
        """S4: comparison with prior work = the source figure embedded, NEVER a bullet
        list of numbers. `note` is one optional line (fig_subtitle role) under the
        title. Picture is named 'prior:<stem>'."""
        slide = self.content_slide(title, plain=True)
        if note:
            self.add_textbox(slide, HEADER_TITLE_LEFT_FIG, FIG_SUBTITLE_TOP,
                              SLIDE_W - 2 * HEADER_TITLE_LEFT_FIG, FIG_SUBTITLE_H,
                              note, role="fig_subtitle")
            top = FIG_SUBTITLE_TOP + FIG_SUBTITLE_H + Inches(0.05)
        else:
            top = FIG_TOP_NO_POINTS
        anchor = self.add_figure(slide, fig_path, top=top,
                                 name="prior:" + Path(fig_path).stem)
        if caption_text:
            self.caption(slide, caption_text, anchor)
        return slide

    def stat_slide(self, title: str, number: str, meaning: str, comparator: str | None = None):
        """One large number (stat_big, 54 pt) + a one-line meaning (+ optional comparator).
        Only themes that list 54 in extra_sizes (mono_one, swiss_grid, metric_first)."""
        self._spec("stat_big")   # raises StyleError outside mono_one
        slide = self.content_slide(title, plain=True)
        w = SLIDE_W - 2 * MARGIN
        self.add_textbox(slide, MARGIN, Inches(2.0), w, Inches(1.4), number,
                         role="stat_big", align=PP_ALIGN.CENTER)
        self.add_textbox(slide, MARGIN, Inches(3.5), w, Inches(0.6), meaning,
                         role="subtitle", align=PP_ALIGN.CENTER)
        if comparator:
            self.add_textbox(slide, MARGIN, Inches(4.3), w, Inches(0.9), comparator,
                             role="body", align=PP_ALIGN.CENTER)
        return slide

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
            a wide wordmark) still read as one consistent row. Get logos via
            `logo_fetch.fetch_institution_logo()` -- do not hand-roll a
            second download path. (logo_fetch.py is not committed yet as of
            2026-10-02; until it is, pass PNGs you saved yourself.)
        corresponding: optional "Name (email)" line, rendered dimmer below
            the affiliation bullets.

        Place it right after title_slide() in the paper-mode slide order
        ("Title -> Authors & Affiliations -> Background -> ...").
        """
        slide = self.content_slide("Authors & affiliations", plain=True)

        body_top = BODY_TOP_NO_FIGURE
        body = self._bullets(slide, [authors_line], role="body",
                             top=body_top, height=Inches(0.9))
        # re-flow: authors_line is one paragraph at body role, not a bullet list
        for para in body.text_frame.paragraphs:
            for run in para.runs:
                if run.text.startswith("• "):
                    run.text = run.text[2:]

        aff_lines = [f"{inst} — {members}" for inst, members in affiliations]
        if corresponding:
            aff_lines.append(corresponding)
        self._bullets(slide, aff_lines, role="sidebar_bullet",
                      top=body_top + Inches(1.0), height=Inches(1.6))

        if logos:
            self._logo_row(slide, logos, band_top=Inches(4.75), band_h=Inches(1.2))

        return slide

    def _logo_row(self, slide, logos: list[tuple[str, str]], band_top, band_h):
        """Lay out logos evenly across the slide width, each centered within
        a COMMON bounding box (band_h tall, ~82% of its column wide) so
        aspect-ratio outliers (a 7:1 wordmark next to a near-square crest)
        still align on one visual row instead of producing wildly different
        logo heights. Adds a caption label under each logo at 'footer' role.
        On a themed plate (dark_seminar) each logo sits on its own light plate.

        This is the exact pattern validated on the IRED journal-club deck
        (260912): constrain by both max width and max height, take whichever
        binds.
        """
        if PILImage is None:
            raise RuntimeError("Pillow is required for _logo_row()")
        n = len(logos)
        margin = MARGIN
        usable_w = SLIDE_W - 2 * margin
        slot_w = int(usable_w / n)
        pad = Inches(0.08) if self.theme.plate is not None else 0

        for i, (path, label) in enumerate(logos):
            with PILImage.open(path) as im:
                iw, ih = im.size
            aspect = iw / ih
            max_w = int(slot_w * 0.82) - 2 * pad
            max_h = band_h - 2 * pad
            w_c = max_w
            h_c = int(w_c / aspect)
            if h_c > max_h:
                h_c = max_h
                w_c = int(h_c * aspect)

            slot_left = margin + i * slot_w
            pic_left = int(slot_left + (slot_w - w_c) / 2)
            pic_top = int(band_top + (band_h - h_c) / 2)
            if pad:
                self._autoshape(slide, pic_left - pad, pic_top - pad, w_c + 2 * pad,
                                h_c + 2 * pad, self.theme.plate, name="plate", no_shadow=True)
            pic = slide.shapes.add_picture(path, pic_left, pic_top, w_c, h_c)
            # Marker consumed by qc_deck.py's QC-11 exemption (logo != results figure).
            pic.name = "logo:" + Path(path).stem

            if label:
                self.add_textbox(slide, slot_left, band_top + band_h + Inches(0.16),
                                  slot_w, Inches(0.3), label, role="footer",
                                  align=PP_ALIGN.CENTER)

    def table_slide(self, title: str, headers: list[str], rows: list[list[str]]):
        slide = self.content_slide(title, plain=True)
        pal = self.theme.palette
        n_cols = len(headers)
        n_rows = len(rows) + 1
        top = BODY_TOP_NO_FIGURE
        avail_h = min(Y_FLOOR - top, Inches(0.4) * n_rows + Inches(0.3))
        table = slide.shapes.add_table(n_rows, n_cols, MARGIN, top,
                                        SLIDE_W - 2 * MARGIN, avail_h).table
        col_w = int((SLIDE_W - 2 * MARGIN) / n_cols)
        for ci in range(n_cols):
            table.columns[ci].width = col_w

        hdr_spec = self._spec("table_header")
        for ci, hdr in enumerate(headers):
            cell = table.cell(0, ci)
            cell.fill.solid()
            cell.fill.fore_color.rgb = pal["table_hdr_bg"]
            _set_cell_borders(cell, self.theme.bg)
            tf = cell.text_frame
            disable_autofit(tf)
            p = tf.paragraphs[0]
            p.alignment = PP_ALIGN.CENTER
            set_line_spacing(p, LINE_SPACING["table_header"])
            p.space_after = Pt(SPACE_AFTER["table_header"])
            run = p.add_run()
            run.text = hdr
            run.font.name = self.theme.font
            run.font.size = Pt(hdr_spec["pt"])
            run.font.bold = True
            run.font.color.rgb = hdr_spec["color"]

        cell_spec = self._spec("table_cell")
        for ri, row in enumerate(rows):
            zebra = pal["zebra"] if ri % 2 == 0 else self.theme.bg
            for ci, val in enumerate(row):
                cell = table.cell(ri + 1, ci)
                cell.fill.solid()
                cell.fill.fore_color.rgb = zebra
                _set_cell_borders(cell, self.theme.bg)
                tf = cell.text_frame
                disable_autofit(tf)
                p = tf.paragraphs[0]
                p.alignment = PP_ALIGN.LEFT
                set_line_spacing(p, LINE_SPACING["table_cell"])
                p.space_after = Pt(SPACE_AFTER["table_cell"])
                run = p.add_run()
                run.text = str(val)
                run.font.name = self.theme.font
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
        spec = self._spec("reference")
        for i, ref in enumerate(refs):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            set_line_spacing(p, LINE_SPACING["reference"])
            p.space_after = Pt(SPACE_AFTER["reference"] if i < len(refs) - 1 else 0)
            run = p.add_run()
            run.text = f"[{i + 1}] {ref}"
            run.font.name = self.theme.font
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

    def name_shape(self, shape, name: str):
        """Give a shape a stable name. Morph matches objects between two slides by name
        (a leading '!!' forces the match), so the same object must carry the same name on both."""
        shape.name = name if name.startswith("!!") else "!!" + name
        return shape

    def morph(self, slide, option: str = "byObject", dur_ms: int = 1500):
        """Set a PowerPoint Morph transition ON this slide (it animates FROM the previous slide).
        python-pptx has no API for it, so the p159:morph element is written as XML inside an
        mc:AlternateContent block with a fade fallback for viewers without Morph. Verified
        2026-10-04: PowerPoint 16 reads the transition (EntryEffect set, duration 1.5 s) and
        keeps the element on re-save. Playback itself is not testable headless.
        option: byObject | byWord | byChar. Charts and tables do not morph."""
        if option not in ("byObject", "byWord", "byChar"):
            raise StyleError(f"unknown morph option {option!r}")
        if not (300 <= int(dur_ms) <= 5000):
            raise StyleError("morph duration must be 300-5000 ms")
        ns_p = "http://schemas.openxmlformats.org/presentationml/2006/main"
        ns_mc = "http://schemas.openxmlformats.org/markup-compatibility/2006"
        ns_159 = "http://schemas.microsoft.com/office/powerpoint/2015/09/main"
        ns_14 = "http://schemas.microsoft.com/office/powerpoint/2010/main"
        el = slide._element
        for old in el.findall("{%s}AlternateContent" % ns_mc) + el.findall("{%s}transition" % ns_p):
            el.remove(old)
        xml = (f'<mc:AlternateContent xmlns:mc="{ns_mc}" xmlns:p="{ns_p}" xmlns:p159="{ns_159}" xmlns:p14="{ns_14}">'
               f'<mc:Choice Requires="p159"><p:transition spd="slow" p14:dur="{int(dur_ms)}">'
               f'<p159:morph option="{option}"/></p:transition></mc:Choice>'
               f'<mc:Fallback><p:transition spd="slow"><p:fade/></p:transition></mc:Fallback></mc:AlternateContent>')
        anchor = el.find("{%s}clrMapOvr" % ns_p)
        if anchor is None:
            anchor = el.find("{%s}cSld" % ns_p)
        anchor.addnext(etree.fromstring(xml))
        return slide

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
        toolkit per style_spec.md §7). height_in = lines x pt x 1.2 (Arial line
        height) x the role's line spacing, i.e. it already includes the 2.0 factor."""
        if PILImage is None:
            raise RuntimeError("Pillow is required for fit_check()")
        from PIL import ImageFont
        spec = _validate_role(role)
        pt = spec["pt"]
        px_size = int(pt * 96 / 72)
        width_px = width_in * 96
        try:
            font = ImageFont.truetype(font_path, px_size)
            measure = lambda s: font.getbbox(s)[2] - font.getbbox(s)[0]
        except OSError:  # no Arial (non-Windows): average Arial glyph ~0.5 em
            measure = lambda s: len(s) * px_size * 0.5

        words = text.split()
        lines = []
        cur = ""
        for w in words:
            trial = (cur + " " + w).strip()
            if measure(trial) <= width_px or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)

        line_h_pt = pt * LINE_HEIGHT_FACTOR * LINE_SPACING.get(role, 1.0)
        n_lines = max(1, len(lines))
        height_in = (n_lines * line_h_pt) / 72.0
        return {"lines": n_lines, "height_in": height_in, "width_in": width_in}

    def layout(self, name: str, **content):
        """Build a slide with a registered layout (see scripts/layouts/__init__.py).
        Records the layout name so qc_deck can allow the extra sizes it declared."""
        from layouts import LAYOUTS, load_all
        load_all()
        if name not in LAYOUTS:
            raise StyleError(f"unknown layout {name!r}; available: {sorted(LAYOUTS)}")
        spec = LAYOUTS[name]
        if not hasattr(self, "_layouts_used"):
            self._layouts_used = set()
        self._layouts_used.add(name)
        self._layout_sizes = set(spec.extra_sizes)      # sizes this layout declared, valid only while it builds
        try:
            return spec.fn(self, **content)
        finally:
            self._layout_sizes = set()

    # -- journal-club structure (prefs preset; 261004 measured preferences) --------------------

    def _hairline(self, slide, left, top, width):
        return self._autoshape(slide, left, top, width, Pt(1), self.theme.palette["caption"],
                               name="deco:hairline", no_shadow=True)

    def _kicker(self, slide, text: str):
        self.add_textbox(slide, CLUB_MARGIN, Inches(0.45), SLIDE_W - 2 * CLUB_MARGIN, Inches(0.5), text, role="subtitle")
        self._hairline(slide, CLUB_MARGIN, Inches(1.05), SLIDE_W - 2 * CLUB_MARGIN)

    def conclusions_slide(self, takeaway: str, columns: list[tuple[str, str, bool]], title: str = "Conclusions"):
        """Journal-club summary slide: one takeaway line + 2-3 hairline columns (head, text, emphasized).
        Goes right before the references slide."""
        if not 2 <= len(columns) <= 3:
            raise StyleError("conclusions_slide takes 2 or 3 columns")
        slide = self.content_slide(title)
        w = SLIDE_W - 2 * CLUB_MARGIN
        self.add_textbox(slide, CLUB_MARGIN, Inches(1.2), w, Inches(0.5), takeaway, role="subtitle")
        cw = int(w / len(columns))
        for i, (head, text, hot) in enumerate(columns):
            x = CLUB_MARGIN + i * cw
            self._hairline(slide, x, Inches(2.0), cw - Inches(0.35))
            h = self.add_textbox(slide, x, Inches(2.1), cw - Inches(0.45), Inches(0.5), head, role="subtitle")
            if not hot:
                for r in h.text_frame.paragraphs[0].runs:
                    r.font.color.rgb = self.theme.palette["body"]
            self.bullets(slide, [text], role="body", left=x, top=Inches(2.75), width=cw - Inches(0.45),
                         height=Inches(3.9), bullet_char="")
        return slide

    def closing_slide(self, headline: str | None = None, subline: str | None = None):
        """Thank-you slide, nothing else (layout 'thank_you': 54 pt headline declared on the layout, any theme)."""
        cp = self.prefs.get("closing") or {}
        return self.layout("thank_you", headline=headline or cp.get("headline", "Thank you"),
                           subline=subline or cp.get("subline", "for listening. Please ask me anything."))

    def appendix_slide(self, title: str, hidden: bool = True):
        """Content slide titled 'Appendix: <title>' (qc_layout L6 only lets slides whose title starts with
        Appendix/Backup follow the references slide) and hidden from the slide show by default."""
        prefix = (self.prefs.get("appendix") or {}).get("title_prefix", "Appendix: ")
        slide = self.content_slide(title if title.lower().startswith(("appendix", "backup")) else prefix + title)
        if hidden:
            self.hide(slide)
        return slide

    @staticmethod
    def hide(slide):
        """Hide a slide from the slide show (kept in the file, shown on request)."""
        slide._element.set("show", "0")
        return slide

    def _strip_trailing_periods(self):
        """prefs slide_text.trailing_period == False: no '.' at the end of a slide text line (references and
        abbreviation endings excepted); speaker notes keep theirs."""
        keep = ("et al.", "vs.", "Fig.", "Eng.", "approx.", "ca.", "..")
        for sl in self.prs.slides:
            texts = [sh.text_frame.text for sh in sl.shapes if sh.has_text_frame]
            if any(x.strip() == "References" for x in texts):
                continue
            for sh in sl.shapes:
                if not sh.has_text_frame:
                    continue
                for para in sh.text_frame.paragraphs:
                    runs = [r for r in para.runs if r.text]
                    full = "".join(r.text for r in runs)
                    if runs and full.endswith(".") and not full.endswith(keep):
                        runs[-1].text = runs[-1].text[:-1]

    def save(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.prs.core_properties.keywords = THEME_KEYWORD_PREFIX + self.theme.name
        if (self.prefs.get("slide_text") or {}).get("trailing_period") is False:
            self._strip_trailing_periods()
        used = sorted(getattr(self, "_layouts_used", ()))
        self.prs.core_properties.subject = (LAYOUT_SUBJECT_PREFIX + ",".join(used)) if used else ""
        self.prs.save(path)
        return path


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="deck_builder theme registry")
    ap.add_argument("--list-themes", action="store_true", help="print name/family/header/description per theme")
    args = ap.parse_args()
    if args.list_themes:
        for t in list_themes():
            print(f"{t['name']:<20} {t['family']:<10} {t['provenance']:<11} {t['header_style']:<9} {t['description']}")
    else:
        ap.print_help()
