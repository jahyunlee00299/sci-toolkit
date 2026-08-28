---
name: endnote-citation-injection
description: Inject EndNote unformatted citations (`{Author, Year #N}`) into a Word docx using Track Changes. Covers ref harvesting from a separate refs docx, DOI verification (CrossRef + OpenAlex cross-check), hallucination detection, alternative paper substitution, EndNote SQLite direct INSERT (bypassing manual RIS import), and lxml-based docx editing that preserves namespaces, places citations before periods, removes leading spaces, and survives Word's integrity check. Use when a thesis/manuscript draft has parenthetical (Author, Year) citations that need to be converted to EndNote `{Author, Year #RecordNumber}` form so EndNote 2025 + Word can render formatted bibliographies.
---

# EndNote Citation Injection

End-to-end pipeline that takes a draft Word docx with parenthetical citations and produces a Word docx with EndNote unformatted citations as Track Changes — every citation is reviewable and rejectable, the docx survives Word's integrity check, and the EndNote library is updated in place so the citations resolve.

## When to Use

Trigger this skill when the user asks any of:
- "이 docx 본문 인용을 EndNote 형식으로 바꿔줘"
- "(Author, 2020) → {Author, 2020 #N} 변환"
- "EndNote 라이브러리에 ref 추가하고 본문 인용 매칭"
- "별도 refs.docx에 reference list 있는데 본문 docx에 적용"
- The user is using (Author, Year) style citations and wants to convert them to EndNote unformatted form

Do NOT use when:
- User wants pure RIS export/import for a third party (use a simpler RIS-only flow)
- DOI verification only without docx editing (use a CrossRef agent directly)

## Execution Method

A non-trivial run (≥10 refs) splits into four roles. Use **whatever delegation
mechanism your agent provides** — a sub-agent/task tool under Claude Code,
`spawn_agent` under Codex. Do not hard-code one vendor's API here; if your agent
has no delegation at all, run the roles sequentially in one context instead.

- **coordinator** — user decisions, orchestration, and the direct DB INSERT
- **crossref-verifier** — CrossRef DOI verification + RIS generation
- **openalex-verifier** — OpenAlex cross-check + new-ref verification
- **ref-resolver** — hallucination recovery + citation rewrite plan

For ≤5 refs, skip delegation — the overhead of spinning up separate contexts
exceeds the work (§6). Whichever way you run it, the verification gate applies
unchanged: a sub-agent reporting "done" is not evidence, so re-read the actual
output before trusting it (§2).

## Pipeline (10 phases)

```
Phase 0: Backup + working area setup
   ↓
Phase 1: Two-docx analysis (refs source + body target)
   ↓
Phase 2: DOI dual verification (CrossRef + OpenAlex)
   ↓
Phase 3: Hallucination recovery (alt paper search)
   ↓
Phase 4: User decision gates (DROP/REPLACE/alt confirmation)
   ↓
Phase 5: Citation rewrite plan (multi-run aware mapping)
   ↓
Phase 6: EndNote DB INSERT (lxml stub functions)
   ↓
Phase 7: lxml Track Changes apply (period-aware)
   ↓
Phase 8: Integrity verification (xmlns + python-docx)
   ↓
Phase 9: User Word review
   ↓
Phase 10: OneDrive overwrite + DB author normalization
```

---

## Phase 0 — Backup + Working Area Setup

Before any edit:

1. **Local docx backup** (always):
   ```bash
   cp "<original>.docx" "<original>.backup-<YYYYMMDD>.docx"
   ```
2. **EndNote DB backup** (mandatory before any DB write):
   ```bash
   cp "$ENDNOTE_DATA/sdb/sdb.eni" "$ENDNOTE_DATA/sdb/sdb.eni.refs-backup-<YYYYMMDD>"
   ```
   Where `$ENDNOTE_DATA = ~/Documents/My EndNote Library_2025.Data/`
3. Working dir: `~/AppData/Local/Temp/refs_work/` (Windows) — short path, no OneDrive sync
4. Copy both target docx files to working dir as `v2.docx` (body target) and `v2_refs.docx` (refs source)

