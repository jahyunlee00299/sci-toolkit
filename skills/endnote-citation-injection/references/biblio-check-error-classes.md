# `endnote_biblio_check.py` — 7 detected error classes (260714/260715)

Full catalog of what the post-render QC gate (`manuscript-pipeline/scripts/endnote_biblio_check.py`) detects from `word/document.xml` (zipfile-only, no Word open, EndNote fields
untouched). Run as:
```
python skills/manuscript-pipeline/scripts/endnote_biblio_check.py <manuscript.docx>
python skills/manuscript-pipeline/scripts/endnote_biblio_check.py <manuscript.docx> --strict   # exit 1 if any error (gate)
```

1. **reference_type wrong** — records rendered as Bill, Generic or Equation (the root cause of real incidents: 33 Bill + 2 Generic from an unset type, and reports/patents stored under a code that renders as Equation). Judged by the rendered NAME only, because the XML number, the sqlite code and a user-defined order all differ (`references/reference-types.md`). Book, Patent, Report, Thesis and similar are legitimate and are not flagged. Fix with `safe_refs_update.py --spec`, the code resolved from the type name.
2. **INVALID CITATION** — split rendered (`w:t`, unrecoverable) vs field (`instrText`, fixed by Update).
3. **journal italic missing** — RSC italicizes every journal name; a reflist paragraph with no italic run is flagged.
4. **author omission** — reference starting `Surname, Journal` (no initials/co-authors) — the SQLite-INSERT-with-single-surname bug.
5. **`&amp;` entity breakage** — double/unescaped entities in rendered text (fixed 260715 to only flag true double-escape `&amp;amp;`, not normal single-escaped `&amp;` which renders correctly).
6. **non-CASSI journal** — multi-word italic journal name with no periods (PubMed-style) or un-abbreviated full name.
7. **missing reflist entries** (260715) — body/table superscript citation numbers exceed the reference list's max entry number, meaning cited numbers have no backing reference (found in a manuscript's SI: body cited 15–30, list only had 1–14).

Make this a mandatory pre-submission gate for any EndNote manuscript (run with `--strict` in a
checklist). It is the verification half of "never wrong again": the INSERT-side fixes
(`en_insert.py`: type by name, journal normalization) prevent the error; this checker catches any that
still slip through (GUI edits, RIS imports, legacy records).
