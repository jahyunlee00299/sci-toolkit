# AGENTS.md — Generic Agent Operating Rules for Scientific Coding Work

This file defines tool-agnostic operating rules for any AI coding agent
(Claude Code, Codex, Cursor, Aider, or similar) working in a scientific /
research codebase. It is deliberately generic: no personal names, machine
names, file paths, billing info, or organization-specific tooling. Copy it
into a new project, or import/symlink it from a shared toolkit repo, and
adapt the pointers (marked `<project-specific>`) to your own setup.

**Section 0 is the entry point**: it maps an incoming request to the route it
must take. Sections 1–7 state the operating *principles*; **Section 8 maps each
capability to the concrete command that re-checks its output and the pass
bar** — read it before finalizing any artifact a skill produced.

**Language.** When the user writes in a non-English language, reason/think in
that language too — don't silently switch to English for internal reasoning
while replying in the user's language. Keep code, identifiers, and technical
terms in English regardless. Never substitute a language's native accented or
special characters with plain ASCII equivalents when writing in that language.

> **Claude Code note**: Claude Code automatically reads a file named
> `CLAUDE.md` in the project root (and in parent directories) as its system
> instructions. If you use Claude Code, either rename this file to
> `CLAUDE.md`, or keep both and symlink one to the other so a single source
> of truth serves every tool:
> ```
> ln -s AGENTS.md CLAUDE.md
> ```
> Other agents (Codex CLI, etc.) generally look for `AGENTS.md` directly —
> keep that as the canonical name and symlink the tool-specific name to it,
> not the reverse, so the generic file stays the source of truth.

> **Codex note**: everything in this file applies to you. One thing does not
> carry over automatically: the guards in `hooks/` run as `PreToolUse` hooks
> under Claude Code, and **under Codex nothing runs them unless you wire them
> yourself** — so by default no check inspects a command before it executes.
> The seven rules those guards enforce therefore become rules you follow by
> reading them. They are spelled out, with the exact patterns, in
> **[`CODEX.md`](CODEX.md)** — which also covers Codex's own hook and rules
> mechanisms, and its sub-agent tools. Read it before your first destructive or
> outward-facing action.

---

## 0. Routing — which path does this request take?

**Read this table first, before picking a skill.** Do not improvise a path: if a
request matches a row, take that row's route. Picking an arbitrary skill is the
most common way work goes wrong here.

Each route ends in a **gate**. A gate is not advice — the artifact is not
finished until the gate passes. Gates marked 🔒 are enforced by a script; run it
and read its exit code rather than judging by eye.

