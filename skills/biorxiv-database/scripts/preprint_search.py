#!/usr/bin/env python3
"""Preprint keyword search across free, keyless APIs — a search front end for scripts/ref_fetch.py.

WHY THIS EXISTS
    bioRxiv/medRxiv's own API has NO keyword search. Three probes confirm it:
      (a) /details/biorxiv/<keyword>          -> {"messages":[{"status":"non-numeric value supplied"}]}
      (b) /search/<keyword>                   -> HTTP 404
      (c) /details/biorxiv/DATE/DATE/0?query= -> the query parameter is SILENTLY IGNORED and
                                                 the identical unfiltered date page comes back
    (c) is the dangerous one: it looks like it worked. So the bioRxiv native API is used here
    ONLY to resolve a known DOI, never to search.

    Keyword search therefore runs through Europe PMC (SRC:PPR) and arXiv, both of which
    genuinely support it with no API key.

DATA SOURCES (all keyless, no registration, no paid tier)
    - Europe PMC  https://www.ebi.ac.uk/europepmc/webservices/rest/search   (SRC:PPR = preprints)
                  Indexes bioRxiv, medRxiv, Research Square, ChemRxiv, SSRN, arXiv preprints.
    - arXiv Atom  https://export.arxiv.org/api/query                        (physics/CS/math)
                  MUST be https:// — http:// returns HTTP 301 with an empty body.
    - bioRxiv     https://api.biorxiv.org/details/{server}/{doi}            (DOI resolution only)
    - medRxiv     https://api.medrxiv.org/details/medrxiv/{doi}             (DOI resolution only)

    OpenAlex is deliberately NOT used for search: it now meters by daily USD budget
    (X-RateLimit-Limit-USD: 0.1) and a ?search= query returns HTTP 429 once exhausted.
    Its free single-DOI route is reached through ref_fetch.py instead.

TWO PEER RETRIEVAL ROUTES
    Every emitted record carries an explicit route. These are peers, not a primary and a
    fallback — which one applies is decided by the identifier the record actually carries.

      route="doi"    DOI-bearing preprints (bioRxiv, medRxiv, Research Square, ChemRxiv, ...)
                     CrossRef returns type="posted-content" for these, so ref_fetch.py
                     resolves them normally:
                         python scripts/ref_fetch.py --doi <DOI> --download
                     DOI prefixes are NOT all 10.1101 — measured live: 10.21203 (Research
                     Square), 10.64898 (new bioRxiv prefix). Branch on "has a DOI", never
                     on a hardcoded prefix or a server name.

      route="arxiv"  arXiv records, which commonly carry no DOI at all. The PDF URL is
                     deterministic from the arXiv ID — https://arxiv.org/pdf/<id> — so this
                     route needs no DOI-resolution hop whatsoever.

USAGE
    # Search (default: every source that supports keywords)
    python preprint_search.py "enzyme cascade" -n 10

    # One source, JSON out, saved under sources/ per repo convention
    python preprint_search.py "CRISPR" -n 20 --source europepmc --json -o sources/preprints_crispr.json

    # Only preprints posted since a date
    python preprint_search.py "directed evolution" --since 2025-01-01

    # Close the loop: search -> retrieve PDFs via both routes into one directory
    python preprint_search.py "enzyme cascade" -n 5 --fetch-refs

    # Emit DOIs for piping into ref_fetch.py (stdin is how ref_fetch accepts a list)
    python preprint_search.py "enzyme cascade" --refs-only | python scripts/ref_fetch.py --download

EVERY RESULT IS A PREPRINT — not peer reviewed. Where a published version exists, this
script surfaces it as `published_doi`/`published_journal`; cite THAT, not the preprint
(see skills/academic-term-rules/SKILL.md section 14, "Preprint cited as published").
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Optional

# Windows consoles default to cp949 and die on non-ASCII output. Match the convention in
# scripts/ref_fetch.py: reconfigure in place rather than wrapping (a TextIOWrapper owns the
# stream and closes the caller's stdout when garbage collected).
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

EPMC_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
ARXIV_BASE = "https://export.arxiv.org/api/query"  # https is mandatory; http 301s to an empty body
BIORXIV_DETAILS = "https://api.biorxiv.org/details/biorxiv"
MEDRXIV_DETAILS = "https://api.medrxiv.org/details/medrxiv"

_TIMEOUT = 25
_MAX_RETRIES = 3
_RETRY_BACKOFF = 1.5
_ARXIV_DELAY = 3.0  # arXiv asks for ~1 request per 3 seconds

# Preprint DOI prefix -> server name. Used only to LABEL a record when the API does not say;
# never to decide the retrieval route (that is decided by which identifier exists).
_DOI_PREFIX_SERVER = {
    "10.1101": "bioRxiv/medRxiv",
    "10.64898": "bioRxiv",
    "10.21203": "Research Square",
    "10.26434": "ChemRxiv",
    "10.20944": "Preprints.org",
    "10.31234": "PsyArXiv",
    "10.31219": "OSF Preprints",
}

_ARXIV_NS = {
    "a": "http://www.w3.org/2005/Atom",
    "arx": "http://arxiv.org/schemas/atom",
    "os": "http://a9.com/-/spec/opensearch/1.1/",
}


# --------------------------------------------------------------------------- #
# Text sanitation
# --------------------------------------------------------------------------- #

_TAG_RE = re.compile(r"<[^>]+>")


def clean_text(raw: Optional[str]) -> str:
    """Strip markup and collapse whitespace.

    Three separate sources of junk are handled here, all observed in real payloads:
      - Europe PMC titles carry <em>...</em> query-highlight tags
      - Europe PMC abstracts embed JATS (<title>Abstract</title>, <p>)
      - arXiv titles/abstracts contain hard newlines plus indentation
    """
    if not raw:
        return ""
    text = _TAG_RE.sub(" ", raw)
    text = (
        text.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&apos;", "'")
        .replace("�", "")  # mojibake replacement chars seen in Crossref/EPMC deposits
    )
    return " ".join(text.split())


def snippet(text: str, limit: int = 300) -> str:
    text = clean_text(text)
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "..."


def server_from_doi(doi: Optional[str]) -> Optional[str]:
    if not doi:
        return None
    prefix = doi.split("/")[0]
    return _DOI_PREFIX_SERVER.get(prefix)


# --------------------------------------------------------------------------- #
# Network helpers — every source degrades independently, none may kill the run
# --------------------------------------------------------------------------- #


def _user_agent(email: Optional[str]) -> str:
    if email:
        return f"sci-toolkit-preprint_search/1.0 (https://github.com/; mailto:{email})"
    return "sci-toolkit-preprint_search/1.0 (no-contact-provided)"


def _http_get(url: str, email: Optional[str], accept: str) -> tuple[Optional[bytes], Optional[str]]:
    headers = {"User-Agent": _user_agent(email), "Accept": accept}
    last_err = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                return resp.read(), None
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code}"
            if e.code == 404:
                return None, "not_found"
        except urllib.error.URLError as e:
            last_err = f"URLError: {e.reason}"
        except Exception as e:  # noqa: BLE001 — report the reason instead of crashing the run
            last_err = f"{type(e).__name__}: {e}"
        if attempt < _MAX_RETRIES:
            time.sleep(_RETRY_BACKOFF * attempt)
    return None, last_err or "unknown_error"


def _http_get_json(url: str, email: Optional[str]) -> tuple[Optional[dict], Optional[str]]:
    raw, err = _http_get(url, email, "application/json")
    if err:
        return None, err
    try:
        return json.loads((raw or b"").decode("utf-8", errors="replace")), None
    except json.JSONDecodeError as e:
        return None, f"JSON parse error: {e}"


# --------------------------------------------------------------------------- #
# Source 1 — Europe PMC (SRC:PPR). The primary keyword route.
# --------------------------------------------------------------------------- #


def search_europepmc(
    query: str,
    max_results: int,
    email: Optional[str],
    since: Optional[str] = None,
    publisher: Optional[str] = None,
) -> tuple[list[dict[str, Any]], Optional[str]]:
    """Keyword-search preprints via Europe PMC.

    resultType=core is REQUIRED — the default (lite) omits abstractText entirely.
    """
    terms = [f'({query})', "SRC:PPR"]
    if publisher:
        terms.append(f'PUBLISHER:"{publisher}"')
    if since:
        terms.append(f"FIRST_PDATE:[{since} TO 3000-01-01]")

    params = {
        "query": " AND ".join(terms),
        "format": "json",
        "pageSize": str(min(max_results, 1000)),
        "resultType": "core",
        "cursorMark": "*",
        "sort": "P_PDATE_D desc",
    }
    url = f"{EPMC_BASE}?{urllib.parse.urlencode(params)}"
    data, err = _http_get_json(url, email)
    if err:
        return [], err

    records = []
    for item in ((data or {}).get("resultList") or {}).get("result", [])[:max_results]:
        doi = item.get("doi")
        details = item.get("bookOrReportDetails") or {}
        srv = details.get("publisher") or server_from_doi(doi) or "unknown"

        # An arXiv record reaching us through Europe PMC still has no DOI. Recover its
        # arXiv ID so it can take the arXiv route rather than being dropped.
        arxiv_id = None
        if not doi:
            for ftu in ((item.get("fullTextUrlList") or {}).get("fullTextUrl") or []):
                m = re.search(r"arxiv\.org/(?:abs|pdf)/([\w.\-/]+)", ftu.get("url", ""))
                if m:
                    arxiv_id = m.group(1)
                    break

        records.append(
            _build_record(
                title=clean_text(item.get("title")),
                authors=clean_text(item.get("authorString")),
                date=item.get("firstPublicationDate") or str(item.get("pubYear") or ""),
                server=srv,
                doi=doi,
                arxiv_id=arxiv_id,
                abstract=clean_text(item.get("abstractText")),
                landing_url=(
                    f"https://doi.org/{doi}"
                    if doi
                    else f"https://europepmc.org/article/PPR/{item.get('id')}"
                ),
                source_api="europepmc",
                extra={"epmc_id": item.get("id")},
            )
        )
    return records, None


# --------------------------------------------------------------------------- #
# Source 2 — arXiv Atom API. A peer keyword route, not a fallback.
# --------------------------------------------------------------------------- #


def search_arxiv(
    query: str, max_results: int, email: Optional[str], since: Optional[str] = None
) -> tuple[list[dict[str, Any]], Optional[str]]:
    # Over-fetch when filtering by date, since arXiv has no server-side date-range filter here.
    fetch_n = min(max_results * 4, 200) if since else max_results
    params = {
        "search_query": f'all:"{query}"',
        "start": "0",
        "max_results": str(fetch_n),
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    url = f"{ARXIV_BASE}?{urllib.parse.urlencode(params)}"
    raw, err = _http_get(url, email, "application/atom+xml")
    if err:
        return [], err

    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        return [], f"Atom parse error: {e}"

    records = []
    for entry in root.findall("a:entry", _ARXIV_NS):
        published = _arxiv_text(entry, "a:published")[:10]
        if since and published and published < since:
            continue

        raw_id = _arxiv_text(entry, "a:id")  # e.g. http://arxiv.org/abs/2606.27238v2
        arxiv_id = raw_id.rsplit("/", 1)[-1] if raw_id else None

        # arxiv:doi is frequently absent; when present, the DOI route is preferable because
        # it yields cross-verified metadata plus BibTeX from ref_fetch.py.
        doi = _arxiv_text(entry, "arx:doi") or None

        authors = ", ".join(
            clean_text(a.findtext("a:name", default="", namespaces=_ARXIV_NS))
            for a in entry.findall("a:author", _ARXIV_NS)
        )

        pdf_url = None
        landing = raw_id
        for link in entry.findall("a:link", _ARXIV_NS):
            if link.get("title") == "pdf":
                pdf_url = link.get("href")
            elif link.get("rel") == "alternate":
                landing = link.get("href") or landing

        cat = entry.find("arx:primary_category", _ARXIV_NS)
        records.append(
            _build_record(
                title=clean_text(_arxiv_text(entry, "a:title")),
                authors=authors,
                date=published,
                server="arXiv",
                doi=doi,
                arxiv_id=arxiv_id,
                abstract=clean_text(_arxiv_text(entry, "a:summary")),
                landing_url=landing,
                source_api="arxiv",
                arxiv_pdf_url=pdf_url,
                extra={
                    "category": cat.get("term") if cat is not None else None,
                    "journal_ref": _arxiv_text(entry, "arx:journal_ref") or None,
                },
            )
        )
        if len(records) >= max_results:
            break
    return records, None


def _arxiv_text(entry: ET.Element, path: str) -> str:
    return (entry.findtext(path, default="", namespaces=_ARXIV_NS) or "").strip()


# --------------------------------------------------------------------------- #
# bioRxiv / medRxiv native API — DOI RESOLUTION ONLY. It cannot search.
# --------------------------------------------------------------------------- #


def enrich_from_biorxiv(doi: str, email: Optional[str]) -> Optional[dict[str, Any]]:
    """Resolve a known DOI against the bioRxiv/medRxiv details API.

    This adds the canonical version number, the subject category, and — the field that
    matters most for citation correctness — whether the preprint has since been published
    in a peer-reviewed journal.

    This function never searches. The native API has no keyword search at all.
    """
    for base in (BIORXIV_DETAILS, MEDRXIV_DETAILS):
        data, err = _http_get_json(f"{base}/{doi}", email)
        if err or not data:
            continue
        collection = data.get("collection") or []
        if not collection:
            continue
        item = collection[-1]  # last entry = newest version
        # "NA" is the API's literal string for "no published version", not a missing key.
        published = item.get("published")
        published_doi = published if published and published != "NA" else None
        return {
            "version": item.get("version"),
            "category": item.get("category"),
            "server": item.get("server"),
            "published_doi": published_doi,
            # The journal name lives on the /pubs/ endpoint, not /details/, so it needs a
            # second call — only worth making when a published version actually exists.
            "published_journal": _published_journal(doi, published_doi, email),
        }
    return None


def _published_journal(doi: str, published_doi: Optional[str], email: Optional[str]) -> Optional[str]:
    """Resolve the journal name for a preprint that has since been published.

    Uses CrossRef on the PUBLISHED DOI (container-title), which is authoritative and
    already a dependency of this repo's ref_fetch.py.
    """
    if not published_doi:
        return None
    data, err = _http_get_json(
        f"https://api.crossref.org/works/{urllib.parse.quote(published_doi)}", email
    )
    if err or not data:
        return None
    titles = ((data.get("message") or {}).get("container-title")) or []
    return titles[0] if titles else None


# --------------------------------------------------------------------------- #
# Record construction — the routing decision lives here and nowhere else
# --------------------------------------------------------------------------- #


def _build_record(
    *,
    title: str,
    authors: str,
    date: str,
    server: str,
    doi: Optional[str],
    arxiv_id: Optional[str],
    abstract: str,
    landing_url: str,
    source_api: str,
    arxiv_pdf_url: Optional[str] = None,
    extra: Optional[dict] = None,
) -> dict[str, Any]:
    """Assemble one record and stamp its retrieval route.

    Route selection is by IDENTIFIER, never by server name or DOI prefix:
      - a DOI present  -> route "doi"   (ref_fetch.py resolves it; CrossRef returns
                                         type="posted-content" for preprints)
      - else an arXiv ID -> route "arxiv" (PDF URL is deterministic from the ID)
    A record with neither identifier cannot be retrieved and is rejected by the caller.
    """
    if doi:
        route = "doi"
        pdf_url = None  # ref_fetch.py resolves the OA PDF via CrossRef/OpenAlex/Unpaywall
    elif arxiv_id:
        route = "arxiv"
        pdf_url = arxiv_pdf_url or f"https://arxiv.org/pdf/{arxiv_id}"
    else:
        route = None
        pdf_url = None

    return {
        "title": title,
        "authors": authors,
        "date": date,
        "server": server,
        "doi": doi,
        "arxiv_id": arxiv_id,
        "route": route,
        "pdf_url": pdf_url,
        "landing_url": landing_url,
        "abstract": abstract,
        "abstract_snippet": snippet(abstract),
        "is_preprint": True,
        "peer_reviewed": False,
        "published_doi": None,      # filled by enrich_from_biorxiv when a journal version exists
        "published_journal": None,
        "source_api": source_api,
        **(extra or {}),
    }


def dedupe(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop duplicates. The same preprint can surface from both Europe PMC and arXiv."""
    seen: set[str] = set()
    out = []
    for r in records:
        key = (r.get("doi") or r.get("arxiv_id") or r.get("title", "")).lower()
        if key and key not in seen:
            seen.add(key)
            out.append(r)
    return out


