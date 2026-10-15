"""Tests for scripts/template_adapter.py and the slide-size / --external-template behavior of the QC.

The suite runs on synthetic templates built with python-pptx (python-pptx's default template plus a few
hand-made layouts and example slides), so it needs no downloads. Tests that use the lab's real template
collection (~/scratch/ppt_templates) skip themselves when a file is missing; no template file is ever
copied into the repository.
"""
from __future__ import annotations

import copy
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from lxml import etree
from pptx import Presentation
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import deck_builder as db  # noqa: E402
import qc_deck  # noqa: E402
import qc_layout  # noqa: E402
import template_adapter as ta  # noqa: E402
from template_adapter import TemplateDeck, TemplateError  # noqa: E402

NOTES = ("이 슬라이드는 템플릿 어댑터 시험용 발표 노트입니다. 핵심 숫자와 그림의 출처를 천천히 읽고, "
         "해석상 주의할 점을 한 문장으로 덧붙이고, 질문이 있으면 이 슬라이드에서 바로 받겠다고 안내합니다.")
REAL = Path.home() / "scratch" / "ppt_templates"


# --------------------------------------------------------------------------- fixtures ---
def _png(path: Path, w: int, h: int, color=(200, 60, 60)):
    from PIL import Image
    Image.new("RGB", (w, h), color).save(path)
    return path


def _add_typed_page_number(layout, text="007"):
    """Put a typed page number on a layout, as some downloaded templates do."""
    scratch = Presentation()
    tb = scratch.slides.add_slide(scratch.slide_layouts[6]).shapes.add_textbox(Inches(8.5), Inches(7.0), Inches(0.8), Inches(0.3))
    tb.text_frame.text = text
    layout.shapes._spTree.append(copy.deepcopy(tb._element))


@pytest.fixture()
def synth(tmp_path):
    """4:3 template from python-pptx's default, with 2 example slides, one of them free-shape based."""
    prs = Presentation()
    s1 = prs.slides.add_slide(prs.slide_layouts[1])
    s1.shapes.title.text = "Sample title"
    s1.placeholders[1].text = "Sample body text from the template"
    s2 = prs.slides.add_slide(prs.slide_layouts[6])        # Blank: free shapes only
    img = _png(tmp_path / "ex.png", 400, 300)
    pic = s2.shapes.add_picture(str(img), Inches(0.5), Inches(1.5), Inches(4), Inches(3))
    pic.name = "Sample photo"
    for name, txt, l, t, w, h, pt in [("Head", "Sample heading", 0.5, 0.4, 8.0, 0.6, 28),
                                      ("Claim", "Sample claim sentence", 5.0, 1.5, 4.5, 1.2, 18),
                                      ("Cap", "Fig. 1 sample caption", 0.5, 4.7, 4.0, 0.4, 12),
                                      ("PageNo", "2", 9.0, 7.0, 0.5, 0.4, 12)]:
        tb = s2.shapes.add_textbox(Inches(l), Inches(t), Inches(w), Inches(h))
        tb.name = name
        tb.text_frame.word_wrap = True
        tb.text_frame.text = txt
        tb.text_frame.paragraphs[0].runs[0].font.size = Pt(pt)
    _add_typed_page_number(prs.slide_layouts[1], "007")
    path = tmp_path / "synth.pptx"
    prs.save(path)
    return path


def _layout_named(deck: TemplateDeck, name: str):
    return next(li for li in deck.layouts if li.name == name)


# --------------------------------------------------------------------------- inspect ---
def test_inspect_reports_size_theme_layouts(synth):
    d = ta.inspect_template(synth)
    assert (d["slide_width_in"], d["slide_height_in"]) == (10.0, 7.5)
    assert d["scale_vs_reference"]["x"] == pytest.approx(0.75, abs=0.001)
    assert d["theme_colors"]["accent1"] and d["theme_fonts"]["minor"]
    roles = {lay["name"]: lay["role"] for lay in d["layouts"]}
    assert roles["Title Slide"] == "title"
    assert roles["Title and Content"] == "content"
    assert roles["Section Header"] == "section"
    assert roles["Two Content"] == "two_content"
    assert roles["Title Only"] == "title_only"
    assert roles["Blank"] == "blank"
    assert roles["Picture with Caption"] == "picture_text"
    assert roles["Title and Vertical Text"] == "vertical"
    body = next(p for lay in d["layouts"] if lay["name"] == "Title and Content" for p in lay["placeholders"] if p["kind"] == "body")
    assert body["capacity_chars"] > 100 and body["font_pt"] > 10 and 0 < body["width_pct"] <= 100


