"""harvest_files.py - discover and download document files from a page.

Workflow:
  1. Fetch a page and scan its links for document files
     (.pdf .docx .xlsx .xls .pptx .csv .zip ... configurable).
  2. Download each matching file via streaming (memory-safe for big PDFs).
  3. Optionally hand each download to the markitdown skill for Markdown
     conversion (LLM-friendly text).

DOI input support (--doi / --doi-list):
  When a DOI is given instead of a URL the script:
    1. Queries Crossref for metadata + pdf_links.
    2. Queries Unpaywall for an open-access PDF URL.
    3. Resolves https://doi.org/{doi} to the landing page and scans it for
       PDF links (via StaticScraper / fetch_static.py).
    4. Runs the normal download logic on all discovered URLs.

The markitdown step is *delegation*, not reimplementation: the user already
has a markitdown skill. This script only prints the recommended command and,
if the markitdown package is importable, can run the conversion directly.

Dual use:
  - CLI:    python harvest_files.py URL -o ./downloads --ext pdf xlsx --convert
  - CLI:    python harvest_files.py --doi 10.1039/c8gc03729a -o ./downloads
  - CLI:    python harvest_files.py --doi-list dois.txt -o ./downloads
  - import: from harvest_files import FileHarvester, DoiHarvester
"""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlparse

from _common import (
    DEFAULT_CONTACT,
    Provenance,
    PoliteHttpClient,
    ScrapeError,
    add_common_cli_args,
    build_client_from_args,
    resolve_within,
    sanitize_filename,
    write_json_output,
    ensure_utf8_stdout,
)
from fetch_static import StaticScraper
from fetch_academic import (
    CrossrefProvider,
    UnpaywallProvider,
    PmcPdfLocator,
    PdfDownloader,
)


# Document extensions worth harvesting for a research workflow.
DEFAULT_EXTENSIONS = ("pdf", "docx", "xlsx", "xls", "pptx", "csv", "zip")


class FileHarvester:
    """Finds document links on a page and downloads them.

    Networking is delegated to an injected PoliteHttpClient; this class only
    decides *what* to download and *where* to put it.
    """

    def __init__(self, client: PoliteHttpClient,
                 extensions: tuple[str, ...] = DEFAULT_EXTENSIONS) -> None:
        self._client = client
        self.extensions = tuple(e.lower().lstrip(".") for e in extensions)

    # -- discovery ---------------------------------------------------------

    def discover(self, page_url: str) -> list[dict]:
        """Return document links found on ``page_url`` matching ``extensions``."""
        scraper = StaticScraper.from_url(page_url, self._client)
        matches: list[dict] = []
        for link in scraper.extract_links():
            ext = self._extension_of(link["url"])
            if ext in self.extensions:
                matches.append({
                    "url": link["url"],
                    "text": link["text"],
                    "extension": ext,
                    "filename": self._filename_of(link["url"]),
                })
        return matches

    @staticmethod
    def _extension_of(url: str) -> str:
        path = urlparse(url).path
        return path.rsplit(".", 1)[-1].lower() if "." in path else ""

    @staticmethod
    def _filename_of(url: str) -> str:
        """Derive a safe local filename from a remote URL.

        The last path segment is attacker-controlled text: ``unquote()`` turns
        ``%2e%2e%2f`` into ``../`` and a Windows drive prefix survives intact,
        which put a file outside the destination directory in the 260730 audit
        (``C:\\Users\\pwned.pdf`` reproduced). Sanitizing happens here so every
        caller of ``discover()`` gets a clean value, and ``download()`` re-checks
        containment rather than trusting this.
        """
        path = urlparse(url).path
        name = unquote(path.rsplit("/", 1)[-1])
        return sanitize_filename(name, fallback="download")

    # -- download ----------------------------------------------------------

    def download(self, file_info: dict, dest_dir: Path) -> dict:
        """Download one discovered file into ``dest_dir``.

        Returns the file_info dict augmented with ``local_path`` and
        ``status``. A failed download is reported, not raised, so a batch
        run continues.
        """
        dest_dir = Path(dest_dir)
        result = dict(file_info)
        try:
            # Containment is re-checked here, independently of _filename_of:
            # file_info may have been built by a caller or read from JSON, and
            # _unique_path only prevents overwrites, never traversal.
            dest = self._unique_path(
                resolve_within(dest_dir, file_info["filename"])
            )
            self._client.stream_to_file(file_info["url"], dest)
            result["local_path"] = str(dest)
            result["size_bytes"] = dest.stat().st_size
            result["status"] = "ok"
        except (ScrapeError, OSError) as exc:
            result["local_path"] = None
            result["status"] = f"failed: {exc}"
        return result

    @staticmethod
    def _unique_path(path: Path) -> Path:
        """Return a non-colliding path by appending _1, _2, ... if needed."""
        if not path.exists():
            return path
        stem, suffix, counter = path.stem, path.suffix, 1
        while True:
            candidate = path.with_name(f"{stem}_{counter}{suffix}")
            if not candidate.exists():
                return candidate
            counter += 1

    def harvest(self, page_url: str, dest_dir: Path,
                limit: Optional[int] = None) -> list[dict]:
        """Discover and download all matching files from ``page_url``."""
        discovered = self.discover(page_url)
        if limit is not None:
            discovered = discovered[:limit]
        return [self.download(item, dest_dir) for item in discovered]


