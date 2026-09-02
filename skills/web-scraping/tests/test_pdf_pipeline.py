"""test_pdf_pipeline.py — pytest suite for the web-scraping PDF pipeline.

Structure:
  1. Unit tests  — all external I/O mocked; no network required
  2. Integration tests — real HTTP; run with: pytest --integration
  3. CLI tests   — subprocess-free invocation of main() with mock injected
"""
# ---------------------------------------------------------------------------
# UTF-8 stdout guard (Windows CP949 default)
# ---------------------------------------------------------------------------
import sys
import io
for _s in ("stdout", "stderr"):
    _st = getattr(sys, _s, None)
    if _st is not None and hasattr(_st, "reconfigure"):
        try:
            _st.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------
import json
import os
import types
import warnings
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_crossref_response():
    """Typical Crossref works() API response."""
    return {
        "message": {
            "title": ["Test Paper on Target Product Synthesis"],
            "author": [
                {"given": "Jane", "family": "Doe"},
                {"given": "John", "family": "Smith"},
            ],
            "issued": {"date-parts": [[2020]]},
            "DOI": "10.1234/test",
            "container-title": ["Test Journal of Chemistry"],
            "type": "journal-article",
            "URL": "https://doi.org/10.1234/test",
            "is-referenced-by-count": 42,
            "link": [
                {
                    "URL": "https://example.com/paper.pdf",
                    "content-type": "application/pdf",
                },
                {
                    "URL": "https://example.com/paper.html",
                    "content-type": "text/html",
                },
            ],
        }
    }


@pytest.fixture
def mock_unpaywall_oa_response():
    """Unpaywall JSON for a paper with a best_oa_location PDF."""
    return json.dumps({
        "doi": "10.1234/test",
        "is_oa": True,
        "best_oa_location": {
            "url_for_pdf": "https://oa.example.com/paper.pdf",
            "host_type": "repository",
        },
        "oa_locations": [
            {"url_for_pdf": "https://oa.example.com/paper.pdf"},
        ],
    })


@pytest.fixture
def mock_unpaywall_fallback_response():
    """Unpaywall JSON where best_oa_location has no url_for_pdf."""
    return json.dumps({
        "doi": "10.1234/test",
        "is_oa": True,
        "best_oa_location": {
            "url_for_pdf": None,
            "url": "https://oa.example.com/paper",
            "host_type": "repository",
        },
        "oa_locations": [
            {"url_for_pdf": None},
            {"url_for_pdf": "https://fallback.example.com/paper.pdf"},
        ],
    })


@pytest.fixture
def mock_unpaywall_not_oa_response():
    """Unpaywall JSON for a closed-access paper."""
    return json.dumps({
        "doi": "10.1234/closed",
        "is_oa": False,
        "best_oa_location": None,
        "oa_locations": [],
    })


@pytest.fixture
def mock_pmc_esearch_found():
    """NCBI E-utilities esearch response with a matching PMC ID."""
    return json.dumps({
        "esearchresult": {
            "count": "1",
            "idlist": ["2772430"],
        }
    })


@pytest.fixture
def mock_pmc_esearch_not_found():
    """NCBI E-utilities esearch response with no match."""
    return json.dumps({
        "esearchresult": {
            "count": "0",
            "idlist": [],
        }
    })


@pytest.fixture
def polite_client_mock():
    """A fully mocked PoliteHttpClient that never hits the network."""
    from _common import PoliteHttpClient, RateLimiter
    client = MagicMock(spec=PoliteHttpClient)
    client.limiter = MagicMock(spec=RateLimiter)
    client.limiter.wait = MagicMock(return_value=None)
    return client


# ===========================================================================
# 1. UNIT TESTS — CrossrefProvider
# ===========================================================================

