# Preprint API guide — verified field paths and traps

Every claim here was checked against a live response. Where a probe contradicted an
expectation, the probe wins and the contradiction is recorded rather than smoothed over.

**All APIs below are free, keyless, and need no registration.**

---

## 1. Europe PMC — the primary keyword route

```
https://www.ebi.ac.uk/europepmc/webservices/rest/search
```

`SRC:PPR` restricts results to preprints. This is the only source in this skill that
combines full-text keyword search, relevance ranking, abstracts, and coverage of every
major biology preprint server.

### Query

```
?query=("enzyme cascade") AND SRC:PPR
&format=json
&pageSize=25
&resultType=core          <-- REQUIRED; the default (lite) omits abstractText
&cursorMark=*
&sort=P_PDATE_D desc
```

Narrow to one server by adding `AND PUBLISHER:"bioRxiv"`.
Filter by date with `AND FIRST_PDATE:[2025-01-01 TO 3000-01-01]`.

### Verified field paths

| Field | Path | Note |
|---|---|---|
| total hits | `hitCount` | top level |
| paging | `nextCursorMark` | pass back as `cursorMark` |
| results | `resultList.result[]` | |
| preprint id | `.id` | e.g. `PPR1283719` |
| source | `.source` | `PPR` confirms preprint |
| DOI | `.doi` | **absent for arXiv-sourced records** |
| title | `.title` | may contain `<em>` highlight tags — strip |
| authors | `.authorString` | a single **flat string**, not a list |
| date | `.firstPublicationDate` | `YYYY-MM-DD` |
| abstract | `.abstractText` | 950–2500 chars measured; embeds JATS tags |
| **server** | `.bookOrReportDetails.publisher` | `journalInfo` is `null` for preprints |
| full-text links | `.fullTextUrlList.fullTextUrl[]` | `{site, documentStyle, availability, url}` |

### Traps

- **`resultType=core` is mandatory** — without it there are no abstracts at all.
- **PDF links expire.** The `europepmc.org/api/fulltextRepo?pprId=…` URL returns
  `403 {"error":"PDF link has expired or is invalid"}` when fetched later. Use Europe PMC
  for *discovery*, then retrieve the PDF by DOI or arXiv ID.
- `hasPDF` is often `N` for bioRxiv records even when bioRxiv serves the PDF fine.
- Titles and abstracts carry HTML/JATS markup; strip before display.
- `pageSize` max is 1000.

---

## 2. arXiv Atom API — a peer keyword route

```
https://export.arxiv.org/api/query
```

> **Trap: the URL must be `https://`.** `http://export.arxiv.org/api/query` returns
> **HTTP 301 with an empty body**. Without redirect-following this looks like an API that
> returned nothing rather than a redirect — a silent, confusing failure.

### Query

```
?search_query=all:"protein folding"
&start=0
&max_results=25
&sortBy=submittedDate
&sortOrder=descending
```

### Namespaces (required for parsing)

```python
{
    "a":   "http://www.w3.org/2005/Atom",
    "arx": "http://arxiv.org/schemas/atom",
    "os":  "http://a9.com/-/spec/opensearch/1.1/",
}
```

### Verified field paths

| Field | Path | Note |
|---|---|---|
| total | `feed/os:totalResults` | |
| entry | `feed/a:entry` | |
| id | `a:id` | `http://arxiv.org/abs/2608.02536v1` — includes the version suffix |
| title | `a:title` | embedded newlines + indent → `" ".join(text.split())` |
| abstract | `a:summary` | same whitespace issue |
| posted | `a:published` | `2026-08-03T…Z` |
| authors | `a:author/a:name` | repeated elements → a real list |
| **PDF** | `a:link[@title='pdf']/@href` | |
| landing | `a:link[@rel='alternate']/@href` | |
| DOI | `arx:doi` | **frequently absent** |
| journal | `arx:journal_ref` | absent if unpublished |
| category | `arx:primary_category/@term` | e.g. `physics.chem-ph` |

### Notes

- `arxiv:doi` is usually missing, so a DOI **cannot** be the join key for arXiv records.
  This is exactly why the arXiv route keys on the arXiv ID instead.
- Courtesy rate: roughly **1 request per 3 seconds**, single connection.
- **Scope:** physics/CS/math. For a biochemistry lab it is largely off-domain —
  `"enzyme cascade"` returned 3 results on arXiv versus 51 on Europe PMC. It earns its
  place for computational/biophysics work, not for wet-lab enzymology.

---

## 3. bioRxiv / medRxiv details API — DOI resolution only

```
https://api.biorxiv.org/details/biorxiv/{doi}
https://api.medrxiv.org/details/medrxiv/{doi}
```

### There is no keyword search. Three probes prove it:

| Probe | Result |
|---|---|
| `/details/biorxiv/crispr` | HTTP 200, body `{"messages":[{"status":"non-numeric value supplied"}],"collection":[]}` |
| `/search/crispr` | HTTP 404 |
| `/details/biorxiv/2026-08-01/2026-08-01/0?query=crispr` | **`query` silently ignored** — byte-identical to the unfiltered page |

The third probe is the dangerous one: HTTP 200, a full-looking result set, and completely
unfiltered. Any code that "searches" this way returns confident nonsense.

