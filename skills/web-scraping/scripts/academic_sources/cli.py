"""Command line for fetch_academic: flags, source dispatch and `main`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from _common import (
    DEFAULT_CONTACT,
    PoliteHttpClient,
    Provenance,
    ScrapeError,
    add_common_cli_args,
    build_client_from_args,
    ensure_utf8_stdout,
    write_json_output,
)

from .arxiv_provider import ArxivProvider
from .biorxiv_provider import BiorxivProvider
from .crossref_provider import CrossrefProvider
from .ezproxy import EZproxyPdfDownloader
from .library_auth import InstitutionalLibraryAuth
from .open_access import PmcPdfLocator, UnpaywallProvider
from .pdf_downloader import PdfDownloader


def _add_source_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source", required=True,
                        choices=["crossref", "arxiv", "biorxiv"],
                        help="metadata source")
    parser.add_argument("--query", default=None,
                        help="keyword query (crossref / arxiv)")
    parser.add_argument("--doi", default=None,
                        help="DOI lookup (crossref / biorxiv)")
    parser.add_argument("--recent", default=None,
                        help="biorxiv: days back to list, e.g. 30")
    parser.add_argument("--server", default="biorxiv",
                        choices=["biorxiv", "medrxiv"],
                        help="biorxiv source server (default biorxiv)")
    parser.add_argument("-n", "--limit", type=int, default=10,
                        help="max results for keyword search (default 10)")
    parser.add_argument("-o", "--output", default=None,
                        help="output JSON path (default: stdout)")


def _add_download_args(parser: argparse.ArgumentParser) -> None:
    dl_group = parser.add_argument_group("PDF download options")
    dl_group.add_argument("--download", action="store_true",
                          help="attempt to download PDF after metadata lookup "
                               "(crossref only; tries Crossref → Unpaywall → PMC → EZproxy)")
    dl_group.add_argument("--download-dir", default="./downloads",
                          help="directory for downloaded PDFs (default ./downloads)")
    dl_group.add_argument("--ezproxy", action="store_true",
                          help="activate institutional EZproxy as final PDF fallback "
                               "(requires cookie file; use with --download)")
    dl_group.add_argument("--auto-login", action="store_true",
                          help="use Selenium auto-login for EZproxy "
                               "(reads credentials from secrets.json; "
                               "implies --ezproxy; use with --download)")
    dl_group.add_argument("--libkey", action="store_true",
                          help="use LibKey Nomad (Chrome MCP) as source 3.5 fallback "
                               "(institutional subscriptions; only works inside "
                               "a Claude Code session with Chrome MCP active; "
                               "use with --download)")
    dl_group.add_argument("--cookie-file",
                          default=EZproxyPdfDownloader.DEFAULT_COOKIE_FILE,
                          help="Netscape-format cookie file for EZproxy "
                               f"(default: {EZproxyPdfDownloader.DEFAULT_COOKIE_FILE})")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Retrieve scholarly metadata + full-text links "
                    "from Crossref / arXiv / bioRxiv.",
    )
    _add_source_args(parser)
    _add_download_args(parser)
    add_common_cli_args(parser)
    return parser


def _run_crossref(args, client: Optional[PoliteHttpClient] = None
                  ) -> tuple[dict, str]:
    provider = CrossrefProvider()
    if args.doi:
        record = provider.lookup_doi(args.doi)
        if getattr(args, "download", False) and client is not None:
            record = _download_pdf_for_record(record, client, args)
        return {"record": record}, "fetch_academic:crossref"
    if args.query:
        results = provider.search(args.query, args.limit)
        if getattr(args, "download", False) and client is not None:
            results = [_download_pdf_for_record(r, client, args)
                       for r in results]
        return {"results": results}, "fetch_academic:crossref"
    raise ScrapeError("crossref needs either --doi or --query")


def _download_pdf_for_record(record: dict, client: PoliteHttpClient,
                              args) -> dict:
    """Run PDF download pipeline for one metadata record."""
    contact = DEFAULT_CONTACT
    unpaywall = UnpaywallProvider(client, contact=contact)
    pmc = PmcPdfLocator(client, contact=contact)

    auto_login = getattr(args, "auto_login", False)
    use_ezproxy = getattr(args, "ezproxy", False) or auto_login
    use_libkey = getattr(args, "libkey", False)
    ezproxy_inst: Optional[EZproxyPdfDownloader] = None

    if use_ezproxy:
        if auto_login:
            # Auto-login mode: use real Chrome profile (no secrets.json needed)
            auth = InstitutionalLibraryAuth()
            ezproxy_inst = EZproxyPdfDownloader(auth=auth)
        else:
            # Legacy cookie file mode
            cookie_file = getattr(args, "cookie_file",
                                  EZproxyPdfDownloader.DEFAULT_COOKIE_FILE)
            ezproxy_inst = EZproxyPdfDownloader(cookie_file=cookie_file)

    downloader = PdfDownloader(
        client=client,
        unpaywall=unpaywall,
        pmc=pmc,
        dest_dir=Path(args.download_dir),
        use_ezproxy=use_ezproxy,
        ezproxy=ezproxy_inst,
        use_libkey=use_libkey,
    )
    return downloader.download(record)


def _run_arxiv(args) -> tuple[dict, str]:
    if not args.query:
        raise ScrapeError("arxiv needs --query")
    provider = ArxivProvider()
    return ({"results": provider.search(args.query, args.limit)},
            "fetch_academic:arxiv")


def _run_biorxiv(args, client: PoliteHttpClient) -> tuple[dict, str]:
    provider = BiorxivProvider(client, server=args.server)
    if args.doi:
        return ({"record": provider.lookup_doi(args.doi)},
                "fetch_academic:biorxiv")
    if args.recent:
        return ({"recent": provider.recent(args.recent)},
                "fetch_academic:biorxiv")
    raise ScrapeError("biorxiv needs either --doi or --recent")


def _dispatch(args) -> tuple[dict, str, str]:
    """Run the selected source; returns (data, provenance method, source url)."""
    if args.source == "crossref":
        # Crossref itself doesn't need the HTTP client, but --download does.
        if getattr(args, "download", False):
            with build_client_from_args(args) as client:
                data, method = _run_crossref(args, client)
        else:
            data, method = _run_crossref(args)
        return data, method, "https://api.crossref.org/works"
    if args.source == "arxiv":
        data, method = _run_arxiv(args)
        return data, method, "http://export.arxiv.org/api/query"
    # biorxiv
    with build_client_from_args(args) as client:
        data, method = _run_biorxiv(args, client)
    return data, method, BiorxivProvider.API_ROOT


def main(argv: Optional[list[str]] = None) -> int:
    ensure_utf8_stdout()
    args = _build_parser().parse_args(argv)
    try:
        data, method, source_url = _dispatch(args)
    except ScrapeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    provenance = Provenance(source_url=source_url, method=method)
    text = write_json_output(data, args.output, provenance)
    if args.output:
        print(f"Wrote {args.output}")
    else:
        print(text)
    return 0