def test_inspect_lists_example_slide_text_shapes(synth):
    d = ta.inspect_template(synth)
    assert len(d["examples"]) == 2
    names = [t["name"] for t in d["examples"][1]["text_shapes"]]
    assert names[:2] == ["Head", "Claim"] or "Head" in names
    assert all(t["capacity_chars"] >= 0 for t in d["examples"][1]["text_shapes"])


def test_cli_inspect_and_theme(synth):
    exe = [sys.executable, str(SCRIPTS / "template_adapter.py")]
    out = subprocess.run(exe + ["inspect", str(synth), "--json"], capture_output=True, text=True, encoding="utf-8")
    assert out.returncode == 0 and json.loads(out.stdout)["file"] == "synth.pptx"
    txt = subprocess.run(exe + ["inspect", str(synth)], capture_output=True, text=True, encoding="utf-8")
    assert "role=content" in txt.stdout
    th = subprocess.run(exe + ["theme", str(synth), "--name", "synth_theme"], capture_output=True, text=True, encoding="utf-8")
    assert th.returncode == 0 and '_theme("synth_theme"' in th.stdout and "contrast report" in th.stdout
    assert subprocess.run(exe + ["inspect", str(synth.parent / "nope.pptx")], capture_output=True).returncode == 2


# --------------------------------------------------------------------------- TemplateDeck ---
def test_add_fills_placeholders_and_removes_empty_ones(synth, tmp_path):
    d = TemplateDeck(synth)
    d.add("content", title="Why recycle", body=["First point", (1, "Sub point")], notes=NOTES)
    d.add("Title Only", title="Only a title", notes=NOTES)
    out = d.save(tmp_path / "out.pptx")
    prs = Presentation(out)
    assert len(prs.slides) == 2                              # the 2 example slides are gone
    s = prs.slides[0]
    assert s.shapes.title.text == "Why recycle"
    body = [p for p in s.placeholders if p.placeholder_format.idx == 1][0]
    assert [p.text for p in body.text_frame.paragraphs] == ["First point", "Sub point"]
    assert body.text_frame.paragraphs[1].level == 1
    assert all(r.font.size is not None for p in body.text_frame.paragraphs for r in p.runs)   # sizes explicit
    # "Title Only" has a title and nothing else; nothing may be left empty
    for sl in prs.slides:
        for ph in sl.placeholders:
            assert ph.text_frame.text.strip(), f"empty placeholder {ph.name} would show 'Click to add'"
    assert s.notes_slide.notes_text_frame.text == NOTES


def test_inherited_properties_are_written_explicitly(synth, tmp_path):
    d = TemplateDeck(synth)
    d.add("content", title="T", body=["a", "b"], notes=NOTES)
    prs = Presentation(d.save(tmp_path / "o.pptx"))
    bp = prs.slides[0].shapes.title._element.find(qn("p:txBody")).find(qn("a:bodyPr"))
    assert bp.get("lIns") is not None and bp.get("anchor") is not None


def test_text_that_does_not_fit_is_refused_and_nothing_is_written(synth):
    d = TemplateDeck(synth)
    n0 = len(d.prs.slides)
    with pytest.raises(TemplateError, match="does not fit"):
        d.add("content", title="T", body=["word " * 400], notes=NOTES, min_scale=1.0)
    assert len(d.prs.slides) == n0                           # the failed add left no slide behind
    assert issubclass(TemplateError, db.StyleError)


def test_shrink_is_explicit_and_bounded(synth, tmp_path):
    d = TemplateDeck(synth)
    long = ["This is a rather long bullet that needs more room than the template gives at its own size"] * 7
    with pytest.raises(TemplateError):
        d.add("content", title="T", body=long, notes=NOTES, min_scale=1.0, grow=1.0)
    d.add("content", title="T", body=long, notes=NOTES, min_scale=0.6, grow=1.0)
    assert d.log[-1]["scales"] and all(0.6 <= v < 1.0 for v in d.log[-1]["scales"].values())
    prs = Presentation(d.save(tmp_path / "o.pptx"))
    body = [p for p in prs.slides[0].placeholders if p.placeholder_format.idx == 1][0]
    assert body.text_frame.paragraphs[0].runs[0].font.size.pt < 32