class DoiHarvester:
    """Resolves one or more DOIs to PDF files using a multi-step pipeline.

    Pipeline per DOI:
      1. CrossrefProvider.lookup_doi → metadata + publisher pdf_links
      2. UnpaywallProvider.get_oa_pdf_url → open-access PDF URL
      3. doi.org redirect → landing page → StaticScraper PDF link scan
      4. PdfDownloader (tries sources in priority order)

    All failures are warnings; a batch of DOIs will always complete.
    """

    DOI_RESOLVER = "https://doi.org/"

    def __init__(self, client: PoliteHttpClient,
                 dest_dir: Path,
                 contact: str = DEFAULT_CONTACT) -> None:
        self._client = client
        self.dest_dir = Path(dest_dir)
        self._crossref = CrossrefProvider(contact=contact)
        self._unpaywall = UnpaywallProvider(client, contact=contact)
        self._pmc = PmcPdfLocator(client, contact=contact)
        self._downloader = PdfDownloader(
            client=client,
            unpaywall=self._unpaywall,
            pmc=self._pmc,
            dest_dir=self.dest_dir,
        )

    def harvest_doi(self, doi: str) -> dict:
        """Run the full pipeline for one ``doi``.  Returns a result dict."""
        doi = doi.strip()
        result: dict = {"doi": doi}

        # Step 1: Crossref metadata
        try:
            record = self._crossref.lookup_doi(doi)
        except ScrapeError as exc:
            warnings.warn(f"Crossref lookup failed for '{doi}': {exc}")
            record = {"doi": doi, "pdf_links": []}
        result["metadata"] = record

        # Step 2 + 3: supplement pdf_links with Unpaywall + landing page scan
        extra_pdf_urls = self._collect_extra_pdf_urls(doi)
        combined_pdf_links = list(dict.fromkeys(
            (record.get("pdf_links") or []) + extra_pdf_urls
        ))
        record = {**record, "pdf_links": combined_pdf_links}

        # Step 4: attempt download
        download_result = self._downloader.download(record)
        result.update(download_result)
        return result

    def _collect_extra_pdf_urls(self, doi: str) -> list[str]:
        """Gather PDF URLs from Unpaywall + DOI landing page."""
        urls: list[str] = []

        # Unpaywall OA PDF
        oa_url = self._unpaywall.get_oa_pdf_url(doi)
        if oa_url:
            urls.append(oa_url)

        # Landing page scan via doi.org redirect
        landing_url = f"{self.DOI_RESOLVER}{doi}"
        try:
            scraper = StaticScraper.from_url(landing_url, self._client)
            for link in scraper.extract_links():
                href = link.get("url", "")
                if href.lower().endswith(".pdf") or "/pdf" in href.lower():
                    if href not in urls:
                        urls.append(href)
        except ScrapeError as exc:
            warnings.warn(
                f"Landing page scan failed for doi.org/{doi}: {exc}"
            )
        except Exception as exc:
            warnings.warn(
                f"Landing page scan unexpected error for '{doi}': {exc}"
            )
        return urls

    def harvest_batch(self, dois: list[str]) -> list[dict]:
        """Run ``harvest_doi`` for each DOI in ``dois``."""
        return [self.harvest_doi(doi) for doi in dois]