## Phase 1 — Two-docx Analysis

Goal: extract ref entries from `_refs.docx` and citations + ref section from `_v2.docx`.

```python
from docx import Document
import re

doc_refs = Document("v2_refs.docx")
doc_body = Document("v2.docx")

# Extract refs from refs.docx (typically last 30+ paragraphs)
refs = []
for i, p in enumerate(doc_refs.paragraphs):
    t = p.text
    if re.search(r'\bdoi\s*[:.]?\s*10\.', t, re.IGNORECASE):
        refs.append({'idx': i, 'text': t})

# Extract parenthetical/narrative citations from body
pat_paren = re.compile(r'\([A-Z][A-Za-zçéèáñ\-]+(?:\s+et\s+al\.)?(?:,?\s*&\s*[A-Z][A-Za-z\-]+)?,?\s*\d{4}[a-z]?\)')
pat_narrative = re.compile(r'[A-Z][A-Za-z\-]+(?:\s+et\s+al\.|\s+and\s+[A-Z][A-Za-z\-]+)?\s+\(\d{4}\)')
```

**Output**: `extraction_report.md` listing all ref entries (with DOI), all body citations (with paragraph indices), and the ref section in v2.docx (often incomplete).

## Phase 2 — Dual DOI Verification

**Critical**: never trust a single API. Hallucinated DOIs are common.

Spawn two agents in parallel with the same `refs_to_verify.json`:

### Agent 1 — `crossref-verifier`
- API: `https://api.crossref.org/works/{DOI}` (User-Agent: user email)
- Verify: author surname, year (±1), title 70%+ token match, journal name
- For DOI-less refs: title query `query.bibliographic={hint}&rows=3`
- Output: `doi_verify_pass1.json` with `match_status: ok|mismatch|not_found|hallucinated`

### Agent 2 — `openalex-verifier`
- API: `https://api.openalex.org/works/doi:{DOI}?mailto={email}`
- Same verification independently
- Output: `doi_verify_pass2.json`
- Plus: `doi_discrepancies.md` cross-checking pass1 vs pass2

**Common findings** (from a real thesis review run, 34 refs):
- Hallucinated DOI (resolves to wrong paper): ~10% of refs
- Title hint paraphrased/wrong despite valid DOI: ~5%
- DOI 404 (typo in identifier): ~3%
- Unresolved (no DOI, search no match): ~25%
- Clean: ~55%

## Phase 3 — Hallucination Recovery

For each hallucinated/404/unresolved ref, spawn `ref-resolver` agent:

1. Title + author + year search via Semantic Scholar:
   `https://api.semanticscholar.org/graph/v1/paper/search?query={title}&limit=3`
2. Crossref re-query with different bibliographic combination
3. Output `final_ref_resolution.json` with verdict per ref:
   - `REPLACE`: actual paper found (provide final_doi, final_authors, etc.)
   - `DROP`: no paper exists (recommend body citation removal or alternative)
   - For DROP, propose `alternative_doi` if a topic-matching paper exists

**Important**: never invent DOIs. If both APIs + manual search fail, mark as DROP with `alternative` field for user decision.

## Phase 4 — User Decision Gates (BLOCKING)

The main coordinator MUST pause here and ask the user:

1. **REPLACE (4 items) confirmation**: "Apply ref-resolver suggested replacements?"
2. **DROP (8 items) handling**: 3 options:
   - Remove all
   - Replace with alternative paper
   - Keep as-is (user manually fixes)
3. **Alt paper context fit**: Show each alt's `context_fit_score` (1–5). For `score<5` (e.g., Shin 2020 in LAI cluster), ask: "place inline OR move to separate sentence?"
4. **Newly discovered body refs** (not in refs.docx): "Add these or remove?"

Use AskUserQuestion tool. **Never assume** — every DROP and alt selection must be user-approved.

## Phase 5 — Citation Rewrite Plan

`ref-resolver` agent produces `citation_rewrite_plan.json`:

