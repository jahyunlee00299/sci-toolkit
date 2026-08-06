"""Reusable matplotlib aesthetic helpers enforcing figure_aesthetics_rules.md.

Drop-in helpers that bake in the house composition rules (R1-R4 + user-confirmed
2026-06-26 rules) so every figure obeys them without re-deriving the logic:

- smart_legend   : corner-preference legend (no center, no title), raises y-limit
                   to fit upper-right when all corners are crowded (never goes outside axes).
- styled_errorbar: error bars in the SERIES color (not black), darkened for legibility.
- panel_label    : (a)(b) panel letters, normal weight by default (bold only if a
                   journal requires it).
- no_bar_edge / top_only_err: bar-chart helpers (no outline; error bar upward only).
- stat_annot / significance_italic: on-figure significance (ns / P / n) in italic
                   per the journal typography rule (never a plain upright 'ns').

These were distilled from a real multi-panel manuscript figure session. See
references/figure_aesthetics_rules.md for the rules these enforce.
"""
from __future__ import annotations
import numpy as np

# ── Color / font SSOT (the ONE source; never inline a literal in a render script) ──
# Okabe-Ito colorblind-safe palette.
OKABE_ITO = {
    "black": "#000000", "orange": "#E69F00", "skyblue": "#56B4E9",
    "green": "#009E73", "yellow": "#F0E442", "blue": "#0072B2",
    "vermillion": "#D55E00", "purple": "#CC79A7",
}
# Entity -> color, fixed across the whole manuscript set (named-entity = one color).
# These are EXAMPLE registrations — replace/extend with your own named entities so each
# entity keeps ONE color across every panel. A protein and its product can share a color
# (e.g. an enzyme and the product it makes); reserve a distinct color per chemical species.
SERIES_COLORS = {
    "ProductA": "#0072B2", "EnzymeA": "#0072B2",   # enzyme + its product share one color
    "ProductB": "#D55E00", "EnzymeB": "#D55E00",
    "D-Gal": "#009E73",                 # RESERVED for D-galactose only
    "D-Glc": "#E69F00", "Formate": "#56B4E9", "Levulinic acid": "#CC79A7",
}
FS_AXIS, FS_TICK, FS_LEGEND, FS_PANEL, FS_ANNOT, FS_ANNOT_SM = 9, 8, 8, 14, 8, 6.5
C_ANNOT = "#333333"        # in-axes annotation text color
C_ANNOT_SOFT = "#666666"
NEUTRAL_PAIR = ("#4D4D4D", "#B0B0B0")   # system/condition comparison grays (not chemical entities)


def series_color(name: str) -> str:
    """Color for a named entity. Raises KeyError on an unknown name so you REGISTER it
    in SERIES_COLORS instead of inventing a literal (enforces named-entity = one color)."""
    return SERIES_COLORS[name]


def bar_xlim_pad(ax, n_groups, pad=0.7):
    """Keep bar charts from gluing the first/last bar onto the y-axis (or right spine).

    A 'tight' x-axis (``ax.margins(x=0)``) looks right for line plots but makes the first
    bar of a bar chart sit flush against the y-axis, which reads as a layout bug. Call this
    AFTER all bars/errorbars/set_xticks (and after any tight-axis styling that sets
    ``margins(x=0)``) to add a half-category + ``pad`` of breathing room on both sides.

    n_groups : number of categorical x positions (len of xticks), assumed at 0..n-1.
    pad      : extra gap in category-spacing units beyond the half-category (0.7 default;
               use ~0.55 for grouped/dodged bars where each category already holds 2+ bars).
    """
    ax.set_xlim(-0.5 - pad, (n_groups - 1) + 0.5 + pad)


# Legend corner preference: upper-right -> lower-right -> lower-left -> upper-left.
# "Don't cover data" is the primary test; this order is the tiebreak.
_CORNER_ORDER = ["upper right", "lower right", "lower left", "upper left"]
_CORNER_BOX = {
    "upper right": (0.62, 0.62, 1.0, 1.0),
    "lower right": (0.62, 0.0, 1.0, 0.38),
    "lower left":  (0.0, 0.0, 0.38, 0.38),
    "upper left":  (0.0, 0.62, 0.38, 1.0),
}

PANEL_WEIGHT = "normal"   # bold panel letters only when a journal requires it


