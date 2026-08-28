#!/usr/bin/env python
"""scheme_render.py — Render enzyme cascade scheme to SVG + PNG (300 DPI).

Layout follows standard biocatalysis figure convention (Bornscheuer/JACS/Angew):

    [Sub]──┐ enzyme  ┌──►[Pro]            main backbone with arrowhead
            \\ ╭──╮ /
             \\│  │/                      cofactor CYCLE (oval) crossing the
              X cycle X                   backbone: NAD(P)H → NAD(P)+ on top,
             /│  │\\                       NAD(P)+ → NAD(P)H on bottom (regen).
            / ╰──╯ \\                     Both arcs have arrowheads.
           regen_in    regen_out          co-substrates of regen enzyme
                regen_enzyme              (italic, below cycle)

Compounds are rendered as RDKit-drawn structures when SMILES is available;
falls back to text-in-box otherwise.

Input: scheme_spec dict (see SPECS below) with optional "smiles" per compound.
Output (in --out dir):
  - <stem>.svg, <stem>.png (300 DPI), <stem>_meta.json
"""
from __future__ import annotations

# Windows' default console is cp949, which dies on Korean/symbol output.
# Force UTF-8. Use reconfigure(): wrapping the stream in a TextIOWrapper
# instead takes ownership of the underlying stream, so once this module is
# imported, the caller's stdout gets closed when that wrapper is later
# garbage-collected (measured).
import sys as _sys
for _s in (_sys.stdout, _sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

import argparse
import json
import math
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Ellipse
from matplotlib.path import Path as MplPath
from matplotlib.patches import PathPatch
import matplotlib.image as mpimg
import numpy as np

# Optional RDKit for structures
try:
    from rdkit import Chem
    from rdkit.Chem import AllChem
    from rdkit.Chem.Draw import rdMolDraw2D
    HAS_RDKIT = True
except Exception:
    HAS_RDKIT = False

DEFAULT_STYLE = {
    "fonts": {
        "compound":  {"family": "Arial", "size_pt": 9.0, "weight": "normal"},
        "enzyme":    {"family": "Arial", "size_pt": 10.0, "weight": "bold"},
        "ec_number": {"family": "Arial", "size_pt": 7.0, "weight": "normal",
                      "color": "#7a8399"},
        "cofactor":  {"family": "Arial", "size_pt": 9.0, "weight": "normal",
                      "style": "italic"},
        "sub":       {"family": "Arial", "size_pt": 7.0, "weight": "normal",
                      "color": "#7a8399"},
    },
    "arrow":   {"main_stroke_pt": 1.1, "main_color": "#1c1917",
                "head_length_pt": 5.0},
    "node":    {"box_color": "#ffffff", "edge_color": "#1c1917",
                "edge_pt": 0.8, "focal_fill": "#f6e5dc",
                "focal_edge": "#b5523a"},
    "cycle":   {"stroke_pt": 1.0, "head_pt": 5.0},
    "colors":  {"NADP": "#2e5aa8", "NAD": "#c84a2c",
                "ATP":  "#7a3ec7", "MISC": "#7a8399"},
}


def load_style(path):
    if path and Path(path).exists():
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            out = json.loads(json.dumps(DEFAULT_STYLE))
            for k, v in data.items():
                if isinstance(v, dict) and k in out:
                    out[k].update(v)
                else:
                    out[k] = v
            return out
        except Exception:
            pass
    return DEFAULT_STYLE


def pool_of(label):
    s = (label or "").upper()
    if "NADP" in s: return "NADP"
    if "NAD"  in s: return "NAD"
    if "ATP"  in s or "ADP" in s: return "ATP"
    return "MISC"


def _mathtext(s):
    """Convert plain subscripts/superscripts to matplotlib mathtext.
    'CO2' -> 'CO$_2$', 'H2O2' -> 'H$_2$O$_2$', 'O2' -> 'O$_2$',
    'NADP+' kept as is (Arial handles +)."""
    if not s:
        return s
    # already mathtext-safe? leave $...$ blocks alone
    if "$" in s:
        return s
    out = []
    i = 0
    while i < len(s):
        ch = s[i]
        # digit following an uppercase letter or closing paren -> subscript
        if ch.isdigit() and i > 0 and (s[i-1].isalpha() or s[i-1] == ")"):
            # group consecutive digits
            j = i
            while j < len(s) and s[j].isdigit():
                j += 1
                # don't gobble digits that look like an EC number (only inside cof labels)
                if j-i >= 2:
                    break
            out.append(f"$_{{{s[i:j]}}}$")
            i = j
            continue
        # unicode subscript digits → mathtext
        if ch in "₀₁₂₃₄₅₆₇₈₉":
            d = "₀₁₂₃₄₅₆₇₈₉".index(ch)
            out.append(f"$_{{{d}}}$")
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def cofactor_pair_label(cof_in, cof_out):
    """Render label like 'NAD(P)H' / 'NAD(P)+' when both forms exist; else verbatim."""
    return cof_in, cof_out


# ============================================================
# Structure rendering helpers
# ============================================================

def render_structure_png(smiles: str, w_px: int = 240, h_px: int = 140):
    """Return a numpy RGBA array of the structure, or None if it fails."""
    if not HAS_RDKIT or not smiles:
        return None
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    AllChem.Compute2DCoords(mol)
    drawer = rdMolDraw2D.MolDraw2DCairo(w_px, h_px)
    opts = drawer.drawOptions()
    opts.bondLineWidth = 1.0
    opts.padding = 0.05
    opts.fixedFontSize = 14
    drawer.DrawMolecule(mol)
    drawer.FinishDrawing()
    png_bytes = drawer.GetDrawingText()
    # Decode via Pillow
    from io import BytesIO
    from PIL import Image
    img = Image.open(BytesIO(png_bytes)).convert("RGBA")
    return np.array(img)


# ============================================================
# Cofactor cycle drawing
# ============================================================

def draw_cofactor_cycle(ax, cx, cy_arrow_top, *,
                       cof_in, cof_out, color,
                       width_cm=1.4, height_cm=1.4,
                       stroke_pt=1.0,
                       font_pt=9.0,
                       regen=None,
                       regen_font_pt=10.0,
                       ec_font_pt=7.0):
    """Draw a cofactor cycle ABOVE the main backbone arrow (ADH-style).

    Layout (matches standard ADH/JACS figure):

                          enzyme name (above cycle)
                              ↓ down-arrow head
                           ╱─────╲
              NAD(P)H ◄──┤  cycle  ├──► NAD(P)+   (labels OUTSIDE, on sides)
                           ╲─────╱
                              ↓ down-tick touches backbone
            ─────────────────────────────────────►  main backbone arrow
                              ↑
                       (cycle is ABOVE backbone, not straddling)

    The cycle is a closed circle. Two short arrowheads at the bottom-left
    and bottom-right of the circle point DOWN towards the main arrow
    (indicating cofactor is consumed during the main reaction).

    For a regen enzyme, a SECOND cycle below the backbone could be added,
    but the cleaner convention (used here) is to label the regen enzyme
    BELOW the backbone with its co-substrate label.

    Args:
        cx, cy_arrow_top: x of cycle centre, y of TOP of main arrow line.
                          The cycle sits centred on cx, with its bottom
                          touching y = cy_arrow_top (no overlap with arrow).
    """
    rx = width_cm / 2
    ry = height_cm / 2
    # In standard ADH-style figures, the cycle's EQUATOR sits slightly above
    # the main backbone arrow (so the bottom arc doesn't touch / overlap the
    # arrow). cy = arrow_top + ry + small gap.
    cy = cy_arrow_top + ry + 0.10

    # ------------------------------------------------------------------
    # Two semicircular arcs forming a closed cycle. Equator is HORIZONTAL.
    #   TOP arc (drawn left→right):  arrowhead at θ≈10° (just past top-right)
    #                                 = main reaction consumes cof_in,
    #                                   produces cof_out
    #   BOTTOM arc (drawn right→left): arrowhead at θ≈190° (just past bottom-left)
    #                                 = regen reaction consumes cof_out,
    #                                   produces cof_in
    # Both arcs are real arrows (semi-circle with -|> head).
    #
    # Labels live INSIDE the cycle in 4 quadrants:
    #   Upper-LEFT  : cof_in   (e.g. NADPH)   ← entering top arc
    #   Upper-RIGHT : cof_out  (e.g. NADP+)   ← leaving top arc
    #   Lower-RIGHT : regen.co_in  (e.g. Formate) ← entering bottom arc
    #   Lower-LEFT  : regen.co_out (e.g. CO2)     ← leaving bottom arc
    # ------------------------------------------------------------------
    import math as _m
    n_seg = 60  # bezier samples for smooth half-ellipse

    def half_ellipse(start_deg, end_deg):
        """Return [(x,y), ...] points along ellipse, deg measured CCW from +x."""
        pts = []
        for k in range(n_seg + 1):
            t = k / n_seg
            deg = start_deg + (end_deg - start_deg) * t
            th = _m.radians(deg)
            pts.append((cx + rx * _m.cos(th), cy + ry * _m.sin(th)))
        return pts

    # TOP arc: from θ=180° (left equator) to θ=0° (right equator) — going CW (via top)
    top_pts = half_ellipse(180, 0)  # this goes via top (sin > 0 region)
    # CCW going 180 -> 0 means we pass through 90 deg (top). Actually 180→0 with
    # linear deg sweep gives 180, 170, ..., 0 — that passes through 90, i.e. TOP. ✓
    top_path = MplPath([(x, y) for x, y in top_pts])
    ax.add_patch(PathPatch(top_path, fc="none", ec=color,
                           lw=stroke_pt, capstyle="round"))
    # Arrowhead near right end of top arc — tangent direction at that point
    # is (-sin θ, cos θ) for CCW; we're going CW so it's (sin θ, -cos θ).
    head_th_top = _m.radians(15)
    head_x = cx + rx * _m.cos(head_th_top)
    head_y = cy + ry * _m.sin(head_th_top)
    # tail just behind along the arc
    tail_th = _m.radians(30)
    tail_x = cx + rx * _m.cos(tail_th)
    tail_y = cy + ry * _m.sin(tail_th)
    ax.annotate("", xy=(head_x, head_y), xytext=(tail_x, tail_y),
                arrowprops=dict(arrowstyle="-|>", color=color,
                                lw=stroke_pt,
                                shrinkA=0, shrinkB=0, mutation_scale=12))

    # BOTTOM arc: from θ=0° (right equator) to θ=-180° (left equator)
    # via -90° (bottom). Going from 0 to -180 sweeps via -90 (bottom). ✓
    bot_pts = half_ellipse(0, -180)
    bot_path = MplPath([(x, y) for x, y in bot_pts])
    ax.add_patch(PathPatch(bot_path, fc="none", ec=color,
                           lw=stroke_pt, capstyle="round"))
    # Arrowhead near left end of bottom arc
    head_th_bot = _m.radians(195)  # past left-equator going CW (i.e. 180 + 15)
    head_x = cx + rx * _m.cos(head_th_bot)
    head_y = cy + ry * _m.sin(head_th_bot)
    tail_th = _m.radians(210)
    tail_x = cx + rx * _m.cos(tail_th)
    tail_y = cy + ry * _m.sin(tail_th)
    ax.annotate("", xy=(head_x, head_y), xytext=(tail_x, tail_y),
                arrowprops=dict(arrowstyle="-|>", color=color,
                                lw=stroke_pt,
                                shrinkA=0, shrinkB=0, mutation_scale=12))

    # ------------------------------------------------------------------
    # Labels — 4 quadrants INSIDE the cycle.
    # ------------------------------------------------------------------
    # Labels — placed at the LEFT and RIGHT exterior of the cycle, vertically
    # offset above/below the equator. Just like the standard ADH figure where
    # "NAD(P)H" sits left of cycle, "NAD(P)+" sits right.
    #   cof_in   on LEFT (outside), upper-half y (alignment to top arc)
    #   cof_out  on RIGHT (outside), upper-half y
    #   co_in    on RIGHT (outside), lower-half y  (sacrificial in)
    #   co_out   on LEFT (outside), lower-half y   (sacrificial out)
    pad_x = 0.08
    upper_y = cy + ry*0.30
    lower_y = cy - ry*0.30

    ax.text(cx - rx - pad_x, upper_y, _mathtext(cof_in),
            family="Arial", size=font_pt, style="italic",
            color=color, ha="right", va="center", zorder=6)
    ax.text(cx + rx + pad_x, upper_y, _mathtext(cof_out),
            family="Arial", size=font_pt, style="italic",
            color=color, ha="left", va="center", zorder=6)

    if regen:
        ax.text(cx + rx + pad_x, lower_y, _mathtext(regen["co_in"]),
                family="Arial", size=font_pt, style="italic",
                color=color, ha="left", va="center", zorder=6)
        ax.text(cx - rx - pad_x, lower_y, _mathtext(regen["co_out"]),
                family="Arial", size=font_pt, style="italic",
                color=color, ha="right", va="center", zorder=6)


# ============================================================
# Main renderer
# ============================================================

NODE_W_CM = 2.2
NODE_H_CM = 1.40


def render_scheme(spec, out_dir, stem, style, *, fig_w_cm=20.0):
    out_dir.mkdir(parents=True, exist_ok=True)
    n = len(spec["backbone"])
    if n < 2:
        raise ValueError("backbone needs ≥ 2 nodes")

    # Layout rows (cm, BOTTOM origin). Vertical stack top → bottom:
    #   H_TOP_PAD
    #   H_TITLE       — figure title
    #   H_CYCLE       — cofactor cycle (closed circle ABOVE backbone)
    #   H_CYCLE_GAP   — gap between cycle bottom and arrow (small)
    #   H_BACKBONE    — compound boxes / arrow row
    #   H_ENZ_BELOW   — enzyme name + EC BELOW arrow (standard ADH convention)
    #   H_REGEN       — regen enzyme + co-substrates (further below)
    #   H_BOTTOM_PAD
    H_TOP_PAD     = 0.3
    H_TITLE       = 0.6
    H_CYCLE       = 2.2    # cycle ~2.0 cm tall + gap
    H_CYCLE_GAP   = 0.10   # tiny gap so cycle doesn't touch arrow
    H_BACKBONE    = NODE_H_CM
    H_ENZ_BELOW   = 0.95   # enzyme name + EC line, BELOW arrow
    H_REGEN       = 1.50   # regen: co-substrate line + enzyme + EC
    H_BOTTOM_PAD  = 0.3

    has_regen = any(s.get("regen") for s in spec["steps"])
    if has_regen:
        fig_h_cm = (H_TOP_PAD + H_TITLE + H_CYCLE + H_CYCLE_GAP + H_BACKBONE
                    + H_ENZ_BELOW + H_REGEN + H_BOTTOM_PAD)
    else:
        fig_h_cm = (H_TOP_PAD + H_TITLE + H_CYCLE + H_CYCLE_GAP + H_BACKBONE
                    + H_ENZ_BELOW + H_BOTTOM_PAD)
    # backbone centre y (cm, from bottom origin)
    backbone_y = (H_BOTTOM_PAD
                  + (H_REGEN if has_regen else 0)
                  + H_ENZ_BELOW
                  + H_BACKBONE/2)

    pad_cm = 0.7  # extra side padding so subscripted text isn't clipped
    gap_cm = (fig_w_cm - 2*pad_cm - n*NODE_W_CM) / max(1, (n - 1))
    if gap_cm < 4.0:  # need room for cycle + side labels with subscripts
        fig_w_cm = 2*pad_cm + n*NODE_W_CM + 4.2*(n-1)
        gap_cm = 4.2
    xs = [pad_cm + NODE_W_CM/2 + i*(NODE_W_CM + gap_cm) for i in range(n)]

    fig, ax = plt.subplots(figsize=(fig_w_cm/2.54, fig_h_cm/2.54), dpi=300)
    ax.set_xlim(0, fig_w_cm)
    ax.set_ylim(0, fig_h_cm)
    ax.set_aspect("equal")
    ax.axis("off")

    # Title
    title = spec.get("title", "")
    if title:
        ax.text(pad_cm, fig_h_cm - H_TOP_PAD, title,
                family="Arial", size=10, weight="bold",
                ha="left", va="top", color="#1c1917")

    # ---- compound nodes (structure or text-box) ----
    for x_cm, node in zip(xs, spec["backbone"]):
        focal = node.get("focal", False)
        smi = node.get("smiles")
        img = render_structure_png(smi, w_px=320, h_px=200) if smi else None

        if img is not None:
            # place the image centred on the backbone row
            extent = (x_cm - NODE_W_CM/2, x_cm + NODE_W_CM/2,
                      backbone_y - NODE_H_CM/2 + 0.18,
                      backbone_y + NODE_H_CM/2 + 0.18)
            ax.imshow(img, extent=extent, aspect="auto", zorder=4,
                      interpolation="bilinear")
            # name below
            ax.text(x_cm, backbone_y - NODE_H_CM/2 + 0.05, node["label"],
                    family="Arial", size=style["fonts"]["compound"]["size_pt"],
                    weight="bold" if focal else "normal",
                    color="#1c1917", ha="center", va="bottom", zorder=5)
            # focal highlight ring
            if focal:
                rect = FancyBboxPatch(
                    (x_cm - NODE_W_CM/2 - 0.05, backbone_y - NODE_H_CM/2 - 0.05),
                    NODE_W_CM + 0.10, NODE_H_CM + 0.10,
                    boxstyle="round,pad=0,rounding_size=0.10",
                    linewidth=0.9,
                    edgecolor=style["node"]["focal_edge"],
                    facecolor="none", zorder=2)
                ax.add_patch(rect)
        else:
            # fallback text box
            fill = style["node"]["focal_fill"] if focal else style["node"]["box_color"]
            edge = style["node"]["focal_edge"] if focal else style["node"]["edge_color"]
            rect = FancyBboxPatch(
                (x_cm - NODE_W_CM/2, backbone_y - NODE_H_CM/2),
                NODE_W_CM, NODE_H_CM,
                boxstyle="round,pad=0,rounding_size=0.10",
                linewidth=style["node"]["edge_pt"],
                edgecolor=edge, facecolor=fill, zorder=3,
            )
            ax.add_patch(rect)
            ax.text(x_cm, backbone_y + 0.10, node["label"],
                    family="Arial", size=style["fonts"]["compound"]["size_pt"],
                    weight="bold", ha="center", va="center",
                    color="#1c1917", zorder=4)
            if node.get("sub"):
                ax.text(x_cm, backbone_y - 0.22, node["sub"],
                        family="Arial", size=style["fonts"]["sub"]["size_pt"],
                        color=style["fonts"]["sub"]["color"],
                        ha="center", va="center", zorder=4)

    # ---- Steps: main arrow + cofactor cycle ABOVE + regen BELOW ----
    for i, step in enumerate(spec["steps"]):
        a_x = xs[i]   + NODE_W_CM/2 + 0.08
        b_x = xs[i+1] - NODE_W_CM/2 - 0.08
        mid_x = (a_x + b_x) / 2

        # (a) main backbone arrow — ends with a clear -|> head OUTSIDE the
        # product node box. We move the arrow tail slightly INSIDE the
        # substrate edge and end the head slightly BEFORE the product edge
        # so the arrowhead is fully visible.
        a_x_arrow = a_x + 0.04
        b_x_arrow = b_x - 0.04
        arrow = FancyArrowPatch(
            (a_x_arrow, backbone_y), (b_x_arrow, backbone_y),
            arrowstyle="-|>",
            mutation_scale=14,
            linewidth=style["arrow"]["main_stroke_pt"],
            color=style["arrow"]["main_color"],
            shrinkA=0, shrinkB=0, zorder=5,  # raised above structure images
        )
        ax.add_patch(arrow)

        # enzyme name + EC BELOW the arrow (standard ADH convention).
        # Reason: cycle sits ABOVE, so labels above arrow would collide.
        enz_top_y = backbone_y - H_BACKBONE/2 - 0.18
        ax.text(mid_x, enz_top_y, step["enz"],
                family="Arial", size=style["fonts"]["enzyme"]["size_pt"],
                weight="bold", ha="center", va="top",
                color="#1c1917", zorder=5)
        # 9 pt Arial text occupies ~0.36 cm vertically; push EC well below
        ec_y = enz_top_y - 0.42
        ax.text(mid_x, ec_y, f"EC {step['ec']}",
                family="Arial", size=style["fonts"]["ec_number"]["size_pt"],
                color="#7a8399", ha="center", va="top", zorder=5)

        # (b) cofactor cycle — ABOVE backbone, centred at mid_x.
        # Skip cycle entirely when this step has no cofactor (e.g. isomerase /
        # epimerase steps that do not use NAD(P)+/NAD(P)H).
        skip_cycle = (step.get("cof_in", "") in ("", "—", "-", None))
        pool = pool_of(step["cof_in"] + " " + step["cof_out"])
        cof_color = style["colors"][pool]
        cycle_w = 1.5
        cycle_h = 1.4
        cycle_bottom_y = backbone_y + H_BACKBONE/2 + H_CYCLE_GAP
        cy_anchor = cycle_bottom_y
        if skip_cycle:
            cof_color = "#1c1917"  # default ink for the enzyme label
        else:
            draw_cofactor_cycle(
                ax, mid_x, cy_anchor,
                cof_in=step["cof_in"], cof_out=step["cof_out"],
                color=cof_color,
                width_cm=cycle_w, height_cm=cycle_h,
                stroke_pt=style["cycle"]["stroke_pt"],
                font_pt=style["fonts"]["cofactor"]["size_pt"],
                regen=step.get("regen"),
                regen_font_pt=style["fonts"]["enzyme"]["size_pt"],
                ec_font_pt=style["fonts"]["ec_number"]["size_pt"],
            )

        # (c) regen enzyme name + EC, drawn BELOW the main enzyme.
        # The co-substrate flow (Formate→CO2 etc.) is already rendered
        # INSIDE the cycle's bottom arc by draw_cofactor_cycle.
        regen = step.get("regen")
        if regen:
            regen_top = ec_y - 0.36
            ax.text(mid_x, regen_top, regen["enz"],
                    family="Arial", size=style["fonts"]["enzyme"]["size_pt"],
                    weight="bold", style="italic", color=cof_color,
                    ha="center", va="top", zorder=5)
            ax.text(mid_x, regen_top - 0.27, f"EC {regen['ec']}",
                    family="Arial", size=style["fonts"]["ec_number"]["size_pt"],
                    color="#7a8399",
                    ha="center", va="top", zorder=5)

    # save
    svg_path = out_dir / f"{stem}.svg"
    png_path = out_dir / f"{stem}.png"
    fig.savefig(svg_path, format="svg", bbox_inches="tight", pad_inches=0.06)
    fig.savefig(png_path, format="png", dpi=300, bbox_inches="tight",
                pad_inches=0.06)
    plt.close(fig)

    meta = {
        "stem": stem,
        "created_at": datetime.now().isoformat() + "Z",
        "fig_w_cm": fig_w_cm, "fig_h_cm": fig_h_cm,
        "n_backbone": n, "has_regen": has_regen,
        "rdkit": HAS_RDKIT,
        "spec": spec,
        "outputs": {"svg": str(svg_path), "png": str(png_path)},
        "script": str(Path(__file__).resolve()),
    }
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL, cwd=Path(__file__).parent
        ).decode().strip()
        meta["git_sha"] = sha
    except Exception:
        pass
    (out_dir / f"{stem}_meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return {"svg": svg_path, "png": png_path}


# ============================================================
# Built-in cascade specs WITH SMILES for substrate / product nodes
# ============================================================
# canonical SMILES from PubChem (verified) — note: stereo simplified for drawing
# Replace the example spec below with your own cascade definition.
SPECS = {
    "example": {
        "title": "Example · Substrate → Product cascade",
        "backbone": [
            {"label": "Substrate", "sub": "starting material",
             "smiles": "OCC(O)CO"},
            {"label": "Intermediate", "sub": "achiral intermediate",
             "smiles": "OCC(O)C(O)C(O)CO", "focal": True},
            {"label": "Product", "sub": "target compound",
             "smiles": "OCC(O)C(O)C(=O)CO"},
        ],
        "steps": [
            {"enz": "Reductase (E1)", "ec": "1.1.1.x",
             "cof_in": "NADPH", "cof_out": "NADP+",
             "regen": {"enz": "FDH (E2)", "ec": "1.17.1.10",
                       "co_in": "Formate", "co_out": "CO₂"}},
            {"enz": "Oxidase (E3)", "ec": "1.1.1.x",
             "cof_in": "NAD+",  "cof_out": "NADH",
             "regen": {"enz": "NOX (E4)", "ec": "1.6.3.4",
                       "co_in": "O₂", "co_out": "H₂O₂"}},
        ],
    },
}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cascade", choices=list(SPECS.keys()) + ["all"], required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--style", type=Path, default=None)
    ap.add_argument("--width-cm", type=float, default=20.0)
    args = ap.parse_args()

    style = load_style(args.style)
    keys = list(SPECS.keys()) if args.cascade == "all" else [args.cascade]
    for k in keys:
        out = render_scheme(SPECS[k], args.out, f"scheme_{k}", style,
                            fig_w_cm=args.width_cm)
        print(f"[{k}] {out['svg']}")
        print(f"[{k}] {out['png']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
