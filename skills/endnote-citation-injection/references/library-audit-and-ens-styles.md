# Library quality audit and output styles

## Library quality audit - `endnote_library_audit.py`

Two defect axes the rest of the toolchain leaves uncovered, both read-only:

| axis | classes | why the existing gates miss it |
|---|---|---|
| author notation | `A0_no_author` - `A1_no_separator` - `A2_lf_separator` - `A3_replacement_char` - `A4_corporate_longform` - `A5_malformed_initial` - `A6_no_comma` | `reference_validator.py --endnote-db` covers only A1 (separator absent). An LF separator folds the whole list into one author, and EndNote's UI renders LF and CR identically, so nothing shows it. A corporate author in long form stops `{Author, Year #N}` from resolving and prints as the last word of the name. |
| DOI accuracy | `D0_missing_doi` - `D1_malformed` - `D2_unresolvable` - `D3_context_mismatch` - `D3b_resolves_other_paper` - `D4_unverified` - `D5_openalex_year_differs` | `reference_validator.check_dois()` is DOCX-driven: it verifies the DOIs printed in one manuscript. A record no manuscript cites yet is never reached. In one run: 475 records, 161 referenced, **314 DOIs never verified by anything**, three of them with an article number glued on. |

```bash
"$PY" endnote_library_audit.py                  # both axes
"$PY" endnote_library_audit.py --offline        # author axis only, no network
"$PY" endnote_library_audit.py --doi-limit 40   # bound the network pass; verdicts cached
```

Exit codes follow the `verification-gates` contract: **0 clean / 1 review / 2 could not run**, and
a 2 is never read as a pass. It reuses `reference_validator._crossref_check` (found next to the
`manuscript-pipeline` skill) rather than a second CrossRef client, and adds OpenAlex as an
independent second opinion. Set `CROSSREF_EMAIL` (or `RESEARCH_CONTACT_EMAIL`) for the polite
pool. Repairs never go through this tool: it only reports, so a false positive cannot corrupt the
library. Apply fixes with `safe_refs_update.py`.

Two caller traps, both caught by running the tool rather than reading it:
`_crossref_check(ctx_surnames=...)` needs a **set of LOWERCASED** surnames (a list raises
TypeError; mixed case flagged 9 of 9 correct DOIs as `mismatch_weak`), and `sqlite3.connect` is
lazy, so a file that is not a database opens cleanly and fails on the first query: wrap the query
or a blind run exits 1 and reads as "findings to review".

## Output styles (.ens) from Python - `ens_style.py`

`.ens` files were GUI-only; the format is now reverse-engineered (layout in the module
docstring). Evidence, in order of strength: every one of the 503 shipped styles plus a user's own
styles round-trips byte-identical; and a style edited in Python (Journal Article: a marker after
Year, Volume bold switched off), selected through `EN.Layout` on a manuscript copy and rendered by
`cwyw_update.py`, came out with exactly those two changes in the bibliography.

```bash
"$PY" ens_style.py templates "Some Journal.ens" --type "Journal Article"
#   Journal Article  Author. Year. Title. *Journal*,.**Volume**(Issue),.Pages.<end>
"$PY" ens_style.py set-template IN.ens "<Styles dir>/NEW NAME.ens" \
      --type "Journal Article" --field 7 --bits 0      # Volume no longer bold
"$PY" ens_style.py info STYLE.ens                     # name, based-on, author-list rules
```

Use it to read what a journal style really does before a reformat (`templates` shows the same
notation as the GUI's template editor, `^` = singular^plural), to diff two styles, or to make a
small, named variant. Limits: only the bibliography section (1002) is named; other panels are
preserved byte-for-byte but not interpreted; a text edit that changes length over an inner
formatting run is refused. Select the new style in a document, then run `cwyw_update.py`
(guarded). Tests: `tests/test_ens_style.py`.
