# EndNote SQLite INSERT internals

Full detail for Phase 6 direct SQLite INSERT: the two custom SQLite
extensions EndNote registers, the INSERT statement's required columns,
the author-separator pitfall, the reference_type code table and its
per-library trap, the auto-fired triggers, and the sync-table gap.

## EN_MAKE_SORT_KEY function

EndNote registers a custom SQLite function on the `refs_ord` AFTER INSERT trigger. Without it, INSERT fails with `no such function: EN_MAKE_SORT_KEY`.

Stub:
```python
import unicodedata, re
def en_make_sort_key(text, key_type, length):
    if text is None: return ''
    s = unicodedata.normalize('NFKD', str(text))
    s = ''.join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower()
    s = re.sub(r'\s+', ' ', s).strip()
    s = re.sub(r'^(the |a |an )', '', s)
    return s[:length * 8] if length else s[:96]

conn.create_function("EN_MAKE_SORT_KEY", 3, en_make_sort_key)
```

## ENCIN_ko_KR collation

The `refs_ord` table uses a Korean case-insensitive collation. Without it, INSERT fails with `no such collation sequence`.

Stub:
```python
def encin_collation(a, b):
    a = (a or '').lower(); b = (b or '').lower()
    return (a > b) - (a < b)

conn.create_collation("ENCIN_ko_KR", encin_collation)
```

## INSERT statement

Required columns (defaults are empty string for TEXT, 0 for INTEGER):
```python
INSERT INTO refs (id, trash_state, text_styles, reference_type, author, year, title,
                  pages, secondary_title, volume, number, publisher, place_published,
                  electronic_resource_number, url,
                  added_to_library, record_last_updated)
VALUES (?, 0, '', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
```

**Author format**: `'Last, F.\rLast, F.\rLast, F.'` (CARRIAGE RETURN-separated, Last comma First initial period).

⚠️ **Critical**: EndNote uses `\r` (CR, 0x0D) as the author separator, NOT `\n` (LF, 0x0A). Using `\n` causes the bibliography output to LOSE author separators entirely — the result is broken text like "Krause-Jensen, D. D., C. M." instead of "Krause-Jensen, D.; Duarte, C. M.". This is the most easily-missed pitfall: the DB save succeeds, the EndNote UI displays authors correctly (since both \r and \n look identical there), but **bibliography rendering fails silently**.

How to verify: query an existing pre-existing working ref (e.g., id < 100) and confirm `\r` separators. Our pre-existing refs with id 450–600 show `\r`; only newer refs (e.g., id 735) imported via certain RIS workflows show `\n` and exhibit the same bug.

Fix on existing refs — **safe only within the same INSERT run/transaction** (fresh ids this
skill just created, before any other session has touched them):
```python
c.execute("UPDATE refs SET author = REPLACE(author, x'0A', x'0D') WHERE id BETWEEN ? AND ?", (start, end))
```
⚠️ Once records are committed and the library has been used/reopened elsewhere (i.e. this is a
retrofit on older/foreign records, not the current run's own inserts), do NOT run this UPDATE
directly against a shared library — see `references/endnote-sqlite-update-rules.md`: back up, test on a throwaway copy, prefer GUI-side correction, and never
UPDATE a shared library's `refs` table without a `PRAGMA integrity_check` dry run first.

**Reference type codes** (typical mapping, but NEVER trust this table blind — see the DB-code-mapping pitfall right below):
- 17 = Journal Article (most common)
- 27 = Report (IPCC, FAO)
- 12 = Web Page (corporate refs like BSH Ingredients)
- 47 = Conference Paper (NeurIPS via arXiv)
- 0 = Generic (in most libraries) — **but not always** (see below)

⚠️ **CRITICAL — DB reference_type code↔name mapping is PER-LIBRARY, do not hardcode (260715 finding).**
EndNote's internal `reference_type` integer code is an index into that specific library's
`Reference Types` list, which the user can reorder/customize per `.enl`/`.Data` library. In
**this project's "My EndNote Library_2025"**, code **0 renders as "Journal Article"**, not
"Generic" — the opposite of the naive assumption above. Reading `reference_type` straight out
of SQLite and assuming a fixed code table is exactly how a diagnosis goes wrong:
- **Before trusting any code→name reading from SQLite, cross-check against the EndNote GUI**
  (open a record with that code, check its displayed Reference Type dropdown) — the **GUI is
  the SSOT** for what a code renders as in a given library (C-55 principle applied here: live
  state over cached/inferred state).
- A faster cross-check: decode `reference_type name="..."` strings that are already embedded in
  the docx's EndNote field blobs (`endnote_biblio_check.py`'s `check_reference_types()` does
  exactly this — it reads the **rendered name string**, not the raw integer, so it is immune to
  this per-library code-index trap). Prefer that over a raw `SELECT reference_type` count when
  diagnosing which records are mis-typed.
