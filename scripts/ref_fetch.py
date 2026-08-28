#!/usr/bin/env python3
"""Automated reference (paper) collection tool — takes a list of DOIs and gathers bibliographic
metadata/PDFs through open-access (OA) channels only.

Data sources (none require an API key):
    - CrossRef  https://api.crossref.org/works/{doi}
    - OpenAlex  https://api.openalex.org/works/doi:{doi}
    - Unpaywall https://api.unpaywall.org/v2/{doi}?email=...  (only when an email is given)

The cache reuses `ref_cache_manager.py`'s `RefCacheManager` as-is
(~/.claude/ref_cache/, filename is the DOI's SHA256 hash). The record schema
this script stores in the cache is exactly the dict that `fetch_one()` below
builds.

No paywall bypass or scraping — if there's no OA link, it's simply recorded
as `oa_status: closed` and moved past.

Usage:
    # single/multiple DOIs (comma-separated)
    python ref_fetch.py --doi 10.1038/nature12373,10.1021/acs.jchemed.7b00361

    # read DOIs from a file (newline-separated)
    python ref_fetch.py --doi-file dois.txt

    # read DOIs from stdin
    cat dois.txt | python ref_fetch.py

    # search by title to resolve a DOI, then proceed
    python ref_fetch.py --title "CRISPR gene editing efficiency"

    # also download the PDF (OA only)
    python ref_fetch.py --doi 10.1186/s13321-015-0069-3 --download

    # export BibTeX
    python ref_fetch.py --doi 10.1038/nature12373 --bibtex out.bib

    # ignore the cache and force a re-fetch
    python ref_fetch.py --doi 10.1038/nature12373 --refresh

    # Unpaywall polite-pool email (never hardcode a real email into the code)
    python ref_fetch.py --doi 10.1038/nature12373 --email you@example.com
    # or: export SCITK_CONTACT_EMAIL=you@example.com

Output:
    refs_report.json (per-DOI metadata / OA status / cross-verification / download path) + a stdout summary.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional

# The default Windows console is cp949, which crashes on Korean/symbol
# output. Force UTF-8. Use reconfigure rather than TextIOWrapper — a wrapper
# owns the underlying stream, so once this module is imported and the
# wrapper is later garbage collected, it closes the caller's stdout too
# (measured).
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

# Reuse ref_cache_manager.py (same scripts/ folder)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ref_cache_manager import RefCacheManager  # noqa: E402

CROSSREF_BASE = "https://api.crossref.org/works"
OPENALEX_BASE = "https://api.openalex.org/works"
UNPAYWALL_BASE = "https://api.unpaywall.org/v2"

_TIMEOUT = 20
_MAX_RETRIES = 3
_RETRY_BACKOFF = 1.5  # seconds, multiplied up each attempt
_RATE_LIMIT_DELAY = 0.5  # minimum wait between requests (recommended for the polite pool)

_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")


# --------------------------------------------------------------------------- #
# Network helpers — timeout + retry, User-Agent carries a contact (when given)
# --------------------------------------------------------------------------- #


def _build_user_agent(email: Optional[str]) -> str:
    base = "sci-toolkit-ref_fetch/1.0 (https://github.com/; mailto:CONTACT)"
    if email:
        return base.replace("CONTACT", email)
    return "sci-toolkit-ref_fetch/1.0 (no-contact-provided)"


def _http_get_json(url: str, email: Optional[str], timeout: int = _TIMEOUT) -> tuple[Optional[dict], Optional[str]]:
    """GET, then parse as JSON. Returns a (data, error) tuple — error=None on success.

    A clear "does not exist" like a 404 is returned quietly as
    (None, "not_found"); any other network/server error that still fails
    after retries is returned as (None, error_message).
    """
    headers = {"User-Agent": _build_user_agent(email), "Accept": "application/json"}
    last_err = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                return json.loads(raw), None
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None, "not_found"
            last_err = f"HTTP {e.code}"
        except urllib.error.URLError as e:
            last_err = f"URLError: {e.reason}"
        except json.JSONDecodeError as e:
            last_err = f"JSON parse error: {e}"
        except Exception as e:  # noqa: BLE001 — caught broadly so every network-failure reason ends up in the report
            last_err = f"{type(e).__name__}: {e}"

        if attempt < _MAX_RETRIES:
            time.sleep(_RETRY_BACKOFF * attempt)

    return None, last_err or "unknown_error"


def _http_get_text(url: str, email: Optional[str], timeout: int = _TIMEOUT) -> tuple[Optional[str], Optional[str]]:
    headers = {"User-Agent": _build_user_agent(email)}
    last_err = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace"), None
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None, "not_found"
            last_err = f"HTTP {e.code}"
        except Exception as e:  # noqa: BLE001
            last_err = f"{type(e).__name__}: {e}"

        if attempt < _MAX_RETRIES:
            time.sleep(_RETRY_BACKOFF * attempt)

    return None, last_err or "unknown_error"


def _download_pdf(url: str, dest: Path, email: Optional[str], timeout: int = 60) -> tuple[bool, Optional[str]]:
    """Download an OA PDF link.

    An OA link often redirects to a landing page (HTML) rather than the
    actual PDF (e.g. the publisher blocks crawlers and returns a
    human-facing page), or returns an access-restriction notice page.
    File size alone can't filter this out (an observed failure case: a 3KB
    HTML page passed the size threshold), so both the Content-Type header
    and the PDF magic byte (`%PDF-`) must be checked before this counts as
    a real PDF.
    """
    headers = {"User-Agent": _build_user_agent(email), "Accept": "application/pdf,*/*"}
    last_err = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                content_type = (resp.headers.get("Content-Type", "") or "").lower()
                data = resp.read()

                is_pdf_magic = data[:5] == b"%PDF-"
                is_pdf_content_type = "application/pdf" in content_type
                looks_like_html = content_type.startswith("text/html") or data.lstrip()[:15].lower().startswith(
                    (b"<!doctype html", b"<html")
                )

                if looks_like_html or not (is_pdf_magic or is_pdf_content_type):
                    return False, (
                        f"response is not a PDF (Content-Type={content_type or 'unknown'}, "
                        f"magic_byte_ok={is_pdf_magic}, {len(data)} bytes) — likely "
                        f"redirected to a landing page"
                    )

                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
                return True, None
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code}"
            if e.code == 404:
                return False, last_err
        except Exception as e:  # noqa: BLE001
            last_err = f"{type(e).__name__}: {e}"

        if attempt < _MAX_RETRIES:
            time.sleep(_RETRY_BACKOFF * attempt)

    return False, last_err or "unknown_error"


# --------------------------------------------------------------------------- #
# DOI normalization / filename sanitization
# --------------------------------------------------------------------------- #


def normalize_doi(raw: str) -> str:
    """Normalize a DOI string (strip URL prefix, lowercase, trim whitespace)."""
    doi = raw.strip()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi, flags=re.IGNORECASE)
    doi = re.sub(r"^doi:\s*", "", doi, flags=re.IGNORECASE)
    return doi.strip()


def doi_to_safe_filename(doi: str) -> str:
    """Convert a DOI into an ASCII-safe filename (avoids Windows cp949 issues)."""
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", doi.strip().lower())
    return safe.strip("_")[:180]  # prevent excessive length


# --------------------------------------------------------------------------- #
# CrossRef / OpenAlex / Unpaywall queries
# --------------------------------------------------------------------------- #


def query_crossref(doi: str, email: Optional[str]) -> dict[str, Any]:
    url = f"{CROSSREF_BASE}/{urllib.parse.quote(doi)}"
    if email:
        url += f"?mailto={urllib.parse.quote(email)}"
    data, err = _http_get_json(url, email)
    if err == "not_found":
        return {"found": False, "error": "not_found"}
    if err:
        return {"found": False, "error": err}

    msg = (data or {}).get("message", {})
    authors = []
    for a in msg.get("author", []) or []:
        given = a.get("given", "")
        family = a.get("family", "")
        name = f"{given} {family}".strip() or a.get("name", "")
        if name:
            authors.append(name)

    year = None
    for date_field in ("published-print", "published-online", "issued", "created"):
        parts = (msg.get(date_field) or {}).get("date-parts")
        if parts and parts[0]:
            year = parts[0][0]
            break

    title_list = msg.get("title") or []
    return {
        "found": True,
        "title": title_list[0] if title_list else None,
        "authors": authors,
        "year": year,
        "journal": (msg.get("container-title") or [None])[0],
        "publisher": msg.get("publisher"),
        "type": msg.get("type"),
        "volume": msg.get("volume"),
        "issue": msg.get("issue"),
        "page": msg.get("page"),
        "is_referenced_by_count": msg.get("is-referenced-by-count"),
        "url": msg.get("URL"),
    }


def query_openalex(doi: str, email: Optional[str]) -> dict[str, Any]:
    url = f"{OPENALEX_BASE}/doi:{urllib.parse.quote(doi)}"
    if email:
        url += f"?mailto={urllib.parse.quote(email)}"
    data, err = _http_get_json(url, email)
    if err == "not_found":
        return {"found": False, "error": "not_found"}
    if err:
        return {"found": False, "error": err}

    d = data or {}
    authors = []
    for authorship in d.get("authorships", []) or []:
        name = (authorship.get("author") or {}).get("display_name")
        if name:
            authors.append(name)

    primary_loc = d.get("primary_location") or {}
    source = primary_loc.get("source") or {}
    oa = d.get("open_access") or {}
    best_oa = d.get("best_oa_location") or {}

    return {
        "found": True,
        "title": d.get("title"),
        "authors": authors,
        "year": d.get("publication_year"),
        "journal": source.get("display_name"),
        "type": d.get("type"),
        "is_oa": oa.get("is_oa"),
        "oa_status": oa.get("oa_status"),
        "best_oa_pdf_url": best_oa.get("pdf_url"),
        "best_oa_landing_page_url": best_oa.get("landing_page_url"),
        "cited_by_count": d.get("cited_by_count"),
        "openalex_id": d.get("id"),
    }


def query_unpaywall(doi: str, email: str) -> dict[str, Any]:
    url = f"{UNPAYWALL_BASE}/{urllib.parse.quote(doi)}?email={urllib.parse.quote(email)}"
    data, err = _http_get_json(url, email)
    if err == "not_found":
        return {"found": False, "error": "not_found"}
    if err:
        return {"found": False, "error": err}

    d = data or {}
    best_oa = d.get("best_oa_location") or {}
    return {
        "found": True,
        "is_oa": d.get("is_oa"),
        "oa_status": d.get("oa_status"),
        "best_oa_pdf_url": best_oa.get("url_for_pdf") or best_oa.get("url"),
        "best_oa_landing_page_url": best_oa.get("url_for_landing_page"),
        "license": best_oa.get("license"),
        "host_type": best_oa.get("host_type"),
    }


def resolve_doi_from_title(title: str, email: Optional[str]) -> Optional[str]:
    """Resolve a single DOI by sending a CrossRef bibliographic query built from the title."""
    params = {"query.bibliographic": title, "rows": 1}
    if email:
        params["mailto"] = email
    url = f"{CROSSREF_BASE}?{urllib.parse.urlencode(params)}"
    data, err = _http_get_json(url, email)
    if err or not data:
        return None
    items = (data.get("message") or {}).get("items") or []
    if not items:
        return None
    return items[0].get("DOI")


# --------------------------------------------------------------------------- #
# Cross-verification
# --------------------------------------------------------------------------- #


def _norm_text(s: Optional[str]) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", s).strip().lower()


def cross_verify(crossref: dict, openalex: dict) -> list[str]:
    """Find field mismatches between CrossRef and OpenAlex and return them as human-readable strings.

    Doesn't silently pick one side — if there's a mismatch, both are kept.
    """
    discrepancies: list[str] = []
    if not crossref.get("found") or not openalex.get("found"):
        return discrepancies

    # Compare titles (flag if not an exact match after normalization; minor punctuation
    # differences are absorbed by normalization)
    cr_title = _norm_text(crossref.get("title"))
    oa_title = _norm_text(openalex.get("title"))
    if cr_title and oa_title and cr_title != oa_title:
        discrepancies.append(
            f"title mismatch — CrossRef: {crossref.get('title')!r} | OpenAlex: {openalex.get('title')!r}"
        )

    # Compare years
    cr_year = crossref.get("year")
    oa_year = openalex.get("year")
    if cr_year and oa_year and cr_year != oa_year:
        discrepancies.append(f"year mismatch — CrossRef: {cr_year} | OpenAlex: {oa_year}")

    # Compare journal names
    cr_journal = _norm_text(crossref.get("journal"))
    oa_journal = _norm_text(openalex.get("journal"))
    if cr_journal and oa_journal and cr_journal != oa_journal:
        discrepancies.append(
            f"journal mismatch — CrossRef: {crossref.get('journal')!r} | OpenAlex: {openalex.get('journal')!r}"
        )

    # Compare author counts (name formatting varies by source, so only compare the
    # rough count — flag only a large difference)
    cr_authors = crossref.get("authors") or []
    oa_authors = openalex.get("authors") or []
    if cr_authors and oa_authors and abs(len(cr_authors) - len(oa_authors)) >= 2:
        discrepancies.append(
            f"author count mismatch — CrossRef: {len(cr_authors)} {cr_authors} | "
            f"OpenAlex: {len(oa_authors)} {oa_authors}"
        )

    return discrepancies


# --------------------------------------------------------------------------- #
# Main fetch-one pipeline
# --------------------------------------------------------------------------- #


def _reconcile_cached_download(
    doi: str, cached: dict[str, Any], pdf_dir: Path, email: Optional[str]
) -> Optional[dict[str, Any]]:
    """Make a cache hit's download path true for THIS call's --pdf-dir.

    The cache is keyed by DOI alone, so a hit replays the download record from
    whichever run first populated it. That record names the *earlier* run's
    --pdf-dir. Returning it unchanged reports status "ok" while the directory
    the caller actually asked for stays empty, and a caller that trusts the
    report gets nothing (reproduced: two runs, same DOI, different --pdf-dir).

    Returns the record with download.path pointing inside pdf_dir, or None when
    the cached PDF cannot be recovered and a fresh fetch is required.
    """
    dl = cached.get("download") or {}
    if dl.get("status") != "ok":
        # "skipped" / "failed" promise no file, so they cannot mislead.
        return cached

    # doi comes from the caller, not from the cached record: an entry written by
    # an older schema may not carry a 'doi' key, and a KeyError here would take
    # down a run that a cache hit should have made cheaper.
    dest = pdf_dir / f"{doi_to_safe_filename(doi)}.pdf"
    if dest.is_file():
        dl["path"] = str(dest)
        return cached

    src = Path(dl.get("path", ""))
    if src.is_file():
        pdf_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        dl["path"] = str(dest)
        dl["reused_from_cache"] = str(src)
        return cached

    # The cached path no longer exists (temp dir cleaned, run on another
    # machine, file deleted). Re-download from the OA URL the cache still holds.
    oa_pdf_url = cached.get("oa_pdf_url")
    if oa_pdf_url:
        pdf_dir.mkdir(parents=True, exist_ok=True)
        ok, err = _download_pdf(oa_pdf_url, dest, email)
        if ok:
            cached["download"] = {"status": "ok", "path": str(dest),
                                  "redownloaded": True}
            return cached
        cached["download"] = {"status": "failed", "error": err,
                              "attempted_url": oa_pdf_url}
        return cached
    return None


def fetch_one(
    doi: str,
    cache: RefCacheManager,
    email: Optional[str],
    refresh: bool,
    download: bool,
    pdf_dir: Path,
) -> dict[str, Any]:
    doi = normalize_doi(doi)

    if not _DOI_RE.match(doi):
        return {
            "doi": doi,
            "status": "error",
            "error": f"not a valid DOI format: {doi!r}",
        }

    if not refresh and cache.has(doi):
        cached = cache.get(doi)
        if cached:
            cached["status"] = "cache_hit"
            if download:
                reconciled = _reconcile_cached_download(doi, cached, pdf_dir, email)
                if reconciled is not None:
                    return reconciled
                # Cached PDF is unrecoverable; fall through and fetch afresh.
            else:
                return cached

    crossref = query_crossref(doi, email)
    time.sleep(_RATE_LIMIT_DELAY)
    openalex = query_openalex(doi, email)
    time.sleep(_RATE_LIMIT_DELAY)

    if not crossref.get("found") and not openalex.get("found"):
        record = {
            "doi": doi,
            "status": "not_found",
            "crossref": crossref,
            "openalex": openalex,
            "discrepancies": [],
            "oa_status": "unknown",
            "download": None,
        }
        return record  # not cached — this could be a transient error

    discrepancies = cross_verify(crossref, openalex)

    # Resolving the OA link: Unpaywall (when there's an email) > OpenAlex best_oa_location
    unpaywall = None
    oa_pdf_url = None
    oa_landing_url = None
    oa_status = "closed"

    if email:
        unpaywall = query_unpaywall(doi, email)
        time.sleep(_RATE_LIMIT_DELAY)
        if unpaywall.get("found"):
            if unpaywall.get("is_oa"):
                oa_status = unpaywall.get("oa_status") or "open"
                oa_pdf_url = unpaywall.get("best_oa_pdf_url")
                oa_landing_url = unpaywall.get("best_oa_landing_page_url")

    if not oa_pdf_url and openalex.get("found") and openalex.get("is_oa"):
        oa_status = openalex.get("oa_status") or "open"
        oa_pdf_url = openalex.get("best_oa_pdf_url")
        oa_landing_url = openalex.get("best_oa_landing_page_url")

    record: dict[str, Any] = {
        "doi": doi,
        "status": "fetched",
        "crossref": crossref,
        "openalex": openalex,
        "unpaywall": unpaywall,
        "discrepancies": discrepancies,
        "oa_status": oa_status,
        "oa_pdf_url": oa_pdf_url,
        "oa_landing_page_url": oa_landing_url,
        "download": None,
    }

    if download:
        if oa_pdf_url:
            dest = pdf_dir / f"{doi_to_safe_filename(doi)}.pdf"
            ok, err = _download_pdf(oa_pdf_url, dest, email)
            if ok:
                record["download"] = {"status": "ok", "path": str(dest)}
            else:
                record["download"] = {
                    "status": "failed",
                    "error": err,
                    "attempted_url": oa_pdf_url,
                }
        else:
            record["download"] = {"status": "skipped", "reason": "no_oa_pdf_link (oa_status=closed)"}

    cache.put(doi, record)
    return record


# --------------------------------------------------------------------------- #
# BibTeX export (CrossRef application/x-bibtex)
# --------------------------------------------------------------------------- #


def fetch_bibtex(doi: str, email: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    url = f"{CROSSREF_BASE}/{urllib.parse.quote(doi)}/transform/application/x-bibtex"
    headers = {"User-Agent": _build_user_agent(email), "Accept": "application/x-bibtex"}
    last_err = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                return resp.read().decode("utf-8", errors="replace"), None
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None, "not_found"
            last_err = f"HTTP {e.code}"
        except Exception as e:  # noqa: BLE001
            last_err = f"{type(e).__name__}: {e}"
        if attempt < _MAX_RETRIES:
            time.sleep(_RETRY_BACKOFF * attempt)
    return None, last_err or "unknown_error"


# --------------------------------------------------------------------------- #
# Input parsing
# --------------------------------------------------------------------------- #


def collect_dois(args: argparse.Namespace, email: Optional[str]) -> list[str]:
    dois: list[str] = []

    if args.doi:
        dois.extend(part.strip() for part in args.doi.split(",") if part.strip())

    if args.doi_file:
        p = Path(args.doi_file)
        if not p.exists():
            print(f"[ERROR] DOI file not found: {p}", file=sys.stderr)
        else:
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    dois.append(line)

    if args.title:
        resolved = resolve_doi_from_title(args.title, email)
        if resolved:
            print(f"[INFO] DOI resolved from title search: {resolved}", file=sys.stderr)
            dois.append(resolved)
        else:
            print(f"[WARN] Could not resolve a DOI from the title: {args.title!r}", file=sys.stderr)

    # stdin (only when piped in, and no other arguments were given)
    if not dois and not sys.stdin.isatty():
        for line in sys.stdin.read().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                dois.append(line)

    # Deduplicate (preserving order)
    seen = set()
    unique = []
    for d in dois:
        nd = normalize_doi(d)
        if nd not in seen:
            seen.add(nd)
            unique.append(nd)
    return unique


# --------------------------------------------------------------------------- #
# Human-readable summary output
# --------------------------------------------------------------------------- #


def print_summary(results: list[dict[str, Any]]) -> None:
    print("\n=== ref_fetch results summary ===")
    print(f"  Total DOIs: {len(results)}")

    ok = [r for r in results if r.get("status") in ("fetched", "cache_hit")]
    not_found = [r for r in results if r.get("status") == "not_found"]
    errors = [r for r in results if r.get("status") == "error"]
    open_oa = [r for r in results if r.get("oa_status") not in (None, "closed", "unknown")]
    with_discrepancies = [r for r in results if r.get("discrepancies")]

    print(f"  Fetched successfully: {len(ok)}")
    print(f"  Not found (404, etc.): {len(not_found)}")
    print(f"  Errors (format/network): {len(errors)}")
    print(f"  Confirmed OA (open): {len(open_oa)}")
    print(f"  Items with cross-verification mismatches: {len(with_discrepancies)}")

    for r in results:
        doi = r.get("doi", "?")
        status = r.get("status", "?")
        title = None
        if r.get("crossref", {}).get("found"):
            title = r["crossref"].get("title")
        elif r.get("openalex", {}).get("found"):
            title = r["openalex"].get("title")
        title_str = f" — {title}" if title else ""
        print(f"\n  [{doi}] status={status}{title_str}")

        if status == "error":
            print(f"    Error: {r.get('error')}")
            continue
        if status == "not_found":
            cr_err = r.get("crossref", {}).get("error")
            oa_err = r.get("openalex", {}).get("error")
            print(f"    CrossRef: {cr_err} / OpenAlex: {oa_err}")
            continue

        print(f"    oa_status: {r.get('oa_status')}")
        if r.get("discrepancies"):
            print("    [!] Cross-verification mismatches:")
            for d in r["discrepancies"]:
                print(f"        - {d}")
        dl = r.get("download")
        if dl:
            if dl.get("status") == "ok":
                print(f"    PDF downloaded: {dl.get('path')}")
            elif dl.get("status") == "failed":
                print(f"    PDF download failed: {dl.get('error')}")
            elif dl.get("status") == "skipped":
                print(f"    PDF download skipped: {dl.get('reason')}")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _run_doi_gate(
    doi: str,
    expect_title: str,
    email: Optional[str],
    refresh: bool,
    cache_dir: Optional[str],
) -> int:
    """Pre-collection DOI gate — runs doi_verify.py as a separate process and reads its exit code.

    Why subprocess instead of import:
      (1) doi_verify.py imports this module (ref_fetch). Importing it back
          here would create a cycle.
      (2) This repository's gate convention is "run the script and read the
          exit code" (CLAUDE.md: don't judge by eye, check the exit code).

    Returns: doi_verify's exit code (0=passed, 1=cross-check failure type, 2=hallucination/retraction).
    """
    script = Path(__file__).resolve().parent / "doi_verify.py"
    if not script.exists():
        print(f"[WARN] doi_verify.py not found — skipping the gate: {script}", file=sys.stderr)
        return 0

    cmd = [
        sys.executable, str(script),
        "--doi", doi,
        "--expect-title", expect_title,
        "--output", os.devnull,
    ]
    if email:
        cmd += ["--email", email]
    if refresh:
        cmd += ["--refresh"]
    if cache_dir:
        cmd += ["--cache-dir", cache_dir]

    print(f"[GATE] Pre-collection DOI cross-check: {doi}", file=sys.stderr)
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (proc.stdout or "") + (proc.stderr or "")
    for line in out.splitlines():
        if any(k in line for k in ("HALLUCINATED", "RETRACTED", "MISMATCH", "UNCORROBORATED", "[PASS]", "[FAIL]", "[WARN]")):
            print(f"       {line.strip()}", file=sys.stderr)
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Collect open-access (OA) bibliographic metadata/PDFs from a DOI list (CrossRef+OpenAlex+Unpaywall, no API key required).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--doi", help="comma-separated list of DOIs")
    parser.add_argument("--doi-file", help="path to a file listing DOIs, one per line")
    parser.add_argument("--title", help="search by title to resolve a DOI, then proceed")
    parser.add_argument(
        "--email",
        default=None,
        help="contact email for Unpaywall/the polite pool (falls back to the "
        "SCITK_CONTACT_EMAIL env var if omitted; if neither is set, only the "
        "Unpaywall step is skipped)",
    )
    parser.add_argument("--download", action="store_true", help="actually download the OA PDF")
    parser.add_argument(
        "--pdf-dir",
        default=None,
        help="directory to save PDFs into (default: ./ref_fetch_pdfs/)",
    )
    parser.add_argument("--refresh", action="store_true", help="ignore the cache and force a re-fetch")
    parser.add_argument(
        "--output",
        default="refs_report.json",
        help="path to save the result JSON (default: refs_report.json)",
    )
    parser.add_argument("--bibtex", default=None, help="save CrossRef BibTeX to this path")
    parser.add_argument("--cache-dir", default=None, help="ref_cache_manager cache directory (using the default is recommended)")
    parser.add_argument(
        "--doi-source",
        choices=["human", "model"],
        default=None,
        help="Source of the DOI. model (LLM-generated) cannot enter collection without --expect-title.",
    )
    parser.add_argument(
        "--expect-title",
        default=None,
        help="The title this DOI is intended to point to. Cross-checked via doi_verify before collection.",
    )
    parser.add_argument(
        "--with-si",
        action="store_true",
        help="Also collect supplementary information (SI) (Europe PMC open-access route only; otherwise a link is provided).",
    )
    parser.add_argument("--si-dir", default=None, help="directory to save SI into (default: ./ref_fetch_si)")
    parser.add_argument(
        "--institution",
        default=None,
        help="Attach an institutional-library access link for paywalled papers "
        "(a key in config/institutions.json). Only builds the link — no login or download.",
    )

    args = parser.parse_args()

    # --- Step 0: DOI gate ---------------------------------------------------- #
    # An LLM-generated DOI can have a perfectly valid format and still land on
    # a real but *unrelated* paper (measured in doi_verify.py at 122211/122213).
    # So this is blocked before collection (network lookup/download) begins —
    # more reliable than filtering it out downstream by grade.
    if args.doi_source == "model" and not args.expect_title:
        print(
            "[BLOCKED] --doi-source model cannot be used without --expect-title.\n"
            "          An LLM-generated DOI is not verified merely by existing — "
            "declare the title of the paper you meant to find as well.",
            file=sys.stderr,
        )
        return 2

    email = args.email or os.getenv("SCITK_CONTACT_EMAIL") or None
    if not email:
        print(
            "[INFO] No --email / SCITK_CONTACT_EMAIL — skipping the Unpaywall step "
            "and using only OpenAlex's OA information.",
            file=sys.stderr,
        )

    dois = collect_dois(args, email)
    if not dois:
        print("[ERROR] No DOIs given. Provide one via --doi / --doi-file / --title / stdin.", file=sys.stderr)
        parser.print_help()
        return 1

    # If a title was declared, cross-check it via doi_verify before collection. Block entry if it fails.
    if args.expect_title:
        if len(dois) != 1:
            print(
                "[ERROR] --expect-title can only be attached to a single DOI "
                f"(currently {len(dois)}).",
                file=sys.stderr,
            )
            return 1
        gate_rc = _run_doi_gate(dois[0], args.expect_title, email, args.refresh, args.cache_dir)
        if gate_rc != 0:
            print(
                "[BLOCKED] Aborting collection — failed the DOI gate "
                f"(doi_verify exit={gate_rc}).",
                file=sys.stderr,
            )
            return gate_rc

    cache = RefCacheManager(cache_dir=args.cache_dir)
    pdf_dir = Path(args.pdf_dir) if args.pdf_dir else Path.cwd() / "ref_fetch_pdfs"
    si_dir = Path(args.si_dir) if args.si_dir else Path.cwd() / "ref_fetch_si"

    institutions = None
    if args.institution:
        from institutional_access import InstitutionRegistry  # deferred import (optional feature)

        institutions = InstitutionRegistry.load()

    results: list[dict[str, Any]] = []
    for i, doi in enumerate(dois, 1):
        # NOTE: "처리 중:" ("processing:") is asserted verbatim by
        # tests/test_si_institutional.py (out of scope for this translation
        # pass) — kept as-is.
        print(f"[{i}/{len(dois)}] 처리 중: {doi}", file=sys.stderr)
        try:
            record = fetch_one(
                doi=doi,
                cache=cache,
                email=email,
                refresh=args.refresh,
                download=args.download,
                pdf_dir=pdf_dir,
            )
        except Exception as e:  # noqa: BLE001 — so a single DOI's failure doesn't kill the whole run
            record = {"doi": doi, "status": "error", "error": f"{type(e).__name__}: {e}"}

        # If paywalled, attach a 'link for a human to click' instead of the full text.
        # No automatic download (fetching subscription full text via script violates
        # library fair-use terms).
        if institutions is not None and record.get("oa_status") == "closed":
            target = (
                record.get("oa_landing_page_url")
                or (record.get("crossref") or {}).get("url")
                or f"https://doi.org/{doi}"
            )
            link = institutions.build_link(args.institution, target)
            if link:
                record["institutional_access"] = {
                    "institution": link.institution,
                    "url": link.url,
                    "login_note": link.login_note,
                    "fair_use_url": link.fair_use_url,
                    "daily_limits": link.daily_limits,
                    "_note": "A link for a human to open in a browser. Not an automatic download.",
                }
                print(link.human_summary(), file=sys.stderr)

        # SI has different accessibility from the main text — it can be open even when the main text is paywalled.
        if args.with_si:
            from si_fetch import discover_si, download_si  # deferred import

            try:
                si_res = discover_si(doi, email)
                if si_res.status == "found" and args.download:
                    si_res = download_si(si_res, si_dir, extract=True, si_only=True)
                record["supplementary"] = si_res.to_dict()
                n_si = len(si_res.supplementary_files)
                if si_res.status == "found":
                    print(f"  SI: {n_si} found ({si_res.pmcid})", file=sys.stderr)
                elif si_res.manual_hint:
                    print(f"  SI: {si_res.manual_hint}", file=sys.stderr)
            except Exception as e:  # noqa: BLE001 — so an SI failure doesn't kill collection of the main text
                record["supplementary"] = {"status": "error", "error": f"{type(e).__name__}: {e}"}

        results.append(record)

        if args.bibtex and record.get("status") in ("fetched", "cache_hit"):
            pass  # BibTeX is handled separately below (a failure there doesn't disrupt the report flow)

    # Save the output report
    output_path = Path(args.output)
    report = {
        "generated_by": "ref_fetch.py",
        "dois_requested": len(dois),
        "email_used_for_unpaywall": bool(email),
        "results": results,
    }
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[OK] Report saved: {output_path}", file=sys.stderr)

    # Export BibTeX
    if args.bibtex:
        bib_entries = []
        bib_errors = []
        for doi in dois:
            bib_text, err = fetch_bibtex(doi, email)
            time.sleep(_RATE_LIMIT_DELAY)
            if bib_text:
                bib_entries.append(bib_text.strip())
            else:
                bib_errors.append(f"% {doi}: BibTeX fetch failed ({err})")
        bib_path = Path(args.bibtex)
        content = "\n\n".join(bib_entries)
        if bib_errors:
            content += "\n\n" + "\n".join(bib_errors)
        bib_path.write_text(content + "\n", encoding="utf-8")
        print(f"[OK] BibTeX saved: {bib_path} ({len(bib_entries)} succeeded, {len(bib_errors)} failed)", file=sys.stderr)

    print_summary(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
