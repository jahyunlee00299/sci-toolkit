---
name: uncertainty-and-units
description: Carry units and uncertainty through a lab calculation and report the result honestly — pint unit conversion (mM/µM, mg/mL via molecular weight), error propagation with correlated inputs (kcat/Km ± from a curve_fit covariance, HPLC calibration slope/intercept → sample concentration), rounding and "±" wording (SD vs SEM vs 95% CI) for tables and figure captions, and an order-of-magnitude plausibility check. Use before any number that carries a "±" or a unit conversion goes into a table, figure, report or manuscript. Whether the fit itself is physically sensible → scientific-validation; which statistical test to run → stats-workflow. 한국어 트리거 — 오차 전파, 불확도, ± 표기, 단위 변환, mM µM 변환, 유효숫자, 표준편차 표준오차 신뢰구간 뭐 써, 검량선 농도 계산, kcat/Km 오차.
license: MIT
compatibility: Python 3.12+ (pint 0.26 requires it). Numeric CLIs need pint, uncertainties, numpy and scipy; audit_units.py is standard-library only. Everything runs locally, no network.
allowed-tools: Read Write Edit Bash
metadata:
  skill-author: sci-toolkit (adapted from K-Dense-AI/scientific-agent-skills, MIT, Copyright (c) 2025 K-Dense Inc.)
  upstream: https://github.com/K-Dense-AI/scientific-agent-skills — skills/uncertainty-and-units
---

# Uncertainty and Units

A fitted `kcat/Km` or an HPLC concentration is only half a result until the
reader knows how far to trust it and in which unit it is expressed. Most
reporting errors here run without any error message: a unit stripped at the
wrong scale, a covariance matrix that was rescaled, two fit parameters that
were treated as independent. This skill is the checklist and the offline
tools that catch those.

## When to use this skill

- A number is about to get a `±` (fit parameter, derived yield, titer, E-factor)
- A unit conversion is needed, especially mM / µM / mg·mL⁻¹ through a molecular weight
- A calibration curve turns a peak area into a concentration
- A caption must say what the error bars are (SD, SEM or 95% CI)
- Existing analysis code strips units or drops correlations (`audit_units.py`)

It does **not** pick the statistical test (`stats-workflow`), judge whether a
fit is physically sensible (`scientific-validation`), or decide the replicate
number (`doe-and-replication`).

## Setup (Python 3.12+)

```bash
pip install pint uncertainties numpy scipy
```

Missing packages are not an install failure: `python doctor.py` reports them
as a WARN and the rest of the toolkit keeps working. Any Python older than
3.12 cannot install the current pint, so use the toolkit's 3.12+ interpreter.

## Six rules

1. **Units in at the boundary, stripped out once.** `(12.7 * ureg.mm).m_as("m")`
   names the unit; a bare `.magnitude` hides it.
2. **Write the model before computing.** `kcat = Vmax / [E]`, then
   `kcat/Km`. A term left out of the model is left out of the uncertainty.
3. **Keep the correlation.** Parameters from one fit are correlated; rebuild
   them with `correlated_values(popt, pcov)`, never with `ufloat(value, sd)`
   pairs (that makes them independent).
4. **`absolute_sigma=True` when `sigma` holds real standard uncertainties.**
   Otherwise `curve_fit` silently rescales `pcov` by the reduced chi-square
   (31% different on a test line). With no `sigma` at all the default scaling is
   the right one.
5. **Round the uncertainty first, then the value to the same decimal place.**
6. **Say what the `±` is** (table below) every time it appears.

## Recipe 1 — kcat/Km ± from a Michaelis-Menten fit

Each point is the mean of n = 3 independent measurements, so `sigma` is the
SEM of each mean; the enzyme concentration has its own uncertainty.

```python
import numpy as np
from scipy.optimize import curve_fit
from uncertainties import ufloat, correlated_values

S      = np.array([0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0])         # mM
v_mean = np.array([0.82, 1.45, 2.95, 4.40, 5.80, 7.05, 7.55])   # uM/min
v_sem  = np.array([0.06, 0.08, 0.12, 0.15, 0.20, 0.25, 0.30])   # uM/min
E_tot  = ufloat(0.050, 0.002)                                   # uM, from the A280 assay

def mm(S, vmax, km):
    return vmax * S / (km + S)

popt, pcov = curve_fit(mm, S, v_mean, p0=[8, 1], sigma=v_sem, absolute_sigma=True)
vmax, km = correlated_values(popt, pcov)
kcat = vmax / E_tot        # 1/min
eff  = kcat / km           # 1/(min*mM)
print(f"{eff:.2uS}")       # 181(10)
```

On this data `Vmax` and `Km` are 0.84 correlated; dropping that and treating
them as independent gives `181 ± 14` instead of `181 ± 10` — a 40% error in the
error bar from one skipped line. Quote the result as
`kcat/Km = 181 ± 10 min⁻¹ mM⁻¹ (± 1 standard error from the fit covariance)`
and keep the unit conversion (min⁻¹ → s⁻¹, mM → µM) for the very end with
`convert_units.py` or pint.

The same numbers from the command line, first-order, no fit needed:

```bash
python skills/uncertainty-and-units/scripts/propagate_uncertainty.py \
  --expression "kcat / Km" --variable "kcat=10,0.5" --variable "Km=2,0.1" \
  --measurand kcat_over_Km --unit "1/(mM*s)" --format markdown
# kcat/Km = 5.0, u_c = 0.354; both inputs 5% -> the budget splits 50/50
```

