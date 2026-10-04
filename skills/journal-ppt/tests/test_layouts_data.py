"""Data-family layouts: bento_kpi, giant_number, highlight_chips, comparison_cards, metric_strip.

Every layout is built under every theme and must pass qc_deck and qc_layout with 0 CRITICAL; negative
tests prove that content which cannot fit raises StyleError and empty lists are rejected.
"""
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from deck_builder import Deck, StyleError, THEMES  # noqa: E402
from layouts import LAYOUTS, load_all  # noqa: E402
from qc_deck import qc_deck  # noqa: E402
from qc_layout import check_layout, CRITICAL  # noqa: E402

KO = "한국어 발표 노트입니다. 이 슬라이드의 핵심 수치와 해석을 설명합니다. " * 6
FAMILY = ["bento_kpi", "giant_number", "highlight_chips", "comparison_cards", "metric_strip"]


def make_fig(path, size=(1600, 1000), title="progress curve"):
    """A plain PIL line plot (white canvas, axes, three curves); no matplotlib needed."""
    im = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(im)
    w, h = size
    l, t, r, b = int(w * 0.09), int(h * 0.08), int(w * 0.96), int(h * 0.86)
    d.line([(l, t), (l, b), (r, b)], fill=(40, 40, 40), width=4)
    for k, col in enumerate([(26, 53, 94), (232, 106, 26), (60, 140, 90)]):
        pts = []
        for i in range(0, 41):
            x = l + (r - l) * i / 40
            y = b - (b - t) * (0.2 + 0.2 * k) * (1 - 2.718 ** (-i / (7 + 4 * k))) * 1.3
            pts.append((x, y))
        d.line(pts, fill=col, width=7)
    im.save(path)
    return str(path)


@pytest.fixture(scope="module")
def figs(tmp_path_factory):
    d = tmp_path_factory.mktemp("figs")
    return dict(wide=make_fig(d / "wide.png"), square=make_fig(d / "square.png", (1200, 1200)),
                tall=make_fig(d / "tall.png", (900, 1400)))


TILES5 = [
    dict(label="Space-time yield", value="12.4", unit="g/L/h", delta="+38 % vs wild type",
         note="UDH variant K12, 30 °C, 5 mM NAD+", span=3),
    dict(label="Conversion", value="94.1", unit="%", delta="+6.2 pp", note="24 h, 200 mM substrate"),
    dict(label="Total turnover number", value="1,850", unit="", note="NAD+ recycled by NOX"),
    dict(label="Half-life at 40 °C", value="7.5", unit="h", delta="x2.1", note="Measured by activity loss"),
    dict(label="MPSP", value="3.1", unit="USD/kg", note="Bayesian-optimized design point"),
]
CLAIMS = [
    dict(chip="Cofactor recycling", text="NADH oxidase closes the redox loop, so NAD+ is needed only at 0.5 mol %."),
    dict(chip="Variant K12", text="One substitution lifts kcat/Km 4.3-fold on the non-native substrate."),
    dict(chip="BO in 18 runs", text="Expected-improvement search reaches the optimum with 18 experiments."),
]
CARDS = [
    dict(heading="Wild type", metric="3.1 g/L", metric_label="Titre after 24 h",
         rows=[("kcat (s⁻¹)", "1.9"), ("Km (mM)", "42"), ("Half-life (h)", "3.6")]),
    dict(heading="Variant K12 (ours)", metric="8.6 g/L", metric_label="Titre after 24 h", recommended=True,
         rows=[("kcat (s⁻¹)", "8.2"), ("Km (mM)", "19"), ("Half-life (h)", "7.5")]),
    dict(heading="Variant D55", metric="5.9 g/L", metric_label="Titre after 24 h",
         rows=[("kcat (s⁻¹)", "4.4"), ("Km (mM)", "27"), ("Half-life (h)", "5.0")]),
]
METRICS = [dict(value="94 %", label="Conversion at 24 h"), dict(value="12.4 g/L/h", label="Space-time yield"),
           dict(value="7.5 h", label="Half-life at 40 °C"), dict(value="3.1 USD/kg", label="MPSP")]