@pytest.mark.parametrize("notes, why", [
    (None, "required"), ("한국어 노트이지만 너무 짧다", "chars"),
    ("This note is long enough in characters but written only in English, so the Korean rule must refuse it. " * 2, "no Korean"),
])
def test_notes_are_required_korean_and_long_enough(synth, notes, why):
    d = TemplateDeck(synth)
    n0 = len(d.prs.slides)
    with pytest.raises(TemplateError, match=why):
        d.add("content", title="T", body=["x"], notes=notes)
    assert len(d.prs.slides) == n0


def test_picture_is_never_stretched(synth, tmp_path):
    d = TemplateDeck(synth)
    wide = _png(tmp_path / "wide.png", 1600, 600)
    d.add("Picture with Caption", title="Fig", body=["caption"], picture=wide, notes=NOTES, picture_small_ok=True)
    pic = next(s for s in d.prs.slides[-1].shapes if s.shape_type == 13)
    assert pic.width / pic.height == pytest.approx(1600 / 600, rel=0.01)
    assert pic.crop_left == 0 and pic.crop_top == 0          # 2.7:1 into ~1.4:1 slot: contained, not cropped


def test_cover_crop_is_limited(synth, tmp_path):
    d = TemplateDeck(synth)
    slot_pic = next(p for p in _layout_named(d, "Picture with Caption").placeholders if p.kind == "picture")
    ratio = slot_pic.width_in / slot_pic.height_in
    near = _png(tmp_path / "near.png", int(1000 * ratio * 1.01), 1000)            # 1 % off: crop allowed
    d.add("Picture with Caption", title="Fig", body=["c"], picture=near, notes=NOTES, picture_small_ok=True)
    pic = next(s for s in d.prs.slides[-1].shapes if s.shape_type == 13)
    assert 0 < pic.crop_left < 0.01 and pic.crop_left == pic.crop_right
    far = _png(tmp_path / "far.png", 1000, 1000)
    with pytest.raises(TemplateError, match="would crop"):
        d.add("Picture with Caption", title="Fig", body=["c"], picture=far, fit="cover", notes=NOTES, picture_small_ok=True)


def _edit_layout(synth, tmp_path, layout_name, fn):
    prs = Presentation(synth)
    lay = next(l for l in prs.slide_layouts if l.name == layout_name)
    fn(lay)
    out = tmp_path / "edited.pptx"
    prs.save(out)
    return out


def test_picture_too_small_for_a_figure_is_refused(synth, tmp_path):
    def shrink(lay):
        pic = next(p for p in lay.placeholders if p.placeholder_format.type is not None and "PICTURE" in str(p.placeholder_format.type))
        pic.width = pic.height = Inches(2.0)
    d = TemplateDeck(_edit_layout(synth, tmp_path, "Picture with Caption", shrink))
    # the slot is now 2 x 2 in, below the 2.25 in legibility floor of a 10 in wide slide: it is not even a figure slot
    with pytest.raises(TemplateError):
        d.add("Picture with Caption", title="Fig", body=["c"], picture=_png(tmp_path / "p.png", 400, 300), notes=NOTES)


def test_text_colliding_with_picture_is_refused(synth, tmp_path):
    def overlap(lay):                                   # move the title on top of the picture slot
        phs = {str(p.placeholder_format.type).split(".")[-1].split(" ")[0]: p for p in lay.placeholders}
        phs["TITLE"].left, phs["TITLE"].top = phs["PICTURE"].left, phs["PICTURE"].top
    d = TemplateDeck(_edit_layout(synth, tmp_path, "Picture with Caption", overlap))
    with pytest.raises(TemplateError, match="run into a picture"):
        d.add("Picture with Caption", title="Title over the figure", body=["c"],
              picture=_png(tmp_path / "p.png", 800, 600), notes=NOTES, picture_small_ok=True)


