#!/usr/bin/env python
"""pfd_render.py — Render Block Flow Diagram / Process Flow Diagram for
enzymatic cascade bioprocesses.

BFD-level with major unit-op blocks + stream labels. Symbols are simplified
ISA S5.1-inspired rectangles for blocks, parallelograms for separators. Later
iterations can swap to true ISA symbols (reactor circle, distillation column,
etc.).

The PROCESS_SPECS dict below ships two generic example cascades — replace the
block/stream/utility entries with your own process to render its diagram.

CLI:
  python pfd_render.py --cascade cascade_a --out runs/pfd/
"""
from __future__ import annotations

# Windows' default console is cp949 and dies on non-ASCII/symbol output. Force UTF-8.
# Use reconfigure: wrapping in a TextIOWrapper takes ownership of the underlying
# stream, so once this module is imported, GC'ing the wrapper closes the
# caller's stdout too (measured).
import sys as _sys
for _s in (_sys.stdout, _sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Polygon, Circle, Rectangle


# ============================================================
# Process specs (BFD level)
# ============================================================

# Two generic example cascades. Each entry is plain data consumed by
# render_pfd(); swap in your own blocks/streams/utilities to draw a real process.
PROCESS_SPECS = {
    "cascade_a": {
        "title": "Example cascade A · biomass to crystalline product",
        "blocks": [
            {"id": "feed",    "kind": "feed",     "label": "Biomass\nfeed",          "x":  0.5,  "y": 1},
            {"id": "pretreat","kind": "block",    "label": "Pretreat",              "x":  3.0,  "y": 1},
            {"id": "hydrol",  "kind": "block",    "label": "Enzymatic\nhydrolysis", "x":  5.5,  "y": 1},
            {"id": "desalt1", "kind": "block",    "label": "Desalt\n(SAC)",         "x":  8.0,  "y": 1},
            {"id": "react",   "kind": "reactor",  "label": "Cascade\nreactor",      "x": 10.7,  "y": 1, "focal": True},
            {"id": "desalt2", "kind": "block",    "label": "Mixed-bed IX",          "x": 13.4,  "y": 1},
            {"id": "evap",    "kind": "block",    "label": "Evaporator",            "x": 15.9,  "y": 1},
            {"id": "cryst",   "kind": "separator","label": "Crystallizer",          "x": 18.4,  "y": 1},
            {"id": "product", "kind": "product",  "label": "Product\n>99%",         "x": 20.9,  "y": 1},
        ],
        "streams": [
            ("feed",    "pretreat", "S1"),
            ("pretreat","hydrol",   "S2 slurry"),
            ("hydrol",  "desalt1",  "S3 sugar+salt"),
            ("desalt1", "react",    "S4 substrate"),
            ("react",   "desalt2",  "S5 product+cofactor salt"),
            ("desalt2", "evap",     "S6 product soln."),
            ("evap",    "cryst",    "S7 concentrate"),
            ("cryst",   "product",  "S8 crystal"),
        ],
        "utilities": [
            {"to": "react", "label": "Cofactor salt",  "from_y": 2.6, "offset_x": -0.7},
            {"to": "react", "label": "Air (O2)",       "from_y": 2.6, "offset_x":  0.7},
        ]
    },
    "cascade_b": {
        "title": "Example cascade B · redox cascade with chiral separation",
        "blocks": [
            {"id": "feed",   "kind": "feed",    "label": "Substrate\nfeed",                      "x":  0.5, "y": 1},
            {"id": "react",  "kind": "reactor", "label": "Redox cascade\nreactor",               "x":  4.0, "y": 1, "focal": True},
            {"id": "desalt", "kind": "block",   "label": "Desalt / IEX\n(salt removal)",         "x":  7.5, "y": 1},
            {"id": "chrom",  "kind": "block",   "label": "Chromatography\n(isomer separation)",  "x": 10.5, "y": 1},
            {"id": "cryst",  "kind": "separator","label": "Crystallization",                     "x": 13.5, "y": 1},
            {"id": "product","kind": "product", "label": "Product\n>99% ee",                     "x": 16.0, "y": 1},
        ],
        "streams": [
            ("feed",   "react",   "S1 substrate"),
            ("react",  "desalt",  "S2 product+intermediate+cofactor salt"),
            ("desalt", "chrom",   "S3"),
            ("chrom",  "cryst",   "S4 product"),
            ("cryst",  "product", "S5"),
        ],
        "utilities": [
            {"to": "react", "label": "Cofactor salt",  "from_y": 2.6, "offset_x": -0.8},
            {"to": "react", "label": "Air (O2)",       "from_y": 2.6, "offset_x":  0.8},
        ]
    },
}


# ============================================================
# Drawing primitives
# ============================================================

BLOCK_W = 1.7
BLOCK_H = 0.95


def draw_block(ax, b, color_focal="#b5523a", color_fill_focal="#f6e5dc"):
    x, y = b["x"], b["y"]
    kind = b["kind"]
    focal = b.get("focal", False)
    label = b["label"]

    if kind == "feed":
        # Trapezoid pointing right (input)
        verts = [(x-BLOCK_W/2, y-BLOCK_H/2),
                 (x+BLOCK_W/2-0.18, y-BLOCK_H/2),
                 (x+BLOCK_W/2, y),
                 (x+BLOCK_W/2-0.18, y+BLOCK_H/2),
                 (x-BLOCK_W/2, y+BLOCK_H/2)]
        poly = Polygon(verts, closed=True, fc="#fff5e6",
                       ec="#b08800", lw=1.2)
        ax.add_patch(poly)
    elif kind == "product":
        # Trapezoid pointing left (output / cup shape)
        verts = [(x-BLOCK_W/2+0.18, y-BLOCK_H/2),
                 (x+BLOCK_W/2, y-BLOCK_H/2),
                 (x+BLOCK_W/2, y+BLOCK_H/2),
                 (x-BLOCK_W/2+0.18, y+BLOCK_H/2),
                 (x-BLOCK_W/2, y)]
        poly = Polygon(verts, closed=True, fc="#e8f5e9",
                       ec="#3a8d5b", lw=1.2)
        ax.add_patch(poly)
    elif kind == "reactor":
        fill = color_fill_focal if focal else "#ffffff"
        edge = color_focal if focal else "#1c1917"
        # rounded rect, taller for emphasis
        rect = FancyBboxPatch(
            (x-BLOCK_W*0.6, y-BLOCK_H*0.7),
            BLOCK_W*1.2, BLOCK_H*1.4,
            boxstyle="round,pad=0,rounding_size=0.12",
            linewidth=1.4, edgecolor=edge, facecolor=fill)
        ax.add_patch(rect)
    elif kind == "separator":
        # parallelogram
        verts = [(x-BLOCK_W/2-0.12, y-BLOCK_H/2),
                 (x+BLOCK_W/2-0.12, y-BLOCK_H/2),
                 (x+BLOCK_W/2+0.12, y+BLOCK_H/2),
                 (x-BLOCK_W/2+0.12, y+BLOCK_H/2)]
        poly = Polygon(verts, closed=True, fc="#ffffff",
                       ec="#1c1917", lw=1.0)
        ax.add_patch(poly)
    else:  # generic block
        rect = FancyBboxPatch(
            (x-BLOCK_W/2, y-BLOCK_H/2),
            BLOCK_W, BLOCK_H,
            boxstyle="round,pad=0,rounding_size=0.06",
            linewidth=1.0, edgecolor="#1c1917", facecolor="#ffffff")
        ax.add_patch(rect)

    ax.text(x, y, label, family="Arial", size=8, weight="bold",
            ha="center", va="center", color="#1c1917")


def draw_stream(ax, blocks_by_id, src, dst, label):
    sb = blocks_by_id[src]; db = blocks_by_id[dst]
    x0 = sb["x"] + BLOCK_W*0.5 + 0.05
    x1 = db["x"] - BLOCK_W*0.5 - 0.05
    if sb["kind"] == "reactor":
        x0 = sb["x"] + BLOCK_W*0.6 + 0.05
    if db["kind"] == "reactor":
        x1 = db["x"] - BLOCK_W*0.6 - 0.05
    y = sb["y"]
    arrow = FancyArrowPatch((x0, y), (x1, y),
                            arrowstyle="-|>,head_length=0.10,head_width=0.06",
                            linewidth=0.9, color="#1c1917",
                            shrinkA=0, shrinkB=0)
    ax.add_patch(arrow)
    if label:
        ax.text((x0+x1)/2, y+0.18, label, family="Arial", size=6.5,
                style="italic", ha="center", va="bottom",
                color="#4f5d75")


def draw_utility(ax, blocks_by_id, util):
    db = blocks_by_id[util["to"]]
    offset = util.get("offset_x", -0.3)
    x = db["x"] + offset
    y0 = util["from_y"]
    y1 = db["y"] + BLOCK_H*0.7 + 0.02
    arrow = FancyArrowPatch((x, y0), (x, y1),
                            arrowstyle="-|>,head_length=0.10,head_width=0.06",
                            linewidth=0.8, color="#7a3ec7",
                            shrinkA=0, shrinkB=0)
    ax.add_patch(arrow)
    ax.text(x, y0 + 0.04, util["label"], family="Arial", size=7,
            style="italic", ha="center", va="bottom",
            color="#7a3ec7")


def render_pfd(cascade_key, out_dir):
    spec = PROCESS_SPECS[cascade_key]
    blocks = spec["blocks"]
    blocks_by_id = {b["id"]: b for b in blocks}

    # figure size
    xs = [b["x"] for b in blocks]
    x_max = max(xs) + 1.0
    x_min = min(xs) - 1.0
    fig_w_cm = min(22.0, (x_max - x_min) * 1.0)  # cap width
    fig_h_cm = 5.5

    fig, ax = plt.subplots(figsize=(fig_w_cm/2.54, fig_h_cm/2.54), dpi=180)
    ax.set_xlim(x_min, x_max)
    ax.set_ylim(0, 3.5)
    ax.set_aspect("equal")
    ax.axis("off")

    # title
    ax.text(x_min + 0.2, 3.3, spec["title"],
            family="Arial", size=10, weight="bold",
            ha="left", va="top", color="#1c1917")

    # streams first (under blocks)
    for src, dst, label in spec.get("streams", []):
        draw_stream(ax, blocks_by_id, src, dst, label)

    # utilities
    for util in spec.get("utilities", []):
        draw_utility(ax, blocks_by_id, util)

    # blocks on top
    for b in blocks:
        draw_block(ax, b)

    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"pfd_{cascade_key}"
    svg = out_dir / f"{stem}.svg"
    png = out_dir / f"{stem}.png"
    fig.savefig(svg, format="svg", bbox_inches="tight", pad_inches=0.05)
    fig.savefig(png, format="png", dpi=180, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)

    meta = {
        "cascade": cascade_key, "title": spec["title"],
        "n_blocks": len(blocks),
        "n_streams": len(spec.get("streams", [])),
        "created_at": datetime.now().isoformat() + "Z",
        "outputs": {"svg": str(svg), "png": str(png)},
    }
    (out_dir / f"{stem}_meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"svg": svg, "png": png}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cascade", choices=list(PROCESS_SPECS.keys()) + ["all"], required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    keys = list(PROCESS_SPECS.keys()) if args.cascade == "all" else [args.cascade]
    for k in keys:
        out = render_pfd(k, args.out)
        print(f"[{k}] {out['svg']}")
        print(f"[{k}] {out['png']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
