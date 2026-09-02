<!-- Moved verbatim from AGENTS.md on 2026-09-02 so that AGENTS.md stays under the 32 KiB that Codex reads (`project_doc_max_bytes`). AGENTS.md keeps a stub with the rules in force; this file is the full text. -->

## 8. Per-Capability Verification Routes (execute after using a skill)

Sections 2–7 are the *principles*. This section is the *operational map*: for
each capability that ships a real verification device, it states the error the
device prevents, the exact command to run, the pass condition, and which
principle it enforces. **When you use one of these skills to produce an
artifact, running its verification route is not optional — it is the second
half of the task.** Paths are relative to the toolkit root.

Two hard truths from auditing the actual scripts, so you don't misuse them:
- **A "PASS" from a static/structural checker is not always ground truth.**
  Where a skill provides both a static check and a real-engine check (docx),
  you must pass *both* — the static one has documented blind spots.
- **"Advisory" ≠ "gate."** Some linters always exit 0 and only *report*. Don't
  treat their clean output as a pass, and don't treat their findings as
  blocking. Each row below marks which is which.

### Blocking gates — artifact is NOT done until this passes

| Capability | Error prevented | Command (from toolkit root) | Pass condition | Enforces |
|---|---|---|---|---|
| **publication-figures** | Style regressions in a figure: raw legend calls, hardcoded hex/fontsize, descriptive panel titles, `suptitle`, in-axes condition labels, external legend, no layout manager, `savefig` without dpi/bbox | `python skills/publication-figures/scripts/figure_lint.py <render_script.py>` | **0 HIGH-severity** findings; nonzero exit = not done. Run on *every* render script. | §5, §2 |
| **manuscript-pipeline** (numeric) | Same quantity with conflicting values across text/table/figure-CSV (>2% rel.); figure/table cited-but-not-captioned or vice-versa | `python skills/manuscript-pipeline/scripts/numeric_consistency_check.py <MANUSCRIPT.docx> --csv <FIGURES_DIR> --json review.json` | exit 0 / `RESULT: PASS`. Rerun until PASS before finalizing (Phase 3→4 gate). | §3, §2 |
| **docx** (structural) | OOXML corruption incl. the duplicate-ZIP-member pattern that python-docx and the static preflight silently miss but Word rejects | `python skills/docx/scripts/docx_preflight.py <file>` **AND** `python skills/docx/scripts/word_validate.py <file>` | preflight = PASS/PASS_WITH_WARNINGS **AND** word_validate = CLEAN. **Both required** — preflight alone is NOT sufficient (documented blind spot). | §2, §7 |
| **scientific-validation** (5 axes) | Physically implausible / unidentifiable / overfit / bound-hit / mass-balance-violating fit reported as trustworthy; results from uncommitted raw data | `python skills/scientific-validation/scripts/check_raw.py <rawfile>` (Axis 0) then `python skills/scientific-validation/scripts/sci_validate.py --json <results.json> --emit-json` (Axes 1–4) | Axis 0 not FAIL; sci_validate exit 0 (exit 1 = real science FAIL, exit 3 = check crashed — distinct). A single contradiction invalidates a blanket PASS. | §2, §3 |
| **primer-design** | Hairpin/homodimer primers, F/R pairs that don't form the intended overlap, internal RE cut sites in the insert, frameshift / premature-stop / CDS-not-×3 | Auto-invoked in the design pipeline (`_check_expression_viability` after design). You must read the result: `overlap_verified == True`, reading frame preserved, `expression_check.verdict != "FAIL"`. | If verdict FAIL → redesign, do not proceed. | §2 |
| **xlsx** | Delivered spreadsheet with live formula errors (`#VALUE! #DIV/0! #REF! #NAME? #NULL! #NUM! #N/A`) | `python skills/xlsx/scripts/recalc.py <file.xlsx>` | **Zero** formula errors reported. Mandatory whenever formulas are used. Note: xlsx has **no** structural/corruption validator — only this formula scan. | §2 |
| **literature-review / endnote-citation-injection** | Hallucinated/unresolvable DOIs, duplicate papers, citation-injection docx corruption | DOI cross-verify (CrossRef **and** OpenAlex — never trust a single source) + dedup before finalizing; for endnote, post-injection docx integrity check | No unresolved DOI; no dup; injected docx passes structural counts | §3, §2 |