Date enumeration is not a workaround either: bioRxiv posts roughly 75–233 papers per day,
so scanning a year means hundreds of requests for one query.

### Verified fields (`collection[]`)

| Field | Note |
|---|---|
| `title`, `abstract` | full text present |
| `authors` | `'Loconsole, M.; Xue, C.'` — semicolon-delimited **string** |
| `doi`, `version`, `date`, `server` | `version` increments per revision |
| `category` | e.g. `animal behavior and cognition` |
| **`published`** | the published DOI, or the literal string `'NA'` |
| `jatsxml` | full-text XML URL |

`published` is the citation-correctness field. Note it is the **string `'NA'`**, not
`null`, when no journal version exists — a plain truthiness test would wrongly mark every
preprint as published.

The `/details/` endpoint gives the published **DOI** but not the journal **name**; that is
resolved with one CrossRef call on the published DOI (`container-title`).

### Related endpoint

```
https://api.biorxiv.org/pubs/biorxiv/{from}/{to}/{cursor}
```

Returns `preprint_doi` → `published_doi` / `published_journal` for a date range — useful
for bulk published-status checks.

### PDF notes

- URL form: `https://www.biorxiv.org/content/{doi}v{version}.full.pdf`
- Requires a browser-like User-Agent.
- `HEAD` returns `000` and a `Range` request returns `500` — use a plain `GET`.
- **Transient 500s are real**: the same URL returned 500, 500, then 200 on consecutive
  tries. Retry with backoff.
- In practice this skill lets `ref_fetch.py` resolve the OA PDF via
  CrossRef/OpenAlex/Unpaywall rather than constructing bioRxiv URLs by hand.

---

## 4. Crossref — Route A metadata resolution

This skill does **not** query Crossref for keyword search — `preprint_search.py` only
implements `search_europepmc()` and `search_arxiv()` (section 1 and 2 above). Crossref's
role here is different and lives one layer down: it is the metadata-resolution call
`scripts/ref_fetch.py` makes for every DOI handed to it, which is what makes **Route A**
(`route="doi"` records → `ref_fetch.py --doi <DOI> --download`) work at all.

```
GET https://api.crossref.org/works/{doi}
```

`filter=type:posted-content` (used with a `?query=` search) is the verified preprint
filter *if* a Crossref-search client is ever added later — it is documented here because
it was probed and confirmed, not because it is wired into anything today.

Confirmed live for a bioRxiv preprint DOI:

```
GET /works/10.1101/2020.03.05.979500
  -> type = "posted-content", institution[0].name = "bioRxiv"
```

`type = "posted-content"` is exactly why `ref_fetch.py` needs no preprint-specific
branching: a preprint DOI resolves through the same single-DOI Crossref call as any other
reference.

### Notes

- `title` is an **array** — use `title[0]`, and it can be empty.
- `author[]` is properly structured (`{given, family}`), unlike the flat author strings
  from Europe PMC and bioRxiv.
- `abstract` is JATS-wrapped (`<jats:p>`) and often missing; real mojibake has been
  observed (`Nucleoside-5??-triphosphates`). Sanitise.
- Identifying *which* preprint server is unreliable — `group-title` and `institution` are
  often `None`. Infer from the DOI prefix (below).
- Add `mailto=` to enter the faster polite pool.

---

## 5. OpenAlex — free only for single-DOI lookups

**OpenAlex is metered by a daily USD budget.** Observed 429 headers:

```
X-RateLimit-Limit: 1000          (credits/day)
X-RateLimit-Limit-USD: 0.1       ($0.10/day free allowance)
X-RateLimit-Remaining-USD: 0
Retry-After: 62291               (~17h, resets midnight UTC)
```

Cost per route:

| Route | Cost |
|---|---|
| `?search=` query | $0.001 |
| bare list | $0.0001 |
| **`works/doi:{doi}`** | **$0 — verified free** |

So OpenAlex must **not** be a keyword-search backend: it would 429 silently after roughly
100 searches a day. Its free single-DOI route is already used by `ref_fetch.py` for
metadata cross-verification, which is exactly where it belongs.

---

## Preprint DOI prefixes

Used only to *label* a record when the API does not name the server — **never** to decide
the retrieval route.

| Prefix | Server |
|---|---|
| `10.1101` | bioRxiv / medRxiv (legacy) |
| `10.64898` | bioRxiv (**new prefix** — do not hardcode `10.1101`) |
| `10.21203` | Research Square |
| `10.26434` | ChemRxiv |
| `10.20944` | Preprints.org |
| `10.31234` | PsyArXiv |
| `10.31219` | OSF Preprints |

---

## Corpus sizes (measured via Europe PMC `SRC:PPR`)

| Server | Preprints |
|---|---|
| Research Square | 463,132 |
| bioRxiv | 344,106 |
| medRxiv | 86,961 |
| SSRN | 17,659 |
| ChemRxiv | 8,952 |
| arXiv (as indexed by Europe PMC) | 7,866 |

---

## Windows notes

- Set `PYTHONUTF8=1`; the cp949 console raises `UnicodeEncodeError` on these payloads.
- Windows Python cannot read Git Bash's `/tmp` — write scratch files to a real Windows
  path.