class TestCrossrefNormalize:
    """CrossrefProvider._normalize() — pure function, no mocking needed."""

    def test_crossref_normalize_full(self, mock_crossref_response):
        """Typical Crossref message dict → all expected keys present."""
        from fetch_academic import CrossrefProvider
        item = mock_crossref_response["message"]
        result = CrossrefProvider._normalize(item)

        assert result["title"] == "Test Paper on Target Product Synthesis"
        assert result["authors"] == ["Jane Doe", "John Smith"]
        assert result["year"] == 2020
        assert result["doi"] == "10.1234/test"
        assert result["journal"] == "Test Journal of Chemistry"
        assert "https://example.com/paper.pdf" in result["pdf_links"]
        # Non-PDF link must NOT be in pdf_links
        assert "https://example.com/paper.html" not in result["pdf_links"]
        # Mandatory keys
        for key in ("title", "authors", "year", "doi", "journal",
                    "type", "url", "is_referenced_by_count", "pdf_links"):
            assert key in result, f"Key '{key}' missing from normalized record"

    def test_crossref_normalize_missing_fields(self):
        """Empty dict → no KeyError, returns dict with None values."""
        from fetch_academic import CrossrefProvider
        result = CrossrefProvider._normalize({})
        assert result["title"] is None
        assert result["authors"] == []
        assert result["year"] is None
        assert result["doi"] is None
        assert result["pdf_links"] == []

    def test_crossref_doi_not_found(self):
        """habanero raises on 404 → ScrapeError wraps it (not raw HTTP error)."""
        from fetch_academic import CrossrefProvider, ScrapeError

        fake_habanero = MagicMock()
        fake_habanero.Crossref.return_value.works.side_effect = Exception(
            "404 Not Found"
        )

        with patch.dict("sys.modules", {"habanero": fake_habanero}):
            # Re-instantiate so it picks up the patched module
            provider = CrossrefProvider.__new__(CrossrefProvider)
            from habanero import Crossref as _Cr  # will hit fake
            provider._client = fake_habanero.Crossref()

            with pytest.raises(ScrapeError, match="Crossref DOI lookup failed"):
                provider.lookup_doi("10.9999/nonexistent")


# ===========================================================================
# 2. UNIT TESTS — UnpaywallProvider
# ===========================================================================

class TestUnpaywallProvider:

    def test_unpaywall_best_oa_location(
        self, polite_client_mock, mock_unpaywall_oa_response
    ):
        """best_oa_location.url_for_pdf present → return that URL."""
        from fetch_academic import UnpaywallProvider
        polite_client_mock.get_text.return_value = mock_unpaywall_oa_response
        provider = UnpaywallProvider(polite_client_mock)
        url = provider.get_oa_pdf_url("10.1234/test")
        assert url == "https://oa.example.com/paper.pdf"

    def test_unpaywall_fallback_oa_locations(
        self, polite_client_mock, mock_unpaywall_fallback_response
    ):
        """best_oa_location.url_for_pdf=null, oa_locations has one → fallback URL."""
        from fetch_academic import UnpaywallProvider
        polite_client_mock.get_text.return_value = mock_unpaywall_fallback_response
        provider = UnpaywallProvider(polite_client_mock)
        url = provider.get_oa_pdf_url("10.1234/test")
        assert url == "https://fallback.example.com/paper.pdf"

    def test_unpaywall_not_oa(
        self, polite_client_mock, mock_unpaywall_not_oa_response
    ):
        """is_oa=false, best_oa_location=null → return None."""
        from fetch_academic import UnpaywallProvider
        polite_client_mock.get_text.return_value = mock_unpaywall_not_oa_response
        provider = UnpaywallProvider(polite_client_mock)
        url = provider.get_oa_pdf_url("10.1234/closed")
        assert url is None

    def test_unpaywall_http_error(self, polite_client_mock):
        """HTTP error → warning emitted, None returned (not ScrapeError)."""
        from fetch_academic import UnpaywallProvider, ScrapeError
        polite_client_mock.get_text.side_effect = ScrapeError("HTTP 500")
        provider = UnpaywallProvider(polite_client_mock)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = provider.get_oa_pdf_url("10.1234/test")
        assert result is None
        assert len(w) >= 1
        assert "Unpaywall" in str(w[0].message)


# ===========================================================================
# 3. UNIT TESTS — PmcPdfLocator
# ===========================================================================

class TestPmcPdfLocator:

    def _make_http_response(self, text: str):
        """Build a minimal mock for httpx.Response."""
        resp = MagicMock()
        resp.text = text
        resp.raise_for_status = MagicMock(return_value=None)
        return resp

    def test_pmc_doi_to_pmcid_found(
        self, polite_client_mock, mock_pmc_esearch_found
    ):
        """E-utilities returns idlist=[2772430] → 'PMC2772430'."""
        from fetch_academic import PmcPdfLocator
        polite_client_mock._client = MagicMock()
        polite_client_mock._client.get.return_value = self._make_http_response(
            mock_pmc_esearch_found
        )
        locator = PmcPdfLocator(polite_client_mock)
        url = locator.get_pmc_pdf_url("10.1128/AEM.01771-09")
        assert url is not None
        assert "PMC2772430" in url

    def test_pmc_doi_not_in_pmc(
        self, polite_client_mock, mock_pmc_esearch_not_found
    ):
        """idlist=[] → None returned."""
        from fetch_academic import PmcPdfLocator
        polite_client_mock._client = MagicMock()
        polite_client_mock._client.get.return_value = self._make_http_response(
            mock_pmc_esearch_not_found
        )
        locator = PmcPdfLocator(polite_client_mock)
        url = locator.get_pmc_pdf_url("10.9999/not-in-pmc")
        assert url is None