def test_keep_originals_variants_and_package_validity(synth, tmp_path):
    keep_all = TemplateDeck(synth, keep_originals=True)
    keep_all.add("content", title="New", body=["x"], notes=NOTES)
    p = keep_all.save(tmp_path / "all.pptx")
    assert len(Presentation(p).slides) == 3
    keep_one = TemplateDeck(synth, keep_originals=[2])
    keep_one.add("content", title="New", body=["x"], notes=NOTES)
    p2 = keep_one.save(tmp_path / "one.pptx")
    prs = Presentation(p2)
    assert len(prs.slides) == 2
    names = zipfile.ZipFile(p2).namelist()
    assert len([n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)]) == 2     # no orphan slide parts
    assert zipfile.ZipFile(p2).testzip() is None


def test_sections_are_cleaned_when_originals_go(synth, tmp_path):
    prs = Presentation(synth)
    ids = [s.get("id") for s in prs.part._element.find(qn("p:sldIdLst"))]
    sld = "".join('<p14:sldId id="%s"/>' % i for i in ids)
    ext = etree.fromstring(
        '<p:extLst xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        '<p:ext uri="{521415D9-36F7-43E2-AB2F-B90AF26B5E84}">'
        '<p14:sectionLst xmlns:p14="http://schemas.microsoft.com/office/powerpoint/2010/main">'
        '<p14:section name="S" id="{11111111-2222-3333-4444-555555555555}"><p14:sldIdLst>' + sld +
        '</p14:sldIdLst></p14:section></p14:sectionLst></p:ext></p:extLst>')
    prs.part._element.append(ext)
    withsec = tmp_path / "sec.pptx"
    prs.save(withsec)
    d = TemplateDeck(withsec)
    d.add("content", title="New", body=["x"], notes=NOTES)
    out = d.save(tmp_path / "o.pptx")
    xml = zipfile.ZipFile(out).read("ppt/presentation.xml").decode("utf8")
    in_sections = set(re.findall(r'<p14:sldId id="(\d+)"', xml))
    in_deck = set(re.findall(r'<p:sldId id="(\d+)"', xml))
    assert in_sections == in_deck and len(in_deck) == 1      # originals left the section list, the new slide joined it


def test_typed_page_number_on_layout_becomes_a_field(synth, tmp_path):
    d = TemplateDeck(synth)
    assert any("007" in r for r in d.repairs)
    lay = next(l for l in d.prs.slide_layouts if l.name == "Title and Content")
    flds = lay._element.findall(".//" + qn("a:fld"))
    assert flds and flds[-1].get("type") == "slidenum"
    assert "007" not in "".join(t.text or "" for t in lay._element.iter(qn("a:t")))


def test_text_in_background_colour_is_refused(synth):
    prs = Presentation(synth)
    lay = next(l for l in prs.slide_layouts if l.name == "Title and Content")
    ph = [p for p in lay.placeholders if p.placeholder_format.idx == 1][0]
    ls = ph._element.find(qn("p:txBody")).find(qn("a:lstStyle"))
    ls.append(etree.fromstring(
        '<a:lvl2pPr xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:defRPr><a:solidFill><a:schemeClr val="bg1"/></a:solidFill></a:defRPr></a:lvl2pPr>'))
    path = synth.parent / "white.pptx"
    prs.save(path)
    d = TemplateDeck(path)
    d.add("content", title="T", body=["level one is fine"], notes=NOTES)
    with pytest.raises(TemplateError, match="invisible"):
        d.add("content", title="T", body=["ok", (1, "level two is white on white")], notes=NOTES)


def test_deck_passes_external_qc_without_critical(synth, tmp_path):
    d = TemplateDeck(synth)
    d.add("title", title="Deck title", subtitle="subtitle", notes=NOTES)
    d.add("content", title="Why recycle", body=["First point", "Second point"], notes=NOTES)
    d.add("two_content", title="Critique", body=[["Strength one"], ["Limit one"]], notes=NOTES)
    p = d.save(tmp_path / "qc.pptx")
    r = qc_deck.qc_deck(str(p), language=False, external_template=True)
    assert not r.critical, r.critical


