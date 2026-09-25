---
name: lab-data-analysis
description: Unified lab data analysis skill combining chemical safety lookup (MSDS/GHS via PubChem) with lab-specific EDA for kinetic, HPLC, clustering, tabular, gel, and sensitivity data, plus general scientific data across 200+ file formats. Use for any data file produced in the lab. For statistical hypothesis testing or APA-formatted reporting use stats-workflow; for making publication figures from analyzed data use publication-figures. 한국어 트리거 — rawdata 분석, 엑셀·xlsx·csv 정리, HPLC 데이터, 측정값 추출, 반복 평균·표준편차, 데이터 전처리·병합.
---

# Lab Data Analysis — Meta-Skill

Integrates: `msds-lookup` + `exploratory-data-analysis` + `lab-eda`

## Trigger

Use when:
- Analyzing any scientific or lab data file
- Checking chemical safety before experimental work
- Performing EDA on kinetic, HPLC, or tabular data
- Summarizing data quality, distributions, or anomalies

## Routing

```
Input
 ├── Chemical name/CAS → [Safety Check] PubChem MSDS + GHS hazard
 ├── Kinetic time-series → [Lab EDA] progress curves, rate analysis
 ├── HPLC data → [Lab EDA] chromatogram, peak detection, deconvolution
 ├── Gel image / densitometry → [Lab EDA] band quantification
 ├── General tabular (CSV/Excel) → [General EDA] distributions, correlations
 └── Exotic format (HDF5, MAT, etc.) → [General EDA] 200+ format parser
```

---

## Safety Check (MSDS/GHS)

**Always run before handling a new chemical.**

1. Query PubChem REST API by name or CAS
2. Return:
   - GHS hazard pictograms and H-statements
   - Hazard level: 🔴 HIGH / 🟡 MODERATE / 🟢 LOW
   - PPE required
   - Storage and disposal notes

```python
# PubChem lookup
url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{name}/JSON"
```

---

## Lab-Specific EDA

### Kinetic Data
- Plot substrate vs. time progress curves
- Estimate initial rates (v₀) via linear regression on early time points
- Fit Michaelis-Menten if [S] series available (→ Km, Vmax, kcat)
- Flag: lag phases, product inhibition, incomplete reactions

### HPLC / Chromatography
- Plot absorbance vs. retention time
- Peak detection (prominence-based)
- Area integration and relative quantification
- Deconvolution for overlapping peaks (Gaussian fit)

Pick the tool by how far the analysis has to go:

| Need | Tool |
|---|---|
| Read a `.ch`/`.txt`/`.csv`/`.arw` trace, quick peak list, CSV/JSON out — no installs | `scripts/hplc_parser.py` (stdlib only) |
| Real quantification: baseline correction (ArPLS/spline), EMG/Gaussian deconvolution, calibration curves with LLOQ/ULOQ, sequence QC, batch runs over `.D` folders, Excel/plot export | **PeakPicker** — https://github.com/jahyunlee00299/hplc-peak-analyzer-PeakPicker |

PeakPicker setup: `git clone` the repo, `pip install -r requirements.txt`, run
`pytest` to confirm. It is generic on purpose — a lab's own sample-name
convention, quantification presets and method YAMLs are **plugins** kept
outside the public repo (`PEAKPICKER_PLUGIN_PATH`, or a gitignored
`plugins/` folder; method selection reads each YAML's `match:` block). See its
`docs/PLUGINS.md` before adding lab-specific code, and never commit real
calibration data or experiment names to the public repo.

### Gel / Western Blot
- Band intensity extraction
- Normalize to loading control
- Relative quantification table

### Tabular / General
- Shape, dtypes, missing values
- Distribution plots (histogram + KDE)
- Correlation heatmap
- Outlier detection (IQR or z-score)

---

## Output Format

Always deliver:
1. **Data summary** — shape, types, missing %
2. **Key findings** — top 3 observations in plain language
3. **Quality flags** — anomalies, suspicious values
4. **Visualization** — at minimum one diagnostic plot
5. **Next step suggestion** — recommend stats test or further analysis; if the
   analysis is being logged as part of a tracked experiment, route to `experiment-hub`
   (mode 6: pattern analysis / record-keeping) rather than ending the reply here

---

## Replaces

- `deprecated/msds-lookup` — chemical safety via PubChem
- `deprecated/exploratory-data-analysis` — 200+ format general EDA
- `deprecated/lab-eda` — kinetic, HPLC, gel, lab-specific EDA
