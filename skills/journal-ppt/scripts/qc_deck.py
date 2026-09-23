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

from pptx import Presentation
from pptx.util import Inches, Emu
from pptx.oxml.ns import qn
from pptx.enum.shapes import MSO_SHAPE_TYPE

ALLOWED_FONT_SIZES = {9, 9.5, 11, 12, 14, 16, 18, 26, 30}
ALLOWED_FONT_SIZES_RESEARCH = ALLOWED_FONT_SIZES | {20}
ALLOWED_LINE_SPACING = {1.0, 1.15, 1.5}
ALLOWED_SPACE_AFTER_PT = {0, 2, 6, 12, 16}
REQUIRED_FONT = "Arial"
HANGUL_RE = re.compile(r'[가-힣㄰-㆏]')
# Base 8-color palette (style_spec.md §5) + 3 sanctioned derived roles added after this
# checker flagged them as false positives on real decks: header-bar subtitle text (light
# tint needed for contrast against the #1A355E navy bar; body #333333 would be invisible
# there), and the Strengths/Limitations slide's paired heading colors (green/red, matching
# the existing #DBE8F7/#FDE8E8 box fills). See style_spec.md §5 "Sanctioned derived colors".
ALLOWED_HEX = {"1A355E", "E86A1A", "333333", "2E5E9B", "888888",
               "DBE8F7", "FDE8E8", "FFFFFF",
               "C5D5EA",  # header-bar subtitle text
               "2C6E3F",  # Strengths heading (paired with DBE8F7 fill)
               "A53636"}  # Limitations heading (paired with FDE8E8 fill)

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
# capital>, e.g. AspRedAm, EcAdh, BsGDH, and reports it as "confirm italic"
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


