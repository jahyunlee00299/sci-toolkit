#!/usr/bin/env python
"""ga_compose.py — Compose a Graphical Abstract for a given cascade × journal.

Reads:
  - journal preset from graphical_abstract_specs.json
  - cascade spec from scheme_render.SPECS (or external JSON)
Produces:
  - <out>/ga_<cascade>_<journal>.svg
  - <out>/ga_<cascade>_<journal>.png  (at preset DPI)
  - <out>/ga_<cascade>_<journal>_meta.json

Layout strategy (placeholder, will refine per journal):
  - Top:    headline (one-liner about the cascade)
  - Middle: condensed cascade scheme (only key compounds + key arrow)
  - Bottom: 1-2 key numbers (yield / ee / titer if present in spec)
"""
from __future__ import annotations

# Windows' default console is cp949, which dies on Korean/symbol output. Force UTF-8.
# Use reconfigure(): wrapping in a TextIOWrapper would take ownership of the
# underlying stream, so once the wrapper is GC'd after this module is imported,
# it closes the caller's stdout too (measured).
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
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from matplotlib.path import Path as MplPath
from matplotlib.patches import PathPatch

sys.path.insert(0, str(Path(__file__).parent))
from scheme_render import SPECS, pool_of, DEFAULT_STYLE, load_style  # noqa


# Headline + key numbers per cascade (fill with your cascade-specific values)
HEADLINES = {
    "example": {
        "headline": "Substrate → Product",
        "subtitle": "Redox cascade · N enzymes",
        "key_nums": [("yield", "fill"), ("step", "N"), ("substrate", "fill")],
    },
}


