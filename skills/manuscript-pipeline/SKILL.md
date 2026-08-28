---
name: manuscript-pipeline
description: End-to-end academic manuscript pipeline — structure → write → self-review → polish → proof. Covers IMRAD drafting, journal-specific styles (Nature/Angewandte/Elsevier/ACS), peer-review checklist, cover letter generation, EndNote citation insertion, and the post-acceptance proof/galley audit (proof, page proof, 교정지, publisher correction request on a 24-48h deadline). Use when producing or editing a manuscript for submission, or when checking a typeset proof before approving it. For searching/synthesizing prior literature use literature-review; for brainstorming or discussing results use research-ideation.
---

# Manuscript Pipeline — Meta-Skill

Integrates manuscript drafting + scientific writing + peer review + revision response + safe DOCX edit + remote delegation. This SKILL.md is a **router**; detailed protocols live in `references/` (progressive disclosure).

> 🔴 **Read this first**: before starting manuscript work (drafting, numbers,
> figures, citations), check the five declarations in
> **[`references/manuscript_ssot_manifesto.md`](references/manuscript_ssot_manifesto.md)**
> first — the principle that every number, citation, and notation comes from
> exactly one SSOT and is never hand-copied. This is central to keeping the
> manuscript trustworthy.


> **Life-science content in a delegated call.** When a MAP-stage or verification
> sub-question touches molecular biology (enzyme mechanism, mutagenesis, primer
> or sequence content), keep it **one subject per agent call**. A bundled prompt
> of this kind can be refused whole by a provider-side classifier before any
> model reads it, and the dead branch returns empty — which reads as "no
> findings" rather than "blocked". If a sub-agent returns empty, check its error
> text before believing the emptiness. See `AGENTS.md` §6b.

## Trigger

Use when: drafting a manuscript, writing a section (Intro/Methods/Results/Discussion), self-reviewing before submission, writing a cover letter or reviewer response, parsing reviewer comments, interpreting results, editing an existing DOCX, or delegating long edits to a background/remote worker.

## Execution Method

All tasks run as a **subagent (Agent tool)** — do not run directly. For a **single docx** touched by multiple agents, follow **map-reduce** (analysis parallel + edit serial): see `references/docx_multiagent_workflow.md`. A useful routing heuristic: 3+ files / 100+ lines / 3+ steps → spin up a small agent team with a lead.

## Modes (router)

Eight modes. Pick one based on the request:

| Mode | Trigger keywords | Output | Detail |
|---|---|---|---|
| `outline` | "구조 잡아줘" (structure this), "outline", target journal | Section-by-section bullet outline | Phase 1 |
| `write` | "Introduction 써줘" (write the Introduction), "Methods 작성" (draft the Methods) | IMRAD prose, full paragraphs | Phase 2 |
| `review` / `peer-review` | "검토해줘" (review this), "self-review", "피어리뷰" (peer review), "외부 리뷰어 시뮬레이션" (simulate an outside reviewer), "EIC 관점" (from the EIC's perspective) | Numbered findings + severity (on request, review by rotating through multiple perspectives — editor-in-chief, peer reviewer, devil's advocate, etc.) | Phase 3 |
| `discuss` | "결과 해석" (interpret the results), "Discussion 보강" (strengthen the Discussion), "이 결과 어떻게 봐야" (how should I read this result) | 7-step Discussion + alt interpretations | `references/templates.md` |
| `revise-response` | "리비전 대응" (handle the revision), "reviewer comment 답변" (respond to reviewer comments) | Point-by-point JSON + Word table + letter | `references/templates.md` |
| `docx-edit` | existing file path passed, "이 docx 수정" (edit this docx), "본문 교정" (proofread the body text), "tracked change 삽입" (insert a tracked change) | Edited DOCX + changelog | docx skill + Phase 4 |
| `academic-qc` | "학술 표기 규칙 전수 교정" (full sweep of academic-notation rules), "표기 통일 전수" (unify notation throughout), "명명법 일괄 적용" (apply nomenclature rules in bulk) | Per-step corrected draft + final merged DOCX | `references/academic_qc_rules.md` |
| `proof-audit` | "proof", "galley", "교정지" (proof/galley), "proof 확인" (check the proof), "page proof", a publisher correction request with a 24-48h reply deadline | 3-way classification (must-fix / recommended / observation) + the replacement string for each item | `references/proof_stage_audit.md` |

