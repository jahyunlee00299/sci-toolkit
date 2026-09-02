---
name: endnote-citation-injection
description: Inject EndNote unformatted citations (`{Author, Year #N}`) into a Word docx using Track Changes. Covers ref harvesting from a separate refs docx, DOI verification (CrossRef + OpenAlex cross-check), hallucination detection, alternative paper substitution, EndNote SQLite direct INSERT (bypassing manual RIS import), and lxml-based docx editing that preserves namespaces, places citations before periods, removes leading spaces, and survives Word's integrity check. Use when a thesis/manuscript draft has parenthetical (Author, Year) citations that need to be converted to EndNote `{Author, Year #RecordNumber}` form so EndNote 2025 + Word can render formatted bibliographies.
---

# EndNote Citation Injection

End-to-end pipeline that takes a draft Word docx with parenthetical citations and produces a Word docx with EndNote unformatted citations as Track Changes — every citation is reviewable and rejectable, the docx survives Word's integrity check, and the EndNote library is updated in place so the citations resolve.

## When to Use

Trigger this skill when the user asks any of:
- "이 docx 본문 인용을 EndNote 형식으로 바꿔줘"
- "(Author, 2020) → {Author, 2020 #N} 변환"
- "EndNote 라이브러리에 ref 추가하고 본문 인용 매칭"
- "별도 refs.docx에 reference list 있는데 본문 docx에 적용"
- The user is using (Author, Year) style citations and wants to convert them to EndNote unformatted form

Do NOT use when:
- User wants pure RIS export/import for a third party (use a simpler RIS-only flow)
- DOI verification only without docx editing (use a CrossRef agent directly)

## Execution Method

A non-trivial run (≥10 refs) splits into four roles — use whatever delegation mechanism your
agent provides (sub-agent/task tool under Claude Code, `spawn_agent` under Codex), not one
vendor's API; with no delegation available, run the roles sequentially in one context:
**coordinator** (user decisions, orchestration, direct DB INSERT), **crossref-verifier**
(CrossRef DOI verification + RIS generation), **openalex-verifier** (OpenAlex cross-check +
new-ref verification), **ref-resolver** (hallucination recovery + citation rewrite plan). For
≤5 refs, skip delegation — the overhead exceeds the work. Either way, the verification gate
applies unchanged: a sub-agent reporting "done" is not evidence, re-read its actual output.

## Pipeline (10 phases)

```
Phase 0: Backup + working area setup
   ↓
Phase 1: Two-docx analysis (refs source + body target)
   ↓
Phase 2: DOI dual verification (CrossRef + OpenAlex)
   ↓
Phase 3: Hallucination recovery (alt paper search)
   ↓
Phase 4: User decision gates (DROP/REPLACE/alt confirmation)
   ↓
Phase 5: Citation rewrite plan (multi-run aware mapping)
   ↓
Phase 6: EndNote DB INSERT (lxml stub functions)
   ↓
Phase 7: lxml Track Changes apply (period-aware)
   ↓
Phase 8: Integrity verification (xmlns + python-docx)
   ↓
Phase 9: User Word review
   ↓
Phase 10: OneDrive overwrite + DB author normalization
```

---

## Phase 0 — Backup + Working Area Setup

Before any edit:

1. **Local docx backup** (always):
   ```bash
   cp "<original>.docx" "<original>.backup-<YYYYMMDD>.docx"
   ```
2. **EndNote DB backup** (mandatory before any DB write):
   ```bash
   cp "$ENDNOTE_DATA/sdb/sdb.eni" "$ENDNOTE_DATA/sdb/sdb.eni.refs-backup-<YYYYMMDD>"
   ```
   Where `$ENDNOTE_DATA = ~/Documents/My EndNote Library_2025.Data/`
3. Working dir: `~/AppData/Local/Temp/refs_work/` (Windows) — short path, no OneDrive sync
4. Copy both target docx files to working dir as `v2.docx` (body target) and `v2_refs.docx` (refs source)