| The user asks for… | Route (in order) | Gate before you call it done |
|---|---|---|
| Find papers / "what's known about X" | `research-search` → (`openalex-database`, `pubmed-database`, `research-lookup`) | 🔒 `scripts/doi_verify.py --doi <list>` — exit 2 means a DOI does not exist (fabricated) or is retracted. Fabricated citations are the failure mode here; do not rely on your own recall. |
| Preprints / "has this been posted yet" / 최신 논문 검색 | `biorxiv-database` (Europe PMC `SRC:PPR` + arXiv) | 🔒 Every hit is **not peer reviewed** — say so, and when the skill reports a published DOI, cite that instead. bioRxiv's own API has no keyword search: its `?query=` is silently ignored. |
| Collect references + OA PDFs for a DOI list | `scripts/ref_fetch.py` | 🔒 Read `refs_report.json`: report `discrepancies` and `not_found` explicitly; never silently pick one source. |
| Write a full literature review document | `literature-review` | Citations verified against the fetched records, not from memory. |
| Write / edit a manuscript | `manuscript-pipeline` (+ `academic-term-rules` for notation) | 🔒 `manuscript-pipeline/scripts/nomenclature_lint.py` + `manuscript-pipeline/scripts/numeric_consistency_check.py` + `manuscript-pipeline/scripts/body_typo_lint.py` (units, NAD⁺, glued punctuation) |
| Edit a `.docx` (any change to an existing file) | `docx`(외부) → its `docx/scripts/incremental_edit.py` | 🔒 `docx/scripts/docx_preflight.py` + `docx/scripts/word_validate.py` on the **output** file. Never promote an unverified file. |
| Edit a `.docx` the user has open in Word right now | `manuscript-pipeline/scripts/word_live_edit.py` | Re-read the edited range afterwards — a reported "[OK]" is not proof the text changed. |
| Extract text from a `.docx` for analysis/QC | 🔒 `manuscript-pipeline/scripts/manuscript_text.py --count-only` **first** | Exit 10 = tracked changes present → extract with `--mode accept`. python-docx text is wrong in that case (§4). |
| Insert citations into a manuscript | `endnote-citation-injection` | 🔒 `scripts/doi_verify.py --bibtex <file>` (DOIs real + metadata matches) **and** `manuscript-pipeline/scripts/endnote_biblio_check.py` (every cited number has a backing entry). |
| Check figure/table numbering + captions | `manuscript-pipeline/scripts/figure_caption_check.py`, `manuscript-pipeline/scripts/manuscript_ref_order.py` | Read the verdict *category*; "cited out of order" ≠ "move the caption" (§5). |
| Make a figure for a paper | `publication-figures` | 🔒 `scripts/figure_lint.py`; numbers redrawn from raw data, not copied from a previous figure (§3). |
| Analyze experimental data | `lab-data-analysis` → `stats-workflow` (or `statsmodels`) | 🔒 `stats-workflow/scripts/assumption_check.py <data> --value <col> --group <col>` — it picks the test from the normality/variance result. Never run a t-test without it. Report n and the assumption verdicts. |
| Fit / optimize / calibrate a model | the relevant analysis skill → **`scientific-validation`** | 🔒 `scientific-validation/scripts/sci_validate.py` — mass balance, physical plausibility, parameter sanity. |
| Report any number in a document/report/email | — | 🔒 §3 SSOT: re-derive from the canonical script/raw data. A number that only exists in chat history is not verified. |
| Design primers / cloning | `primer-design` | Sequence re-checked against the construct; order sheet re-read before sending. |
| Make slides | figures first via `publication-figures` → `journal-presentation-maker` + the office skill your agent ships (see the note below the table) | Numbers and claims traced to their source (§3). Slide figures are finished image files, never plotted by the slide skill. |
| Convert a file (PDF/docx/xlsx → md) | `markitdown`, `paper-extract` (또는 외부 `pdf`·`xlsx`) | Spot-check the output against the source; conversion silently drops content. |
| Search the live web | `research-search` → built-in WebSearch / WebFetch | Cite sources; separate what a source said from your inference. No API key is needed. |
| Read anything from an external service (my tasks, issues, pages, inbox) | the connector in `scripts/connectors/` — reads need no flag (`mail list`, `github issues`, `asana tasks`, `notion search`) | Report what the service returned, not what you remember. Never reach for an always-on app connection when a connector covers the service (§9). |
| Send/post anything outward (mail, issue, task, page) | the connector in `scripts/connectors/` | 🔒 §9 draft-first: **stop at the draft.** A human sends it. Without `--write` a connector only previews; that preview is not proof the write would succeed. |
| Write or restructure code | `code-quality` | §1 SOLID; §2 verification gate before claiming it works. Reviewing a change: run **Standards** and **Spec** as separate passes and report them separately — a change that follows every convention can still implement the wrong thing. |
| A bug that survived the first read — wrong number, crash, empty output, sudden slowdown | `debugging-loop` | 🔒 Name the **one command** that goes red on this bug and green once fixed, and show you ran it, **before** proposing a cause. A fix is not done until that same command is re-run on the original (un-minimised) case. |
| Write tests, or work out why a green suite missed a real defect | `test-quality` | 🔒 For every assertion, name where the expected value came from. If it was recomputed the way the code computes it, the test passes by construction and verifies nothing. Ask: would this test still pass if the function returned a plausible wrong answer? |
| Set up / install / "it's not working" | `doctor.py` | 🔒 `python doctor.py` must print `PASS` — quote the failing line, don't paraphrase. |
| The user says something in this toolkit is broken, confusing, missing, or annoying ("이거 불편해요", "왜 안 되지", "자꾸 실패해요", "이런 게 있으면 좋겠는데") | fix it if you can, **and** `scripts/feedback_log.py add "<what>"` | Ask **one** question to fill in what you cannot infer, then record. Do not interrogate — an incomplete record beats no record. See §10. |

