"""The PDF download waterfall: Crossref links, Unpaywall, PMC, LibKey, EZproxy."""

from __future__ import annotations

import re
import warnings
from pathlib import Path
from typing import Optional

from _common import PoliteHttpClient, resolve_within, sanitize_filename

from .ezproxy import EZproxyPdfDownloader
from .libkey import LibKeyNomadProvider
from .open_access import PmcPdfLocator, UnpaywallProvider
from .pdf_identity import check_downloaded_pdf


def _doi_to_safe_filename(doi: str) -> str:
    """Convert a DOI to a filesystem-safe string (replaces / and : with _)."""
    return re.sub(r"[/:\\]", "_", doi)


class PdfDownloader:
    """Downloads a PDF for a metadata record using up to five fallback sources.

    Priority:
      1. Crossref ``pdf_links`` (publisher CDN, may be paywalled)
      2. Unpaywall best OA PDF
      3. PubMed Central (PMC) PDF
      3.5 LibKey Nomad (Chrome MCP; institutionally subscribed journals, lighter than EZproxy)
      4. Institutional EZproxy (optional, Selenium-based)

    Download failures emit warnings and are recorded in the returned dict
    rather than raising exceptions, so batch runs continue uninterrupted.
    """

    def __init__(self, client: PoliteHttpClient,
                 unpaywall: UnpaywallProvider,
                 pmc: PmcPdfLocator,
                 dest_dir: Path,
                 use_ezproxy: bool = False,
                 ezproxy: Optional[EZproxyPdfDownloader] = None,
                 use_libkey: bool = False,
                 libkey: Optional[LibKeyNomadProvider] = None) -> None:
        self._client = client
        self._unpaywall = unpaywall
        self._pmc = pmc
        self.dest_dir = Path(dest_dir)
        self.dest_dir.mkdir(parents=True, exist_ok=True)
        self._use_ezproxy = use_ezproxy
        self._use_libkey = use_libkey
        # Allow caller to inject a custom EZproxyPdfDownloader instance;
        # otherwise create a default one if EZproxy is enabled.
        self._ezproxy = ezproxy if ezproxy is not None else (
            EZproxyPdfDownloader() if use_ezproxy else None
        )
        self._libkey = libkey if libkey is not None else (
            LibKeyNomadProvider() if use_libkey else None
        )

    def download(self, record: dict) -> dict:
        """Try to download the PDF for ``record``.  Returns augmented record.

        Adds keys: ``downloaded_path`` (str or None), ``download_source``
        (which fallback succeeded), ``download_status`` ("ok" / warning msg).
        """
        doi = record.get("doi") or ""
        authors = record.get("authors") or []
        first_author = (
            (authors[0] or "").split()[-1] if authors else "unknown"
        )
        year = record.get("year") or "unknownyear"
        doi_safe = _doi_to_safe_filename(doi) if doi else "nodoi"
        # The DOI is sanitized (_doi_to_safe_filename) but first_author and year
        # come from the same untrusted Crossref record and were not — an
        # asymmetry inside one filename that reads as "this is sanitized"
        # (260730 audit). resolve_within re-checks containment regardless.
        stem = f"{first_author}_{year}_{doi_safe}"
        filename = sanitize_filename(f"{stem}.pdf", fallback="paper.pdf")

        dest = resolve_within(self.dest_dir, filename, fallback="paper.pdf")

        # The criteria for checking that the received file is "the requested paper" — already all present in record.
        expected = {
            "title": record.get("title") or "",
            "first_author": first_author if first_author != "unknown" else "",
            "journal": record.get("journal") or "",
            "year": year if year != "unknownyear" else None,
        }

        # Priority order; each source runs only if every earlier one fell through.
        sources = (
            lambda: self._from_crossref_links(record, dest, doi, expected),
            lambda: self._from_unpaywall(doi, dest, expected),
            lambda: self._from_pmc(doi, dest, expected),
            lambda: self._from_libkey(doi, stem, expected),
            lambda: self._from_ezproxy(doi, stem, expected),
        )
        for source in sources:
            result = source()
            if result is not None:
                return {**record, **result}
        return self._not_found(record, doi)

    # Each source returns a status dict on success and None to fall through to the
    # next one.

    def _from_crossref_links(self, record: dict, dest: Path, doi: str,
                             expected: dict) -> Optional[dict]:
        """Source 1: Crossref ``pdf_links``."""
        for pdf_url in (record.get("pdf_links") or []):
            result = self._try_download(pdf_url, dest, "crossref_direct",
                                        doi=doi, expected=expected)
            if result["download_status"].startswith("ok"):
                return result
        return None

    def _from_unpaywall(self, doi: str, dest: Path,
                        expected: dict) -> Optional[dict]:
        """Source 2: Unpaywall best OA PDF."""
        if doi:
            oa_url = self._unpaywall.get_oa_pdf_url(doi)
            if oa_url:
                result = self._try_download(oa_url, dest, "unpaywall", doi=doi, expected=expected)
                if result["download_status"].startswith("ok"):
                    return result
        return None

    def _from_pmc(self, doi: str, dest: Path, expected: dict) -> Optional[dict]:
        """Source 3: PubMed Central."""
        if doi:
            pmc_url = self._pmc.get_pmc_pdf_url(doi)
            if pmc_url:
                result = self._try_download(pmc_url, dest, "pmc", doi=doi, expected=expected)
                if result["download_status"].startswith("ok"):
                    return result
        return None

    def _from_libkey(self, doi: str, stem: str, expected: dict) -> Optional[dict]:
        """Source 3.5: LibKey Nomad (Chrome MCP, institutional subscription).

        Only works inside a Claude Code session; auto-skipped in a standalone CLI run.
        """
        if doi and self._use_libkey and self._libkey is not None:
            libkey_url = self._libkey.get_pdf_url(doi)
            if libkey_url:
                libkey_filename = sanitize_filename(
                    f"{stem}_libkey.pdf", fallback="paper_libkey.pdf")
                libkey_dest = resolve_within(self.dest_dir, libkey_filename,
                                             fallback="paper_libkey.pdf")
                result = self._try_download(libkey_url, libkey_dest, "libkey_nomad", doi=doi, expected=expected)
                if result["download_status"].startswith("ok"):
                    return result
        return None

    def _from_ezproxy(self, doi: str, stem: str, expected: dict) -> Optional[dict]:
        """Source 4: institutional EZproxy (optional)."""
        if doi and self._use_ezproxy and self._ezproxy is not None:
            ezproxy_filename = sanitize_filename(
                f"{stem}_ezproxy.pdf", fallback="paper_ezproxy.pdf")
            ezproxy_dest = resolve_within(self.dest_dir, ezproxy_filename,
                                          fallback="paper_ezproxy.pdf")
            result = self._ezproxy.download(
                doi, ezproxy_dest,
                rate_limiter=self._client.limiter,
                expected=expected,          # must pass the identity-verification criteria, or this gate is a no-op
            )
            if result["download_status"].startswith("ok"):
                return result
        return None

    def _not_found(self, record: dict, doi: str) -> dict:
        """All sources exhausted: warn and return the record with a failure status."""
        sources = "Crossref/Unpaywall/PMC"
        if self._use_libkey:
            sources += "/LibKey"
        if self._use_ezproxy:
            sources += "/EZproxy"
        warn_msg = f"PDF not found via {sources} for DOI '{doi}'"
        warnings.warn(warn_msg)
        return {
            **record,
            "downloaded_path": None,
            "download_source": None,
            "download_status": warn_msg,
        }

    def _try_download(self, url: str, dest: Path,
                      source: str, doi: str = "",
                      expected: Optional[dict] = None) -> dict:
        """Attempt streaming download; return status dict."""
        try:
            self._client.stream_to_file(url, dest)
            size = dest.stat().st_size
            if size < 1024:
                # Suspiciously small — likely an error page, not a real PDF
                dest.unlink(missing_ok=True)
                return {
                    "downloaded_path": None,
                    "download_source": source,
                    "download_status": f"response too small ({size} B), likely not a PDF",
                }
            # Size alone isn't enough — a 691 KB "someone else's paper" has passed this way before.
            return check_downloaded_pdf(dest, doi, expected, source, size)
        except Exception as exc:
            warnings.warn(f"Download failed from {source} ({url}): {exc}")
            return {
                "downloaded_path": None,
                "download_source": source,
                "download_status": f"download failed: {exc}",
            }