## Phase 1 — Two-docx Analysis

Goal: extract ref entries from `_refs.docx` (DOI-pattern paragraphs) and citations
(parenthetical + narrative forms) plus the existing ref section from `_v2.docx`. Worked
extraction code: `references/phase1-extraction-code.md`.

**Output**: `extraction_report.md` — ref entries (with DOI), body citations (with paragraph
indices), and the v2.docx ref section (often incomplete).

## Phase 2 — Dual DOI Verification

**Critical**: never trust a single API. Hallucinated DOIs are common. Spawn two agents in
parallel with the same `refs_to_verify.json`: **`crossref-verifier`**
(`https://api.crossref.org/works/{DOI}`, User-Agent: user email; verify author surname, year
±1, title 70%+ token match, journal name; DOI-less refs use `query.bibliographic={hint}&rows=3`;
output `doi_verify_pass1.json` with `match_status: ok|mismatch|not_found|hallucinated`) and
**`openalex-verifier`** (`https://api.openalex.org/works/doi:{DOI}?mailto={email}`, same
verification independently; output `doi_verify_pass2.json` plus `doi_discrepancies.md`
cross-checking both passes).

**Common findings** (measured distribution from a real 34-ref run): `references/phase2-verification-findings.md`.

## Phase 3 — Hallucination Recovery

For each hallucinated/404/unresolved ref, spawn `ref-resolver` agent: (1) title+author+year
search via Semantic Scholar (`https://api.semanticscholar.org/graph/v1/paper/search?query={title}&limit=3`),
(2) Crossref re-query with a different bibliographic combination, (3) output
`final_ref_resolution.json` with a per-ref verdict — `REPLACE` (paper found, with
final_doi/final_authors) or `DROP` (no paper exists; propose `alternative_doi` if a
topic-matching paper exists).

**Important**: never invent DOIs. If both APIs + manual search fail, mark DROP with
`alternative` field for user decision.

## Phase 4 — User Decision Gates (BLOCKING)

The main coordinator MUST pause and ask the user via AskUserQuestion: (1) REPLACE confirmation
per item, (2) DROP handling (remove all / replace with alternative / keep as-is), (3) alt paper
context fit — show `context_fit_score` (1-5), for score<5 ask inline vs separate sentence, (4)
newly discovered body refs not in refs.docx (add or remove). **Never assume** — every DROP and
alt selection must be user-approved.

## Phase 5 — Citation Rewrite Plan

`ref-resolver` agent produces `citation_rewrite_plan.json`: `transformations` each naming the
paragraph index, original substring, new substring (`#PLACEHOLDER_*` tokens filled in Phase 6
after EndNote DB INSERT returns real IDs), and one of 7 `operation` types (RETAIN / REPLACE /
REPLACE_NARRATIVE / REPLACE_WITH_ALT / REMOVE_CITATION_BUNDLE / REMOVE_CITATION_PARTIAL /
INSERT_NEW_SENTENCE). Full schema + worked example: `references/citation-rewrite-plan-schema.md`.

## Phase 6 — EndNote SQLite Direct INSERT

### Phase 6.0 — DOI-match existing records first (skip INSERT if already present)

**Critical (hard-won):** before inserting anything, query the DB by normalized DOI
(`SELECT id, author, year, electronic_resource_number FROM refs WHERE
LOWER(electronic_resource_number) LIKE '%<doi>%'`) for every target ref — many/all targets
already exist in a mature library, and duplicates are worse than reusing. Only INSERT refs with
genuinely no match. For each hit, confirm author/year sanity and **verify the author separator
is `\r`, not `\n`** (needs the CR fix even if matched). Map `plan_ref_id -> existing_id`; route
only unmatched refs to INSERT below. (One real run: all 6 targets already existed — safest path.)

### Phase 6.1 — Orphan citation recovery (body cites a rec-number with no backing record)

