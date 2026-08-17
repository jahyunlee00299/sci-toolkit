"""fetch_academic.py - retrieve scholarly metadata and full-text links.

Sources (all official APIs, never page scraping):
  - crossref : DOI lookup + keyword search via habanero (Crossref REST API)
  - arxiv    : preprint search + PDF links via the arxiv package
  - biorxiv  : bioRxiv / medRxiv metadata via their public REST API

Each source is wrapped by a small provider class with a uniform ``search``
method, so adding a source later (chemRxiv, OpenAlex, ...) means adding one
class without touching the CLI. This is the Open/Closed principle in action.

Note on overlap with existing skills: the user already has pubmed-database,
openalex-database and biopython (Bio.Entrez). This script intentionally
covers Crossref / arXiv / bioRxiv only and defers PubMed/OpenAlex to those
skills.

Download support (--download flag):
  Priority order: (1) Crossref pdf_links, (2) Unpaywall best OA PDF,
  (3) PubMed Central PDF, (4) institutional EZproxy (if --ezproxy or --auto-login).
  Failures are warnings only; batch continues.
  Unpaywall API: https://api.unpaywall.org/v2/{doi}?email={contact}

EZproxy support:
  Uses an institutional library's N2 OpenLink proxy (configure PROXY_BASE in EZproxyPdfDownloader).
  Two modes:
  --ezproxy      : legacy — requires Netscape cookie file (see DEFAULT_COOKIE_FILE)
  --auto-login   : new    — Selenium Chrome (real profile) auto-login using browser-saved
                            auto-fill credentials; no secrets.json keys required.
  Activate with --download --ezproxy or --download --auto-login.

Dual use:
  - CLI:    python fetch_academic.py --source crossref --query "enzyme cascade" -n 10
  - CLI:    python fetch_academic.py --source crossref --doi 10.1039/D0GC00000A
  - CLI:    python fetch_academic.py --source crossref --doi 10.1039/D0GC00000A --download
  - CLI:    python fetch_academic.py --source crossref --doi 10.1039/D0GC00000A --download --ezproxy
  - CLI:    python fetch_academic.py --source crossref --doi 10.1039/D0GC00000A --download --auto-login
  - import: from fetch_academic import CrossrefProvider, ArxivProvider, UnpaywallProvider
  - import: from fetch_academic import EZproxyPdfDownloader, InstitutionalLibraryAuth
"""

from __future__ import annotations

import argparse
import datetime
import http.cookiejar
import json
import re
import sys
import time
import warnings
from urllib.parse import urlparse
from pathlib import Path
from typing import Optional
import os

from _common import (
    DEFAULT_CONTACT,
    HttpClientConfig,
    Provenance,
    PoliteHttpClient,
    ScrapeError,
    UnsafeTargetError,
    add_common_cli_args,
    build_client_from_args,
    resolve_within,
    sanitize_filename,
    validate_url,
    write_json_output,
    ensure_utf8_stdout,
)


# --------------------------------------------------------------------------
# Crossref
# --------------------------------------------------------------------------

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


# --------------------------------------------------------------------------
# Unpaywall
# --------------------------------------------------------------------------

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


# --------------------------------------------------------------------------
# PubMed Central PDF helper
# --------------------------------------------------------------------------

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


# --------------------------------------------------------------------------
# PDF Downloader
# --------------------------------------------------------------------------

def _doi_to_safe_filename(doi: str) -> str:
    """Convert a DOI to a filesystem-safe string (replaces / and : with _)."""
    return re.sub(r"[/:\\]", "_", doi)


# --------------------------------------------------------------------------
# Downloaded-file identity verification
# --------------------------------------------------------------------------
# Real incident: a download for one DOI silently resolved to an unrelated
# paper (a decades-old humanities article from a different journal/publisher,
# hundreds of KB, PDF-shaped). The manifest recorded it as status=success.
#
# The only check at the time was "size > 1 KB", so the wrong file sailed
# through — it never even checked the magic bytes (%PDF-). "A file arrived"
# and "the requested paper arrived" are not the same claim. If this isn't
# caught at download time, catching it later means auditing every file by
# hand — so it's enforced here instead.

