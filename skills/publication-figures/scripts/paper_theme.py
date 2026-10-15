#!/usr/bin/env python3
"""paper_theme.py - the Tagatose paper look (Prism style) as a light module.

Keeps only what changes how a plot looks: inward ticks with minor ticks, 1.8 pt axes, 1.6 pt lines with circle
markers, Arial 11/10/10 pt, frameless legend, one colour AND one line style per named entity, 600 dpi PNG plus SVG.
Panel-letter placement and print-width fitting stay in `aesthetic_helpers.py` (reused, not copied).

Usage in a render script:
    import matplotlib.pyplot as plt
    import paper_theme as pt
    pt.apply()
    fig, axes = plt.subplots(1, 2, figsize=(pt.SLOT_W_IN, pt.SLOT_W_IN * 0.46), sharey=True)
    for ax, letter in zip(axes, "ab"):
        pt.plot_series(ax, t, y_wt, "WT", label="WT", markevery=5)
        pt.legend(ax); pt.panel(ax, letter); pt.style_axis(ax)
    fig.tight_layout(); pt.save(fig, "fig.png")          # also writes fig.svg

Colours are the Okabe-Ito palette with its saturation scaled by 0.78 (hue and lightness unchanged), the same
definition the manuscript theme uses. Register every entity once with `register_series`, then use the name everywhere.
"""
from __future__ import annotations

import colorsys
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
from matplotlib.colors import to_hex, to_rgb
from matplotlib.ticker import AutoMinorLocator

from aesthetic_helpers import panel_label, smart_legend

FS_AXIS, FS_TICK, FS_LEGEND, FS_PANEL = 11, 10, 10, 16
SLOT_W_IN = 165.0 / 25.4          # 165 mm slot, the width the Tagatose bioreactor panels use
MUTE_KEEP = 0.78
_RAW = {"orange": "#E69F00", "skyblue": "#56B4E9", "green": "#009E73", "blue": "#0072B2",
        "vermillion": "#D55E00", "purple": "#CC79A7"}


def muted(color: str, keep: float = MUTE_KEEP) -> str:
    """Palette colour with its HLS saturation scaled by `keep` (1 = unchanged)."""
    h, l, s = colorsys.rgb_to_hls(*to_rgb(color))
    return to_hex(colorsys.hls_to_rgb(h, l, s * keep))


OKABE_ITO = {k: muted(v) for k, v in _RAW.items()}
GREY = "#666666"                  # no-enzyme / blank traces

# entity -> (colour, line style). Distinct line styles keep the series apart in a black-and-white print.
SERIES = {
    "WT": (OKABE_ITO["blue"], "-"), "variant": (OKABE_ITO["vermillion"], "--"),
    "other protein": (OKABE_ITO["purple"], "-."), "no enzyme": (GREY, ":"),
}


def register_series(name: str, color: str, linestyle: str = "-") -> None:
    """Fix the colour and line style of one entity for every figure (colour via OKABE_ITO[...])."""
    SERIES[name] = (color, linestyle)


def series_style(name: str) -> tuple[str, str]:
    if name not in SERIES:
        raise KeyError(f"{name!r} is not registered: call register_series() once so every figure agrees")
    return SERIES[name]


def apply() -> dict:
    """Set every rcParam of the paper look and return the numbers a script may need."""
    matplotlib.rcParams.update({
        "font.family": "Arial", "font.size": FS_AXIS, "axes.labelsize": FS_AXIS, "axes.titlesize": FS_PANEL,
        "xtick.labelsize": FS_TICK, "ytick.labelsize": FS_TICK, "legend.fontsize": FS_LEGEND,
        "axes.linewidth": 1.8, "axes.spines.top": False, "axes.spines.right": False,
        "xtick.direction": "in", "ytick.direction": "in",
        "xtick.major.size": 6.5, "ytick.major.size": 6.5, "xtick.major.width": 1.8, "ytick.major.width": 1.8,
        "xtick.minor.size": 3.6, "ytick.minor.size": 3.6, "xtick.minor.width": 1.4, "ytick.minor.width": 1.4,
        "lines.linewidth": 1.6, "lines.markersize": 4, "legend.frameon": False,
        "figure.dpi": 120, "savefig.dpi": 600, "savefig.bbox": "tight", "svg.fonttype": "none",
        "pdf.fonttype": 42, "axes.unicode_minus": False, "mathtext.fontset": "custom",
        "mathtext.rm": "Arial", "mathtext.it": "Arial:italic", "mathtext.bf": "Arial:bold",
    })
    return {"axes_lw": 1.8, "line_lw": 1.6, "marker_size": 4}


def plot_series(ax, x, y, name: str, *, markevery=None, zorder: float = 3, **kw):
    """Line with circle markers in the entity's fixed colour and style. Pass markevery=5 for dense traces."""
    color, linestyle = series_style(name)
    return ax.plot(x, y, color=color, linestyle=linestyle, marker="o", markevery=markevery, zorder=zorder, **kw)


def style_axis(ax) -> None:
    """Minor ticks on both axes (the Prism look); call after the limits are final."""
    ax.xaxis.set_minor_locator(AutoMinorLocator())
    ax.yaxis.set_minor_locator(AutoMinorLocator())
    ax.tick_params(which="both", direction="in")


def legend(ax):
    """Frameless legend in the first data-free corner (aesthetic_helpers.smart_legend at the paper font size)."""
    return smart_legend(ax, fontsize=FS_LEGEND)


def panel(ax, letter: str) -> None:
    """Panel letter (a), (b), ... in normal weight."""
    panel_label(ax, letter, fontsize=FS_PANEL)


def save(fig, path) -> None:
    """600 dpi PNG plus an SVG next to it, tight bbox."""
    path = Path(path)
    fig.savefig(path, dpi=600, bbox_inches="tight")
    fig.savefig(path.with_suffix(".svg"), dpi=600, bbox_inches="tight")