Add `--correlation "kcat,Km=0.84"` when the two come from one fit.

## Recipe 2 — HPLC calibration → sample concentration

Slope and intercept of one calibration line are correlated; the sample's peak
area has its own uncertainty.

```python
import numpy as np
from scipy.optimize import curve_fit
from uncertainties import ufloat, correlated_values

std  = np.array([0.5, 1, 2, 5, 10, 20])                    # mM glucose standards
area = np.array([12.1, 24.5, 47.9, 121.0, 243.5, 480.2])   # mAU*s

popt, pcov = curve_fit(lambda c, m, b: m * c + b, std, area)   # no sigma -> default scaling
m, b = correlated_values(popt, pcov)
A_sample = ufloat(100.3, 1.2)       # mean +/- SEM of 3 independently prepared samples
conc = (A_sample - b) / m * 10      # x10 dilution -> 41.5 +/- 0.6 mM
```

Three injections of **one** vial are technical replicates: their scatter
measures the instrument, not the preparation, and must not stand in for the
SEM of independent preps (see `doe-and-replication`). A sample area outside the
standards' range is an extrapolation; say so instead of reporting it.

## What the "±" means — pick one and write it in the caption

| You report | Meaning | Caption wording |
|---|---|---|
| **SD** | spread of the individual measurements | "mean ± SD, n = 3 independent preparations" |
| **SEM** = SD/√n | precision of the mean, shrinks with n | "mean ± SEM, n = 3 independent preparations" |
| **95% CI** = mean ± t·SEM | range that covers the true mean in 95% of repeats | "mean with 95% CI (t, df = 2)" |
| **fit standard error** | one s.e. from `sqrt(diag(pcov))` | "± 1 s.e. of the nonlinear fit" |

For n = 3 the 95% CI half-width is 4.30 × SEM = 2.48 × SD, so a CI and an SEM
bar are far apart: never swap one for the other without relabelling. Always
state **n and what n counts** (independent preparations, not wells or
injections). Notation conventions (`mean ± SD`, italic *n*, symbols) live in
`academic-term-rules`; error-bar drawing lives in `publication-figures`.
Wording helper: `format_result.py` prints the rounded value, the `12.346(23)`
form and the sentence that has to accompany it.

## Bundled CLIs (offline, no network)

| Script | Use it for |
|---|---|
| `propagate_uncertainty.py` | model → value, u_c, sensitivity coefficients, budget %, GUM vs Monte Carlo endpoints |
| `uncertainty_budget.py` | combine certificate / data-sheet components (pipette tolerance, balance, stock purity); `--template` writes a starter |
| `format_result.py` | round the uncertainty first, then the value; units and coverage sentence |
| `convert_units.py` | pint conversion with contexts, e.g. g → mol needs `--context chemistry --context-parameter "mw=180.156 g/mol"` |
| `check_plausibility.py` | order-of-magnitude check against dimensionless groups, scales and typical-value bands (`--list`) |
| `audit_units.py` | static review of your own script for stripped units, `curve_fit` without `absolute_sigma`, `ufloat` rebuilds |

```bash
python skills/uncertainty-and-units/scripts/convert_units.py --value 1.0 --unit g --to mol \
  --context chemistry --context-parameter "mw=180.156 g/mol"      # 5.5507e-3 mol
python skills/uncertainty-and-units/scripts/convert_units.py --value 2.5 --unit mM --to uM   # 2500 uM
python skills/uncertainty-and-units/scripts/format_result.py --value 12.34567 --uncertainty 0.02345 --unit mM
```

`--help` on each lists the options. A malformed argument (for example
`--variable "kcat=abc"`) exits non-zero with a one-line error; a failing exit
code is information, not noise. In these CLIs `--unit` is only a report label:
convert the inputs to one consistent unit system first.

## Traps that run without an error

- **Offset temperatures**: `20 ± 0.5 °C` in Fahrenheit is `68 °F ± 0.9 Δ°F`.
  An uncertainty on a temperature is a difference (`delta_degC`).
- **Logarithmic units** (dB, pH as a mathematical mean): do not add or average
  in the log scale; convert to linear first. The average of pH values is not the
  pH of the mean concentration.
- **A linearised squared or bounded quantity**: for `y = x²`, `x = 1.0 ± 0.5`
  the linear 95% interval goes negative. When the model is strongly nonlinear
  or the output is bounded (concentration, rate), run the Monte Carlo branch of
  `propagate_uncertainty.py` and compare.
- **Constants from memory**: take them from `scipy.constants` and check their
  stated precision.

## Hand-offs

- Fit converged but is it physical, identifiable, mass-balanced → `scientific-validation`
- Test selection, p-values, power paragraph → `stats-workflow`
- Replicate level (technical vs biological), n, run order → `doe-and-replication`
- Notation, units style, captions → `academic-term-rules`, `publication-figures`
- Where the underlying raw numbers came from → `lab-record`

Depth for the rest (GUM Type A/B, Welch-Satterthwaite, coverage factors,
Monte Carlo procedure): `references/lab-recipes.md` (lab worked cases) and
the vendored script docstrings.

## Attribution

Adapted from the K-Dense `uncertainty-and-units` skill (MIT). The scripts are
vendored without logic changes; see `scripts/` headers, `NOTICE.md` and
`licenses/K-Dense-MIT.txt`.
