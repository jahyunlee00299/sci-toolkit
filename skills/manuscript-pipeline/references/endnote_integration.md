# EndNote Citation Integration (manuscript-pipeline reference)

> Workflow for inserting a single DOI or a handful of DOIs into the body text incrementally.
> For **bulk batch conversion (10+, needs hallucination verification)**, use the `endnote-citation-injection` skill instead.
> For the Track Changes XML insertion pattern, see the docx skill (not in this repo — see docs/12).

Proceed in order: collect bibliographic info by DOI → verify existence/consistency → insert the citation.

**Tools that actually exist in this distribution** (relative to the distribution root's `scripts/`; relative to this doc's own location it's `../../../scripts/`):
- `../../../scripts/ref_fetch.py` — DOI (or title) → bibliographic info/OA PDF collection (CrossRef+OpenAlex+Unpaywall, no API key required)
- `../../../scripts/doi_verify.py` — cross-verifies whether a DOI already in a document/BibTeX actually exists and whether its bibliographic info is correct (the hallucinated-DOI gate)

Features that connect **directly to the EndNote DB itself** — DB search, RIS
generation, looking up an unformatted citation (`{Author, Year #N}`), or
auto-generating Word comments — **are not included in this distribution**
(in the original repo, a separate external helper handled these). For bulk
(10+) EndNote-library batch insertion, use the `endnote-citation-injection`
skill; for anything even that skill doesn't cover, the user handles it
directly in the EndNote GUI.

## DOI-first workflow

```
DOI input
  ↓
../../../scripts/ref_fetch.py --doi <DOI>   : collect bibliographic info from CrossRef+OpenAlex+Unpaywall
  ↓
../../../scripts/doi_verify.py --doi <DOI>  : verify existence + author/year/title consistency + retraction status
  ↓
  ├─ OK                         → insert the citation with the bibliographic info as-is
  ├─ MISMATCH / ONE_SOURCE_ONLY → report the issue, then get user confirmation
  └─ HALLUCINATED / RETRACTED   → never cite it, report to the user immediately (exit code 2)
```

## Commands

```bash
# 1) Collect bibliographic info + OA PDF by DOI (paths below are relative to this doc — run from the distribution root)
python ../../../scripts/ref_fetch.py --doi "10.1234/xxx" --download

# Batch multiple DOIs (save results as JSON)
python ../../../scripts/ref_fetch.py --doi "10.1/a,10.2/b,10.3/c" --output result.json

# Process from a DOI list file (newline-separated)
python ../../../scripts/ref_fetch.py --doi-file dois.txt --output result.json

# Search by title to resolve the DOI first (when you don't know the DOI)
python ../../../scripts/ref_fetch.py --title "rare sugar isomerase" --download

# 2) Verify a DOI already present in a document/BibTeX (the hallucination gate)
python ../../../scripts/doi_verify.py --file manuscript.md
python ../../../scripts/doi_verify.py --bibtex refs.bib
```

See `python ../../../scripts/ref_fetch.py --help` / `python ../../../scripts/doi_verify.py --help`
for the full option list (the paths above are relative to this doc's own
location — when running from the distribution root directory, drop the
leading `../../../` and keep just the `scripts/` part).

## Interpreting doi_verify grades

```json
{
  "doi": "10.xxxx/xxx",
  "grade": "OK",              // HALLUCINATED | RETRACTED | MISMATCH | ONE_SOURCE_ONLY | UNVERIFIED | OK
  "issues": [],
  "crossref_meta": { ... },
  "openalex_meta": { ... }
}
```

| grade | meaning | action |
|---|---|---|
| `OK` | existence confirmed + metadata matches + not retracted | insert the citation as-is |
| `MISMATCH` | exists, but the stated author/year/title differs from the actual record | report the issue, let the user decide |
| `ONE_SOURCE_ONLY` | found in only one of the two sources | report it, don't let it pass silently |
| `UNVERIFIED` | the lookup itself failed (network, etc.) | "couldn't verify" ≠ "it's fine" — retry or report |
| `HALLUCINATED` | doesn't exist in either CrossRef or OpenAlex | never cite, report immediately (exit 2) |
| `RETRACTED` | OpenAlex reports it as retracted | never cite, report immediately (exit 2) |

## Word comment format

Whenever a citation is inserted, always add a Word comment next to it
manually (there is no auto-generation tool — use the docx skill's (not in
this repo — see docs/12) comment-insertion feature):

```
[REF] Author et al. (2024) Journal Name
https://doi.org/10.1234/xxx
Key finding: <summarize from the ref_fetch result's abstract/metadata>
Why cited: <why this reference supports the cited claim — if not explicitly stated, infer from context then confirm with the user>
```

## Updating the EndNote library

`ref_fetch`/`doi_verify` never touch the EndNote DB directly. To add a new
reference to the EndNote library:

1. Import the `--bibtex` output of `ref_fetch`'s result into EndNote (BibTeX filter)
2. Or search directly by DOI in the EndNote GUI and import
3. After import, use the Record Number EndNote assigned to build and insert the unformatted citation (`{LastName, Year #N}`)

The Record Number differs per library, so never hardcode it or reuse a
value from a previous session — always re-check it in EndNote each time.

## Rules

- **Never remember or store a Record Number** — it differs per library, always re-check it in the EndNote GUI
- Always run `doi_verify` **before** putting a citation into the manuscript — verifying the DOI before INSERT is mandatory
- Report `MISMATCH`/`ONE_SOURCE_ONLY`/`UNVERIFIED` issues to the user in specific detail and get their judgment
- `HALLUCINATED`/`RETRACTED` are always blocked — never inserted into the manuscript for any reason
- When processing a whole section at once, use a DOI list file → `ref_fetch --doi-file`
- **Always** add a Word comment when inserting a citation (manually if there's no automation — it's still mandatory)
- If "Why cited" is unclear, infer it from context and note it in the comment; if still uncertain, ask the user to confirm
- **Preserve the EndNote field result text**: never convert the `[N]` between the separate~end markers of an `ADDIN EN.CITE` field to plain text (doing so breaks the EndNote field and makes it unable to reformat).
