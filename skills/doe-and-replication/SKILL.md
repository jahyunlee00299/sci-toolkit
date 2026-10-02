---
name: doe-and-replication
description: Plan an experiment BEFORE running it — choose the design (blocked A-vs-B, fractional/Plackett-Burman screen, full factorial, central composite / Box-Behnken response surface), generate a seeded run table in real units (pH x temperature x NAD ratio), randomize run order and 96-well plate positions (edge effect, drift), and decide what counts as a replicate (technical vs biological vs independent preparation; n = 3 wells from one prep is pseudoreplication). Includes the sample-size essentials (smallest effect of interest first, sensitivity range, no post-hoc power, is n = 3 enough). Use before any run with two or more factors, a plate, or the question "how many replicates". Reaction-matrix / pipetting workbook → experiment-hub; the test and APA reporting → stats-workflow. 한국어 트리거 — 실험 설계, DoE, 반복수, 몇 번 반복, 플레이트 배치, 무작위화, 중심합성설계, 요인설계, 가짜 반복, n=3 충분한가.
license: MIT
compatibility: Python 3.12+. The DoE generator needs numpy, pandas and pydoe 1.5; the randomization helpers need numpy and pandas. Everything runs locally, no network.
allowed-tools: Read Write Edit Bash
metadata:
  skill-author: sci-toolkit (adapted from K-Dense-AI/scientific-agent-skills, MIT, Copyright (c) 2025 K-Dense Inc.)
  upstream: https://github.com/K-Dense-AI/scientific-agent-skills — skills/experimental-design (SESOI/power essentials folded in from skills/statistical-power)
---

# DoE and Replication

The design decides what the data can answer. A confounded plate or three wells
counted as n = 3 cannot be repaired in the analysis. This skill is the short
decision path before the first pipette, plus a generator that gives a seeded,
reproducible run table.

## When to use this skill

- Two or more factors (pH, temperature, NAD⁺ ratio, enzyme loading, substrate) change in one study
- A plate or HPLC sequence is being laid out (edge effect, drift, run order)
- Someone asks "how many replicates", "is n = 3 enough" or "which conditions do I run"
- A screen of 5+ factors needs trimming, or an optimum must be located

Not for: building the stock/final/volume pipetting workbook (`experiment-hub`
Mode 10), running the test (`stats-workflow`), or error bars and ± wording
(`uncertainty-and-units`).

## Setup (Python 3.12+)

```bash
pip install numpy pandas pydoe
```

pydoe is only needed for `doe_designs.py`; `randomization.py` needs just numpy
and pandas. Missing packages show up as a WARN in `python doctor.py`, not as an
install failure. Python older than 3.12 is not supported by the pinned pydoe 1.5.

## Step 1 — What is the unit, and what is a real replicate?

Write down what is randomized and what the reader will call "n".

| Level | Example | Counts as n? |
|---|---|---|
| **Technical** | 3 wells from one master mix; 3 injections of one HPLC vial | No — measures pipetting and instrument noise |
| **Biological / independent preparation** | 3 separate enzyme purifications or 3 separate cultures, each prepared from scratch | Yes — this is the replicate for a claim about the enzyme or strain |
| **Independent run** | same prep, new day, fresh reagents | Intermediate: say exactly what was repeated |

**Pseudoreplication**: 3 wells from one prep, run once, is n = 1 (one prep),
however small the error bar looks. Report n as the number of independent
preparations and name it in the caption. If you can afford only technical
replicates, say so in the text and do not test a prep-level claim with them.

## Step 2 — Pick the design

```
Compare a few fixed conditions (A vs B vs C)?
  -> Randomized block: block = day / plate / batch, every treatment in every block.
Screen 5+ factors for the few that matter?
  -> Fractional factorial or Plackett-Burman (main effects only; know the aliasing).
2-4 factors and you need interactions?
  -> Full 2^k factorial (3 factors = 8 runs, 4 = 16).
Find the optimum, curvature matters?
  -> Central composite (CCD) or Box-Behnken; add center-point replicates.
Many continuous settings of a simulation?
  -> Latin hypercube.
```

Order of work: screen (PB / fractional) -> factorial on the survivors -> CCD
around the best region. Do not start with a CCD on eight factors.

## Step 3 — Generate the run table (seeded, real units)

```python
import sys; sys.path.insert(0, "skills/doe-and-replication/scripts")
from doe_designs import central_composite

factors = {"pH": (6.0, 8.0), "temp_C": (30, 50), "NAD_ratio": (0.5, 2.0)}
SEED = 261002                                   # write it into the lab-record EXP
design = central_composite(factors, center=(4, 2), face="inscribed", seed=SEED)
design.to_csv("ccd_runs.csv", index=False)      # 20 runs, run_order already randomized
```

Other generators in `doe_designs.py`: `two_level_factorial`, `full_factorial`
(categorical levels too), `fractional_factorial`, `plackett_burman`,
`box_behnken`, `latin_hypercube`.

