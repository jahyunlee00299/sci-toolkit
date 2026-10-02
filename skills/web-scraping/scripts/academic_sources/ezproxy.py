"""EZproxy: Netscape cookie loading and the proxied PDF downloader."""

from __future__ import annotations

import http.cookiejar
import os
import re
import warnings
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from _common import ScrapeError, UnsafeTargetError, validate_url

from .library_auth import InstitutionalLibraryAuth
from .pdf_identity import check_downloaded_pdf

# --------------------------------------------------------------------------
# EZproxy cookie utilities
# --------------------------------------------------------------------------

class CookieNotFoundError(Exception):
    """Raised when the EZproxy session-cookie file is missing."""


EZPROXY_COOKIE_GUIDANCE = """\
An institutional library session cookie is required for EZproxy downloads.

[Recommended] Auto-login method (--auto-login flag):
  1. Save your institutional library site credentials as auto-fill in Chrome
  2. Run with the --download --auto-login flags (no secrets.json needed)

[Legacy] Manual cookie file:
  1. Log in to the institutional library site in Chrome
  2. Use a browser extension (e.g. "Get cookies.txt LOCALLY") to save the
     EZproxy domain cookie in Netscape format to {cookie_file}
  3. Run with the --download --ezproxy flags
Then run it again."""


def load_netscape_cookies(cookie_file: str) -> "http.cookiejar.MozillaCookieJar":
    """Load a Netscape-format cookie file into a MozillaCookieJar.

    .. deprecated::
        Use ``InstitutionalLibraryAuth`` (``InstitutionalLibraryAuth``) with ``--auto-login`` instead.
        This function is retained for backward compatibility with
        the ``--ezproxy`` / ``--cookie-file`` workflow.

    Returns a populated MozillaCookieJar ready to be passed to a
    requests.Session or used directly.

    Raises CookieNotFoundError if the file does not exist.
    Raises http.cookiejar.LoadError if the file format is invalid.
    """
    path = Path(cookie_file)
    if not path.exists():
        raise CookieNotFoundError(
            EZPROXY_COOKIE_GUIDANCE.format(cookie_file=cookie_file)
        )
    jar = http.cookiejar.MozillaCookieJar(str(path))
    jar.load(ignore_discard=True, ignore_expires=True)
    return jar


# --------------------------------------------------------------------------
# EZproxy PDF Downloader
# --------------------------------------------------------------------------

_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