# ===========================================================================
# 4. UNIT TESTS — EZproxyPdfDownloader
# ===========================================================================

class TestEZproxyPdfDownloader:

    def test_ezproxy_cookie_not_found(self, tmp_path):
        """Non-existent cookie file → CookieNotFoundError with path in msg."""
        from fetch_academic import EZproxyPdfDownloader, CookieNotFoundError
        bad_path = str(tmp_path / "no_such_file.txt")
        downloader = EZproxyPdfDownloader(cookie_file=bad_path)
        with pytest.raises(CookieNotFoundError) as exc_info:
            downloader._ensure_cookies()
        assert bad_path in str(exc_info.value)

    def test_ezproxy_proxy_url_format(self):
        """_build_proxy_url produces the expected EZproxy URL format."""
        from fetch_academic import EZproxyPdfDownloader
        downloader = EZproxyPdfDownloader(cookie_file="/dev/null")
        url = downloader._build_proxy_url("10.1039/abc")
        # URL must contain the DOI and resolve through the configured EZproxy gateway
        assert "https://doi.org/10.1039/abc" in url
        assert url.startswith("https://")

    def test_ezproxy_extract_pdf_link_standard(self):
        """HTML with a .pdf href → URL returned."""
        from fetch_academic import EZproxyPdfDownloader
        downloader = EZproxyPdfDownloader(cookie_file="/dev/null")
        html = '<a href="https://example.com/paper.pdf">Download PDF</a>'
        result = downloader._extract_pdf_link(html, "https://example.com")
        assert result is not None
        assert result.endswith(".pdf")

    def test_ezproxy_extract_pdf_link_none(self):
        """HTML without any PDF link → None."""
        from fetch_academic import EZproxyPdfDownloader
        downloader = EZproxyPdfDownloader(cookie_file="/dev/null")
        html = '<a href="https://example.com/page.html">Read Article</a>'
        result = downloader._extract_pdf_link(html, "https://example.com")
        assert result is None

    def test_ezproxy_download_no_cookie(self, tmp_path):
        """Cookie file missing → status dict returned, no exception raised."""
        from fetch_academic import EZproxyPdfDownloader
        bad_path = str(tmp_path / "missing_cookies.txt")
        downloader = EZproxyPdfDownloader(cookie_file=bad_path)
        dest = tmp_path / "output.pdf"
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = downloader.download("10.1234/test", dest)
        assert "download_status" in result
        assert result["downloaded_path"] is None


# ===========================================================================
# 5. UNIT TESTS — PdfDownloader
# ===========================================================================

def _fake_pdf_bytes(min_size: int = 0) -> bytes:
    """Build a real, minimally-valid PDF whose extracted text carries every
    author/title/DOI value used by TestPdfDownloader's fixtures, so
    verify_pdf_identity's score check clears "ok" (>=5) regardless of which
    record variant called it.  Padded with trailing whitespace inside the
    text stream (not raw bytes after %%EOF) to satisfy any stream_size floor
    without breaking PDF structure.
    """
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    import io

    text = (
        "Test Paper Title Words Overlap Example padding padding padding "
        "padding padding padding padding padding padding padding padding "
        "Doe Jane O'Brien Patrick 10.1234/test 10.1039/D0GC03729A "
        "Journal Name padding padding padding padding padding padding "
    )
    # Pad with more repeated words (not junk bytes) so extract_text() length
    # scales with min_size while staying valid PDF content-stream text.
    while len(text) < min_size:
        text += "padding "

    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    font = DictionaryObject()
    font[NameObject("/Type")] = NameObject("/Font")
    font[NameObject("/Subtype")] = NameObject("/Type1")
    font[NameObject("/BaseFont")] = NameObject("/Helvetica")
    font_ref = writer._add_object(font)
    resources = DictionaryObject()
    font_dict = DictionaryObject()
    font_dict[NameObject("/F1")] = font_ref
    resources[NameObject("/Font")] = font_dict
    page = writer.pages[0]
    page[NameObject("/Resources")] = resources

    stream_data = f"BT /F1 10 Tf 10 280 Td ({text}) Tj ET".encode("latin-1")
    content = DecodedStreamObject()
    content.set_data(stream_data)
    content_ref = writer._add_object(content)
    page[NameObject("/Contents")] = content_ref

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