**CCD cautions.** The default `face="circumscribed"` puts axial points
**outside** your (low, high) box, which can mean pH 9 on an enzyme that denatures
there. If the ranges are real limits use `face="inscribed"` (as above: the
factorial corners move inside, to about 6.4 / 7.6 for pH) or `"faced"`, then check
the min and max of every column. Do not clip rows afterwards, that changes the
design geometry. `center=(4, 2)` gives 6 center runs, whose spread is your pure
error; the wrapper default has only one. If the pH meter or the bath cannot set
the exact value, round to what you can set and record the **actual** settings,
then fit on those.

## Step 4 — Randomize run order and plate positions

Run order randomized against time (reagent aging, warm-up drift) is already in
the table. For a 96-well plate keep the edge wells (rows A/H, columns 1/12) out
of the assay or fill them with buffer, because they evaporate and sit in a
thermal gradient; then scatter the conditions over the 60 inner wells:

```python
import numpy as np
inner = [f"{r}{c}" for r in "BCDEFG" for c in range(2, 12)]            # 60 wells
reps = 3
layout = design.loc[design.index.repeat(reps)].reset_index(drop=True)  # 20 runs x 3 = 60
layout["rep"] = np.tile(np.arange(1, reps + 1), len(design))
layout["well"] = np.random.default_rng(SEED).permutation(inner)
layout.to_csv("plate_layout.csv", index=False)
```

Never put all controls in one column or all of one condition in one row. These
three wells per condition are positional (technical) replicates; the
prep-level n still needs independent preparations (Step 1). If the design must
run over several days, keep a `block` column and randomize only **within** a
block: the wrappers shuffle globally.

A simple A-vs-B comparison with balanced blocks:

```python
from randomization import block_randomization, arm_balance
sched = block_randomization(n=12, arms=["A", "B"], seed=7)
print(arm_balance(sched))                      # 6 and 6
```

`stratified_block_randomization` balances within strata (for example the
enzyme batch); `assign_factorial_runs` shuffles any existing run table.
`cluster_randomization` also ships in the file but is not part of the lab
workflow.

Record the seed, the pydoe version (`python -c "import pydoe; print(pydoe.__version__)"`)
and the exported CSV in the `lab-record` EXP, because a seed alone does not
promise identical output after a package upgrade.

## Step 5 — How many replicates? (power essentials)

1. **Smallest effect of interest first.** Ask what difference would change a
   decision (for example a 20% higher activity) and express it in units of the
   assay's SD. Do not back-solve the effect from the n you can afford.
2. **Use a pilot's SD with care**: three points give a very rough SD. Show a
   sensitivity range, not one number.
3. **No post-hoc power.** Power computed from the effect you just measured
   restates the p-value; it adds no evidence.

```python
from statsmodels.stats.power import TTestIndPower
tp = TTestIndPower()
tp.solve_power(effect_size=0.5, alpha=0.05, power=0.80)   # 64 per group
tp.solve_power(effect_size=2.0, alpha=0.05, power=0.80)   # 5.1 -> 6 per group
tp.solve_power(nobs1=3, alpha=0.05, power=0.80)           # 3.07 = detectable d with n = 3
```

Answer to "is n = 3 enough": with 3 independent preparations per group a
two-group t-test at 80% power only detects a difference of about 3 SD. That is
fine for a 10-fold activity change with a tight assay and not enough for a 20%
effect. Inflate for unusable samples: `n_enroll = ceil(n / (1 - loss))`.
Statistical test choice and APA reporting stay in `stats-workflow`.

## Mistakes that cannot be fixed afterwards

1. **Pseudoreplication** (Step 1).
2. **Confounding by day or plate**: all treatment on Monday, all control on Tuesday.
3. **No randomization**: first tube = treatment.
4. **No concurrent control** (no-enzyme, no-substrate, vehicle) in the same run.
5. **Edge or position effects** ignored (Step 4).
6. **Aliasing ignored**: a low-resolution fraction confounds main effects with
   interactions, so "no effect" may be two effects cancelling.
7. **Optimising without curvature**: a two-level factorial cannot see an
   interior optimum.

## Hand-offs

- Run table -> pipetting workbook: `experiment-hub` (`reaction_matrix.py`; its DoE mode defers here)
- Record the design, seed and what a replicate is: `lab-record` (EXP)
- Test selection, assumptions, APA reporting: `stats-workflow` (and `statsmodels` for blocks and nested terms)
- Error bars and ± wording: `uncertainty-and-units`; raw table sanity: `data-quality-checks`
- Is the fitted surface physical: `scientific-validation`
- Plots with significance marks: `publication-figures`

Depth: `references/design-notes.md` (resolution and aliasing, CCD variants,
blocking in a plate-reader run).

## Attribution

Adapted from the K-Dense experimental-design skill and the sample-size
principles of its statistical-power skill (both MIT). The clinical designs
(cluster, crossover, group-sequential, adaptive) were dropped. Scripts are
vendored without logic changes; see `scripts/` headers, `NOTICE.md` and
`licenses/K-Dense-MIT.txt`.