def qc_deck(pptx_path: str, research_mode: bool = False) -> Report:
    r = Report()
    prs = Presentation(pptx_path)
    allowed_sizes = ALLOWED_FONT_SIZES_RESEARCH if research_mode else ALLOWED_FONT_SIZES

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
                    if max(shape.width, shape.height) < Inches(3):
                        picture_too_small += 1
                        r.crit(f"Slide {i}: picture below 3in minimum dimension "
                               f"(shape_id={shape.shape_id})")

            # QC-9: geometry
            # Two sanctioned exemptions, both from style_spec.md §6:
            #  (a) full-bleed header bars (left==0, spanning the slide width) are an
            #      intentional background element, not "content" bound by the 0.3in margin.
            #  (b) the footer band (top in [7.1in, 7.4in]) sits below the Y_FLOOR by
            #      design -- Y_FLOOR governs figures/text/tables, not the footer text itself.
            try:
                is_full_bleed_bar = (
                    shape.left is not None and shape.top is not None and
                    abs(shape.left) <= TOLERANCE_EMU and abs(shape.top) <= TOLERANCE_EMU and
                    shape.width is not None and abs(shape.width - SLIDE_W) <= Emu(2000)
                )
                is_footer_band = (
                    shape.top is not None and shape.height is not None and
                    shape.height <= FOOTER_MAX_HEIGHT and
                    (SLIDE_H - (shape.top + shape.height)) <= FOOTER_BOTTOM_SLACK
                )
                if shape.top is not None and shape.height is not None and not is_footer_band:
                    if shape.top + shape.height > Y_FLOOR + TOLERANCE_EMU:
                        geometry_violations += 1
                        r.crit(f"Slide {i}: shape {shape.shape_id} extends below "
                               f"Y=7.0in floor (bottom={(shape.top + shape.height) / 914400:.2f}in)")
                if shape.left is not None and not is_full_bleed_bar:
                    if shape.left < LEFT_MARGIN - TOLERANCE_EMU:
                        geometry_violations += 1
                        r.crit(f"Slide {i}: shape {shape.shape_id} breaches left margin")
                    if shape.width is not None and shape.left + shape.width > RIGHT_EDGE:
                        geometry_violations += 1
                        r.crit(f"Slide {i}: shape {shape.shape_id} breaches right margin")
            except Exception:
                pass

            # dispersion: fill color on rectangles/autoshapes (skip pictures, which
            # have no meaningful "fill color" for this purpose, and connectors/lines)
            if shape.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE:
                try:
                    if shape.fill.type is not None:
                        fc = _rgb_hex(shape.fill.fore_color)
                        if fc:
                            disp_fill_colors[fc] += 1
                except Exception:
                    pass

            if not shape.has_text_frame:
                continue
            tf = shape.text_frame

            if not tf.word_wrap:
                r.crit(f"Slide {i}: word_wrap not set on shape {shape.shape_id}")
            if not _has_noautofit(tf):
                missing_autofit += 1
                r.crit(f"Slide {i}: disable_autofit() not applied on shape {shape.shape_id} "
                       f"(line_spacing will be silently ignored by PowerPoint)")

            for para in tf.paragraphs:
                if para.runs and para.line_spacing is not None:
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

                if para.space_after is not None:
                    sa = round(para.space_after.pt, 1)
                    disp_space_after[sa] += 1
                    if sa not in ALLOWED_SPACE_AFTER_PT:
                        off_scale_spacing.add(f"space_after={sa}")
                        r.warn(f"Slide {i}: space_after={sa}pt not in {sorted(ALLOWED_SPACE_AFTER_PT)}")

                for run in para.runs:
                    if not run.text.strip():
                        continue
                    disp_font_names[run.font.name or "(inherited)"] += 1
                    if run.font.name not in (None, REQUIRED_FONT):
                        r.crit(f"Slide {i}: font {run.font.name!r} != Arial (text={run.text[:30]!r})")
                    if run.font.size is not None:
                        pt = round(run.font.size.pt, 1)
                        disp_font_sizes[pt] += 1
                        if pt not in allowed_sizes:
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
                    if hexc and hexc not in ALLOWED_HEX:
                        off_palette_colors.add(hexc)
                        r.warn(f"Slide {i}: font color #{hexc} not in resolved palette")

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
    if missing_autofit == 0 and total_shapes > 0:
        r.ok(f"QC-2: disable_autofit() applied on all {total_shapes} text-frame shapes")
    if not off_scale_sizes:
        r.ok(f"QC-6: all font sizes within closed type scale {sorted(allowed_sizes)}")
    if not off_scale_spacing:
        r.ok(f"QC-3/4: all line_spacing/space_after values within closed lists")
    if geometry_violations == 0:
        r.ok(f"QC-9: no shape crosses the Y=7.0in floor or side margins")
    if picture_too_small == 0 and total_pictures > 0:
        r.ok(f"QC-11: all {total_pictures} pictures >= 3in minimum dimension")
    if total_logos > 0:
        r.ok(f"QC-11: {total_logos} attribution logo(s) exempted from the 3in "
             f"figure-legibility floor (shape.name startswith 'logo:')")
    if missing_notes == 0:
        r.ok(f"QC-10: every slide has a speaker-notes pane ({n_slides} slides)")
    if short_notes == 0 and missing_notes == 0:
        r.ok(f"QC-10: every slide's notes >= 100 chars")
    if notes_without_korean == 0 and missing_notes == 0:
        r.ok(f"QC-10: every slide's notes contain Korean")
    if origin_prefix_candidates == 0:
        r.ok("QC-15: no origin-prefix-shaped tokens found (nothing to confirm)")

    # -- Value-dispersion check (independent of any named rule) -----------
    # Ceilings: font.size -> the closed-list size (9, or 10 in research mode);
    # line_spacing -> 3 (1.0/1.15/1.5); space_after -> 5 (0/2/6/12/16);
    # font.name -> 1 (Arial); fill colors -> the resolved palette size (11).
    # A count exceeding its ceiling is WARNING even when every individual value is
    # inside the allowed set -- that combination is exactly what a closed-list
    # assertion cannot see (each value legal in isolation, but nobody controlled
    # how MANY distinct ones crept in).
    dispersion_specs = [
        ("font.size.pt", disp_font_sizes, len(allowed_sizes)),
        ("paragraph.line_spacing", disp_line_spacing, len(ALLOWED_LINE_SPACING)),
        ("paragraph.space_after.pt", disp_space_after, len(ALLOWED_SPACE_AFTER_PT)),
        ("font.name", disp_font_names, 1),
        ("shape fill color (autoshapes)", disp_fill_colors, len(ALLOWED_HEX)),
    ]
    any_dispersion_flagged = False
    for label, counter, ceiling in dispersion_specs:
        if not counter:
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
    if not any_dispersion_flagged and any(c for _, c, _ in dispersion_specs):
        r.ok("Value-dispersion check: no property exceeded its expected ceiling")

    return r


def main():
    ap = argparse.ArgumentParser(description="QC gate for journal-ppt decks")
    ap.add_argument("pptx_path")
    ap.add_argument("--research-mode", action="store_true",
                     help="allow the conditional 20pt stat-tile size")
    args = ap.parse_args()

    if not Path(args.pptx_path).exists():
        print(f"ERROR: file not found: {args.pptx_path}", file=sys.stderr)
        sys.exit(2)

    report = qc_deck(args.pptx_path, research_mode=args.research_mode)
    print(report.render(args.pptx_path))
    sys.exit(1 if report.critical else 0)


if __name__ == "__main__":
    main()
