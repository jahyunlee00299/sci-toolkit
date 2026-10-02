"""Circular vector construct map (a circular plasmid map), drawn with matplotlib.

``generate_vector_construct_map`` is re-exported by ``cloning_report`` so the
historical import path keeps working. The drawing is split into small steps
(backbone circle, insert, RE ticks, fusion tags, signal peptide, backbone
features, centre text, frame status, direction arrow, date, legend) that run in
a fixed order; the order matters because artists with equal zorder are painted
in creation order. tests/test_characterization.py pins every artist.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import numpy as np

from ._plot_style import FONT as _FONT, FONT_SANS as _FONT_SANS


# ── Backbone feature data for supported vectors ─────────────────────────────
# Angular fractions (0 = top/12 o'clock, clockwise) + approximate sizes
# Based on GenBank annotations for each vector series.

_BACKBONE_FEATURES: dict[str, dict] = {
    "pET-28a(+)": {
        "total_bp": 5369,
        "resistance": "KanR",
        "features": [
            # (name, frac_start, frac_span, color, label_side)
            ("T7 promoter",    0.065, 0.010, "#E74C3C", "out"),
            ("lac operator",   0.076, 0.008, "#E67E22", "out"),
            ("RBS",            0.085, 0.004, "#F39C12", "out"),
            ("T7 terminator",  0.005, 0.015, "#C0392B", "out"),
            ("lacI",           0.14,  0.20,  "#95A5A6", "out"),
            ("KanR",           0.74,  0.15,  "#E74C3C", "out"),
            ("f1 ori",         0.91,  0.08,  "#3498DB", "out"),
            ("pBR322 ori",     0.61,  0.12,  "#2980B9", "out"),
        ],
    },
    "pET-21a(+)": {
        "total_bp": 5443,
        "resistance": "AmpR",
        "features": [
            ("T7 promoter",    0.065, 0.010, "#E74C3C", "out"),
            ("lac operator",   0.076, 0.008, "#E67E22", "out"),
            ("RBS",            0.085, 0.004, "#F39C12", "out"),
            ("T7 terminator",  0.005, 0.015, "#C0392B", "out"),
            ("lacI",           0.14,  0.20,  "#95A5A6", "out"),
            ("AmpR",           0.72,  0.16,  "#E74C3C", "out"),
            ("f1 ori",         0.91,  0.08,  "#3498DB", "out"),
            ("pBR322 ori",     0.61,  0.10,  "#2980B9", "out"),
        ],
    },
    "pMAL-c6T": {
        "total_bp": 6721,
        "resistance": "AmpR",
        "features": [
            ("Ptac promoter",  0.065, 0.010, "#E74C3C", "out"),
            ("malE (MBP)",     0.08,  0.17,  "#8E44AD", "out"),
            ("TEV site",       0.25,  0.005, "#F39C12", "out"),
            ("rrnB terminator",0.005, 0.015, "#C0392B", "out"),
            ("AmpR",           0.72,  0.14,  "#E74C3C", "out"),
            ("pBR322 ori",     0.58,  0.10,  "#2980B9", "out"),
            ("lacIq",          0.38,  0.15,  "#95A5A6", "out"),
        ],
    },
}

# Duet vectors reuse pET backbone layout
for _duet in ("pETDuet-1:MCS1", "pETDuet-1:MCS2",
              "pACYCDuet-1:MCS1", "pACYCDuet-1:MCS2"):
    _res = "CmR" if "pACYC" in _duet else "AmpR"
    _BACKBONE_FEATURES[_duet] = {
        "total_bp": 5420 if "pET" in _duet else 4008,
        "resistance": _res,
        "features": [
            ("T7 promoter",  0.065, 0.010, "#E74C3C", "out"),
            ("T7 terminator",0.005, 0.015, "#C0392B", "out"),
            ("lacI",         0.14,  0.20,  "#95A5A6", "out"),
            (_res,           0.72,  0.15,  "#E74C3C", "out"),
            ("ori",          0.61,  0.10,  "#2980B9", "out"),
        ],
    }


# ── Color palette for construct map ──────────────────────────────────────────

_CM = {
    "backbone":    "#B0BEC5",
    "insert":      "#2ECC71",
    "tag":         "#9B59B6",
    "re_site":     "#E74C3C",
    "promoter":    "#E74C3C",
    "resistance":  "#E74C3C",
    "origin":      "#3498DB",
    "regulatory":  "#95A5A6",
    "signal_pep":  "#F39C12",
}


# ── Layout constants ─────────────────────────────────────────────────────────

_RADIUS = 1.0           # backbone circle radius
_LW_BACKBONE = 10
_LW_FEATURE = 14
_LW_INSERT = 18


# ── Circular canvas helpers ──────────────────────────────────────────────────

def _frac_to_angle(frac):
    """Fraction (0=top, clockwise) to matplotlib angle (degrees, CCW from right)."""
    return 90 - frac * 360


class _CircularCanvas:
    """Axes plus the fraction-of-circle drawing primitives used by the map."""

    def __init__(self, ax, radius: float = _RADIUS):
        self.ax = ax
        self.R = radius

    def draw_arc(self, frac_start, frac_span, radius, color, linewidth, zorder=2):
        """Draw a colored arc on the circle."""
        angle_start = _frac_to_angle(frac_start + frac_span)
        angle_end = _frac_to_angle(frac_start)
        theta = np.linspace(np.radians(angle_start), np.radians(angle_end), 100)
        x = radius * np.cos(theta)
        y = radius * np.sin(theta)
        self.ax.plot(x, y, color=color, linewidth=linewidth, solid_capstyle="round", zorder=zorder)

    def label_at_frac(self, frac, text, radius_offset=0.18, fontsize=8, color="#333",
                      fontweight="normal", ha_override=None):
        """Place a label at a fraction position, pointing outward."""
        angle_rad = np.radians(_frac_to_angle(frac))
        r_label = self.R + radius_offset
        x = r_label * np.cos(angle_rad)
        y = r_label * np.sin(angle_rad)

        # Determine horizontal alignment based on position
        if ha_override:
            ha = ha_override
        elif abs(x) < 0.05:
            ha = "center"
        elif x > 0:
            ha = "left"
        else:
            ha = "right"

        self.ax.text(x, y, text, fontsize=fontsize, fontweight=fontweight,
                     fontfamily=_FONT_SANS, color=color, ha=ha, va="center",
                     zorder=10)

    def tick_at_frac(self, frac, radius, length=0.04, color="#555", lw=1.5):
        """Draw a small radial tick mark."""
        angle_rad = np.radians(_frac_to_angle(frac))
        x1 = (radius - length / 2) * np.cos(angle_rad)
        y1 = (radius - length / 2) * np.sin(angle_rad)
        x2 = (radius + length / 2) * np.cos(angle_rad)
        y2 = (radius + length / 2) * np.sin(angle_rad)
        self.ax.plot([x1, x2], [y1, y2], color=color, linewidth=lw, zorder=5)


# ── Backbone lookup ──────────────────────────────────────────────────────────

def _normalise_vector_name(name: str) -> str:
    return name.lower().replace(" ", "").replace("-", "").replace("(", "").replace(")", "").replace("+", "")


def _resolve_backbone(vector_name: str) -> dict:
    """Backbone layout for ``vector_name`` (canonical-name match), else a generic E. coli vector."""
    wanted = _normalise_vector_name(vector_name)
    for canon_name, bb_data in _BACKBONE_FEATURES.items():
        if _normalise_vector_name(canon_name) == wanted:
            return bb_data
    # Fallback: generic E. coli expression vector
    return {
        "total_bp": 5000,
        "resistance": "AmpR",
        "features": [
            ("Promoter",    0.065, 0.010, "#E74C3C", "out"),
            ("Terminator",  0.005, 0.015, "#C0392B", "out"),
            ("AmpR",        0.72,  0.15,  "#E74C3C", "out"),
            ("ori",         0.61,  0.10,  "#2980B9", "out"),
        ],
    }


# ── Drawing steps (called in this order by generate_vector_construct_map) ────

def _draw_backbone_circle(cv: _CircularCanvas) -> None:
    circle = plt.Circle((0, 0), cv.R, fill=False, edgecolor=_CM["backbone"],
                        linewidth=_LW_BACKBONE, zorder=1)
    cv.ax.add_patch(circle)


def _insert_geometry(insert_len: int, total_bp: int) -> tuple[float, float]:
    """(insert_start_frac, insert_frac): the insert arc is centred at the top."""
    insert_frac = insert_len / total_bp if total_bp > 0 else 0.1
    insert_frac = max(insert_frac, 0.06)  # minimum visibility
    insert_start_frac = 1.0 - insert_frac / 2  # centered at top
    return insert_start_frac, insert_frac


def _draw_insert(cv: _CircularCanvas, gene_name: str, insert_len: int,
                 insert_start_frac: float, insert_frac: float) -> None:
    cv.draw_arc(insert_start_frac, insert_frac, cv.R, _CM["insert"], _LW_INSERT, zorder=3)

    insert_mid = (insert_start_frac + insert_frac / 2) % 1.0
    cv.label_at_frac(insert_mid, f"{gene_name}\n({insert_len} bp)",
                     radius_offset=0.22, fontsize=11, color="#1B5E20",
                     fontweight="bold")


def _draw_re_sites(cv: _CircularCanvas, re_5prime: str, re_3prime: str,
                   insert_start_frac: float, insert_frac: float) -> None:
    if re_5prime:
        cv.tick_at_frac(insert_start_frac, cv.R, length=0.08, color=_CM["re_site"], lw=2.5)
        cv.label_at_frac(insert_start_frac, re_5prime,
                         radius_offset=0.14, fontsize=8, color=_CM["re_site"],
                         fontweight="bold")

    if re_3prime:
        re3_frac = (insert_start_frac + insert_frac) % 1.0
        cv.tick_at_frac(re3_frac, cv.R, length=0.08, color=_CM["re_site"], lw=2.5)
        cv.label_at_frac(re3_frac, re_3prime,
                         radius_offset=0.14, fontsize=8, color=_CM["re_site"],
                         fontweight="bold")


def _draw_fusion_tags(cv: _CircularCanvas, frame_check: dict,
                      insert_start_frac: float, insert_frac: float) -> None:
    """Small purple arcs for N-terminal tags (before the insert) and C-terminal tags (after).

    Tag names are parsed out of ``frame_check["topology"]``.
    """
    topology = frame_check.get("topology", "")
    tag_frac_size = 0.015  # small arc for tags

    # N-terminal tags (before insert)
    n_tags = []
    if "[N-His6]" in topology:
        n_tags.append("N-His6")
    if "[Thrombin]" in topology:
        n_tags.append("Thrombin")
    if "[T7-tag]" in topology:
        n_tags.append("T7-tag")

    for i, tag in enumerate(n_tags):
        tag_start = insert_start_frac - (i + 1) * tag_frac_size
        cv.draw_arc(tag_start, tag_frac_size, cv.R, _CM["tag"], _LW_FEATURE, zorder=3)
        if i == 0:  # only label the first/nearest tag
            cv.label_at_frac(tag_start + tag_frac_size / 2,
                             " + ".join(n_tags),
                             radius_offset=0.15, fontsize=7.5, color="#6A1B9A")

    # C-terminal tags (after insert)
    c_tags = []
    if "[C-His6]" in topology and ":OUT-OF-FRAME" not in topology:
        c_tags.append("C-His6")
    if "[S-tag]" in topology and ":OUT-OF-FRAME" not in topology:
        c_tags.append("S-tag")

    for i, tag in enumerate(c_tags):
        tag_start = (insert_start_frac + insert_frac + i * tag_frac_size) % 1.0
        cv.draw_arc(tag_start, tag_frac_size, cv.R, _CM["tag"], _LW_FEATURE, zorder=3)
        if i == 0:
            cv.label_at_frac((tag_start + tag_frac_size / 2) % 1.0,
                             " + ".join(c_tags),
                             radius_offset=0.15, fontsize=7.5, color="#6A1B9A")


def _draw_signal_peptide(cv: _CircularCanvas, signal_peptide: dict, insert_len: int,
                         total_bp: int, insert_start_frac: float, insert_frac: float) -> None:
    """Signal-peptide stretch inside the insert arc, with a cleavage tick and scissors."""
    R = cv.R
    cleavage = signal_peptide.get("cleavage_site_estimate", 20)
    if not (cleavage and insert_len > 0):
        return
    sp_bp = cleavage * 3  # approximate bp for signal peptide
    sp_frac = (sp_bp / total_bp) if total_bp > 0 else 0.02
    sp_frac = min(sp_frac, insert_frac * 0.4)  # max 40% of insert arc
    # Draw signal peptide as a distinct color within the insert arc
    cv.draw_arc(insert_start_frac, sp_frac, R, _CM["signal_pep"], _LW_INSERT - 2, zorder=4)
    # Add "scissors" annotation for cleavage site
    sp_end_frac = (insert_start_frac + sp_frac) % 1.0
    cv.tick_at_frac(sp_end_frac, R, length=0.10, color="#D35400", lw=2)
    sp_angle = np.radians(_frac_to_angle(sp_end_frac))
    sx = (R + 0.08) * np.cos(sp_angle)
    sy = (R + 0.08) * np.sin(sp_angle)
    cv.ax.text(sx, sy, "✂", fontsize=14, ha="center", va="center",
               color="#D35400", zorder=10)
    cv.label_at_frac((insert_start_frac + sp_frac / 2) % 1.0,
                     f"SP ({cleavage} aa)",
                     radius_offset=-0.18, fontsize=7.5, color="#D35400",
                     fontweight="bold")


def _draw_backbone_features(cv: _CircularCanvas, backbone: dict) -> None:
    for feat_name, f_start, f_span, f_color, _ in backbone["features"]:
        cv.draw_arc(f_start, f_span, cv.R, f_color, _LW_FEATURE, zorder=2)
        cv.label_at_frac(f_start + f_span / 2, feat_name,
                         radius_offset=0.18, fontsize=7.5, color="#444")


def _draw_center_text(ax, vector_name: str, gene_name: str, total_bp: int) -> None:
    ax.text(0, 0.12, vector_name, fontsize=16, fontweight="bold",
            ha="center", va="center", fontfamily=_FONT_SANS, color="#1A237E")
    ax.text(0, -0.05, f"+ {gene_name}", fontsize=12,
            ha="center", va="center", fontfamily=_FONT_SANS, color="#2E7D32")
    ax.text(0, -0.22, f"{total_bp:,} bp", fontsize=11,
            ha="center", va="center", fontfamily=_FONT, color="#555")


def _draw_frame_status(ax, frame_check: dict) -> None:
    in5 = frame_check.get("in_frame_5prime", False)
    in3 = frame_check.get("in_frame_3prime", False)
    mark5 = "✓" if in5 else "✗"
    mark3 = "✓" if in3 else "✗"

    ax.text(0, -0.42, f"5' frame: {mark5}  |  3' frame: {mark3}",
            fontsize=9, ha="center", va="center", fontfamily=_FONT_SANS,
            color="#555")


def _draw_direction_arrow(cv: _CircularCanvas) -> None:
    """Clockwise arrow at the bottom of the circle."""
    R = cv.R
    arrow_frac = 0.5  # bottom of circle
    arrow_angle = np.radians(_frac_to_angle(arrow_frac))
    cv.ax.annotate("",
                   xy=((R + 0.02) * np.cos(arrow_angle + 0.05),
                       (R + 0.02) * np.sin(arrow_angle + 0.05)),
                   xytext=((R + 0.02) * np.cos(arrow_angle - 0.05),
                           (R + 0.02) * np.sin(arrow_angle - 0.05)),
                   arrowprops=dict(arrowstyle="->", color="#888", lw=1.5),
                   zorder=5)


def _draw_date(ax) -> None:
    ax.text(0, -0.58, f"Generated: {date.today().isoformat()}",
            fontsize=7, ha="center", va="center", fontfamily=_FONT,
            color="#999")


def _draw_legend(ax, signal_peptide: dict | None) -> None:
    legend_items = [
        (_CM["insert"], "Insert CDS"),
        (_CM["tag"], "Fusion tag"),
        (_CM["re_site"], "Promoter / Resistance"),
        (_CM["origin"], "Origin of replication"),
        (_CM["regulatory"], "Regulatory"),
    ]
    if signal_peptide and signal_peptide.get("has_signal_peptide"):
        legend_items.insert(1, (_CM["signal_pep"], "Signal peptide"))

    legend_y = -1.35
    legend_x_start = -1.2
    for i, (lc, lt) in enumerate(legend_items):
        x = legend_x_start + i * 0.55
        ax.add_patch(FancyBboxPatch(
            (x, legend_y - 0.03), 0.08, 0.06,
            boxstyle="round,pad=0.01",
            facecolor=lc, edgecolor="#999", linewidth=0.5,
        ))
        ax.text(x + 0.10, legend_y, lt, fontsize=6.5,
                fontfamily=_FONT_SANS, va="center", color="#555")


# ── Public API: Circular Vector Construct Map ────────────────────────────────

def generate_vector_construct_map(
    vector_name: str,
    gene_name: str = "Insert",
    insert_len: int = 0,
    re_5prime: str = "",
    re_3prime: str = "",
    include_stop: bool = False,
    frame_check: dict | None = None,
    signal_peptide: dict | None = None,
    output_path: Path | str | None = None,
) -> Path:
    """Generates a circular vector construct map (a circular plasmid map) PNG.

    Parameters
    ----------
    vector_name : str
        Vector name (e.g. "pET-28a(+)")
    gene_name : str
        Name of the inserted gene
    insert_len : int
        Insert length (bp)
    re_5prime, re_3prime : str
        5'/3' restriction enzyme names
    include_stop : bool
        Whether the insert includes a stop codon
    frame_check : dict | None
        Result of check_reading_frame()
    signal_peptide : dict | None
        Signal peptide analysis result (has_signal_peptide, cleavage_site_estimate, etc.)
    output_path : Path | str | None
        Output file path (.png)

    Returns
    -------
    Path : Path to the generated PNG file
    """
    if output_path is None:
        output_path = Path.cwd() / f"{gene_name}_{vector_name.replace('(', '').replace(')', '').replace('+', '')}_construct.png"
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(1, 1, figsize=(10, 10), facecolor="white")
    ax.set_xlim(-1.6, 1.6)
    ax.set_ylim(-1.6, 1.6)
    ax.set_aspect("equal")
    ax.set_axis_off()

    backbone = _resolve_backbone(vector_name)
    total_bp = backbone["total_bp"] + insert_len
    cv = _CircularCanvas(ax)

    _draw_backbone_circle(cv)

    # Insert region: arc + label + RE ticks + fusion tags + signal peptide
    insert_start_frac, insert_frac = _insert_geometry(insert_len, total_bp)
    _draw_insert(cv, gene_name, insert_len, insert_start_frac, insert_frac)
    _draw_re_sites(cv, re_5prime, re_3prime, insert_start_frac, insert_frac)
    if frame_check:
        _draw_fusion_tags(cv, frame_check, insert_start_frac, insert_frac)
    if signal_peptide and signal_peptide.get("has_signal_peptide"):
        _draw_signal_peptide(cv, signal_peptide, insert_len, total_bp,
                             insert_start_frac, insert_frac)

    _draw_backbone_features(cv, backbone)

    # Annotations
    _draw_center_text(ax, vector_name, gene_name, total_bp)
    if frame_check:
        _draw_frame_status(ax, frame_check)
    _draw_direction_arrow(cv)
    _draw_date(ax)
    _draw_legend(ax, signal_peptide)

    fig.savefig(str(output_path), dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    return output_path
