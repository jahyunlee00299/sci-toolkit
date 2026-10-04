"""Mutation test for journal-ppt qc_deck.py: build a clean deck, inject one defect at a time,
report which defects the gate catches (CRITICAL/WARNING) and which slip through."""
import sys, copy, io, contextlib
from pathlib import Path
SK = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SK))
from deck_builder import Deck
import json
from qc_deck import qc_deck, _merge_numbers
from pptx import Presentation
from pptx.util import Pt, Inches, Emu
from pptx.dml.color import RGBColor
from PIL import Image

W = Path.home() / "scratch" / "jppt_mut"  # regression: python tests/mutation_suite.py (expect caught=18 of 18)
W.mkdir(parents=True, exist_ok=True)
fig = W / "fig.png"
Image.new("RGB", (1600, 900), (200, 220, 240)).save(fig)
KO = "한국어 발표 노트입니다. " * 12


def build(path):
    d = Deck(footer_right="Test et al., J Test 2026")
    d.title_slide("Test Title", "Test et al. (2026)", "J Test 1:1-2 -- DOI", "J. Lee", "2026-10-04")
    d.notes(d.prs.slides[0], KO)
    s = d.content_slide("Background")
    d.bullets(s, ["Yield reached 85% in 3 h.", "kcat = 12 s-1 at 30 C.", "Third point."], role="body")
    d.notes(s, KO)
    s2 = d.figure_slide("Result", "Sub", ["Point A", "Point B"], str(fig), "Figure 1. Caption.")
    d.notes(s2, KO)
    s3 = d.references_slide(["Ref one.", "Ref two."])
    d.notes(s3, KO)
    d.save(str(path))


def first_body(prs, idx=1):
    sl = prs.slides[idx]
    for sh in sl.shapes:
        if sh.has_text_frame and "Yield" in sh.text_frame.text:
            return sl, sh
    raise RuntimeError


def run_of(sh):
    return sh.text_frame.paragraphs[0].runs[0]


def m_hangul(p):
    _, sh = first_body(p); run_of(sh).text = "수율 85% 달성"
def m_font13(p):
    _, sh = first_body(p); run_of(sh).font.size = Pt(13)
def m_calibri(p):
    _, sh = first_body(p); run_of(sh).font.name = "Calibri"
def m_below_floor(p):
    _, sh = first_body(p); sh.top = Inches(6.9); sh.height = Inches(0.9)
def m_linesp(p):
    _, sh = first_body(p); sh.text_frame.paragraphs[0].line_spacing = 1.3
def m_number_drift(p):  # text says 85% but source says 58% -- semantic
    _, sh = first_body(p); run_of(sh).text = "• Yield reached 95% in 3 h."
def m_overflow_text(p):  # 40 words into a 0.4in box, still inside slide bounds
    _, sh = first_body(p); sh.height = Inches(0.4)
    run_of(sh).text = "• " + "This bullet is intentionally very long and wraps many times. " * 6
def m_overlap(p):  # picture on top of the bullets
    sl, sh = first_body(p)
    sl.shapes.add_picture(str(fig), sh.left, sh.top, Inches(6), Inches(3.4))
def m_lowcontrast(p):  # allowed palette color, but near-invisible on its fill
    sl, sh = first_body(p); run_of(sh).font.color.rgb = RGBColor(0xDB, 0xE8, 0xF7)
def m_offpalette_fill(p):
    sl, _ = first_body(p)
    r = sl.shapes.add_shape(1, Inches(9), Inches(2), Inches(2), Inches(1))
    r.fill.solid(); r.fill.fore_color.rgb = RGBColor(0xFF, 0x00, 0xFF)
    r.text_frame.word_wrap = True
    from pptx.oxml.ns import qn
    from lxml import etree
    etree.SubElement(r.text_frame._txBody.find(qn('a:bodyPr')), qn('a:noAutofit'))
def m_placeholder(p):
    _, sh = first_body(p); run_of(sh).text = "• Lorem ipsum dolor sit amet XXXX"
def m_stretched_pic(p):
    sl = p.slides[2]
    for sh in sl.shapes:
        if sh.shape_type == 13:
            sh.width = int(sh.width * 0.5)
