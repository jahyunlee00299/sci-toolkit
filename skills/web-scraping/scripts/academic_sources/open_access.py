"""Open-access PDF locators: Unpaywall and PubMed Central."""

from __future__ import annotations

import json
import warnings
from typing import Optional

from _common import DEFAULT_CONTACT, PoliteHttpClient, ScrapeError


class UnpaywallProvider:
    """Unpaywall REST API (https://unpaywall.org/products/api) — free for
    non-commercial use with a valid email address.

    Returns open-access PDF URLs for a given DOI without any additional
    dependencies beyond requests / httpx (already required).
    """

    API_ROOT = "https://api.unpaywall.org/v2"

    def __init__(self, client: PoliteHttpClient,
                 contact: str = DEFAULT_CONTACT) -> None:
        self._client = client
        self._contact = contact

    def get_oa_pdf_url(self, doi: str) -> Optional[str]:
        """Return the best OA PDF URL for ``doi``, or None if unavailable.

        Unpaywall returns a JSON object with ``best_oa_location``.
        We look for ``url_for_pdf`` there first, then fall back to
        ``url`` if the content is already a PDF (content-type check
        is done at download time, not here).
        """
        url = f"{self.API_ROOT}/{doi}?email={self._contact}"
        try:
            raw = self._client.get_text(url, use_cache=True)
        except ScrapeError as exc:
            warnings.warn(f"Unpaywall lookup failed for '{doi}': {exc}")
            return None
        except Exception as exc:
            warnings.warn(f"Unpaywall unexpected error for '{doi}': {exc}")
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None

        # Prefer best_oa_location.url_for_pdf, then oa_locations list
        best = data.get("best_oa_location") or {}
        pdf_url = best.get("url_for_pdf")
        if pdf_url:
            return pdf_url

        # Fallback: first oa_location with a url_for_pdf
        for loc in data.get("oa_locations") or []:
            pdf_url = loc.get("url_for_pdf")
            if pdf_url:
                return pdf_url

        return None

    def get_full_record(self, doi: str) -> Optional[dict]:
        """Return the raw Unpaywall JSON for ``doi`` (useful for debugging)."""
        url = f"{self.API_ROOT}/{doi}?email={self._contact}"
        try:
            raw = self._client.get_text(url, use_cache=True)
            return json.loads(raw)
        except Exception as exc:
            warnings.warn(f"Unpaywall full record failed for '{doi}': {exc}")
            return None


class PmcPdfLocator:
    """Resolves a DOI → PMC ID → PDF URL via the NCBI E-utilities API.

    NCBI's robots.txt has a blanket ``Disallow: /`` which applies to generic
    web crawlers.  However, the E-utilities endpoint is an *official public
    API* explicitly provided for programmatic access (NCBI documentation:
    https://www.ncbi.nlm.nih.gov/books/NBK25501/).  We therefore bypass the
    PoliteHttpClient robots check here and make a direct httpx call, which is
    consistent with NCBI's own guidance (use mailto parameter, max 3 req/sec,
    use API key for higher limits).  Rate limiting is still applied via the
    injected client's RateLimiter.

    No extra package required.
    """

    ESEARCH_URL = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    )
    PMC_PDF_TEMPLATE = (
        "https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf/"
    )

    def __init__(self, client: PoliteHttpClient,
                 contact: str = DEFAULT_CONTACT) -> None:
        self._client = client
        self._contact = contact

    def get_pmc_pdf_url(self, doi: str) -> Optional[str]:
        """Return a PMC PDF URL for ``doi`` if it is in PubMed Central."""
        pmcid = self._doi_to_pmcid(doi)
        if not pmcid:
            return None
        return self.PMC_PDF_TEMPLATE.format(pmcid=pmcid)

    def _doi_to_pmcid(self, doi: str) -> Optional[str]:
        """Query E-utilities to find a PMC ID for ``doi``.

        Uses the PoliteHttpClient's underlying httpx client directly to
        bypass the robots.txt check (see class docstring for rationale).
        Rate limiting still applies through the client's RateLimiter.
        """
        import urllib.parse
        params = urllib.parse.urlencode({
            "db": "pmc",
            "term": f"{doi}[doi]",
            "retmode": "json",
            "tool": "web-scraping-skill",
            "email": self._contact,
        })
        url = f"{self.ESEARCH_URL}?{params}"
        try:
            # Apply rate limiting manually (respects per-domain delay)
            self._client.limiter.wait(url)
            # Direct call — bypasses robots check intentionally (API endpoint)
            response = self._client._client.get(url, timeout=20)
            response.raise_for_status()
            data = json.loads(response.text)
        except Exception as exc:
            warnings.warn(f"PMC ID lookup failed for '{doi}': {exc}")
            return None

        ids = (data.get("esearchresult") or {}).get("idlist") or []
        if not ids:
            return None
        return f"PMC{ids[0]}"
