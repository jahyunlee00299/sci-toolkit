"""make_fig_template.py — copy this to start a new manuscript figure. DO NOT author from blank.

This template is the RULE-INJECTION POINT (figure_aesthetics_rules.md R0): it pre-wires the
helper imports, a layout manager, per-panel panel_label + smart_legend, the SSOT color/font
accessors, and a correct savefig — so a new figure obeys the rules by construction instead of
re-deriving (and forgetting) them. After editing, the figure is done only when
`python figure_lint.py <thisfile>` reports 0 high-severity findings.

Workflow note: when a workflow creates a new figure, COPY this file and fill in the panels —
never Write a blank render script. That is what stops "rules get ignored on figure work."
"""
from __future__ import annotations

# Windows 기본 콘솔은 cp949 라서 한글/기호 출력에서 죽는다. UTF-8로 맞춘다.
# reconfigure 를 쓴다: TextIOWrapper 로 감싸면 원본 스트림을 소유하게 되어,
# 이 모듈이 import 된 뒤 래퍼가 GC 될 때 호출자의 stdout 까지 닫는다(실측).
import sys as _sys
for _s in (_sys.stdout, _sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
import sys
sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import matplotlib.pyplot as plt

# --- SSOT helpers: colors/fonts/legend/errorbar all come from here, never literals ---
# (Use the project's theme.py if present; else the skill's aesthetic_helpers.)
try:
    import theme  # project-local prism theme (theme.py via paths)
    import paths
    _T = theme.apply_theme("themeB")
    series_color = theme.series_color
    OKABE_ITO = theme.OKABE_ITO
    NEUTRAL_PAIR = theme.NEUTRAL_PAIR
    C_ANNOT = theme.C_ANNOT
    FS_AXIS, FS_TICK, FS_LEGEND, FS_ANNOT = theme.FS_AXIS, theme.FS_TICK, theme.FS_LEGEND, theme.FS_ANNOT
    smart_legend = theme.smart_legend
    styled_errorbar = theme.styled_errorbar
    panel_label = theme.panel_label
    apply_axis_style = lambda ax: theme.apply_axis_style(ax, _T)
    OUT = paths.ensure_out("themeB")
except ImportError:
    from aesthetic_helpers import (smart_legend, styled_errorbar, panel_label,
                                   series_color, FS_AXIS, FS_TICK, FS_LEGEND, FS_ANNOT, C_ANNOT)
    from pathlib import Path
    OUT = Path("out"); OUT.mkdir(exist_ok=True)
    apply_axis_style = lambda ax: None


def load_data():
    """Read rawdata here (openpyxl/json/csv). Return what the panels need.
    🔴 Numbers come from rawdata only — never hardcode a value (caption-sync rule)."""
    raise NotImplementedError("fill in: read the rawdata sheet/file")


def panel_a(ax, data):
    # ... plot series (ax.plot / ax.bar / ax.scatter) ...
    ax.set_xlabel("X (unit)")
    ax.set_ylabel("Y (unit)")
    # in-axes annotation text: color=C_ANNOT (never a literal hex)
    # ax.text(0.03, 0.97, r"$\it{Ro}$Gdh", transform=ax.transAxes,
    #         fontsize=FS_ANNOT, va="top", ha="left", color=C_ANNOT)
    apply_axis_style(ax)
    panel_label(ax, "a")
    smart_legend(ax)          # AFTER all data + final set_ylim. corner auto, never loc=/center


def main():
    data = load_data()
    # ONE layout manager for the whole manuscript set (R4):
    fig, axes = plt.subplots(1, 1, figsize=(3.5, 3.0), constrained_layout=True)  # Nature 1-col
    panel_a(axes, data)
    # savefig MUST have dpi=300 + bbox_inches='tight' + facecolor='white' (R0):
    fig.savefig(OUT / "FigN.png", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("SAVED", OUT / "FigN.png")
    # Emit the caption from the SAME rawdata values (no hand-typing) → FigN.caption.txt.


if __name__ == "__main__":
    main()