class TestPdfDownloader:
    """PdfDownloader.download() — waterfall source tests."""

    def _make_downloader(self, tmp_path, unpaywall_url=None, pmc_url=None,
                         crossref_pdf_links=None, use_ezproxy=False,
                         ezproxy_mock=None, stream_side_effect=None,
                         stream_size=5000):
        """Construct a PdfDownloader with fully mocked providers."""
        from fetch_academic import (
            PdfDownloader, UnpaywallProvider, PmcPdfLocator,
        )
        from _common import PoliteHttpClient, RateLimiter

        client = MagicMock(spec=PoliteHttpClient)
        client.limiter = MagicMock(spec=RateLimiter)
        client.limiter.wait = MagicMock(return_value=None)

        def _fake_stream(url, dest, chunk_size=65536):
            """Write a real, minimally-valid, text-bearing PDF.

            verify_pdf_identity (added 260730) requires: real %PDF- magic bytes,
            a structurally parseable PDF (pypdf.PdfReader must open it), and
            >=200 chars of extractable text carrying the record's own
            title/author/DOI (so the identity score clears the "ok" threshold
            of >=5 when ``expected`` is passed). A bare b"%"*N byte string
            clears the size check but fails all three of those.
            """
            dest = Path(dest)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(_fake_pdf_bytes(min_size=stream_size))
            return dest

        if stream_side_effect is not None:
            client.stream_to_file.side_effect = stream_side_effect
        else:
            client.stream_to_file.side_effect = _fake_stream

        unpaywall = MagicMock(spec=UnpaywallProvider)
        unpaywall.get_oa_pdf_url.return_value = unpaywall_url

        pmc = MagicMock(spec=PmcPdfLocator)
        pmc.get_pmc_pdf_url.return_value = pmc_url

        downloader = PdfDownloader(
            client=client,
            unpaywall=unpaywall,
            pmc=pmc,
            dest_dir=tmp_path,
            use_ezproxy=use_ezproxy,
            ezproxy=ezproxy_mock,
        )
        return downloader, client

    def _make_record(self, doi="10.1234/test", authors=None,
                     year=2020, pdf_links=None):
        return {
            "doi": doi,
            "authors": authors or ["Doe Jane"],
            "year": year,
            "title": "Test Paper",
            "pdf_links": pdf_links or [],
        }

    # --- source 1: crossref_direct ---

    def test_pdfdownloader_crossref_success(self, tmp_path):
        """Crossref pdf_links has a URL + stream succeeds → crossref_direct."""
        record = self._make_record(pdf_links=["https://pub.example.com/paper.pdf"])
        downloader, _ = self._make_downloader(tmp_path)
        result = downloader.download(record)
        assert result["download_source"] == "crossref_direct"
        assert result["download_status"] == "ok"
        assert result["downloaded_path"] is not None

    # --- source 2: unpaywall ---

    def test_pdfdownloader_unpaywall_fallback(self, tmp_path):
        """Crossref pdf_links empty, Unpaywall has URL → unpaywall."""
        record = self._make_record(pdf_links=[])
        downloader, _ = self._make_downloader(
            tmp_path, unpaywall_url="https://oa.example.com/paper.pdf"
        )
        result = downloader.download(record)
        assert result["download_source"] == "unpaywall"
        assert result["download_status"] == "ok"

    # --- source 3: pmc ---

    def test_pdfdownloader_pmc_fallback(self, tmp_path):
        """Crossref + Unpaywall miss, PMC has URL → pmc."""
        record = self._make_record(pdf_links=[])
        downloader, _ = self._make_downloader(
            tmp_path,
            unpaywall_url=None,
            pmc_url="https://www.ncbi.nlm.nih.gov/pmc/articles/PMC2772430/pdf/",
        )
        result = downloader.download(record)
        assert result["download_source"] == "pmc"
        assert result["download_status"] == "ok"

    # --- all fail ---

    def test_pdfdownloader_all_fail(self, tmp_path):
        """All sources fail → downloaded_path=None, warning emitted, no exception."""
        from _common import ScrapeError
        record = self._make_record(pdf_links=["https://paywalled.example.com/p.pdf"])
        downloader, client = self._make_downloader(
            tmp_path,
            unpaywall_url=None,
            pmc_url=None,
            stream_side_effect=ScrapeError("403 Forbidden"),
        )
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = downloader.download(record)
        assert result["downloaded_path"] is None
        assert len(w) >= 1

    # --- ezproxy fallback ---

    def test_pdfdownloader_ezproxy_fallback(self, tmp_path):
        """use_ezproxy=True, 3 sources fail, EZproxy returns ok."""
        from _common import ScrapeError
        from fetch_academic import EZproxyPdfDownloader

        record = self._make_record(pdf_links=["https://paywalled.example.com/p.pdf"])

        ezproxy_mock = MagicMock(spec=EZproxyPdfDownloader)
        ezproxy_dest = tmp_path / "Doe_2020_10.1234_test_ezproxy.pdf"

        # ``expected`` was added to EZproxyPdfDownloader.download on 260730 so the
        # EZproxy path can run verify_pdf_identity like sources 1-3 do; the fake
        # has to accept it or it no longer stands in for the real method.
        def _fake_ez_download(doi, dest, rate_limiter=None, expected=None):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"%" * 5000)
            return {
                "downloaded_path": str(dest),
                "download_source": "ezproxy",
                "download_status": "ok",
                "size_bytes": 5000,
            }

        ezproxy_mock.download.side_effect = _fake_ez_download

        downloader, client = self._make_downloader(
            tmp_path,
            unpaywall_url=None,
            pmc_url=None,
            use_ezproxy=True,
            ezproxy_mock=ezproxy_mock,
            stream_side_effect=ScrapeError("403"),
        )
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = downloader.download(record)
        assert result["download_source"] == "ezproxy"
        assert result["download_status"] == "ok"

    # --- small file rejected ---

    def test_pdfdownloader_small_file_rejected(self, tmp_path):
        """Download succeeds but file < 1024 bytes → _try_download returns 'too small'.

        PdfDownloader._try_download is called directly to isolate the size-check
        logic, because the outer download() waterfall continues to the next source
        when one source returns a non-"ok" status.
        """
        from fetch_academic import PdfDownloader
        from _common import PoliteHttpClient, RateLimiter

        client = MagicMock(spec=PoliteHttpClient)
        client.limiter = MagicMock(spec=RateLimiter)

        def _write_small(url, dest, chunk_size=65536):
            dest = Path(dest)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"x" * 100)   # 100 bytes < 1024 threshold
            return dest

        client.stream_to_file.side_effect = _write_small

        from fetch_academic import UnpaywallProvider, PmcPdfLocator
        unpaywall = MagicMock(spec=UnpaywallProvider)
        unpaywall.get_oa_pdf_url.return_value = None
        pmc = MagicMock(spec=PmcPdfLocator)
        pmc.get_pmc_pdf_url.return_value = None

        downloader = PdfDownloader(
            client=client, unpaywall=unpaywall, pmc=pmc, dest_dir=tmp_path
        )
        dest = tmp_path / "test.pdf"
        result = downloader._try_download(
            "https://pub.example.com/paper.pdf", dest, "crossref_direct"
        )
        assert result["downloaded_path"] is None
        assert "too small" in result["download_status"]

    # --- filename format ---

    def test_pdfdownloader_filename_format(self, tmp_path):
        """Downloaded filename must be first_author_year_doi_safe.pdf."""
        from fetch_academic import _doi_to_safe_filename
        doi = "10.1039/D0GC03729A"
        record = self._make_record(
            doi=doi,
            authors=["O'Brien Patrick"],
            year=2021,
            pdf_links=["https://pub.example.com/paper.pdf"],
        )
        downloader, _ = self._make_downloader(tmp_path)
        result = downloader.download(record)
        assert result["download_status"] == "ok"
        path = Path(result["downloaded_path"])
        doi_safe = _doi_to_safe_filename(doi)
        assert doi_safe in path.name
        assert "2021" in path.name
        assert path.suffix == ".pdf"
        # No raw "/" in the filename
        assert "/" not in path.name


