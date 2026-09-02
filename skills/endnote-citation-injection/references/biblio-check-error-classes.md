# `endnote_biblio_check.py` — 7 detected error classes (260714/260715)

Full catalog of what the post-render QC gate (`manuscript-pipeline/scripts/endnote_biblio_check.py`) detects from `word/document.xml` (zipfile-only, no Word open, EndNote fields
untouched). Run as:
```
python skills/manuscript-pipeline/scripts/endnote_biblio_check.py <manuscript.docx>
python skills/manuscript-pipeline/scripts/endnote_biblio_check.py <manuscript.docx> --strict   # exit 1 if any error (gate)
```

1. **reference_type wrong** — records rendered as Bill/Generic instead of Journal Article (the root cause of a real incident — 33 Bill + 2 Generic were caught this way; fix via EndNote **Library → Find and Replace → In: Reference Type → Bill → Journal Article** bulk change, [Clarivate KB](https://support.clarivate.com/Endnote/s/article/EndNote-Change-reference-type-for-many-records)).
2. **INVALID CITATION** — split rendered (`w:t`, unrecoverable) vs field (`instrText`, fixed by Update).
3. **journal italic missing** — RSC italicizes every journal name; a reflist paragraph with no italic run is flagged.
4. **author omission** — reference starting `Surname, Journal` (no initials/co-authors) — the SQLite-INSERT-with-single-surname bug.
5. **`&amp;` entity breakage** — double/unescaped entities in rendered text (fixed 260715 to only flag true double-escape `&amp;amp;`, not normal single-escaped `&amp;` which renders correctly).
6. **non-CASSI journal** — multi-word italic journal name with no periods (PubMed-style) or un-abbreviated full name.
7. **missing reflist entries** (260715) — body/table superscript citation numbers exceed the reference list's max entry number, meaning cited numbers have no backing reference (found in a manuscript's SI: body cited 15–30, list only had 1–14).

Make this a mandatory pre-submission gate for any EndNote manuscript (run with `--strict` in a
checklist). It is the verification half of "never wrong again": the INSERT-side fixes
(reference_type=17, journal normalization) prevent the error; this checker catches any that
still slip through (GUI edits, RIS imports, legacy records).