# --------------------------------------------------------------------------- example slides ---
def test_add_from_example_replaces_text_keeps_formatting(synth, tmp_path):
    d = TemplateDeck(synth)
    img = _png(tmp_path / "fig.png", 400, 300, (10, 120, 200))
    d.add_from_example(2, {"Head": "Results", "Claim": ["Yield rose to 88%", "Rate rose 1.6-fold"], "Cap": "Fig. 1 Yield"},
                       pictures={"Sample photo": img}, notes=NOTES)
    p = d.save(tmp_path / "ex.pptx")
    prs = Presentation(p)
    assert len(prs.slides) == 1
    shapes = {s.name: s for s in prs.slides[0].shapes}
    assert shapes["Head"].text_frame.text == "Results"
    assert shapes["Head"].text_frame.paragraphs[0].runs[0].font.size.pt == 28            # original run properties kept
    assert [q.text for q in shapes["Claim"].text_frame.paragraphs] == ["Yield rose to 88%", "Rate rose 1.6-fold"]
    pic = [s for s in prs.slides[0].shapes if s.shape_type == 13]
    assert len(pic) == 1 and pic[0].name == "figure:fig"
    # the page number became a field, so it follows the slide
    assert shapes["PageNo"]._element.findall(".//" + qn("a:fld"))
    assert zipfile.ZipFile(p).testzip() is None


def test_add_from_example_refuses_leftover_sample_text(synth):
    d = TemplateDeck(synth)
    with pytest.raises(TemplateError, match="sample text"):
        d.add_from_example(2, {"Head": "Only the heading"}, notes=NOTES)
    d.add_from_example(2, {"Head": "Only the heading"}, unassigned="drop", notes=NOTES)
    d.add_from_example(2, {"Head": "H", "Claim": None, "Cap": "c"}, notes=NOTES)
    names = [s.name for s in d.prs.slides[-1].shapes]
    assert "Claim" not in names and "Head" in names


def test_add_from_example_fit_and_unknown_shape(synth):
    d = TemplateDeck(synth)
    with pytest.raises(TemplateError, match="does not fit"):
        d.add_from_example(2, {"Head": "Heading", "Claim": "very long claim " * 40, "Cap": "c"}, notes=NOTES)
    with pytest.raises(TemplateError, match="no text shape"):
        d.add_from_example(2, {"Nope": "x"}, notes=NOTES)
    assert len(d.prs.slides) == d.n_originals                # nothing added by the failed calls


def test_add_from_example_picture_must_not_cover_text(synth, tmp_path):
    d = TemplateDeck(synth)
    tall = _png(tmp_path / "tall.png", 300, 1200)
    # the sample photo sits left of 'Claim'; slide the claim text to x = 1 in so its line crosses the picture
    src = d.prs.slides[1]
    next(s for s in src.shapes if s.name == "Claim").left = Inches(1.0)
    with pytest.raises(TemplateError, match="would cover"):
        d.add_from_example(2, {"Head": "H", "Claim": "claim text long enough to reach the picture", "Cap": "c"},
                           pictures={"Sample photo": tall}, fit="contain", notes=NOTES)


# --------------------------------------------------------------------------- theme ---
def test_theme_from_template_is_theme_shaped_and_contrast_checked(synth):
    t = ta.theme_from_template(synth)
    assert set(t["palette"]) == set(db._PALETTE_KEYS)
    assert all(re.fullmatch(r"[0-9A-F]{6}", v) for v in t["palette"].values())
    assert t["all_pass"] and all(r["pass"] for r in t["contrast_report"])
    assert t["header_style"] in db.HEADER_STYLES
    # the draft pastes into THEMES unchanged: _theme() accepts it and builds a Theme
    (theme,) = eval(ta.theme_entry_source(t, "Synth Theme"), {"_theme": db._theme})
    assert isinstance(theme, db.Theme) and theme.name == "synth_theme"


def test_theme_from_dark_template_flips_text_to_light(synth, tmp_path):
    prs = Presentation(synth)
    m = prs.slide_masters[0]._element.find(qn("p:cSld"))
    old = m.find(qn("p:bg"))
    if old is not None:
        m.remove(old)
    m.insert(0, etree.fromstring('<p:bg xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
                                 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><p:bgPr><a:solidFill>'
                                 '<a:srgbClr val="101820"/></a:solidFill><a:effectLst/></p:bgPr></p:bg>'))
    dark = tmp_path / "dark.pptx"
    prs.save(dark)
    t = ta.theme_from_template(dark)
    assert t["bg"] == "101820"
    assert qc_layout.luminance(t["palette"]["body"]) > 0.5 and t["all_pass"]


