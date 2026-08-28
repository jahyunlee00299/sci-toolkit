---
name: web-scraping
description: 웹페이지·논문·문서를 크롤링/스크래핑하여 텍스트·표·링크·메타데이터를 추출하고 PDF/xlsx/docx 파일을 수집한다. Use this skill when the user wants to 크롤링, 스크래핑, scrape, 웹페이지 추출, 웹 데이터 수집, 논문 다운로드, fetch a web page, extract tables/text/links from a site, harvest PDFs, or retrieve scholarly metadata (Crossref/arXiv/bioRxiv DOIs and full-text links). Covers static HTML, JavaScript-rendered pages, academic sources, and bulk document harvesting.
allowed-tools: Read Write Edit Bash
license: MIT license
metadata:
    skill-author: web-scraping-skill team
    axis: Research
---

# Web Scraping

A reusable web-crawling skill for research and paperwork. Covers static HTML,
dynamic JS pages, academic metadata, and document-file collection across 4
modes. Every script works both as a CLI and as a Python import.

## Execution Method

For tasks that require running code, execute the scripts under `scripts/`
with the **Bash tool**. Delegate long crawls (many pages, bulk downloads) to
a subagent; a single-page extraction is fine to run directly.

## When to Use This Skill

- Extracting body text/tables/links from a web page ("crawl", "scrape", "extract")
- Gathering paper metadata (DOI, authors, full-text PDF links) from Crossref/arXiv/bioRxiv
- Needing content from a dynamic page rendered by JavaScript
- Bulk-downloading PDF/xlsx/docx files linked from a page ("download the paper")
- Converting a collected document to Markdown for analysis

## When NOT to Use

- PubMed / OpenAlex search -> prefer the existing `pubmed-database`,
  `openalex-database` skills, or the `biopython` (Bio.Entrez) library.
  This skill only covers Crossref/arXiv/bioRxiv.
- Converting an already-downloaded local document -> use the `markitdown` skill directly.
- A systematic literature review -> use the `literature-review` skill.

## PDF download priority (fetch_academic.py --download)

```
1. Crossref pdf_links      (publisher CDN, immediate for OA papers)
2. Unpaywall              (automatically finds an OA version)
3. PubMed Central (PMC)   (free full-text repository)
3.5 LibKey Nomad          (institutional-subscription journals — via Chrome MCP, --libkey flag)
4. EZproxy (Selenium)     (last resort, --ezproxy / --auto-login flags)
```

**LibKey Nomad (source 3.5, recommended):** full-text access for
institutional-library subscription journals. Use `--download --libkey` with
the LibKey Nomad Chrome extension installed and Claude Code's Chrome MCP
connected. Lighter and faster than EZproxy Selenium. Only use Chrome MCP
when dynamic JS is actually required.