def convert_with_markitdown(path: str) -> dict:
    """Convert one downloaded file to Markdown via the markitdown package.

    This mirrors what the user's markitdown skill does. If markitdown is not
    importable, returns a status pointing the caller at that skill instead.
    """
    try:
        from markitdown import MarkItDown
    except ImportError:
        return {
            "converted": False,
            "note": "markitdown not importable; use the markitdown skill: "
                    f"markitdown \"{path}\" -o \"{Path(path).with_suffix('.md')}\"",
        }
    try:
        md_path = Path(path).with_suffix(".md")
        result = MarkItDown().convert(path)
        md_path.write_text(result.text_content, encoding="utf-8")
        return {"converted": True, "markdown_path": str(md_path)}
    except Exception as exc:  # conversion is best-effort
        return {"converted": False, "note": f"conversion failed: {exc}"}


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Discover and download document files (PDF/XLSX/DOCX...) "
                    "linked from a page or resolved from a DOI, optionally "
                    "converting to Markdown.",
    )
    # url is now optional so --doi / --doi-list can be used instead
    parser.add_argument("url", nargs="?", default=None,
                        help="page URL to scan for file links "
                             "(omit when using --doi / --doi-list)")
    parser.add_argument("-o", "--output-dir", default="./downloads",
                        help="directory for downloaded files (default ./downloads)")
    parser.add_argument("--ext", nargs="+", default=list(DEFAULT_EXTENSIONS),
                        help="file extensions to harvest "
                             f"(default: {' '.join(DEFAULT_EXTENSIONS)})")
    parser.add_argument("-n", "--limit", type=int, default=None,
                        help="max files to download (default: all found)")
    parser.add_argument("--discover-only", action="store_true",
                        help="list matching links without downloading "
                             "(URL mode only)")
    parser.add_argument("--convert", action="store_true",
                        help="convert each download to Markdown via markitdown")
    parser.add_argument("--report", default=None,
                        help="write a JSON harvest report to this path")
    # DOI input options
    doi_group = parser.add_argument_group("DOI input options")
    doi_group.add_argument("--doi", default=None,
                           help="single DOI to resolve and download PDF for")
    doi_group.add_argument("--doi-list", default=None,
                           help="path to a plain-text file with one DOI per line "
                                "for batch download")
    add_common_cli_args(parser)
    return parser


def _run_url_mode(args, client: PoliteHttpClient) -> tuple[dict, str]:
    """Original URL-based harvesting logic."""
    harvester = FileHarvester(client, extensions=tuple(args.ext))

    if args.discover_only:
        discovered = harvester.discover(args.url)
        if args.limit is not None:
            discovered = discovered[:args.limit]
        return {"discovered": discovered, "count": len(discovered)}, args.url

    results = harvester.harvest(
        args.url, Path(args.output_dir), limit=args.limit
    )
    if args.convert:
        for item in results:
            if item.get("status") == "ok" and item.get("local_path"):
                item["markitdown"] = convert_with_markitdown(
                    item["local_path"]
                )
    ok = sum(1 for r in results if r.get("status") == "ok")
    data = {
        "downloaded": results,
        "count": len(results),
        "succeeded": ok,
        "failed": len(results) - ok,
    }
    return data, args.url


def _run_doi_mode(args, client: PoliteHttpClient) -> tuple[dict, str]:
    """DOI-based PDF harvesting using DoiHarvester."""
    doi_harvester = DoiHarvester(
        client=client,
        dest_dir=Path(args.output_dir),
    )

    # Collect DOIs from --doi and/or --doi-list
    dois: list[str] = []
    if args.doi:
        dois.append(args.doi.strip())
    if args.doi_list:
        doi_list_path = Path(args.doi_list)
        if not doi_list_path.exists():
            raise ScrapeError(f"--doi-list file not found: {args.doi_list}")
        raw_lines = doi_list_path.read_text(encoding="utf-8").splitlines()
        dois.extend(
            line.strip() for line in raw_lines
            if line.strip() and not line.strip().startswith("#")
        )

    if not dois:
        raise ScrapeError("--doi / --doi-list produced no DOIs to process")

    if args.limit is not None:
        dois = dois[: args.limit]

    results = doi_harvester.harvest_batch(dois)

    if args.convert:
        for item in results:
            local = item.get("downloaded_path")
            if item.get("download_status") == "ok" and local:
                item["markitdown"] = convert_with_markitdown(local)

    ok = sum(1 for r in results if r.get("download_status") == "ok")
    data = {
        "downloaded": results,
        "count": len(results),
        "succeeded": ok,
        "failed": len(results) - ok,
    }
    source_url = (
        f"doi:{dois[0]}" if len(dois) == 1
        else f"doi-batch:{len(dois)}-items"
    )
    return data, source_url


def main(argv: Optional[list[str]] = None) -> int:
    ensure_utf8_stdout()
    args = _build_parser().parse_args(argv)

    # Validate: must provide either url or --doi/--doi-list
    doi_mode = bool(args.doi or args.doi_list)
    if not doi_mode and not args.url:
        print(
            "ERROR: provide a URL positional argument, or use --doi / --doi-list",
            file=sys.stderr,
        )
        return 1

    try:
        with build_client_from_args(args) as client:
            if doi_mode:
                data, source_url = _run_doi_mode(args, client)
            else:
                data, source_url = _run_url_mode(args, client)
    except ScrapeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    provenance = Provenance(source_url=source_url, method="harvest_files")
    text = write_json_output(data, args.report, provenance)
    if args.report:
        print(f"Wrote report to {args.report}")
    print(text if not args.report else
          f"{data.get('count', 0)} file(s) processed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