# --------------------------------------------------------------------------- QC: slide size ---
def _big_deck(path, size=(20.0, 11.25), font="Calibri", pt=17, body="Plain English text.", notes=NOTES, pic_in=None):
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(size[0]), Inches(size[1])
    s = prs.slides.add_slide(prs.slide_layouts[6])
    tb = s.shapes.add_textbox(Inches(1), Inches(1), Inches(9), Inches(1))
    tb.text_frame.word_wrap = True
    tb.text_frame.text = body
    r = tb.text_frame.paragraphs[0].runs[0]
    r.font.name, r.font.size = font, Pt(pt)
    if pic_in:
        s.shapes.add_picture(str(_png(path.parent / "pic.png", 400, 300)), Inches(1), Inches(3), Inches(pic_in), Inches(pic_in * 0.75))
    if notes:
        s.notes_slide.notes_text_frame.text = notes
    prs.save(path)
    return path


def test_slide_geometry_reference_is_unchanged_and_scales_proportionally(tmp_path):
    ref = Presentation()
    ref.slide_width, ref.slide_height = Inches(13.333), Inches(7.5)
    g = qc_deck.slide_geometry(ref)
    assert (g["y_floor"], g["left"], g["right"], g["min_pic"], g["slide_w"]) == (
        qc_deck.Y_FLOOR, qc_deck.LEFT_MARGIN, qc_deck.RIGHT_EDGE, qc_deck.MIN_PICTURE, qc_deck.SLIDE_W)
    big = Presentation()
    big.slide_width, big.slide_height = Inches(20), Inches(11.25)
    g2 = qc_deck.slide_geometry(big)
    assert g2["y_floor"] / 914400 == pytest.approx(10.5, abs=0.01)
    assert g2["left"] / 914400 == pytest.approx(0.45, abs=0.01)
    assert g2["min_pic"] / 914400 == pytest.approx(4.5, abs=0.01)
    assert qc_layout.scaled_floor(7.5) == qc_layout.FLOOR_IN and qc_layout.scaled_floor(11.25) == pytest.approx(10.5)


def test_floor_and_picture_minimum_scale_with_the_slide(tmp_path):
    p = _big_deck(tmp_path / "big.pptx", font="Arial", pt=18, pic_in=3.5)
    r = qc_deck.qc_deck(str(p), language=False)
    assert any("picture below 4.5in" in c for c in r.critical)           # 3.5 in is legible on 13.3 in, not on 20 in
    p2 = _big_deck(tmp_path / "big2.pptx", font="Arial", pt=18, pic_in=4.8)
    assert not any("picture below" in c for c in qc_deck.qc_deck(str(p2), language=False).critical)
    # text at y = 9.4 in is far below the OLD 7.0 in floor but above the scaled 10.5 in floor
    prs = Presentation(p2)
    tb = prs.slides[0].shapes.add_textbox(Inches(1), Inches(9.4), Inches(9), Inches(0.8))
    tb.text_frame.word_wrap = True
    tb.text_frame.text = "Low text"
    tb.text_frame.paragraphs[0].runs[0].font.name = "Arial"
    tb.text_frame.paragraphs[0].runs[0].font.size = Pt(18)
    prs.save(tmp_path / "low.pptx")
    rr = qc_deck.qc_deck(str(tmp_path / "low.pptx"), language=False)
    assert not any("floor" in c for c in rr.critical)
    fs = qc_layout.check_layout(Presentation(tmp_path / "low.pptx"))
    assert not any(f.rule == "L1.floor" for f in fs)


def test_overflow_is_still_caught_on_a_big_slide(tmp_path):
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(20), Inches(11.25)
    s = prs.slides.add_slide(prs.slide_layouts[6])
    tb = s.shapes.add_textbox(Inches(1), Inches(9.5), Inches(6), Inches(1.0))
    tb.text_frame.word_wrap = True
    tb.text_frame.text = "overflowing line of text " * 30
    for r in tb.text_frame.paragraphs[0].runs:
        r.font.size, r.font.name = Pt(24), "Arial"
    s.notes_slide.notes_text_frame.text = NOTES
    prs.save(tmp_path / "of.pptx")
    fs = qc_layout.check_layout(Presentation(tmp_path / "of.pptx"))
    assert any(f.rule == "L1.floor" and f.severity == "CRITICAL" for f in fs)


