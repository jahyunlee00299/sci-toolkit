#!/usr/bin/env python
"""lab_plot.py — Publication-quality data plots in SigmaPlot / Prism / recommended styles.

Supports 7 figure types (per `figure_type_routing` in plot_style_tokens.json):
  - kinetic_time_course (single / multi)
  - hplc_chromatogram
  - dose_response  (4PL fit + IC50/EC50 marker)
  - ph_rate
  - bo_surface_contour
  - bar_with_error (significance markers)
  - pareto_front

Style presets: sigmaplot / prism / recommended (default).
Wong palette (Nature Methods 2011) is built into 'recommended'.

CLI:
  python lab_plot.py --kind time_course --csv data.csv --style recommended --out runs/

Library usage:
  from lab_plot import apply_style, plot_time_course
  apply_style("recommended")
  fig = plot_time_course(...)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable, Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

TOKENS_PATH = (Path(__file__).resolve().parent.parent
               / "references" / "plot_style_tokens.json")


def load_tokens(path: Path | None = None) -> dict:
    p = Path(path) if path else TOKENS_PATH
    return json.loads(p.read_text(encoding="utf-8"))


def apply_style(preset: str = "recommended", tokens: dict | None = None) -> dict:
    """Set matplotlib rcParams from the given preset; return the resolved preset dict."""
    tk = tokens or load_tokens()
    presets = tk["presets"]
    if preset not in presets:
        raise KeyError(f"unknown preset '{preset}' (choose from {list(presets)})")
    sp = presets[preset]
    plt.rcdefaults()
    for k, v in sp["rcParams"].items():
        plt.rcParams[k] = v
    # color cycle
    from cycler import cycler
    plt.rcParams["axes.prop_cycle"] = cycler(color=sp["color_cycle"])
    return sp


def _save(fig, out_dir: Path, stem: str, dpi: int = 600) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    svg = out_dir / f"{stem}.svg"
    png = out_dir / f"{stem}.png"
    fig.savefig(svg, format="svg", bbox_inches="tight", pad_inches=0.04)
    fig.savefig(png, format="png", dpi=dpi, bbox_inches="tight", pad_inches=0.04)
    plt.close(fig)
    return {"svg": svg, "png": png}


# ============================================================
# Plot 1 — kinetic time course (single or multi condition)
# ============================================================

def plot_time_course(conditions: dict[str, dict], *,
                     xlabel: str = "Time (h)",
                     ylabel: str = "Concentration (mM)",
                     title: str | None = None,
                     legend_title: str | None = None,
                     figsize_cm: tuple = (8.5, 6.5),
                     preset: str = "recommended"):
    """conditions = { label: {"t": array, "y": array,
                              "yerr": array | None (SD/SEM),
                              "marker": "o" (optional),
                              "fit_t": array | None, "fit_y": array | None} }.
    """
    sp = apply_style(preset)
    markers = sp["marker_cycle"]
    fig, ax = plt.subplots(figsize=(figsize_cm[0]/2.54, figsize_cm[1]/2.54))

    for i, (lbl, d) in enumerate(conditions.items()):
        m = d.get("marker", markers[i % len(markers)])
        yerr = d.get("yerr")
        if yerr is not None:
            ax.errorbar(d["t"], d["y"], yerr=yerr, fmt=m,
                        markersize=plt.rcParams["lines.markersize"],
                        capsize=plt.rcParams["errorbar.capsize"],
                        elinewidth=sp["error_bar_style"]["elinewidth_pt"],
                        markeredgewidth=plt.rcParams["lines.markeredgewidth"],
                        label=lbl, zorder=5)
        else:
            ax.plot(d["t"], d["y"], marker=m,
                    markersize=plt.rcParams["lines.markersize"],
                    linestyle="none", label=lbl, zorder=5)
        if d.get("fit_t") is not None and d.get("fit_y") is not None:
            color = ax.lines[-1].get_color() if ax.lines else None
            ax.plot(d["fit_t"], d["fit_y"], linestyle="-",
                    color=color, zorder=3, label="_nolegend_")

    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    if title:
        ax.set_title(title)
    if len(conditions) > 1:
        leg = ax.legend(title=legend_title, loc="best")
        if leg and legend_title:
            leg.get_title().set_fontsize(plt.rcParams["legend.fontsize"])
    return fig


# ============================================================
# Plot 2 — HPLC chromatogram
# ============================================================

def plot_hplc(time_min, signal, peaks: list[dict] | None = None, *,
              xlabel: str = "Retention time (min)",
              ylabel: str = "Absorbance (mAU)",
              title: str | None = None,
              figsize_cm: tuple = (10.0, 5.0),
              preset: str = "sigmaplot",
              fill: bool = True):
    """peaks = [{"rt": 4.21, "name": "D-Rib", "color": "#0072B2"}, ...]
    """
    sp = apply_style(preset)
    fig, ax = plt.subplots(figsize=(figsize_cm[0]/2.54, figsize_cm[1]/2.54))
    ax.plot(time_min, signal, color="black",
            linewidth=plt.rcParams["lines.linewidth"], zorder=4)
    if fill:
        ax.fill_between(time_min, signal, 0, color="black", alpha=0.06, zorder=2)
    if peaks:
        for pk in peaks:
            rt = pk["rt"]
            # find closest signal at rt
            idx = int(np.argmin(np.abs(np.asarray(time_min) - rt)))
            y_pk = float(signal[idx])
            color = pk.get("color", "#D55E00")
            ax.annotate(pk["name"], xy=(rt, y_pk),
                        xytext=(rt, y_pk + max(signal) * 0.08),
                        ha="center",
                        fontsize=plt.rcParams["legend.fontsize"],
                        color=color,
                        arrowprops=dict(arrowstyle="-", color=color, lw=0.7))
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    if title:
        ax.set_title(title)
    ax.margins(x=0)
    ax.set_ylim(bottom=0)
    return fig


# ============================================================
# Plot 3 — dose-response (4-parameter logistic)
# ============================================================

def four_pl(x, bottom, top, ic50, hill):
    return bottom + (top - bottom) / (1.0 + (x / ic50) ** -hill)


def plot_dose_response(dose, response, *, response_err=None,
                       fit: dict | None = None,
                       ic50: float | None = None,
                       xlabel: str = "[Substrate] (mM)",
                       ylabel: str = "v / V$_{max}$",
                       title: str | None = None,
                       label: str | None = None,
                       figsize_cm: tuple = (8.0, 6.0),
                       preset: str = "prism",
                       logx: bool = True):
    """fit = {"bottom":, "top":, "ic50":, "hill":} → overlay 4PL curve."""
    sp = apply_style(preset)
    fig, ax = plt.subplots(figsize=(figsize_cm[0]/2.54, figsize_cm[1]/2.54))
    if response_err is not None:
        ax.errorbar(dose, response, yerr=response_err, fmt="o",
                    markersize=plt.rcParams["lines.markersize"],
                    capsize=plt.rcParams["errorbar.capsize"],
                    elinewidth=sp["error_bar_style"]["elinewidth_pt"],
                    label=label, zorder=5)
    else:
        ax.plot(dose, response, "o",
                markersize=plt.rcParams["lines.markersize"],
                label=label, zorder=5)
    if fit:
        xs = np.geomspace(min(dose)*0.5, max(dose)*2, 200) if logx else \
             np.linspace(min(dose), max(dose), 200)
        ys = four_pl(xs, fit["bottom"], fit["top"], fit["ic50"], fit["hill"])
        ax.plot(xs, ys, "-", linewidth=plt.rcParams["lines.linewidth"], zorder=4)
    if ic50 is not None:
        ax.axvline(ic50, linestyle="--", color="#7f7f7f", lw=0.8, zorder=2)
        ax.text(ic50, ax.get_ylim()[0], rf" IC$_{{50}}$ = {ic50:g}",
                fontsize=plt.rcParams["legend.fontsize"],
                color="#7f7f7f", va="bottom")
    if logx:
        ax.set_xscale("log")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    if title:
        ax.set_title(title)
    if label:
        ax.legend(loc="best")
    return fig


# ============================================================
# Plot 4 — pH-rate profile
# ============================================================

def plot_ph_rate(ph, rate, rate_err=None, *,
                 fit_curve=None,
                 xlabel: str = "pH",
                 ylabel: str = "Specific activity (U / mg)",
                 title: str | None = None,
                 figsize_cm: tuple = (8.0, 6.0),
                 preset: str = "prism"):
    sp = apply_style(preset)
    fig, ax = plt.subplots(figsize=(figsize_cm[0]/2.54, figsize_cm[1]/2.54))
    if rate_err is not None:
        ax.errorbar(ph, rate, yerr=rate_err, fmt="o",
                    markersize=plt.rcParams["lines.markersize"],
                    capsize=plt.rcParams["errorbar.capsize"], zorder=5)
    else:
        ax.plot(ph, rate, "o",
                markersize=plt.rcParams["lines.markersize"], zorder=5)
    if fit_curve is not None:
        ax.plot(fit_curve[0], fit_curve[1], "-",
                linewidth=plt.rcParams["lines.linewidth"], zorder=4)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    if title:
        ax.set_title(title)
    return fig


# ============================================================
# Plot 5 — BO / response surface contour
# ============================================================

def plot_bo_surface(X, Y, Z, *,
                    samples=None, best_xy=None,
                    xlabel: str = r"$x_1$", ylabel: str = r"$x_2$",
                    title: str | None = None,
                    figsize_cm: tuple = (8.5, 7.0),
                    preset: str = "recommended",
                    cmap: str = "viridis"):
    """X,Y,Z 2-D grids (np.meshgrid). samples = (xs, ys) for observed pts."""
    sp = apply_style(preset)
    fig, ax = plt.subplots(figsize=(figsize_cm[0]/2.54, figsize_cm[1]/2.54))
    cs = ax.contourf(X, Y, Z, levels=18, cmap=cmap, zorder=2)
    cline = ax.contour(X, Y, Z, levels=8, colors="white", alpha=0.4,
                       linewidths=0.5, zorder=3)
    cb = fig.colorbar(cs, ax=ax, fraction=0.045, pad=0.04)
    cb.outline.set_linewidth(plt.rcParams["axes.linewidth"])
    if samples is not None:
        ax.plot(samples[0], samples[1], "o",
                color="white", markeredgecolor="black",
                markersize=plt.rcParams["lines.markersize"],
                markeredgewidth=0.8, linestyle="none", zorder=5)
    if best_xy is not None:
        ax.plot(*best_xy, "*", color="#FFD700", markeredgecolor="black",
                markersize=plt.rcParams["lines.markersize"]*2.2,
                markeredgewidth=0.8, zorder=6)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    if title:
        ax.set_title(title)
    return fig


# ============================================================
# Plot 6 — bar with error + significance
# ============================================================

def plot_bar(values, errors=None, *, labels=None,
             significance: list[tuple] | None = None,
             ylabel: str = "Yield (%)",
             title: str | None = None,
             figsize_cm: tuple = (8.0, 6.0),
             preset: str = "prism"):
    """significance = [(i, j, stars), ...] e.g. [(0, 1, '*'), (0, 2, '***')].
    Brackets drawn above the bars."""
    sp = apply_style(preset)
    n = len(values)
    fig, ax = plt.subplots(figsize=(figsize_cm[0]/2.54, figsize_cm[1]/2.54))
    xs = np.arange(n)
    colors = (sp["color_cycle"] * ((n // len(sp["color_cycle"])) + 1))[:n]
    bars = ax.bar(xs, values, yerr=errors,
                  capsize=plt.rcParams["errorbar.capsize"],
                  color=colors, edgecolor="black",
                  linewidth=plt.rcParams["axes.linewidth"]*0.8, zorder=5)
    if labels is not None:
        ax.set_xticks(xs); ax.set_xticklabels(labels, rotation=0)
    ax.set_ylabel(ylabel)
    if title:
        ax.set_title(title)

    # Significance brackets
    if significance:
        y_top = max(v + (e if e else 0) for v, e in zip(values, errors or [0]*n))
        dy = y_top * 0.08
        for k, (i, j, mark) in enumerate(significance):
            y_lvl = y_top + dy * (k + 1) * 1.1
            ax.plot([i, i, j, j], [y_lvl - dy*0.25, y_lvl, y_lvl, y_lvl - dy*0.25],
                    "-", color="black", lw=1.0, zorder=6)
            ax.text((i + j) / 2, y_lvl + dy*0.05, mark,
                    ha="center", va="bottom",
                    fontsize=plt.rcParams["legend.fontsize"],
                    fontweight="bold", zorder=6)
        ax.set_ylim(top=y_top + dy*(len(significance)+1)*1.2)
    return fig


# ============================================================
# Plot 7 — Pareto front (MOBO)
# ============================================================

def plot_pareto(objs_dominated, objs_pareto, *,
                xlabel: str = "Yield (%)",
                ylabel: str = "Unit cost ($/kg)",
                title: str | None = None,
                invert_y: bool = True,
                figsize_cm: tuple = (8.5, 7.0),
                preset: str = "recommended"):
    """objs_dominated = (xs, ys) for dominated points
       objs_pareto    = (xs, ys) for the non-dominated front."""
    sp = apply_style(preset)
    fig, ax = plt.subplots(figsize=(figsize_cm[0]/2.54, figsize_cm[1]/2.54))
    ax.plot(objs_dominated[0], objs_dominated[1], "o",
            color="#bfbfbf", markersize=plt.rcParams["lines.markersize"]*0.8,
            markeredgecolor="none", linestyle="none",
            label="dominated", zorder=3)
    # sort pareto by x for the line
    pareto = sorted(zip(objs_pareto[0], objs_pareto[1]))
    px, py = zip(*pareto) if pareto else ([], [])
    ax.plot(px, py, "-o", color=sp["color_cycle"][1],
            markersize=plt.rcParams["lines.markersize"],
            linewidth=plt.rcParams["lines.linewidth"],
            label="Pareto front", zorder=5)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    if invert_y:
        ax.invert_yaxis()
    if title:
        ax.set_title(title)
    ax.legend(loc="best")
    return fig


# ============================================================
# Demo / CLI
# ============================================================

def _demo_all(out_dir: Path):
    """Generate one of each plot type with synthetic data — for visual QC of presets."""
    # 1. time course (substrate decay + product rise)
    rng = np.random.default_rng(0)
    t = np.linspace(0, 72, 13)
    gal = 200 * np.exp(-0.06 * t) + rng.normal(0, 3, t.size)
    tag = 200 * (1 - np.exp(-0.06 * t)) + rng.normal(0, 3, t.size)
    fit_t = np.linspace(0, 72, 200)
    tc_data = {
        "D-Galactose": {"t": t, "y": gal, "yerr": np.full_like(t, 4.0),
                        "fit_t": fit_t, "fit_y": 200 * np.exp(-0.06 * fit_t)},
        "D-Fructose":  {"t": t, "y": tag, "yerr": np.full_like(t, 4.0),
                        "fit_t": fit_t, "fit_y": 200 * (1 - np.exp(-0.06 * fit_t))},
    }
    for preset in ["recommended", "sigmaplot", "prism"]:
        fig = plot_time_course(tc_data,
                               xlabel="Time (h)", ylabel="Concentration (mM)",
                               title=f"Time course · {preset}",
                               preset=preset)
        _save(fig, out_dir, f"demo_time_course_{preset}")

    # 2. HPLC
    t_hplc = np.linspace(0, 12, 1200)
    sig = (60*np.exp(-((t_hplc-4.2)/0.10)**2)
           + 35*np.exp(-((t_hplc-7.6)/0.10)**2)
           + 22*np.exp(-((t_hplc-9.1)/0.13)**2)
           + rng.normal(0, 0.4, t_hplc.size))
    fig = plot_hplc(t_hplc, sig,
                    peaks=[{"rt":4.2,"name":"D-Rib","color":"#0072B2"},
                           {"rt":7.6,"name":"Ribitol","color":"#D55E00"},
                           {"rt":9.1,"name":"L-Arabinose","color":"#009E73"}],
                    title="HPLC chromatogram · sigmaplot",
                    preset="sigmaplot")
    _save(fig, out_dir, "demo_hplc_sigmaplot")

    # 3. Dose-response
    dose = np.array([0.01, 0.03, 0.1, 0.3, 1, 3, 10, 30, 100])
    response = four_pl(dose, bottom=0.05, top=1.0, ic50=2.0, hill=1.2) \
               + rng.normal(0, 0.03, dose.size)
    fig = plot_dose_response(dose, response,
                             response_err=np.full_like(dose, 0.04),
                             fit={"bottom":0.05,"top":1.0,"ic50":2.0,"hill":1.2},
                             ic50=2.0,
                             xlabel="[Inhibitor] (μM)",
                             ylabel="v / V$_{max}$",
                             title="Dose-response · prism",
                             preset="prism")
    _save(fig, out_dir, "demo_dose_response_prism")

    # 4. pH-rate
    ph = np.array([5.0, 5.5, 6.0, 6.5, 7.0, 7.4, 7.8, 8.5, 9.0])
    # bell curve centred ~7.0
    rate = 100 * np.exp(-((ph - 7.0)/1.1)**2) + rng.normal(0, 2.5, ph.size)
    fp = np.linspace(5, 9, 200)
    fr = 100 * np.exp(-((fp - 7.0)/1.1)**2)
    fig = plot_ph_rate(ph, rate, rate_err=np.full_like(ph, 3.0),
                       fit_curve=(fp, fr),
                       title="pH–rate · prism", preset="prism")
    _save(fig, out_dir, "demo_ph_rate_prism")

    # 5. BO surface
    x1 = np.linspace(0, 1, 60)
    x2 = np.linspace(0, 1, 60)
    X, Y = np.meshgrid(x1, x2)
    Z = -((X-0.65)**2 + (Y-0.40)**2) * 4 - 0.3*np.sin(6*X)*np.sin(6*Y)
    samples = (rng.uniform(0, 1, 18), rng.uniform(0, 1, 18))
    best_xy = (0.65, 0.40)
    fig = plot_bo_surface(X, Y, Z, samples=samples, best_xy=best_xy,
                          xlabel=r"$x_1$ (dimensionless)",
                          ylabel=r"$x_2$ (dimensionless)",
                          title="BO surface · recommended",
                          preset="recommended")
    _save(fig, out_dir, "demo_bo_surface_recommended")

    # 6. bar with error + significance
    vals = [62, 78, 89, 91]
    errs = [4, 3, 3, 2]
    labels = ["Control", "+ NoxV", "+ FdhV9", "Both"]
    fig = plot_bar(vals, errors=errs, labels=labels,
                   significance=[(0,1,"*"),(0,2,"**"),(0,3,"***")],
                   ylabel="Conversion (%)",
                   title="Bar + significance · prism", preset="prism")
    _save(fig, out_dir, "demo_bar_prism")

    # 7. Pareto
    rng2 = np.random.default_rng(1)
    n = 80
    yld = rng2.uniform(40, 95, n)
    unit_cost = 200 - 1.4*yld + rng2.normal(0, 12, n)
    # build pareto front (max yld, min unit_cost)
    points = sorted(zip(yld, unit_cost), key=lambda p: -p[0])
    pareto = []
    best_y = np.inf
    for x, y in points:
        if y < best_y:
            pareto.append((x, y))
            best_y = y
    px, py = zip(*pareto)
    dx, dy = zip(*[(x, y) for x, y in zip(yld, unit_cost) if (x, y) not in pareto])
    fig = plot_pareto((dx, dy), (px, py),
                      xlabel="Yield (%)", ylabel="Unit cost ($/kg)",
                      title="Pareto front · recommended",
                      preset="recommended")
    _save(fig, out_dir, "demo_pareto_recommended")

    return list(out_dir.glob("demo_*.png"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true",
                    help="render demo gallery of all 7 plot types")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    if args.demo:
        imgs = _demo_all(args.out)
        for p in imgs:
            print(p)
        return 0
    ap.error("nothing to do — pass --demo for a gallery")


if __name__ == "__main__":
    sys.exit(main())