_PDF_STOPWORDS = {
    "the", "and", "for", "from", "with", "via", "using", "a", "an", "of", "in",
    "on", "to", "by", "its", "into", "at", "as", "is", "are", "be", "new", "novel",
    "study", "approach", "analysis", "effect", "effects", "role",
}


def _title_tokens(text: str) -> set:
    return {w for w in re.findall(r"[a-z]{4,}", (text or "").lower())
            if w not in _PDF_STOPWORDS}


def verify_pdf_identity(path: "Path", doi: str = "",
                        expected: Optional[dict] = None) -> dict:
    """받은 PDF가 *요청한 논문*인지 확인한다.

    단일 신호로 판정하지 않는다 — 연도나 저널만 우연히 맞아도 통과해 버리기 때문.
    본문 DOI(+3) · 제목토큰(+3/2/1) · 제1저자(+2) · 저널(+1) · 연도(+1) 를 합산해
    >=5 = ok, 3-4 = suspect, 그 미만 = mismatch.

    expected = {"title","first_author","journal","year"} (Crossref 레코드에서 구성).
    expected 가 없으면 매직바이트/구조 검사만 수행한다(약한 검증).

    반환: {"verdict","score","reasons"} — verdict ∈ ok/suspect/mismatch/not_pdf/no_text
    """
    reasons: list = []
    try:
        head = path.open("rb").read(5)
    except Exception as exc:
        return {"verdict": "not_pdf", "score": 0,
                "reasons": [f"열 수 없음: {type(exc).__name__}"]}
    if head != b"%PDF-":
        return {"verdict": "not_pdf", "score": 0,
                "reasons": [f"매직바이트가 %PDF- 가 아님 ({head!r}) — 오류/로그인 페이지 가능성"]}

    try:
        try:
            from pypdf import PdfReader
        except ImportError:                                     # pragma: no cover
            from PyPDF2 import PdfReader                          # type: ignore
        reader = PdfReader(str(path))
        n_pages = len(reader.pages)
        text = " ".join(
            " ".join((reader.pages[i].extract_text() or "").split())
            for i in range(min(2, n_pages))
        )
    except Exception as exc:
        return {"verdict": "not_pdf", "score": 0,
                "reasons": [f"PDF 파싱 실패: {type(exc).__name__} — 손상 파일"]}

    if len(text.strip()) < 200:
        # 스캔본일 수 있다. 자동 판정하지 말고 사람에게 넘긴다.
        return {"verdict": "no_text", "score": 0,
                "reasons": ["본문 텍스트 거의 없음(스캔본 추정) — 육안 확인 필요"]}

    if not expected:
        return {"verdict": "ok", "score": 0,
                "reasons": ["기대 메타데이터 없음 — 매직바이트/구조만 확인(약한 검증)"]}

    low = text.lower()
    score = 0

    if doi and doi.lower() in low:
        score += 3
        reasons.append("본문에 DOI 존재(+3)")
    elif doi:
        reasons.append("본문에 DOI 없음")

    exp_title = expected.get("title") or ""
    tt = _title_tokens(exp_title)
    if tt:
        overlap = len(tt & _title_tokens(text)) / len(tt)
        if overlap >= 0.6:
            score += 3
        elif overlap >= 0.35:
            score += 2
        elif overlap >= 0.2:
            score += 1
        reasons.append(f"제목 토큰 일치 {overlap:.0%}")

    fa = (expected.get("first_author") or "").lower()
    if len(fa) >= 3:
        if fa in low:
            score += 2
            reasons.append(f"제1저자 '{fa}' 확인(+2)")
        else:
            reasons.append(f"제1저자 '{fa}' 본문에 없음")

    jt = _title_tokens(expected.get("journal") or "")
    if jt and len(jt & _title_tokens(text)) / len(jt) >= 0.5:
        score += 1
        reasons.append("저널명 일치(+1)")

    yr = expected.get("year")
    if yr and str(yr) in text:
        score += 1
        reasons.append(f"연도 {yr} 확인(+1)")

    verdict = "ok" if score >= 5 else ("suspect" if score >= 3 else "mismatch")
    return {"verdict": verdict, "score": score, "reasons": reasons}


# --------------------------------------------------------------------------
# Institutional Library (EZproxy) auto-login
# --------------------------------------------------------------------------