class EZproxyPdfDownloader:
    """Downloads subscription-journal PDFs via the institutional library's EZproxy.

    Institutional library N2 OpenLink proxy.
    Configure PROXY_BASE and LOGIN_URL in InstitutionalLibraryAuth (or subclass)
    to match your institution's EZproxy gateway.

    Two authentication modes:
      1. Auto-login (recommended): pass ``auth=InstitutionalLibraryAuth(...)``
         to use Selenium-based automatic login.  Cookies are refreshed
         automatically when the session expires.
      2. Legacy cookie file (deprecated): pass ``cookie_file`` pointing to a
         Netscape-format cookie file manually exported from the browser.
         Use the ``--ezproxy`` CLI flag for this mode.

    Supported subscription databases: Elsevier, Springer/Nature, Wiley, ACS, RSC,
                  Taylor & Francis, Oxford, Cambridge

    Publisher domain rewrite pattern:
      pubs.acs.org → pubs-acs-org-ssl.<ezproxy-host>
      Rule: replace each '.' in the domain with '-', then append '-ssl.<ezproxy-host>'
    """

    # Your institution's EZproxy link-resolver base. Set EZPROXY_BASE env var
    # (e.g. "https://ezproxy.your-institution.edu/link?url=") or subclass.
    #
    # The default below is a PLACEHOLDER host that does not exist. Until 260730
    # nothing checked it, so with EZPROXY_BASE unset this class happily assembled
    # requests against the placeholder and reported an ordinary lookup failure —
    # indistinguishable from "the paper is not available". ``_require_configured``
    # now refuses instead, which keeps both options open: set EZPROXY_BASE to
    # enable the path, leave it unset to keep EZproxy off (SKILL.md marks it
    # deprecated in favour of LibKey).
    PLACEHOLDER_PROXY_HOST = "ezproxy.your-institution.edu"
    PROXY_BASE = os.environ.get("EZPROXY_BASE", "https://ezproxy.your-institution.edu/link.n2s?url=")
    DEFAULT_COOKIE_FILE = os.path.expanduser("~/.claude/institution_cookies.txt")

    # Subscribed publisher domains that EZproxy can unlock
    SUBSCRIBED_DOMAINS = frozenset([
        "www.sciencedirect.com",      # Elsevier
        "linkinghub.elsevier.com",    # Elsevier redirect
        "link.springer.com",          # Springer
        "www.nature.com",             # Nature/Springer
        "onlinelibrary.wiley.com",    # Wiley
        "pubs.acs.org",               # ACS
        "pubs.rsc.org",               # RSC
        "www.tandfonline.com",        # Taylor & Francis
        "academic.oup.com",           # Oxford
        "www.cambridge.org",          # Cambridge
    ])

    def __init__(
        self,
        cookie_file: Optional[str] = None,
        auth: Optional["InstitutionalLibraryAuth"] = None,
    ) -> None:
        """Initialise the downloader.

        Parameters
        ----------
        cookie_file:
            Path to a Netscape-format cookie file (legacy mode).
            Ignored when ``auth`` is provided.
        auth:
            A ``InstitutionalLibraryAuth`` instance for automatic Selenium-based
            login (new mode).  When supplied, ``cookie_file`` is not used.
        """
        self._auth = auth
        self._cookie_file = cookie_file or self.DEFAULT_COOKIE_FILE
        self._jar: Optional[http.cookiejar.MozillaCookieJar] = None
        # requests.Session maintained when auto-login mode is active
        self._session: Optional["requests.Session"] = None

    def _ensure_cookies(self) -> http.cookiejar.MozillaCookieJar:
        """Load cookies lazily (legacy mode); raise CookieNotFoundError if absent."""
        if self._jar is None:
            self._jar = load_netscape_cookies(self._cookie_file)
        return self._jar

    def _get_cookie_dict(self) -> dict:
        """Return cookies as a plain dict, from either auth or cookie file."""
        if self._auth is not None:
            if self._session is None:
                self._session = self._auth.get_session()
            else:
                self._auth.refresh_if_expired(self._session)
            return dict(self._session.cookies)
        # Legacy mode
        jar = self._ensure_cookies()
        return {cookie.name: cookie.value for cookie in jar}

    def _require_configured(self) -> str:
        """Return the EZproxy host, or refuse if it is still the placeholder.

        Raises ScrapeError so the caller reports a configuration problem rather
        than a silent "PDF not found".
        """
        host = (urlparse(self.PROXY_BASE).hostname or "").lower()
        if not host or host == self.PLACEHOLDER_PROXY_HOST:
            raise ScrapeError(
                "EZproxy is not configured: PROXY_BASE is still the placeholder "
                f"({self.PLACEHOLDER_PROXY_HOST}). Set the EZPROXY_BASE "
                "environment variable to your institution's link-resolver base, "
                "or leave the EZproxy path unused (LibKey is the recommended "
                "route per SKILL.md)."
            )
        return host

    def _cookie_jar(self, host: str) -> "httpx.Cookies":
        """Return session cookies BOUND to the EZproxy host and its subdomains.

        Passing a bare mapping to ``httpx.Client(cookies=...)`` registers every
        cookie with an empty domain, and httpx then attaches it to *any* host it
        talks to — measured on httpx 0.28.1 (260730 audit). Combined with
        ``follow_redirects=True`` and a PDF link extracted from page HTML, an
        institutional session cookie could be sent to an unrelated server, which
        is both a credential leak and a library-access-policy violation.

        Binding to ".<ezproxy-host>" keeps the cookie working for the rewritten
        publisher hosts EZproxy generates (``pubs-acs-org-ssl.<ezproxy-host>``)
        while withholding it from everything else.
        """
        import httpx

        jar = httpx.Cookies()
        domain = host if host.startswith(".") else f".{host}"
        for name, value in self._get_cookie_dict().items():
            jar.set(name, value, domain=domain)
        return jar

    def _accept_pdf_url(self, url: Optional[str],
                        proxy_host: str) -> Optional[str]:
        """Return ``url`` only if it is a proxied or subscribed publisher host.

        ``_extract_pdf_link`` scrapes an href out of page HTML, so the value is
        chosen by whatever the proxy served. Without this check the caller would
        follow it with the institutional session cookie attached — the exact
        combination the audit flagged. ``SUBSCRIBED_DOMAINS`` was already
        declared for this purpose but nothing consulted it.
        """
        if not url:
            return None
        try:
            validate_url(url)
        except UnsafeTargetError as exc:
            warnings.warn(f"EZproxy: refusing extracted PDF link — {exc}")
            return None
        host = (urlparse(url).hostname or "").lower().rstrip(".")
        if host == proxy_host or host.endswith(f".{proxy_host}"):
            return url
        if host in self.SUBSCRIBED_DOMAINS:
            return url
        warnings.warn(
            f"EZproxy: extracted PDF link points at an unrecognized host "
            f"({host}); not following it with institutional cookies. "
            f"Add it to SUBSCRIBED_DOMAINS if it is genuinely subscribed."
        )
        return None

    def _build_proxy_url(self, doi: str) -> str:
        """Return the EZproxy entry URL for ``doi``."""
        return f"{self.PROXY_BASE}https://doi.org/{doi}"

    def _extract_pdf_link(self, html: str, base_url: str) -> Optional[str]:
        """Scan HTML for a direct PDF link.

        Looks for <a> href values that contain 'pdf' or 'download' and
        end with '.pdf' or contain 'application/pdf' hints in the URL.
        Returns the first plausible candidate or None.
        """
        from urllib.parse import urljoin, urlparse

        # Patterns ordered by specificity
        patterns = [
            # Standard .pdf link
            r'href=["\']([^"\']*\.pdf[^"\']*)["\']',
            # Elsevier / Wiley download links
            r'href=["\']([^"\']*(?:pdf|download)[^"\']*)["\']',
        ]
        for pat in patterns:
            for m in re.finditer(pat, html, re.IGNORECASE):
                href = m.group(1)
                # Skip fragments, javascript: etc.
                if href.startswith(("#", "javascript:", "mailto:")):
                    continue
                full = urljoin(base_url, href)
                parsed = urlparse(full)
                # Accept only http(s) links that look like PDF
                if parsed.scheme in ("http", "https") and (
                    full.lower().endswith(".pdf")
                    or "pdf" in parsed.path.lower()
                    or "download" in parsed.path.lower()
                ):
                    return full
        return None

    def get_pdf_url(self, doi: str, rate_limiter=None) -> Optional[str]:
        """Resolve DOI via EZproxy and return a direct PDF URL, or None.

        This performs the actual HTTP round-trip through the proxy.
        ``rate_limiter`` is an optional RateLimiter instance.

        Returns:
            str  — final PDF URL (may be a redirect destination)
            None — could not resolve to a PDF
        """
        try:
            import httpx
        except ImportError as exc:
            raise ScrapeError(
                "httpx is required for EZproxyPdfDownloader"
            ) from exc

        proxy_host = self._require_configured()

        try:
            cookies = self._cookie_jar(proxy_host)
        except CookieNotFoundError:
            raise
        except ScrapeError:
            raise
        except Exception as exc:
            warnings.warn(f"EZproxy cookie retrieval failed: {exc}")
            return None

        proxy_url = self._build_proxy_url(doi)

        headers = {
            "User-Agent": _BROWSER_USER_AGENT,
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "application/pdf,*/*;q=0.8"
            ),
        }

        if rate_limiter is not None:
            # EZproxy has no published rate limit; 3 s spacing (base 1 s + 2 s extra)
            # keeps batch throughput to ~20 DOIs/min — safe without being banned.
            rate_limiter.wait(proxy_url, extra_delay=2.0)

        try:
            with httpx.Client(
                follow_redirects=True,
                timeout=30.0,
                headers=headers,
                cookies=cookies,
            ) as client:
                return self._resolve_pdf_url(client, proxy_url, proxy_host)
        except Exception as exc:
            warnings.warn(f"EZproxy lookup failed for DOI '{doi}': {exc}")
            return None

    def _resolve_pdf_url(self, client, proxy_url: str,
                         proxy_host: str) -> Optional[str]:
        """GET the proxied DOI page and return an accepted PDF URL, if any."""
        response = client.get(proxy_url)
        response.raise_for_status()

        # Content-Type application/pdf → we already have the PDF URL
        ct = response.headers.get("content-type", "")
        if "application/pdf" in ct:
            return self._accept_pdf_url(str(response.url), proxy_host)

        # HTML page: scan for PDF download link
        if "text/html" in ct:
            pdf_link = self._extract_pdf_link(
                response.text, str(response.url)
            )
            accepted = self._accept_pdf_url(pdf_link, proxy_host)
            if accepted:
                return accepted

        return None

    def download(self, doi: str, dest: Path,
                 rate_limiter=None, expected: Optional[dict] = None) -> dict:
        """Download a PDF via EZproxy.

        Returns a status dict with keys:
          downloaded_path, download_source, download_status[, size_bytes]

        ``expected`` is the same identity record ``_try_download`` uses. Passing
        it is what turns the check below into a real comparison; without it only
        the magic bytes and PDF structure are verified.
        """
        try:
            import httpx
        except ImportError as exc:
            raise ScrapeError(
                "httpx is required for EZproxyPdfDownloader"
            ) from exc

        try:
            proxy_host = self._require_configured()
            cookies = self._cookie_jar(proxy_host)
        except CookieNotFoundError as exc:
            warnings.warn(str(exc))
            return {
                "downloaded_path": None,
                "download_source": "ezproxy",
                "download_status": f"cookie file not found: {self._cookie_file}",
            }
        except ScrapeError as exc:
            warnings.warn(str(exc))
            return {
                "downloaded_path": None,
                "download_source": "ezproxy",
                "download_status": f"EZproxy auth failed: {exc}",
            }

        pdf_url = self.get_pdf_url(doi, rate_limiter=rate_limiter)
        if not pdf_url:
            return {
                "downloaded_path": None,
                "download_source": "ezproxy",
                "download_status": "EZproxy: PDF URL not resolved",
            }

        if rate_limiter is not None:
            # Same 3 s spacing as get_pdf_url to protect the EZproxy server.
            rate_limiter.wait(pdf_url, extra_delay=2.0)

        try:
            size = self._stream_pdf(httpx, pdf_url, dest, cookies)
            if size < 1024:
                dest.unlink(missing_ok=True)
                return {
                    "downloaded_path": None,
                    "download_source": "ezproxy",
                    "download_status": (
                        f"EZproxy response too small ({size} B), likely not a PDF"
                    ),
                }

            # Sources 1-3 must clear verify_pdf_identity before they may report
            # "ok"; this path checked size alone (260730 audit — the same gate
            # applied asymmetrically). A publisher paywall or SSO page is
            # comfortably larger than 1 KB, so size proves nothing.
            return check_downloaded_pdf(dest, doi, expected, "ezproxy", size)
        except Exception as exc:
            warnings.warn(f"EZproxy download failed for '{doi}': {exc}")
            return {
                "downloaded_path": None,
                "download_source": "ezproxy",
                "download_status": f"EZproxy download failed: {exc}",
            }

    @staticmethod
    def _stream_pdf(httpx, pdf_url: str, dest: Path, cookies) -> int:
        """Stream ``pdf_url`` (with the bound cookie jar) into ``dest``; return its size."""
        headers = {"User-Agent": _BROWSER_USER_AGENT}
        dest.parent.mkdir(parents=True, exist_ok=True)
        with httpx.Client(
            follow_redirects=True,
            timeout=60.0,
            headers=headers,
            cookies=cookies,
        ) as client:
            with client.stream("GET", pdf_url) as response:
                response.raise_for_status()
                with open(dest, "wb") as fh:
                    for chunk in response.iter_bytes(65536):
                        fh.write(chunk)
        return dest.stat().st_size
