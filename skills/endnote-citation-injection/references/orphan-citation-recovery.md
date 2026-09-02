# Phase 6.1 — Orphan citation recovery (body cites a rec-number with no backing record)

Full detail for the reverse failure mode of Phase 6.0: the docx body already contains an EndNote field citing a
specific rec-number (`{Author, Year #901}`), but that id has **no matching row in `refs`** —
either the record was deleted from the library after the citation was inserted, or the citation
was hand-typed/copy-pasted with a guessed/wrong id, or it came from a different library the
document was once linked to. Symptom in Word: the citation renders as **unformatted / raw
brace text** (`{Author, Year #901}` shown literally) instead of the formatted `(Author, Year)`
output, and EndNote's Find Citation(s) turns up nothing for that id.

## Diagnosis

```python
c.execute("SELECT id FROM refs WHERE id = ?", (901,))
# empty result confirms the id is a true orphan, not a lock/sync-table issue
```
Cross-check against `check_invalid_citations()` in `endnote_biblio_check.py` — an orphan
rec-number usually surfaces there as a rendered/unresolved citation, not a clean `instrText`
field (distinguish this from the ordinary "sync table missing" pitfall, which affects
records that DO exist but aren't yet CWYW-searchable — see `references/endnote-sqlite-internals.md`).

## Recovery procedure

1. Identify the intended paper from the surrounding text/context (author/year the citation
   claims, or the manuscript's own reference list draft if one exists).
2. Resolve/verify via DOI (CrossRef + OpenAlex dual-check, same as Phase 2) — never guess a
   replacement id or fabricate metadata.
3. **Add the record to the library first** (via this skill's normal Phase 6 INSERT path, with
   `reference_type` forced correctly per the rule in `references/endnote-sqlite-internals.md`), obtaining a **new, real** rec-number.
4. **Re-link the existing citation in Word, do NOT hand-edit the field text.** Use EndNote's
   **Edit & Manage Citation(s)** dialog (select the citation in Word → CWYW → Edit & Manage
   Citations) and use "Insert" / replace-with-search to point the citation at the newly added
   record. This rewrites the field's underlying `fldData` correctly (record link + guid), which
   a manual text edit of the brace content cannot do — hand-editing the visible
   `{Author, Year #N}` text does not repair the field's internal EndNote link.
5. Re-run Update Citations and Bibliography, then `endnote_biblio_check.py` to confirm the
   citation now renders formatted and is no longer flagged as invalid/rendered-orphan.

**Do not**: silently renumber to a nearby existing id that "looks close enough" — that
attaches the citation to the WRONG paper's metadata. If the intended paper cannot be identified
with confidence, treat it like a Phase 3 hallucination case (flag for user DROP/REPLACE
decision) rather than guessing.

## Custom placeholder forms

Body citations are not always `(Author, Year)`. This skill also handles pre-seeded
placeholders like `[REF:34]` / `[REF:87-91]` (inserted by an earlier editing pass).
Treat them as opaque find-strings: partition the run on the placeholder and wrap the
placeholder in `<w:del>`, the `{Author, Year #id}` in `<w:ins>` (Phase 7). Multi-ref
placeholders (`[REF:87-91]`) expand to one brace group with `;`-separated cites:
`{Seo, 2019 #520; Chong, 2022 #548; ...}`.
