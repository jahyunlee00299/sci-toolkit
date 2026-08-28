# web-scraping skill — detailed usage guide

Detailed examples and troubleshooting that supplement `SKILL.md`'s quick reference.

## Table of contents

1. Installation and environment
2. Detailed usage per mode
3. Python import patterns
4. Common options (polite crawling)
5. Output format and provenance
6. Troubleshooting
7. Ethical/legal guidelines

---

## 1. Installation and environment

### Core dependencies (required)

```bash
# from the base or research-agent conda env
cd <skill-root>
pip install -r requirements.txt
```

Install footprint is about 20-30 MB (excluding the Playwright browser). All MIT/BSD/Apache-2.0.

On Windows, `selectolax` and `lxml` ship as pip wheels, so no compiler is needed.
If you're mixing in conda, `lxml` from conda-forge is fine to prefer:

```bash
conda install -c conda-forge lxml
pip install httpx selectolax trafilatura beautifulsoup4 habanero arxiv markitdown
```

### Dynamic mode (optional)

Install this only if you'll use `fetch_dynamic.py`. Not needed for the static,
academic, or file-harvest modes.

```bash
pip install playwright
playwright install chromium      # browser binary (~150 MB)
```

Running `fetch_dynamic.py` without it installed prints a friendly install guide and exits.

### Where to run it from

The scripts import `_common.py` from the same directory, so
**run them from inside the `scripts/` directory**:

```bash
cd <skill-root>/scripts
python fetch_static.py "https://..." --mode text
```

---

## 2. Detailed usage per mode

### 2.1 fetch_static.py — static HTML

| Mode | What it returns |
|---|---|
| `text` | trafilatura body extraction (Markdown) + metadata (title/author/date) |
| `tables` | every HTML `<table>` -> `{columns, rows, n_rows, n_cols}` |
| `links` | every `<a href>` -> absolute URL + anchor text (deduplicated) |
| `html` | the raw HTML as-is |

```bash
# extract a paper page's body text + tables together
python fetch_static.py \
    "https://pubs.rsc.org/en/content/articlehtml/2024/gc/d4gc00000a" \
    --mode text tables -o article.json

# only the tables from a DB page, in DataFrame form
python fetch_static.py "https://www.uniprot.org/uniprotkb/P12345" \
    --mode tables -o uniprot_tables.json

# be more conservative by raising the rate limit (3s per domain)
python fetch_static.py "https://slow-server.org/page" \
    --mode text --delay 3.0 --timeout 60
```

If `trafilatura` isn't available or can't find the body, `text` mode falls back to a
selectolax-based extractor that returns tag-stripped text (distinguished by the
`extractor` field).

### 2.2 fetch_academic.py — academic metadata

All three sources use only official APIs. No page scraping.

```bash
# Crossref keyword search (sorted by relevance)
python fetch_academic.py --source crossref \
    --query "enzyme cascade biocatalysis" -n 20 -o crossref_results.json

# a single Crossref DOI — feeds directly into the EndNote DOI verification workflow
python fetch_academic.py --source crossref --doi 10.1021/acscatal.3c00000

# arXiv search (newest submission date first)
python fetch_academic.py --source arxiv \
    --query "Bayesian optimization enzyme" -n 10

# recent bioRxiv preprints (last 30 days)
python fetch_academic.py --source biorxiv --recent 30 --server biorxiv

# medRxiv DOI lookup
python fetch_academic.py --source biorxiv --server medrxiv \
    --doi 10.1101/2024.01.01.24300000
```

Unified fields across returned records: `title, authors, year, doi, journal/url, pdf_links`.
If `pdf_links` has a full-text PDF URL, it can be downloaded directly with `harvest_files.py`.

For PubMed/OpenAlex search, use the `pubmed-database`/`openalex-database` skills or the
Biopython (Bio.Entrez) package instead of this skill (division of responsibility, avoid duplication).

### 2.3 fetch_dynamic.py — dynamic JS pages

Only when static extraction returns nothing, or the content is rendered by JS.

```bash
# default: wait for networkidle, then extract the body text
python fetch_dynamic.py "https://spa-dashboard.org/data" --mode text

# wait for a specific element to appear (a search-results table, etc.)
python fetch_dynamic.py "https://search-site.org/results?q=target+compound" \
    --mode tables --wait-selector "div.result-table" --timeout 45

# debugging: show the browser window
python fetch_dynamic.py "https://site.org" --mode html --no-headless
```

`--wait-until` options: `load` / `domcontentloaded` / `networkidle` (default).
After rendering, the HTML is handed to `StaticScraper`, so the extraction modes are the same as static.

### 2.4 harvest_files.py — document file collection

```bash
# step 1: check which files are linked first (no download)
python harvest_files.py "https://journal.org/article/si" \
    --discover-only --ext pdf xlsx docx

# step 2: download only the PDFs
python harvest_files.py "https://journal.org/article/si" \
    -o ./si_files --ext pdf -n 5 --report harvest.json

# download + markitdown conversion together
python harvest_files.py "https://journal.org/article/si" \
    -o ./si_files --ext pdf docx xlsx --convert --report harvest.json
```

