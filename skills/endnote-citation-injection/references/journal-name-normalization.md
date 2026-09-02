# Journal name normalization + the frozen-abbreviation problem

Full detail for Phase 6: how to normalize `secondary_title` before INSERT,
the CASSI term-list import procedure, term-list hygiene (duplicate rows),
and the frozen-`fldData` problem that survives a normal Update Citations.

## Journal name normalization (a real incident — MUST normalize before INSERT)

**Do NOT write the raw `container-title` from CrossRef / OpenAlex / PubMed straight into `secondary_title`.** Those sources return the journal name inconsistently — CrossRef gives full names (`Green Chemistry`), PubMed gives no-period abbreviations (`J Org Chem`), OpenAlex varies, and some carry PubMed-only suffixes (`(Tokyo)`, `(Amst)`, `Engl`) or unescaped entities (`&amp;`). Writing these raw produced a bibliography with **mixed abbreviated/full names and inconsistent periods** across the reference list (a manuscript run).

**Store the full journal name in `secondary_title`, then let EndNote's Journals Term List + style do the abbreviation** — this is the correct division of labor (the style's "Journal Name Format = Abbreviation 1" + "Remove periods" toggle switches abbreviation per target journal, so the DB should hold the canonical FULL name):

1. **Normalize `secondary_title` to the canonical full journal title.** Strip PubMed suffixes (` (Tokyo)`, ` (Amst)`, trailing ` Engl`), un-escape HTML entities (`&amp;` → `&`), expand known no-period abbreviations to full names when confident.
2. **Provide the term-list mapping** so the style can abbreviate. RSC/chemistry uses **CASSI**, not ISO4. EndNote ships the official CASSI list at:
   ```
   C:\Program Files (x86)\EndNote <year>\Terms Lists\Chemical.txt
   ```
   3-column tab-separated: `Full Name <tab> Abbrev-with-periods <tab> Abbrev-no-periods` (e.g. `Journal of Organic Chemistry\tJ. Org. Chem.\tJ Org Chem`). Import it via **Library → Open Term Lists → Journals → Import List** into the target library, then set the style's **Journal Name Format = "Abbreviation 1"** (periods) or add "Remove periods" for no-period journals.
   - For journals missing from `Chemical.txt` (newer titles like *Green Chem.*, *ACS Sustainable Chem. Eng.*), look up the CASSI abbreviation at https://cassi.cas.org and add via "New Term".
3. **Never rely on the raw source string being RSC-correct.** The term-list layer is what guarantees consistency; the DB field just needs the clean full name that matches a term-list "Full Name" entry.

**Term list hygiene — duplicates are the #1 cause of "abbreviation just doesn't apply" (260715 finding):**
- **No duplicate term rows for the same journal.** Importing `Chemical.txt` (or any RIS/term-list
  import) merges with the library's existing Journals term list rather than replacing it — if the
  library already had a manually-added row for a journal (e.g. from an earlier RIS import), the
  import creates a **second** row for the same journal. EndNote's abbreviation matching gets
  confused across duplicate "Full Name" entries for the same title and silently fails to abbreviate
  — this looked identical to a missing term-list entry until the duplicate was found and removed.
  Before importing, or when abbreviation isn't applying despite the term existing, open Term Lists
  and check for duplicate rows for the journal in question; delete the extra one (see
  `references/endnote-sqlite-update-rules.md`'s ENCI_Base/REINDEX safe path for `jterms` — this is
  exactly the table it applies to).
- **The record's `secondary_title` must match a term-list "Full Name" EXACTLY, character-for-character**
  — `&` vs `and`, capitalization, and especially `&amp;` (unescaped entity leaking into the stored
  string) vs `&` all count as a non-match, and a non-match means no abbreviation is applied (the
  full name renders as-is instead). When a specific reference won't abbreviate but others in the
  same journal do, diff the exact `secondary_title` string against the term-list "Full Name" byte
  for byte before assuming the term list itself is incomplete.
- **Reference list text lives in the `EN.REFLIST` field, not the docx body — editing docx text
  directly does nothing.** The formatted bibliography paragraphs are a live EndNote field; any
  hand-edit to the visible reference-list text in Word is silently overwritten the next time
  "Update Citations and Bibliography" runs (or even on save, depending on CWYW settings). Fix the
  underlying **record** (`secondary_title`) or the **term list**, never the rendered reflist text.
- **"Open Term Lists" showing "database does not contain any Term Lists"** has been observed as a
  transient index/UI glitch, not an actual empty term list — restarting EndNote resolved it in this
  session. Don't conclude the term list was wiped/corrupted from this message alone; restart first
  and re-check before treating it as data loss.

## ⚠️ Frozen-abbreviation problem: term-list import + Update Citations is NOT always enough (260715 finding)

Each in-text/bibliography citation's rendered text is stored as **`fldData` (a frozen snapshot)**
inside the docx field, captured at the moment the citation was last formatted. Importing the
Journals Term List and running **Edit & Manage Citations → Update Citations and Bibliography**
re-runs the style against the *current* `secondary_title` + term list — but if a reference's
`fldData` was frozen *before* the term list existed (or before `secondary_title` was normalized),
some entries do **not** get re-abbreviated even after Update. Symptom: after importing
`Chemical.txt` and running Update, most journal names abbreviate correctly but a handful stay as
full names / inconsistent abbreviations — those are the frozen ones.

**Fix — force a full re-format instead of an incremental Update:**
1. Select the whole bibliography / whole document.
2. **Edit & Manage Citations → Convert Citations and Bibliography → Convert to Unformatted
   Citations.** This strips all `fldData` snapshots back to the raw `{Author, Year #id}`
   unformatted form — nothing left frozen.
3. **Convert back: Convert Citations and Bibliography → Convert to Formatted Citations** (or
   simply re-open/re-save with CWYW on, which triggers a full reformat), which rebuilds every
   `fldData` snapshot from scratch against the *current* term list + style. This is the only way
   to guarantee no citation is silently exempt from the abbreviation pass.
4. Re-run `endnote_biblio_check.py` (`check_non_cassi_journal`) after this round-trip to confirm
   the frozen entries are gone — do not assume "I ran Update, so it must be fixed" (see C-40:
   this is exactly a "distrust self-report, re-parse ground truth" case).

Do this Unformatted→Formatted round-trip **any time** the term list is imported/edited, the
style's Journal Name Format is changed, or `secondary_title` values are corrected on existing
records — a plain "Update Citations" is not guaranteed to touch already-frozen fields.