def m_nomenclature(p):
    _, sh = first_body(p); run_of(sh).text = "• NAD+ and 5uM Km, E. coli, 30°C"
def m_too_many_bullets(p):
    sl, sh = first_body(p)
    tf = sh.text_frame
    for i in range(10):
        q = tf.add_paragraph(); q.text = f"extra bullet {i}"
        q.runs[0].font.size = Pt(16); q.runs[0].font.name = "Arial"; q.line_spacing = 2.0
def m_notes_english(p):
    sl, _ = first_body(p); sl.notes_slide.notes_text_frame.text = "English only notes " * 10
def m_empty_slide(p):
    p.slides.add_slide(p.slide_layouts[6])
def m_hidden_slide(p):
    p.slides[1]._element.set("show", "0")
def m_no_alt_text(p):
    pass  # no alt-text mechanism in builder at all -> report as design gap, not mutation
def m_wrong_slide_order(p):
    lst = p.slides._sldIdLst; items = list(lst)
    lst.remove(items[-1]); lst.insert(0, items[-1])  # refs slide first

MUTS = [
    ("M01 Hangul in slide body", m_hangul, "must catch"),
    ("M02 off-scale font 13pt", m_font13, "must catch"),
    ("M03 font Calibri", m_calibri, "must catch"),
    ("M04 shape crosses Y=7.0 floor", m_below_floor, "must catch"),
    ("M05 line_spacing 1.3", m_linesp, "must catch"),
    ("M06 notes English only", m_notes_english, "must catch"),
    ("M07 NUMBER DRIFT 85%->95%", m_number_drift, "semantic"),
    ("M08 text overflows its box", m_overflow_text, "layout"),
    ("M09 picture overlaps text", m_overlap, "layout"),
    ("M10 low-contrast text", m_lowcontrast, "design"),
    ("M11 off-palette magenta fill", m_offpalette_fill, "design"),
    ("M12 placeholder Lorem/XXXX", m_placeholder, "content"),
    ("M13 picture aspect stretched", m_stretched_pic, "design"),
    ("M14 nomenclature NAD+/5uM/30C", m_nomenclature, "content"),
    ("M15 10 extra bullets", m_too_many_bullets, "layout"),
    ("M16 blank slide appended", m_empty_slide, "structure"),
    ("M17 slide hidden", m_hidden_slide, "structure"),
    ("M18 references slide moved first", m_wrong_slide_order, "structure"),
]

SRC = W / "content_analysis.json"
SRC.write_text(json.dumps({"title":"T","validated_numbers":[
  {"claim":"yield 85% in 3 h","value":85,"unit":"%","match":True,"source":"Fig 1"},
  {"claim":"3 h","value":3,"unit":"h","match":True,"source":"Fig 1"},
  {"claim":"kcat 12 s-1","value":12,"unit":"s-1","match":True,"source":"Table 1"},
  {"claim":"30 C","value":30,"unit":"°C","match":True,"source":"Methods"}]}),encoding="utf-8")
def evaluate(path):
    r = qc_deck(str(path))
    _merge_numbers(r, str(path), str(SRC), None, False)
    return r
base = W / "clean.pptx"
build(base)
r0 = evaluate(base)
print(f"BASELINE clean deck: CRIT={len(r0.critical)} WARN={len(r0.warning)}")
for m in r0.critical + r0.warning:
    print("   ", m)

print()
print(f"{'mutation':38s} {'class':9s} {'result':10s} detail")
caught = missed = 0
for name, fn, cls in MUTS:
    p = W / "mut.pptx"
    build(p)
    prs = Presentation(str(p)); fn(prs); prs.save(str(p))
    r = evaluate(p)
    new_c = [m for m in r.critical if m not in r0.critical]
    new_w = [m for m in r.warning if m not in r0.warning and not m.startswith("DISPERSION")]
    if new_c:
        res, det = "CRITICAL", new_c[0][:70]
    elif new_w:
        res, det = "warn", new_w[0][:70]
    else:
        res, det = "MISSED", ""
    if res == "MISSED": missed += 1
    else: caught += 1
    print(f"{name:38s} {cls:9s} {res:10s} {det}")
print(f"\ncaught={caught} missed={missed} of {len(MUTS)}")
