---
name: scientific-validation
description: |
  Scientific validity gate for any experimental fit / model calibration / optimization result
  BEFORE it is reported, written into a manuscript, merged into params files, or used downstream.
  This is the "does this actually make scientific sense" check that sits AFTER a fit converges
  and BEFORE the number is trusted. Complements (does not replace) kinetic-bo-pipeline (which
  runs the fit) and verify_reminder/verify_gate_stop hooks (which nudge generic verification).

  Use this skill when:
  - A fit / regression / ODE calibration just produced parameters (kcat, Km, alpha, kLa, ...) or a curve
  - A Bayesian optimization / NSGA / Pareto run produced an optimum to be reported
  - A model number (the cost metric, titer, yield, E-factor, ΔG) is about to go into a manuscript / report / docx
  - Raw experimental data is being extracted / stored / version-controlled, or a mass balance must
    close (measured total = product + byproducts + residual substrate vs t0) — run the
    Axis 0 raw-integrity + Axis 3 mass-balance checks
  - The user says: "이 fitting 맞아?", "결과 검증", "이거 말이 돼?", "타당한지 봐줘",
    "validate fit", "sanity check", "physical plausibility", "scientific validation",
    "mass balance", "질량 보존", "raw 저장", "raw 버전관리", "컬럼 확정",
    "/scientific-validation", "/sci-validate"
  - You delegated a fit to a remote/home machine and got numbers back (remote/delegated numbers are PROVISIONAL until
    this gate + an independent 1-line reproduction agree)

  Do NOT use for: running the fit itself (kinetic-bo-pipeline), generic code review (code-review),
  manuscript reference auditing (manuscript-pipeline).
license: MIT license
metadata:
    skill-author: generic
---

# Scientific Validation Gate

A converged fit is **not** a correct fit. High R², optimizer "SUCCESS", and "all checks PASS"
self-reports have all shipped wrong science (a single-basis number that drifted across re-runs; a
filled-in figure that failed arithmetic verification). This skill is the adversarial gate that runs
between "the number exists" and "the number is trusted."

**Core stance — be the skeptic.** Default to "this is wrong until each axis passes." A number that
contradicts physics, units, or a 1-line reproduction is rejected even if every other check is green
(a single contradiction invalidates a blanket PASS).

## When this fires

1. **After any fit/calibration/optimization completes** — before reporting or merging params.
2. **Before a model number enters a manuscript / docx / a tracker.**
3. **On delegated/remote numbers** — they stay PROVISIONAL until this gate AND an independent reproduction agree.

## The axes (run all; report each PASS/FAIL/CAUTION with evidence)

### Axis 0 — Raw-data integrity (provenance · version control · column map)
A number is only as trustworthy as the bytes it came from. Before anything else, the RAW must be
**committed, hash-pinned, and column-documented** (a generalized provenance pattern).

- **Version control.** The raw file must be tracked by git in the project repo — not floating in
  Downloads / `chat downloads` / a one-off path. Run `scripts/check_raw.py <file>` or
  `check_raw.py --dir <data_dir>`: it flags untracked raw (FAIL), uncommitted working-copy drift
  (CAUTION), and records the sha256 to log alongside the result for attribution.
- **Column map by HEADER LABEL, never by position.** Position-based column reads have silently
  corrupted real results (e.g. a byproduct column read as the product column). When extracting, confirm each
  species/quantity by its header label and 2-row-header structure, and write the resulting
  `label → column → meaning + unit` map into the extraction output and a sibling README.
  `check_raw.py` warns if no sibling doc carries a column-map signal.
- **Provenance note.** Source (instrument / who sent it / original filename), date, and any
  rename/dedup must be in the data dir's README so the chain is auditable later.
- **Versioning the result, not just the raw.** When the fit is re-run on new raw or new params,
  bump a version (v4a→v4b…) and keep the old one — never overwrite a reported number in place.

## The four scientific axes