The reverse failure of 6.0: the docx body cites a rec-number (`{Author, Year #901}`) with no
matching row in `refs`, rendering as raw brace text. Diagnose via `SELECT id FROM refs WHERE
id = ?`; recover by adding a verified new record (never guess a replacement id or hand-edit the
brace text) and re-linking via EndNote's Edit & Manage Citation(s) dialog. Full procedure and
custom placeholder forms (`[REF:34]`, `[REF:87-91]`): `references/orphan-citation-recovery.md`.

---

**When INSERT is needed** (refs with no existing DB match): EndNote's RIS import is GUI-only and
slow. Direct SQLite INSERT works IF you handle two EndNote-specific SQLite extensions —
`EN_MAKE_SORT_KEY` and `ENCIN_ko_KR` (custom function + collation on the `refs_ord`
AFTER-INSERT trigger, both failing INSERT with a clear error if missing). Full stub code,
INSERT columns, mandatory post-INSERT audit: `references/endnote-sqlite-internals.md`.

Two hard rules that gate whether Phase 6 is safe to run at all:
- **Author separator MUST be `\r` (CR), never `\n` (LF)** — LF silently breaks author-list
  rendering while the EndNote UI still looks correct.
- **`reference_type` MUST be set explicitly (default 17 = Journal Article)** — 0/NULL/omitted
  renders as "Bill" (lost italics/bold), no UI-visible error. One incident: 33 Bill + 2 Generic.

### ⚠️ SQLite UPDATE on shared records = forbidden, use GUI (260715 finding)