**EZproxy (source 4, deprecated):** last resort when LibKey fails.
`--auto-login` (Chrome's saved credentials) or `--ezproxy` (manual cookie).

### Real-world traps in OA/PMC downloads

**1. A PMC PDF requires the new domain + a browser.**
- Yes: `https://pmc.ncbi.nlm.nih.gov/articles/<PMCID>/` — the **new domain**, works via browser automation.
  Pattern: navigate -> find `href="pdf/<file>.pdf"` on an interactive element -> navigate to that absolute URL -> download.
- No: `https://www.ncbi.nlm.nih.gov/pmc/articles/<PMCID>/pdf/` — **old domain, bot-blocked**
  (returns 1816-byte "Preparing to download..." HTML). Direct urllib/requests access is blocked on both the old and new domains -> **a browser is required**.

**2. "Listed in PMC" does not mean "in the OA subset."**
- Even when listed in PMC, an author-deposit article keeps the publisher's copyright -> bot downloads are blocked.
- To tell the difference: `pmc/utils/oa/oa.fcgi?id=<PMCID>` — an `href` (tgz/pdf) means it's genuinely OA; `"is not Open Access"` means institutional access (EZproxy, etc.) is needed.
- Even in a genuinely OA subset, if the tgz has no PDF and only XML/images, retry via a browser on the new PMC domain.

**3. PMID->DOI/PMCID (idconv) requires batches of 4 or fewer.**
- `pmc/utils/idconv/v1.0/?ids=<csv>` — a larger batch (10+) comes back entirely as status=error.
- Normalize with `str(pmid).strip()` when matching on the PMID key (prevents dict-matching failures).

**4. A publisher-specific "block" is more often something other than a CAPTCHA.**
Measured across multiple institutional EZproxy setups and many publishers: real
Cloudflare/reCAPTCHA blocks were a minority, and most cases were session
expiry, a stale URL pattern, or an SSO configuration problem. Don't assume
"this publisher throws a CAPTCHA" — narrow the cause first using the
checklist below.

- **JBC (J Biol Chem) is hosted on ScienceDirect/Elsevier** (don't be misled by the ASBMB branding) -> counts against the Elsevier limit.
- **Going straight to the original publisher site via a doi.org redirect sometimes triggers a Cloudflare challenge** (e.g. ScienceDirect). Routing precisely through the institutional proxy (EZproxy, etc.) usually loads normally — suspect a path that skips the proxy and goes straight to the origin domain first.
- **Some publisher platforms genuinely enforce strong bot-blocking** (e.g. Microbiology Society was measured to dead-end completely at a Cloudflare challenge). Exclude such sites from automation and let a human handle them directly.
- **Some cases look like a CAPTCHA but are actually an SSO/OAuth configuration error** — e.g. a publisher uses a third-party SSO like Auth0, and after the institution changes its proxy domain, if that new host isn't registered on the SSO's callback-URL allowlist, a "Callback URL mismatch" error appears. This is an institution-to-publisher configuration problem that neither the user nor a script can fix — it needs to go to the library/IT contact.
- **When a publisher migrates platforms, old URL patterns can 404 entirely** — first confirm whether that URL reproduces on the origin site itself, to separate "blocked" from "the link is dead." Measured case: a legacy path like `/doi/full/<DOI>` was dead while `/doi/<DOI>` was the new correct form.
- If a link resolver like LibKey gives only **"ARTICLE LINK"/"LIBRARY ACCESS OPTIONS"** instead of a direct PDF link, that publisher has no direct PDF link through the resolver — go direct to the publisher page or route through PMC instead.
- When scouting (checking where things get blocked), testing with an arbitrarily made-up DOI/PII can't distinguish "a genuine 404" from "a genuine block" — first secure a real, recent DOI via the Crossref API and test with that.

**5. Don't trust a midnight-based tracker for rate limits.**
- A commercial publisher's institutional download limit is usually enforced over a **rolling window (e.g. ~24h)** -> a midnight-reset tracker like "N today" undercounts, so you can actually exceed the limit and get blocked (CAPTCHA/suspension) without the tracker showing it.
- Re-check against a 24h rolling basis, and avoid consecutive/bulk downloads (space them a few seconds to tens of seconds apart).
- Downloading a large volume (10+ papers) in a row from the same publisher in a short time can get the entire institution blocked from that publisher's database for a period (e.g. a month) — exhaust OA sources first, and go slowly/in small batches for subscription content.

**6. For a subscription paper, opening the publisher page directly in a browser is priority #1.**
- Lesson from a failure sequence: a direct curl only returned an HTML login page (no session). Routing through a link-resolver bypass service (EBSCO/ProQuest-type) can hit a **separate login popup wall** ("find your institution") — a library-portal login alone doesn't propagate a session to that service. If a link resolver (LibKey, etc.) can't supply a direct PDF link for that journal, all you get is "LIBRARY ACCESS OPTIONS."
- **The answer: use browser automation to navigate directly to the publisher's article page (e.g. `link.springer.com/article/{DOI}`) -> click/navigate to the page's PDF link (e.g. `/content/pdf/{DOI}.pdf`).** If the browser has a live institutional-subscription session (IP/cookies), the download just works (no login popup).
- **If curl can't get it, don't switch to a bypass service** — try direct publisher-page access first. The bypass path actually tends to hit more login walls. If you hit 2-3 walls, it's a rabbit hole — ask the user to download it directly instead (usually a one-click "view PDF" in their browser, not hard for them).
- Never enter credentials or perform a login on the user's behalf (security). Once the user does the institutional login themselves, the session can be picked up from there.

## 4 Modes

| Mode | Script | Purpose |
|---|---|---|
| Static HTML | `fetch_static.py` | Extract body text/tables/links (requests/httpx + selectolax/trafilatura) |
| Academic metadata | `fetch_academic.py` | Search Crossref/arXiv/bioRxiv + DOI/full-text PDF links |
| Dynamic JS | `fetch_dynamic.py` | Extract after Playwright headless rendering (optional dependency) |
| File harvesting | `harvest_files.py` | Auto-discover/download PDF/xlsx/docx from a page + markitdown conversion |

The shared module `_common.py` provides robots.txt checking, a per-domain
rate limiter, a response cache, a retry/backoff HTTP client, and provenance
logging.

## Setup

```bash
# Install dependencies (base or the research-agent conda env)
pip install -r requirements.txt

# Only needed if you'll use dynamic mode (optional)
pip install playwright
playwright install chromium
```

## Usage

All scripts are run from the `scripts/` directory (because of the `_common.py` import).

### 1. Static HTML — fetch_static.py

```bash
cd scripts

# Extract body text (boilerplate removed, Markdown output)
python fetch_static.py "https://example.com/article" --mode text -o out.json

# Extract tables + links at once
python fetch_static.py "https://example.com/data" --mode tables links -o out.json

# Adjust the rate limit (2-second interval per domain)
python fetch_static.py "https://example.com" --mode text --delay 2.0
```

Modes: `text` (body + metadata), `tables` (every HTML table -> row data),
`links` (absolute URL + anchor text), `html` (raw HTML).

### 2. Academic metadata — fetch_academic.py

```bash
cd scripts

# Crossref keyword search
python fetch_academic.py --source crossref --query "enzyme cascade biosynthesis" -n 10

# Crossref single-DOI lookup
python fetch_academic.py --source crossref --doi 10.1039/D0GC00000A

# arXiv search
python fetch_academic.py --source arxiv --query "enzyme cascade optimization" -n 5

# bioRxiv preprints from the last 30 days
python fetch_academic.py --source biorxiv --recent 30 --server biorxiv
```

Each result returns title/authors/year/DOI/full-text PDF link in a unified
format. Crossref uses the polite pool (`mailto`).

### 3. Dynamic JS pages — fetch_dynamic.py

Use only when static extraction returns an empty result, or JS rendering is
clearly required.

```bash
cd scripts

# Extract body text after JS rendering
python fetch_dynamic.py "https://spa-site.com/page" --mode text

# Wait for a specific element to appear, then extract tables
python fetch_dynamic.py "https://site.com/results" --mode tables \
    --wait-selector "#results-table"
```

If Playwright isn't installed, this prints a clear install message and exits.

### 4. File harvesting — harvest_files.py

```bash
cd scripts

# Preview a page's PDF/xlsx links (no download)
python harvest_files.py "https://journal.com/article" --discover-only --ext pdf

# Download PDFs only + convert to Markdown
python harvest_files.py "https://journal.com/si" -o ./downloads \
    --ext pdf docx xlsx --convert --report harvest.json
```

Downloads use streaming (memory-efficient even for large PDFs), and
`--convert` chains into Markdown conversion via the `markitdown` package.

## Python Import (reusable)

```python
import sys
sys.path.insert(0, "scripts")

from _common import PoliteHttpClient, HttpClientConfig
from fetch_static import StaticScraper
from fetch_academic import CrossrefProvider

with PoliteHttpClient(HttpClientConfig(min_delay=1.0)) as client:
    scraper = StaticScraper.from_url("https://example.com", client)
    tables = scraper.extract_tables()

papers = CrossrefProvider().search("target compound", limit=5)
```

## Safety Rules (must be followed)

This skill only does ethical, legal crawling — enforced in `_common.py`.

1. **robots.txt compliance** — checks the target domain's robots.txt before
   any request and blocks `Disallow` paths. Only use `--ignore-robots` with
   explicit permission.
2. **Rate limiting** — a minimum 1-second interval per domain (default), or
   robots.txt's `Crawl-delay` when it's longer.
3. **An identifiable User-Agent** — sends an honest UA that includes a
   contact (email). Never impersonates a browser (unnecessary for research/
   public-data use).
4. **Prefer official APIs** — always prefers an official API (Crossref,
   arXiv, etc.) over HTML scraping.
5. **Honors HTTP 429 / Retry-After** — exponential backoff + a maximum
   retry limit.
6. **Caching** — prevents repeated requests to the same URL, reducing
   server load and improving reproducibility (`.cache/`, default 24h TTL,
   disable with `--no-cache`).
7. **Copyright / terms of service** — never bypasses login/paywalled
   content. Excludes illegitimate routes like Sci-Hub. Uses legitimate
   institutional access such as the affiliated library's EZproxy.
8. **Records data provenance** — every output JSON logs `provenance`
   (source URL, retrieval time, method).
9. **Public repo caution** — never commits raw crawled data to a public repo.

## Output Format

Every script outputs JSON (`-o`/`--report` to save to a file, stdout if omitted).

```json
{
  "provenance": {
    "source_url": "https://...",
    "method": "fetch_static",
    "retrieved_at": "2026-05-23T...Z",
    "tool": "web-scraping-skill/1.0"
  },
  "data": { ... }
}
```

## Integration with Other Skills

- `markitdown` — converts collected PDF/DOCX to Markdown (harvest_files `--convert`).
- `pubmed-database`, `openalex-database` skills, or importing the Biopython
  (Bio.Entrez) package directly — for PubMed/OpenAlex search. This skill
  doesn't duplicate that; it only handles Crossref/arXiv/bioRxiv.
- `literature-review` — systematic literature review, using metadata
  collected by this skill as input.
- `onedrive` — when saving to a OneDrive path. Follow OneDrive Safety rules
  (no recursive glob, confirm large files first).

## Institutional off-campus-access PDF download rules
1. Collect OA papers first — downloads that don't need institutional access
   (EZproxy, etc.) don't count against the limit.
2. Only downloads requiring off-campus access (EZproxy, etc.) are tracked
   against the limit — if needed, build a separate download-counter script
   to log per-publisher counts (e.g. ScienceDirect and JBC are both
   Elsevier, so sum them into the same counter).
3. Always check the cumulative count for that day/time window before
   working — institutional limits are often enforced as a rolling window
   (e.g. ~24h) rather than a midnight reset (see the §4 rate-limit item above).
4. Violating institutional library policy can suspend access — respect
   each publisher's daily/monthly limit.

## Pre-submission reference-PDF cross-check audit

When judging whether manuscript reference PDFs are "all collected":

1. **The manuscript (docx) is the SSOT** — use the actual reference list
   **extracted from the latest canonical manuscript**, not a download list
   or folder, as the baseline.
   Run `manuscript_text.py <docx> --count-only` first to check for tracked
   changes (a CITE field counts as EN.CITE) -> extract text with
   `--mode accept` -> parse each numbered entry as (first author surname, year, journal).
2. **When there are multiple folders, treat the superset as canonical** —
   even with differing filename conventions (`author_year.pdf` vs.
   `authoryear_tag_abbrev.pdf`), cross-check by normalized
   surname+year matching. Treat one superset folder as canonical and the
   rest as subsets.
3. **Distinguish "MISSING" from an actual download target** — filter out
   books/book chapters (confirmed to have no accessible full text) from
   **bibliographic errors**.
   Warning — a bibliographic-error blind spot: author+year matching
   **misses a case where only the year is wrong**. Example: Wong &
   Whitesides "JACS 2002, **103**, 4890" -> JACS vol. 103 is actually from
   **1981** (a wrong year in the citation; the PDF already exists as
   wong_1981). If the vol/page are correct, independently verify the year
   via CrossRef -> this is not a download target, it's a
   **manuscript/EndNote bibliographic correction** target.
4. **Never fix an EndNote manuscript's bibliography with a text
   find-replace** — if the reference renders as an `ADDIN EN.CITE` field,
   fixing only the text can revert on the next "Update Citations" and
   break the field. The real fix: correct that reference's field in the
   **EndNote library (sdb.eni)** itself, then Update.
5. Quarantine mis-downloaded leftovers (`*_FIRSTPAGE_ONLY`, `*_WRONG_*`,
   `*_BROKEN*.bak`) into **`_quarantine/` rather than permanently
   deleting them**. On a Korean OneDrive path, `mv` gets locked, so use
   PowerShell's `Move-Item -LiteralPath`.

## Resources

- `scripts/_common.py` — shared infrastructure (robots, rate limiter, cache, HTTP client, provenance)
- `scripts/fetch_static.py` — static HTML extraction
- `scripts/fetch_academic.py` — academic metadata (Crossref/arXiv/bioRxiv)
- `scripts/fetch_dynamic.py` — dynamic JS rendering (Playwright)
- `scripts/harvest_files.py` — document file harvesting
- `requirements.txt` — dependencies
- `references/usage.md` — detailed usage examples + troubleshooting