- If you must read the raw integer from SQLite (e.g. to build an UPDATE target list), first
  resolve the code↔name mapping for *this* library by querying a handful of already-known-good
  records of each type (a confirmed Journal Article record, a confirmed Book Section, etc.) and
  reading their `reference_type` value — do not assume 17/27/12/47/0 from another library or
  from this skill's table.

⚠️ **CRITICAL — reference_type MUST be set explicitly, never left to default (a real incident).**
If `reference_type` is passed as 0/NULL/empty or omitted, EndNote does NOT show it as "Journal Article" — it renders the record with the **"Bill"** template (EndNote's alphabetically-first reference type), so the bibliography loses journal-name italic + bold volume and the whole entry comes out in the wrong format. In one real run **33 records were silently created as Bill + 2 as Generic** exactly this way, and the error is invisible in the EndNote UI (only the bibliography output reveals it).
- **Default to 17 (Journal Article) and pass it as an integer literal**, not a variable that might be None. For every INSERT, assert `reference_type is not None and reference_type != 0` unless the ref is genuinely a book chapter (`Book Section` code) / report (27) / web page (12).
- Book chapters → look up the correct EndNote `Book Section` code in the target library (query an existing known-good book-section record's `reference_type`); do not leave them as 17.
- **Post-INSERT audit (mandatory):** re-query every id you inserted and confirm `reference_type` is the intended code. Add this to the Phase 6 audit alongside the `\r` author check:
  ```python
  bad = c.execute("SELECT id, reference_type, secondary_title FROM refs WHERE id IN (%s) AND reference_type NOT IN (17,27,12,47,<book_section_code>)" % ",".join("?"*len(ids)), ids).fetchall()
  assert not bad, f"wrong reference_type (Bill/Generic leak): {bad}"
  ```

## Triggers (auto-fire on INSERT)
- `refs__refs_ord_AI`: populates `refs_ord` (uses EN_MAKE_SORT_KEY)
- `refs__ref_props_AI`: populates `ref_props`
- `refs__ret_watch_AI`: populates `ret_watch`
- `refs__tag_members_AI`: populates `tag_members`

**No need to manually populate** these auxiliary tables.

## sync table (potential issue)

The `sync` table tracks which refs are sync-eligible. New records inserted directly do NOT get sync entries automatically. **EndNote CWYW search may fail to find newly inserted records** until either:
- User runs EndNote → Tools → Recover Library
- Or sync entry is added manually:
  ```python
  c.execute("""INSERT INTO sync (type, item_id, item_id2, guid, usn, action,
              status, file_timestamp, file_checksum, action_timestamp,
              changed_membership_timestamp, changed_readstatus_timestamp,
              changed_rating_timestamp, changed_trash_timestamp,
              reserved1, reserved2, reserved3, reserved4)
              VALUES (1, ?, '', ?, 0, 0, 0, 0, 0, ?, 0, 0, 0, 0, 0, 0, 0, '')""",
              (new_id, str(uuid.uuid4()), int(time.time())))
  ```

## Lock check

Before INSERT, verify EndNote is closed:
```python
try:
    stream = open(db_path, 'rb+')
    stream.close()
except IOError:
    raise RuntimeError("DB locked — close EndNote 2025 first")
```

## Author normalization

After INSERT, audit and fix:
- Replacement chars (`\xef\xbf\xbd` from RIS encoding errors): restore proper unicode (ø, é, ä)
- Long corporate names → short forms matching inline citation: 'FAO' not 'Food and Agriculture Organization (FAO)', 'BSH Ingredients' not 'BSH Ingredients GmbH'

This match between author field and inline citation key is what makes EndNote CWYW resolve `{Author, Year #N}`.