**Router disambiguation** (was a bug — both used to match "학술 규칙 수정" [fix academic-notation rules]):
- `academic-qc` = **full/bulk** notation-rule correction (systematic sweep of species names, enzymes, abbreviations, units — produces step0~6 output).
- `docx-edit` = editing text/structure at a **specific location** (revising a given sentence, table, or citation). Also use docx-edit when touching only part of the academic-notation rules.
- The notation rules themselves are always defined by the `academic-term-rules` skill (SSOT).
- `proof-audit` = the stage **after publication is confirmed, right before printing**. What separates it from `academic-qc`/`review` is "can the manuscript still be changed?" — a proof has no SSOT access and can't be undone, so instead of cross-checking the manuscript against raw data, it checks whether **the printed values reproduce each other**. Before submission, use `academic-qc`; while awaiting print approval, use `proof-audit`.

## Pipeline Phases

```
1. Structure & Outline → 2. Section Writing (IMRAD) → 3. Self-Review (+ Consistency Gate)
   → 4. Polish & Submit Prep → 5. Revision Response (post-review)
   → 6. Proof / Galley Audit (post-acceptance, irreversible — references/proof_stage_audit.md)
```

---

## Phase 1 — Structure & Outline

1. Ask: target journal, word limit, figure count
2. Read journal author guidelines (see Journal Style Reference)
3. Generate section-by-section outline with key points (bullet form)
4. Get user approval before writing

**Key questions:** central claim in one sentence? the 3 key figures? what gap does this fill?

## Phase 2 — Section Writing

**Rules (all sections):** full paragraphs only (never bullets in manuscript body); active voice preferred; define abbreviations on first use; every figure/table cited in order; no orphan references. Writing-style detail (declarative sentences, no em-dash clauses, sentence-level citations) → `references/writing_style.md`.

### IMRAD Guide
- **Introduction**: broad context → gap → prior work + limitations → this study's approach → findings → significance
- **Methods**: subheadings per procedure; enough detail to reproduce; statistics last
- **Results**: figures first then interpretation; one message per paragraph; no implications here
- **Discussion**: restate finding (no new data) → literature (agreements then discrepancies) → mechanism → limitations → future → conclusion

## Phase 3 — Self-Review

### Scientific Validity
Central claim supported by all key figures · controls described · stats correct for data type (→ `stats-workflow`) · effect sizes + CIs · N consistent · **Consistency Gate** (below).

### Reporting & Format
ARRIVE/CONSORT/STROBE as applicable · abbreviations defined on first use · figure/table numbers sequential and all cited · supplementary items referenced · no bullets in body · word limit · journal-style references · author contributions + conflicts declared.

### Consistency Gate (automated — run before Phase 4)
Auto-flags (a) same labelled quantity (sEF, cEF, titer, yield, MPSP, ee…) carrying conflicting values across body / tables / figure CSVs — the single-source-of-truth check that catches conflicting-value incidents (e.g. one metric reported as 1.8 in the body but 2.0 in a table) — and (b) floats cited-without-caption or captioned-but-never-cited. Exit 0 = PASS; non-zero blocks Phase 4.

```bash
python scripts/numeric_consistency_check.py \
    MANUSCRIPT.docx --csv FIGURES_DIR --json review.json
# Windows python: pass C:/... paths, not /c/... ; rerun until RESULT: PASS
```
Designate one canonical rawdata file and reconcile every flagged conflict to it — never silently "fix" by editing one site. Tune `--tol` (default 0.02).

## Phase 4 — Polish & Submit Prep
Cover letter + reviewer-response templates → `references/templates.md`. **Before declaring the draft "final": run the 30-item QC checklist** (`references/manuscript_qc_checklist.md`) and **figure provenance** (below). Citations/EndNote → see EndNote Integration.