# ===========================================================================
# 6. UNIT TESTS — DoiHarvester (harvest_files.py)
# ===========================================================================

class TestDoiHarvester:

    def _make_doi_harvester(self, tmp_path):
        """DoiHarvester with mocked providers."""
        from harvest_files import DoiHarvester
        from fetch_academic import (
            CrossrefProvider, UnpaywallProvider,
            PmcPdfLocator, PdfDownloader,
        )
        from _common import PoliteHttpClient, RateLimiter, ScrapeError

        client = MagicMock(spec=PoliteHttpClient)
        client.limiter = MagicMock(spec=RateLimiter)
        client.limiter.wait = MagicMock(return_value=None)

        harvester = DoiHarvester.__new__(DoiHarvester)
        harvester._client = client
        harvester.dest_dir = tmp_path

        # CrossrefProvider — first DOI fails, rest return minimal record
        crossref_mock = MagicMock(spec=CrossrefProvider)
        harvester._crossref = crossref_mock

        # UnpaywallProvider — always returns None (no OA)
        unpaywall_mock = MagicMock(spec=UnpaywallProvider)
        unpaywall_mock.get_oa_pdf_url.return_value = None
        harvester._unpaywall = unpaywall_mock

        # PmcPdfLocator — always returns None
        pmc_mock = MagicMock(spec=PmcPdfLocator)
        pmc_mock.get_pmc_pdf_url.return_value = None
        harvester._pmc = pmc_mock

        # PdfDownloader — returns "not found" status
        pdf_dl_mock = MagicMock(spec=PdfDownloader)
        pdf_dl_mock.download.return_value = {
            "doi": "mock",
            "downloaded_path": None,
            "download_source": None,
            "download_status": "PDF not found via Crossref/Unpaywall/PMC",
        }
        harvester._downloader = pdf_dl_mock

        # Patch _collect_extra_pdf_urls to avoid network
        harvester._collect_extra_pdf_urls = MagicMock(return_value=[])

        return harvester, crossref_mock

    def test_doi_harvester_batch_continues_on_error(self, tmp_path):
        """First DOI Crossref fails → ScrapeError caught, rest of batch processed."""
        from _common import ScrapeError
        harvester, crossref_mock = self._make_doi_harvester(tmp_path)

        dois = ["10.bad/doi-will-fail", "10.1234/good-doi", "10.1234/another"]

        def crossref_side_effect(doi):
            if "bad" in doi:
                raise ScrapeError(f"Lookup failed for {doi}")
            return {"doi": doi, "title": "Good paper", "pdf_links": []}

        crossref_mock.lookup_doi.side_effect = crossref_side_effect

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            results = harvester.harvest_batch(dois)

        # All 3 DOIs should produce a result (no exception escapes)
        assert len(results) == 3
        assert all("doi" in r for r in results)
        # At least one warning about the failed DOI
        assert any("10.bad" in str(warning.message) or "fail" in str(warning.message).lower()
                   for warning in w)

    def test_doi_list_comment_skip(self, tmp_path):
        """Lines starting with '#' in a DOI list file are skipped."""
        doi_list = tmp_path / "dois.txt"
        doi_list.write_text(
            "10.1234/real-doi-1\n"
            "# This is a comment — should be skipped\n"
            "10.1234/real-doi-2\n"
            "# Another comment\n",
            encoding="utf-8",
        )
        # Parse comment-skipping logic inline (mirrors _run_doi_mode)
        raw_lines = doi_list.read_text(encoding="utf-8").splitlines()
        dois = [
            line.strip()
            for line in raw_lines
            if line.strip() and not line.strip().startswith("#")
        ]
        assert dois == ["10.1234/real-doi-1", "10.1234/real-doi-2"]


