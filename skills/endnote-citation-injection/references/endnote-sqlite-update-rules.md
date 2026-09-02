# SQLite direct UPDATE on existing EndNote records — rules and the ENCI_Base exception

Full rationale for why `refs` stays read-only after INSERT, and the one
validated exception (`jterms`-class self-contained term-list tables) that
can be safely edited via a real-collation REINDEX pipeline.

## ⚠️ SQLite direct UPDATE on existing records = read-only diagnosis, NOT a fix path (260715 finding)

Everything in `references/endnote-sqlite-internals.md` (INSERT + the two stub functions) works because INSERT only fires the
`refs__refs_ord_AI` **AFTER-INSERT** trigger, which this skill's `EN_MAKE_SORT_KEY` +
`ENCIN_ko_KR` stubs are sufficient for. **Fixing already-inserted bad records (e.g. bulk
`reference_type` correction, or a bulk `\r`/`\n` author-separator fix) is a different
operation — it fires the AFTER-**UPDATE** trigger (`refs__refs_ord_AU`), which requires the
library's real collation/sort-key behavior, not our approximations.**

In a mature, actively-used library (this project's "My EndNote Library_2025") the `refs_ord`
index is built with **three custom collations**: `ENCIN_ko_KR`, `ENCI_Base`, and `NOCASE`. This
skill's Python-side collation stub (`encin_collation`, a naive `.lower()` compare) does not
reproduce the real `ENCIN_ko_KR`/`ENCI_Base` behavior. A direct `UPDATE refs SET reference_type
= ... WHERE id IN (...)` against a library that uses these collations can throw
`database disk image is malformed` when the AU trigger tries to re-sort `refs_ord`, and even a
successful-looking UPDATE risks leaving the sort index inconsistent with the real collation
rules — `PRAGMA integrity_check` will then report spurious issues (or mask real ones) because
it is being evaluated against the wrong collation implementation.

**Rule: SQLite access to an existing/shared EndNote library is read-only (diagnosis, counting,
export) — never `UPDATE`/`DELETE` on `refs` once records exist beyond what this run itself just
inserted.** Concretely:
- **Bulk `reference_type` correction (Bill → Journal Article, etc.)** → use EndNote's own
  **Library → Find and Replace → In: Reference Type → Bill → Journal Article** (bulk, GUI-native,
  respects the library's own collation/sort-key logic). This is the only safe path once bad
  records are already committed to a shared library. ([Clarivate KB](https://support.clarivate.com/Endnote/s/article/EndNote-Change-reference-type-for-many-records))
- **Bulk author `\r`/`\n` separator fix** on records that were NOT inserted by this same run/session
  → also prefer GUI (open record, re-enter/re-paste author field) or, if scripting is
  unavoidable, restrict the UPDATE to the exact id range this skill's own INSERT just created in
  the same transaction (fresh rows, AU trigger has not yet had to re-sort them against
  collation-dependent neighbors) — never retrofit older/foreign records this way.
- **Before any UPDATE attempt at all**: back up `sdb.eni` (mandatory, see Phase 0), then test the
  UPDATE against a **throwaway copy** of the DB file first and run `PRAGMA integrity_check` on
  the copy afterward. If it reports anything beyond the expected diff, do not apply to the live
  file — fall back to GUI Find&Replace and restore from backup if a live UPDATE was already
  attempted.
- **Diagnosis is always safe** (`SELECT ... FROM refs`, `SELECT ... FROM refs_ord` read-only) —
  only `INSERT`/`UPDATE`/`DELETE` carry the trigger/collation risk. Use SQLite freely to count,
  audit, and locate bad records; use the EndNote GUI to actually fix them once records already
  exist in a shared/multi-manuscript library.

## Exception: ENCI_Base reverse-engineered + REINDEX pipeline makes trigger-free tables safely editable (260715 finding)

The blanket "read-only, use GUI" rule above still holds for **`refs`** (it drives `refs_ord` via
an AFTER-UPDATE trigger that needs the real collation). But **`ENCI_Base` itself has now been
reverse-engineered successfully** — see `enci_base_collation.py` (co-located in this skill's
folder, `endnote-citation-injection/enci_base_collation.py`) — reproducing 3526/3527 (99.97%) of
real `ENCI_Base`-ordered rows across every `COLLATE ENCI_Base` index in a live library (`jterms`
+ `terms` tables). This changes the calculus for **tables whose only ENCI_Base-collated index is
their own, self-contained sort index (no cross-table AU trigger depending on `refs`)** — e.g.
`jterms` (journal name/abbreviation term list):

**Safe pipeline for such tables** (validated on `jterms`, 34 duplicates removed 195→161, `refs`
byte-identical afterward, GUI-confirmed):
```
1. Register the REAL collation: enci_base_collation.register(conn)  (not a naive .lower() stub)
2. DELETE the target rows (duplicates, bad terms, etc.)
3. REINDEX <table>  -- e.g. REINDEX jterms  (rebuilds the ENCI_Base-collated B-tree index
                        using the now-correctly-registered real collation)
4. VACUUM            -- reclaim space, keep file compact
5. PRAGMA integrity_check  -- only trustworthy NOW that the real collation is registered;
                              running this with the OLD naive stub collation gives false
                              results either way (false pass or false fail) because the check
                              itself re-evaluates index order under whatever collation is
                              currently registered.
```
**Why this works where the earlier "PRAGMA alone" attempts failed**: PRAGMA/integrity_check does
not rebuild anything — it only re-validates existing index order against the *currently
registered* collation function. If that function is the naive stub (case-fold only, no accent
stripping, wrong punctuation precedence), the check is comparing real on-disk order against a
wrong reference and reports "malformed" even when nothing is actually broken (or vice versa,
silently missing real corruption). **`REINDEX` is the operative step** — it doesn't just check,
it *regenerates* the index from the base table using whatever collation is registered at that
moment, so a correct collation registration is a hard precondition, not optional.

**Scope of this exception — do NOT generalize to `refs`:** `jterms`/`terms` are self-contained
(their ENCI_Base index only orders their own rows for the Term List UI). `refs`/`refs_ord` is
cross-referenced by CWYW citation resolution and the AU trigger's sort-key regeneration touches
sync/tag/prop side-tables too — a `refs` DELETE/UPDATE + REINDEX is a materially larger blast
radius that has NOT been validated this way. Until that validation exists, `refs` stays GUI-only
per the rule above; only `jterms`-class term-list tables get this safe direct-SQLite path.

**Always required regardless of scope**: backup `sdb.eni` first (Phase 0), close EndNote before
opening the file, and validate on a throwaway copy before touching the live library if there is
any doubt about which tables a given `REINDEX` cascades into.
