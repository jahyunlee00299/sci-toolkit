# Editing existing EndNote records: `safe_refs_update.py`

Direct `UPDATE`/`DELETE` on `refs` was once forbidden outright (read-only diagnosis, GUI Find and
Replace for fixes). That rule is **superseded**: `EN_MAKE_SORT_KEY` has been reproduced exactly
(`en_make_sort_key.py`), so an `UPDATE refs ...` is a supported operation again, but only through
the pipeline tool. Do not hand-roll the UPDATE.

## Why a hand-written UPDATE is still wrong

An INSERT fires only the `refs__refs_ord_AI` AFTER-INSERT trigger. An UPDATE fires the
AFTER-UPDATE trigger (`refs__refs_ord_AU`), which re-sorts `refs_ord` with the library's real
sort-key function and collations (`ENCIN_ko_KR`, `ENCI_Base`, `NOCASE`). A naive Python stub
(`.lower()` compare) can throw `database disk image is malformed`, or leave the sort index
inconsistent with EndNote's own rules while `PRAGMA integrity_check` (evaluated under the wrong
collation) reports spurious results or masks real ones.

## The tool

```bash
# 1. write a spec: record id -> column -> value  (a list value for `author` is joined with 
)
cat > fix.json <<'JSON'
{ "123": {"author": ["Smith, Anna Maria", "Jones, Peter", "Lee, Soo", "Costa, Ana"]} }
JSON

"$PY" safe_refs_update.py --spec fix.json            # rehearsal only (library untouched)
"$PY" safe_refs_update.py --spec fix.json --apply    # rehearse -> back up -> apply -> verify
```

What it guarantees, in order: refuses to run while `EndNote.exe` is open -> backs up `sdb.eni` ->
rehearses `REINDEX -> UPDATE -> REINDEX -> integrity_check` on a copy and re-derives every sort
key -> only then repeats it on the live file with `VACUUM` -> **restores the backup automatically
if post-apply verification fails**. Columns are allow-listed (`author`, `year`, `title`,
`secondary_title`, `volume`, `number`, `pages`, `electronic_resource_number`, `reference_type`);
`trash_state` and friends are rejected. Resolve a `reference_type` code from the type name
(`references/reference-types.md`).

Two facts worth knowing at the call site:

- **Authors are separated by `
` only.** A `
` is not a separator: EndNote folds the whole
  string into one author, which is what produces bibliography output such as
  `Smith, Anna MariaJones, Peter...` with the first author's given name swallowed. Scan for it
  with `SELECT id FROM refs WHERE author LIKE '%' || char(10) || '%'`.
- `ENCIN_ko_KR` is BINARY; `ENCI_Base` comes from the sibling `enci_base_collation.py`.

Tests (run both after touching either module; they are the gate, not decoration):

```bash
"$PY" tests/test_en_make_sort_key.py         # fixtures + full-library replay (skipped if no library)
"$PY" tests/test_safe_refs_update_guards.py  # every refusal path must actually fire (skipped if no library)
```

The replay test regenerates `key_2` for every row of a real library and compares it with what
EndNote itself stored; on the library it was derived from, every trigger-produced row reproduces
exactly. Rows that store a raw lower-cased author string instead of a sort key were inserted
without the trigger running (direct SQL INSERTs) and are a defect of those rows; re-saving them in
EndNote, or running any `--apply` edit against them, regenerates a proper key.

If the tool is unavailable, the fallback is the GUI: Library -> Find and Replace (for example
In: Reference Type, Bill -> Journal Article), and `SELECT` for diagnosis only. Before any
experiment, back up `sdb.eni`, close EndNote, and test on a throwaway copy.

## Exception: ENCI_Base reverse-engineered + REINDEX pipeline makes trigger-free tables safely editable 

`refs` is edited only through `safe_refs_update.py` (above): it drives `refs_ord` via an
AFTER-UPDATE trigger that needs the real collation. Separately, **`ENCI_Base` itself has now been
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
radius that has NOT been validated this way. `refs` edits go through `safe_refs_update.py`; only
`jterms`-class term-list tables get this direct-SQLite REINDEX path.

**Always required regardless of scope**: backup `sdb.eni` first (Phase 0), close EndNote before
opening the file, and validate on a throwaway copy before touching the live library if there is
any doubt about which tables a given `REINDEX` cascades into.
