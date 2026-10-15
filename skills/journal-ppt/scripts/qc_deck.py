#!/usr/bin/env python3
"""
qc_deck.py -- runnable QC gate for journal-ppt decks (style_spec.md §9).

Usage:
    python qc_deck.py <path-to.pptx> [--research-mode]

Exits 0 only if there are zero CRITICAL findings. Always prints a categorized
report (CRITICAL / WARNING / PASSED) so it can gate delivery in a pipeline.

This intentionally re-implements the checks as *assertions gathered into a
report* rather than raising on the first failure, so a single run surfaces
every defect in the deck instead of stopping at the first slide.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pptx import Presentation
from pptx.util import Inches, Emu
from pptx.oxml.ns import qn
from pptx.enum.shapes import MSO_SHAPE_TYPE

ALLOWED_FONT_SIZES = {9, 9.5, 11, 12, 14, 16, 18, 26, 30}
ALLOWED_FONT_SIZES_RESEARCH = ALLOWED_FONT_SIZES | {20}
ALLOWED_LINE_SPACING = {1.0, 1.15, 2.0}   # 1.5 retired 261004 (body = 2.0, memory S2)
ALLOWED_SPACE_AFTER_PT = {0, 2, 6, 12, 16}
REQUIRED_FONT = "Arial"
HANGUL_RE = re.compile(r'[가-힣㄰-㆏]')
# The allowed-hex set is per THEME (deck_builder.THEMES[...].allowed_hex); the theme name is
# read from core_properties.keywords ("journal-ppt-theme:<name>"), overridable with --theme,
# fallback navy_lab. navy_lab keeps its 3 sanctioned derived colors (header-bar subtitle tint,
# Strengths green, Limitations red -- style_spec.md §5). The old #888888 caption/footer gray was
# retired on 261004 (3.54:1 on white, below WCAG AA 4.5:1) in favor of #666666.
from deck_builder import (THEMES, DEFAULT_THEME, THEME_KEYWORD_PREFIX,  # noqa: E402
                          contrast_ratio, required_contrast)
ALLOWED_HEX = set(THEMES[DEFAULT_THEME].allowed_hex)   # legacy name: the navy_lab set
THEME_KEYWORD_RE = re.compile(re.escape(THEME_KEYWORD_PREFIX) + r"([A-Za-z0-9_\-]+)")

# QC-15: origin-prefix italic flag (academic-term-rules SKILL.md §2 -- the
# 2-letter genus-abbreviation prefix on an engineered-enzyme label is italic,
# the protein-name suffix is roman: EcAdh, BsLdh, AoRedAm). The named 8-prefix
# table there (Bs/Ec/Ps/Pf/Gc/Ao/Sc/Lp/Ag) is NOT exhaustive -- the IRED-deck
# case (AspRedAm, "Asp" for Aspergillus, 260912) used a 3-letter prefix not on
# that list. A hardcoded prefix list would have missed it; a fully generic
# "any leading capitalized run before another capital" regex would false-fire
# on ordinary all-caps tokens (IRED, RedAm alone, NADPH, RF). So this check is
# heuristic and FLAG-ONLY (WARNING, never CRITICAL): it looks for a token of
# the shape <2-4 lowercase-after-cap letters><CamelCase word starting with a
# capital>, e.g. AspRedAm, EcAdh, BsLdh, and reports it as "confirm italic"
# rather than asserting a verdict -- a human (or the Academic QC agent,
# pipeline.md Phase 4) still has to judge whether it is really a genus-prefix
# label and not a coincidental CamelCase token.
ORIGIN_PREFIX_CANDIDATE_RE = re.compile(r'\b([A-Z][a-z]{1,3})([A-Z][A-Za-z0-9]{2,})\b')
# tokens that are legitimate CamelCase-looking words on their own and should
# never be flagged even though they match the shape (measured false positives
# from the IRED deck run: enzyme-class abbreviations, not origin-prefixed
# labels)
ORIGIN_PREFIX_ALLOWLIST = {"RedAm", "IREDs", "NADPH", "NADH"}

Y_FLOOR = Inches(7.0)
# Footer text legitimately sits below Y_FLOOR (style_spec.md §6 puts the footer band at
# 7.1-7.4in, but measured real decks -- including the one this checker was validated
# against -- place it as early as 7.05in). Rather than chase a moving top-coordinate
# threshold, identify "footer-band" by shape SHAPE: short (<=0.4in tall) and its bottom
# edge close to the slide's true bottom (7.5in) with generous slack. A tall content shape
# that happens to start near 7in will not match this (it fails the height test), so this
# does not silently exempt a genuine overflow.
FOOTER_MAX_HEIGHT = Inches(0.4)
FOOTER_BOTTOM_SLACK = Inches(0.55)  # how close to the true slide bottom (7.5in) counts as footer
SLIDE_H = Inches(7.5)
LEFT_MARGIN = Inches(0.3)
RIGHT_EDGE = Inches(13.033)
SLIDE_W = Inches(13.333)
TOLERANCE_EMU = Emu(1000)
MIN_PICTURE = Inches(3)     # figure legibility floor (max dimension)
REF_W_IN, REF_H_IN = 13.333, 7.5


def slide_geometry(prs) -> dict:
    """Geometry limits for this presentation's slide size.

    The constants above are defined for the 13.333 x 7.5 in reference slide. A slide of another
    size (a 20 x 11.25 in third-party template, 4:3) gets them scaled proportionally: widths and
    margins by width/13.333, heights, Y floor and footer band by height/7.5, the picture
    minimum by the smaller of the two. A slide within 0.2% of the reference returns the original
    constants unchanged, so a deck built by deck_builder.Deck is checked exactly as before."""
    w_in, h_in = prs.slide_width / 914400.0, prs.slide_height / 914400.0
    sx = 1.0 if abs(w_in / REF_W_IN - 1) < 0.002 else w_in / REF_W_IN
    sy = 1.0 if abs(h_in / REF_H_IN - 1) < 0.002 else h_in / REF_H_IN
    if sx == 1.0 and sy == 1.0:
        return dict(sx=1.0, sy=1.0, slide_w=SLIDE_W, slide_h=SLIDE_H, y_floor=Y_FLOOR,
                    left=LEFT_MARGIN, right=RIGHT_EDGE, footer_h=FOOTER_MAX_HEIGHT,
                    footer_slack=FOOTER_BOTTOM_SLACK, min_pic=MIN_PICTURE)
    return dict(sx=sx, sy=sy, slide_w=prs.slide_width, slide_h=prs.slide_height,
                y_floor=Emu(int(Y_FLOOR * sy)), left=Emu(int(LEFT_MARGIN * sx)),
                right=Emu(int(prs.slide_width - (SLIDE_W - RIGHT_EDGE) * sx)),
                footer_h=Emu(int(FOOTER_MAX_HEIGHT * sy)),
                footer_slack=Emu(int(FOOTER_BOTTOM_SLACK * sy)),
                min_pic=Emu(int(MIN_PICTURE * min(sx, sy))))


class Report:
    def __init__(self):
        self.critical: list[str] = []
        self.warning: list[str] = []
        self.passed: list[str] = []

    def crit(self, msg: str):
        self.critical.append(msg)

    def warn(self, msg: str):
        self.warning.append(msg)

    def ok(self, msg: str):
        self.passed.append(msg)

    def render(self, path: str) -> str:
        lines = [f"## Deck QC Report", f"File: {path}", ""]
        lines.append(f"### CRITICAL ({len(self.critical)})")
        lines += [f"- {m}" for m in self.critical] or ["- (none)"]
        lines.append("")
        lines.append(f"### WARNING ({len(self.warning)})")
        lines += [f"- {m}" for m in self.warning] or ["- (none)"]
        lines.append("")
        lines.append(f"### PASSED ({len(self.passed)})")
        lines += [f"- {m}" for m in self.passed] or ["- (none)"]
        lines.append("")
        verdict = "FAIL" if self.critical else ("PASS WITH WARNINGS" if self.warning else "PASS")
        lines.append(f"### Summary")
        lines.append(f"CRITICAL: {len(self.critical)} | WARNING: {len(self.warning)} | PASSED: {len(self.passed)}")
        lines.append(f"VERDICT: {verdict}")
        return "\n".join(lines)


def _has_noautofit(tf) -> bool:
    bodyPr = tf._txBody.find(qn('a:bodyPr'))
    return bodyPr is not None and bodyPr.find(qn('a:noAutofit')) is not None


def _rgb_hex(color) -> str | None:
    try:
        if color.type is None:
            return None
        return str(color.rgb)
    except Exception:
        return None


def detect_theme(prs) -> str | None:
    """Theme name stored by Deck.save() in core_properties.keywords, or None."""
    try:
        m = THEME_KEYWORD_RE.search(prs.core_properties.keywords or "")
    except Exception:
        return None
    return m.group(1) if m else None


def detect_layouts(prs) -> list[str]:
    """Layout names recorded by Deck.save() in core_properties.subject."""
    try:
        subj = prs.core_properties.subject or ""
    except Exception:
        return []
    pre = "journal-ppt-layouts:"
    return [x for x in subj[len(pre):].split(",") if x] if subj.startswith(pre) else []


def _slide_bg_rgb(slide, theme):
    try:
        f = slide.background.fill
        if f.type is not None:
            return f.fore_color.rgb
    except Exception:
        pass
    return theme.bg


def _shape_fill_rgb(shape):
    try:
        if shape.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE and shape.fill.type is not None:
            return shape.fill.fore_color.rgb
    except Exception:
        pass
    return None


def qc_deck(pptx_path: str, research_mode: bool = False,
            theme_override: str | None = None, layout: bool = True,
            language: bool = True, external_template: bool = False, prose: bool = True) -> Report:
    """external_template=True: the deck was built on a third-party template, so the checks that
    only make sense for our own themes (closed palette hex list, Arial-only font, closed type
    scale / line-spacing / space-after lists, no-autofit + word-wrap flags, value dispersion,
    side margins) are not run. Overflow, overlap, contrast, notes, Hangul-in-body, language gate,
    picture legibility, the Y floor and the number check stay on."""
    r = Report()
    prs = Presentation(pptx_path)
    G = slide_geometry(prs)
    detected = detect_theme(prs)
    theme_name = theme_override or detected or DEFAULT_THEME
    if theme_name not in THEMES:
        if not external_template:
            r.warn(f"unknown theme {theme_name!r} in file/flag; falling back to {DEFAULT_THEME}")
        theme_name = DEFAULT_THEME
    theme = THEMES[theme_name]
    src = "--theme flag" if theme_override else ("file keywords" if detected else "default fallback")
    if external_template:
        r.ok(f"External template: slide {prs.slide_width / 914400:.2f} x {prs.slide_height / 914400:.2f} in "
             f"(limits scaled x{G['sx']:.3f} w / x{G['sy']:.3f} h); palette, font, type-scale, "
             f"spacing and dispersion checks are OFF (they describe our own themes only)")
    else:
        r.ok(f"Theme: {theme_name} ({src}); palette check uses {len(theme.allowed_hex)} hex values")
    if theme_override and detected and detected != theme_override and not external_template:
        r.warn(f"--theme {theme_override} overrides the theme recorded in the file ({detected}); "
               f"one deck must use one theme")
    allowed_hex = set(theme.allowed_hex)
    allowed_sizes = set(ALLOWED_FONT_SIZES_RESEARCH if research_mode else ALLOWED_FONT_SIZES)
    allowed_sizes |= set(theme.extra_sizes)
    layouts_used = detect_layouts(prs)
    if layouts_used:
        try:
            from layouts import LAYOUTS, load_all
            load_all()
            for ln in layouts_used:
                if ln in LAYOUTS:
                    allowed_sizes |= set(LAYOUTS[ln].extra_sizes)
                else:
                    r.warn(f"deck records unknown layout {ln!r} (registry changed?)")
            r.ok(f"Layouts used: {', '.join(layouts_used)}")
        except ImportError:
            r.warn("layouts package not importable: extra sizes of layouts were NOT allowed")
    total_reaction_pics = 0
    off_palette_fills = set()
    low_contrast = 0

    total_shapes = 0
    total_pictures = 0
    off_scale_sizes = set()
    off_scale_spacing = set()
    hangul_hits = 0
    missing_autofit = 0
    missing_notes = 0
    short_notes = 0
    notes_without_korean = 0
    geometry_violations = 0
    picture_too_small = 0
    off_palette_colors = set()
    origin_prefix_candidates = 0
    total_logos = 0

    # -- Value-dispersion tracking (independent of any named rule) --------
    # Rationale: the defects that got through prior builds were both "the spec was
    # silent on this property, so the builder improvised, and nobody noticed because
    # no rule NAMED the property." A dispersion check catches that class of defect by
    # asking "why does this vary at all" instead of "does this match rule X" -- it
    # flags spread even when every individual value happens to be inside an allowed
    # set. Do not delete this as redundant with the closed-list assertions above; it
    # is the only check that would have caught the Korean-body-text and 16-19-distinct-
    # font-size defects if a builder had used ostensibly "in range" values with no
    # actual named rule stopping the drift into 8 different in-range choices.
    disp_font_sizes = Counter()
    disp_line_spacing = Counter()
    disp_space_after = Counter()
    disp_font_names = Counter()
    disp_fill_colors = Counter()

    for i, slide in enumerate(prs.slides, start=1):
        for shape in slide.shapes:
            total_shapes += 1

            # QC-11: pictures (results/scheme figures only -- an attribution
            # logo is exempt, see below). deck_builder.Deck._logo_row() marks
            # every logo picture's shape.name as "logo:<stem>" specifically so
            # this check can tell the two content classes apart; a picture
            # inserted by hand-written python-pptx code with no such name
            # still gets the full 3in figure-legibility floor.
            if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                is_logo = (shape.name or "").startswith("logo:")
                if is_logo:
                    total_logos += 1
                else:
                    total_pictures += 1
                    if (shape.name or "").startswith("reaction:"):
                        total_reaction_pics += 1
                    if max(shape.width, shape.height) < G['min_pic']:
                        picture_too_small += 1
                        r.crit(f"Slide {i}: picture below {G['min_pic'] / 914400:.2g}in minimum dimension "
                               f"(shape_id={shape.shape_id})")

            # QC-9: geometry
            # Two sanctioned exemptions, both from style_spec.md §6:
            #  (a) full-bleed header bars (left==0, spanning the slide width) are an
            #      intentional background element, not "content" bound by the 0.3in margin.
            #  (b) the footer band (top in [7.1in, 7.4in]) sits below the Y_FLOOR by
            #      design -- Y_FLOOR governs figures/text/tables, not the footer text itself.
            try:
                is_deco = (shape.name or "").startswith("deco:")   # sidebar band etc.: full-height decoration
                is_full_bleed_bar = is_deco or (
                    shape.left is not None and shape.top is not None and
                    abs(shape.left) <= TOLERANCE_EMU and abs(shape.top) <= TOLERANCE_EMU and
                    shape.width is not None and abs(shape.width - G['slide_w']) <= Emu(2000)
                )
                is_footer_band = (
                    shape.top is not None and shape.height is not None and
                    shape.height <= G['footer_h'] and
                    (G['slide_h'] - (shape.top + shape.height)) <= G['footer_slack']
                )
                if external_template:
                    # template geometry is the template's own. A picture that leaves the slide by more than
                    # 0.1 in is reported (a warning: full-bleed crops are a design device); text boxes are
                    # judged by their text (qc_layout), since a box may extend past the edge with its text inside
                    if shape.shape_type == MSO_SHAPE_TYPE.PICTURE and shape.left is not None and                             shape.width is not None and shape.top is not None and shape.height is not None and (
                            shape.left < -Inches(0.1) or shape.top < -Inches(0.1) or
                            shape.left + shape.width > G['slide_w'] + Inches(0.1) or
                            shape.top + shape.height > G['slide_h'] + Inches(0.1)):
                        r.warn(f"Slide {i}: picture {shape.shape_id} extends more than 0.1in outside the slide")
                elif shape.top is not None and shape.height is not None and not is_footer_band and not is_deco:
                    if shape.top + shape.height > G['y_floor'] + TOLERANCE_EMU:
                        geometry_violations += 1
                        r.crit(f"Slide {i}: shape {shape.shape_id} extends below "
                               f"Y={G['y_floor'] / 914400:.2g}in floor (bottom={(shape.top + shape.height) / 914400:.2f}in)")
                if shape.left is not None and not is_full_bleed_bar and not external_template:
                    if shape.left < G['left'] - TOLERANCE_EMU:
                        geometry_violations += 1
                        r.crit(f"Slide {i}: shape {shape.shape_id} breaches left margin")
                    if shape.width is not None and shape.left + shape.width > G['right']:
                        geometry_violations += 1
                        r.crit(f"Slide {i}: shape {shape.shape_id} breaches right margin")
            except Exception:
                pass

            # dispersion: fill color on rectangles/autoshapes (skip pictures, which
            # have no meaningful "fill color" for this purpose, and connectors/lines)
            if shape.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE and not external_template:
                try:
                    if shape.fill.type is not None:
                        fc = _rgb_hex(shape.fill.fore_color)
                        if fc:
                            disp_fill_colors[fc] += 1
                            if fc not in allowed_hex and fc not in off_palette_fills:
                                off_palette_fills.add(fc)
                                r.warn(f"Slide {i}: shape fill #{fc} not in the {theme_name} palette")
                except Exception:
                    pass

            if not shape.has_text_frame:
                continue
            tf = shape.text_frame

            if not tf.word_wrap and not external_template:
                r.crit(f"Slide {i}: word_wrap not set on shape {shape.shape_id}")
            if not _has_noautofit(tf) and not external_template:
                missing_autofit += 1
                r.crit(f"Slide {i}: disable_autofit() not applied on shape {shape.shape_id} "
                       f"(line_spacing will be silently ignored by PowerPoint)")

            for para in tf.paragraphs:
                if external_template:
                    pass
                elif para.runs and para.line_spacing is not None:
                    ls = round(para.line_spacing, 2) if isinstance(para.line_spacing, float) else para.line_spacing
                    disp_line_spacing[ls] += 1
                    if ls not in ALLOWED_LINE_SPACING:
                        off_scale_spacing.add(ls)
                        r.crit(f"Slide {i}: line_spacing={ls} not in {sorted(ALLOWED_LINE_SPACING)} "
                               f"(shape {shape.shape_id})")
                elif para.runs and para.line_spacing is None:
                    disp_line_spacing["None"] += 1
                    r.warn(f"Slide {i}: line_spacing=None (unset) on shape {shape.shape_id} -- "
                           f"PowerPoint uses default 1.0x, likely unintended")

                if para.space_after is not None and not external_template:
                    sa = round(para.space_after.pt, 1)
                    disp_space_after[sa] += 1
                    if sa not in ALLOWED_SPACE_AFTER_PT:
                        off_scale_spacing.add(f"space_after={sa}")
                        r.warn(f"Slide {i}: space_after={sa}pt not in {sorted(ALLOWED_SPACE_AFTER_PT)}")

                for run in para.runs:
                    if not run.text.strip():
                        continue
                    disp_font_names[run.font.name or "(inherited)"] += 1
                    if run.font.name not in (None, theme.font) and not external_template:
                        r.crit(f"Slide {i}: font {run.font.name!r} != {theme.font} (text={run.text[:30]!r})")
                    if run.font.size is not None:
                        pt = round(run.font.size.pt, 1)
                        disp_font_sizes[pt] += 1
                        if external_template:
                            if pt < 9:
                                r.crit(f"Slide {i}: font {pt}pt below 9pt floor")
                        elif pt not in allowed_sizes:
                            off_scale_sizes.add(pt)
                            r.crit(f"Slide {i}: font size {pt}pt not in closed type scale "
                                   f"{sorted(allowed_sizes)} (text={run.text[:30]!r})")
                        elif pt < 9:
                            r.crit(f"Slide {i}: font {pt}pt below 9pt floor")

                    if HANGUL_RE.search(run.text):
                        hangul_hits += 1
                        r.crit(f"Slide {i}: Hangul found in slide body: {run.text[:40]!r}")

                    # QC-15: origin-prefix italic candidate (heuristic, WARNING-only,
                    # see ORIGIN_PREFIX_CANDIDATE_RE comment above for why this
                    # cannot be a hard assertion)
                    for m in ORIGIN_PREFIX_CANDIDATE_RE.finditer(run.text):
                        token = m.group(0)
                        if token in ORIGIN_PREFIX_ALLOWLIST:
                            continue
                        prefix = m.group(1)
                        origin_prefix_candidates += 1
                        if not run.font.italic:
                            r.warn(f"Slide {i}: possible unitalicized origin prefix "
                                   f"'{prefix}' in {token!r} (text={run.text[:50]!r}) -- "
                                   f"confirm whether this is a genus-origin enzyme label "
                                   f"(academic-term-rules §2: prefix italic, suffix roman) "
                                   f"or a false positive")

                    hexc = _rgb_hex(run.font.color)
                    if hexc and hexc not in allowed_hex and not external_template:
                        off_palette_colors.add(hexc)
                        r.warn(f"Slide {i}: font color #{hexc} not in the {theme_name} palette")
                    if hexc and not (external_template and layout):
                        # (external template + layout QC on: qc_layout L3 judges contrast, resolving theme colors,
                        # style fills and master/layout backgrounds, which this explicit-color check cannot)
                        # contrast vs the shape's own fill, else the slide background
                        bg = _shape_fill_rgb(shape) or _slide_bg_rgb(slide, theme)
                        fg = run.font.color.rgb
                        ratio = contrast_ratio(fg, bg)
                        psz = run.font.size.pt if run.font.size is not None else 0
                        need = required_contrast(psz, bool(run.font.bold))
                        if ratio < need:
                            low_contrast += 1
                            r.warn(f"Slide {i}: contrast {ratio:.2f}:1 < {need}:1 for #{hexc} on "
                                   f"#{bg} ({psz}pt, text={run.text[:30]!r})")

        # QC-10: speaker notes
        if slide.has_notes_slide:
            notes_text = slide.notes_slide.notes_text_frame.text
            if len(notes_text) < 100:
                short_notes += 1
                r.warn(f"Slide {i}: speaker notes too short ({len(notes_text)} chars, need >=100)")
            if not HANGUL_RE.search(notes_text):
                notes_without_korean += 1
                r.warn(f"Slide {i}: speaker notes contain no Korean")
        else:
            missing_notes += 1
            r.crit(f"Slide {i}: missing speaker notes entirely")

    n_slides = len(prs.slides.__iter__.__self__._sldIdLst) if False else len(list(prs.slides))

    if hangul_hits == 0:
        r.ok(f"Language QC-8: no Hangul found outside speaker notes ({n_slides} slides)")
    if missing_autofit == 0 and total_shapes > 0 and not external_template:
        r.ok(f"QC-2: disable_autofit() applied on all {total_shapes} text-frame shapes")
    if not off_scale_sizes and not external_template:
        r.ok(f"QC-6: all font sizes within closed type scale {sorted(allowed_sizes)}")
    if not off_scale_spacing and not external_template:
        r.ok(f"QC-3/4: all line_spacing/space_after values within closed lists")
    if geometry_violations == 0 and external_template:
        r.ok("QC-9 (external): no text-bearing shape is outside the slide (pictures: see warnings)")
    elif geometry_violations == 0:
        r.ok(f"QC-9: no shape crosses the Y=7.0in floor or side margins")
    if picture_too_small == 0 and total_pictures > 0:
        r.ok(f"QC-11: all {total_pictures} pictures >= {G['min_pic'] / 914400:.2g}in minimum dimension")
    if total_logos > 0:
        r.ok(f"QC-11: {total_logos} attribution logo(s) exempted from the 3in "
             f"figure-legibility floor (shape.name startswith 'logo:')")
    if missing_notes == 0:
        r.ok(f"QC-10: every slide has a speaker-notes pane ({n_slides} slides)")
    if short_notes == 0 and missing_notes == 0:
        r.ok(f"QC-10: every slide's notes >= 100 chars")
    if notes_without_korean == 0 and missing_notes == 0:
        r.ok(f"QC-10: every slide's notes contain Korean")
    if low_contrast == 0 and external_template and layout:
        r.ok("QC-18 (external): contrast is judged by qc_layout L3 (theme colors, style fills, backgrounds)")
    elif low_contrast == 0:
        r.ok("QC-18: every explicitly colored text run reaches its WCAG contrast "
             "(4.5:1, or 3:1 for >=18pt bold) vs its fill/background")
    if total_reaction_pics > 0:
        r.ok(f"S3: reactions slide present ({total_reaction_pics} reaction picture(s))")
    elif not research_mode and n_slides >= 6:
        r.warn("S3: no reactions slide (Deck.reactions_slide(), pictures named 'reaction:*') -- "
               "journal-mode decks must show the paper's reaction structures right after "
               "Background (memory standard S3); ignore in research mode")
    if origin_prefix_candidates == 0:
        r.ok("QC-15: no origin-prefix-shaped tokens found (nothing to confirm)")

    # -- Value-dispersion check (independent of any named rule) -----------
    # Ceilings: font.size -> the closed-list size; line_spacing -> 3 (1.0/1.15/2.0);
    # space_after -> 5 (0/2/6/12/16); font.name -> 1 (Arial); fill colors -> theme palette size.
    # A count exceeding its ceiling is WARNING even when every individual value is
    # inside the allowed set -- that combination is exactly what a closed-list
    # assertion cannot see (each value legal in isolation, but nobody controlled
    # how MANY distinct ones crept in).
    dispersion_specs = [
        ("font.size.pt", disp_font_sizes, len(allowed_sizes)),
        ("paragraph.line_spacing", disp_line_spacing, len(ALLOWED_LINE_SPACING)),
        ("paragraph.space_after.pt", disp_space_after, len(ALLOWED_SPACE_AFTER_PT)),
        ("font.name", disp_font_names, 1),
        ("shape fill color (autoshapes)", disp_fill_colors, len(allowed_hex)),
    ]
    any_dispersion_flagged = False
    for label, counter, ceiling in dispersion_specs:
        if not counter or external_template:
            continue
        distinct = len(counter)
        dist_str = ", ".join(f"{v!r}×{n}" for v, n in
                              sorted(counter.items(), key=lambda kv: -kv[1]))
        if distinct > ceiling:
            any_dispersion_flagged = True
            r.warn(f"DISPERSION {label}: {distinct} distinct values found (ceiling {ceiling}) "
                   f"-- distribution: {dist_str}")
        else:
            r.ok(f"DISPERSION {label}: {distinct} distinct value(s) <= ceiling {ceiling} "
                 f"-- distribution: {dist_str}")
    if not any_dispersion_flagged and not external_template and any(c for _, c, _ in dispersion_specs):
        r.ok("Value-dispersion check: no property exceeded its expected ceiling")

    if layout:
        _merge_layout(r, prs, theme_name, external_template)
    if language:
        _merge_language(r, prs)
    if prose and not external_template:
        _merge_prose(r, prs)

    return r


# -- QC-19: language gate (language-gate skill) ---------------------------------------------
# Korean/English-only policy (261004). Slide body: foreign script = CRITICAL, English
# spelling (British variants, known misspellings), accents and Latin-script foreign prose =
# WARNING (Hangul in the body stays QC-8's CRITICAL). Speaker notes: foreign script =
# CRITICAL, Korean spelling/spacing and English spelling = WARNING. Imported through the
# skills tree (active/language-gate/scripts), never pip, so the deck QC and the CLI gate run
# the same rules.
LANGUAGE_GATE_SCRIPTS = Path(__file__).resolve().parents[2] / "language-gate" / "scripts"


def _load_language_gate():
    if str(LANGUAGE_GATE_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(LANGUAGE_GATE_SCRIPTS))
    try:
        import langgate  # noqa: F401
        return langgate
    except ImportError:
        return None


def _iter_text(shapes):
    """Text of every text frame, table cell and grouped shape, in reading order."""
    for shape in shapes:
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            yield from _iter_text(shape.shapes)
            continue
        if getattr(shape, "has_table", False) and shape.has_table:
            for row in shape.table.rows:
                for cell in row.cells:
                    if cell.text.strip():
                        yield cell.text
        elif shape.has_text_frame and shape.text_frame.text.strip():
            yield shape.text_frame.text


def _merge_language(r: Report, prs) -> None:
    lg = _load_language_gate()
    if lg is None:
        r.warn(f"language-gate NOT RUN: langgate not importable from {LANGUAGE_GATE_SCRIPTS} "
               f"-- foreign-script / spelling checks did not run (not a pass)")
        return
    body_opts = lg.Options(checks=("script", "latin", "en"))
    notes_opts = lg.Options(checks=("script", "latin", "en", "ko"))
    n_checked, crit_before, warn_before = 0, len(r.critical), len(r.warning)
    unknown: list[str] = []
    for i, slide in enumerate(prs.slides, start=1):
        parts = [("body", t, body_opts) for t in _iter_text(slide.shapes)]
        if slide.has_notes_slide:
            nt = slide.notes_slide.notes_text_frame.text
            if nt.strip():
                parts.append(("notes", nt, notes_opts))
        for where, text, opts in parts:
            n_checked += 1
            for f in lg.check_text(text, "txt", f"slide{i}:{where}", opts):
                if f.category == "en-unknown":
                    unknown.append(f"{f.token} (slide {i} {where})")
                    continue
                if f.severity == lg.INFO:
                    continue
                fix = f" -> {f.fix!r}" if f.fix else ""
                msg = (f"Slide {i}: [QC-19 {f.category}] {where}: {f.token!r}{fix} -- "
                       f"{f.message}")
                (r.crit if f.severity == lg.CRITICAL else r.warn)(msg)
    if unknown:
        r.warn(f"QC-19 en-unknown (dictionary, review only): {len(unknown)} word(s) not in the "
               f"English list: {', '.join(unknown[:12])}{' ...' if len(unknown) > 12 else ''}")
    if n_checked == 0:
        r.warn("language-gate BLIND: no slide text or notes to check (not a pass)")
    elif len(r.critical) == crit_before and len(r.warning) == warn_before:
        r.ok(f"QC-19 language-gate: {n_checked} text block(s) Korean/English only, no "
             f"spelling/spacing finding")


def _merge_prose(r: Report, prs) -> None:
    """QC-20: speaker-notes residue / count / duplicate sentences, slide AI-isms, trailing periods, conclusions
    slide, hidden appendix (qc_prose.py; all WARNING, never a verdict -- avoid-ai-writing detect still owns C-62)."""
    try:
        from qc_prose import check_prose, prefs_from_deck
    except ImportError:
        r.warn("qc_prose.py not importable: notes/prose checks did NOT run")
        return
    prefs = prefs_from_deck(prs)
    found = check_prose(prs, prefs=prefs)
    for f in found:
        where = f"Slide {f.slide}" if f.slide else "Deck"
        r.warn(f"{where}: [QC-20 {f.rule}] {f.message}")
    if not found:
        r.ok(f"QC-20 prose: no notes residue, count mismatch, duplicate sentence, AI-ism or trailing period"
             f"{' (prefs: ' + prefs['name'] + ')' if prefs else ''}; run avoid-ai-writing detect for the full catalog")


def _merge_layout(r: Report, prs, theme_name: str, external_template: bool = False) -> None:
    """Fold qc_layout findings (overflow L1, overlap L2, contrast L3, structure L4, aspect L5, slide order L6) into the report."""
    try:
        from qc_layout import check_layout
    except ImportError:
        r.warn("qc_layout.py not importable: overflow/overlap/contrast checks did NOT run")
        return
    findings = check_layout(prs, theme=None if external_template else theme_name,
                            external_template=external_template)
    for f in findings:
        msg = f"Slide {f.slide}: [{f.rule}] {f.shape_name}: {f.message}"
        (r.crit if f.severity == "CRITICAL" else r.warn)(msg)
    if not any(f.severity == "CRITICAL" for f in findings):
        r.ok(f"qc_layout: no CRITICAL overflow/overlap/contrast/structure finding "
             f"({len(findings)} warning-level)")


def _merge_numbers(r: Report, pptx_path: str, source: str, ledger: str | None, strict: bool) -> None:
    """Fold qc_numbers (slide numbers vs content_analysis.json) into the report."""
    try:
        from qc_numbers import run as run_numbers, EXIT_BLIND
    except ImportError:
        r.warn("qc_numbers.py not importable: number cross-check did NOT run")
        return
    code, led = run_numbers(pptx_path, source, ledger, strict)
    if code == EXIT_BLIND:
        r.warn(f"qc_numbers BLIND (not a pass, nothing was verified): {led.get('error')}")
        return
    for row in led["claims"]:
        msg = f"Slide {row['slide']}: [{row['status']}] {row['raw']!r} ({row['reason']})"
        if row["severity"] == "CRITICAL":
            r.crit(msg)
        elif row["severity"] == "WARNING":
            r.warn(msg)
    r.ok(f"qc_numbers: {len(led['claims'])} claims, counts {led.get('counts')}")


def main():
    ap = argparse.ArgumentParser(description="QC gate for journal-ppt decks")
    ap.add_argument("pptx_path")
    ap.add_argument("--research-mode", action="store_true",
                     help="allow the conditional 20pt stat-tile size")
    ap.add_argument("--theme", choices=sorted(THEMES), default=None,
                     help="override the theme (default: autodetect from file keywords, "
                          "fallback navy_lab)")
    ap.add_argument("--source", default=None,
                     help="content_analysis.json: enables the slide-number cross-check (qc_numbers)")
    ap.add_argument("--ledger", default=None, help="write the number ledger JSON here")
    ap.add_argument("--strict-numbers", action="store_true", help="number warnings also exit 1")
    ap.add_argument("--external-template", action="store_true",
                     help="deck built on a third-party template (see template_adapter.py): skip the "
                          "closed palette / Arial-only / type-scale / spacing / dispersion checks, keep "
                          "overflow, overlap, contrast, notes, Hangul-in-body, language gate, numbers")
    ap.add_argument("--no-layout", action="store_true", help="skip qc_layout checks")
    ap.add_argument("--no-prose", action="store_true", help="skip the QC-20 prose/notes check (qc_prose.py)")
    ap.add_argument("--no-language", action="store_true",
                     help="skip the QC-19 language-gate check (reported as NOT RUN)")
    args = ap.parse_args()

    if not Path(args.pptx_path).exists():
        print(f"ERROR: file not found: {args.pptx_path}", file=sys.stderr)
        sys.exit(2)

    report = qc_deck(args.pptx_path, research_mode=args.research_mode,
                     theme_override=args.theme, layout=not args.no_layout,
                     language=not args.no_language, external_template=args.external_template,
                     prose=not args.no_prose)
    if args.no_language:
        report.warn("language-gate NOT RUN (--no-language): foreign-script/spelling unchecked")
    if args.source:
        _merge_numbers(report, args.pptx_path, args.source, args.ledger, args.strict_numbers)
    else:
        report.warn("qc_numbers NOT RUN: no --source content_analysis.json, so slide numbers are unverified (C-40)")
    print(report.render(args.pptx_path))
    sys.exit(1 if report.critical else 0)


if __name__ == "__main__":
    main()