# --------------------------------------------------------------------------- QC: --external-template ---
def test_external_template_switches_off_only_own_theme_checks(tmp_path):
    p = _big_deck(tmp_path / "ext.pptx", font="Calibri", pt=17)
    own = qc_deck.qc_deck(str(p), language=False)
    ext = qc_deck.qc_deck(str(p), language=False, external_template=True)
    assert any("Calibri" in c for c in own.critical) and any("17" in c and "type scale" in c for c in own.critical)
    assert not any("Calibri" in c or "type scale" in c or "disable_autofit" in c or "word_wrap" in c for c in ext.critical)
    assert not ext.critical, ext.critical


def test_external_template_keeps_hangul_notes_and_layout_checks(tmp_path):
    ko = _big_deck(tmp_path / "ko.pptx", body="한글 본문")
    assert any("Hangul" in c for c in qc_deck.qc_deck(str(ko), language=False, external_template=True).critical)
    nn = _big_deck(tmp_path / "nn.pptx", notes=None)
    assert any("missing speaker notes" in c for c in qc_deck.qc_deck(str(nn), language=False, external_template=True).critical)
    short = _big_deck(tmp_path / "sh.pptx", notes="짧은 노트")
    assert any("notes too short" in w for w in qc_deck.qc_deck(str(short), language=False, external_template=True).warning)
    # overflow (qc_layout) stays on: a 24 pt paragraph in a 1 in tall box
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(20), Inches(11.25)
    s = prs.slides.add_slide(prs.slide_layouts[6])
    tb = s.shapes.add_textbox(Inches(1), Inches(9.6), Inches(5), Inches(0.5))
    tb.text_frame.word_wrap = True
    tb.text_frame.text = "text that wraps and runs past the floor " * 12
    tb.text_frame.paragraphs[0].runs[0].font.size = Pt(24)
    s.notes_slide.notes_text_frame.text = NOTES
    prs.save(tmp_path / "of.pptx")
    assert qc_deck.qc_deck(str(tmp_path / "of.pptx"), language=False, external_template=True).critical
    # language gate stays on in external mode (foreign script in the body is CRITICAL)
    jp = _big_deck(tmp_path / "jp.pptx", body="\u65e5\u672c\u8a9e\u306e\u30c6\u30ad\u30b9\u30c8")
    assert any("QC-19" in c for c in qc_deck.qc_deck(str(jp), language=True, external_template=True).critical)


def test_external_template_contrast_is_judged_by_layout_qc(tmp_path):
    prs = Presentation()
    s = prs.slides.add_slide(prs.slide_layouts[6])
    tb = s.shapes.add_textbox(Inches(1), Inches(1), Inches(6), Inches(1))
    tb.text_frame.text = "white on white"
    run = tb.text_frame.paragraphs[0].runs[0]
    run.font.size = Pt(18)
    from pptx.dml.color import RGBColor
    run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    s.notes_slide.notes_text_frame.text = NOTES
    prs.save(tmp_path / "c.pptx")
    r = qc_deck.qc_deck(str(tmp_path / "c.pptx"), language=False, external_template=True)
    assert any("L3.contrast" in c for c in r.critical)


def test_style_fill_is_resolved_for_contrast(tmp_path):
    """White text on a shape whose fill comes only from p:style (fillRef) is legible, not a false alarm."""
    prs = Presentation()
    s = prs.slides.add_slide(prs.slide_layouts[6])
    from pptx.enum.shapes import MSO_SHAPE
    box = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1), Inches(1), Inches(4), Inches(1))
    sppr = box._element.find(qn("p:spPr"))
    for tag in ("a:solidFill", "a:noFill"):
        for e in sppr.findall(qn(tag)):
            sppr.remove(e)
    box.text_frame.text = "white on accent"
    from pptx.dml.color import RGBColor
    run = box.text_frame.paragraphs[0].runs[0]
    run.font.size, run.font.color.rgb = Pt(18), RGBColor(0xFF, 0xFF, 0xFF)
    prs.save(tmp_path / "s.pptx")
    fs = qc_layout.check_layout(Presentation(tmp_path / "s.pptx"))
    assert not [f for f in fs if f.rule == "L3.contrast" and f.severity == "CRITICAL"]