### Axis 1 — Physical plausibility + identifiability
Every fitted parameter must (a) land inside its physical range, (b) NOT sit on a search bound, and
(c) be actually identifiable from the data.

- **Physical range.** Each parameter has a known plausible window. Out-of-window = unit error or wrong mechanism.
  The shipped table is `PHYSICAL_RANGES` in `scripts/sci_validate.py` — read it there, and widen it in
  that file when a new parameter class appears. (A lab may keep further domain windows in its own
  kinetics/BO pipeline skill; that skill is not part of this package, so do not send the reader to it.)
  Examples:
  - `kcat_true` (dehydrogenase): **1–50 s⁻¹**; <0.1 or >500 → suspect Vmax(mM/s)-vs-kcat(1/s) unit error.
  - `Km` (mM): typically 0.01–10; <0.01 or >50 → caution.
  - `effectiveness_factor`: 0.15–1.0; >1.0 is **non-physical** (can't exceed unity).
  - `alpha_pntab`: 1–5; `qo2_basal`: 0.05–0.30; `kLa`: not pinned at 0.0001 or upper limit.
- **Bound-hit.** A parameter converging to its lower/upper search bound means the optimum is OUTSIDE the
  box → the value is meaningless. Flag any |param − bound| / bound < 1%. (`sci_validate.py` does this if
  you pass bounds.)
- **Identifiability.** Are two parameters trading off (compensation effect)? Signals:
  - huge correlation in the covariance / Hessian (|corr| > 0.95),
  - a parameter with a confidence interval wider than its own value (CV > ~50%),
  - fixing param A makes param B run away to non-physical (a compensation pattern across fit versions).
  If a parameter isn't identifiable, fix it (literature value) and refit — don't report its fitted value.

### Axis 2 — Goodness-of-fit done right (folded into the physical axis)
R² alone is not evidence. Check:
- **Residual structure.** Residuals must look like noise. A systematic run (runs test, or eyeball:
  all-positive then all-negative across the curve) = wrong model, not a good fit, even at R²=0.99.
  `sci_validate.py` runs a Wald–Wolfowitz runs test on residuals if you pass them.
- **Overfitting.** #free params vs #independent data points. Near-saturated DOF + perfect fit = memorization.
- **Prediction↔observation gap & extrapolation.** If the model is used outside the fitted range
  (BO proposing conditions beyond the data box), say so explicitly — extrapolation is not validated.

### Axis 3 — Consistency (units · conservation · SSOT)
- **Units.** Trace every quantity's units end to end. The single most common lab bug
  (mM/s apparent-Vmax stored as 1/s kcat → cascade rate off by [E]). Convert, don't assume.
- **Conservation (mass balance).** Mass and cofactor balance must close (NAD(P)+ + NAD(P)H = const;
  carbon in = out). Pass `mass_balance` to `sci_validate.py` (`t0_total` + measured `species`) and it
  reports closure %: **>100% = FAIL** (impossible; unit/column error — the kind of bug a position-based
  read causes); **<~50% = FAIL** (half the mass missing; wrong species/column); a **mild gap (e.g. 87%)
  = CAUTION → normalize the basis before fitting** (don't fit to a leaking total — e.g. a
  "measured total carbon = product + byproducts + residual substrate vs t0" normalization
  decision). An ODE that leaks mass is wrong regardless of fit quality.
- **Initial conditions / nominal-vs-measured.** Don't fit to a nominal concentration when a measured one
  exists (e.g. a nominal substrate conc. vs the measured one). Confirm IC source in code, not by guess.
- **SSOT.** Canonical numbers come from a single-basis script with parameters pinned in code,
  NOT from one-off calls passing args by hand (one missing arg silently shifts the whole result).
  If the number will be canonical, it must trace to that script.

### Axis 4 — Independent reproduction
- **Re-run is the ground truth.** A delegated/remote number is PROVISIONAL until reproduced on your
  primary machine with a 1-line re-run that matches. Mismatch → discard the number and trace the parameter
  (a real case: a delegated cost figure could not be reproduced locally because a key cost term had been dropped).
- **Robustness.** Refit from a different seed / different initial guess. A real optimum re-converges to
  the same basin; a fragile one wanders. Report the spread.
- **Cross-check against an independent estimate** where one exists (literature kcat, thermodynamic ΔG
  sign from eQuilibrator, a back-of-envelope mass balance).

#### Axis 4a — The reproduction must not have side effects (260721)

Reproducing a claim must not *perform* the thing being claimed. Two real failures, same day:

**Never call a side-effecting function to test its guard.** Verifying a duplicate-send guard by
calling `dispatch(card, "send", None)` posted a real comment to a live project-tracker task — the "simulation"
was the actual send path. Deleted immediately, but the verification of a guard against duplicate
sends *caused* a duplicate send.
- Call the **guard/predicate function alone** (`_check_duplicate_send`, `_content_hash`) — pure, no I/O out.
- Inject a **fake state file** and assert the verdict; never touch live state.
- If the entry point must be exercised, pass the **non-acting branch** (`action="skip"`) or mock the outbound call.
- Writes to shared state (`queue.json`, ledgers, remote APIs): **back up → dry-run → simulate the
  post-state in memory → only then apply.** A dry-run that only lists targets is not enough; simulate
  what the change *does* (e.g. re-derive each record's routing after the edit) before writing.

**Absence of a name is not absence of a feature.** Grepping for a function named `*meta*` returned
nothing, so a guard was reported as unimplemented. It existed as a module-level regex constant
(`_INTERNAL_MEMO_RE`) and worked correctly. Verify by **behaviour, not by identifier**: feed the known
failing input and the known-good inputs, and check the verdicts. Report "not implemented" only after
a behavioural probe fails.

**Both false directions cost.** A false FAIL (feature exists, reported missing) triggers redundant
work; a false PASS ships a defect. State which one a check can produce, and test the guard against
**both** its trigger case and its regression case (must-block AND must-not-block) — a guard that
blocks everything passes a must-block test.

## Workflow

```
0. Raw integrity FIRST: run scripts/check_raw.py on the raw file(s) (or --dir on the data folder).
   Untracked/uncommitted raw → stop and version-control it before trusting any derived number.
   Confirm the column map by header label.
1. Locate the result artifact (results.json / params file / fit object / BO summary). Load it
   DIRECTLY — do not trust a prose summary of it.
2. Run scripts/sci_validate.py on it (auto-checks: physical ranges, bound-hits, residual runs test,
   DOF, unit-sanity, mass-balance closure). It emits a PASS/FAIL/CAUTION per check + JSON.
3. For axes the script can't fully judge (identifiability covariance, SSOT provenance, independent
   reproduction) — do them yourself, with evidence, per the axis notes above.
4. If ANY axis FAILs, or any two checks contradict each other, the overall verdict is FAIL/REJECT —
   even if everything else is green. State exactly which axis failed and why.
5. Report a compact table: axis | verdict | evidence. End with one of:
   ✅ VALIDATED (safe to report/merge) / ⚠️ CAUTION (usable with caveat X) / ❌ REJECT (do not use; fix Y).
```

## Escalation to adversarial multi-agent verify

For a high-stakes number (manuscript canonical value, patent claim figure, a result that flips a
conclusion), don't self-certify. Run an adversarial Workflow: fan out 3 independent verifiers each
prompted to REFUTE the result via a distinct lens (physics / units+conservation / reproduction),
reject unless a majority fail to refute . One verifier ≠ verification.

## Anti-patterns (common real failure modes)

- "Optimizer said SUCCESS" → SUCCESS means it stopped, not that the answer is physical.
- "R² = 0.99" → say nothing about residual structure or units; can be a unit-error fit.
- "전 항목 PASS" self-report when a number contradicts physics → that PASS is void; reproduce and break it.
- Trusting a delegated/remote number before an independent reproduction.
- Building a canonical value from a hand-assembled one-off call instead of the SSOT script.
- Reading rawdata columns / units by assumption instead of confirming in code.
```
