---
name: data-quality-checks
description: Structural integrity check on a raw or assembled data table BEFORE analysis — completeness, uniqueness, validity ranges, cross-column consistency, and freshness/provenance. Six named quality dimensions with a concrete check per dimension, expressed in pandas so no data-warehouse tooling is required. Use when a spreadsheet or instrument export first arrives, when merging replicates or runs into one table, or when a downstream result looks wrong and you need to rule out the input. For distributions and exploratory plots use lab-data-analysis; for whether a computed result is physically sensible use scientific-validation.
license: MIT
metadata:
  skill-author: sci-toolkit (adapted from wshobson/agents, MIT)
  upstream: https://github.com/wshobson/agents — plugins/data-engineering/skills/data-quality-frameworks
---

# Data Quality Checks

Most "the analysis is wrong" investigations end at the input table: a
duplicated replicate, a column silently read as text, a blank cell that
`mean()` skipped. This skill runs a structural pass over the table *before*
any analysis touches it, so a later surprise can be attributed to the method
rather than the data.

Upstream frames this around Great Expectations, dbt tests, and data contracts
between teams. Those assume a warehouse and a pipeline owner. The framing that
transfers is the **six quality dimensions** — that part is tool-independent,
and it is reproduced here in pandas.

## When to use this skill

- A spreadsheet or instrument export just arrived and has not been analyzed
- Replicates, runs, or batches are being merged into one table
- A downstream number looks wrong and you need to rule out the input first
- A table is about to become the raw-data SSOT for a reported number (§3)

This runs **before** `lab-data-analysis` (which describes the data) and long
before `scientific-validation` (which judges a result). It answers only:
*is this table structurally trustworthy enough to analyze?*

## The six dimensions

| Dimension | Question | Check |
|---|---|---|
| **Completeness** | Is anything missing? | Null counts per column; expected row count per group |
| **Uniqueness** | Is anything duplicated? | Duplicate keys; repeated (sample, timepoint) pairs |
| **Validity** | Are values in range? | Bounds, allowed category sets, dtype |
| **Consistency** | Do columns contradict? | Cross-column relations, sums, ordering |
| **Accuracy** | Does it match reality? | Cross-reference an independent record |
| **Freshness** | Is this the current file? | Provenance: path, mtime, version, who produced it |

Accuracy is the one no script can settle — it needs an external reference
(the lab notebook, the instrument log, a second measurement). Say so rather
than reporting the other five as if they covered it.

## Checks, per dimension

### Completeness

```python
missing = df.isna().sum()
print(missing[missing > 0])

# Missing rows are harder to see than missing cells: a group short of its
# expected replicate count looks complete until you count it.
counts = df.groupby(["sample", "timepoint"]).size()
short = counts[counts != EXPECTED_REPLICATES]
assert short.empty, f"incomplete groups:\n{short}"
```

A fully-absent row never shows up in `isna()`. Count by group.

### Uniqueness

```python
key = ["sample", "timepoint", "replicate"]
dupes = df[df.duplicated(subset=key, keep=False)].sort_values(key)
assert dupes.empty, f"duplicate keys:\n{dupes}"
```

Decide explicitly what a duplicate means: a re-injection to be averaged, or a
copy-paste error to be removed. Do not let `drop_duplicates()` make that call
silently.

### Validity

```python
assert df["concentration"].between(0, 100).all(), \
    df.loc[~df["concentration"].between(0, 100)]

allowed = {"WT", "M1", "M2"}
unexpected = set(df["variant"]) - allowed
assert not unexpected, f"unexpected categories: {unexpected}"

# The silent one: a numeric column read as object because a cell holds
# "n.d." or "<LOD" or a stray space. Everything downstream then does
# string concatenation instead of arithmetic.
assert pd.api.types.is_numeric_dtype(df["concentration"]), \
    df["concentration"].apply(type).value_counts()
```

### Consistency

```python
# Relations that must hold between columns
assert (df["product"] <= df["substrate_initial"]).all()

# A total column that stopped matching its parts after an edit
assert np.allclose(df["total"], df["a"] + df["b"] + df["c"], rtol=1e-6)

# Ordering that later code assumes
assert df.groupby("sample")["timepoint"].is_monotonic_increasing.all()
```

### Freshness / provenance

```python
from pathlib import Path
p = Path(path)
print(f"file:  {p.resolve()}")
print(f"bytes: {p.stat().st_size}")
print(f"rows:  {len(df)}  cols: {list(df.columns)}")
```

Record which file this was, not just that a file was read. Two exports of the
same run, one hour apart, are indistinguishable in the resulting numbers —
and §3 SSOT requires knowing which one produced the reported value. On a
cloud-synced folder (OneDrive, Dropbox, Drive), an mtime can lag the actual
content: confirm the file exists and check its size and row count rather than
trusting the timestamp.

## Reporting

Report **counts and the offending rows**, never a bare verdict. "3 duplicate
keys in `sample=M2`" is actionable; "quality check failed" is not.

```python
def quality_report(df, key, bounds):
    """Return (passed, lines). Prints what failed, with the rows."""
    lines, passed = [], True
    nulls = df.isna().sum()
    if (nulls > 0).any():
        passed = False
        lines.append(f"[completeness] nulls:\n{nulls[nulls > 0]}")
    dupes = df[df.duplicated(subset=key, keep=False)]
    if not dupes.empty:
        passed = False
        lines.append(f"[uniqueness] {len(dupes)} duplicate-key rows:\n{dupes}")
    for col, (lo, hi) in bounds.items():
        bad = df[~df[col].between(lo, hi)]
        if not bad.empty:
            passed = False
            lines.append(f"[validity] {col} outside [{lo}, {hi}]:\n{bad}")
    return passed, lines
```

## What to do with a failure

Do not silently repair. Each of these is a decision with a scientific
consequence, and it belongs in the record:

| Finding | Wrong move | Right move |
|---|---|---|
| Duplicate rows | `drop_duplicates()` | Determine which is real; note the choice |
| Nulls | `fillna(0)` | Distinguish "not measured" from "measured as zero" — they are not the same and 0 biases every mean |
| Out-of-range value | Clip to the bound | Check the raw trace; below-detection is a value with a meaning, an instrument fault is not |
| Short replicate group | Analyze anyway | Report the actual n; a mean of 2 labelled n=3 is a fabricated number |
| Wrong dtype | `astype(float)` | Find what the non-numeric cells hold first — they usually encode something |

## Gate

Before analyzing a table:

1. All six dimensions checked, or explicitly stated as not applicable
2. Every failure either resolved or recorded with the decision taken
3. Actual n reported per group — not the intended n
4. File path and row/column count recorded alongside the result (§3 SSOT)
5. Accuracy stated honestly: cross-referenced against what, or not checked

Focus the effort on the columns that reach a reported number. Checking every
column of a 200-column export equally is how a quality pass becomes a ritual
nobody reads.