def build(deck, name, figs):
    if name == "bento_kpi":
        return deck.layout(name, title="Variant K12 beats wild type on every KPI", tiles=TILES5)
    if name == "giant_number":
        return deck.layout(name, number="4.3", unit="x", headline_a="One substitution lifts", headline_b="catalytic efficiency",
                           context="kcat/Km on the non-native substrate, 30 °C, pH 7.5.",
                           source_note="Source: Michaelis-Menten fits, n = 3 replicates.", kicker="Result 2")
    if name == "highlight_chips":
        return deck.layout(name, title="What this paper claims", claims=CLAIMS)
    if name == "comparison_cards":
        return deck.layout(name, title="Variant K12 is the recommended biocatalyst", cards=CARDS)
    if name == "metric_strip":
        return deck.layout(name, title="The optimized batch reaches 94 % conversion", metrics=METRICS,
                           figure=figs["wide"], caption="Fig. 3. Progress curves of the optimized batch (n = 3).")
    raise AssertionError(name)


def _save(deck, tmp_path, tag):
    p = tmp_path / f"{tag}.pptx"
    deck.save(str(p))
    return str(p)


@pytest.mark.parametrize("theme", sorted(THEMES))
@pytest.mark.parametrize("name", FAMILY)
def test_layout_passes_qc_under_every_theme(name, theme, figs, tmp_path):
    d = Deck(theme=theme)
    s = build(d, name, figs)
    d.notes(s, KO)
    path = _save(d, tmp_path, f"{name}_{theme}")
    rep = qc_deck(path, layout=True)
    assert not rep.critical, rep.critical
    crit = [f for f in check_layout(Presentation(path), theme) if f.severity == CRITICAL]
    assert not crit, [str(f) for f in crit]


def test_registered_as_data_family():
    load_all()
    for n in FAMILY:
        assert n in LAYOUTS and LAYOUTS[n].kind == "data" and LAYOUTS[n].source


def test_extra_size_declared_where_stat_big_is_used():
    load_all()
    for n in ("bento_kpi", "giant_number", "comparison_cards"):
        assert 54 in LAYOUTS[n].extra_sizes
    for n in ("highlight_chips", "metric_strip"):
        assert not LAYOUTS[n].extra_sizes


def test_decor_shapes_named_and_autofit_off(figs, tmp_path):
    d = Deck(theme="navy_lab")
    for n in FAMILY:
        s = build(d, n, figs)
        d.notes(s, KO)
        for shp in s.shapes:
            if shp.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE and shp.name != "header_bar":
                assert shp.name.startswith("deco:"), shp.name
                assert shp.text_frame.word_wrap
                assert shp.text_frame._txBody.find(
                    "{http://schemas.openxmlformats.org/drawingml/2006/main}bodyPr").find(
                    "{http://schemas.openxmlformats.org/drawingml/2006/main}noAutofit") is not None


# ----------------------------------------------------------------------------- figure rules
def test_bento_figure_tile_keeps_aspect_and_three_inches(figs, tmp_path):
    d = Deck(theme="navy_lab")
    s = d.layout("bento_kpi", title="Progress curves and KPIs", tiles=TILES5[:3], figure=figs["wide"],
                 figure_label="Progress curves", figure_note="Fig. 2. Product titer over 24 h (n = 3).")
    d.notes(s, KO)
    pic = [p for p in s.shapes if p.shape_type == MSO_SHAPE_TYPE.PICTURE][0]
    assert abs(pic.width / pic.height - 1.6) < 0.01
    assert max(pic.width, pic.height) >= 914400 * 3
    assert not qc_deck(_save(d, tmp_path, "bf"), layout=True).critical


def test_metric_strip_figure_keeps_aspect_and_three_inches(figs, tmp_path):
    for key, ratio in (("wide", 1.6), ("square", 1.0), ("tall", 900 / 1400)):
        d = Deck(theme="journal_print")
        s = d.layout("metric_strip", title="The optimized batch reaches 94 % conversion", metrics=METRICS,
                     figure=figs[key], caption="Fig. 3. Progress curves.")
        d.notes(s, KO)
        pic = [p for p in s.shapes if p.shape_type == MSO_SHAPE_TYPE.PICTURE][0]
        assert abs(pic.width / pic.height - ratio) < 0.01
        assert max(pic.width, pic.height) >= 914400 * 3


