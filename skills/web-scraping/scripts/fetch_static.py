"""fetch_static.py - extract content from static HTML pages.

Modes of extraction (selectable, combinable via CLI):
  - text   : main article text + metadata via trafilatura (boilerplate removed)
  - tables : every HTML <table> as structured rows via pandas.read_html
  - links  : all hyperlinks, with absolute URLs and anchor text
  - html   : the raw fetched HTML (useful for piping / debugging)

Parsing backends, in line with the researcher's recommended stack:
  - trafilatura  : main-content extraction (text mode)
  - selectolax   : fast CSS-selector parsing (links mode, primary)
  - lxml / bs4   : fallbacks selectolax cannot cover

Dual use:
  - CLI:     python fetch_static.py URL --mode text tables -o out.json
  - import:  from fetch_static import StaticScraper

SOLID note: StaticScraper holds extraction logic only; all networking is
delegated to PoliteHttpClient from _common.
"""

from __future__ import annotations

import argparse
import io
import sys
from typing import Optional
from urllib.parse import urljoin

from _common import (
    Provenance,
    PoliteHttpClient,
    ScrapeError,
    add_common_cli_args,
    build_client_from_args,
    write_json_output,
    ensure_utf8_stdout,
)


class StaticScraper:
    """Extracts text, tables, and links from a static HTML document.

    The scraper does not fetch on its own; pass in HTML (via :meth:`from_url`
    using an injected client, or directly via the constructor) so it stays
    testable and decoupled from networking.
    """

    def __init__(self, html: str, base_url: str = "") -> None:
        self.html = html
        self.base_url = base_url

    # -- construction ------------------------------------------------------

    @classmethod
    def from_url(cls, url: str, client: PoliteHttpClient) -> "StaticScraper":
        """Fetch ``url`` with ``client`` and wrap the result."""
        html = client.get_text(url)
        return cls(html=html, base_url=url)

    # -- extraction: text --------------------------------------------------

    def extract_text(self) -> dict:
        """Return main-content text + metadata using trafilatura.

        Falls back to a naive selectolax text dump if trafilatura is absent
        or yields nothing.
        """
        result: dict = {"text": None, "metadata": {}, "extractor": None}
        try:
            import trafilatura
            from trafilatura import extract, extract_metadata

            text = extract(
                self.html,
                output_format="markdown",
                include_tables=True,
                include_links=True,
                with_metadata=False,
            )
            if text:
                result["text"] = text
                result["extractor"] = "trafilatura"
                meta = extract_metadata(self.html)
                if meta is not None:
                    result["metadata"] = {
                        "title": meta.title,
                        "author": meta.author,
                        "date": meta.date,
                        "sitename": meta.sitename,
                        "description": meta.description,
                    }
                return result
        except ImportError:
            pass  # fall through to selectolax

        # Fallback: strip tags with selectolax.
        result["text"] = self._fallback_text()
        result["extractor"] = "selectolax-fallback"
        return result

    def _fallback_text(self) -> str:
        try:
            from selectolax.parser import HTMLParser

            tree = HTMLParser(self.html)
            for tag in tree.css("script, style, nav, footer, header"):
                tag.decompose()
            body = tree.body or tree.root
            return body.text(separator="\n", strip=True) if body else ""
        except ImportError:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(self.html, "lxml")
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            return soup.get_text(separator="\n", strip=True)

    # -- extraction: tables ------------------------------------------------

    def extract_tables(self) -> list[dict]:
        """Return every HTML <table> as a list of row dicts.

        Uses pandas.read_html. Each table is reported with its column names
        and rows; non-tabular markup is skipped silently by pandas.
        """
        try:
            import pandas as pd
        except ImportError as exc:
            raise ScrapeError("pandas is required for table extraction") from exc

        try:
            frames = pd.read_html(io.StringIO(self.html), flavor="lxml")
        except ValueError:
            return []  # "No tables found" is not an error
        except ImportError:
            # lxml not available, fall back to bs4/html5lib if present
            try:
                frames = pd.read_html(io.StringIO(self.html))
            except (ValueError, ImportError):
                return []

        tables: list[dict] = []
        for index, frame in enumerate(frames):
            frame = frame.where(frame.notna(), None)
            tables.append({
                "index": index,
                "n_rows": int(frame.shape[0]),
                "n_cols": int(frame.shape[1]),
                "columns": [str(col) for col in frame.columns],
                "rows": frame.astype(object).values.tolist(),
            })
        return tables

    # -- extraction: links -------------------------------------------------

    def extract_links(self) -> list[dict]:
        """Return all <a href> links with absolute URLs and anchor text."""
        links: list[dict] = []
        seen: set[str] = set()
        try:
            from selectolax.parser import HTMLParser

            tree = HTMLParser(self.html)
            anchors = [
                (node.attributes.get("href"), node.text(strip=True))
                for node in tree.css("a")
            ]
        except ImportError:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(self.html, "lxml")
            anchors = [
                (a.get("href"), a.get_text(strip=True))
                for a in soup.find_all("a")
            ]

        for href, text in anchors:
            if not href or href.startswith(("#", "javascript:", "mailto:")):
                continue
            absolute = urljoin(self.base_url, href) if self.base_url else href
            if absolute in seen:
                continue
            seen.add(absolute)
            links.append({"url": absolute, "text": text})
        return links


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract text / tables / links from a static HTML page.",
    )
    parser.add_argument("url", help="page URL to fetch")
    parser.add_argument(
        "--mode", nargs="+", default=["text"],
        choices=["text", "tables", "links", "html"],
        help="what to extract (space-separated, default: text)",
    )
    parser.add_argument("-o", "--output", default=None,
                        help="output JSON path (default: print to stdout)")
    add_common_cli_args(parser)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    ensure_utf8_stdout()
    args = _build_parser().parse_args(argv)
    try:
        with build_client_from_args(args) as client:
            scraper = StaticScraper.from_url(args.url, client)
            data: dict = {}
            if "text" in args.mode:
                data["text"] = scraper.extract_text()
            if "tables" in args.mode:
                data["tables"] = scraper.extract_tables()
            if "links" in args.mode:
                data["links"] = scraper.extract_links()
            if "html" in args.mode:
                data["html"] = scraper.html
    except ScrapeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    provenance = Provenance(source_url=args.url, method="fetch_static")
    text = write_json_output(data, args.output, provenance)
    if args.output:
        print(f"Wrote {args.output}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
