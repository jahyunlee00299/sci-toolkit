# Reference type codes: resolve by NAME, never by number

Three different numberings are in play, and mixing them is how records end up with the wrong
bibliography template.

| scheme | where it appears | example |
| --- | --- | --- |
| EndNote XML `ref-type` number | inside a formatted citation field: `<ref-type name="Journal Article">17</ref-type>` | Journal Article = 17 |
| sqlite `refs.reference_type` | the `refs` table of `sdb.eni` | Journal Article = 0, **17 = Bill** |
| user-defined order | a customised installation | anything |

The sqlite code table lives per **installation**, in `%APPDATA%\EndNote\RefTypeTable.xml`
(`<RefType id=".." name="..">`); the library's own `misc` table carries none. Measured on a stock
EndNote 2025 install, and matching every code a mature library actually used:

| code | type | | code | type |
|---|---|---|---|---|
| 0 | Journal Article | | 12 | Audiovisual Material |
| 1 | Book | | 15 | Patent |
| 3 | Conference Proceedings | | 16 | Web Page |
| 7 | Book Section | | 17 | **Bill** |
| 10 | Report | | 27 | **Equation** |
| | | | 31 | Generic |

Treat the table as an illustration of the trap, not as a lookup: read the installation's own file.

```python
import en_reftypes
types = en_reftypes.load()                         # reads RefTypeTable.xml
code = en_reftypes.code_for("Journal Article", types)
```

`en_insert.py` and `safe_refs_update.py` resolve the type this way, and `en_insert.py` refuses a
spec without a `type`.

## Why this page exists (incidents)

- **Left unset renders as Bill.** A record inserted with `reference_type` 0/NULL/omitted on an
  install where 17 is Bill, or with the "default" copied from another source, renders with the
  Bill template: journal-name italics and bold volume vanish, and the EndNote UI shows no error.
  One run produced 33 Bill and 2 Generic records this way.
- **"Default to 17 (Journal Article)" was wrong.** An older version of this skill said exactly
  that. 17 is Bill in the SQLite column; it is Journal Article only in the XML numbering.
  Following the advice created the very records it warned about.
- **27 is Equation, not Report; 12 is Audiovisual Material, not Web Page.** Eight reports and
  patents had been stored as 27, so each printed with the Equation template. Confirmed from the
  formatted field (`<ref-type name="Equation">`).
- **An audit filter such as `reference_type NOT IN (17,27,12,47,...)` passes bad records.** It is
  built from the wrong numbering, so Bill, Equation and Audiovisual rows are all on its "allowed"
  list. Never write one. Compare names, or let `endnote_library_audit.py` and
  `endnote_biblio_check.py` do it.

## How to confirm a type

1. `endnote_biblio_check.py` reads the **rendered name** (`<ref-type name="...">`) from the
   fields of a manuscript, so it is immune to every numbering trap. Only Bill, Generic and
   Equation are flagged: Book, Patent, Report, Thesis and the like are legitimate.
2. For a raw SQLite reading, map the code through `en_reftypes.load()`. If the XML file is
   missing, query a few known-good records of each type, or check the GUI's Reference Type
   drop-down, which is the final authority for what a code renders as.
3. The sort-key table `en_make_sort_key.TYPE_NAMES` must carry the name of any code you store, or
   `safe_refs_update.py` stops at the rehearsal with a sort-key mismatch (it stopped exactly this
   way for the Patent code before the live file was touched).

## Fixing wrong types

Never a hand-written `UPDATE`. Put the type in a spec and let `safe_refs_update.py` rehearse,
back up and verify (`references/endnote-sqlite-update-rules.md`):

```json
{ "123": {"reference_type": 15} }
```

with the code taken from `en_reftypes.code_for("Patent", en_reftypes.load())`, not typed from
memory.