### Advisory checks — run and read, but they do NOT block (never treat clean output as a "gate passed")

| Capability | Reports | Command |
|---|---|---|
| **manuscript-pipeline** (nomenclature) | Abbrev/unit/dash/species-italic flags for *manual* review (does not verify formatting itself) | `python skills/manuscript-pipeline/scripts/nomenclature_lint.py <file>` — advisory, no exit gate |
| **manuscript-pipeline** (AI-tells) | AI-sounding prose (inflated adjectives, filler, signature verbs) | `python skills/manuscript-pipeline/scripts/ai_tells_lint.py <file>` — always exits 0, report-only |
| **docx** (visual) | Renders pages to PNG for layout inspection (figure placement, table overflow, page breaks) — a *rendering* aid, not a structural check | `python skills/manuscript-pipeline/scripts/visual_check.py <file> <outdir>` |
| **publication-figures** (fidelity) | SSIM + pixel-MAE vs a reference image when reconstructing a figure | `python skills/publication-figures/scripts/figure_compare.py <a> <b>` (≥0.85 high) |

### Capabilities with NO built-in verification device

Do **not** invent a `*_lint.py` for these — none exists. Enforce the relevant
principle *manually* instead:
- **research-ideation** — judgement-shaped output; there is
  nothing mechanical to check. The claims it produces still pass §2/§3.
- **paper-extract, markitdown, pdf** — extraction/conversion wrappers. They fail
  by silently dropping content, so spot-check the output against the source
  rather than trusting a clean exit.
- **research-search, research-lookup, openalex-database, pubmed-database, biorxiv-database** — the
  search itself has no correctness gate, but **the DOIs they return do**: run
  `scripts/doi_verify.py` before any of them enters a document (see below).

### Devices added because "no device" was the wrong answer

These three used to be in the list above. Each was a place where a wrong result
was both plausible and expensive, and the check turned out to be mechanical
after all — so it became a script instead of a instruction to be careful.

| Was "manual only" | Now | What it catches |
|---|---|---|
| DOI cross-verify (literature, citations) | `python scripts/doi_verify.py --doi <list>` / `--bibtex <file>` | A DOI that **does not exist** (fabricated), a retracted paper, or metadata that disagrees with the record. Exit 2 = fabricated/retracted, 1 = mismatch or could-not-verify. **"Could not reach the API" is reported as UNVERIFIED, never as a pass.** |
| stats-workflow assumption checks | `python skills/stats-workflow/scripts/assumption_check.py <data> --value <col> [--group <col>] [--run]` | Running a t-test on non-normal data, or a pooled t-test under unequal variance. Implements the SKILL.md decision tree: normality (Shapiro / D'Agostino by n) + Levene → names the test to use, and with `--run` reports it in APA form with effect size. |
| academic-term-rules TYPO_PATTERNS | `python skills/manuscript-pipeline/scripts/body_typo_lint.py <file.md>` | Unit/notation typos (`50ul`, `37°C`, `n=3`, `NAD+`) as AUTO-FIXABLE, and punctuation glued to the next word as REVIEW-ONLY (never auto-replaced — the whitelist for abbreviations/URLs/decimals must be applied by a human first). |

> The lesson worth keeping: "the mistake is cheap to undo" is not a reason to
> leave a check unwritten. If the rule is stated precisely enough to follow, it
> is usually precise enough to execute — and a script does not get tired or
> assume it already checked. Only leave it manual when the judgement genuinely
> cannot be reduced to a rule.

> **How to wire this into your own project**: if you add or fork a skill,
> add its verification route to the correct table above (blocking vs advisory
> vs none). An AI reading this file should be able to answer, for any artifact
> it just produced, "which command re-checks it, and what's the pass bar?"
> If the answer is "there is no device," that means *you* run the §2/§3 check
> by hand — it does not mean the artifact is exempt from verification.