class InstitutionalLibraryAuth:
    """기관 도서관 자동 로그인 + 세션 쿠키 관리.

    실제 Chrome 프로필(User Data)을 사용해 로그인하고, 쿠키를
    requests.Session에 주입한다. 브라우저에 저장된 자동완성 비밀번호를
    그대로 활용하므로 secrets.json 자격증명 불필요.
    세션 만료 감지 시 자동 재로그인.

    The obtained cookies are cached to COOKIE_CACHE_FILE as JSON.
    A fresh cache (< COOKIE_MAX_AGE_HOURS) is reused without re-launching
    the browser.
    """

    # Set these to your institution's library login / EZproxy endpoints, e.g.
    # via env vars LIBRARY_LOGIN_URL / LIBRARY_SESSION_URL, or subclass.
    LOGIN_URL = os.environ.get("LIBRARY_LOGIN_URL", "https://library.your-institution.edu/login/")
    SESSION_CHECK_URL = os.environ.get("LIBRARY_SESSION_URL", "https://library.your-institution.edu/")
    COOKIE_CACHE_FILE = os.path.expanduser("~/.claude/institution_cookies.json")
    COOKIE_MAX_AGE_HOURS = 6  # re-login after 6 hours
    SECRETS_FILE = os.path.expanduser("~/.secrets/secrets.json")

    def __init__(
        self,
        user_id: Optional[str] = None,
        password: Optional[str] = None,
    ) -> None:
        """Initialise auth manager.

        ``user_id`` / ``password`` are optional legacy parameters kept for
        backward compatibility but are no longer required.  Login relies on
        the saved auto-fill credentials in the real Chrome profile.
        """
        # Keep optional explicit credentials for backward compat / testing,
        # but do NOT load from secrets.json — not needed for profile-based login.
        self._user_id = user_id
        self._password = password

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_session(self) -> "requests.Session":
        """Return a requests.Session with valid institutional library cookies.

        Uses cached cookies when fresh; otherwise triggers Selenium login.
        Raises ScrapeError on login failure.
        """
        try:
            import requests
        except ImportError as exc:
            raise ScrapeError(
                "requests is required for InstitutionalLibraryAuth. "
                "Install: pip install requests"
            ) from exc

        cookies = self._load_cached_cookies()
        if cookies is None:
            cookies = self._selenium_login()
            self._save_cookie_cache(cookies)

        session = requests.Session()
        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        })
        for name, value in cookies.items():
            session.cookies.set(name, value)
        return session

    def is_session_valid(self, session: "requests.Session") -> bool:
        """Check whether ``session`` still has an active institutional library login.

        Accesses SESSION_CHECK_URL and looks for the "LOGOUT" text that
        the library page shows when the user IS logged in.
        Returns False on any network error (conservative: will re-login).
        """
        try:
            resp = session.get(self.SESSION_CHECK_URL, timeout=15)
            # The library menu bar shows "LOGOUT" (or Korean equivalent) when
            # a session is active; "LOGIN" (or Korean) when not authenticated.
            text = resp.text
            return "LOGOUT" in text or "로그아웃" in text
        except Exception as exc:
            warnings.warn(f"Session validity check failed: {exc}")
            return False

    def refresh_if_expired(self, session: "requests.Session") -> "requests.Session":
        """Re-login and update ``session`` cookies if the session has expired.

        Returns the (possibly refreshed) session for chaining.
        """
        if not self.is_session_valid(session):
            warnings.warn(
                "InstitutionalLibraryAuth: session expired, re-logging in via Selenium"
            )
            cookies = self._selenium_login()
            self._save_cookie_cache(cookies)
            # Clear old cookies and inject new ones
            session.cookies.clear()
            for name, value in cookies.items():
                session.cookies.set(name, value)
        return session

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_cached_cookies(self) -> Optional[dict]:
        """Return cached cookies if the file is fresh, else None."""
        cache_path = Path(self.COOKIE_CACHE_FILE)
        if not cache_path.exists():
            return None
        try:
            with open(cache_path, encoding="utf-8") as fh:
                data = json.load(fh)
            saved_at_str = data.get("saved_at")
            if not saved_at_str:
                return None
            saved_at = datetime.datetime.fromisoformat(saved_at_str)
            age_hours = (
                datetime.datetime.now() - saved_at
            ).total_seconds() / 3600
            if age_hours >= self.COOKIE_MAX_AGE_HOURS:
                return None
            cookies = data.get("cookies")
            if not isinstance(cookies, dict):
                return None
            return cookies
        except Exception as exc:
            warnings.warn(f"Cookie cache read failed: {exc}; will re-login")
            return None

    def _save_cookie_cache(self, cookies: dict) -> None:
        """Write cookies + timestamp to COOKIE_CACHE_FILE."""
        cache_path = Path(self.COOKIE_CACHE_FILE)
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as fh:
                json.dump(
                    {
                        "saved_at": datetime.datetime.now().isoformat(),
                        "cookies": cookies,
                    },
                    fh,
                    indent=2,
                    ensure_ascii=False,
                )
        except Exception as exc:
            warnings.warn(f"Failed to save cookie cache: {exc}")

    def _selenium_login(self) -> dict:
        """Launch Chrome with real user profile, click login, return session cookies.

        Uses the browser's saved auto-fill credentials — no secrets.json needed.
        The window is positioned off-screen to minimise distraction.

        Raises ScrapeError on login failure or if Selenium is not installed.
        Falls back to ``Profile 1`` if ``Default`` profile is locked by another
        Chrome instance.
        """
        try:
            from selenium import webdriver
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
        except ImportError as exc:
            raise ScrapeError(
                "selenium is required for --auto-login. "
                "Install: pip install selenium webdriver-manager"
            ) from exc

        import platform

        # Resolve Chrome User Data directory
        if platform.system() == "Windows":
            user_data = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data")
        else:
            user_data = os.path.expanduser("~/.config/google-chrome")

        # Attempt webdriver-manager first, fall back to system ChromeDriver
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            from selenium.webdriver.chrome.service import Service as ChromeService
            service = ChromeService(ChromeDriverManager().install())
        except ImportError:
            service = None  # type: ignore[assignment]
        except Exception as exc:
            warnings.warn(
                f"webdriver-manager failed ({exc}); "
                "falling back to system ChromeDriver"
            )
            service = None  # type: ignore[assignment]

        def _make_options(profile_dir: str) -> "webdriver.ChromeOptions":
            opts = webdriver.ChromeOptions()
            # Use real Chrome profile so saved passwords / auto-fill work
            opts.add_argument(f"--user-data-dir={user_data}")
            opts.add_argument(f"--profile-directory={profile_dir}")
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            # Position off-screen to avoid disturbing the user
            opts.add_argument("--window-position=-2000,0")
            opts.add_argument("--window-size=800,600")
            return opts

        def _try_launch(profile_dir: str):
            opts = _make_options(profile_dir)
            if service is not None:
                return webdriver.Chrome(service=service, options=opts)
            return webdriver.Chrome(options=opts)

        # Try Default profile first; fall back to Profile 1 if it is locked.
        driver = None
        for profile in ("Default", "Profile 1"):
            try:
                driver = _try_launch(profile)
                break
            except Exception as exc:
                err_str = str(exc).lower()
                if "user data directory is already in use" in err_str or profile == "Profile 1":
                    if profile == "Default":
                        warnings.warn(
                            f"Chrome Default profile locked ({exc}); "
                            "retrying with 'Profile 1'"
                        )
                        continue
                    raise ScrapeError(
                        f"Failed to launch Chrome with profile '{profile}': {exc}\n"
                        "Make sure Google Chrome and ChromeDriver are installed.\n"
                        "Install ChromeDriver manager: pip install webdriver-manager"
                    ) from exc
                raise ScrapeError(
                    f"Failed to launch Chrome: {exc}\n"
                    "Make sure Google Chrome and ChromeDriver are installed.\n"
                    "Install ChromeDriver manager: pip install webdriver-manager"
                ) from exc

        if driver is None:
            raise ScrapeError("Could not launch Chrome with any available profile.")

        try:
            driver.get(self.LOGIN_URL)
            wait = WebDriverWait(driver, 10)

            # Wait for the login button to appear, then give auto-fill time to
            # populate the credential fields before clicking.
            login_btn = wait.until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR,
                     "input[type='submit'], button[type='submit'], "
                     ".btn-login, input.btn")
                )
            )
            # Brief pause to let the browser populate auto-fill fields
            time.sleep(1)
            login_btn.click()

            # Wait for redirect to library home (host derived from SESSION_CHECK_URL)
            from urllib.parse import urlparse as _urlparse
            _lib_host = _urlparse(self.SESSION_CHECK_URL).netloc or "library"
            wait.until(EC.url_contains(_lib_host))
            # Verify login succeeded by looking for logout indicator
            wait.until(
                lambda d: "logout" in d.page_source.lower()
                or "로그아웃" in d.page_source
            )

            # Extract cookies as plain dict
            cookies = {
                c["name"]: c["value"]
                for c in driver.get_cookies()
            }
            return cookies

        except ScrapeError:
            raise
        except Exception as exc:
            raise ScrapeError(
                f"Institutional library login failed: {exc}\n"
                "Ensure Chrome has saved credentials for the library login page "
                "so the auto-fill can populate the login form."
            ) from exc
        finally:
            try:
                driver.quit()
            except Exception:
                pass