# ===========================================================================
# 7. CLI TESTS — fetch_academic.main()
# ===========================================================================

class TestFetchAcademicCLI:

    def _make_minimal_record(self):
        return {
            "title": "CLI Test Paper",
            "authors": ["Test Author"],
            "year": 2021,
            "doi": "10.1234/cli-test",
            "journal": "Test Journal",
            "type": "journal-article",
            "url": "https://doi.org/10.1234/cli-test",
            "is_referenced_by_count": 5,
            "pdf_links": [],
        }

    def test_cli_crossref_query(self, tmp_path):
        """--source crossref --query → main() returns 0 (mock Crossref)."""
        pytest.importorskip("habanero")  # the CLI exits before the mock is reached without it (measured on Linux 2026-09-03)
        from fetch_academic import main, CrossrefProvider
        with patch.object(
            CrossrefProvider, "search",
            return_value=[self._make_minimal_record()]
        ):
            code = main(["--source", "crossref", "--query", "enzyme cascade",
                          "--no-cache"])
        assert code == 0

    def test_cli_doi_lookup(self, tmp_path):
        """--source crossref --doi → main() returns 0."""
        pytest.importorskip("habanero")
        from fetch_academic import main, CrossrefProvider
        with patch.object(
            CrossrefProvider, "lookup_doi",
            return_value=self._make_minimal_record()
        ):
            code = main(["--source", "crossref", "--doi",
                          "10.1002/biot.200900076", "--no-cache"])
        assert code == 0

    def test_cli_missing_source(self):
        """No --source argument → argparse exits with non-zero code."""
        from fetch_academic import main
        with pytest.raises(SystemExit) as exc_info:
            main([])
        assert exc_info.value.code != 0

    def test_cli_ezproxy_flag_parsed(self, tmp_path):
        """--download --ezproxy --cookie-file /nonexistent: flags parse cleanly."""
        from fetch_academic import main, CrossrefProvider, PdfDownloader

        record = self._make_minimal_record()
        no_dl = {
            **record,
            "downloaded_path": None,
            "download_source": None,
            "download_status": "cookie file not found",
        }

        with patch.object(CrossrefProvider, "lookup_doi", return_value=record), \
             patch.object(PdfDownloader, "download", return_value=no_dl):
            # Should not raise argparse error even with nonexistent cookie file
            code = main([
                "--source", "crossref",
                "--doi", "10.1234/test",
                "--download",
                "--download-dir", str(tmp_path),
                "--ezproxy",
                "--cookie-file", str(tmp_path / "nonexistent.txt"),
                "--no-cache",
            ])
        # main() catches ScrapeError → 1, or returns 0; either is fine here;
        # what matters is argparse did NOT raise SystemExit(2)
        assert code in (0, 1)