> **외부 의존 — 오피스 문서(docx·pdf·pptx·xlsx)**: 이 저장소는 오피스 스킬을
> 재배포하지 않는다. 표에서 `docx`·`pdf`·`pptx`·`xlsx` 를 가리키는 행은 **네가
> 돌고 있는 에이전트가 제공하는 오피스 스킬**로 읽어라 — 구현이 무엇이든 그 행의
> 게이트(🔒)는 그대로 적용된다.
>
> - **Claude Code** — Anthropic 오피스 스킬(사용자 환경에 있을 때)
> - **Codex** — 자체 번들 오피스 플러그인이 기본 활성이다. 이름과 제약은
>   `CODEX.md` 를 볼 것(슬라이드 쪽에 그림 관련 제약이 있다)
> - **둘 다 없음** — `docs/12_문서스킬_직접_준비하기.md`
>
> 어느 쪽이든 **산출물 검증 게이트는 동일하다**: `.docx` 텍스트 추출은
> `manuscript_text.py --count-only` 를 먼저 통과해야 하고(exit 10 = 추적변경),
> figure 는 `scripts/figure_lint.py`, 수치는 §3 SSOT 를 탄다. 랩 자체 제작 원고 QC
> 도구 7종(`manuscript-pipeline/scripts/`)은 오피스 스킬과 무관하게 동작한다.
>
> 슬라이드에 들어갈 그림은 **먼저 `publication-figures` 로 만들고 완성된 이미지
> 파일을 넘겨라.** 슬라이드 스킬에 데이터를 주고 플롯을 그리게 하지 말 것 —
> 그림의 출처 추적(§3)과 회귀 방지(§5)가 그 순간 끊기고, 에이전트에 따라서는
> 아예 금지된 동작이다.

### Rules that override the table

1. **Verify before reporting done** (§2). A script exiting 0 is not proof the
   output is correct. Re-derive the result independently.
2. **Never weaken a gate to make it pass.** If a check fails, fix the artifact.
   If you change a check, say so explicitly and justify it.
3. **Don't invent a file or skill.** If a path or skill you want doesn't exist
   in this package, say so — do not write instructions that point at it.
   `python tests/test_skill_references.py` catches this.
4. **Uncertain which route applies?** Ask, or state the assumption you're
   proceeding under. Do not silently pick the closest-looking skill.



---

## 1. Code Quality — SOLID / Clean Code

- New code should follow SOLID principles: **S**ingle responsibility,
  **O**pen/closed, **L**iskov substitution, **I**nterface segregation,
  **D**ependency inversion. A function or class should have one clear job.
- Prefer small, composable functions over long monolithic scripts. If a
  script exceeds a few hundred lines or mixes unrelated concerns (I/O,
  math, plotting, CLI parsing all in one file), split it.
- No duplicated logic across files — extract shared code into a common
  module rather than copy-pasting between scripts.
- Read a file immediately when it's the target of a task rather than
  guessing its contents or running exploratory shell commands first.
- On starting a new project, write a short `PROJECT_STRUCTURE.md` (or
  equivalent) describing directory layout and entry points, so future
  agents don't have to reverse-engineer it.
- One-off / throwaway scripts belong in a dedicated scratch or
  `scripts/oneshot/` directory — never scattered at the project root.

## 2. Verification Gate — Never Trust Self-Report

This is the single most important rule for scientific / numerical work.

- **After any critical output** (a numeric result, a fitted parameter, a
  figure, a generated report, a code change with runtime behavior),
  perform an **independent re-verification** before treating it as final.
  "Independent" means: re-derive or re-check from the underlying data/code
  directly, not by re-reading the same summary that produced the claim.
- **Distrust self-report from sub-agents or delegated processes.** If a
  task was delegated (to a sub-agent, a background process, another
  session), do not accept its own "done ✅" message at face value —
  re-parse the actual output, re-run the check, or re-read the file it
  claims to have changed.
- A "verified" result should be reproducible by a second, independent pass
  (different method, different agent, or simply re-running from raw
  inputs) that agrees with the first. If the two disagree, the result is
  **not** verified — investigate the discrepancy before reporting either
  number.
- For code changes with observable runtime behavior, actually exercise the
  change (run it, drive the affected flow) rather than relying solely on
  a type-check or a diff read-through.
