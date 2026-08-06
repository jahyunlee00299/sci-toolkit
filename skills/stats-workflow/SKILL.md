---
name: stats-workflow
description: Three-phase statistical workflow — seaborn quick exploration → guided test selection with assumption checks → APA 7th formatted reporting with effect sizes and power analysis. Use when you need test selection guidance, assumption checking, or formatted results. For implementing specific parametric models (OLS, GLM, ARIMA) with full diagnostics use statsmodels; for Bayesian/MCMC modeling use pymc.
---

# Stats Workflow — Meta-Skill

Integrates: `seaborn` + `statistical-analysis`

## Trigger

Use when:
- Choosing the right statistical test for your data
- Checking assumptions before running a test
- Reporting results in APA 7th format
- Visualizing distributions, relationships, or group comparisons

## Three-Phase Workflow

```
Phase 1: Explore (seaborn)
      ↓
Phase 2: Test Selection + Assumption Checks
      ↓
Phase 3: APA Reporting + Effect Size
```

---

## Phase 1 — Quick Exploration (Seaborn)

```python
import seaborn as sns
import matplotlib.pyplot as plt

# Distribution
sns.histplot(data, kde=True)

# Group comparison
sns.boxplot(x='group', y='value', data=df)
sns.stripplot(x='group', y='value', data=df, alpha=0.5, jitter=True)

# Correlation
sns.heatmap(df.corr(), annot=True, cmap='coolwarm', center=0)

# Pairplot
sns.pairplot(df, hue='group')
```

---

## Phase 2 — Test Selection

### Decision Tree

```
How many groups?
├── 1 group
│   └── Compare to known value → One-sample t-test
├── 2 groups
│   ├── Paired → Paired t-test / Wilcoxon signed-rank
│   └── Independent
│       ├── Normal + equal variance → Independent t-test
│       ├── Normal + unequal variance → Welch's t-test
│       └── Non-normal → Mann-Whitney U
└── 3+ groups
    ├── One factor → One-way ANOVA / Kruskal-Wallis
    ├── Two factors → Two-way ANOVA
    └── Repeated measures → rmANOVA / Friedman
```

### Assumption Checks

```python
# Normality
from scipy import stats
stat, p = stats.shapiro(data)  # n < 50
stat, p = stats.normaltest(data)  # n >= 50

# Equal variance
stat, p = stats.levene(*groups)

# Post-hoc (after ANOVA)
from statsmodels.stats.multicomp import pairwise_tukeyhsd
result = pairwise_tukeyhsd(data, groups)
```

---

## Phase 3 — APA 7th Reporting

### Format Templates

**t-test:**
```
t(df) = X.XX, p = .XXX, d = X.XX [95% CI: X.XX, X.XX]
```

**ANOVA:**
```
F(df_between, df_within) = X.XX, p = .XXX, η² = .XX
```

**Correlation:**
```
r(df) = .XX, p = .XXX
```

### Effect Size Reference

| Test | Small | Medium | Large |
|---|---|---|---|
| Cohen's d (t-test) | 0.2 | 0.5 | 0.8 |
| η² (ANOVA) | 0.01 | 0.06 | 0.14 |
| r (correlation) | 0.1 | 0.3 | 0.5 |

### Power Analysis

```python
from statsmodels.stats.power import TTestIndPower
analysis = TTestIndPower()
n = analysis.solve_power(effect_size=0.5, alpha=0.05, power=0.8)
print(f"Required n per group: {n:.0f}")
```

---

## Common Pitfalls

- ❌ Running t-test without checking normality (n < 30)
- ❌ Multiple comparisons without correction (use Bonferroni or FDR)
- ❌ Reporting only p-value without effect size
- ❌ Treating ordinal data as continuous
- ✅ Always report exact p-values (not "p < 0.05")
- ✅ Include confidence intervals

---

## Replaces

- `deprecated/seaborn` — statistical visualization and quick exploration
- `deprecated/statistical-analysis` — test selection, assumption checking, APA reporting