def compose(cascade: str, journal_key: str, presets: dict,
            style: dict, out_dir: Path) -> dict:
    if cascade not in SPECS:
        raise SystemExit(f"unknown cascade {cascade}")
    if journal_key not in presets:
        raise SystemExit(f"unknown journal {journal_key}")
    if journal_key.startswith("_"):
        raise SystemExit("invalid journal key")
    spec = SPECS[cascade]
    pre = presets[journal_key]
    head = HEADLINES.get(cascade, {"headline": cascade, "subtitle": "",
                                    "key_nums": []})

    w_cm, h_cm, dpi = pre["w_cm"], pre["h_cm"], pre["dpi"]
    fig, ax = plt.subplots(figsize=(w_cm/2.54, h_cm/2.54), dpi=dpi)
    ax.set_xlim(0, w_cm)
    ax.set_ylim(0, h_cm)
    ax.set_aspect("equal")
    ax.axis("off")

    # font sizing relative to journal max (pt)
    max_pt = pre["max_font_pt"]
    body_pt  = max_pt
    head_pt  = max_pt + 1  # slightly bigger headline
    small_pt = max_pt - 1.5

    orientation = pre["orientation"]
    # Layout differs by aspect ratio
    is_portrait = h_cm > w_cm * 1.2
    is_landscape_wide = w_cm > h_cm * 2.0  # Elsevier-like

    # ---- Headline (top) ----
    y_head = h_cm - 0.35
    ax.text(w_cm/2, y_head, head["headline"],
            family="Arial", size=head_pt, weight="bold",
            ha="center", va="top", color="#1c1917")
    if head["subtitle"]:
        ax.text(w_cm/2, y_head - 0.40, head["subtitle"],
                family="Arial", size=small_pt, weight="normal",
                ha="center", va="top", color="#4f5d75", style="italic")

    # ---- Cascade strip (middle) ----
    # Condensed: show only first → focal → last compound + main arrow
    compounds = spec["backbone"]
    # pick representative subset depending on length
    if len(compounds) <= 3:
        cmps = compounds
    else:
        # first, middle (or focal), last
        focals = [i for i, c in enumerate(compounds) if c.get("focal")]
        mid_idx = focals[0] if focals else len(compounds)//2
        cmps = [compounds[0], compounds[mid_idx], compounds[-1]]
    n = len(cmps)

    strip_h = 1.5 if not is_portrait else 2.0
    strip_top = y_head - 0.95
    strip_bottom = strip_top - strip_h
    backbone_y = (strip_top + strip_bottom)/2

    # node sizing — depends on width
    node_w = min(2.4, (w_cm - 0.6 - 0.3*(n-1)) / n) if not is_portrait else \
             min(w_cm - 0.6, 3.5)
    node_h = 0.55
    if is_portrait:
        # stack vertically
        gap_y = (strip_top - strip_bottom - n*node_h) / max(1, (n-1))
        ys = [strip_top - node_h/2 - i*(node_h + gap_y) for i in range(n)]
        xs = [w_cm/2 for _ in range(n)]
    else:
        pad = 0.3
        if n == 1:
            xs = [w_cm/2]
        else:
            xs = [pad + node_w/2 + i*((w_cm - 2*pad - node_w)/(n-1)) for i in range(n)]
        ys = [backbone_y for _ in range(n)]

    # draw nodes
    for x, y, node in zip(xs, ys, cmps):
        focal = node.get("focal", False)
        rect = FancyBboxPatch(
            (x - node_w/2, y - node_h/2),
            node_w, node_h,
            boxstyle=f"round,pad=0,rounding_size=0.10",
            linewidth=0.7,
            edgecolor=style["node"]["focal_edge"] if focal else "#1c1917",
            facecolor=style["node"]["focal_fill"] if focal else "#ffffff",
        )
        ax.add_patch(rect)
        ax.text(x, y, node["label"],
                family="Arial", size=body_pt, weight="bold",
                ha="center", va="center", color="#1c1917")

    # arrows between nodes (with single short enzyme name on top)
    for i in range(n-1):
        if is_portrait:
            # vertical arrow
            arr = FancyArrowPatch((xs[i], ys[i] - node_h/2),
                                  (xs[i+1], ys[i+1] + node_h/2),
                                  arrowstyle="-|>,head_length=0.10,head_width=0.06",
                                  linewidth=1.0, color="#1c1917",
                                  shrinkA=0, shrinkB=0)
        else:
            arr = FancyArrowPatch((xs[i] + node_w/2 + 0.04, ys[i]),
                                  (xs[i+1] - node_w/2 - 0.04, ys[i+1]),
                                  arrowstyle="-|>,head_length=0.10,head_width=0.06",
                                  linewidth=1.0, color="#1c1917",
                                  shrinkA=0, shrinkB=0)
        ax.add_patch(arr)

    # ---- Key numbers (bottom strip) ----
    y_kn = strip_bottom - 0.45
    if head["key_nums"] and y_kn > 0.3:
        n_kn = len(head["key_nums"])
        x_step = w_cm / (n_kn + 1)
        for i, (label, val) in enumerate(head["key_nums"]):
            cx = (i+1) * x_step
            ax.text(cx, y_kn, val,
                    family="Arial", size=head_pt, weight="bold",
                    ha="center", va="top", color=style["colors"]["NADP"])
            ax.text(cx, y_kn - 0.40, label.upper(),
                    family="Arial", size=small_pt, weight="normal",
                    ha="center", va="top", color="#7a8399",
                    style="italic")

    # Borders disabled by default; some journals require frame
    # ax.add_patch(plt.Rectangle((0,0), w_cm, h_cm, fill=False, ec="#bfc0c0", lw=0.3))

    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"ga_{cascade}_{journal_key}"
    svg = out_dir / f"{stem}.svg"
    png = out_dir / f"{stem}.png"
    fig.savefig(svg, format="svg", bbox_inches="tight", pad_inches=0.04,
                transparent=False)
    fig.savefig(png, format="png", dpi=dpi, bbox_inches="tight",
                pad_inches=0.04, transparent=False)
    plt.close(fig)

    meta = {
        "cascade": cascade,
        "journal": journal_key,
        "journal_label": pre["label"],
        "w_cm": w_cm, "h_cm": h_cm, "dpi": dpi,
        "headline": head["headline"],
        "outputs": {"svg": str(svg), "png": str(png)},
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    (out_dir / f"{stem}_meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return meta


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cascade", choices=list(SPECS.keys()) + ["all"], required=True)
    ap.add_argument("--journal", default="all",
                    help="journal preset key or 'all'")
    ap.add_argument("--specs", type=Path,
                    default=Path(__file__).parent.parent / "references" / "graphical_abstract_specs.json")
    ap.add_argument("--style", type=Path,
                    default=Path(__file__).parent.parent / "references" / "style_tokens.json")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    presets = json.loads(args.specs.read_text(encoding="utf-8"))
    style = load_style(args.style)

    cascades = list(SPECS.keys()) if args.cascade == "all" else [args.cascade]
    journal_keys = [k for k in presets if not k.startswith("_")]
    journals = journal_keys if args.journal == "all" else [args.journal]

    for c in cascades:
        for j in journals:
            m = compose(c, j, presets, style, args.out)
            print(f"[{c} × {j}] {m['outputs']['png']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