def darken(hex_color: str, factor: float = 0.78) -> str:
    """Darken a #RRGGBB color by factor (0..1) — used for error bars on light fills."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return hex_color
    r, g, b = (int(h[i:i+2], 16) for i in (0, 2, 4))
    r, g, b = (int(c * factor) for c in (r, g, b))
    return f"#{r:02X}{g:02X}{b:02X}"


def _data_in_box(ax, box) -> int:
    """Count data points (lines + bars) falling inside a corner box (axes-fraction)."""
    x0f, y0f, x1f, y1f = box
    xlim, ylim = ax.get_xlim(), ax.get_ylim()
    dx, dy = xlim[1] - xlim[0], ylim[1] - ylim[0]
    if dx == 0 or dy == 0:
        return 10**9
    bx0, bx1 = xlim[0] + x0f * dx, xlim[0] + x1f * dx
    by0, by1 = ylim[0] + y0f * dy, ylim[0] + y1f * dy
    cnt = 0
    for ln in ax.get_lines():
        xd, yd = np.atleast_1d(ln.get_xdata()), np.atleast_1d(ln.get_ydata())
        for xx, yy in zip(xd, yd):
            try:
                if bx0 <= xx <= bx1 and by0 <= yy <= by1:
                    cnt += 1
            except TypeError:
                pass
    for cont in getattr(ax, "containers", []):
        for patch in getattr(cont, "patches", []):
            try:
                px = patch.get_x() + patch.get_width() / 2
                py = patch.get_height()
                if bx0 <= px <= bx1 and by0 <= py <= by1:
                    cnt += 1
            except Exception:
                pass
    return cnt


def _legend_overlaps(ax, leg) -> bool:
    """True if the RENDERED legend bbox overlaps a data artist or exits the axes.
    (The old anchor-only check missed wide/2-col legends spilling to center — the bug
    that produced the user-reported overlaps.)"""
    fig = ax.figure
    fig.canvas.draw()
    rend = fig.canvas.get_renderer()
    lb = leg.get_window_extent(rend)
    ab = ax.get_window_extent(rend)
    if lb.x0 < ab.x0 - 1 or lb.x1 > ab.x1 + 1 or lb.y0 < ab.y0 - 1 or lb.y1 > ab.y1 + 1:
        return True
    for ln in ax.get_lines():
        try:
            if lb.overlaps(ln.get_window_extent(rend)):
                return True
        except Exception:
            pass
    for cont in getattr(ax, "containers", []):
        for patch in getattr(cont, "patches", []):
            try:
                if lb.overlaps(patch.get_window_extent(rend)):
                    return True
            except Exception:
                pass
    # in-axes text annotations (enzyme/condition labels) — legend must not collide with them.
    for txt in ax.texts:
        try:
            if txt.get_text().strip() and lb.overlaps(txt.get_window_extent(rend)):
                return True
        except Exception:
            pass
    return False


def smart_legend(ax, tol: int = 2, headroom: float = 0.0, ncol: int = 1, fontsize=None, **kwargs):
    """Place legend in a data-free corner (never center, never outside axes, no title).

    Rewritten 2026-06-26 (audit): the old version checked only the anchor, so a wide /
    2-column legend at 'upper right' spilled into center over the data, and tol=0 callers
    collapsed straight to a single 62% y-blowup that broke panel proportions. Now:
    1. Try each corner in preference order, actually DRAW the legend, and accept the first
       whose RENDERED bbox clears all data artists and stays inside the axes (_legend_overlaps).
    2. If no corner works, expand the y-limit in SMALL steps (0.12 -> 0.40, not a single 0.62
       jump) and retry upper-right, taking the first clear fit.
    🔴 frameon=False, title dropped, loc=/center/bbox_to_anchor ignored (corner auto-pick is
       this function's job). Call AFTER all data and the final set_ylim.
    """
    kwargs.pop("title", None)
    kwargs.pop("loc", None)
    kwargs.pop("bbox_to_anchor", None)
    handles, _ = ax.get_legend_handles_labels()
    if not handles:
        return None
    fs = fontsize if fontsize is not None else FS_LEGEND
    for loc in _CORNER_ORDER:
        leg = ax.legend(loc=loc, frameon=False, fontsize=fs, ncol=ncol, **kwargs)
        if not _legend_overlaps(ax, leg):
            return leg
        leg.remove()
    y0, y1 = ax.get_ylim()
    span = y1 - y0
    for h in (0.12, 0.20, 0.30, 0.40):
        ax.set_ylim(y0, y1 + span * h)
        leg = ax.legend(loc="upper right", frameon=False, fontsize=fs, ncol=ncol, **kwargs)
        if not _legend_overlaps(ax, leg):
            return leg
        leg.remove()
    return ax.legend(loc="upper right", frameon=False, fontsize=fs, ncol=ncol, **kwargs)


def styled_errorbar(ax, x, y, yerr, color, capsize=3.0, elinewidth=1.0,
                    top_only=False, **kwargs):
    """Error bars in the series color (darkened), not black.

    ``top_only=True`` draws the upward error only — use for bar charts so small bars
    don't get a downward bar piercing the baseline.
    """
    ec = darken(color, 0.78)
    yerr_arg = [np.zeros_like(np.atleast_1d(yerr)), np.atleast_1d(yerr)] if top_only else yerr
    return ax.errorbar(x, y, yerr=yerr_arg, fmt="none", ecolor=ec,
                       capsize=capsize, elinewidth=elinewidth, capthick=elinewidth,
                       zorder=5, **kwargs)


def panel_label(ax, letter: str, fontsize=14, weight: str | None = None, pad=4):
    """Panel letter (a)(b) at the top-left, normal weight by default (the only
    sanctioned ``set_title`` use). Pass weight='bold' only if the journal requires it."""
    ax.set_title(f"({letter})", loc="left", fontsize=fontsize,
                 fontweight=weight or PANEL_WEIGHT, pad=pad)


def bar_no_edge(ax, *args, **kwargs):
    """ax.bar with no outline (edgecolor='none', linewidth=0) per house rule."""
    kwargs.setdefault("edgecolor", "none")
    kwargs.setdefault("linewidth", 0)
    return ax.bar(*args, **kwargs)


# --- Significance notation (italic statistics) ------------------------------
# Journal rule (Nature/ACS/most): statistical variables/abbreviations are ITALIC;
# operators, digits, and asterisks are roman. 'ns', 'P', 'n', 't', 'F', 'r', 'R',
# 'df' italicize; '*'/'**'/'***', '<', '=', numbers stay roman.
# A plain ``ax.text(x, y, 'ns')`` renders upright and breaks the rule — use these.
_STAT_ITALIC_TOKENS = {"ns", "P", "n", "t", "F", "r", "R", "df", "p"}


def significance_italic(text: str) -> str:
    r"""Return ``text`` with statistical tokens wrapped in italic mathtext.

    Only whole alphabetic tokens in the stats set are italicized; digits, operators,
    and asterisks are left roman. If the string already contains ``$…$`` mathtext it
    is returned unchanged (assume the caller styled it deliberately).

    >>> significance_italic('ns')
    '$\\it{ns}$'
    >>> significance_italic('P < 0.05')
    '$\\it{P}$ < 0.05'
    >>> significance_italic('***')
    '***'
    >>> significance_italic('P = 0.03 (n = 3)')
    '$\\it{P}$ = 0.03 ($\\it{n}$ = 3)'
    """
    import re
    if "$" in text:
        return text
    return re.sub(r"[A-Za-z]+",
                  lambda m: r"$\it{%s}$" % m.group(0)
                  if m.group(0) in _STAT_ITALIC_TOKENS else m.group(0),
                  text)


def stat_annot(ax, x, y, text, *, ha="center", va="bottom",
               fontsize=None, color="k", **kwargs):
    """Place an on-figure significance annotation with the italic-stats rule applied.

    Auto-italicizes ns / P / n / etc. via ``significance_italic``. Use for the label
    above a significance bracket ('ns', '***', 'P = 0.01') instead of a plain
    ``ax.text`` (which would render upright and silently violate the rule).
    """
    return ax.text(x, y, significance_italic(text), ha=ha, va=va,
                   fontsize=fontsize, color=color, **kwargs)


# --- Abbreviation consistency lint (academic-term-rules §2) -----------------
# A set of legend/axis labels must not mix an abbreviation with a full name for
# the same KIND of entity. The classic miss: "D-Gal" (abbrev) next to "Glucose"
# (full) — the sugar pair should be D-Gal + D-Glc, OR D-galactose + D-glucose,
# not one of each. Run this on your legend label list before saving the figure.

# Known sugar full<->abbrev pairs (extend as needed; manuscript definition wins).
_SUGAR_PAIRS = {
    "d-galactose": "D-Gal", "d-gal": "D-Gal",
    "d-glucose": "D-Glc", "d-glc": "D-Glc", "glucose": "D-Glc",
    "d-fructose": "D-Fru", "d-fru": "D-Fru",
    "d-mannose": "D-Man", "d-man": "D-Man",
}


def check_abbrev_consistency(labels):
    """Return a list of (label, issue) for abbreviation inconsistencies in a label set.

    Flags the case where, within the same figure, one sugar is abbreviated and a
    sibling sugar is spelled out (or vice versa) — they must match in style.
    Empty list == consistent. This catches the "D-Gal + Glucose" mismatch.

    >>> check_abbrev_consistency(["D-Gal", "D-Glc", "Formate"])
    []
    >>> [lab for lab, _ in check_abbrev_consistency(["D-Gal", "Glucose", "Formate"])]
    ['Glucose']
    """
    norm = [(lab, lab.strip().lower()) for lab in labels]
    sugar_styles = {}  # label -> 'abbrev' | 'full'
    for lab, low in norm:
        if low not in _SUGAR_PAIRS:
            continue
        canon = _SUGAR_PAIRS[low]
        style = "abbrev" if lab.strip().lower() == canon.lower() else "full"
        sugar_styles[lab] = (style, canon)
    issues = []
    styles_present = {s for s, _ in sugar_styles.values()}
    if "abbrev" in styles_present and "full" in styles_present:
        for lab, (style, canon) in sugar_styles.items():
            if style == "full":
                issues.append(
                    (lab, f"sugar spelled out while a sibling is abbreviated; "
                          f"use '{canon}' to match the abbreviated labels"))
    return issues

