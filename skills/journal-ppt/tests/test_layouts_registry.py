"""Layout registry + dispatcher + qc size allowance."""
import sys
from pathlib import Path

import pytest
from pptx.util import Inches

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from deck_builder import Deck, StyleError, STAT_BIG_PT, ROLES  # noqa: E402
from layouts import LAYOUTS, register, list_layouts  # noqa: E402
from qc_deck import qc_deck  # noqa: E402

KO = "한국어 발표 노트입니다. " * 12


@register("_probe_big", kind="data", summary="test layout using stat_big", extra_sizes=(STAT_BIG_PT,))
def _probe_big(deck, number="3.2x", title="Probe"):
    s = deck.content_slide(title)
    deck.add_textbox(s, Inches(1), Inches(2), Inches(6), Inches(2), number, role="stat_big")
    return s


@register("_probe_plain", kind="content", summary="test layout without extra sizes")
def _probe_plain(deck, title="Plain"):
    return deck.content_slide(title)


def _deck_with(name):
    d = Deck()
    d.title_slide("T", "c", "j", "p", "2026-10-04"); d.notes(d.prs.slides[0], KO)
    s = d.layout(name); d.notes(s, KO)
    return d


def test_unknown_layout_rejected():
    with pytest.raises(StyleError):
        Deck().layout("nope")


def test_duplicate_registration_rejected():
    with pytest.raises(ValueError):
        register("_probe_plain", kind="content", summary="dup")(lambda d: None)


def test_extra_size_allowed_only_when_declared(tmp_path):
    p = tmp_path / "a.pptx"; _deck_with("_probe_big").save(str(p))
    assert not [m for m in qc_deck(str(p), layout=False).critical if "54" in m]
    # the same role outside a declaring layout is refused at build time
    d = Deck(); s_ = d.content_slide("x")
    with pytest.raises(StyleError):
        d.add_textbox(s_, Inches(1), Inches(2), Inches(6), Inches(2), "3.2x", role="stat_big")


def test_listing():
    names = {x["name"] for x in list_layouts()}
    assert {"_probe_big", "_probe_plain"} <= names