- Scale verification effort to the cost of being wrong: a quick internal
  script needs a lighter check than a number going into a publication,
  a report, or a decision with real consequences.

## 3. Number SSOT (Single Source of Truth)

- Any number reported, plotted, or written into a document must trace
  back to a single canonical source — the raw data file or the script
  that computes it directly from raw data. Never hand-copy or re-type a
  number from memory, from a chat transcript, or from a previous report.
- Never guess column names, units, or the definition of a computed
  quantity (e.g., yield, conversion, rate) — open the raw data and the
  method description and confirm before using it.
- Before comparing a model output to an experimental result, confirm that
  the comparison is apples-to-apples: same conditions, same method, same
  definition of the reported metric. A mismatch here is a common silent
  error.
- If a number came from a delegated/remote computation, treat it as
  **provisional** until it has been independently reproduced (ideally in
  one line/command) from the same raw source.
- Prefer a single canonical script per figure/table/number over "one-off
  hand calculation, then copy the result elsewhere." If the number needs
  to be regenerated, running that one script should be sufficient.

## 4. Academic / Scientific Writing Conventions

`<project-specific: point this at your own nomenclature/style skill or
style guide>`

General rules to apply regardless of specific style guide:
- Species names are italicized (*Escherichia coli*, not E. coli in plain
  text) and follow standard binomial nomenclature (genus capitalized,
  species lowercase, abbreviated after first use: *E. coli*).
- Gene names are italicized and lowercase (or per organism convention);
  protein names are typically not italicized and follow the organism's
  standard capitalization convention.
- Units follow SI conventions with a space between number and unit
  (`25 °C`, `10 mM`, not `25°C`/`10mM`), and are consistent throughout a
  document (don't mix `g/L` and `mg/mL` for the same quantity across
  figures).
- Kinetic parameters use standard symbols (k_cat, K_m, V_max) with
  consistent subscript/italic formatting.
- Figure captions state what is plotted, the conditions, sample size /
  replicates, and error bar definition (SD vs SEM) — and every number in
  a caption must trace back to the raw data (see Section 3), not be
  retyped from memory.
- If your project has a dedicated nomenclature/style skill or reference
  document, load and follow it before finalizing any manuscript text —
  don't rely on general knowledge for field-specific conventions.

## 5. Figure Anti-Regression Rule

Figures for publication or reports are easy to silently regress (wrong
theme, broken caption, stale numbers) when re-generated repeatedly. Apply
this discipline:

- **Locked theme**: maintain one canonical plotting theme/style module
  (fonts, colors, sizes) that all figure scripts import — don't
  hand-tune styling inline per figure, and don't let a "quick fix" drift
  the theme for one figure away from the rest.
- **Lint gate**: run a figure linter (font consistency, missing axis
  labels, non-standard colors, resolution/DPI checks, etc.) before
  treating a figure as final. Target: zero high-severity lint findings.
- **Captions from rawdata only**: any number appearing in a figure
  caption is pulled from the same raw-data source as the plot itself
  (see Section 3) — never typed by hand.
