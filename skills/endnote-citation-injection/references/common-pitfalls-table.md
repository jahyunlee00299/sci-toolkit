# Common Pitfalls (full table)

| Pitfall | Symptom | Fix |
|---------|---------|-----|
| ElementTree used | "File corrupted" in Word | Switch to lxml |
| Period before citation | `.{Author}` | Phase 7 ins placement order |
| Leading space | `text {Author}` | Phase 7 idx -= 1 if preceding space |
| Author field has corporate full name | `{FAO, 2021 #N}` doesn't resolve | Phase 6 author normalization (use 'FAO' not 'Food and Agriculture Organization') |
| EN_MAKE_SORT_KEY error | INSERT fails | Phase 6 stub function |
| ENCIN_ko_KR error | INSERT fails | Phase 6 stub collation |
| `\xef\xbf\xbd` in author | Broken ø/é/ä display in EndNote | Phase 6 author normalization with proper unicode |
| Bibliography author separator missing ("D. D., C. M." vs "D.; D., C. M.") | Authors used `\n` separator | Use `\r` (CR), not `\n` (LF) — most common silent failure |
| sync table missing entry | EndNote search "No matching reference" despite record exists | Phase 6 sync entry insert OR user runs Tools → Recover Library |
| Multi-run substring not found | Citation skipped | Phase 7 multi-run aware concat-match-split algorithm |
| Same substring N times in 1 para | Only first replaced | Phase 7 inner while-loop per paragraph |
| Bibliography output looks like "D. D., C. M." (no separator) | Output Style author separator broken | NOT our INSERT issue — user's EndNote Output Style needs author list separator config |
| `reference_type` code table assumed universal | Code 0 read as "Generic" but library renders it as "Journal Article" (or vice versa) | Per-library code↔name mapping — verify via GUI or via rendered `ref-type name="..."` string in the docx, never hardcode this skill's table (see DB-code-mapping warning, `references/endnote-sqlite-internals.md`) |
| Bulk `UPDATE refs SET ...` on existing/shared library | `database disk image is malformed`, or silent `refs_ord` inconsistency | Do NOT SQLite-UPDATE existing records — use EndNote GUI Find and Replace (In: Reference Type, etc.); SQLite is read-only diagnosis on a library beyond this run's own fresh INSERTs |
| Journal name still full/inconsistent after term-list import + Update Citations | A few entries didn't re-abbreviate | `fldData` was frozen before the term list existed — Convert to Unformatted Citations, then back to Formatted, to force a full re-render (`references/journal-name-normalization.md`, "Frozen-abbreviation problem") |
| Body cites `{Author, Year #N}` but `refs` has no row with that id | Citation renders as raw unformatted brace text; Find Citation(s) finds nothing | Phase 6.1 orphan recovery (`references/orphan-citation-recovery.md`) — resolve real paper via DOI, INSERT as a new record, then re-link via Edit & Manage Citation(s) (never hand-edit the brace text or guess a nearby id) |
| Duplicate rows in Journals term list for same title | Abbreviation silently doesn't apply despite term existing | Check/remove duplicate term-list rows (`jterms`) — see "Term list hygiene" note; use ENCI_Base/REINDEX safe path or GUI Term Lists editor |
| Record `secondary_title` doesn't byte-match term-list "Full Name" (`&` vs `and`, `&amp;` leak) | That one reference stays full/unabbreviated while others in the same journal abbreviate fine | Diff exact string vs term-list Full Name; fix `secondary_title`, not the term list |
| Edited reference-list text directly in Word body | Edit vanishes after next Update Citations / save | `EN.REFLIST` is a live field — fix the record's `secondary_title` or the term list instead |
| "database does not contain any Term Lists" in Open Term Lists dialog | Looks like term list wiped | Transient index/UI glitch — restart EndNote and re-check before assuming data loss |
| Body superscript citation numbers exceed reference-list max number | `endnote_biblio_check.py` check 7 flags missing numbers | Reference-list entries missing for cited numbers — locate and add the missing records (see `check_missing_reflist_entries`) |
| Direct `UPDATE`/`DELETE` on `refs` (not `jterms`) using the naive collation stub | `database disk image is malformed` | `refs`/`refs_ord` is cross-referenced (CWYW+sync+tags) — stay GUI-only; the ENCI_Base+REINDEX safe path is validated for `jterms`-class self-contained tables only, not `refs` |