# --------------------------------------------------------------------------
# EZproxy cookie utilities
# --------------------------------------------------------------------------

class CookieNotFoundError(Exception):
    """Raised when the EZproxy session-cookie file is missing."""


EZPROXY_COOKIE_GUIDANCE = """\
EZproxy 다운로드를 위해 기관 도서관 세션 쿠키가 필요합니다.

[권장] 자동 로그인 방법 (--auto-login 플래그):
  1. Chrome에 기관 도서관 사이트 자격증명을 자동완성으로 저장
  2. --download --auto-login 플래그로 실행 (secrets.json 불필요)

[구 방식] 수동 쿠키 파일:
  1. Chrome에서 기관 도서관 사이트 로그인
  2. 브라우저 확장 프로그램(예: "Get cookies.txt LOCALLY")으로
     EZproxy 도메인 쿠키를 Netscape 형식으로 {cookie_file} 에 저장
  3. --download --ezproxy 플래그로 실행
그 후 다시 실행하세요."""


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

class EZproxyPdfDownloader:
    """기관 도서관 EZproxy를 통한 구독 저널 PDF 다운로드.

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

    지원 구독 DB: Elsevier, Springer/Nature, Wiley, ACS, RSC,
                  Taylor & Francis, Oxford, Cambridge

    출판사 도메인 변환 패턴:
      pubs.acs.org → pubs-acs-org-ssl.<ezproxy-host>
      규칙: 도메인의 '.' → '-', 마지막에 '-ssl.<ezproxy-host>' 추가
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
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
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

        except Exception as exc:
            warnings.warn(f"EZproxy lookup failed for DOI '{doi}': {exc}")
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

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        }

        if rate_limiter is not None:
            # Same 3 s spacing as get_pdf_url to protect the EZproxy server.
            rate_limiter.wait(pdf_url, extra_delay=2.0)

        try:
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

            size = dest.stat().st_size
            if size < 1024:
                dest.unlink(missing_ok=True)
                return {
                    "downloaded_path": None,
                    "download_source": "ezproxy",
                    "download_status": (
                        f"EZproxy response too small ({size} B), likely not a PDF"
                    ),
                }

            # Sources 1-3 must clear verify_pdf_identity in _try_download before
            # they may report "ok"; this path checked size alone (260730 audit —
            # the same gate applied asymmetrically). A publisher paywall or SSO
            # page is comfortably larger than 1 KB, so size proves nothing.
            ident = verify_pdf_identity(dest, doi=doi, expected=expected)
            if ident["verdict"] in ("mismatch", "not_pdf"):
                quarantine = dest.with_suffix(dest.suffix + ".REJECTED")
                dest.replace(quarantine)   # 격리, 삭제 아님 — 진단 가능해야 한다
                return {
                    "downloaded_path": None,
                    "download_source": "ezproxy",
                    "download_status": (
                        f"identity {ident['verdict']} (score={ident['score']}): "
                        + "; ".join(ident["reasons"][:3])
                        + f" -> 격리: {quarantine.name}"
                    ),
                    "identity": ident,
                }
            return {
                "downloaded_path": str(dest),
                "download_source": "ezproxy",
                "download_status": "ok" if ident["verdict"] == "ok"
                                   else f"ok (identity {ident['verdict']}, score={ident['score']})",
                "size_bytes": size,
                "identity": ident,
            }
        except Exception as exc:
            warnings.warn(f"EZproxy download failed for '{doi}': {exc}")
            return {
                "downloaded_path": None,
                "download_source": "ezproxy",
                "download_status": f"EZproxy download failed: {exc}",
            }


# --------------------------------------------------------------------------
# LibKey Nomad provider (Chrome MCP fallback)
# --------------------------------------------------------------------------

class LibKeyNomadProvider:
    """기관 도서관 LibKey Nomad 확장 경유 PDF URL 추출.

    LibKey Nomad는 PubMed/DOI 페이지에서 기관 구독 저널의 PDF 직접 링크를
    자동으로 삽입한다. Chrome MCP를 통해 해당 버튼의 href를 추출한다.

    동적 JS·EZproxy 인증이 필요할 때만 Chrome MCP fallback 사용.
    이 클래스는 EZproxy Selenium 보다 가볍고 안정적이므로 source 3.5에 위치.

    요구사항:
      - Chrome에 LibKey Nomad 확장 설치 (chrome-extension://dihbgbndebgnbjfmelmegjepbnkhlgni/)
      - Claude Code가 Chrome MCP 연결 상태 (mcp__claude-in-chrome__* 도구 활성)
    """

    PUBMED_BASE = "https://pubmed.ncbi.nlm.nih.gov"
    DOI_BASE = "https://doi.org"

    def __init__(self) -> None:
        self._chrome_mcp_available = self._check_chrome_mcp()

    @staticmethod
    def _check_chrome_mcp() -> bool:
        """Claude Code 세션에 Chrome MCP가 연결되어 있는지 확인."""
        # 실제 MCP 연결 여부는 런타임에 결정되므로 항상 True 반환
        # (MCP 미연결 시 get_pdf_url에서 None 반환)
        return True

    def get_pdf_url(self, doi: str) -> Optional[str]:
        """DOI에 대해 LibKey Nomad가 삽입한 PDF 버튼 URL을 추출.

        PubMed 페이지를 Chrome MCP로 열고 LibKey "Download PDF" 버튼 href를 반환.
        LibKey 버튼이 없거나 Chrome MCP 미연결 시 None 반환.

        이 메서드는 Claude Code 세션 내 MCP 도구 호출로만 동작하므로,
        단독 CLI 실행에서는 항상 None을 반환한다 (graceful degradation).
        """
        # CLI/스크립트 단독 실행 환경에서는 Chrome MCP 불가 → skip
        # Claude Code 세션 내에서는 SKILL.md 지침대로 Claude가 직접 MCP 호출
        return None

    def is_available(self) -> bool:
        """Chrome MCP 연결 여부 (Claude Code 세션 내에서만 True)."""
        return self._chrome_mcp_available


class PdfDownloader:
    """Downloads a PDF for a metadata record using up to five fallback sources.

    Priority:
      1. Crossref ``pdf_links`` (publisher CDN, may be paywalled)
      2. Unpaywall best OA PDF
      3. PubMed Central (PMC) PDF
      3.5 LibKey Nomad (Chrome MCP; 기관 구독 저널, EZproxy보다 가벼움)
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
        filename = sanitize_filename(
            f"{first_author}_{year}_{doi_safe}.pdf", fallback="paper.pdf"
        )

        dest = resolve_within(self.dest_dir, filename, fallback="paper.pdf")

        # 받은 파일이 '요청한 논문'인지 대조할 기준. 이미 record 안에 다 있다.
        expected = {
            "title": record.get("title") or "",
            "first_author": first_author if first_author != "unknown" else "",
            "journal": record.get("journal") or "",
            "year": year if year != "unknownyear" else None,
        }

        # --- source 1: Crossref pdf_links ---
        for pdf_url in (record.get("pdf_links") or []):
            result = self._try_download(pdf_url, dest, "crossref_direct",
                                        doi=doi, expected=expected)
            if result["download_status"].startswith("ok"):
                return {**record, **result}

        # --- source 2: Unpaywall ---
        if doi:
            oa_url = self._unpaywall.get_oa_pdf_url(doi)
            if oa_url:
                result = self._try_download(oa_url, dest, "unpaywall", doi=doi, expected=expected)
                if result["download_status"].startswith("ok"):
                    return {**record, **result}

        # --- source 3: PMC ---
        if doi:
            pmc_url = self._pmc.get_pmc_pdf_url(doi)
            if pmc_url:
                result = self._try_download(pmc_url, dest, "pmc", doi=doi, expected=expected)
                if result["download_status"].startswith("ok"):
                    return {**record, **result}

        # --- source 3.5: LibKey Nomad (Chrome MCP, institutional subscription) ---
        # Claude Code 세션 내에서만 동작; CLI 단독 실행 시 자동 skip
        if doi and self._use_libkey and self._libkey is not None:
            libkey_url = self._libkey.get_pdf_url(doi)
            if libkey_url:
                libkey_filename = sanitize_filename(
                    f"{first_author}_{year}_{doi_safe}_libkey.pdf",
                    fallback="paper_libkey.pdf")
                libkey_dest = resolve_within(self.dest_dir, libkey_filename,
                                             fallback="paper_libkey.pdf")
                result = self._try_download(libkey_url, libkey_dest, "libkey_nomad", doi=doi, expected=expected)
                if result["download_status"].startswith("ok"):
                    return {**record, **result}

        # --- source 4: EZproxy (institutional, optional) ---
        if doi and self._use_ezproxy and self._ezproxy is not None:
            ezproxy_filename = sanitize_filename(
                f"{first_author}_{year}_{doi_safe}_ezproxy.pdf",
                fallback="paper_ezproxy.pdf")
            ezproxy_dest = resolve_within(self.dest_dir, ezproxy_filename,
                                          fallback="paper_ezproxy.pdf")
            result = self._ezproxy.download(
                doi, ezproxy_dest,
                rate_limiter=self._client.limiter,
                expected=expected,          # 정체 검증 기준을 넘겨야 관문이 실효한다
            )
            if result["download_status"].startswith("ok"):
                return {**record, **result}

        # All sources exhausted
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
            # 크기만으로는 부족하다 — 691 KB짜리 '남의 논문'이 통과한 전례가 있다.
            ident = verify_pdf_identity(dest, doi=doi, expected=expected)
            if ident["verdict"] in ("mismatch", "not_pdf"):
                quarantine = dest.with_suffix(dest.suffix + ".REJECTED")
                dest.replace(quarantine)      # 지우지 않고 격리 — 진단 가능해야 한다
                return {
                    "downloaded_path": None,
                    "download_source": source,
                    "download_status": (
                        f"identity {ident['verdict']} (score={ident['score']}): "
                        + "; ".join(ident["reasons"][:3])
                        + f" -> 격리: {quarantine.name}"
                    ),
                    "identity": ident,
                }
            return {
                "downloaded_path": str(dest),
                "download_source": source,
                "download_status": "ok" if ident["verdict"] == "ok"
                                   else f"ok (identity {ident['verdict']}, score={ident['score']})",
                "size_bytes": size,
                "identity": ident,
            }
        except Exception as exc:
            warnings.warn(f"Download failed from {source} ({url}): {exc}")
            return {
                "downloaded_path": None,
                "download_source": source,
                "download_status": f"download failed: {exc}",
            }


# --------------------------------------------------------------------------
# arXiv
# --------------------------------------------------------------------------

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


# --------------------------------------------------------------------------
# bioRxiv / medRxiv
# --------------------------------------------------------------------------

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


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Retrieve scholarly metadata + full-text links "
                    "from Crossref / arXiv / bioRxiv.",
    )
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
    # PDF download options
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


def main(argv: Optional[list[str]] = None) -> int:
    ensure_utf8_stdout()
    args = _build_parser().parse_args(argv)
    try:
        if args.source == "crossref":
            # Crossref itself doesn't need the HTTP client, but --download does.
            if getattr(args, "download", False):
                with build_client_from_args(args) as client:
                    data, method = _run_crossref(args, client)
            else:
                data, method = _run_crossref(args)
            source_url = "https://api.crossref.org/works"
        elif args.source == "arxiv":
            data, method = _run_arxiv(args)
            source_url = "http://export.arxiv.org/api/query"
        else:  # biorxiv
            with build_client_from_args(args) as client:
                data, method = _run_biorxiv(args, client)
            source_url = BiorxivProvider.API_ROOT
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


if __name__ == "__main__":
    raise SystemExit(main())