- Downloads stream (64KB chunks), so even a several-hundred-MB PDF is memory-safe.
- On a filename collision, a `_1`, `_2` suffix is added automatically.
- An individual download failure is not raised — it's recorded in the report's `status`
  field and the batch continues.
- `--convert` uses the `markitdown` package. If it's not installed, this prints the
  markitdown skill command as guidance.

---

## 3. Python import patterns

Every script is importable. Add `scripts/` to sys.path.

```python
import sys
sys.path.insert(0, "scripts")  # run from skill root, or use absolute path to scripts/

from _common import PoliteHttpClient, HttpClientConfig, Provenance
from fetch_static import StaticScraper
from fetch_academic import CrossrefProvider, ArxivProvider, BiorxivProvider
from harvest_files import FileHarvester, convert_with_markitdown

# reuse one client across multiple pages (shares rate-limit state)
config = HttpClientConfig(min_delay=1.5, max_retries=5, use_cache=True)
with PoliteHttpClient(config) as client:
    for url in page_urls:
        scraper = StaticScraper.from_url(url, client)
        print(scraper.extract_tables())

    harvester = FileHarvester(client, extensions=("pdf",))
    results = harvester.harvest("https://journal.org/si", "./out")

# academic metadata
papers = CrossrefProvider().search("target product biosynthesis", limit=10)
for p in papers:
    print(p["title"], p["doi"], p["pdf_links"])
```

### The dynamic scraper

```python
from fetch_dynamic import DynamicScraper, DynamicConfig

cfg = DynamicConfig(wait_selector="#results", timeout_ms=45000)
scraper = DynamicScraper(cfg).scrape("https://spa-site.org/page")
text = scraper.extract_text()
```

---

## 4. Common options (polite crawling)

Shared by `fetch_static.py`, `fetch_academic.py` (biorxiv), and `harvest_files.py`:

| Option | Default | Meaning |
|---|---|---|
| `--delay` | 1.0 | minimum seconds between requests to the same domain |
| `--timeout` | 30.0 | request timeout (seconds) |
| `--retries` | 3 | max retries on 429/5xx/transport error |
| `--ignore-robots` | off | ignore robots.txt (only with authorization) |
| `--no-cache` | off | disable the response cache |

`fetch_dynamic.py` uses `--timeout`, `--ignore-robots`, `--no-headless`,
`--wait-selector`, and `--wait-until`.

### Cache

- Location: `web-scraping/.cache/` (keyed by the SHA-256 hash of the URL)
- Default TTL: 24 hours
- To clear the cache: delete the contents of the `.cache/` directory (going through the recycle bin is recommended)

---

## 5. Output format and provenance

Every output JSON has the same structure:

```json
{
  "provenance": {
    "source_url": "https://example.com/page",
    "method": "fetch_static",
    "retrieved_at": "2026-05-23T04:12:00+00:00",
    "tool": "web-scraping-skill/1.0"
  },
  "data": { "...": "per-mode extraction result" }
}
```

`provenance` is always included, per the data-provenance recording policy. When saving
collected data to a research notebook or a `runs/` directory, keep this metadata alongside it.

---

## 6. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `ImportError: httpx is required` | `pip install -r requirements.txt` |
| `robots.txt disallows fetching` | the target disallows crawling. Consider using its official API. If you have authorization, `--ignore-robots` (at your own responsibility) |
| `text` mode returns empty | likely a JS-rendered page -> use `fetch_dynamic.py` |
| `tables` mode returns an empty list | the page has no HTML `<table>` (a div-based grid) -> parse it directly with a selectolax CSS selector, or use dynamic mode |
| `Playwright is not installed` | `pip install playwright && playwright install chromium` |
| `Chromium browser binary missing` | `playwright install chromium` |
| repeated HTTP 429 | increase `--delay` and check `--retries`. The server is rate-limiting heavily |
| `habanero is required` | `pip install habanero` |
| Korean text garbled | the output JSON is UTF-8. Check the terminal encoding (`chcp 65001`) |
| slow when saving to a OneDrive path | forces a cloud-only file download. Recommended: save to a local path, then move it |

### When dynamic mode is slow

Switching to `--wait-until domcontentloaded` is faster than networkidle (though it may
miss lazily-loaded content). Or use `--wait-selector` to wait only for the element you need.

---

## 7. Ethical/legal guidelines

This skill enforces ethical crawling at the code level. The user must also follow these:

1. **Prefer official APIs** — check the Crossref/arXiv/PubMed/OpenAlex API before scraping.
2. **robots.txt** — respected by default. `--ignore-robots` is only for a site you own
   or have explicit permission for.
3. **Rate limit** — don't casually drop the default 1-second interval to 0. Consider the
   target server's load.
4. **No paywall bypass** — do not bypass login/subscription content. Illegitimate routes
   like Sci-Hub are excluded from this skill. Use legitimate institutional access, such
   as your institution's library EZproxy.
5. **Personal data** — be careful that collected data doesn't mix in personal
   information. Do not commit raw crawl data to a public repo.
6. **Copyright** — redistribution of collected text/PDFs follows the original copyright and license.

A problematic request (bulk paywall bypass, anti-bot evasion disguises, etc.) is outside
this skill's design scope.
