"""Figure advisor — recommends BOTH the chart type and the panel layout.

Two questions answered from the data's shape, rigorously and with reasons:

1. chart_type(data_profile)  -> ranked chart kinds (bar / line / scatter / donut /
   contour / box / grouped-bar / stacked-bar) with a score and a one-line rationale
   and the gotchas to watch.
2. suggest_layout(n_panels)  -> ranked grid layouts with placeholder previews
   (this is the layout half; see layout scoring below).

The chart recommender is rule-based on a small DataProfile so the choice is auditable —
no black box. Encodes the conventions in references/figure_aesthetics_rules.md and
plot_style_sigmaplot_prism.md (biocatalysis / enzyme-kinetics figures).

Usage:
    python figure_advisor.py chart --x time --y continuous --series 5 --repeats 3
    python figure_advisor.py chart --x category --y continuous --groups 4 --repeats 3
    python figure_advisor.py chart --tradeoff yield,titer --front pareto
    python figure_advisor.py layout 4 --col double
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
import itertools
from dataclasses import dataclass, field
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import gridspec


# ---------------------------------------------------------------------------
# Part 1 — chart-type recommendation
# ---------------------------------------------------------------------------

@dataclass
class DataProfile:
    """What you know about the data before plotting. All optional; more = better advice."""
    x_kind: str = "continuous"      # "continuous" | "category" | "ordinal" | "time"
    y_kind: str = "continuous"      # usually "continuous"
    n_series: int = 1               # number of overlaid series / curves
    n_groups: int = 0               # number of categorical groups (for bar)
    repeats: int = 1                # replicates (n) -> error bars meaningful if >1
    is_tradeoff: bool = False       # two objectives traded off (Pareto)
    has_front: bool = False         # a Pareto/optimal front to draw
    is_part_of_whole: bool = False  # composition / cost breakdown summing to a total
    is_2d_response: bool = False    # response over a 2-factor grid (RSM)
    is_distribution: bool = False   # comparing distributions, many points per group
    monotonic_time: bool = False    # x is time and y accumulates (time course)


# Each recommender returns (score 0..100, rationale, gotchas[]) given a profile.
def _bar(p: DataProfile):
    if p.x_kind not in ("category", "ordinal"):
        return 0, "", []
    score = 80
    why = "categorical x with a single value per group -> bars compare magnitudes directly"
    gotchas = ["no bar outline (edgecolor='none')",
               "upward error bar only (top_only) so small bars don't pierce baseline",
               "x margin so first/last bar doesn't touch the spine (not tight-x)"]
    if p.n_groups and p.n_groups <= 6 and p.n_series > 1:
        score = 88
        why = "few categories x a few sub-series -> grouped bar reads cleanly"
        gotchas.append("<=5 sub-series; beyond that switch to small-multiples")
    if p.n_groups > 8:
        score -= 25
        gotchas.append("many categories -> consider horizontal bars or a dot plot")
    if p.repeats > 1:
        gotchas.append("show mean +/- SD (n>=3); state n in caption")
    return score, why, gotchas


def _line(p: DataProfile):
    if p.x_kind not in ("continuous", "time", "ordinal"):
        return 0, "", []
    # a line needs an ordered x carrying a trend — not a breakdown / RSM / distribution.
    if p.is_part_of_whole or p.is_2d_response or p.is_distribution or p.is_tradeoff:
        return 0, "", []
    score = 70
    why = "continuous/ordered x with connected trend -> line shows the trajectory"
    gotchas = ["markers ON for measured points, solid line through them",
               "dashed only for fit extrapolation, never for the data itself"]
    if p.monotonic_time or p.x_kind == "time":
        score = 90
        why = "time course -> line + markers is the standard; one line per condition"
        gotchas.append("marker white edge so overlapping points at early t stay distinct")
    if p.n_series >= 6:
        score -= 10
        gotchas.append(">=6 series crowd a legend; move legend out-of-data or split panels")
    if p.repeats > 1:
        gotchas.append("error bars in the series color (not black), cap above marker")
    return score, why, gotchas


def _scatter(p: DataProfile):
    if p.is_tradeoff:
        score = 92
        why = "two objectives traded off -> scatter is the only honest view (no false trend line)"
        gotchas = ["draw the Pareto front as a stepped/connected line, points as markers",
                   "mark the experimentally validated point(s) distinctly",
                   "no regression line through a trade-off cloud"]
        return score, why, gotchas
    # scatter only when there really are two free continuous variables to relate —
    # NOT for breakdowns, RSM grids, distributions, or plain time courses.
    if (p.x_kind == "continuous" and p.y_kind == "continuous" and not p.monotonic_time
            and not p.is_part_of_whole and not p.is_2d_response and not p.is_distribution
            and p.n_groups == 0):
        score = 75
        why = "two continuous variables, relationship unknown -> scatter (add fit only if justified)"
        gotchas = ["only add a fit line if a model is justified; show R^2/CI then",
                   "marker edge for density"]
        return score, why, gotchas
    return 0, "", []


def _donut(p: DataProfile):
    if not p.is_part_of_whole:
        return 0, "", []
    score = 72
    why = "parts of a single total (cost/composition breakdown) -> donut shows share at a glance"
    gotchas = ["<=6 slices; merge small ones into 'Other'",
               "put the total (e.g. the overall cost/amount) in the center",
               "for comparing breakdowns ACROSS cases, a stacked/100% bar beats several donuts"]
    if p.n_groups and p.n_groups > 1:
        score = 60
        gotchas.append("comparing multiple cases -> prefer stacked bar over multiple donuts")
    return score, why, gotchas


def _stacked(p: DataProfile):
    if not (p.is_part_of_whole and p.n_groups and p.n_groups > 1):
        return 0, "", []
    return 80, ("parts of a whole compared ACROSS several cases -> 100%/stacked bar "
                "lines the shares up for direct comparison"), \
           ["order segments consistently across bars", "label or legend the segments, no center text"]


def _contour(p: DataProfile):
    if not p.is_2d_response:
        return 0, "", []
    return 85, ("a response over a 2-factor grid (RSM) -> filled contour (or 3D surface) "
                "shows the optimum region"), \
           ["prefer 2D filled contour over 3D for print readability",
            "viridis colormap; mark the optimum",
            "3D surfaces score low on SSIM vs originals — that's expected, verify by data"]


def _box(p: DataProfile):
    if not p.is_distribution:
        return 0, "", []
    return 82, ("comparing distributions with many points per group -> box/violin "
                "shows spread, not just the mean"), \
           ["overlay individual points (strip) when n is small",
            "violin only when n is large enough to estimate a density"]


_RECOMMENDERS = {
    "bar": _bar, "grouped-bar": _bar, "line": _line, "scatter": _scatter,
    "donut": _donut, "stacked-bar": _stacked, "contour/3D": _contour, "box/violin": _box,
}


def recommend_chart(profile: DataProfile, top: int = 3):
    """Return ranked chart-type recommendations with rationale + gotchas."""
    seen = {}
    for kind, fn in _RECOMMENDERS.items():
        score, why, gotchas = fn(profile)
        if score <= 0:
            continue
        # bar and grouped-bar share _bar; keep the better-labeled one
        key = "grouped-bar" if (kind == "grouped-bar" and profile.n_series > 1) else kind
        if kind == "bar" and profile.n_series > 1:
            continue  # let grouped-bar represent it
        if kind == "grouped-bar" and profile.n_series <= 1:
            continue
        if key not in seen or score > seen[key][0]:
            seen[key] = (score, why, gotchas)
    ranked = sorted(({"chart": k, "score": v[0], "why": v[1], "gotchas": v[2]}
                     for k, v in seen.items()), key=lambda d: -d["score"])
    return ranked[:top]


# ---------------------------------------------------------------------------
# Part 2 — layout recommendation (placeholder previews)
# ---------------------------------------------------------------------------

COL_WIDTH = {"single": 3.4, "double": 7.0, "1.5col": 5.0}


def _grid_candidates(n: int):
    out = []
    for cols in range(1, n + 1):
        rows = -(-n // cols)
        empty = rows * cols - n
        if empty >= cols:
            continue
        out.append((rows, cols, empty))
    return out


def _score_layout(rows, cols, empty, n, panel_ar, target):
    width_in = COL_WIDTH[target]
    cell_w = width_in / cols
    cell_h = cell_w / panel_ar
    fig_h = cell_h * rows
    waste = empty / (rows * cols)
    too_tall = max(0, fig_h - 8.0) / 4.0
    too_flat = max(0, (width_in / fig_h) - 3.5) / 3.5
    skinny = max(0, (cell_h / cell_w) - 2.2) / 2.2
    row_penalty = max(0, rows - 3) * 0.06
    score = 100 * (1 - 0.45 * waste - 0.40 * too_tall - 0.15 * too_flat - 0.20 * skinny) \
        - 100 * row_penalty
    return round(max(0, min(100, score)), 1), round(width_in, 2), round(fig_h, 2)


def suggest_layout(n, panel_ar=1.3, target="double", top=3):
    out = []
    for rows, cols, empty in _grid_candidates(n):
        sc, w, h = _score_layout(rows, cols, empty, n, panel_ar, target)
        out.append({"rows": rows, "cols": cols, "empty": empty, "score": sc,
                    "figsize": (w, h)})
    return sorted(out, key=lambda d: -d["score"])[:top]


def render_layout_preview(n, rows, cols, figsize, out_path):
    fig = plt.figure(figsize=figsize)
    gs = gridspec.GridSpec(rows, cols, figure=fig, wspace=0.25, hspace=0.30)
    abc = "abcdefghijklmnop"
    for i in range(n):
        r, c = divmod(i, cols)
        ax = fig.add_subplot(gs[r, c])
        ax.set_xticks([]); ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_edgecolor("#888"); sp.set_linewidth(1.0)
        ax.text(0.04, 0.92, f"({abc[i]})", transform=ax.transAxes, fontsize=13,
                va="top", family="Arial")
        ax.text(0.5, 0.5, f"panel {i+1}", transform=ax.transAxes, ha="center",
                va="center", color="#aaa", fontsize=10, family="Arial")
    fig.savefig(out_path, dpi=110, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _arg(flag, default=None):
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


def _print_chart(profile):
    recs = recommend_chart(profile)
    print(f"\nChart-type recommendation (x={profile.x_kind}, y={profile.y_kind}, "
          f"series={profile.n_series}, groups={profile.n_groups}, n={profile.repeats}):\n")
    for k, r in enumerate(recs):
        print(f"  {k+1}. {r['chart']:<12} score {r['score']}")
        print(f"     why: {r['why']}")
        for g in r['gotchas']:
            print(f"       - {g}")
    if not recs:
        print("  (no match — refine the data profile)")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "chart"
    if mode == "chart":
        prof = DataProfile(
            x_kind=_arg("--x", "continuous"),
            y_kind=_arg("--y", "continuous"),
            n_series=int(_arg("--series", "1")),
            n_groups=int(_arg("--groups", "0")),
            repeats=int(_arg("--repeats", "1")),
            is_tradeoff=("--front" in sys.argv or _arg("--tradeoff") is not None),
            has_front=("--front" in sys.argv),
            is_part_of_whole=("--breakdown" in sys.argv),
            is_2d_response=("--rsm" in sys.argv),
            is_distribution=("--dist" in sys.argv),
            monotonic_time=(_arg("--x") == "time"),
        )
        _print_chart(prof)
    elif mode == "layout":
        from pathlib import Path
        n = int(sys.argv[2])
        target = _arg("--col", "double")
        ar = float(_arg("--ar", "1.3"))
        outdir = Path.cwd() / "layouts"; outdir.mkdir(exist_ok=True)
        res = suggest_layout(n, ar, target)
        print(f"\nLayout suggestions for {n} panels ({target} column):\n")
        for k, d in enumerate(res):
            name = f"layout_{d['rows']}x{d['cols']}_rank{k+1}.png"
            render_layout_preview(n, d["rows"], d["cols"], d["figsize"], outdir / name)
            print(f"  {k+1}. {d['rows']}x{d['cols']}  score {d['score']}  "
                  f"figsize {d['figsize']}  empty {d['empty']}  -> {name}")
    else:
        print("usage: figure_advisor.py [chart|layout] ...")
