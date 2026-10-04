#!/usr/bin/env python3
"""
extract_figures.py -- lab standard S7: crop figures out of a paper PDF by their
IMAGE BLOCKS (PyMuPDF text-dict block type == 1), caption-free, 300 DPI.

Why a new script: ~/.claude/skills/pptx/scripts/extract_figures.py (whitespace-band
auto-detect / manual fractional boxes) and references/paper_download.md
(`doc.extract_image`, page render + hand crop) both exist and stay valid fallbacks, but
neither crops by image block: the whitespace detector swallows the caption text under a
figure, and extract_image returns raw embedded rasters without page layout (multi-panel
figures arrive as dozens of fragments). This helper only adds the missing mode; for
vector-only schemes (no image blocks) fall back to the pptx skill's `--spec` manual crops.

Algorithm
  1. page.get_text("dict")["blocks"], keep blocks with type == 1 (image) whose bbox is at
     least --min-size inches on both sides (drops logos/icons/rules).
  2. Merge image blocks whose boxes overlap or lie within --merge-gap points of each other
     (panels of one multi-panel figure).
  3. Clip the page render to that union box only -- text blocks (type == 0, i.e. the
     caption and body text) are never part of the clip, so the crop is caption-free.
  4. Render with get_pixmap(matrix=dpi/72, clip=box) -> PNG, 300 DPI by default.
  5. Name the file after the nearest "Fig./Figure/Scheme N" caption text block (below the
     figure first, then above); fall back to p<page>_<k>.

Usage
    python extract_figures.py paper.pdf --out assets/ [--pages 3-6] [--dpi 300]
Prints one line per saved file: path, size in px, page, caption label, caption text.
Captions that got no crop (vector figures) are listed as WARNING lines on stderr.
Requires: pip install pymupdf
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover
    print("ERROR: pip install pymupdf", file=sys.stderr)
    sys.exit(1)

CAPTION_RE = re.compile(r'^\s*(Fig(?:ure)?s?\.?|Scheme|Chart)\s*(S?\d+)', re.IGNORECASE)


def image_blocks(page, min_size_in: float = 1.0) -> list:
    """bbox (fitz.Rect) of every type==1 block at least min_size_in on both sides."""
    min_pt = min_size_in * 72
    out = []
    for b in page.get_text("dict")["blocks"]:
        if b.get("type") != 1:
            continue
        r = fitz.Rect(b["bbox"])
        if r.width >= min_pt and r.height >= min_pt:
            out.append(r)
    return out


def merge_boxes(boxes: list, gap_pt: float = 12.0) -> list:
    """Union boxes that overlap or sit within gap_pt of each other (transitively)."""
    boxes = [fitz.Rect(b) for b in boxes]
    merged = True
    while merged:
        merged = False
        out = []
        for b in boxes:
            for o in out:
                grown = fitz.Rect(o.x0 - gap_pt, o.y0 - gap_pt, o.x1 + gap_pt, o.y1 + gap_pt)
                if grown.intersects(b):
                    o |= b
                    merged = True
                    break
            else:
                out.append(fitz.Rect(b))
        boxes = out
    return sorted(boxes, key=lambda r: (round(r.y0), r.x0))


def caption_blocks(page) -> list:
    """[(rect, label, text)] for text blocks that start like a figure caption."""
    caps = []
    for b in page.get_text("dict")["blocks"]:
        if b.get("type") != 0:
            continue
        text = " ".join(span["text"] for ln in b["lines"] for span in ln["spans"]).strip()
        m = CAPTION_RE.match(text)
        if m:
            kind = m.group(1).rstrip(".").lower()
            kind = "scheme" if kind.startswith("scheme") else ("chart" if kind.startswith("chart") else "fig")
            caps.append((fitz.Rect(b["bbox"]), f"{kind}{m.group(2).lower()}", text))
    return caps


def nearest_caption(box, caps):
    """Caption directly below the figure first (journal default), else the closest above."""
    below = [c for c in caps if c[0].y0 >= box.y1 - 2 and c[0].x0 < box.x1 and c[0].x1 > box.x0]
    if below:
        return min(below, key=lambda c: c[0].y0 - box.y1)
    above = [c for c in caps if c[0].y1 <= box.y0 + 2 and c[0].x0 < box.x1 and c[0].x1 > box.x0]
    if above:
        return min(above, key=lambda c: box.y0 - c[0].y1)
    return None


def extract(pdf_path, out_dir, pages=None, dpi: int = 300, min_size_in: float = 1.0,
            merge_gap_pt: float = 12.0) -> list[dict]:
    """Crop every figure; returns [{path, page, label, caption, width_px, height_px, bbox}]."""
    doc = fitz.open(str(pdf_path))
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    zoom = dpi / 72.0
    results = []
    page_ids = pages if pages else range(len(doc))
    for pi in page_ids:
        if pi >= len(doc):
            continue
        page = doc[pi]
        boxes = merge_boxes(image_blocks(page, min_size_in), merge_gap_pt)
        caps = caption_blocks(page)
        for k, box in enumerate(boxes, start=1):
            box = box & page.rect
            cap = nearest_caption(box, caps)
            label = cap[1] if cap else f"p{pi + 1}_{k}"
            name = f"{label}_p{pi + 1}.png"
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=box, alpha=False)
            path = out_dir / name
            pix.save(str(path))
            results.append(dict(path=str(path), page=pi + 1, label=label,
                                caption=cap[2][:200] if cap else "",
                                width_px=pix.width, height_px=pix.height,
                                bbox=tuple(round(v, 1) for v in box)))
    doc.close()
    return results


def uncovered_captions(pdf_path, results, pages=None) -> list[dict]:
    """Caption-like text blocks with no crop attached: [{page, label, caption}].

    A figure drawn as vectors has no image block, so extract() skips it without a word. A caption
    that no crop claimed marks such a figure (or a body paragraph that merely starts with
    "Figure N", hence "candidate"); the caller prints these so nothing disappears silently."""
    claimed = {(r["page"], r["label"]) for r in results}
    doc = fitz.open(str(pdf_path))
    out = []
    for pi in (pages if pages else range(len(doc))):
        if pi >= len(doc):
            continue
        for _, label, text in caption_blocks(doc[pi]):
            if (pi + 1, label) not in claimed:
                out.append(dict(page=pi + 1, label=label, caption=text[:200]))
    doc.close()
    return out


def _parse_pages(spec: str) -> list[int]:
    out = []
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a) - 1, int(b)))
        else:
            out.append(int(part) - 1)
    return sorted(set(out))


def main():
    ap = argparse.ArgumentParser(description="S7: image-block (type==1) figure crops, caption-free, 300 DPI")
    ap.add_argument("pdf")
    ap.add_argument("--out", required=True)
    ap.add_argument("--pages", help="1-based, e.g. '2,3,5-7' (default: all)")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--min-size", type=float, default=1.0, help="min block side in inches (default 1.0)")
    ap.add_argument("--merge-gap", type=float, default=12.0, help="merge distance in points (default 12)")
    a = ap.parse_args()
    if not Path(a.pdf).exists():
        print(f"ERROR: PDF not found: {a.pdf}", file=sys.stderr)
        sys.exit(2)
    res = extract(a.pdf, a.out, _parse_pages(a.pages) if a.pages else None, a.dpi,
                  a.min_size, a.merge_gap)
    for r in res:
        print(f"{r['path']}  {r['width_px']}x{r['height_px']}px  page {r['page']}  "
              f"{r['label']}  | {r['caption'][:80]}")
    page_ids = _parse_pages(a.pages) if a.pages else None
    for u in uncovered_captions(a.pdf, res, page_ids):
        print(f"WARNING: page {u['page']} {u['label']}: caption but no image block cropped "
              f"(vector figure? crop it with the pptx skill's --spec) | {u['caption'][:70]}",
              file=sys.stderr)
    if not res:
        print("no image blocks found (vector-only figures? use ~/.claude/skills/pptx/scripts/"
              "extract_figures.py --spec for manual crops)")
        sys.exit(1)


if __name__ == "__main__":
    main()
