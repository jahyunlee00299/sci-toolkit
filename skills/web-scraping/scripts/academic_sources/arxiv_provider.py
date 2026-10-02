"""arXiv search provider."""

from __future__ import annotations

from _common import ScrapeError


class ArxivProvider:
    """arXiv search via the official-API-backed ``arxiv`` package."""

    name = "arxiv"

    def __init__(self) -> None:
        try:
            import arxiv
        except ImportError as exc:
            raise ScrapeError(
                "the 'arxiv' package is required for the arxiv source. "
                "Install: pip install arxiv"
            ) from exc
        self._arxiv = arxiv
        self._client = arxiv.Client()

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """Return ``limit`` arXiv results for ``query``, newest first."""
        search = self._arxiv.Search(
            query=query,
            max_results=limit,
            sort_by=self._arxiv.SortCriterion.SubmittedDate,
        )
        results = []
        try:
            for paper in self._client.results(search):
                results.append({
                    "title": paper.title,
                    "authors": [a.name for a in paper.authors],
                    "year": paper.published.year if paper.published else None,
                    "doi": paper.doi,
                    "arxiv_id": paper.get_short_id(),
                    "summary": paper.summary,
                    "url": paper.entry_id,
                    "pdf_links": [paper.pdf_url] if paper.pdf_url else [],
                    "categories": paper.categories,
                })
        except Exception as exc:
            raise ScrapeError(f"arXiv search failed for '{query}': {exc}") from exc
        return results
