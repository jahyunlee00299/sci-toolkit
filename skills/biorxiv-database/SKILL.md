---
name: biorxiv-database
description: Search preprints across bioRxiv, medRxiv, arXiv, Research Square and ChemRxiv using free keyless APIs, and hand the results to scripts/ref_fetch.py for PDF retrieval and BibTeX. Use when looking for the newest unpublished work, checking whether a result has already been posted, or gathering 최신 논문 검색 before peer-reviewed literature exists. Triggers — 프리프린트, preprint, bioRxiv, medRxiv, arXiv, 출판전 논문, 최신 논문 검색, 프리프린트 검색, 사전공개 논문, preprint search, latest preprints.
license: MIT license
---

# biorxiv-database — Preprint Search

Keyword search over preprint servers using **only free APIs that need no key, no
registration, and no paid tier**. This skill is the *search front end* for
`scripts/ref_fetch.py`; it finds preprints and hands them straight to the existing
reference pipeline for PDF download, cross-verified metadata and BibTeX.

**Every result is a preprint — not peer reviewed.** Where a preprint has since appeared
in a journal, this skill surfaces the published DOI and journal name so you cite that
instead (see `skills/academic-term-rules/SKILL.md` §14, "Preprint cited as published").

---

## Quick start

```bash
# Search everything that supports keywords
python skills/biorxiv-database/scripts/preprint_search.py "enzyme cascade" -n 10

# Narrow to one server, save under sources/ per repo convention
python skills/biorxiv-database/scripts/preprint_search.py "CRISPR" -n 20 \
    --source biorxiv --json -o sources/preprints_crispr.json

# Only recent postings
python skills/biorxiv-database/scripts/preprint_search.py "directed evolution" --since 2025-01-01

# Search -> retrieve PDFs through both routes into one directory
python skills/biorxiv-database/scripts/preprint_search.py "enzyme cascade" -n 5 --fetch-refs
```

---

## The two peer retrieval routes

A record's route is decided by **which identifier it carries** — never by the server
name or the DOI prefix. Both routes are first-class; neither is a fallback.

| Record carries | `route` | How the PDF is obtained | Command |
|---|---|---|---|
| a DOI (bioRxiv, medRxiv, Research Square, ChemRxiv, …) | `"doi"` | `ref_fetch.py` resolves it — CrossRef returns `type="posted-content"` for preprints — then downloads the OA PDF and can emit BibTeX | `python scripts/ref_fetch.py --doi <DOI> --download` |
| an arXiv ID (commonly **no DOI at all**) | `"arxiv"` | The PDF URL is **deterministic from the ID**: `https://arxiv.org/pdf/<id>`. No DOI-resolution hop is needed, which makes this the more direct of the two routes. | downloaded directly by `--fetch-refs` |

Every emitted record carries both fields, either of which may be `null`:

```json
{
  "doi": "10.64898/2026.07.24.740396",
  "arxiv_id": null,
  "route": "doi",
  "pdf_url": null
}
```

`pdf_url` is filled only for the arXiv route; on the DOI route `ref_fetch.py` resolves
the OA link itself. A record carrying **neither** identifier cannot be retrieved — that
is a parser bug, so it is reported as a warning and listed under
`rejected_no_identifier` rather than dropped silently.

> **Preprint DOI prefixes are not all `10.1101`.** Measured live: `10.21203`
> (Research Square), `10.26434` (ChemRxiv), and `10.64898` — a **new bioRxiv prefix**
> issued alongside the legacy one. Branch on "has a DOI", never on a prefix.

---

## Handing results to `ref_fetch.py`

```bash
# One command, both routes, one output directory
python skills/biorxiv-database/scripts/preprint_search.py "enzyme cascade" -n 5 --fetch-refs

# Or emit DOIs and pipe them — ref_fetch.py reads a newline-delimited list from stdin
python skills/biorxiv-database/scripts/preprint_search.py "enzyme cascade" --refs-only \
    | python scripts/ref_fetch.py --download

# ...and via a file
python skills/biorxiv-database/scripts/preprint_search.py "enzyme cascade" --refs-only > dois.txt
python scripts/ref_fetch.py --doi-file dois.txt --download --bibtex refs.bib
```

`--refs-only` prints DOIs only. arXiv records have no DOI, so they are omitted from that
list and reported on stderr — use `--fetch-refs` to retrieve those.

---

## Flags

