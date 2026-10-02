"""Institutional library auto-login (Selenium + the real Chrome profile) and cookie cache."""

from __future__ import annotations

import datetime
import json
import os
import time
import warnings
from pathlib import Path
from typing import Optional

from _common import ScrapeError


class InstitutionalLibraryAuth:
    """Institutional library auto-login + session cookie management.

    Logs in using the real Chrome profile (User Data) and injects the
    resulting cookies into a requests.Session. Reuses the auto-fill password
    already saved in the browser, so no secrets.json credentials are needed.
    Automatically re-logs in when session expiry is detected.

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
            # The library menu bar shows "LOGOUT" (or the Korean equivalent)
            # when a session is active; "LOGIN" (or Korean) when not authenticated.
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

        user_data = _chrome_user_data_dir()
        service = _chromedriver_service()
        driver = _launch_chrome(webdriver, service, user_data)

        try:
            return self._login_and_collect_cookies(driver, By, WebDriverWait, EC)
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

    def _login_and_collect_cookies(self, driver, By, WebDriverWait, EC) -> dict:
        """Click the login button (auto-fill supplies the credentials) and return the cookies."""
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
        return {c["name"]: c["value"] for c in driver.get_cookies()}


def _chrome_user_data_dir() -> str:
    """The Chrome "User Data" directory whose profile holds the saved credentials."""
    import platform

    if platform.system() == "Windows":
        return os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data")
    return os.path.expanduser("~/.config/google-chrome")


def _chromedriver_service():
    """webdriver-manager's ChromeDriver service, or None to use the system ChromeDriver."""
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        from selenium.webdriver.chrome.service import Service as ChromeService
        return ChromeService(ChromeDriverManager().install())
    except ImportError:
        return None
    except Exception as exc:
        warnings.warn(
            f"webdriver-manager failed ({exc}); "
            "falling back to system ChromeDriver"
        )
        return None


def _launch_chrome(webdriver, service, user_data: str):
    """Start Chrome on the Default profile; fall back to ``Profile 1`` if it is locked."""

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
    return driver
