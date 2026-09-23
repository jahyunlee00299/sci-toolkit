# Changelog

This file records the version history of the sci-toolkit distribution.
Format follows [Keep a Changelog](https://keepachangelog.com/), versioning
follows [Semantic Versioning (SemVer)](https://semver.org/).

## [1.2.74] — 2026-09-24

- ledger: describe the sanitized markers without naming them

## [1.2.73] — 2026-09-24

- toolkit: fix what the journal-ppt swap surfaced (dead refs, markers, EOL)

## [1.2.72] — 2026-09-24

- toolkit: replace deprecated journal-presentation-maker with journal-ppt

## [1.2.71] — 2026-09-23

- markitdown: point OpenRouter examples at current Claude models

## [1.2.70] — 2026-09-22

- paramguard: document rule (4), the document-vs-document gate

## [1.2.69] — 2026-09-21

- skills: ship compat-check's code from PyPI instead of a vendored copy

## [1.2.68] — 2026-09-21

- catalog: keep the original category grouping when inserting paramguard

## [1.2.67] — 2026-09-21

- skills: register paramguard in the catalog, and strip private research data from it

## [1.2.66] — 2026-09-21

- skills: add paramguard, with its unpublished status stated up front

## [1.2.65] — 2026-09-16

- Add compat-check skill: pre-install dry-run compatibility probe

## [1.2.64] — 2026-09-16

- chore: dedupe CHANGELOG entry from rebase

## [1.2.63] — 2026-09-16

- docs: English pass on README/QUICKSTART/docs-04 for public distribution

## [1.2.60] — 2026-09-16

- publication-figures: retire the white marker edge, separate series by stroke

## [1.2.59] — 2026-09-15

## [1.2.58] — 2026-09-07

- feat(skills): add patent-invention-disclosure

## [1.2.57] — 2026-09-03

- CI installs requests for the web-scraping EZproxy path

## [1.2.56] — 2026-09-03

- web-scraping suite: importorskip pypdf in the PdfDownloader fixture; CI installs pypdf

## [1.2.55] — 2026-09-03

- CI fixes: pytest-style sniff requires no __main__ guard; gitleaks allowlist anchors match relative and absolute paths; CI installs pytest and httpx

## [1.2.54] — 2026-09-03

- web-scraping suite: importorskip habanero on the three CrossRef CLI cases; CI installs habanero and pyyaml

## [1.2.53] — 2026-09-03

- Adopt four measured gaps from a 12-repo GitHub survey: skill spec contract, script-level drift, dependency declaration, gitleaks layer

## [1.2.52] — 2026-09-03

- tests: SKILL.md size ratchet, dual-mode runner (script + pytest), doctor --offline

## [1.2.51] — 2026-09-03

- doctor: split the 1,300-line module into doctor_lib/ (result, sentinel, env/repo checks, dead-automation, self-test runner)

## [1.2.50] — 2026-09-02

- scripts: one HTTP retry policy (sci_http) for ref_fetch, si_fetch and jcr_batch_verify

## [1.2.49] — 2026-09-02

- doctor: report an upstream outage as WARN, not a broken tool; one subprocess helper; drop the dead Korean summary matcher

## [1.2.48] — 2026-09-02

- Make tool connectivity measurable: orphan/untested check in doctor, route eight orphan tools, retire two dead files

## [1.2.47] — 2026-09-02

- Lightweight agent rules and two oversized skills; add skill-drift check

## [1.2.46] — 2026-08-28

- Merge branch 'toolkit/chore/english-only-260828' into main

## [1.2.45] — 2026-08-28

- Translate repository text to English; add the rule that governs it

## [1.2.44] — 2026-08-28

- skills: two figure-integration failure modes the existing gates cannot see

## [1.2.43] — 2026-08-27

- docs(asana): cap tables at ~5 columns in sanitize_html rules

## [1.2.42] — 2026-08-26

- Normalise two working-tree files to LF and stop the drift from coming back

## [1.2.41] — 2026-08-26

- Fix the checks the new doc broke: dead reference, doc count, checksums

## [1.2.40] — 2026-08-26

- Add terminal_setup: colour scheme, CJK-correct font, tab colours, history search

## [1.2.39] — 2026-08-26

- docs: life-science requests can be blocked above the model (AGENTS.md 6b)

## [1.2.38] — 2026-08-22

- fix(doctor): the credentials-divergence check only looked at the old secrets
  path (C-66). The shared repo moved from `~/.claude/secrets.json` to
  `~/.secrets/secrets.json` on 2026-08-16, but the check kept stat-ing only
  the old path, so it handed installers who had already migrated a **false
  diagnosis** ("no repo found"). It now checks the new path first and keeps
  the old path only as a fallback for installers who haven't migrated yet.
  The WARN message now quotes whichever path it actually read.
- fix(tests): `test_credentials_divergence.py` was **writing to, deleting,
  and restoring the user's actual secrets path directly**. The only reason
  this hadn't caused an incident is that the path happened to be empty — the
  design itself was dangerous. Fixed by redirecting `HOME`/`USERPROFILE` to a
  temp home so the real home directory is never touched (patching
  `Path.home()` alone isn't enough — the doctor uses `expanduser()`, which
  reads environment variables directly and doesn't go through
  `Path.home()`). Check strength was not reduced: all 10 assertions across
  8 cases still pass.
- docs(CODEX): cross-checked the hooks/rules contract measured on 0.147.0
  against the 0.148.0–0.149.0 release notes. All five measured facts **still
  hold** (exit-2 contract, global-only load path, payload shape, trust gate,
  `${CLAUDE_PLUGIN_ROOT}` not injected — none of them were overturned).
  Recorded 4 extensions and 1 risk: 🔴 hooks now run with the environment
  captured at session start (#39314), async hook execution and MCP tool-call
  support (#37533/#38705/#39296 — async hooks can't be blocked, so every
  guard in this repo stays synchronous), the `SessionEnd` event (#33895) and
  timeout-triggered hook process-tree termination (#37527), removal of
  `codex exec --full-auto` (#36054), sandbox fail-closed behavior and
  Windows ACL failure propagation (#39279).
- docs(AGENTS): wired `avoid-ai-writing` into the §0 routing table. It was
  already listed in README/catalog.json, but **absent from the table that
  actually triggers invocation** — being listed isn't being wired. Also
  specified that it's detect-only and that recipient-specific tone always
  overrides the skill's suggestions.

## [1.2.37] — 2026-08-22

- chore: normalize proof_stage_audit.md to LF, regenerate SHA256SUMS

## [1.2.36] — 2026-08-22

- feat(manuscript-pipeline): add the proof/galley stage audit

## [1.2.35] — 2026-08-22

- feat(avoid-ai-writing): korean-tells.md — strengthens Korean AI-writing-style
  detection (adopted from epoko77-ai/im-not-ai, MIT)

## [1.2.34] — 2026-08-22

- feat(skills): add debugging-loop — a bug-diagnosis discipline that
  establishes a reproduction loop before a hypothesis (adopted from
  mattpocock/skills' diagnosing-bugs, MIT)
- feat(skills): add test-quality — flags 3 kinds of tests that pass without
  actually verifying anything (recomputing the expected value the same way
  the implementation does, internal coupling, batch-written-in-advance) and
  seam selection (adopted from mattpocock/skills' tdd, MIT)
- feat(code-quality): split review into two axes, Standards / Spec — no
  reordering across axes, fixed comparison baseline, explicit statement when
  no Spec exists (adopted from mattpocock/skills' code-review, MIT)
- feat(skills): add `spec-first-development` and `test-first-development` —
  spec/plan-before-code and test-before-implementation discipline, adapted from
  obra/superpowers (MIT, see `NOTICE.md`). Routed from `AGENTS.md` §0.
- feat(skills): add spec-driven-research-dev — a 4-stage spec flow
  (specify→plan→tasks→implement), adapted from github/spec-kit (MIT).
  Rewritten for research code (reflects units, failure policy, numeric
  provenance SSOT)
- feat(skills): add `analysis-code-testing` — pytest patterns for analysis code
  (known-answer tests, golden-file regression, float tolerances, seeded
  reproducibility). Adapted from wshobson/agents `python-testing-patterns` (MIT);
  web-service patterns (HTTP mocks, retries, token expiry) dropped.
- feat(skills): add `data-quality-checks` — six-dimension structural check on a
  raw table before analysis. Adapted from wshobson/agents
  `data-quality-frameworks` (MIT); Great Expectations/dbt/warehouse tooling
  replaced with pandas so no extra dependency is required.
- docs(AGENTS): route both skills in §0; record upstream attribution in NOTICE.md.

## [1.2.33] — 2026-08-21

- fix(connectors): preserve real newlines in asana add-comment --html

## [1.2.32] — 2026-08-21

- fix(connectors): fixed a defect where asana add-comment --html was
  demoting real newlines to `&#10;` literals (#4) — now preserves actual
  LF, auto-restores legacy `&#10;` input, and added a re-fetch
  self-verification after posting

## [1.2.31] — 2026-08-17

- fix(web-scraping): resolve CI failures from doctor gate

## [1.2.30] — 2026-08-17

- chore: bump version to 1.2.29 for web-scraping skill addition

## [1.2.29] — 2026-08-17

- feat(skills): add web-scraping skill (lab-shared)

## [1.2.28] — 2026-08-16

- feat(connectors): add Google Calendar and Sheets, stdlib-only

## [1.2.27] — 2026-08-16

- fix(skills): replace retired TeamCreate API with role-based delegation

## [1.2.26] — 2026-08-16

- fix(routing): drop connector-silent Notion steering; gate the class

## [1.2.25] — 2026-08-16

- test(connectors): offline regression suite; unify dry-run token gating

## [1.2.24] — 2026-08-16

- docs(office): route office work per-agent; Codex ships its own bundle

## [1.2.23] — 2026-08-16

- docs(codex): correct stale Codex capability claims; install to ~/.codex/skills

## [1.2.22] — 2026-08-13

- docs: sync remaining skill-count references after avoid-ai-writing add

## [1.2.21] — 2026-08-13

- docs: sync QUICKSTART.md skill counts (28->29 shipped, 32->33 cataloged)

## [1.2.20] — 2026-08-13

- fix: normalize avoid-ai-writing to LF, update skill count to 29

## [1.2.19] — 2026-08-13

- feat(skills): add avoid-ai-writing skill

## [1.2.18] — 2026-08-10

- feat(doctor): detect credentials.json / secrets.json divergence

## [1.2.17] — 2026-08-10

- merge: origin/main (token-guide doc updates, unrelated to feedback-log work)

## [1.2.16] — 2026-08-10

- feat(feedback): auto-assign GitHub issues to the finder, not the maintainer

## [1.2.15] — 2026-08-10

- docs: document MCP preview-confirm silent-failure trap + account-wide connector scope

## [1.2.14] — 2026-08-10

- docs: dedupe repeated CHANGELOG entries from post-commit hook firing during rebase conflict resolution

## [1.2.13] — 2026-08-10

- fix: F2 preprint test reports SKIP (not FAIL) when OA host rate-limits every retry

## [1.2.8] — 2026-08-10

- refactor: replace install.py's hardcoded doctor timeout with doctor.py's own constant

## [1.2.7] — 2026-08-10

- feat: hook-wiring integrity gate + auto doctor run after install

## [1.2.6] — 2026-08-10

- feat(connectors): add register_token.py, close the token-onboarding gap

## [1.2.5] — 2026-08-10

- feat: detect whether hooks can actually run before assuming they do

## [1.2.4] — 2026-08-10

- docs: add Chrome-MCP-assisted token issuance guide

## [1.2.3] — 2026-08-10

- feat(connectors): add --sort to notion_db_connector query

## [1.2.2] — 2026-08-10

- feat: auto version-bump on every commit (post-commit hook)

## [1.2.1] — 2026-08-09

- docs: make REST connectors the default over MCP for mail/GitHub/Asana/Notion

## [1.2.0] — 2026-07-23

### Added
- **Turned 3 rule categories that had existed only as documentation into
  executable gates.** These had been judged as "the cost of a mistake is low
  enough that documentation suffices," but all three turned out to be
  mechanically checkable. Reframed the criterion from that judgment to
  **"is this hard to undo?" → "can this be written as a checkable rule?"**:
  - **`scripts/doi_verify.py`** — checks against both CrossRef and OpenAlex
    whether a DOI **actually exists**. Catches fabricated DOIs (exit 2),
    retracted papers, and bibliographic mismatches. `AGENTS.md` §8 instructed
    "hallucinated DOIs are dangerous, cross-verify" while **no tool existed
    to run that verification** — an AI could just say "verified" and that
    was that. **A network failure is now reported as UNVERIFIED, not a
    pass** ("couldn't check" and "checked and it's fine" are different
    claims).
  - **`skills/stats-workflow/scripts/assumption_check.py`** — actually runs
    normality (Shapiro-Wilk / D'Agostino depending on n) and equal-variance
    (Levene) tests, and **names which test to use** per SKILL.md's decision
    tree. With `--run`, outputs APA 7th-edition formatting plus effect size.
    Previously this was just a code snippet inside SKILL.md, so "assumptions
    checked" was never actually verified.
  - **`skills/manuscript-pipeline/scripts/body_typo_lint.py`** — the
    `academic-term-rules` SKILL.md §12a **explicitly pointed at this file as
    the enforcement side, and it didn't exist.** Unit/notation typos
    (`50ul`, `n=3`, `NAD+`) are separated into AUTO-FIXABLE; punctuation
    stuck to text is REVIEW-ONLY (a human judges only after the
    abbreviation/URL/decimal-point whitelist has been applied).
- **`tests/test_agents_routing.py`, `test_body_typo_lint.py`, `test_doi_verify.py`,
  `test_assumption_check.py`** — regression tests for the gates above.
  `doctor.py` now **auto-runs all 4 self-tests** (the `Toolkit self-tests`
  check). If a gate quietly breaks, every deliverable it was supposed to
  guard goes out unverified.
- **`AGENTS.md` §0 routing table** — nails down "which request → which skill
  → which verification" as a table. Previously the operating principles
  (§1–7) and the verification paths (§8) existed, but **there was no entry
  map**, so an agent picked skills arbitrarily. Every path ends in a gate,
  and a gate marked 🔒 is enforced by script (no eyeballing it, and no
  weakening the check just to get it to pass). `CLAUDE.md` was updated to
  point at this table first.
- **`docs/10_full_workflow_map.md`** — a human-facing structure diagram. The
  three layers (rules → skills → verification), the actual flow when a
  request comes in, **the criterion for what gets mechanically enforced vs.
  what's just documented guidance** ("is this hard to undo if it's wrong"),
  and what to say when the AI has lost its way.
- **`docs/09_working_on_a_remote_server.md`** — how to work on a shared lab
  server / HPC / cloud instance. VS Code Remote-SSH, SSH+CLI, keeping a job
  running across a dropped connection via tmux/nohup, retrieving results,
  SLURM caveats, security practices. Does not include personal connection
  info (users fill that in themselves).
- **Added a VS Code extension path to the install guide** — previously only
  the desktop app and terminal were documented. Now all three paths are
  explained side by side with a "which one are you" selection table, and it
  notes that all three share `~/.claude/skills/`.
- **`tests/test_agents_routing.py`** — checks that every skill/script the §0
  routing table points to actually exists (40 targets checked). Wired into
  `doctor.py` to run automatically. If the table points at something that
  doesn't exist, an agent either fails or plausibly fabricates a substitute,
  so this check guards the part of the docs that must never be the first
  thing to silently break.
- **Added 14 skills** (21 → **35**). Selected only skills that passed a
  distribution-fitness check (no PII / no private infrastructure) from the
  internal skill repo:
  - documents/presentations — `pptx`, `journal-presentation-maker`
  - figures — `markdown-mermaid-writing`, `generate-image`
  - data/stats — `statsmodels`, `conda-env-manager`, `get-available-resources`
  - experiments — `experiment-hub`
  - literature/search — `parallel-web`, `perplexity-search`
  - papers — `research-grants`
  - dev discipline — `code-quality`, `git-workflow-manager`, `skill-developer`
- Added a table to the README describing **the distribution package's own
  layout** (install/config/hooks/scripts/docs/doctor). The existing README
  described these folders as an "empty scaffold," but they were in fact all
  populated.
- **6 manuscript editing/QC tools** (`docx` skill, Windows/Word COM):
  - `word_live_edit.py` — **live-edits a document the user already has open
    in Word.** Attaches to the already-open instance so there's no file-lock
    conflict, and the screen scrolls to the edit point.
  - `word_com_ops.py` — accepts tracked changes, find-replace across run
    boundaries, caption replacement, table moves, figure/table insertion.
  - `manuscript_text.py` — **extracts text from a docx that has tracked
    changes.** python-docx silently drops `<w:ins>` content, which makes a
    perfectly intact manuscript look like it has "truncated sentences." This
    tool routes through pandoc's `--track-changes` path to prevent that
    illusion (MUST 5b).
  - `manuscript_ref_order.py` — diagnoses Figure/Table citation order.
    Reports a "numbering-order violation" **broken down** into missing
    citation / phantom citation with no caption / draft state.
  - `figure_caption_check.py` — caption↔figure consistency QC,
    `endnote_biblio_check.py` — bibliography completeness check.
- **`scripts/ref_fetch.py`** — collects bibliographic info and open-access
  (OA) PDFs from a list of DOIs. **Cross-verifies against both** CrossRef
  and OpenAlex and records any mismatch in the report (never silently picks
  one). Resolves OA links via Unpaywall/OpenAlex, and **fetches only what is
  openly available under open access**. No API key required, reuses the
  `ref_cache_manager.py` cache, supports BibTeX export.
- **2 regression tests** (`tests/`) — `test_doctor_sentinel.py` (21 secret-
  detection cases), `test_skill_references.py` (407 references checked).
  Both wired into `doctor.py` to run automatically.

### Fixed
- **Restored 2 scripts that had gone missing from the distribution** — found
  by diffing file-by-file against the internal repo.
  - `skills/publication-figures/scripts/lab_plot.py` (487 lines) — HPLC/
    kinetic/dose-response/BO-surface/Pareto routine plotting. SKILL.md
    referenced this file, and it was missing — **the docs had wrongly been
    edited to say "not a bundled script."** It actually existed and had
    just been dropped during packaging. Sanitized the demo data (only the
    unpublished research name, replaced with a generic sugar name) before
    restoring it, and confirmed with `--demo` that all 18 figures generate
    correctly.
  - `skills/research-lookup/scripts/manuscript_packet.py` (754 lines, no
    PII) — DOI/PMID extraction, evidence weighting, publication-type
    classification helpers.
  > Lesson: when a file a doc points to is missing, **first check whether it
  > exists upstream and was dropped** — editing the docs is only the right
  > move after you've confirmed it's also missing upstream.
- **The `NAD⁺` correction rule was barely catching real sentences** —
  `academic-term-rules` §12's `\bNAD\+\b` doesn't match when `+` (a
  non-word character) is followed by whitespace or punctuation, as in
  `NAD+ regeneration`, because the trailing `\b` boundary never fires
  (measured). This meant it missed nearly every form actually seen in
  manuscripts and only caught the dead pattern `NAD+regeneration`. Removed
  the trailing `\b` and fixed the ordering so `NADP+` is substituted first,
  correcting **both SKILL.md and the implementation** (the hyphenated
  modifier form `NAD+-dependent` is also included as a correction target,
  since §3 says the superscript is correct there too). Added the 6 missed
  forms to the regression tests.

A full scan found and resolved **40 dead references** (things that would
fail exactly as documented if a user followed the instructions).
`tests/test_skill_references.py` now checks 407 references, and `doctor.py`
runs this check automatically.

- **28 places instructing execution of a file that doesn't exist** — the
  worst case was `paper-extract`, whose docs entirely depended on
  `scripts/extract_paper_assets.py`, which **didn't exist at all — the
  whole skill was inoperable.** Implemented that script from scratch (PDF/
  docx → table xlsx + figure PNGs + body markdown + extraction report). The
  rest were corrected to point at real files/skills: 21 in `research-grants`,
  plus references in `research-search`, `journal-presentation-maker`,
  `parallel-web`, `publication-figures`, and others.
- **12 instructions to use a skill that doesn't exist** —
  `scientific-schematics`, `diagram-design`, `gget`, `citation-management`,
  `hypothesis-generation`, `scientific-critical-thinking`,
  `scientific-writing`, `agent-guardian`, `infographics`, `pptx-reviewer`,
  and others. All mapped to skills that actually exist in the distribution.
- **6 case-mismatched file references in the `pdf` skill** — the actual
  files are `reference.md` / `forms.md`, but were referenced as
  `REFERENCE.md` / `FORMS.md`. This reference fails on case-sensitive
  Linux/WSL environments.
- **37 scripts that died on first output on a Windows console (cp949)** —
  scripts printing Korean text or em-dashes, including `doctor.py` and
  `install/install.py`, terminated immediately with a `UnicodeEncodeError`.
  Resolved by adding a UTF-8 stdout guard (verified with
  `PYTHONIOENCODING=cp949`). Library modules that are only imported and
  used elsewhere were excluded, since they shouldn't mutate their caller's
  stdout.
- Replaced the stack trace `manuscript_ref_order.py` produced when run
  with no arguments with a usage message.

### Changed
- **Updated 4 existing skills to their latest internal versions** (merged
  after sanitization):
  - `academic-term-rules` 417→596 lines — citation-order diagnosis (§7c:
    "missing citation" and "out-of-order citation" are different problems),
    other QC-rule improvements
  - `endnote-citation-injection` 490→784 lines — pre-INSERT DOI lookup to
    prevent duplicate insertion, orphan-citation recovery, the trap where an
    unset reference_type silently breaks the bibliography, journal-name
    normalization, safe UPDATE procedure for the shared library
  - `scientific-validation` 157→183 lines — "the reproduction process must
    not itself cause a side effect" (Axis 4a): a real case where a guard was
    validated by actually invoking the real send path it was meant to
    check; the absence of a name doesn't mean the absence of the capability
  - `research-lookup` — strengthened routing table
- Regenerated `config/catalog.json` as v1.2.0 — registered the 14 new
  skills, re-measured `size_kb` for every skill, strengthened the presets
  (`paper-writing`, `literature`, `data-figures`).
- **Strengthened `doctor.py`'s secret check (SENTINEL)** — fixed 2 real
  holes:
  1. It was checking **only the first match** per file. If the top of a
     file is a placeholder, a real key further down goes entirely
     unnoticed. Changed to iterate over all matches; doing so immediately
     surfaced a file that had previously been hidden this way.
  2. Placeholder detection was **substring-based**, so a real key value
     that happened to contain a string like `project1` or `key-here` passed
     through unchecked (demonstrated in adversarial verification). Changed
     to split the value into words and only classify it as a placeholder
     when **every word** is filler.
  3. The defensive logic added while fixing ② **created 2 new holes**
     (caught in a second round of adversarial verification). A
     purely-numeric value (e.g. a 30-digit number) was unconditionally
     treated as filler and passed through, and anything in
     SCREAMING_SNAKE_CASE was read as an environment-variable name and
     passed through even when an opaque hex token was appended to it.
     Narrowed this so only short numbers (`key1`, `v2`) count as filler,
     and an environment-variable name is accepted only when **every
     segment is a pure English word**.
     (See `tests/test_doctor_sentinel.py`'s MUST_BLOCK list for the
     specific bypass strings — leaving key-shaped strings in the docs would
     let the scanner catch itself.)
  To prove this wasn't loosened just to make it pass, added bidirectional
  cases to `tests/test_doctor_sentinel.py` — 18 real-key variants
  (including the 11 bypasses that had gotten through) that **must always be
  blocked**, and 13 placeholder variants that **must always pass**. All 31
  cases pass.

  > Lesson: an exception added to reduce false positives becomes a bypass
  > route by construction. When touching this check, always run the test
  > above, and for every new exception, devise one "real key that this
  > exception would let through" and add it to MUST_BLOCK.
- Regenerated `SHA256SUMS` and pinned the generation procedure to
  `scripts/make_checksums.py` (previously the regeneration method existed
  nowhere in the package).

### Notes
- Internal skills **excluded** as unfit for distribution:
  `web-scraping` (cache held many real names/emails),
  `system-inspector` (private-infrastructure-only),
  `kinetic-bo-pipeline`/`cascade-scheme-renderer` (unpublished research
  paths are the body of the skill itself).

## [1.1.0] — 2026-07-15

### Changed
- **Removed 6 unused/duplicate skills** (reflecting the internal skill
  repo's 2026-07-14 cleanup):
  `research-assistant` (duplicates research-search, risk of delegation
  loops), `academic-paper-reviewer` (duplicates adversarial-verifier),
  `bgpt-paper-search` / `bioservices` (replaceable by Claude Science /
  internal-only), `biopython` (a pure library wrapper). Skills 27 → **21**.

### Notes
- Regenerated `config/catalog.json` and `SHA256SUMS` to match the skill
  removal.

## [1.0.0] — 2026-07-03

Initial release for internal lab distribution. Aimed at beginners (lab
members using an AI agent for the first time), assembled as an all-in-one
scientific research toolkit usable directly on top of Claude Code (+Codex).

### Added
- **27 skills** — literature search/writing (literature-review,
  manuscript-pipeline, paper-extract, research-search, etc.), molecular
  biology (primer-design, biopython, bioservices), figures/visualization
  (publication-figures), statistics (stats-workflow), documents (docx,
  xlsx, pdf, markitdown), academic verification (academic-paper-reviewer,
  scholar-evaluation, scientific-validation), terminology rules
  (academic-term-rules), conference posters (conference-poster), and more.
- **Research tool scripts** — hplc_parser, primer_structure_check,
  variant_filter, jcr_batch_verify, ref_cache_manager, excel_formula_check,
  fetch_public_vector, advanced_wsl.
- **Enforced QC lint tools** — figure_lint (figures), nomenclature_lint /
  ai_tells_lint / numeric_consistency_check (manuscripts), visual_check
  (docx). Regression-prevention gates for deliverables.
- **5 beginner docs** — `docs/00_getting_started`,
  `01_installation_and_first_command`, `02_api_and_mcp`,
  `03_tokens_and_cost`, `04_giving_an_ai_rules`, plus `README` and
  `QUICKSTART`.
- **Generalized AGENTS.md** — shared agent instructions for Claude Code /
  Codex (all private infrastructure and personal paths removed).
- **doctor.py** — distribution-integrity/environment check script
  (PASS/FAIL report).
- **SHA256SUMS** — hash of every file (for copy-integrity verification).
- **.distignore** — distribution-exclusion rules.

### Security
- Fully sanitized unpublished research names, real-name paths, institution
  affiliations, emails, and secrets references, replacing them with
  placeholders. Passed 2 rounds of adversarial verification.
- Dual-PC delegation, financial, personal-MEMORY, `.git`, and
  private-infrastructure-related assets are entirely excluded from the
  distribution.

### Notes
- Designed to run on a monthly subscription alone (Claude Pro/Max, ChatGPT
  Plus or higher), no API key required.
- Core configuration needs no WSL. Assumes an all-in-one manual
  distribution (USB, etc.) as the default delivery method.