def test_deck_built_by_deck_is_checked_as_before(tmp_path):
    deck = db.Deck(footer_right="test")
    s = deck.title_slide("Title", "Citation line", "Journal 2026", "Presenter", "2026-10-04")
    deck.notes(s, NOTES)
    p = tmp_path / "d.pptx"
    deck.save(str(p))
    r = qc_deck.qc_deck(str(p), language=False)
    assert not r.critical, r.critical
    g = qc_deck.slide_geometry(Presentation(p))
    assert g["y_floor"] == qc_deck.Y_FLOOR and g["min_pic"] == qc_deck.MIN_PICTURE


# --------------------------------------------------------------------------- real templates (skip if absent) ---
REAL_FILES = {
    "eth": REAL / "converted" / "inst_eth_no_class.pptx",
    "k105": REAL / "github" / "SciToolsmith__journal-club-ppt" / "assets" / "k105-blue" / "reference.pptx",
    "minimalist": REAL / "slidescarnival" / "sc_minimalist-grayscale-pitch-deck.pptx",
    "market": REAL / "slidescarnival" / "sc_market-research-report-slides.pptx",
    "ucsd": REAL / "github" / "x3zou__UCSD_Defense_Template" / "ucsd_defense_template.pptx",
}


@pytest.mark.parametrize("key", sorted(REAL_FILES))
def test_real_template_inspect_and_theme(key):
    path = REAL_FILES[key]
    if not path.exists():
        pytest.skip(f"{path.name} not downloaded")
    d = ta.inspect_template(path)
    assert d["layouts"] and d["slide_width_in"] > 0
    t = ta.theme_from_template(path)
    assert set(t["palette"]) == set(db._PALETTE_KEYS) and t["all_pass"]


def test_real_minimalist_is_20_by_11_25_and_builds_clean(tmp_path):
    path = REAL_FILES["minimalist"]
    if not path.exists():
        pytest.skip("template not downloaded")
    d = TemplateDeck(path)
    assert (d.slide_w_in, d.slide_h_in) == (20.0, 11.25)
    d.add("CUSTOM_1", title="Cofactor recycling", body=["Journal club"], notes=NOTES, min_scale=0.3)
    d.add("CUSTOM_2", title="Why recycle", body=["Point one", "Point two"], picture=_png(tmp_path / "f.png", 1600, 900), notes=NOTES, min_scale=0.3)
    assert any("picture" in w for w in _layout_named(d, "CUSTOM_4").warnings)     # sample chart image drawn by the layout
    p = d.save(tmp_path / "m.pptx")
    r = qc_deck.qc_deck(str(p), language=False, external_template=True)
    assert not r.critical, r.critical


def test_real_eth_layouts_build_clean(tmp_path):
    path = REAL_FILES["eth"]
    if not path.exists():
        pytest.skip("template not downloaded")
    d = TemplateDeck(path)
    d.add("Titelfolie 04", title="A title", body=["subtitle"], notes=NOTES)
    d.add("Inhalt", title="Content", body=["a", (1, "b")], notes=NOTES)
    d.add("Inhalt Bild", title="Figure", picture=_png(tmp_path / "f.png", 1600, 900), notes=NOTES)
    with pytest.raises(TemplateError, match="invisible"):
        d.add("Schlussfolie", body=["a", (1, "white on white")], notes=NOTES)
    p = d.save(tmp_path / "e.pptx")
    assert not qc_deck.qc_deck(str(p), language=False, external_template=True).critical


def test_real_k105_example_path_builds_clean(tmp_path):
    path = REAL_FILES["k105"]
    if not path.exists():
        pytest.skip("template not downloaded")
    d = TemplateDeck(path)
    d.add_from_example(1, {0: "Cofactor recycling", 1: "Journal club", 2: "2026.10.04"}, notes=NOTES)
    d.add_from_example(2, {0: "Agenda", 1: "contents", 3: "A", 5: "B", 7: "C", 9: "D"}, keep=d.numeral_shapes(2), notes=NOTES)
    p = d.save(tmp_path / "k.pptx")
    prs = Presentation(p)
    assert len(prs.slides) == 2
    assert not qc_deck.qc_deck(str(p), language=False, external_template=True).critical
