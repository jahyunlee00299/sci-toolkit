"""Crossref metadata provider."""

from __future__ import annotations

from _common import DEFAULT_CONTACT, ScrapeError


class CrossrefProvider:
    """Crossref REST API access via habanero.

    Uses the polite pool (mailto in the request) so Crossref routes requests
    to faster, more reliable infrastructure.
    """

    name = "crossref"

    def __init__(self, contact: str = DEFAULT_CONTACT) -> None:
        try:
            from habanero import Crossref
        except ImportError as exc:
            raise ScrapeError(
                "habanero is required for the crossref source. "
                "Install: pip install habanero"
            ) from exc
        self._client = Crossref(mailto=contact)

    def lookup_doi(self, doi: str) -> dict:
        """Return metadata for a single DOI.

        Raises ScrapeError (not a raw HTTP error) when the DOI is unknown,
        so the CLI reports a clean message instead of a traceback.
        """
        try:
            result = self._client.works(ids=doi)
        except Exception as exc:  # habanero raises httpx.HTTPStatusError on 404
            raise ScrapeError(f"Crossref DOI lookup failed for '{doi}': {exc}") from exc
        return self._normalize(result.get("message", {}))

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """Return ``limit`` works matching ``query``, sorted by relevance."""
        try:
            result = self._client.works(query=query, limit=limit)
        except Exception as exc:
            raise ScrapeError(f"Crossref search failed for '{query}': {exc}") from exc
        items = result.get("message", {}).get("items", [])
        return [self._normalize(item) for item in items]

    @staticmethod
    def _normalize(item: dict) -> dict:
        """Map a Crossref work record to a uniform metadata dict."""
        authors = [
            " ".join(filter(None, [a.get("given"), a.get("family")]))
            for a in item.get("author", [])
        ]
        title = item.get("title") or [None]
        date_parts = (item.get("issued", {})
                          .get("date-parts", [[None]]))[0]
        return {
            "title": title[0] if title else None,
            "authors": authors,
            "year": date_parts[0] if date_parts else None,
            "doi": item.get("DOI"),
            "journal": (item.get("container-title") or [None])[0],
            "type": item.get("type"),
            "url": item.get("URL"),
            "is_referenced_by_count": item.get("is-referenced-by-count"),
            "pdf_links": [
                link.get("URL") for link in item.get("link", [])
                if link.get("content-type") == "application/pdf"
            ],
        }
