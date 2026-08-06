---
name: manuscript-pipeline
description: End-to-end academic manuscript pipeline — structure → write → self-review → polish. Covers IMRAD drafting, journal-specific styles (Nature/Angewandte/Elsevier/ACS), peer-review checklist, cover letter generation, and EndNote citation insertion. Use when producing or editing a manuscript for submission. For searching/synthesizing prior literature use literature-review; for brainstorming or discussing results use research-ideation.
---

# Manuscript Pipeline — Meta-Skill

Integrates manuscript drafting + scientific writing + peer review + revision response + safe DOCX edit + remote delegation. This SKILL.md is a **router**; detailed protocols live in `references/` (progressive disclosure).

> 🔴 **먼저 읽어라**: 원고 작업(작성·수치·figure·인용)을 시작하기 전에
> **[`references/manuscript_ssot_manifesto.md`](references/manuscript_ssot_manifesto.md)** 의
> 다섯 선언을 먼저 확인한다 — 모든 숫자·인용·표기는 하나의 SSOT에서만 나오고 손으로
> 베끼지 않는다는 원칙. 논문 신뢰를 지키는 핵심이다.

## Trigger

Use when: drafting a manuscript, writing a section (Intro/Methods/Results/Discussion), self-reviewing before submission, writing a cover letter or reviewer response, parsing reviewer comments, interpreting results, editing an existing DOCX, or delegating long edits to a background/remote worker.

## Execution Method

All tasks run as a **subagent (Agent tool)** — do not run directly. For a **single docx** touched by multiple agents, follow **map-reduce** (analysis parallel + edit serial): see `references/docx_multiagent_workflow.md`. A useful routing heuristic: 3+ files / 100+ lines / 3+ steps → spin up a small agent team with a lead.

## Modes (router)

Eight modes. Pick one based on the request:

| Mode | Trigger keywords | Output | Detail |
|---|---|---|---|
| `outline` | "구조 잡아줘", "outline", target journal | Section-by-section bullet outline | Phase 1 |
| `write` | "Introduction 써줘", "Methods 작성" | IMRAD prose, full paragraphs | Phase 2 |
| `review` / `peer-review` | "검토해줘", "self-review", "피어리뷰", "외부 리뷰어 시뮬레이션", "EIC 관점" | Numbered findings + severity (요청 시 편집장/동료심사자/devil's advocate 등 여러 관점을 번갈아 적용해 심사) | Phase 3 |
| `discuss` | "결과 해석", "Discussion 보강", "이 결과 어떻게 봐야" | 7-step Discussion + alt interpretations | `references/templates.md` |
| `revise-response` | "리비전 대응", "reviewer comment 답변" | Point-by-point JSON + Word table + letter | `references/templates.md` |
| `docx-edit` | existing file path passed, "이 docx 수정", "본문 교정", "tracked change 삽입" | Edited DOCX + changelog | docx skill + Phase 4 |
| `academic-qc` | "학술 표기 규칙 전수 교정", "표기 통일 전수", "명명법 일괄 적용" | step별 교정본 + 최종 통합 DOCX | `references/academic_qc_rules.md` |

**Router disambiguation** (was a bug — both matched "학술 규칙 수정"):
- `academic-qc` = **전수/일괄** 표기 규칙 교정 (종명·효소·약어·단위 systematic sweep, step0~6 산출).
- `docx-edit` = **특정 위치** 텍스트/구조 편집 (지정한 문장·표·인용 수정). 학술 규칙을 일부만 손볼 때도 docx-edit.
- 표기 규칙 정의 자체는 항상 `academic-term-rules` 스킬(SSOT).

## Pipeline Phases

```
1. Structure & Outline → 2. Section Writing (IMRAD) → 3. Self-Review (+ Consistency Gate)
   → 4. Polish & Submit Prep → 5. Revision Response (post-review)
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
Cover letter + reviewer-response templates → `references/templates.md`. **Before declaring "최종본": run the 30-item QC checklist** (`references/manuscript_qc_checklist.md`) and **figure provenance** (below). Citations/EndNote → see EndNote Integration.

## Phase 5 — Revision Response (`revise-response`)
Parse → classify → point-by-point draft → tone policy → JSON/table/letter. Full protocol + IJBM/Elsevier letter format → `references/templates.md`.

---

## EndNote Citation Integration

DOI 기준 DB 검색 → 정합성 확인 → 없으면 RIS 생성 → 인용 삽입. **단일/소수 DOI**는 EndNote helper CLI의 `doi-resolve` (provided separately); 상세 워크플로우·출력 해석·댓글 포맷·규칙 → `references/endnote_integration.md`. **대량 batch 변환(10+ , hallucination 검증)** → `endnote-citation-injection` 스킬. **Track Changes XML 삽입 패턴** → docx 스킬(이 저장소에 없음 — docs/12 참조)(이 저장소에 없음 — docs/12 참조). INSERT 전 CrossRef DOI 검증 필수.

## DOCX Safe Editing
DOCX 편집(ZIP 무결성 보존, incremental_edit 세션, 4단계 preflight + Word COM ground-truth, tracked changes, comment anchor)은 **docx 스킬이 단일 진실원천(SSOT)**. python-docx `Document().save()` 금지. manuscript 작업 시 docx 스킬 프로토콜을 그대로 따른다.

## Academic Notation (표기 규칙)
종명/효소/coenzyme/단위/kinetics/캡션/dash/superscript 등 모든 표기 규칙의 SSOT는 **`academic-term-rules` 스킬** (§1~14). `academic-qc` 모드는 그 규칙을 docx 전수 교정에 매핑 → `references/academic_qc_rules.md`. 도메인 약어 → `references/domain_abbrev_registry.md`.

## Comment Mode
Word 코멘트 prefix 태그 체계([STRUCTURE]/[FLOW]/[NOVELTY]/[ABBREV]/[NUMBERING]… + [Critical]) → `references/comment_tags.md`. 작성자명 명시(예: Claude). comment anchor는 id = 기존 max + 1, commentRangeStart는 `w:p` 직속 run 경계에 삽입.

## Track Changes & Comments (적극 사용)
사용자 검토가 필요한 편집은 **변경 추적(`<w:ins>`/`<w:del>`, author="Claude") + 메모로 근거 기재**가 기본. 기계적·확정 수정만 직접 편집. 동시 편집 금지(OOXML 손상). 상세 → `references/docx_multiagent_workflow.md`.

---

## Working-Copy Editing (large / long edits)

장시간 DOCX 편집·전면 review·여러 섹션 동시 수정 시, 원본을 직접 건드리지 말고 **working copy**에서 작업한 뒤 승인 후에만 원본 교체.

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

## External tooling integration

| Tool | Purpose | When |
|---|---|---|
| `scripts/reference_validator.py` | EndNote 필드 + DOI hallucination 검증 (404=지어낸DOI, 망단절=검증불가, 실재DOI 오인용 탐지). `--crossref` 기본 ON, `--no-crossref`로 끔 | reference QC / 최종본 게이트 |
| `scripts/nomenclature_lint.py` | 명명법/표기 read-only 린트 (R1~R15 안전부분집합: R2약어·R5단위·en-dash·종명). 자동수정 안 함 | 표기 QC, academic-qc 수정 전 위치 파악 |
| `scripts/ai_tells_lint.py` | AI 작문 안티패턴(A1~A10) 진단. advisory(exit 0), 자동수정 안 함 | self-review / voice 점검 |
| `scripts/renumber_figures.py` | Figure/Table 인용순 재번호(2단계 토큰, Main↔SI 동일맵, `--dry-run` 기본·`--apply`·`--tracked`) | figure 순서 재편 시 |
| `scripts/figure_provenance.py` | figure 폴더 순회 → PROVENANCE.md + MANIFEST.md | figure 제출 직전 |
| `scripts/numeric_consistency_check.py` | 수치/인용 정합성 게이트 | Phase 3 종료 전 |

> 코멘트/Track Changes를 docx에 삽입하려면 docx 스킬(이 저장소에 없음 — docs/12 참조)의 `inject_comments_from_csv.py`·`comment.py`(rStyle 동적정합)를 쓴다 — 이 스킬엔 별도 코멘트 삽입 스크립트가 없다. Markdown→Word 변환은 docx 스킬(이 저장소에 없음 — docs/12 참조)을 경유.

출력 JSON을 `manuscript_workdir.py record`로 changelog에 반영.

## Journal Style Reference

| Journal | Style | Word limit | Figures |
|---|---|---|---|
| Nature | Author-date | 3000 (Letter) | 4 |
| Angewandte | Numbered | 5000 | 5 |
| ACS journals | Numbered | Varies | Varies |
| Elsevier | Numbered | Varies | Unlimited |

## references/ index
- `endnote_integration.md` — 단일 DOI 인용 워크플로우
- `academic_qc_rules.md` — academic-qc 모드 규칙 R1~R15 (R14 US spelling, R15 *E*-factor) + 순회 코드
- `comment_tags.md` — Word 코멘트 prefix 분류
- `domain_abbrev_registry.md` — 도메인 약어 표준 (예시 테이블)
- `backup_naming.md` — working.docx backup 파일명 카탈로그
- `templates.md` — cover letter / reviewer response / revise-response / discuss
- `writing_style.md` — 문장·헤딩·인용 스타일 규칙
- `docx_multiagent_workflow.md` — 단일 docx map-reduce (분석 병렬 + 편집 직렬)
- `manuscript_qc_checklist.md` — "최종본" 30항목 전수 QC

## Related Skills
`academic-term-rules` (표기 SSOT) · `docx` (안전편집 SSOT) · `endnote-citation-injection` (대량 인용) · `literature-review` (선행문헌) · `publication-figures` (그림) · `research-ideation` (해석·토론).

## Replaces
- `deprecated/manuscript-writer` — full manuscript writing with research integration
- `deprecated/scientific-writing` — scientific prose style, paragraph structure
