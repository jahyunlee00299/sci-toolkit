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

After the EDA: a mean ± SD/SEM, a fitted parameter's `±`, or a calibration-curve concentration → `uncertainty-and-units` (units, propagation, caption wording). Before the next run, replicate level and plate layout → `doe-and-replication`.

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

🔴 **Vial number and sample name are two different identifiers — never conflate them (Agilent
ChemStation).** A real failure cost a whole analysis pass: the assistant read only vial numbers,
concluded "there are no sample names, so no time course is possible", and was corrected by the
researcher, who had written the numbers into the sample-name field only.

| | where it lives | what it means |
|---|---|---|
| **vial** | the 3-digit PREFIX of the data folder (`043-1801.D` -> vial 43), and the ONLY id the sequence `.LOG` reports (`Instrument running sample Vial 43`) | tray position, nothing else |
| injection index | the 4-digit part (`043-**1801**.D` -> injection 18) | order within the sequence |
| **sample name** | the `.ch` header field `notebook`: `rainbow.agilent.chemstation.parse_ch(path).metadata['notebook']` | what the researcher wrote on the tube |

- The sequence `.S` is a register file and carries **no** sample names. The `.LOG` gives vial numbers
  and the analyzed `.D` name, never the sample name. So neither file can identify a sample on its own.
- **A vial is reused.** Measured in one sequence: vial 1 held sample `1` at 12:59 and sample
  `90` at 04:35 the next morning; same for vials 7 and 16. Keying a time course on vial silently
  merges two different samples. Carry `vial` and `sample_name` as separate columns and join on the name.
- **The sample name IS the key — so a repeated name is a DEFECT to fix, not a reason to stop
  keying on it.** This is the opposite of the vial above, and the two need opposite responses: a
  reused vial is by design (the tray gets refilled), a repeated sample name is a label error in one
  record. Measured in the same sequence: one name sat on two different tubes (a 12 h
  no-enzyme control and a 24 h reacting tube), both injected. Assert the name is unique; when it is
  not, **flag the collision loudly, say which reading you assumed meanwhile, and send the question
  to the bench notes** — the chromatogram cannot tell you which of the two labels is the wrong one.
  A tie-break on the acquisition timestamp (a later timepoint cannot be injected before the earlier
  round is through) keeps the analysis moving; it is a stopgap, not a new key.
- The `.LOG` also lists `.D` folders that are **not on disk** (calibration standards written
  elsewhere, entries queued but not run). Skip a missing path; do not let it abort the parse.
- Read the acquisition timestamp (`metadata['date']`, `metadata['time']`) with every injection: it is
  the cheapest check that a decoded timepoint is physically possible. Measured once: an injection
  acquired at 05:27 could not hold a sample drawn at 11:00 the same day, which is what exposed a
  one-number gap in the researcher's numbering.

**Decoding a researcher's numbering scheme: anchor it on a control, do not assume the stride.**
A scheme like "19 tubes per round, rounds in timepoint order" looks arithmetic (`round = (n-1)//19`)
but a skipped number shifts every later round by one and the arithmetic form fails silently with no
error — it just assigns the wrong timepoint. Anchor each round on a sample whose chromatogram is
self-identifying (a no-enzyme control: substrate intact, products absent) and derive the round start
from it, then assert that every detected control lands on the control tube and no reacting trace does.
Measured once: the control signature placed the rounds at names 1/20/39/**59**/**78**/**96**, not
the assumed 1/20/39/58/77/96. **Then diff the anchored round starts to localize the slip**: every
gap should equal the round size, and the one gap that is +1 and the one that is −1 BRACKET the
mislabeled block. Here the gaps ran 19, 19, **20**, 19, **18** — so the 8 h round was written one
high, carried the slip through 12 h, and the 24 h round landed back on the planned number and
collided with the 12 h control. That names the tubes the bench has to check, instead of reporting
"the numbering is odd"; it also beats the alternative of two independent slips, since one error
explains both the wide gap and the collision. Re-anchor every new round as it arrives, never
extrapolate the stride forward, and keep the control gate on — it caught a genuine control anomaly
instead of hiding it, and later caught the collision by placing a control on a reacting tube.

- Plot absorbance vs. retention time
- Peak detection (prominence-based)
- Area integration and relative quantification
- Deconvolution for overlapping peaks (Gaussian fit)
- 


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
