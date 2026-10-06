<!-- Full gate text moved verbatim from AGENTS.md section 0 on 2026-10-07 so that AGENTS.md stays well under the 32 KiB Codex cap. The table keeps the short form; this file is the long form. -->

# Routing gates — long form

Each entry: the request the row matches, then the full gate text.

## Find papers / "what's known about X"

🔒 `scripts/doi_verify.py --doi <list>` — exit 2 means a DOI does not exist (fabricated) or is retracted. Fabricated citations are the failure mode here; do not rely on your own recall.

## Preprints / "has this been posted yet" / 최신 논문 검색 (search for recent papers)

🔒 Every hit is **not peer reviewed** — say so, and when the skill reports a published DOI, cite that instead. bioRxiv's own API has no keyword search: its `?query=` is silently ignored.

## Turn a manuscript into a Korean patent invention disclosure (발명내용설명서)

🔒 `patent-invention-disclosure/scripts/verify_numeric_claims.py` on every claim-critical number **before** the draft is called final. UNRESOLVED is not a pass. Claims + prior-art stay in separate docx files, never merged into the disclosure.

## Analyze experimental data

🔒 `stats-workflow/scripts/assumption_check.py <data> --value <col> --group <col>` — it picks the test from the normality/variance result. Never run a t-test without it. Report n and the assumption verdicts.

## A reported number needs a `±`, a unit conversion (mM/µM, mg/mL via MW) or a calibration-curve concentration; "SD or SEM?"; error propagation, 오차 전파, 불확도, 단위 변환

🔒 Re-run `uncertainty-and-units/scripts/propagate_uncertainty.py` or `uncertainty-and-units/scripts/format_result.py` on the number (never a hand-typed ±); fit parameters rebuilt with correlated_values(popt, pcov), and curve_fit with absolute_sigma=True when the weights are real standard uncertainties; the caption says what the `±` is and what n counts. Needs Python 3.12+ and pint/uncertainties — if absent, say the check could not run.

## Plan an experiment before running it: ≥2 factors, a plate layout, "how many replicates", 실험 설계, DoE, 반복수, 플레이트 배치

Replicate level named (technical vs independent preparation; wells from one prep are not n); seed + pydoe version + run-table CSV recorded in the `lab-record` EXP; CCD axial points checked against the real limits (`face="inscribed"`). Needs Python 3.12+ and pydoe for `doe-and-replication/scripts/doe_designs.py`.

## Molecular weight / band size / pI of an expressed or tagged protein, from a plasmid map ("분자량 계산", "몇 kDa", "밴드 크기")

🔒 `sequence-verification/scripts/construct_mw.py <map> --native-start <motif>` must exit 0 — quote the fusion for a gel and the native for stoichiometry, and label the figure as computed, not measured.

## "Which file carries this variant" / find the expected sequence to align a sequencing read against / which primer reaches the mutation ("시퀀스 파일 찾아", "시퀀싱 대조", "변이 확인용 맵")

🔒 `sequence-verification/scripts/find_variant_maps.py --expect <residue>=<AA>` — a filename or an annotated primer is not evidence, only the translated residue is. A built map is an *expected* sequence, never a verified clone; `sequence-verification/scripts/read_coverage.py` must exit 0 before a primer is ordered.

## Read anything from an external service (my tasks, issues, pages, inbox)

Report what the service returned, not what you remember. Never reach for an always-on app connection when a connector covers the service (§9).

## A document is about to leave the session as finished (mail draft, report, manuscript-adjacent doc)

Flag em-dash / AI-word / template-phrase tells; do not auto-rewrite. A tone learned from the recipient's own thread wins over the skill's suggestion every time. Skip for casual internal chat.

## A bug that survived the first read — wrong number, crash, empty output, sudden slowdown

🔒 Name the **one command** that goes red on this bug and green once fixed, and show you ran it, **before** proposing a cause. A fix is not done until that same command is re-run on the original (un-minimised) case.

## Write tests, or work out why a green suite missed a real defect

🔒 For every assertion, name where the expected value came from. If it was recomputed the way the code computes it, the test passes by construction and verifies nothing. Ask: would this test still pass if the function returned a plausible wrong answer?

## Build a new pipeline/tool, or rewrite a module ("설계부터 하자" [let's design first], "스펙부터" [spec first], "작업 쪼개줘" [break the task down])

Each phase reads the previous artifact, not chat history. Before "done": walk the spec's Success Criteria one at a time and state the observation satisfying each — §2 still applies, a passing run is not a met criterion. Skip the whole workflow for a one-line fix and say you skipped it.

## Test analysis code / "did my change move a number" / a result won't reproduce

🔒 `pytest` exits 0 — quote the summary line. At least one known-answer test for the central computation; every numeric assertion carries an explicit tolerance; stochastic steps take an explicit seed. Regenerating a golden file to go green must be stated and justified.

## The user says something in this toolkit is broken, confusing, missing, or annoying ("이거 불편해요" [this is inconvenient], "왜 안 되지" [why doesn't this work], "자꾸 실패해요" [it keeps failing], "이런 게 있으면 좋겠는데" [it'd be nice if there were something like this])

Ask **one** question to fill in what you cannot infer, then record. Do not interrogate — an incomplete record beats no record. See §10.
