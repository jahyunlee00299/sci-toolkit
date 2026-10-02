# Lab recipes — uncertainty and units

Worked cases that go one level deeper than `SKILL.md`. Every number below was
produced by the bundled scripts (run `--help` for options); re-run them rather
than copying a value.

## 1. Where does the uncertainty of a stock solution come from?

0.1000 M glucose: weigh 1.8016 g, dissolve to 100 mL in a volumetric flask.
Model: `c = m / (MW * V)`. Balance tolerance +/-0.5 mg and flask tolerance
+/-0.14 mL are Type B limits, so they are rectangular (divide the half-width by
sqrt(3): 0.0005/sqrt(3) = 0.00029 g; 0.00014/sqrt(3) = 0.00008 L).

```bash
python skills/uncertainty-and-units/scripts/propagate_uncertainty.py \
  --expression "m / (MW * V)" \
  --variable "m=1.8016,0.00029,rectangular" \
  --variable "MW=180.156,0,exact" \
  --variable "V=0.100,0.00008,rectangular" \
  --measurand c --unit "mol/L" --format markdown
# c = 0.100002 mol/L, u_c = 8.2e-05 mol/L (0.08 %); the flask carries 96 % of the variance
```

Reading the budget, not the total, is the point: a better balance would change
nothing here, a better flask would. (`--unit` is a label; m in g, V in L, MW in
g/mol keep the model consistent.)

## 2. Type B divisors (certificate and data-sheet statements)

| The sheet says | Distribution | Divide by |
|---|---|---|
| "expanded uncertainty U, k = 2" | expanded | k (here 2) |
| "tolerance ±a" (flask, pipette, balance), no more info | rectangular | sqrt(3) |
| "±a, values near the centre are likelier" | triangular | sqrt(6) |
| temperature cycling between limits ±a | arcsine | sqrt(2) |

`uncertainty_budget.py --template` writes a JSON starter with these
distributions; it assumes independent components.

## 3. SD, SEM and 95% CI from n = 3

```python
import numpy as np
from scipy import stats
x = np.array([4.1, 4.4, 4.0])            # three independent preparations
sd  = x.std(ddof=1)                      # ddof=1: sample SD (np.std defaults to 0)
sem = sd / np.sqrt(len(x))
ci  = stats.t.ppf(0.975, len(x) - 1) * sem   # t = 4.30 for df = 2
```

`np.std` without `ddof=1` underestimates the SD at small n; `audit_units.py`
flags it (rule UNC002).

## 4. When linear propagation is not enough

Squared, reciprocal, bounded (concentration >= 0) or rectangular-dominated
outputs can have an interval the linear formula gets wrong. `propagate_uncertainty.py`
prints both the GUM interval and a Monte Carlo interval and a DISAGREE/AGREE
verdict (a fixed-trial diagnostic, not a full JCGM 101 validation). On a DISAGREE
report the Monte Carlo interval, and say which method you used.

## 5. Plausibility after the arithmetic

`check_plausibility.py --list` shows the dimensionless groups, scales and
typical-value bands. A unit-consistent answer can still be impossible (a
cytoplasmic diffusion time of years, a cell 2 m across); the dimensionality
check refuses a dynamic viscosity entered as a kinematic one. Bands are
screening heuristics, not physical laws; a hit is a reason to look again, and
the judgement of whether a fitted parameter is physical stays with
`scientific-validation`.