```json
{
  "transformations": [
    {
      "para_idx": 127,
      "original_substring": "(Tong et al., 2022; Park et al., 2011)",
      "new_substring": "{Bayu, 2021 #PLACEHOLDER_ALT28; Xu, 2014 #PLACEHOLDER_ALT22}",
      "ref_ids_used": [28, 22],
      "operation": "REPLACE_WITH_ALT"
    }
  ]
}
```

PLACEHOLDER tokens are filled in Phase 6 after EndNote DB INSERT returns the actual record IDs.

**Operation types**:
- `RETAIN`: clean ref, just convert format
- `REPLACE`: ref entry metadata changes (#14 author, #17 venue, etc.)
- `REPLACE_NARRATIVE`: "Author et al. (Year)" form — replace text + add EndNote tag
- `REPLACE_WITH_ALT`: substitute alt paper
- `REMOVE_CITATION_BUNDLE`: drop entire group
- `REMOVE_CITATION_PARTIAL`: keep some, drop others in same group
- `INSERT_NEW_SENTENCE`: relocate citation (e.g., epimerase paper out of LAI cluster)

## Phase 6 — EndNote SQLite Direct INSERT

### Phase 6.0 — DOI-match existing records FIRST (skip INSERT when already present)

**Critical (hard-won):** before inserting anything, query the DB by DOI
for every target ref. In a mature library many/all targets already exist — inserting
duplicates is worse than reusing. Only INSERT the refs that genuinely have no match.

```python
def norm(d): return (d or "").strip().lower().replace("https://doi.org/","")
c.execute("SELECT id, author, year, electronic_resource_number FROM refs "
          "WHERE LOWER(electronic_resource_number) LIKE ?", (f"%{norm(doi)}%",))
```
For each hit, confirm author/year sanity and **verify the author separator is `\r`
(CR), not `\n`** (see pitfall below) — a matched record with `\n` still needs the
CR fix before its bibliography renders. Map `plan_ref_id -> existing_id` and route
only the unmatched refs to the INSERT path below.

In one real run all 6 targets (a drug ref + 5 alkane refs) already existed
(#520/#540/#542/#548/#551/#888), so Phase 6 INSERT was skipped entirely and only
Phase 7 (lxml Track Changes) ran. The DB was backed up but never written — safest path.

### Phase 6.1 — Orphan citation recovery: body cites a rec-number with NO backing record (a real case)

The reverse failure mode of 6.0: the docx body already contains an EndNote field citing a
specific rec-number (`{Author, Year #901}`), but that id has **no matching row in `refs`** —
either the record was deleted from the library after the citation was inserted, or the citation
was hand-typed/copy-pasted with a guessed/wrong id, or it came from a different library the
document was once linked to. Symptom in Word: the citation renders as **unformatted / raw
brace text** (`{Author, Year #901}` shown literally) instead of the formatted `(Author, Year)`
output, and EndNote's Find Citation(s) turns up nothing for that id.

**Diagnosis:**
```python
c.execute("SELECT id FROM refs WHERE id = ?", (901,))
# empty result confirms the id is a true orphan, not a lock/sync-table issue
```
Cross-check against `check_invalid_citations()` in `endnote_biblio_check.py` — an orphan
rec-number usually surfaces there as a rendered/unresolved citation, not a clean `instrText`
field (distinguish this from the ordinary "sync table missing" pitfall below, which affects
records that DO exist but aren't yet CWYW-searchable).

**Recovery procedure:**
1. Identify the intended paper from the surrounding text/context (author/year the citation
   claims, or the manuscript's own reference list draft if one exists).
2. Resolve/verify via DOI (CrossRef + OpenAlex dual-check, same as Phase 2) — never guess a
   replacement id or fabricate metadata.
3. **Add the record to the library first** (via this skill's normal Phase 6 INSERT path, with
   `reference_type` forced correctly per the rule above), obtaining a **new, real** rec-number.
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

### Custom placeholder forms

Body citations are not always `(Author, Year)`. This skill also handles pre-seeded
placeholders like `[REF:34]` / `[REF:87-91]` (inserted by an earlier editing pass).
Treat them as opaque find-strings: partition the run on the placeholder and wrap the
placeholder in `<w:del>`, the `{Author, Year #id}` in `<w:ins>` (Phase 7). Multi-ref
placeholders (`[REF:87-91]`) expand to one brace group with `;`-separated cites:
`{Seo, 2019 #520; Chong, 2022 #548; ...}`.

---

**When INSERT is needed** (refs with no existing DB match): EndNote's RIS import is GUI-only and slow. Direct SQLite INSERT works IF you handle two EndNote-specific SQLite extensions:

### EN_MAKE_SORT_KEY function

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

### ENCIN_ko_KR collation

The `refs_ord` table uses a Korean case-insensitive collation. Without it, INSERT fails with `no such collation sequence`.

Stub:
```python
def encin_collation(a, b):
    a = (a or '').lower(); b = (b or '').lower()
    return (a > b) - (a < b)

conn.create_collation("ENCIN_ko_KR", encin_collation)
```

### INSERT statement

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
directly against a shared library — see "SQLite direct UPDATE on existing records" below the
reference_type section: back up, test on a throwaway copy, prefer GUI-side correction, and never
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

### ⚠️ SQLite direct UPDATE on existing records = read-only diagnosis, NOT a fix path (260715 finding)

Everything above (INSERT + the two stub functions) works because INSERT only fires the
`refs__refs_ord_AI` **AFTER-INSERT** trigger, which this skill's `EN_MAKE_SORT_KEY` +
`ENCIN_ko_KR` stubs are sufficient for. **Fixing already-inserted bad records (e.g. bulk
`reference_type` correction, or a bulk `\r`/`\n` author-separator fix) is a different
operation — it fires the AFTER-**UPDATE** trigger (`refs__refs_ord_AU`), which requires the
library's real collation/sort-key behavior, not our approximations.**

In a mature, actively-used library (this project's "My EndNote Library_2025") the `refs_ord`
index is built with **three custom collations**: `ENCIN_ko_KR`, `ENCI_Base`, and `NOCASE`. This
skill's Python-side collation stub (`encin_collation`, a naive `.lower()` compare) does not
reproduce the real `ENCIN_ko_KR`/`ENCI_Base` behavior. A direct `UPDATE refs SET reference_type
= ... WHERE id IN (...)` against a library that uses these collations can throw
`database disk image is malformed` when the AU trigger tries to re-sort `refs_ord`, and even a
successful-looking UPDATE risks leaving the sort index inconsistent with the real collation
rules — `PRAGMA integrity_check` will then report spurious issues (or mask real ones) because
it is being evaluated against the wrong collation implementation.

**Rule: SQLite access to an existing/shared EndNote library is read-only (diagnosis, counting,
export) — never `UPDATE`/`DELETE` on `refs` once records exist beyond what this run itself just
inserted.** Concretely:
- **Bulk `reference_type` correction (Bill → Journal Article, etc.)** → use EndNote's own
  **Library → Find and Replace → In: Reference Type → Bill → Journal Article** (bulk, GUI-native,
  respects the library's own collation/sort-key logic). This is the only safe path once bad
  records are already committed to a shared library. ([Clarivate KB](https://support.clarivate.com/Endnote/s/article/EndNote-Change-reference-type-for-many-records))
- **Bulk author `\r`/`\n` separator fix** on records that were NOT inserted by this same run/session
  → also prefer GUI (open record, re-enter/re-paste author field) or, if scripting is
  unavoidable, restrict the UPDATE to the exact id range this skill's own INSERT just created in
  the same transaction (fresh rows, AU trigger has not yet had to re-sort them against
  collation-dependent neighbors) — never retrofit older/foreign records this way.
- **Before any UPDATE attempt at all**: back up `sdb.eni` (mandatory, see Phase 0), then test the
  UPDATE against a **throwaway copy** of the DB file first and run `PRAGMA integrity_check` on
  the copy afterward. If it reports anything beyond the expected diff, do not apply to the live
  file — fall back to GUI Find&Replace and restore from backup if a live UPDATE was already
  attempted.
- **Diagnosis is always safe** (`SELECT ... FROM refs`, `SELECT ... FROM refs_ord` read-only) —
  only `INSERT`/`UPDATE`/`DELETE` carry the trigger/collation risk. Use SQLite freely to count,
  audit, and locate bad records; use the EndNote GUI to actually fix them once records already
  exist in a shared/multi-manuscript library.

### Exception: ENCI_Base reverse-engineered + REINDEX pipeline makes trigger-free tables safely editable (260715 finding)

The blanket "read-only, use GUI" rule above still holds for **`refs`** (it drives `refs_ord` via
an AFTER-UPDATE trigger that needs the real collation). But **`ENCI_Base` itself has now been
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
radius that has NOT been validated this way. Until that validation exists, `refs` stays GUI-only
per the rule above; only `jterms`-class term-list tables get this safe direct-SQLite path.

**Always required regardless of scope**: backup `sdb.eni` first (Phase 0), close EndNote before
opening the file, and validate on a throwaway copy before touching the live library if there is
any doubt about which tables a given `REINDEX` cascades into.

### Triggers (auto-fire on INSERT)
- `refs__refs_ord_AI`: populates `refs_ord` (uses EN_MAKE_SORT_KEY)
- `refs__ref_props_AI`: populates `ref_props`
- `refs__ret_watch_AI`: populates `ret_watch`
- `refs__tag_members_AI`: populates `tag_members`

**No need to manually populate** these auxiliary tables.

### sync table (potential issue)

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

### Lock check

Before INSERT, verify EndNote is closed:
```python
try:
    stream = open(db_path, 'rb+')
    stream.close()
except IOError:
    raise RuntimeError("DB locked — close EndNote 2025 first")
```

### Author normalization

After INSERT, audit and fix:
- Replacement chars (`\xef\xbf\xbd` from RIS encoding errors): restore proper unicode (ø, é, ä)
- Long corporate names → short forms matching inline citation: 'FAO' not 'Food and Agriculture Organization (FAO)', 'BSH Ingredients' not 'BSH Ingredients GmbH'

This match between author field and inline citation key is what makes EndNote CWYW resolve `{Author, Year #N}`.

### Post-render QC gate — `endnote_biblio_check.py` (260714, recurrence-prevention gate)

After EndNote renders the bibliography (or on any manuscript before submission), run the
non-destructive checker to catch the exact errors this incident produced:

```
python <docx-skill>/scripts/endnote_biblio_check.py <manuscript.docx>
python <docx-skill>/scripts/endnote_biblio_check.py <manuscript.docx> --strict   # exit 1 if any error (gate)
```
Detects 7 error classes from `word/document.xml` (zipfile, no Word open, EndNote fields untouched):
1. **reference_type wrong** — records rendered as Bill/Generic instead of Journal Article (the root cause here — 33 Bill + 2 Generic were caught this way; fix via EndNote **Library → Find and Replace → In: Reference Type → Bill → Journal Article** bulk change, [Clarivate KB](https://support.clarivate.com/Endnote/s/article/EndNote-Change-reference-type-for-many-records)).
2. **INVALID CITATION** — split rendered (`w:t`, unrecoverable) vs field (`instrText`, fixed by Update).
3. **journal italic missing** — RSC italicizes every journal name; a reflist paragraph with no italic run is flagged.
4. **author omission** — reference starting `Surname, Journal` (no initials/co-authors) — the SQLite-INSERT-with-single-surname bug.
5. **`&amp;` entity breakage** — double/unescaped entities in rendered text (fixed 260715 to only flag true double-escape `&amp;amp;`, not normal single-escaped `&amp;` which renders correctly).
6. **non-CASSI journal** — multi-word italic journal name with no periods (PubMed-style) or un-abbreviated full name.
7. **missing reflist entries** (260715) — body/table superscript citation numbers exceed the reference list's max entry number, meaning cited numbers have no backing reference (found in a manuscript's SI: body cited 15–30, list only had 1–14).

Make this a mandatory pre-submission gate for any EndNote manuscript (run with `--strict` in a checklist). It is the verification half of "never wrong again": the INSERT-side fixes (reference_type=17, journal normalization) prevent the error; this checker catches any that still slip through (GUI edits, RIS imports, legacy records).

### Journal name normalization (a real incident — MUST normalize before INSERT)

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
  and check for duplicate rows for the journal in question; delete the extra one (see the
  `ENCI_Base`/REINDEX safe-path above for `jterms` — this is exactly the table it applies to).
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

### ⚠️ Frozen-abbreviation problem: term-list import + Update Citations is NOT always enough (260715 finding)

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

## Phase 7 — lxml Track Changes Application

**Critical**: NEVER use `xml.etree.ElementTree` for docx editing.

ElementTree drops xmlns declarations it doesn't recognize and renames prefixes (`wpc:` → `ns5:`, `cx:` → `ns6:`, etc.), corrupting Word's namespace map. Word will display the file as corrupted on open.

Use `lxml.etree` with `ET.tostring(..., xml_declaration=True, encoding='UTF-8')`. lxml preserves nsmap exactly.

### Algorithm

For each transformation:
1. Find the paragraph (lxml `root.iter(f'{W}p')`) containing the substring (concat `<w:t>` text)
2. Within paragraph, identify involved `<w:r>` runs
3. Build replacement structure:
   ```
   prefix_run + <w:del>middle</w:del> + <w:ins>new_text</w:ins> + suffix_run
   ```
4. Place `<w:ins>` BETWEEN `<w:del>` and suffix run — this is what keeps period/comma after the citation, not before

### Period-before-citation fix

**Wrong** (places ins at end of involved range):
```
prefix → del → suffix → ins
```
Result after Accept All: `text. {Author}` ← period goes BEFORE citation. Bad.

**Correct** (place ins immediately after del):
```
prefix → del → ins → suffix
```
Result: `text {Author}.` ← period stays after, as required by academic style.

### Leading space removal (optional but recommended)

User often wants `text{Author}` not `text {Author}`. Extend deletion to include preceding space:
```python
if idx > 0 and full[idx-1] == ' ':
    idx -= 1   # absorb single leading space into the deletion
```

This makes `text (Author, Year). next` → `text{Author, Year #N}. next` (no space between "text" and brace).

### Multi-run handling

Word splits text into multiple `<w:r>` runs when formatting changes (italic species names, superscripts, etc.). The substring may span multiple runs. Algorithm:

1. Concatenate all `<w:t>` in paragraph → find substring index
2. Determine which runs overlap [idx, idx+len]
3. For each involved run: split into `prefix` (before match) / `middle` (matched) / `suffix` (after match)
4. Rebuild paragraph children: `[all prefixes] + [all dels (middle wrapped)] + [ins] + [all suffixes]`

### `<w:ins>` / `<w:del>` element format

```xml
<w:del w:id="100000" w:author="Citation Update" w:date="2026-05-07T20:30:00Z">
  <w:r><w:rPr/><w:delText>(Author, 2020)</w:delText></w:r>
</w:del>
<w:ins w:id="100001" w:author="Citation Update" w:date="2026-05-07T20:30:00Z">
  <w:r><w:rPr/><w:t>{Author, 2020 #N}</w:t></w:r>
</w:ins>
```

Note: deletion uses `<w:delText>`, insertion uses `<w:t>`. ID must be unique per change. Author and date appear in Word's review pane.

### Apply incrementally per find_text group

Same substring may appear multiple times in same paragraph (e.g., `(Liu et al., 2019)` appearing twice). Loop within paragraph:
```python
for find_text, ops in op_groups.items():
    found_count = 0
    for p in all_paragraphs:
        if found_count >= len(ops): break
        while found_count < len(ops):
            full = concat_text(p)
            if find_text not in full: break
            replace_track(p, find_text, ops[found_count]['replace'])
            found_count += 1
```

## Phase 8 — Integrity Verification

After Phase 7, before showing user:

```python
# 1. python-docx open test
doc = Document(out_path)
assert len(doc.paragraphs) == orig_paras
assert len(doc.tables) == orig_tables
assert len(doc.inline_shapes) == orig_shapes
assert len(doc.sections) == orig_sections

# 2. namespace count check
import re
o_xml = zipfile.ZipFile(orig).read('word/document.xml').decode()
f_xml = zipfile.ZipFile(out_path).read('word/document.xml').decode()
o_ns = re.search(r'<w:document\s+([^>]+)>', o_xml).group(1).count('xmlns')
f_ns = re.search(r'<w:document\s+([^>]+)>', f_xml).group(1).count('xmlns')
assert o_ns == f_ns, f'xmlns count changed: {o_ns} → {f_ns}'

# 3. ns artifact check (ElementTree leak)
ns_artifact = len(re.findall(r'\bns\d+:', f_xml))
assert ns_artifact == 0, f'ElementTree namespace artifacts: {ns_artifact}'
```

If any check fails — abort, restore from backup, debug. Common cause: switched to ET by accident.

## Phase 9 — User Word Review

Open the tracked docx:
```bash
start "" "<output_path>"   # Windows
```

Tell user:
- Open Review tab → "All Markup" → see red strikethrough (deletions) + colored insertions
- Spot-check 3–5 transformations: period placement, no leading space, correct record IDs
- Accept All Changes (when satisfied) or Reject specific ones

User must approve before Phase 10.

## Phase 10 — OneDrive Overwrite

Once approved:
```bash
cp "<work_dir>/v2.tracked.docx" "<original_path>"
```

Final verification: re-open original via python-docx and confirm structural counts match the tracked output.

## Common Pitfalls

| Pitfall | Symptom | Fix |
|---------|---------|-----|
| ElementTree used | "File corrupted" in Word | Switch to lxml |
| Period before citation | `.{Author}` | Phase 7 ins placement order |
| Leading space | `text {Author}` | Phase 7 idx -= 1 if preceding space |
| Author field has corporate full name | `{FAO, 2021 #N}` doesn't resolve | Phase 6 author normalization (use 'FAO' not 'Food and Agriculture Organization') |
| EN_MAKE_SORT_KEY error | INSERT fails | Phase 6 stub function |
| ENCIN_ko_KR error | INSERT fails | Phase 6 stub collation |
| `\xef\xbf\xbd` in author | Broken ø/é/ä display in EndNote | Phase 6 author normalization with proper unicode |
| Bibliography author separator missing ("D. D., C. M." vs "D.; D., C. M.") | Authors used `\n` separator | Use `\r` (CR), not `\n` (LF) — most common silent failure |
| sync table missing entry | EndNote search "No matching reference" despite record exists | Phase 6 sync entry insert OR user runs Tools → Recover Library |
| Multi-run substring not found | Citation skipped | Phase 7 multi-run aware concat-match-split algorithm |
| Same substring N times in 1 para | Only first replaced | Phase 7 inner while-loop per paragraph |
| Bibliography output looks like "D. D., C. M." (no separator) | Output Style author separator broken | NOT our INSERT issue — user's EndNote Output Style needs author list separator config |
| `reference_type` code table assumed universal | Code 0 read as "Generic" but library renders it as "Journal Article" (or vice versa) | Per-library code↔name mapping — verify via GUI or via rendered `ref-type name="..."` string in the docx, never hardcode this skill's table (see DB-code-mapping warning, Phase 6) |
| Bulk `UPDATE refs SET ...` on existing/shared library | `database disk image is malformed`, or silent `refs_ord` inconsistency | Do NOT SQLite-UPDATE existing records — use EndNote GUI Find and Replace (In: Reference Type, etc.); SQLite is read-only diagnosis on a library beyond this run's own fresh INSERTs |
| Journal name still full/inconsistent after term-list import + Update Citations | A few entries didn't re-abbreviate | `fldData` was frozen before the term list existed — Convert to Unformatted Citations, then back to Formatted, to force a full re-render (Phase 6, "Frozen-abbreviation problem") |
| Body cites `{Author, Year #N}` but `refs` has no row with that id | Citation renders as raw unformatted brace text; Find Citation(s) finds nothing | Phase 6.1 orphan recovery — resolve real paper via DOI, INSERT as a new record, then re-link via Edit & Manage Citation(s) (never hand-edit the brace text or guess a nearby id) |
| Duplicate rows in Journals term list for same title | Abbreviation silently doesn't apply despite term existing | Check/remove duplicate term-list rows (`jterms`) — see "Term list hygiene" note; use ENCI_Base/REINDEX safe path or GUI Term Lists editor |
| Record `secondary_title` doesn't byte-match term-list "Full Name" (`&` vs `and`, `&amp;` leak) | That one reference stays full/unabbreviated while others in the same journal abbreviate fine | Diff exact string vs term-list Full Name; fix `secondary_title`, not the term list |
| Edited reference-list text directly in Word body | Edit vanishes after next Update Citations / save | `EN.REFLIST` is a live field — fix the record's `secondary_title` or the term list instead |
| "database does not contain any Term Lists" in Open Term Lists dialog | Looks like term list wiped | Transient index/UI glitch — restart EndNote and re-check before assuming data loss |
| Body superscript citation numbers exceed reference-list max number | `endnote_biblio_check.py` check 7 flags missing numbers | Reference-list entries missing for cited numbers — locate and add the missing records (see `check_missing_reflist_entries`) |
| Direct `UPDATE`/`DELETE` on `refs` (not `jterms`) using the naive collation stub | `database disk image is malformed` | `refs`/`refs_ord` is cross-referenced (CWYW+sync+tags) — stay GUI-only; the ENCI_Base+REINDEX safe path is validated for `jterms`-class self-contained tables only, not `refs` |

## Output Files (per run)

```
refs_work/
├── refs_to_verify.json          # input ref list with DOI hints
├── doi_verify_pass1.json        # CrossRef results
├── doi_verify_pass2.json        # OpenAlex results
├── doi_discrepancies.md         # cross-check report
├── final_ref_resolution.json    # REPLACE/DROP decisions
├── alternative_verification.json # alt paper validation
├── new_refs_verification.json   # newly discovered refs
├── ref_metadata_full.json       # full metadata + RIS blocks
├── refs_for_endnote_import.ris  # backup RIS (manual fallback)
├── citation_rewrite_plan.json   # transformation plan
├── endnote_record_map.json      # plan_ref_id → EndNote record id
├── apply_report_v4.json         # transformation log
└── v2.tracked.docx              # final Track Changes output
```

## Memory Hooks

Save the following to memory after each successful run:
- Project name + manuscript file path
- Date applied
- Number of refs processed (N inserted, M alt'd, K dropped)
- EndNote record id range (start–end) so future updates know where these came from

Example note to keep alongside the project (`endnote_injection_<project>.md`):
```
DOI verification by ref-resolver caught 3 hallucinated DOIs and 1 typo (e.g. wrong year 2017 vs 2019).
Direct SQLite INSERT works with EN_MAKE_SORT_KEY + locale stubs.
Track Changes via lxml preserved 35 xmlns declarations (vs ET which drops to 10).
```

## Reference Run

Validated end-to-end on a real manuscript:
- Manuscript: a thesis-review .docx
- Refs: 34 candidates → 33 INSERT-ed (1 dropped no replacement) → 34 body transformations
- EndNote record range: 748–780
- Result: zero corruption, all transformations as Track Changes, in-place overwrite

---

## Related Skills

| Skill | Relationship |
|-------|-------------|
| `manuscript-pipeline` | Upstream — manuscript editing context; for **single/few DOIs** use its `references/endnote_integration.md` (`ref_fetch` + `doi_verify`) instead of this skill. This skill is for **bulk batch** (10+ refs) with DOI hallucination verification. |
| `docx` | OOXML insertion mechanics SSOT — the `<w:ins>`/comment-marker XML patterns used in Phase 7 are documented there. |
| `academic-term-rules` | Species/enzyme italic conventions applied when rendering author names in inserted citations. |

**Role boundary:** single DOI → `manuscript-pipeline`; bulk batch + SQLite INSERT + hallucination check → this skill; raw OOXML patterns → `docx`.