# --------------------------------------------------------------------------- #
# Search orchestration — per-source failure degrades, never crashes
# --------------------------------------------------------------------------- #


def run_search(
    query: str,
    max_results: int,
    source: str,
    since: Optional[str],
    email: Optional[str],
    enrich: bool = True,
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    """Returns (records, warnings, rejected)."""
    records: list[dict[str, Any]] = []
    warnings: list[str] = []

    # Europe PMC covers bioRxiv/medRxiv, so those two --source values narrow it by publisher
    # rather than hitting the native API (which cannot search).
    epmc_publisher = {"biorxiv": "bioRxiv", "medrxiv": "medRxiv"}.get(source)

    if source in ("all", "europepmc", "biorxiv", "medrxiv"):
        got, err = search_europepmc(query, max_results, email, since, epmc_publisher)
        if err:
            warnings.append(f"Europe PMC unavailable ({err}) — continuing with other sources")
        records.extend(got)

    if source in ("all", "arxiv"):
        if source == "all" and records:
            time.sleep(_ARXIV_DELAY)  # honour arXiv's ~1 req/3 s courtesy rate
        got, err = search_arxiv(query, max_results, email, since)
        if err:
            warnings.append(f"arXiv unavailable ({err}) — continuing with other sources")
        records.extend(got)

    records = dedupe(records)

    # A record with no retrievable identifier is a bug in the parser, not a normal result.
    # Surface it loudly instead of dropping it silently.
    rejected = [r for r in records if not r.get("route")]
    records = [r for r in records if r.get("route")]
    for r in rejected:
        warnings.append(
            f"BUG: record has neither DOI nor arXiv ID, cannot be retrieved — {r.get('title', '?')[:70]!r}"
        )

    records.sort(key=lambda r: r.get("date") or "", reverse=True)
    records = records[:max_results]

    # Enrich bioRxiv/medRxiv DOIs with version + published-version status. This is the
    # citation-correctness step: a preprint later published must not be cited as a preprint.
    if enrich:
        for r in records:
            doi = r.get("doi") or ""
            if doi.split("/")[0] in ("10.1101", "10.64898"):
                info = enrich_from_biorxiv(doi, email)
                if info:
                    r["version"] = info.get("version")
                    r["category"] = info.get("category") or r.get("category")
                    r["server"] = info.get("server") or r["server"]
                    if info.get("published_doi"):
                        r["published_doi"] = info["published_doi"]
                        r["published_journal"] = info.get("published_journal")
                        r["peer_reviewed"] = True

    return records, warnings, rejected


# --------------------------------------------------------------------------- #
# Retrieval — the two peer routes, landing in one directory
# --------------------------------------------------------------------------- #


def find_repo_root() -> Optional[Path]:
    """Locate the repo root by walking up from this file looking for scripts/ref_fetch.py."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "scripts" / "ref_fetch.py").is_file():
            return parent
    return None


def fetch_via_doi_route(
    records: list[dict[str, Any]], out_dir: Path, email: Optional[str]
) -> dict[str, Any]:
    """Route A — hand the DOIs to scripts/ref_fetch.py, which resolves and downloads OA PDFs."""
    dois = [r["doi"] for r in records if r.get("route") == "doi" and r.get("doi")]
    if not dois:
        return {"attempted": 0, "downloaded": 0, "failures": []}

    repo_root = find_repo_root()
    if not repo_root:
        return {
            "attempted": len(dois),
            "downloaded": 0,
            "failures": [{"doi": d, "error": "repo root (scripts/ref_fetch.py) not found"} for d in dois],
        }

    ref_fetch = repo_root / "scripts" / "ref_fetch.py"
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(ref_fetch),
        "--doi", ",".join(dois),
        "--download",
        "--pdf-dir", str(out_dir),
        "--output", str(out_dir / "refs_report.json"),
    ]
    if email:
        cmd += ["--email", email]

    print(f"  -> invoking ref_fetch.py for {len(dois)} DOI(s)", file=sys.stderr)
    env = dict(os.environ, PYTHONUTF8="1")
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=600, env=env,
        )
    except subprocess.TimeoutExpired:
        return {
            "attempted": len(dois),
            "downloaded": 0,
            "failures": [{"doi": d, "error": "ref_fetch.py timed out"} for d in dois],
        }

    # Judge by ref_fetch's own report on disk, not by its exit code or stdout text.
    downloaded, failures = 0, []
    report_path = out_dir / "refs_report.json"
    if report_path.is_file():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            for res in report.get("results", []):
                dl = res.get("download") or {}
                if dl.get("status") == "ok":
                    downloaded += 1
                else:
                    failures.append(
                        {
                            "doi": res.get("doi"),
                            "error": dl.get("error") or dl.get("reason") or res.get("status"),
                        }
                    )
        except json.JSONDecodeError as e:
            failures.append({"doi": "*", "error": f"could not parse refs_report.json: {e}"})
    else:
        failures.append({"doi": "*", "error": f"ref_fetch.py produced no report (rc={proc.returncode})"})

    return {"attempted": len(dois), "downloaded": downloaded, "failures": failures}


def fetch_via_arxiv_route(records: list[dict[str, Any]], out_dir: Path, email: Optional[str]) -> dict[str, Any]:
    """Route B — the arXiv PDF URL is deterministic from the ID, so download it directly.

    No DOI-resolution hop is needed, which makes this route the more direct of the two.
    """
    targets = [r for r in records if r.get("route") == "arxiv"]
    if not targets:
        return {"attempted": 0, "downloaded": 0, "failures": []}

    out_dir.mkdir(parents=True, exist_ok=True)
    downloaded, failures = 0, []
    for i, r in enumerate(targets):
        arxiv_id = r["arxiv_id"]
        url = r.get("pdf_url") or f"https://arxiv.org/pdf/{arxiv_id}"
        if i:
            time.sleep(_ARXIV_DELAY)
        raw, err = _http_get(url, email, "application/pdf,*/*")
        if err or not raw:
            failures.append({"arxiv_id": arxiv_id, "error": err or "empty response"})
            continue
        # Verify it is really a PDF — an HTML error page passes any size threshold.
        if raw[:5] != b"%PDF-":
            failures.append(
                {"arxiv_id": arxiv_id, "error": f"not a PDF (first bytes {raw[:16]!r}, {len(raw)} bytes)"}
            )
            continue
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", f"arxiv_{arxiv_id}")[:180]
        dest = out_dir / f"{safe}.pdf"
        dest.write_bytes(raw)
        downloaded += 1
        print(f"  -> arXiv PDF saved: {dest.name} ({len(raw):,} bytes)", file=sys.stderr)

    return {"attempted": len(targets), "downloaded": downloaded, "failures": failures}


# --------------------------------------------------------------------------- #
# Output formatting
# --------------------------------------------------------------------------- #


def format_text(records: list[dict[str, Any]], query: str, warnings: list[str]) -> str:
    lines = [
        f"Preprint search: {query!r}",
        f"{len(records)} record(s). ALL RESULTS ARE PREPRINTS — not peer reviewed.",
        "=" * 78,
    ]
    for w in warnings:
        lines.append(f"[WARN] {w}")
    if warnings:
        lines.append("-" * 78)

    for i, r in enumerate(records, 1):
        lines.append(f"\n[{i}] {r['title'] or '(no title)'}")
        lines.append(f"    Authors : {r['authors'] or '(unknown)'}")
        lines.append(f"    Date    : {r['date'] or '(unknown)'}   Server: {r['server']}")
        if r.get("doi"):
            lines.append(f"    DOI     : {r['doi']}   [route: doi -> ref_fetch.py]")
        if r.get("arxiv_id"):
            lines.append(f"    arXiv ID: {r['arxiv_id']}   [route: arxiv -> {r.get('pdf_url')}]")
        if r.get("version"):
            lines.append(f"    Version : v{r['version']}")
        if r.get("category"):
            lines.append(f"    Category: {r['category']}")
        if r.get("published_doi"):
            journal = f" in {r['published_journal']}" if r.get("published_journal") else ""
            lines.append(
                f"    *** PUBLISHED{journal} as {r['published_doi']} — cite the published "
                f"version, NOT this preprint ***"
            )
        lines.append(f"    URL     : {r['landing_url']}")
        if r.get("abstract_snippet"):
            lines.append(f"    Abstract: {r['abstract_snippet']}")
    return "\n".join(lines)


def print_fetch_summary(doi_res: dict, arxiv_res: dict, out_dir: Path) -> None:
    total_ok = doi_res["downloaded"] + arxiv_res["downloaded"]
    total_try = doi_res["attempted"] + arxiv_res["attempted"]
    failures = doi_res["failures"] + arxiv_res["failures"]

    print("\n=== retrieval summary ===")
    print(f"  output directory : {out_dir}")
    print(f"  via DOI route    : {doi_res['downloaded']}/{doi_res['attempted']} PDF(s)")
    print(f"  via arXiv route  : {arxiv_res['downloaded']}/{arxiv_res['attempted']} PDF(s)")
    print(f"  total downloaded : {total_ok}/{total_try}")
    if failures:
        print(f"  failed           : {len(failures)}")
        for f in failures:
            ident = f.get("doi") or f.get("arxiv_id") or "?"
            print(f"    - {ident}: {f.get('error')}")
        print("  (a closed-access preprint with no OA PDF is a legitimate result, not a bug)")

    # Judge by what is actually on disk, never by the counters above.
    on_disk = sorted(out_dir.glob("*.pdf")) if out_dir.is_dir() else []
    print(f"  PDFs on disk     : {len(on_disk)}")
    for p in on_disk:
        head = p.open("rb").read(5)
        print(f"    - {p.name} ({p.stat().st_size:,} bytes, header={head!r})")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Search preprint servers (bioRxiv/medRxiv/arXiv/Research Square/ChemRxiv) "
        "via free keyless APIs, and hand results to scripts/ref_fetch.py.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("query", help="Search keywords")
    parser.add_argument("-n", "--max-results", type=int, default=10, help="Max records (default: 10)")
    parser.add_argument(
        "--source",
        default="all",
        choices=["all", "biorxiv", "medrxiv", "arxiv", "europepmc"],
        help="Which source to query. biorxiv/medrxiv narrow Europe PMC by publisher, because "
        "the native bioRxiv API has NO keyword search.",
    )
    parser.add_argument("--since", help="Only preprints posted on/after this date (YYYY-MM-DD)")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    parser.add_argument("-o", "--output", help="Write results to FILE (repo convention: sources/)")
    parser.add_argument(
        "--fetch-refs",
        action="store_true",
        help="Retrieve PDFs for every result: DOI records via scripts/ref_fetch.py, "
        "arXiv records via their deterministic PDF URL. Both land in one directory.",
    )
    parser.add_argument(
        "--refs-dir",
        default=None,
        help="Directory for --fetch-refs PDFs (default: ./preprint_refs/)",
    )
    parser.add_argument(
        "--refs-only",
        action="store_true",
        help="Print only the DOI list, one per line, for piping into ref_fetch.py",
    )
    parser.add_argument(
        "--email",
        default=None,
        help="Contact email for polite-pool requests (or set SCITK_CONTACT_EMAIL)",
    )
    parser.add_argument("--no-enrich", action="store_true", help="Skip bioRxiv version/published-status lookup")

    args = parser.parse_args()
    email = args.email or os.getenv("SCITK_CONTACT_EMAIL") or None

    if args.since and not re.match(r"^\d{4}-\d{2}-\d{2}$", args.since):
        print(f"[ERROR] --since must be YYYY-MM-DD, got {args.since!r}", file=sys.stderr)
        return 1

    records, warnings, rejected = run_search(
        query=args.query,
        max_results=args.max_results,
        source=args.source,
        since=args.since,
        email=email,
        enrich=not args.no_enrich,
    )

    for w in warnings:
        print(f"[WARN] {w}", file=sys.stderr)

    if not records:
        print("[INFO] No preprints found (every source either returned nothing or was unreachable).", file=sys.stderr)
        if not args.json:
            return 0 if not warnings else 2

    # --refs-only: DOIs only, on stdout, so the caller can pipe it. ref_fetch.py reads a
    # newline-delimited DOI list from stdin when given no --doi/--doi-file/--title argument.
    if args.refs_only:
        for r in records:
            if r.get("doi"):
                print(r["doi"])
        skipped = [r for r in records if not r.get("doi")]
        if skipped:
            print(
                f"[INFO] {len(skipped)} arXiv record(s) omitted — they carry no DOI and take the "
                f"arXiv route instead (use --fetch-refs to retrieve them).",
                file=sys.stderr,
            )
        return 0

    output = json.dumps(
        {
            "query": args.query,
            "source": args.source,
            "since": args.since,
            "count": len(records),
            "warnings": warnings,
            "rejected_no_identifier": rejected,
            "note": "All records are PREPRINTS (not peer reviewed). Where published_doi is set, "
            "cite the published version instead.",
            "records": records,
        },
        ensure_ascii=False,
        indent=2,
    ) if args.json else format_text(records, args.query, warnings)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output + "\n", encoding="utf-8")
        print(f"[OK] Saved to {out_path}", file=sys.stderr)
    else:
        print(output)

    if args.fetch_refs:
        refs_dir = Path(args.refs_dir) if args.refs_dir else Path.cwd() / "preprint_refs"
        print(f"\n[INFO] Retrieving PDFs into {refs_dir}", file=sys.stderr)
        doi_res = fetch_via_doi_route(records, refs_dir, email)
        arxiv_res = fetch_via_arxiv_route(records, refs_dir, email)
        print_fetch_summary(doi_res, arxiv_res, refs_dir)

    return 0


if __name__ == "__main__":
    sys.exit(main())