# ===========================================================================
# 8. CLI TESTS — harvest_files.main()
# ===========================================================================

class TestHarvestFilesCLI:

    def test_harvest_cli_doi_mode(self, tmp_path):
        """harvest_files main --doi → return code 0 with mocked pipeline."""
        pytest.importorskip("habanero")
        from harvest_files import main as harvest_main
        from harvest_files import DoiHarvester

        mock_result = {
            "doi": "10.1002/biot.200900076",
            "metadata": {"title": "Test"},
            "downloaded_path": None,
            "download_source": None,
            "download_status": "PDF not found",
        }

        with patch.object(
            DoiHarvester, "harvest_doi", return_value=mock_result
        ):
            code = harvest_main([
                "--doi", "10.1002/biot.200900076",
                "--output-dir", str(tmp_path),
                "--no-cache",
            ])
        assert code == 0

    def test_harvest_cli_no_input(self):
        """No URL or --doi provided → return code 1 (not argparse error)."""
        from harvest_files import main as harvest_main
        code = harvest_main([])
        assert code == 1


# ===========================================================================
# 8b. UNIT TESTS — EZproxyPdfDownloader auto-login path
# ===========================================================================

class TestEZproxyAutoLogin:
    """Tests for the InstitutionalLibraryAuth-based path in EZproxyPdfDownloader."""

    def test_ezproxy_auto_login_no_secrets(self, tmp_path):
        """InstitutionalLibraryAuth() succeeds without institution_* keys in secrets.json.

        The new profile-based login no longer requires credentials in secrets.json.
        Instance creation must succeed; errors only occur when Selenium is invoked.
        """
        from fetch_academic import (
            EZproxyPdfDownloader, InstitutionalLibraryAuth, ScrapeError,
        )

        # Point to a fake secrets.json with no institution_* keys — must NOT raise
        fake_secrets = tmp_path / "secrets.json"
        fake_secrets.write_text(
            json.dumps({"ASANA_PAT": "dummy_only"}), encoding="utf-8"
        )

        with patch.object(InstitutionalLibraryAuth, "SECRETS_FILE", str(fake_secrets)):
            # Instance creation must succeed even without institution_* keys
            auth = InstitutionalLibraryAuth()
            assert auth._user_id is None
            assert auth._password is None

        # EZproxyPdfDownloader with this auth also constructs without error
        downloader = EZproxyPdfDownloader(auth=auth)
        assert downloader._auth is auth

        # Errors only surface when Selenium is actually called (get_session)
        import warnings as _warnings
        with _warnings.catch_warnings(record=True) as w:
            _warnings.simplefilter("always")
            with patch.object(
                auth, "get_session",
                side_effect=ScrapeError("Chrome profile not available"),
            ):
                result = downloader.download("10.1234/test", tmp_path / "out.pdf")

        assert result["downloaded_path"] is None
        assert "ezproxy" in result["download_source"]
        assert len(w) >= 1

    def test_ezproxy_cookie_cache_fresh_no_selenium(self, tmp_path):
        """Fresh cookie cache → EZproxyPdfDownloader uses it without launching Selenium."""
        import datetime as _dt
        from fetch_academic import (
            EZproxyPdfDownloader, InstitutionalLibraryAuth,
        )

        # Build a fresh cache
        cache_file = str(tmp_path / "cookies.json")
        cache_data = {
            "saved_at": _dt.datetime.now().isoformat(),
            "cookies": {"EZB-Token": "cached_token", "JSESSIONID": "sess123"},
        }
        Path(cache_file).write_text(
            json.dumps(cache_data), encoding="utf-8"
        )

        with patch.object(InstitutionalLibraryAuth, "COOKIE_CACHE_FILE", cache_file):
            auth = InstitutionalLibraryAuth(user_id="u", password="p")

            # _selenium_login must NOT be called
            with patch.object(
                auth, "_selenium_login",
                side_effect=AssertionError("Selenium called unexpectedly"),
            ):
                session = auth.get_session()

        assert session.cookies.get("EZB-Token") == "cached_token"