- **Version control the figure pipeline, not just the output image**:
  commit the script/data changes *before* rendering, so regressions are
  traceable to a specific commit. Treat rendered images as build
  artifacts (can be regenerated, don't need their own manual history);
  the SSOT is the script + raw data.
- Recommended order: edit script → commit → render → visually verify the
  output actually looks right (don't assume a clean run == correct
  figure).
- Avoid repeatedly overwriting one review/gallery file if it destroys the
  ability to compare against a previous version — snapshot when it
  matters.

## 6. Model Routing Philosophy

Match model/agent capability to task difficulty — this saves cost and
often improves quality (a heavy model overthinking a trivial task can
introduce unnecessary changes).

- **Simple, mechanical, or shallow tasks** (read a file, run a lookup,
  extract a field, compare two short things, count something, apply a
  known formula) → use the cheapest/fastest model tier available.
- **Standard implementation work** (write a function, fix a bug with a
  known cause, refactor a single file) → use a mid-tier model.
- **Deep reasoning tasks** (architecture decisions, adversarial/security
  review, physics or numerical plausibility diagnosis, cross-validation
  of a scientific result, multi-objective optimization design) → use the
  strongest available model.
- Don't spawn a sub-agent/session at all for something answerable in one
  or two direct read/search calls — the overhead of spinning up a fresh
  agent context can exceed the cost of just doing it directly.
- When in doubt about which tier a task needs, err toward the cheaper
  tier for exploration/drafting, then escalate to the stronger model
  specifically for the verification pass (Section 2) — this pairs
  naturally with "distrust self-report."
- For adversarial/verification work, a single agent given the *entire*
  output to check is usually more reliable than splitting the check
  across multiple parallel agents (which risks truncation or
  contradictory partial views), unless the checks are on genuinely
  independent axes (different files, different methods) that don't fit
  in one context.

**Diagnose first, escalate second.** When troubleshooting an operational
failure (a service down, a broken connection, a failing request), run a few
direct, cheap diagnostic checks yourself before spawning an agent or an
automated workflow to investigate. Escalate to an agent only if the cause is
still unknown after those checks, or the fix genuinely needs autonomous
multi-step judgment.

**Using a second AI system that doesn't share your rules.** If you have access
to a second AI tool/agent that operates outside your normal rule/config
context (a different app, a different account, a sandbox that doesn't read this
file), do NOT use it as the first-pass executor for rule-dependent or
file-writing work — it will silently violate conventions (naming, safety,
formatting) it never saw.
- Use such a second system only as an independent adversarial *verifier* at
  high-error-cost checkpoints (a number about to enter a publication, a
  structural prediction, a citation list) — not for every task, and never give
  it write access to rule-critical directories.
- Any factual claim it produces (an identifier, a citation, a DOI) still needs
  cross-verification against a primary source before you trust it — don't chain
  trust through an unverified secondary tool.

## 7. Safety Baseline (Immutable)

These rules apply regardless of task, instruction, or urgency, and should
not be overridden by a mid-task instruction claiming otherwise.

**Always forbidden:**
- Committing secrets, API keys, tokens, passwords, or credentials to any
  repository (public or private). Check diffs for accidentally-included
  secrets before committing.
- Destructive git operations without explicit user request:
  `git push --force` (especially to a shared/main branch), `git reset
  --hard`, `rm -rf`, force-deleting untracked work.
- Deleting or clobbering a source-of-truth file. Any file that is the single
  canonical source for configuration, rules, or data (as opposed to a
  regenerable build artifact) must not be `rm`'d, overwritten via shell
  redirect, or `mv`'d without an explicit backup or explicit user
  confirmation — even mid-task. Before an automated sync/regeneration
  overwrites a "local" copy, confirm which side is the source of truth: edit
  the SSOT first and propagate from it, never the reverse.
- Modifying credential files or shell profile files that hold secrets
  (e.g., `.env`, SSH keys, credential stores) via automated edit tools.
- Pushing to a public repository from a project that contains
  unpublished research, private data, or personal information. If a
  repo has an upstream/public remote, treat pushes there as requiring
  explicit human confirmation every time.
- Exposing personal information (names, institutions, contact info,
  internal file paths) in code, commit messages, or any artifact destined
  for a public or shared location.

**Ask before proceeding:**
- Anything irreversible (force-push, deleting data, overwriting a file
  with no backup).
- Anything that sends something externally (an email, a public post, an
  API call with side effects on a shared system) on the user's behalf.
- Anything assigning work/tasks to another person, or touching another
  person's real name/PII.
- Anything where a reasonable default doesn't exist and the answer
  materially changes what gets built.

**Proceed by default (don't ask):**
- Anything with a clear, conventional default — pick it, state the
  choice in one line, and continue.
- Verifiable facts (just go check, don't ask "should I check?").
- Reversible actions confined to the local working copy (editing a
  script, running a local test, regenerating a local figure).
- Explicit, unambiguous instructions — don't ask for confirmation on
  something the user already clearly asked for.

### Git branch hygiene (safe cleanup)

Repos accumulate stale branches; clean them with a reversibility test, not
intuition. Verified procedure (260809, six-repo cleanup, zero loss):

- **Classify before deleting**, and write every SHA to a backup file first:
  a local branch whose tip is an ancestor of `origin/<default>` (merged), or
  reachable from *any* origin ref (`git branch -r --contains <sha>`, pushed),
  is deletable with zero loss — the origin retains the objects. A branch on
  no origin ref is **irreversible** to delete: judge it per-branch, never in
  bulk. `git branch -d` is not a safety judge — it only compares against the
  default branch and misses "preserved in a different branch".
- **Containment chains**: run `git merge-base --is-ancestor A B` pairwise
  among unmerged branches; in a chain `A ⊂ B ⊂ TIP`, processing the TIP
  resolves the members. `git cherry origin/<default> <branch>` with all `-`
  means the content already lives in default (squash/rebase residue).
- **Hands off live work**: never delete a branch checked out in a worktree,
  and treat a branch with today's commits as belonging to a live session.
- **Oversized/binary-polluted branches**: archive as a verified `git bundle`
  (checksum both ends) on bulk storage instead of pushing to the code host.
- **Before pushing to any public or shared repo**, scan the full diff — not
  just filenames — for private markers (names, home paths, tokens,
  unpublished model/reaction structure). Example code and docs are the
  classic leak: the numbers are absent but the structure of unpublished
  work is not.
- **Merging accumulated branches**: merge only with the repo's test suite
  green on the *merged* tree; otherwise record a verdict (HOLD / SUPERSEDED
  / ARCHIVE) with the exact command as evidence. "Superseded" needs
  file-level diff proof, not "looks replaced".

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

---

## 9. External Service Connections (mail, GitHub, Asana, Notion, calendar, shared sheets)

Connecting the agent to external services (mail, code host, task/doc
managers, calendar, shared spreadsheets) adds power but also the ability to
take OUTWARD, hard-to-undo actions. These rules govern how to do it safely;
they extend §7 (Safety Baseline).

### Credentials & connection

- **Avoid MCP-style always-on connections.** For any service that already
  ships a REST/API connector script (`scripts/connectors/`) — mail, GitHub,
  Asana, Notion, calendar, shared sheets — use that connector with a scoped
  personal token (or, for calendar/sheets, a one-time OAuth consent) instead
  of the tool's built-in "connect" button. A connector invocation only
  touches what that one command asked for; an MCP connection stays open to
  the whole account for every future turn regardless of whether the current
  task needs it. Treat MCP as a last resort: only for a service that has no
  connector yet, or for exploratory browser work that has no API
  equivalent.
- Once a service has been switched to its connector, disconnect that
  service's MCP connection in the app's own settings (a human action, not
  something the agent does on its own) so the standing access shrinks to
  what's actually in use.
- When a token IS required (e.g. a code-host personal access token), store
  it in a secrets store or the tool's credential manager, NEVER inline in
  code, chat, commits, or a plaintext file in the repo. Never echo a token
  into visible output.
- Treat tokens like keys: scope them minimally, rotate/revoke on any
  suspected leak. Do not commit anything matching a secret pattern (check
  the diff before committing — this restates §7).

### ⭐ Draft-first for outward actions (the core rule)

- **Anything that goes OUT to other people is draft-first by default:
  compose it and leave it in a draft / staging state; do NOT send/publish/
  submit it.** The human reviews and performs the final send themselves.
  This applies to: email (leave in Drafts, never auto-send), posting/
  commenting on a task or doc, sending a calendar invite to others, opening
  a pull request.
- State clearly when you've left something as a draft and that the human
  must send it. Do not press "send" on a person's behalf unless they
  explicitly, unambiguously ask you to send *this specific* message now.
- Prefer composing via the service's own draft mechanism (a real Drafts
  folder) so the human sends from the normal UI, rather than staging text
  somewhere non-standard.

### The `--write` contract (what a dry-run does and does not prove)

Every write-capable connector command refuses to act without `--write`; it
prints the exact payload instead. Two consequences worth stating, because
getting either backwards is how a preview turns into a surprise:

- **A dry-run runs without credentials.** Previewing a write does not require
  a token, so you can inspect what *would* be sent before any token exists.
  The one deliberate exception is a command whose preview must be checked
  against live schema to mean anything — there, the connector says so and
  asks for the token rather than showing an unvalidated payload.
- **A dry-run is not a rehearsal.** It shows the payload; it does not prove
  the request would be accepted, that the target exists, or that a safety
  check passed. When a connector could not run one of its guards without a
  token, it says so in the preview — read that line rather than assuming
  silence means "checked and fine."

Never remove or weaken a `--write` gate to make an automation smoother. If a
flow needs many writes, have the human approve the batch — do not make the
gate disappear.

### Reading vs. writing vs. sending

- **Reading** your own inbox / repo / task list / sheet / calendar = safe,
  proceed without asking.
- **Writing to your own space** that's easily reversible (a draft, a local
  branch, a scratch row) = proceed, state what you did.
- **Sending outward, deleting shared data, assigning work to a real
  person, force-pushing** = confirm first (and for outward messages,
  draft-first per above).

### Code host (e.g. GitHub) specifics

- Never push unpublished research, private data, or personal info to a
  public repository.
- If a repo has an upstream/original remote (i.e. it's a fork), treat any
  push or PR to that upstream as requiring explicit human confirmation
  EVERY time — an accidental push there can expose unpublished work.
  Default pushes go to your OWN fork/origin, on a feature branch, never
  directly to a shared main/master.
- Pull requests are draft-first: open them for review; do not merge to a
  shared main branch on your own authority.

### Shared spreadsheets / documents

- A shared sheet/doc is multi-person data: prefer additive, reversible
  edits; never bulk-delete or restructure a shared sheet without explicit
  confirmation and ideally a backup/snapshot first.
- When a number will be read by others, it still follows §3 (Number SSOT)
  — trace it to its source, don't hand-type.

These rules exist so the agent can safely touch external systems without
ever taking an irreversible outward action on a human's behalf by
surprise.

---

## 10. Recording Friction — when the toolkit itself is the problem

Most friction with a tool gets worked around silently and then forgotten.
The workaround lives in one person's head, and the next person hits the same
wall. A recorded complaint is the only kind that can be fixed.

**Trigger.** The user says something in this toolkit is broken, confusing,
missing, or simply annoying — "이거 왜 안 되지", "자꾸 실패해요", "이런 게 있으면
좋겠는데", "this is confusing", "it keeps failing". This includes the case where
you have already solved their immediate problem: the workaround is *evidence*,
not a reason to skip the record.

**What to do.**

1. **Fix or unblock them first.** The record is not a substitute for helping.
2. **Ask at most one question** — whatever you genuinely cannot infer from the
   conversation (usually "what did you expect to happen instead?"). Then stop
   asking. Interrogating someone who is already frustrated is how you get zero
   records. An incomplete record beats no record.
3. **Record it**, filling in what you already know from context:

   ```bash
   python scripts/feedback_log.py add "<what went wrong, in their words>" \
       --kind bug --skill <skill name> \
       --expected "<what they wanted>" --actual "<what happened>"
   ```

   `--kind` is one of `bug`, `friction`, `missing`, `docs`, `idea`.
   Everything except the first argument is optional; omit what you don't know
   rather than guessing.
4. **Tell them it was recorded**, in one line. People stop reporting things
   when reports seem to vanish.

**Where it goes.** `out/feedback.jsonl`, a local file. No account, token, or
network access is required — that is deliberate. Someone who received this
toolkit on a USB stick must be able to record a problem on day one.

**Promotion (maintainers).** Whoever maintains the toolkit collects the records
later:

```bash
python scripts/feedback_log.py list --pending
python scripts/feedback_log.py export                       # print issue bodies
python scripts/feedback_log.py export --github --repo owner/name --write
```

Each exported issue carries its origin (record ID, timestamp, OS, Python and
Claude Code versions) so it can be reproduced without going back to ask.
Per §9 this is an outward action: without `--write` it only previews.

**Do not** record another person's private data, credentials, or unpublished
research content in a feedback entry — it is written to a file that is meant to
be shared upward. Describe the failure, not the material it happened to.

---

## Adapting This File

Sections marked `<project-specific>` are pointers, not content — replace
them with links to your own style guides, linters, or reference docs.
Everything else is meant to be usable as-is across projects. Keep this
file itself free of: personal names, hostnames/IPs, absolute file paths,
API keys or account IDs, billing/financial details, and any
organization-internal tooling names — those belong in a separate,
project-specific (and likely git-ignored or private) configuration layer
that this file can reference by role ("your CI system", "your issue
tracker") rather than by name.
