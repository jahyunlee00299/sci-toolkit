# EndNote SQLite internals (reference for diagnosis only)

**Do not hand-write an INSERT or UPDATE from this page.** Records are added with `en_insert.py`
and edited with `safe_refs_update.py`; they use the real sort key (`en_make_sort_key.py`) and
real collation (`enci_base_collation.py`) and carry the type, author, journal, DOI-duplicate and
markup refusals. The snippets below describe what those tools do internally, so a failure can be
read. A hand-written INSERT built from them skips every refusal.

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

Fix for existing records: a `safe_refs_update.py` spec with the corrected `author` list (joined
with ``); never a bare `UPDATE ... REPLACE(author, x'0A', x'0D')` on a shared library. See
`references/endnote-sqlite-update-rules.md`.

**Reference type** is never typed as a number: see `references/reference-types.md`. Left unset or
copied from another numbering, it renders as Bill (17 on a stock install) with no UI-visible
error; `en_insert.py` resolves the code from the type NAME and re-reads every inserted row.

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
- Long corporate names → short forms matching inline citation: 'FAO' not 'Food and Agriculture Organization (FAO)', 'Acme Ingredients' not 'Acme Ingredients GmbH'

This match between author field and inline citation key is what makes EndNote CWYW resolve `{Author, Year #N}`.