## Phase 5 — Revision Response (`revise-response`)
Parse → classify → point-by-point draft → tone policy → JSON/table/letter. Full protocol + IJBM/Elsevier letter format → `references/templates.md`.

---

## EndNote Citation Integration

DOI-based DB search → consistency check → generate a RIS entry if absent → insert the citation. For a **single DOI or a handful**, use the EndNote helper CLI's `doi-resolve` (provided separately); for the detailed workflow, output interpretation, comment format, and rules, see `references/endnote_integration.md`. For **bulk batch conversion (10+, needs hallucination verification)**, use the `endnote-citation-injection` skill. For the **Track Changes XML insertion pattern**, see the docx skill (not in this repo — see docs/12). Verifying the DOI against CrossRef before INSERT is mandatory.

## DOCX Safe Editing
For DOCX editing (preserving ZIP integrity, incremental_edit sessions, 4-stage preflight + Word COM ground-truth, tracked changes, comment anchors), **the docx skill is the single source of truth (SSOT)**. Never use python-docx's `Document().save()`. Follow the docx skill's protocol as-is for manuscript work.

## Academic Notation
The SSOT for every notation rule — species names, enzymes, coenzymes, units, kinetics, captions, dashes, superscripts, and so on — is the **`academic-term-rules` skill** (§1~14). `academic-qc` mode maps those rules onto a full docx sweep → `references/academic_qc_rules.md`. Domain abbreviations → `references/domain_abbrev_registry.md`.

## Comment Mode
Word-comment prefix tag scheme ([STRUCTURE]/[FLOW]/[NOVELTY]/[ABBREV]/[NUMBERING]… + [Critical]) → `references/comment_tags.md`. State the author name explicitly (e.g. Claude). Comment anchor id = existing max + 1; insert commentRangeStart at a run boundary directly under `w:p`.

## Track Changes & Comments (use actively)
Edits that need user review default to **tracked changes (`<w:ins>`/`<w:del>`, author="Claude") + a note recording the rationale**. Edit directly only for mechanical, settled corrections. No concurrent editing (corrupts OOXML). Details → `references/docx_multiagent_workflow.md`.

---

## Working-Copy Editing (large / long edits)

For a long DOCX edit, a full review, or editing multiple sections at once, never touch the original directly — work in a **working copy** and replace the original only after approval.

```
original.docx (read-only)  ──copy──►  working.docx (edit here)
                                          │  edit + record changelog
   original.docx  ◄── merge (after user approval) ──┘
```

### Rules
1. Edit only `working.docx`, never the original in place. 2. After every meaningful change, append to a changelog (section / before / after / rationale). 3. Use the docx-skill safe-edit protocol for all writes. 4. Single docx + multiple agents → **map-reduce (edit serial)**, no 3-way merge. 5. User reviews the working copy in Word and accepts/rejects manually before merge.

**When to use:** DOCX >500 KB, many tracked changes, or edit expected to take a while. **Skip when:** one-shot small edit (<5 substitutions) or real-time same-window review.

---

## Logging & Provenance (recommended)

- **Decision Log**: record research/edit decisions in a single-source-of-truth location (a `Decision_Log/` folder you choose) when doing structural edits (academic-qc / docx-edit / revise-response).
- **changelog**: every edit records a backup filename (`references/backup_naming.md`) + change summary.
- **Figure provenance** (before submission): run `python scripts/figure_provenance.py <figures_root>` (path relative to this skill) → record each figure's raw data + producing-script path. Confirm output by file existence, not mtime (cloud-synced folders report stale mtimes).
- **rawdata single source of truth**: numbers in text / tables / figures must trace back to a single rawdata file.
- 🔴 **Figure files map to manuscript slots by CAPTION, never by filename** — read the
  sidecar (`<stem>.caption.txt`) or open the picture. A gallery `Fig6.png` whose own
  sidecar caption said "Fig. 7" once overwrote the manuscript's correct Fig. 6. Byte-identity
  and aspect-ratio checks both passed on it, because they answer "is this image
  well-formed", not "is this the right image". Detail: `publication-figures`
  §Identifying a figure file.