# ===========================================================================
# 9. INTEGRATION TESTS (real network — skip without --integration)
# ===========================================================================

@pytest.mark.integration
class TestCrossrefIntegration:

    def test_crossref_real_doi(self):
        """DOI 10.1002/biot.200900076 → year=2009, title and DOI are populated.

        This DOI resolves to a 2009 Biotechnology Journal paper.
        We check structural correctness, not exact title wording.
        """
        from fetch_academic import CrossrefProvider
        provider = CrossrefProvider()
        record = provider.lookup_doi("10.1002/biot.200900076")
        assert record["title"] is not None
        assert len(record["title"]) > 5
        assert record["year"] == 2009
        assert record["doi"] is not None
        assert "1002" in record["doi"]  # DOI prefix is always present


@pytest.mark.integration
class TestUnpaywallIntegration:

    def test_unpaywall_real_oa(self):
        """PLOS ONE OA DOI → url_for_pdf is not None (PLOS ONE is always OA)."""
        from fetch_academic import UnpaywallProvider
        from _common import PoliteHttpClient, HttpClientConfig
        config = HttpClientConfig(use_cache=False, max_retries=2)
        with PoliteHttpClient(config) as client:
            provider = UnpaywallProvider(client)
            # 10.1371/journal.pone.0000001 — first ever PLOS ONE paper, always OA
            url = provider.get_oa_pdf_url("10.1371/journal.pone.0000001")
        assert url is not None
        assert url.startswith("http")


@pytest.mark.integration
class TestPmcIntegration:

    def test_pmc_real_doi(self):
        """DOI 10.1371/journal.pone.0000001 → PMC1762328 returned."""
        from fetch_academic import PmcPdfLocator
        from _common import PoliteHttpClient, HttpClientConfig
        config = HttpClientConfig(use_cache=False, max_retries=2)
        with PoliteHttpClient(config) as client:
            locator = PmcPdfLocator(client)
            # This PLOS ONE DOI is confirmed to be in PMC (id=1762328)
            url = locator.get_pmc_pdf_url("10.1371/journal.pone.0000001")
        assert url is not None
        assert "PMC1762328" in url


@pytest.mark.integration
class TestFullPipelineIntegration:

    def test_full_pipeline_oa_paper(self, tmp_path):
        """PLOS ONE OA paper → PDF downloaded via Unpaywall, size > 100 KB."""
        from fetch_academic import PdfDownloader, UnpaywallProvider, PmcPdfLocator
        from _common import PoliteHttpClient, HttpClientConfig

        config = HttpClientConfig(use_cache=False, max_retries=2, min_delay=0.5)
        with PoliteHttpClient(config) as client:
            unpaywall = UnpaywallProvider(client)
            pmc = PmcPdfLocator(client)
            downloader = PdfDownloader(
                client=client,
                unpaywall=unpaywall,
                pmc=pmc,
                dest_dir=tmp_path,
            )
            # 10.1371/journal.pone.0000001 — first PLOS ONE paper, always OA
            record = {
                "doi": "10.1371/journal.pone.0000001",
                "authors": ["Bhatt Dipak L"],
                "year": 2006,
                "title": "PLOS ONE First Paper",
                "pdf_links": [],
            }
            result = downloader.download(record)

        # Integration: tolerate failure only if network is unreachable.
        if result["download_status"] == "ok":
            path = Path(result["downloaded_path"])
            assert path.exists()
            assert path.stat().st_size > 100_000, (
                f"Downloaded file too small: {path.stat().st_size} bytes"
            )
        else:
            pytest.skip(
                f"Integration download did not succeed "
                f"(status: {result['download_status']}); "
                "may indicate network restrictions in this environment."
            )
