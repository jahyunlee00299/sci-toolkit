"""bioRxiv / medRxiv provider (public REST API)."""

from __future__ import annotations

from _common import PoliteHttpClient, ScrapeError


class BiorxivProvider:
    """bioRxiv / medRxiv metadata via their public REST API.

    The API does not support keyword search; it serves recent windows and
    DOI lookups. Provide a DOI for a single record, or a date range for a
    recent listing.
    """

    name = "biorxiv"
    API_ROOT = "https://api.biorxiv.org"

    def __init__(self, client: PoliteHttpClient, server: str = "biorxiv") -> None:
        self._client = client
        self.server = server  # "biorxiv" or "medrxiv"

    def lookup_doi(self, doi: str) -> dict:
        """Return metadata for a bioRxiv/medRxiv preprint by DOI."""
        url = f"{self.API_ROOT}/details/{self.server}/{doi}"
        return self._fetch(url)

    def recent(self, interval: str = "30") -> dict:
        """Return preprints from the last ``interval`` days (string)."""
        url = f"{self.API_ROOT}/details/{self.server}/{interval}"
        return self._fetch(url)

    def _fetch(self, url: str) -> dict:
        import json

        raw = self._client.get_text(url)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ScrapeError(f"bioRxiv API returned non-JSON: {url}") from exc
        collection = payload.get("collection", [])
        records = [
            {
                "title": rec.get("title"),
                "authors": rec.get("authors"),
                "year": (rec.get("date") or "")[:4] or None,
                "doi": rec.get("doi"),
                "category": rec.get("category"),
                "url": (f"https://www.{self.server}.org/content/"
                        f"{rec.get('doi')}"),
                "pdf_links": [
                    f"https://www.{self.server}.org/content/"
                    f"{rec.get('doi')}.full.pdf"
                ] if rec.get("doi") else [],
            }
            for rec in collection
        ]
        return {"messages": payload.get("messages"), "records": records}