| Flag | Meaning |
|---|---|
| `query` | positional; the search keywords |
| `-n`, `--max-results` | max records (default 10) |
| `--source` | `all` (default), `biorxiv`, `medrxiv`, `arxiv`, `europepmc` |
| `--since YYYY-MM-DD` | only preprints posted on/after this date |
| `--json` | JSON output instead of text |
| `-o`, `--output FILE` | write to FILE (repo convention: under `sources/`) |
| `--fetch-refs` | retrieve PDFs via both routes into one directory |
| `--refs-dir DIR` | where `--fetch-refs` writes (default `./preprint_refs/`) |
| `--refs-only` | print the DOI list to stdout for piping |
| `--email` | contact email for polite-pool requests (or `SCITK_CONTACT_EMAIL`) |
| `--no-enrich` | skip the bioRxiv version / published-status lookup |

---

## Which API answers which question

| Source | Used for | Keyword search? |
|---|---|---|
| **Europe PMC** (`SRC:PPR`) | the primary keyword route; indexes bioRxiv, medRxiv, Research Square, ChemRxiv, SSRN | **Yes** — with real relevance ranking |
| **arXiv** Atom API | keyword route for physics/CS/math preprints | **Yes** |
| **bioRxiv / medRxiv** native API | version number, subject category, published-version status — **by DOI only** | **No — see below** |
| OpenAlex | *not used for search* | n/a |

### bioRxiv's own API cannot search — this is measured, not assumed

Three probes, all run live:

| Probe | Result |
|---|---|
| `/details/biorxiv/crispr` | `{"messages":[{"status":"non-numeric value supplied"}]}` |
| `/search/crispr` | HTTP 404 |
| `/details/biorxiv/DATE/DATE/0?query=crispr` | **the query parameter is silently ignored** — byte-identical to the unfiltered date page |

The third is the dangerous one: it returns HTTP 200 and looks like it worked. So
`--source biorxiv` and `--source medrxiv` narrow **Europe PMC** by publisher rather than
calling the native API, which is used only to resolve a DOI you already have.

### Why OpenAlex is not the search backend

OpenAlex now meters by **daily USD budget** (`X-RateLimit-Limit-USD: 0.1`). A `?search=`
query costs $0.001 and returns HTTP 429 once the allowance is gone, so it would fail
silently after roughly 100 searches per day. Its **single-DOI lookup is still free**
($0 per call) and is reached through `ref_fetch.py`, which already uses it.

---

## Citation correctness

A preprint that has since been published must not be cited as a preprint. When a
bioRxiv/medRxiv record has a journal version, the output says so explicitly:

```
*** PUBLISHED in The CRISPR Journal as 10.1089/crispr.2023.0040 —
    cite the published version, NOT this preprint ***
```

In JSON this is `published_doi` + `published_journal`, with `peer_reviewed` flipped to
`true`. Pass `--no-enrich` to skip the lookup when you only need a fast title scan.

---

## Complementary skills

| Skill | When to use together |
|---|---|
| **research-lookup** | peer-reviewed literature (OpenAlex, PubMed) |
| **pubmed-database** | biomedical published work, MeSH queries |
| **literature-review** | systematic review once the papers are gathered |
| **paper-extract** | pull structured content out of a downloaded PDF |
| **academic-term-rules** | citation and nomenclature conventions |
| **journal-presentation-maker** | build slides from the preprints found here |

---

## Notes and gotchas encoded in the script

- **arXiv must be `https://`.** `http://export.arxiv.org/api/query` returns HTTP 301 with
  an **empty body** — a silent failure if you do not follow redirects.
- **Europe PMC needs `resultType=core`.** The default (`lite`) omits `abstractText`.
- **Europe PMC PDF links expire** (`403 "PDF link has expired or is invalid"`), so they
  are never persisted; PDFs come from the routes above instead.
- **Text is sanitised.** Europe PMC titles carry `<em>` highlight tags, abstracts carry
  JATS markup, arXiv fields carry hard newlines, and Crossref deposits contain mojibake.
- **Rate limits are honoured**: arXiv is queried at roughly one request per 3 seconds.
- **Per-source failure degrades, never crashes** — if one API is unreachable the run
  continues on the others and reports a warning.
- A downloaded file is only accepted as a PDF if it actually begins with `%PDF-`; an HTML
  error page passes any size threshold, so size alone is not checked.