# ----------------------------------------------------------------------------- negative tests
@pytest.mark.parametrize("name,kw", [
    ("bento_kpi", dict(tiles=[])), ("highlight_chips", dict(claims=[])),
    ("comparison_cards", dict(cards=[])), ("metric_strip", dict(metrics=[])),
])
def test_empty_list_rejected(name, kw, figs):
    extra = dict(figure=figs["wide"]) if name == "metric_strip" else {}
    with pytest.raises(StyleError):
        Deck().layout(name, title="t", **kw, **extra)


def test_wrong_counts_rejected(figs):
    with pytest.raises(StyleError):
        Deck().layout("bento_kpi", title="t", tiles=TILES5 + TILES5[:3])          # 8 tiles
    with pytest.raises(StyleError):
        Deck().layout("bento_kpi", title="t", tiles=TILES5[:2])                   # 2 tiles
    with pytest.raises(StyleError):
        Deck().layout("bento_kpi", title="t", tiles=TILES5[:5], figure=figs["wide"])   # figure + 5 tiles
    with pytest.raises(StyleError):
        Deck().layout("comparison_cards", title="t", cards=CARDS[:1])
    with pytest.raises(StyleError):
        Deck().layout("highlight_chips", title="t", claims=CLAIMS * 2)


def test_overlong_text_raises_instead_of_overflowing(figs):
    long_note = "This note is deliberately far too long for a bento tile. " * 8
    tiles = [dict(TILES5[0], note=long_note)] + TILES5[1:3]
    with pytest.raises(StyleError):
        Deck().layout("bento_kpi", title="t", tiles=tiles)
    with pytest.raises(StyleError):
        Deck().layout("bento_kpi", title="t", tiles=[dict(TILES5[0], value="1234567890" * 6)] + TILES5[1:3])
    with pytest.raises(StyleError):
        Deck().layout("highlight_chips", title="t",
                      claims=[dict(chip="K", text="word " * 120)] + CLAIMS[1:])
    with pytest.raises(StyleError):
        Deck().layout("highlight_chips", title="t",
                      claims=[dict(chip="A chip label that cannot possibly fit one pill line at 18 pt bold", text="x")] + CLAIMS[1:])
    with pytest.raises(StyleError):
        Deck().layout("giant_number", number="4.3", unit="x", headline_a="word " * 80, headline_b="b")
    with pytest.raises(StyleError):
        Deck().layout("comparison_cards", title="t",
                      cards=[dict(CARDS[0], heading="Heading " * 30)] + CARDS[1:])
    with pytest.raises(StyleError):
        Deck().layout("metric_strip", title="t", figure=figs["wide"],
                      metrics=[dict(value="1234567890 g/L/h units", label="x")] * 5)


def test_missing_fields_and_double_recommendation(figs):
    with pytest.raises(StyleError):
        Deck().layout("bento_kpi", title="t", tiles=[dict(label="a", value="")] + TILES5[1:3])
    with pytest.raises(StyleError):
        Deck().layout("comparison_cards", title="t", cards=[dict(c, recommended=True) for c in CARDS])
    with pytest.raises(StyleError):
        Deck().layout("comparison_cards", title="t", cards=[dict(CARDS[0], rows=CARDS[0]["rows"][:2])] + CARDS[1:])
    with pytest.raises(StyleError):
        Deck().layout("giant_number", number="", headline_a="x")


def test_picture_helper_refuses_a_figure_under_three_inches(figs):
    from layouts.data import _picture
    prs = Deck().prs
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    with pytest.raises(StyleError):
        _picture(slide, figs["wide"], 1.0, 1.0, 2.8, 2.0)          # 2.8 x 1.75 in -> longer side < 3 in
    left, top, w, h = _picture(slide, figs["wide"], 1.0, 1.0, 4.0, 4.0)
    assert abs(w / h - 1.6) < 0.01 and max(w, h) >= 3.0


def test_figure_tile_always_at_least_three_inches(figs, tmp_path):
    for key in ("wide", "square", "tall"):
        for n in (3, 4):
            d = Deck()
            s = d.layout("bento_kpi", title="t", tiles=TILES5[:n], figure=figs[key], figure_label="Fig", figure_note="n = 3")
            pic = [p for p in s.shapes if p.shape_type == MSO_SHAPE_TYPE.PICTURE][0]
            assert max(pic.width, pic.height) >= 914400 * 3
