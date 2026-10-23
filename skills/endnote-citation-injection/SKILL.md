---
name: endnote-citation-injection
description: EndNote 2025 library and its Word citations. INJECT - turn (Author, Year) citations into {Author, Year #RecNum} via Track Changes, with DOI verification, hallucination checks and rule-checked inserts (en_insert.py). REPAIR - fix library records that render wrongly (merged or garbled authors, wrong reference type, broken journal names) with safe_refs_update.py, never a hand-written UPDATE. ADD records with en_insert.py. FORMAT - guarded CWYW (cwyw_update.py) and .ens output styles read and edited with ens_style.py. Use when a thesis or manuscript draft has parenthetical citations to convert to EndNote form, or when an EndNote bibliography renders wrongly.
---

# EndNote Citation Injection

End-to-end pipeline that takes a draft Word docx with parenthetical citations and produces a Word docx with EndNote unformatted citations as Track Changes — every citation is reviewable and rejectable, the docx survives Word's integrity check, and the EndNote library is updated in place so the citations resolve.

## When to Use

Trigger this skill when the user asks any of:
- "convert the citations in this docx to EndNote form"
- "(Author, 2020) -> {Author, 2020 #N}"
- "add these refs to the EndNote library and match them to the body citations"
- "the reference list is in a separate refs.docx; apply it to the body docx"
- "the bibliography shows merged authors / the wrong reference type / unabbreviated journals"
- "change this EndNote output style" or "run Update Citations and Bibliography"

Do NOT use when:
- User wants pure RIS export/import for a third party (use a simpler RIS-only flow)
- DOI verification only without docx editing (use a CrossRef agent directly)
- A single DOI or a handful of citations (use `manuscript-pipeline`'s `references/endnote_integration.md`)

## Default: insert unformatted, format once before submission

A new citation enters a manuscript ONLY as an unformatted EndNote marker `{Author, Year #RecNum}`
(a group is `{A, 2017 #123; B, 2023 #124}`), as plain text runs under Track Changes. "Update
Citations and Bibliography" (CWYW, `cwyw_update.py`) is NOT part of the editing loop. It is run
**once, near submission, on a document with no tracked changes**, and its rendered output is then
read against the sentences.

Why: CWYW has two measured failure modes that every automated gate passes - a tracked-deleted
citation field is resurrected, and every citation can shift by one position
(`references/cwyw-update-and-failure-modes.md`). Unformatted markers are visible, recoverable and
break nothing; the formatted state is only produced once, where it can be audited.

**Pre-submission sequence (exact order):**

1. Accept all tracked changes (no revision may remain; `manuscript-pipeline/scripts/manuscript_text.py --count-only` must not report tracked changes).
2. Close EndNote (`safe_refs_update.py` refuses to run while `EndNote.exe` is open); kill every Word process.
3. Library fixes via `safe_refs_update.py --apply` (`references/endnote-sqlite-update-rules.md`).
4. `cwyw_update.py <docx>`. Fix the library first: CWYW prints whatever the record says at that moment.
5. Read EVERY rendered citation against its sentence. A field census or `INVALID CITATION 0` is not evidence.
6. `endnote_biblio_check.py --strict` and `reference_validator.py`.

**Marker format:**

- **Surname = the first author exactly as stored in the record** (`refs.author`, text before the first `\r` and its comma), not the surname printed in the paper's byline if the record differs.
- **Resolve the RecNum from the LIVE DB**: a read-only copy of `$ENDNOTE_DATA/sdb/sdb.eni`, never the stale `.enl` (Phase 0). List every candidate with id, authors, year, title and DOI before choosing; trashed rows (`trash_state != 0`) and duplicates are normal.
- **Same surname, different year is a trap** - a wrong id resolves silently to a different paper. Confirm id, year AND title together, never surname + year from memory.
- **Corporate author = the record's exact author string** (`FAO`, not `Food and Agriculture Organization`; see Phase 6 "Author normalization"). A long-form record stops `{Author, Year #N}` from resolving and prints as the wrong name.
- A marker whose id has no row in `refs` is an orphan (Phase 6.1). While it is still an unformatted marker, correcting the brace text IS the repair; field re-linking is only for already-formatted fields.

## Tools in this skill

| script | job |
| --- | --- |
| `en_insert.py` | add records (validated spec, rehearsal on a copy, backup, verification) |
| `safe_refs_update.py` | edit existing records (rehearse, back up, verify, auto-restore) |
| `cwyw_update.py` + `cwyw_guard.py` + `en_fields.py` | the one guarded Update Citations run |
| `endnote_library_audit.py` | read-only author-notation and DOI audit of the whole library (`references/library-audit-and-ens-styles.md`) |
| `ens_style.py` | read and edit `.ens` output styles (`references/library-audit-and-ens-styles.md`) |
| `en_reftypes.py`, `en_journal.py`, `en_make_sort_key.py`, `enci_base_collation.py` | support modules (type by name, journal normalization, sort key, collation) |
| `../manuscript-pipeline/scripts/endnote_biblio_check.py` | post-render QC gate on a docx |

Tests run on synthetic data and skip cleanly when no EndNote library or install is present:
`for t in tests/test_*.py; do "$PY" "$t"; done`.

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
Phase 6: EndNote record INSERT (en_insert.py)
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

   **Read the library ONLY through `$ENDNOTE_DATA/sdb/sdb.eni`. The sibling
   `My EndNote Library_2025.enl` is a stale snapshot and querying it produces false "not in the
   library" answers.** Measured: the `.enl` was a copy whose highest record id was far below the
   live file's, so a lookup reported a paper absent that the live `sdb.eni` held, and the false
   verdict was relayed before it was caught. A wrong absence verdict is expensive: it sends the
   next step off to re-import a reference that already exists. Copy `sdb.eni` to a scratch path
   and open the copy read-only (`file:...?mode=ro`); never read or write the live file in place.
   A read-only query is also the fastest way to resolve "which Chen 2021 is this?": list every
   candidate with id, authors, title and DOI before judging.
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

## Phase 6 — EndNote record INSERT (`en_insert.py`)

### Phase 6.0 — DOI-match existing records first (skip INSERT if already present)

**Critical (hard-won):** before inserting anything, query the DB by normalized DOI
(`SELECT id, author, year, electronic_resource_number FROM refs WHERE
LOWER(electronic_resource_number) LIKE '%<doi>%'`) for every target ref — many/all targets
already exist in a mature library, and duplicates are worse than reusing. Only INSERT refs with
genuinely no match. For each hit, confirm author/year sanity and **verify the author separator
is `\r`, not `\n`** (needs the CR fix even if matched). Map `plan_ref_id -> existing_id`; route
only unmatched refs to INSERT below. (One real run: all 6 targets already existed — safest path.)

### Phase 6.1 — Orphan citation recovery (body cites a rec-number with no backing record)

The reverse failure of 6.0: the docx body cites a rec-number (`{Author, Year #123}`) with no
matching row in `refs`, rendering as raw brace text. Diagnose via `SELECT id FROM refs WHERE
id = ?`; recover by adding a verified new record (never guess a replacement id or hand-edit the
brace text) and re-linking via EndNote's Edit & Manage Citation(s) dialog. Full procedure and
custom placeholder forms (`[REF:34]`, `[REF:87-91]`): `references/orphan-citation-recovery.md`.

---

**When INSERT is needed** (refs with no existing DB match): run **`en_insert.py`**. Do not hand-write
the INSERT; EndNote's RIS import is GUI-only and slow, and a direct SQLite INSERT needs two
EndNote-specific extensions (`EN_MAKE_SORT_KEY`, `ENCIN_ko_KR`) that the tool already registers.

```bash
"$PY" en_insert.py --spec new_refs.json                    # validate + rehearse on a copy
"$PY" en_insert.py --spec new_refs.json --apply --json ids.json   # back up, insert, verify
```

The spec is a JSON list (`type`, `authors`, `year`, `title`, `journal`, `volume`, `issue`,
`pages`, `doi`, optional `url`/`publisher`/`place`/`date`/`notes`/`access_date`/`corporate`). Each
rule below is a refusal before anything is written, and each closes an incident:

| rule | source module | incident it closes |
| --- | --- | --- |
| `type` required, resolved by **name** from `%APPDATA%\EndNote\RefTypeTable.xml`; Bill/Generic need `--allow-type` | `en_reftypes.py` | Bill/Generic leak (33 + 2 records); XML-number mix-up |
| authors `Surname, Given`, CR-joined, no LF/U+FFFD, no bare surname (`corporate: true` for organisations) | `en_insert.py` | `\n` separator; author omission |
| journal resolved to the canonical full name via the library term list, then the shipped lists (`Terms Lists\*.txt`); abbreviations expand, shipped full names stay; a name missing from the library list is reported | `en_journal.py` | raw PubMed strings; unabbreviated journals |
| DOI normalised; one already in the library is skipped and its id returned | `en_insert.py` | duplicate records (Phase 6.0) |
| no markup (`<sub>`, `<i>`, `<scp>` ...) in any field - EndNote prints it literally | `en_insert.py` | `CO<sub>2</sub>` printed as text in several records |

It prints the `{Surname, Year #id}` marker for each new record and adds the `sync` row by default
(`--no-sync-row` to skip). `en_journal.JournalIndex.polluted_terms()` lists library term-list
entries whose "full name" is really an abbreviation (e.g. `ACS Catal` next to `ACS Catalysis`);
they are reported, not auto-deleted. Tests: `"$PY" tests/test_en_insert.py`.

Internals (sort-key function, collation, column list, `\r` author separator, triggers, sync table,
lock check, author normalization) are kept for diagnosis only in
`references/endnote-sqlite-internals.md`. Do not copy them into a hand-written INSERT.

Hard rules the tool enforces, worth knowing when reading a failure:
- **Author separator MUST be `\r` (CR), never `\n` (LF)** - LF silently breaks author-list
  rendering while the EndNote UI still looks correct.
- **`reference_type` is resolved from the type NAME, never typed as a number.** 🔴 An older
  version of this skill said "default 17 = Journal Article"; 17 is **Bill** in the SQLite column
  (0 = Journal Article on a stock EndNote 2025 install). 27 is Equation and 12 is Audiovisual
  Material, not Report and Web Page. The numbering differs between the XML field, the SQLite
  column and a customised install: `references/reference-types.md`.
- **Corporate authors keep the short form** the citation key uses (author normalization, `references/endnote-sqlite-internals.md`).

### Editing existing records: `safe_refs_update.py`

`UPDATE refs ...` is supported, but only through the pipeline tool, which rehearses on a throwaway
copy first, backs up `sdb.eni`, verifies every sort key and restores the backup if verification
fails. It refuses to run while EndNote is open. Never a hand-written UPDATE: it fires the
AFTER-UPDATE trigger that needs the real collation and can corrupt the sort index.

```bash
"$PY" safe_refs_update.py --spec fix.json            # rehearsal only (library untouched)
"$PY" safe_refs_update.py --spec fix.json --apply    # rehearse -> back up -> apply -> verify
```

Spec, allow-listed columns, tests and the `jterms` term-list exception:
`references/endnote-sqlite-update-rules.md`. Wrong reference types are fixed the same way.

### Running Update Citations: `cwyw_update.py`

Only step 4 of the pre-submission sequence above. It is guarded by default (precheck, unhusk,
verify with exit 4 on a shifted or resurrected citation). The measured failure modes, the
untracked-delete route for replacing a citation, and the benign `empty_field_result` artifact:
`references/cwyw-update-and-failure-modes.md`.

### Post-render QC gate — `endnote_biblio_check.py` (MANDATORY)

After EndNote renders the bibliography (or before any manuscript submission), run the
non-destructive checker:
```
python skills/manuscript-pipeline/scripts/endnote_biblio_check.py <manuscript.docx>
python skills/manuscript-pipeline/scripts/endnote_biblio_check.py <manuscript.docx> --strict   # exit 1 if any error (gate)
```
Detects 7 error classes (reference_type wrong - Bill, Generic or Equation, judged by rendered name -, invalid citation, journal italic missing, author
omission, `&amp;` breakage, non-CASSI journal, missing reflist entries) from `word/document.xml`
alone, no Word needed. Full catalog: `references/biblio-check-error-classes.md`. Mandatory
pre-submission gate (`--strict`), not optional cleanup.

### Journal name normalization (MUST normalize before INSERT)

**Never write the raw `container-title` from CrossRef/OpenAlex/PubMed straight into
`secondary_title`** — sources disagree on abbreviation/periods/suffixes, producing a mixed
abbreviated/full-name bibliography in a real run. **Store the full canonical name** and let
EndNote's Journals Term List + style (CASSI for RSC/chemistry, not ISO4) do the abbreviation.
Full steps, CASSI import, term-list hygiene: `references/journal-name-normalization.md`.

### ⚠️ Frozen-abbreviation problem 

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

Full table (25 rows, symptom → fix, all phases + DB/term-list edge cases):
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
transformations, a contiguous block of new record ids, zero corruption, in-place overwrite.

---

## Related Skills

- `manuscript-pipeline` — upstream context; single/few DOIs use its
  `references/endnote_integration.md` instead.
- `docx` — OOXML insertion mechanics SSOT for `<w:ins>`/comment-marker patterns in Phase 7.
- `academic-term-rules` — italic conventions for author names.
- `verification-gates` — routes "verify" requests to the right gate; `endnote_library_audit.py` is its references axis.

**Role boundary:** single DOI → `manuscript-pipeline`; bulk batch (10+) → this skill; OOXML → `docx`.
