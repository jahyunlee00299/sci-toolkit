"""extract_figures.py: raster figures are cropped caption-free, vector-only figures are reported."""
import io
import sys
from pathlib import Path

import fitz
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import extract_figures as E  # noqa: E402


def _png(w=600, h=400):
    b = io.BytesIO()
    Image.new("RGB", (w, h), (30, 90, 160)).save(b, "PNG")
    return b.getvalue()


@pytest.fixture()
def pdf(tmp_path):
    doc = fitz.open()
    p1 = doc.new_page()
    p1.insert_image(fitz.Rect(72, 100, 372, 300), stream=_png())
    p1.insert_text((72, 330), "Figure 1: A raster figure.", fontsize=10)
    p2 = doc.new_page()                       # vector-only figure: shapes, no image block
    p2.draw_rect(fitz.Rect(72, 100, 372, 300), color=(0, 0, 0), fill=(0.8, 0.8, 1))
    p2.insert_text((72, 330), "Figure 2: A vector figure.", fontsize=10)
    path = tmp_path / "paper.pdf"
    doc.save(str(path))
    return path


def test_raster_figure_cropped_without_caption(pdf, tmp_path):
    res = E.extract(pdf, tmp_path / "out")
    assert [(r["page"], r["label"]) for r in res] == [(1, "fig1")]
    pix = fitz.Pixmap(res[0]["path"])
    assert abs(pix.width / pix.height - 300 / 200) < 0.02       # figure only, caption text not in the clip


def test_vector_figure_is_reported_not_silently_dropped(pdf, tmp_path):
    res = E.extract(pdf, tmp_path / "out")
    miss = E.uncovered_captions(pdf, res)
    assert [(m["page"], m["label"]) for m in miss] == [(2, "fig2")]


def test_cli_warns_on_stderr(pdf, tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["extract_figures.py", str(pdf), "--out", str(tmp_path / "o")])
    E.main()
    cap = capsys.readouterr()
    assert "fig1" in cap.out and "WARNING: page 2 fig2" in cap.err
