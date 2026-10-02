"""fetch_academic.py - retrieve scholarly metadata and full-text links.

Sources (all official APIs, never page scraping):
  - crossref : DOI lookup + keyword search via habanero (Crossref REST API)
  - arxiv    : preprint search + PDF links via the arxiv package
  - biorxiv  : bioRxiv / medRxiv metadata via their public REST API

Each source is wrapped by a small provider class with a uniform ``search``
method, so adding a source later (chemRxiv, OpenAlex, ...) means adding one
class without touching the CLI. This is the Open/Closed principle in action.

Note on overlap with existing skills: the user already has pubmed-database,
openalex-database and biopython (Bio.Entrez). This script intentionally
covers Crossref / arXiv / bioRxiv only and defers PubMed/OpenAlex to those
skills.

Download support (--download flag):
  Priority order: (1) Crossref pdf_links, (2) Unpaywall best OA PDF,
  (3) PubMed Central PDF, (4) institutional EZproxy (if --ezproxy or --auto-login).
  Failures are warnings only; batch continues.
  Unpaywall API: https://api.unpaywall.org/v2/{doi}?email={contact}

EZproxy support:
  Uses an institutional library's N2 OpenLink proxy (configure PROXY_BASE in EZproxyPdfDownloader).
  Two modes:
  --ezproxy      : legacy — requires Netscape cookie file (see DEFAULT_COOKIE_FILE)
  --auto-login   : new    — Selenium Chrome (real profile) auto-login using browser-saved
                            auto-fill credentials; no secrets.json keys required.
  Activate with --download --ezproxy or --download --auto-login.

Dual use:
  - CLI:    python fetch_academic.py --source crossref --query "enzyme cascade" -n 10
  - CLI:    python fetch_academic.py --source crossref --doi 10.1039/D0GC00000A
  - CLI:    python fetch_academic.py --source crossref --doi 10.1039/D0GC00000A --download
  - CLI:    python fetch_academic.py --source crossref --doi 10.1039/D0GC00000A --download --ezproxy
  - CLI:    python fetch_academic.py --source crossref --doi 10.1039/D0GC00000A --download --auto-login
  - import: from fetch_academic import CrossrefProvider, ArxivProvider, UnpaywallProvider
  - import: from fetch_academic import EZproxyPdfDownloader, InstitutionalLibraryAuth

Layout: this file is the CLI entry point and re-exports every name the single-file
script defined. The sources and backends live in the `academic_sources` package
next to it (see its docstring for the module map).
"""

from __future__ import annotations

# Names the single-file script exposed as module attributes are kept importable
# (`from fetch_academic import ...`, and `fetch_academic.warnings` style access).
import argparse  # noqa: F401
import datetime  # noqa: F401
import http.cookiejar  # noqa: F401
import json  # noqa: F401
import os  # noqa: F401
import re  # noqa: F401
import sys  # noqa: F401
import time  # noqa: F401
import warnings  # noqa: F401
from pathlib import Path  # noqa: F401
from typing import Optional  # noqa: F401
from urllib.parse import urlparse  # noqa: F401

from _common import (  # noqa: F401
    DEFAULT_CONTACT,
    HttpClientConfig,
    PoliteHttpClient,
    Provenance,
    ScrapeError,
    UnsafeTargetError,
    add_common_cli_args,
    build_client_from_args,
    ensure_utf8_stdout,
    resolve_within,
    sanitize_filename,
    validate_url,
    write_json_output,
)
from academic_sources.arxiv_provider import ArxivProvider  # noqa: F401
from academic_sources.biorxiv_provider import BiorxivProvider  # noqa: F401
from academic_sources.cli import (  # noqa: F401
    _build_parser,
    _download_pdf_for_record,
    _run_arxiv,
    _run_biorxiv,
    _run_crossref,
    main,
)
from academic_sources.crossref_provider import CrossrefProvider  # noqa: F401
from academic_sources.ezproxy import (  # noqa: F401
    EZPROXY_COOKIE_GUIDANCE,
    CookieNotFoundError,
    EZproxyPdfDownloader,
    load_netscape_cookies,
)
from academic_sources.libkey import LibKeyNomadProvider  # noqa: F401
from academic_sources.library_auth import InstitutionalLibraryAuth  # noqa: F401
from academic_sources.open_access import PmcPdfLocator, UnpaywallProvider  # noqa: F401
from academic_sources.pdf_downloader import PdfDownloader, _doi_to_safe_filename  # noqa: F401
from academic_sources.pdf_identity import (  # noqa: F401
    _PDF_STOPWORDS,
    _title_tokens,
    verify_pdf_identity,
)


if __name__ == "__main__":
    raise SystemExit(main())
