# Publication Figures — recurring patterns

A multi-panel manuscript figure rebuild (5 main + 12 SI) surfaced the patterns below repeatedly.
Reference script location (example): `<your library path>/<paper>/submissions/<Journal>/figures/`

---

## Pattern 1: Put the errorbar cap on top of the marker

**When to use:** when datapoints are dense or the marker is large enough that the cap gets hidden.

Separate `plot()` and `errorbar(fmt="none")`, and raise the errorbar to a higher zorder.
Prefer `"#222222"` for ecolor instead of the species color (reads more clearly against a dense background).

```python
ax.plot(x, y, marker="o", color=color, zorder=3)
ax.errorbar(x, y, yerr=yerr, fmt="none",
            ecolor="#222222", capsize=4, capthick=1.1,
            elinewidth=1.1, zorder=5)
```

Reference example: `fig_S1_enzyme_activity/script.py`

---

## Pattern 2: 3D surface RSM colorbar position

**When to use:** when a 2-panel 3D surface subplot needs the colorbar sitting right against the z-axis.

```python
cb = fig.colorbar(surf, ax=ax, pad=0.10, shrink=0.55, aspect=18)
fig.subplots_adjust(wspace=-0.05)
```

Reference example: `fig_1_response_surface/script.py`

---

## Pattern 3: Sobol/bar chart errorbar cap style

**When to use:** when a sensitivity analysis (Sobol) or bar chart needs a clearly visible errorbar cap.

```python
ax.bar(x, height, yerr=err,
       capsize=4, error_kw=dict(capthick=1.1, elinewidth=1.1, ecolor="#222222"))
```

Reference example: `fig_2_sensitivity/script.py`

---

## Pattern 4: Avoiding scatter + text label collisions

**When to use:** to prevent overlap when attaching per-item text labels to a scatter plot.

Assign a `(dx, dy_factor, ha)` tuple in a `LABEL_OFFSET` dict. Spread across 4 directions
(upper-left/lower-left/upper-right/lower-right). fontsize 7.5–8.5 pt.

```python
LABEL_OFFSET = {
    "item_A": (-0.15,  0.04, "right"),
    "item_B": ( 0.10, -0.06, "left"),
    "item_C": ( 0.10,  0.04, "left"),
}
for name, (x, y) in data.items():
    dx, dy_f, ha = LABEL_OFFSET.get(name, (0.10, 0.04, "left"))
    ax.text(x + dx, y + dy_f * y_range, name, ha=ha, fontsize=8)
```

Reference example: `fig_S2_green_metrics/script.py`

---

## Pattern 5: Showing fit-line extrapolation

**When to use:** when a trend (e.g. thermal inactivation) needs to be shown across the entire xlim range.

Don't clip to each enzyme's own data range — draw across the full xlim instead. Match the y-range to
the reference via `set_ylim`.

```python
x_fit = np.linspace(*ax.get_xlim(), 200)
ax.plot(x_fit, model(x_fit, *popt), "-", color=color, lw=1.2, zorder=2)
ax.set_ylim(y_lo, y_hi)
```

Reference example: `fig_S3_stability/script.py`

---

## Pattern 6: EF metric unit notation

**When to use:** when writing E-factor or another mass-based green-metric unit.

Use the `g/g` slash form instead of `g g⁻¹` (superscript).
Apply the same form consistently across axis labels, colorbar labels, and legends.

```python
ax.set_ylabel("E-factor (g/g)")
cb.set_label("sEF (g/g)")
```

Reference: slash-unit convention (academic-term-rules §8).

---

## Pattern 7: Simplifying subplot titles

**When to use:** when a panel title duplicates what the caption already says, in a multi-panel figure.

Remove text like the enzyme/substrate name, leaving only the panel letter (a/b/c…).

```python
ax.set_title("a", fontsize=11, fontweight="bold", loc="left")
```

Put the detailed description in the caption instead. Reference examples: `fig_S4_residuals/script.py`, `fig_S5_obs_pred/script.py`