INSERT is safe (AFTER-INSERT trigger, handled by this skill's two stubs). **Fixing
already-inserted bad records fires the AFTER-UPDATE trigger, needing the library's REAL
collation (`ENCIN_ko_KR`, `ENCI_Base`, `NOCASE`) that our stubs do not reproduce** — a direct
`UPDATE` on a shared library can throw `database disk image is malformed` or silently corrupt
the sort index. **Rule: SQLite on `refs` beyond this run's own fresh INSERTs is read-only
diagnosis only — use EndNote's Library → Find and Replace for bulk fixes.** One exception exists
for self-contained term-list tables (`jterms`, `ENCI_Base` + `REINDEX`); does NOT generalize to
`refs`. Full rule: `references/endnote-sqlite-update-rules.md`.

### Triggers (auto-fire on INSERT, no manual population needed)
`refs__refs_ord_AI`, `refs__ref_props_AI`, `refs__ret_watch_AI`, `refs__tag_members_AI`. The
`sync` table is the exception — NOT auto-populated, so a new record may not be CWYW-searchable
until a sync row is added or the user runs Tools → Recover Library. Sync INSERT, lock check,
author normalization: `references/endnote-sqlite-internals.md`.

### Post-render QC gate — `endnote_biblio_check.py` (260714, MANDATORY)

After EndNote renders the bibliography (or before any manuscript submission), run the
non-destructive checker:
```
python <docx-skill>/scripts/endnote_biblio_check.py <manuscript.docx>
python <docx-skill>/scripts/endnote_biblio_check.py <manuscript.docx> --strict   # exit 1 if any error (gate)
```
Detects 7 error classes (reference_type wrong, invalid citation, journal italic missing, author
omission, `&amp;` breakage, non-CASSI journal, missing reflist entries) from `word/document.xml`
alone, no Word needed. Full catalog: `references/biblio-check-error-classes.md`. Mandatory
pre-submission gate (`--strict`), not optional cleanup.

### Journal name normalization (MUST normalize before INSERT)

**Never write the raw `container-title` from CrossRef/OpenAlex/PubMed straight into
`secondary_title`** — sources disagree on abbreviation/periods/suffixes, producing a mixed
abbreviated/full-name bibliography in a real run. **Store the full canonical name** and let
EndNote's Journals Term List + style (CASSI for RSC/chemistry, not ISO4) do the abbreviation.
Full steps, CASSI import, term-list hygiene: `references/journal-name-normalization.md`.

### ⚠️ Frozen-abbreviation problem (260715 finding)

Each citation's rendered text is a **frozen `fldData` snapshot** — if frozen before the term
list existed or `secondary_title` was normalized, a plain "Update Citations and Bibliography"
will NOT re-abbreviate it. **Fix: Convert to Unformatted Citations, then back to Formatted
Citations** — forces every snapshot to rebuild. Do this any time the term list changes or
`secondary_title` is corrected. Full procedure: `references/journal-name-normalization.md`.

## Phase 7 — lxml Track Changes Application

**Critical**: NEVER use `xml.etree.ElementTree` for docx editing — it drops unrecognized xmlns
declarations and renames prefixes (`wpc:` → `ns5:`, etc.), corrupting Word's namespace map so
Word shows the file as corrupted on open. Use `lxml.etree` with
`ET.tostring(..., xml_declaration=True, encoding='UTF-8')`, which preserves nsmap exactly.

**Critical (ins/del ordering)**: place `<w:ins>` immediately after `<w:del>`, never after the
suffix run — `del → suffix → ins` puts the period BEFORE the citation (wrong); `del → ins →
suffix` keeps it after (correct per academic style).

Full algorithm (multi-run concat-match-split), leading-space removal, exact XML element format,
and the per-paragraph apply loop: `references/lxml-track-changes-mechanics.md`.

## Phase 8 — Integrity Verification

After Phase 7, before showing user, run three checks in order: (1) python-docx open test —
paragraph/table/inline_shape/section counts must match original, (2) namespace count check —
`xmlns` count in `word/document.xml` unchanged, (3) ns-artifact check — zero `ns\d+:` matches
(ElementTree leak signature). Full code: `references/phase8-integrity-check-code.md`.

**If any check fails — abort, restore from backup, debug.** Common cause: switched to
`xml.etree.ElementTree` by accident.

## Phase 9 — User Word Review

Open the tracked docx (`start "" "<output_path>"` on Windows). Tell the user: Review tab → "All
Markup" shows red strikethrough (deletions) + colored insertions; spot-check 3-5 transformations
(period placement, no leading space, correct record IDs); Accept All or Reject specific ones.
User must approve before Phase 10.

## Phase 10 — OneDrive Overwrite

Once approved:
```bash
cp "<work_dir>/v2.tracked.docx" "<original_path>"
```

Final verification: re-open via python-docx, confirm structural counts match.

## Common Pitfalls

Full table (19 rows, symptom → fix, all phases + DB/term-list edge cases):
`references/common-pitfalls-table.md`.

## Output Files (per run)

All under `refs_work/`, pipeline order: `refs_to_verify.json`, `doi_verify_pass1.json`
(CrossRef), `doi_verify_pass2.json` (OpenAlex), `doi_discrepancies.md`,
`final_ref_resolution.json`, `alternative_verification.json`, `new_refs_verification.json`,
`ref_metadata_full.json`, `refs_for_endnote_import.ris` (fallback), `citation_rewrite_plan.json`,
`endnote_record_map.json` (plan_ref_id→record id), `apply_report_v4.json`, `v2.tracked.docx`.

## Memory Hooks

Save after each run: project name + manuscript path, date applied, refs processed (N inserted,
M alt'd, K dropped), and the EndNote record id range for future updates.
Worked example of the note (`endnote_injection_<project>.md`): `references/memory-hook-example.md`.

## Reference Run

Validated end-to-end (thesis-review .docx): 34 candidate refs → 33 INSERT-ed (1 dropped) → 34
transformations, record range 748–780, zero corruption, in-place overwrite.

---

## Related Skills

- `manuscript-pipeline` — upstream context; single/few DOIs use its
  `references/endnote_integration.md` instead.
- `docx` — OOXML insertion mechanics SSOT for `<w:ins>`/comment-marker patterns in Phase 7.
- `academic-term-rules` — italic conventions for author names.

**Role boundary:** single DOI → `manuscript-pipeline`; bulk batch (10+) → this skill; OOXML → `docx`.
