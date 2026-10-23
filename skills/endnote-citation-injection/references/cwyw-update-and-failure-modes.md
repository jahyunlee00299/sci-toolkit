# Running "Update Citations and Bibliography" from Python

`cwyw_update.py` drives EndNote's Cite-While-You-Write macro on a Word document. Use it only as
the single pre-submission formatting run described in SKILL.md ("Default: insert unformatted,
format once before submission"), on a document with no tracked changes. The two failure modes
below are why it is not part of the editing loop.

## Usage

```bash
"$PY" cwyw_update.py "path/to/manuscript.docx"   # open -> ENFormatBibliography -> save
"$PY" cwyw_update.py --attached                   # use the document already open in Word
```

An earlier note said CWYW could not be automated (`Application.Run` raised "RPC server
unavailable"). The cause was `win32.Dispatch("Word.Application")`, which starts Word in
automation mode **with no COM add-ins**, so the EndNote macro did not exist in that instance.
Opening the document normally and attaching to that session works: `os.startfile(docx)` (a full
Word session, add-ins load) -> `GetActiveObject` -> verify `EndNote.WordAddin.Connect` is
connected -> `Application.Run("ENFormatBibliography")` -> `Save()`. Verified on Word 16 +
EndNote 2025: 173 `{Author, Year #RN}` markers became fields and a 57-entry bibliography was
generated with `INVALID CITATION 0`. `VBProject` enumeration stays blocked (it needs "Trust
access to the VBA project object model") and is not required.

Always re-verify the result: `manuscript-pipeline/scripts/endnote_biblio_check.py` and
`manuscript-pipeline/scripts/reference_validator.py`, and read every rendered citation against
its sentence.

## Guarded by default: `cwyw_guard.py` + `en_fields.py`

`cwyw_update.py` wraps the macro in three gates (`--no-guard` turns them off):

1. **precheck** (`cwyw_guard.py precheck doc.docx`) - BLOCK on a tracked-deleted citation field
   (resurrection, below), a cite whose `db-id` is not this library's (CWYW would resolve its
   RecNum against the wrong library), or a RecNum missing from / trashed in the library; WARN on
   other tracked changes (the SHIFT case below) and on **husk fields**. `--force` overrides a
   BLOCK.
2. **unhusk** - an `EN.CITE` field whose fldData collapsed to one byte (`PB==`, produced by
   accepting tracked changes around a field) and whose result is still `{Author, Year #N}`.
   Measured on a copy of a real manuscript: CWYW turned all three such fields into
   `!!! INVALID CITATION !!!` with RecNum 0, in the body and the bibliography. `Field.Unlink()`
   loses nothing (the field holds only its result), so `cwyw_update.py` unlinks them, untracked,
   before the macro; the same copy then came out with every group verified and
   `INVALID CITATION 0`. `--keep-husks` disables it.
3. **verify** - the citation groups (RecNum tuples, document order) snapshotted before the macro
   are aligned with the fields after it. Adjacent groups may merge and reorder inside a group
   (CWYW does that legitimately); a different record at a position (SHIFT), a record that
   existed only in deleted citations (RESURRECTED), an unconverted marker, or an author-year
   rendering that does not name the record's first author and year fails with **exit 4**.

The reader underneath, `en_fields.py`, is the documented answer to "a flat begin/end parser
mis-pairs the nested field": it walks the XML with a field stack, decodes inline payloads and
the nested `EN.CITE.DATA` fldData (plain base64 of UTF-8 `<EndNote>` XML, no compression), reads
`{...#N}` markers at their position in the paragraph, and flags `<w:del>`/`<w:ins>`.
Tests: `"$PY" tests/test_cwyw_guard.py` (synthetic SHIFT / RESURRECTION / merge / husk cases).

## A tracked-DELETED citation field does NOT survive CWYW

Replacing citation A with citation B is the common case (a wrong record, a book chapter swapped
for the paper that actually reports the result). The obvious route - delete the old field with
`Field.Delete()` while `TrackRevisions = True`, insert `{Author, Year #B}`, run CWYW - **puts the
old citation back**. `ENFormatBibliography` rewrites every citation field and does not preserve
the `<w:del>` wrapping. Measured on one manuscript pass, it failed two different ways in the same
document:

| site | what CWYW did | accepted text |
| --- | --- | --- |
| marker inserted directly against the deleted field | **merged** both into one live field | `(Smith et al., 2011a; Smith et al., 2011b)` |
| marker and field adjacent but separate | kept the field separate, kept `<w:del>` on the `fldChar`s only - **not** on the result run | `(Smith et al., 2011b)(Smith et al., 2011a)` |

Both resurrected the record the edit existed to remove, and both passed a Word validation,
`docx_preflight --strict`, `INVALID CITATION 0` and `endnote_biblio_check` with zero findings.
The `a`/`b` year suffixes in the accepted text were the only visible symptom, and they are easy
to read as a legitimate disambiguation. The detector is a word-level accept diff against the
parent docx, plus a field census keyed on `<rec-number>`.

A tell at the deletion step itself: `doc.Fields.Count` **does not drop**. Tracked `Field.Delete()`
reported `fields 74 -> 74`; the untracked delete of the same three fields reported
`fields 74 -> 71`.

**Supported route: delete the old field untracked, then insert the replacement tracked.**

```python
doc.TrackRevisions = False                 # the field removal only
for fl in [f for f in doc.Fields if (f.Result.Text or '').strip() == OLD_RENDERED]:
    fl.Delete()
doc.Save()
# then insert '{Author, Year #B}' as a tracked change and STOP; the pre-submission run formats it
```

Nothing is lost to the reviewer: the replacement arrives as a tracked insertion, and when A and B
render the same string the rendered text does not change at all - only the record behind it,
which is the edit. Removing the field first also makes the surrounding text edits ordinary string
work, because Word's Find cannot match across a tracked deletion.

Order matters when a record edit is also due: **fix the library first, then run CWYW once.**
CWYW prints whatever the record says at that moment, so an issue-number or author fix applied
afterwards needs a second CWYW pass. `safe_refs_update.py` refuses to run while EndNote is open,
and `cwyw_update.py` needs EndNote running, so the sequence is: close EndNote ->
`safe_refs_update.py --apply` -> `cwyw_update.py` (which relaunches it).

## CWYW can shift EVERY citation in the document by one position

A worse failure from the same pass. After three **multi-record** fields were hard-deleted (two
records each) and six markers inserted into a document carrying 74 tracked revisions,
`ENFormatBibliography` rendered every citation one position off - the new markers and the fields
it was never asked to touch alike:

| site | should render | actually rendered |
| --- | --- | --- |
| new marker, record A | (Author A et al., 1998) | (Author X et al., 2019) |
| new marker, record B | (Author B & Author C, 1969) | (Author Y et al., 1995) |
| **untouched** field, record D | (Author D et al., 2015) | (Author Z et al., 2014) |

Word reported `fields 74 -> 75` and `saved: True`; `endnote_biblio_check` reported
`INVALID CITATION 0`; `docx_preflight --strict` and a Word validation passed. Every field still
held a valid, well-formed citation - just the wrong one, which is why no gate sees it. Two
independent Word sessions from the same clean input reproduced the identical shift, so it is
deterministic, not a crash artifact.

**After every CWYW run, read the rendered citations against their sentences.** `cwyw_update.py`
does the positional half automatically (verify, exit 4); reading against the sentence still
matters for numbered styles, where the rendering carries no author. A field census keyed on
`<rec-number>` is not enough, and a flat begin/end field parser will itself mis-pair the nested
fields, which can make a correct document look broken.

Two operational rules this produced:
- **Kill every Word process before running.** One attempt attached to a stale snapshot still
  open in Word and formatted that instead.
- **A crashed `doc.Save()` leaves the file untouched**, so re-running after a disconnect is safe.

When the formatting step cannot be trusted, the safe delivery is to promote the text edits with
the citations left as unformatted `{Author, Year #Rec}` markers: they are visible, recoverable,
and break nothing. Suspected cause, untested: EndNote's per-document record cache (`docVar`)
losing step with the field order once multi-record fields are removed from a document that also
carries tracked revisions. Reproduce on a copy with revisions accepted before trusting CWYW on
such a document again.

One benign artifact to expect afterwards: `reference_validator.py` gains `empty_field_result`
warnings equal to the number of new `ADDIN EN.CITE.DATA` splits (a large citation blob is stored
as an outer `EN.CITE` field plus a nested `EN.CITE.DATA` field holding only data). Confirm by
counting `EN.CITE.DATA` instrText elements before and after (7 -> 10 matched 3 new warnings
exactly) and by checking the rendered text is unchanged. It is a parser artifact, not a defect.
