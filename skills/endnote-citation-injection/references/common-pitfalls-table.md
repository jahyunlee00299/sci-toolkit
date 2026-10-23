# Common Pitfalls (full table)

| Pitfall | Symptom | Fix |
|---------|---------|-----|
| ElementTree used | "File corrupted" in Word | Switch to lxml |
| Period before citation | `.{Author}` | Phase 7 ins placement order |
| Leading space | `text {Author}` | Phase 7 idx -= 1 if preceding space |
| Author field has corporate full name | `{FAO, 2021 #N}` doesn't resolve | Phase 6 author normalization (use 'FAO' not 'Food and Agriculture Organization') |
| EN_MAKE_SORT_KEY error | INSERT fails | A hand-written INSERT: use `en_insert.py` (`references/endnote-sqlite-internals.md` explains the function) |
| ENCIN_ko_KR error | INSERT fails | A hand-written INSERT: use `en_insert.py` (`references/endnote-sqlite-internals.md`) |
| `\xef\xbf\xbd` in author | Broken ø/é/ä display in EndNote | Phase 6 author normalization with proper unicode |
| Bibliography author separator missing ("D. D., C. M." vs "D.; D., C. M.") | Authors used `\n` separator | Use `\r` (CR), not `\n` (LF) — most common silent failure |
| sync table missing entry | EndNote search "No matching reference" despite record exists | Phase 6 sync entry insert OR user runs Tools → Recover Library |
| Multi-run substring not found | Citation skipped | Phase 7 multi-run aware concat-match-split algorithm |
| Same substring N times in 1 para | Only first replaced | Phase 7 inner while-loop per paragraph |
| Bibliography output looks like "D. D., C. M." (no separator) | Output Style author separator broken | NOT our INSERT issue — user's EndNote Output Style needs author list separator config |
| `reference_type` read or typed as a number | Code 17 stored as "Journal Article" renders as **Bill**; 27 renders as Equation, 12 as Audiovisual Material | Three numberings exist (XML, sqlite, user-defined). Resolve by NAME with `en_reftypes` (`references/reference-types.md`); verify the rendered `ref-type name` with `endnote_biblio_check.py`. Never write an audit filter such as `NOT IN (17,27,12,...)` |
| Bulk or hand-written `UPDATE refs SET ...` on an existing library | `database disk image is malformed`, or silent `refs_ord` inconsistency | Never a hand-written UPDATE: `safe_refs_update.py --spec` (rehearse on a copy, back up, verify, auto-restore). GUI Find and Replace only if the tool is missing (`references/endnote-sqlite-update-rules.md`) |
| Journal name still full/inconsistent after term-list import + Update Citations | A few entries didn't re-abbreviate | `fldData` was frozen before the term list existed — Convert to Unformatted Citations, then back to Formatted, to force a full re-render (`references/journal-name-normalization.md`, "Frozen-abbreviation problem") |
| Body cites `{Author, Year #N}` but `refs` has no row with that id | Citation renders as raw unformatted brace text; Find Citation(s) finds nothing | Phase 6.1 orphan recovery (`references/orphan-citation-recovery.md`) — resolve real paper via DOI, INSERT as a new record, then re-link via Edit & Manage Citation(s) (never hand-edit the brace text or guess a nearby id) |
| Duplicate rows in Journals term list for same title | Abbreviation silently doesn't apply despite term existing | Check/remove duplicate term-list rows (`jterms`) — see "Term list hygiene" note; use ENCI_Base/REINDEX safe path or GUI Term Lists editor |
| Record `secondary_title` doesn't byte-match term-list "Full Name" (`&` vs `and`, `&amp;` leak) | That one reference stays full/unabbreviated while others in the same journal abbreviate fine | Diff exact string vs term-list Full Name; fix `secondary_title`, not the term list |
| Edited reference-list text directly in Word body | Edit vanishes after next Update Citations / save | `EN.REFLIST` is a live field — fix the record's `secondary_title` or the term list instead |
| "database does not contain any Term Lists" in Open Term Lists dialog | Looks like term list wiped | Transient index/UI glitch — restart EndNote and re-check before assuming data loss |
| Body superscript citation numbers exceed reference-list max number | `endnote_biblio_check.py` check 7 flags missing numbers | Reference-list entries missing for cited numbers — locate and add the missing records (see `check_missing_reflist_entries`) |
| Direct `UPDATE`/`DELETE` on `refs` using a naive collation stub | `database disk image is malformed` | Use `safe_refs_update.py` (real sort key and collation, rehearsal on a copy); the ENCI_Base + REINDEX path is for `jterms`-class self-contained tables only |

| Tracked-deleted citation field, then CWYW | The deleted record comes back (merged or as a second field), every gate passes | Delete the old field untracked, insert the replacement tracked, format once before submission (`references/cwyw-update-and-failure-modes.md`) |
| CWYW run on a document with many tracked changes | Every citation renders one position off, `INVALID CITATION 0` | `cwyw_update.py` guard (exit 4); accept all revisions first; read each rendered citation against its sentence |
| Library queried through the sibling `.enl` file | False "not in the library" answers | Read only a copy of `sdb/sdb.eni`; the `.enl` is a stale snapshot |
| Markup (`<sub>`, `<i>`) typed into a title or journal field | Tags print literally in the bibliography | `en_insert.py` refuses markup; EndNote keeps character formatting in `text_styles` |