- 🔴 **After any figure replacement or resize, re-measure figure/caption pagination**
  (`scripts/figure_caption_pagination.py --before <original>`). Equal page counts are
  not evidence of safety — one measured case split a caption off its figure while the
  document stayed the same length. Fix a split by shrinking the figure's WIDTH, never
  by dropping lettering below the journal's minimum (typically 7 pt).

## External tooling integration

| Tool | Purpose | When |
|---|---|---|
| `scripts/reference_validator.py` | Verifies EndNote fields + DOI hallucination (404=fabricated DOI, network unreachable=cannot verify, detects real-DOI-but-wrong-citation). `--crossref` is ON by default; turn it off with `--no-crossref` | reference QC / final-draft gate |
| `scripts/nomenclature_lint.py` | Read-only nomenclature/notation lint (safe subset of R1~R15: R2 abbreviations, R5 units, en-dash, species names). Never auto-fixes | notation QC, locating issues before an academic-qc correction pass |
| `scripts/ai_tells_lint.py` | Diagnoses AI-writing anti-patterns (A1~A10). Advisory (exit 0), never auto-fixes | self-review / voice check |
| `scripts/renumber_figures.py` | Renumbers Figure/Table citation order (2-stage token scheme, same Main↔SI map, `--dry-run` by default · `--apply` · `--tracked`) | when reordering figures |
| `scripts/figure_provenance.py` | Walks the figure folder → PROVENANCE.md + MANIFEST.md | right before submitting figures |
| `scripts/figure_caption_pagination.py` | Measures via Word re-typesetting **whether a figure and its caption land on the same page**. `--before <original>` distinguishes a pre-existing split from a newly introduced one. Read-only (never saves). exit 1 = new split. 🔴 A different axis from `figure_caption_check.py`'s C7 — C7 reads an explicit page break in the XML, while this catches the case where a figure simply grew large enough to force a split (which leaves no trace in the XML) | **after replacing or resizing a figure** |
| `scripts/numeric_consistency_check.py` | Numeric/citation consistency gate | before closing out Phase 3 |

> To insert comments/Track Changes into a docx, use the docx skill's (not in this repo — see docs/12) `inject_comments_from_csv.py`/`comment.py` (dynamic rStyle matching) — this skill has no separate comment-insertion script of its own. Markdown→Word conversion also routes through the docx skill (not in this repo — see docs/12).

Feed the output JSON into the changelog via `manuscript_workdir.py record`.

## Journal Style Reference

| Journal | Style | Word limit | Figures |
|---|---|---|---|
| Nature | Author-date | 3000 (Letter) | 4 |
| Angewandte | Numbered | 5000 | 5 |
| ACS journals | Numbered | Varies | Varies |
| Elsevier | Numbered | Varies | Unlimited |

## references/ index
- `endnote_integration.md` — single-DOI citation workflow
- `academic_qc_rules.md` — academic-qc mode rules R1~R15 (R14 US spelling, R15 *E*-factor) + the sweep code
- `comment_tags.md` — Word comment prefix taxonomy
- `domain_abbrev_registry.md` — domain abbreviation standards (example table)
- `backup_naming.md` — working.docx backup filename catalog
- `templates.md` — cover letter / reviewer response / revise-response / discuss
- `writing_style.md` — sentence/heading/citation style rules
- `docx_multiagent_workflow.md` — map-reduce for a single docx (parallel analysis + serial edit)
- `manuscript_qc_checklist.md` — the 30-item full QC for a "final" draft

## Related Skills
`academic-term-rules` (notation SSOT) · `docx` (safe-editing SSOT) · `endnote-citation-injection` (bulk citations) · `literature-review` (prior literature) · `publication-figures` (figures) · `research-ideation` (interpretation/discussion).

## Replaces
- `deprecated/manuscript-writer` — full manuscript writing with research integration
- `deprecated/scientific-writing` — scientific prose style, paragraph structure
