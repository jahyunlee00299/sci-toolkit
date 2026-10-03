"""Characterization snapshots for scripts/fetch_academic.py (refactor batch 3).

`fetch_academic.py` (1638 lines) was split into the `academic_sources` package, one
module per source/backend. This module drives every provider, the identity gate,
the downloaders and the CLI against local fakes (fake habanero / arxiv / selenium /
requests modules, an httpx MockTransport, a scripted PoliteHttpClient; DNS is
disabled) and dumps what they return, warn and raise. test_academic_characterization
compares it with tests/golden/fetch_academic.json, which was produced from the
unsplit script. Nothing here touches the network or the real browser profile.
"""
from __future__ import annotations

import contextlib
import datetime
import inspect
import io
import json
import os
import re
import socket
import sys
import types
import warnings
from pathlib import Path

HERE = Path(__file__).resolve().parent
GOLDEN = HERE / "golden"
SCRIPTS = HERE.parent / "scripts"
for _p in (SCRIPTS, HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import fetch_academic as fa  # noqa: E402
from _common import PoliteHttpClient, RateLimiter, ScrapeError  # noqa: E402

BS2 = chr(92) * 2          # a JSON-escaped backslash
# httpx appends this documentation hint to HTTPStatusError messages only in some versions
HTTPX_HINT = re.compile(re.escape(chr(92)) + "nFor more information check: [^" + chr(34) + "]*?/Status/[0-9]+")
# the exception class named in "PDF parsing failed: <Class>" differs between pypdf versions
PARSE_FAIL = re.compile(r"PDF parsing failed: [A-Za-z]+")
SIZE = re.compile(r'"size_bytes": [0-9]+')
TS = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:\+00:00|Z)?")
# argparse's "invalid choice" message lists the choices as repr() ('a', 'b') in older
# CPython 3.12 patch releases and bare (a, b) in newer ones; only the quoting differs
CHOICES = re.compile(r"\(choose from ([^)]*)\)")


def _jsonable(obj):
    return json.loads(json.dumps(obj, sort_keys=True, default=str, ensure_ascii=False))


def call(fn, *args, _trunc: int | None = None, **kwargs) -> dict:
    """Run fn and record result / raised error / emitted warnings.

    `_trunc` cuts messages that embed OS- or library-version-specific text.
    """
    out: dict = {}
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            out["result"] = _jsonable(fn(*args, **kwargs))
        except BaseException as exc:  # noqa: BLE001 - the type and message are the snapshot
            out["raised"] = [type(exc).__name__, str(exc)[:_trunc]]
    # ResourceWarning = GC-timing noise (verify_pdf_identity leaves a file handle to the collector)
    out["warnings"] = [f"{w.category.__name__}: {w.message}"[:_trunc] for w in caught
                       if not issubclass(w.category, ResourceWarning)]
    return out


def norm(obj, tmp: Path | None = None):
    """Make paths and timestamps stable."""
    text = json.dumps(obj, sort_keys=True, default=str, ensure_ascii=False)
    if tmp is not None:
        raw = str(tmp)
        for variant in (raw, raw.replace("\\", "\\\\"), tmp.as_posix()):
            text = text.replace(variant, "<TMP>")
    # Match the home directory with ANY run of separators between its parts: repr() inside
    # json.dumps quadruples Windows backslashes, which a fixed list of variants missed and
    # leaked the local username into the golden file.
    # The root separator of a POSIX home ("/home/runner") belongs to the home path too:
    # leaving it out turned "/home/runner/.claude" into "/<HOME>/.claude" on Linux while a
    # Windows home (drive letter first, no leading separator) gave "<HOME>/.claude"
    # (measured on the Linux CI runner, 2026-10-04).
    home = Path.home()
    parts = [re.escape(p) for p in home.parts if p not in ("/", "\\")]
    parts[0] = parts[0].rstrip("\\\\/") if parts else parts
    root = r"[\\/]+" if home.anchor in ("/", "\\") else ""
    text = re.sub(root + r"[\\/]*".join(parts) if parts else r"(?!)", "<HOME>", text)
    text = CHOICES.sub(lambda m: "(choose from " + m.group(1).replace("'", "") + ")", text)
    text = TS.sub("<TS>", text)
    text = text.replace(BS2, "/")
    text = HTTPX_HINT.sub("", text)
    text = PARSE_FAIL.sub("PDF parsing failed: <E>", text)
    text = SIZE.sub('"size_bytes": "<N>"', text)
    return json.loads(text)


# --------------------------------------------------------------------------
# PDFs and fake clients
# --------------------------------------------------------------------------
def pdf_bytes(text: str) -> bytes:
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
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
    stream = DecodedStreamObject()
    import textwrap
    lines = []
    y = 280
    for chunk in textwrap.wrap(text.replace("(", " ").replace(")", " "), 60, break_long_words=False):
        lines.append(f"BT /F1 6 Tf 5 {y} Td ({chunk}) Tj ET")
        y -= 8
    stream.set_data("\n".join(lines).encode("latin-1", errors="replace"))
    page = writer.pages[0]
    page[NameObject("/Resources")] = resources
    page[NameObject("/Contents")] = writer._add_object(stream)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


PAD = " padding" * 40
GOOD_TEXT = ("Target Product Synthesis Enzymatic Cascades Journal of Chemistry Catalysis 2020 "
             "Jane Doe 10.1234/test" + PAD)
SUSPECT_TEXT = "An unrelated report on weather patterns by Doe published in 2020" + PAD
MISMATCH_TEXT = "Medieval manuscripts and their binding practices in northern monasteries" + PAD
SHORT_TEXT = "tiny"
# exact score boundaries of verify_pdf_identity: author 2 + journal 1 + year 1 = 4 (suspect);
# plus one title token (overlap 0.2) = 5 (ok)
SCORE4_TEXT = "A note by Doe in Journal Chemistry Catalysis from 2020 about other matters" + PAD
SCORE5_TEXT = "Target note by Doe in Journal Chemistry Catalysis from 2020 about other matters" + PAD
EXPECTED = {"title": "Target Product Synthesis Enzymatic Cascades", "first_author": "Doe",
            "journal": "Journal of Chemistry Catalysis", "year": 2020}


class FakeClient:
    """Stand-in for PoliteHttpClient: scripted get_text / stream_to_file."""

    def __init__(self, texts=None, streams=None, http_get=None):
        self.texts = texts or {}
        self.streams = streams or {}
        self.calls = []
        self.limiter = types.SimpleNamespace(wait=lambda url, extra_delay=0.0: self.calls.append(
            ["wait", url, extra_delay]))
        self._client = types.SimpleNamespace(get=http_get or self._no_get)

    @staticmethod
    def _no_get(url, timeout=None):
        raise RuntimeError("no http_get scripted")

    def get_text(self, url, use_cache=True):
        self.calls.append(["get_text", url, use_cache])
        res = self.texts.get(url)
        if isinstance(res, BaseException):
            raise res
        if res is None:
            raise ScrapeError(f"no fixture for {url}")
        return res

    def stream_to_file(self, url, dest, chunk_size=65536):
        self.calls.append(["stream", url, Path(dest).name])
        res = self.streams.get(url)
        if isinstance(res, BaseException):
            raise res
        if res is None:
            raise ScrapeError(f"no stream fixture for {url}")
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(res)
        return dest


# --------------------------------------------------------------------------
# Crossref / Unpaywall / PMC
# --------------------------------------------------------------------------
CROSSREF_ITEM = {
    "title": ["Target Product Synthesis"], "author": [{"given": "Jane", "family": "Doe"},
                                                      {"family": "Smith"}, {"given": "Only"}],
    "issued": {"date-parts": [[2020, 5]]}, "DOI": "10.1234/test",
    "container-title": ["Journal of Chemistry"], "type": "journal-article", "URL": "https://doi.org/10.1234/test",
    "is-referenced-by-count": 7,
    "link": [{"URL": "https://x.example.com/a.pdf", "content-type": "application/pdf"},
             {"URL": "https://x.example.com/a.html", "content-type": "text/html"}, {"URL": "u"}],
}
CROSSREF_ITEM_NOLINK = dict(CROSSREF_ITEM, link=[{"URL": "https://x.example.com/missing.pdf",
                                                  "content-type": "application/pdf"}])
CROSSREF_ITEMS = {
    "full": CROSSREF_ITEM,
    "empty": {},
    "no_title_list": {"title": []},
    "no_date": {"issued": {}},
    "empty_date_parts": {"issued": {"date-parts": [[]]}},
    "no_container": {"container-title": []},
    "only_doi": {"DOI": "10.1/x"},
}


class FakeHabanero:
    def __init__(self, *, works_result=None, raises=None):
        self.works_result, self.raises, self.calls = works_result, raises, []

    def module(self):
        outer = self

        class Crossref:
            def __init__(self, mailto=None):
                outer.calls.append(["init", mailto])

            def works(self, **kw):
                outer.calls.append(["works", kw])
                if outer.raises:
                    raise outer.raises
                return outer.works_result
        return types.SimpleNamespace(Crossref=Crossref)


def snapshot_crossref(mp) -> dict:
    out = {}
    out["normalize"] = {k: call(fa.CrossrefProvider._normalize, v) for k, v in CROSSREF_ITEMS.items()}
    for key, fh in {
        "ok": FakeHabanero(works_result={"message": CROSSREF_ITEM}),
        "ok_search": FakeHabanero(works_result={"message": {"items": [CROSSREF_ITEM, {}]}}),
        "empty_message": FakeHabanero(works_result={}),
        "boom": FakeHabanero(raises=RuntimeError("404 Not Found")),
    }.items():
        mp.setitem(sys.modules, "habanero", fh.module())
        provider = fa.CrossrefProvider(contact="me@example.org")
        out[f"lookup_{key}"] = call(provider.lookup_doi, "10.1234/test")
        out[f"search_{key}"] = call(provider.search, "enzyme cascade", 3)
        out[f"calls_{key}"] = _jsonable(fh.calls)
    mp.setitem(sys.modules, "habanero", None)
    out["habanero_missing"] = call(fa.CrossrefProvider)
    return out


UNPAYWALL_PAYLOADS = {
    "best": json.dumps({"best_oa_location": {"url_for_pdf": "https://oa.example.com/p.pdf"}}),
    "locations": json.dumps({"best_oa_location": {"url_for_pdf": None},
                             "oa_locations": [{"url_for_pdf": None}, {"url_for_pdf": "https://f.example.com/p.pdf"}]}),
    "closed": json.dumps({"best_oa_location": None, "oa_locations": []}),
    "null_locations": json.dumps({"oa_locations": None}),
    "not_json": "<html>",
}


def snapshot_unpaywall() -> dict:
    out = {}
    for key, payload in UNPAYWALL_PAYLOADS.items():
        url = f"{fa.UnpaywallProvider.API_ROOT}/10.1/x?email=me@example.org"
        client = FakeClient(texts={url: payload})
        up = fa.UnpaywallProvider(client, contact="me@example.org")
        out[key] = {"url": call(up.get_oa_pdf_url, "10.1/x"), "full": call(up.get_full_record, "10.1/x"),
                    "calls": client.calls}
    for key, exc in {"scrape_error": ScrapeError("blocked"), "other": RuntimeError("boom")}.items():
        url = f"{fa.UnpaywallProvider.API_ROOT}/10.1/x?email=me@example.org"
        client = FakeClient(texts={url: exc})
        up = fa.UnpaywallProvider(client, contact="me@example.org")
        out[key] = {"url": call(up.get_oa_pdf_url, "10.1/x"), "full": call(up.get_full_record, "10.1/x")}
    return _jsonable(out)


def snapshot_pmc() -> dict:
    out = {}

    class Resp:
        def __init__(self, text, status_error=None):
            self.text, self._err = text, status_error

        def raise_for_status(self):
            if self._err:
                raise self._err
    cases = {
        "found": lambda url, timeout=None: Resp(json.dumps({"esearchresult": {"idlist": ["2772430", "1"]}})),
        "not_found": lambda url, timeout=None: Resp(json.dumps({"esearchresult": {"idlist": []}})),
        "no_result_key": lambda url, timeout=None: Resp("{}"),
        "bad_json": lambda url, timeout=None: Resp("nope"),
        "http_error": lambda url, timeout=None: Resp("", status_error=RuntimeError("500")),
        "get_raises": lambda url, timeout=None: (_ for _ in ()).throw(OSError("net down")),
    }
    for key, getter in cases.items():
        urls = []

        def recording(url, timeout=None, _g=getter, _u=urls):
            _u.append([url, timeout])
            return _g(url, timeout)
        client = FakeClient(http_get=recording)
        pmc = fa.PmcPdfLocator(client, contact="me@example.org")
        out[key] = {"pdf_url": call(pmc.get_pmc_pdf_url, "10.1234/a b"), "http": urls, "client": client.calls}
    return _jsonable(out)


# --------------------------------------------------------------------------
# Identity gate and helpers
# --------------------------------------------------------------------------
def snapshot_identity(tmp: Path) -> dict:
    out = {}
    docs = {"good": GOOD_TEXT, "suspect": SUSPECT_TEXT, "mismatch": MISMATCH_TEXT, "short": SHORT_TEXT,
            "score4": SCORE4_TEXT, "score5": SCORE5_TEXT}
    for name, text in docs.items():
        path = tmp / f"{name}.pdf"
        path.write_bytes(pdf_bytes(text))
        for exp_name, exp in (("expected", EXPECTED), ("no_expected", None)):
            out[f"{name}|{exp_name}"] = call(fa.verify_pdf_identity, path, doi="10.1234/test", expected=exp)
        out[f"{name}|no_doi"] = call(fa.verify_pdf_identity, path, doi="", expected=EXPECTED)
    html = tmp / "page.pdf"
    html.write_bytes(b"<html>login</html>")
    out["html"] = call(fa.verify_pdf_identity, html, doi="10.1/x", expected=EXPECTED)
    broken = tmp / "broken.pdf"
    broken.write_bytes(b"%PDF-1.4 not really")
    res = fa.verify_pdf_identity(broken, doi="10.1/x", expected=EXPECTED)   # reason text names a pypdf exception
    out["broken"] = {"verdict": res["verdict"], "score": res["score"]}
    out["missing_file"] = call(fa.verify_pdf_identity, tmp / "none.pdf", doi="", expected=None)
    out["short_author_year_variants"] = {
        k: call(fa.verify_pdf_identity, tmp / "good.pdf", doi="", expected=v)
        for k, v in {"author_short": {"first_author": "Do"}, "year_none": {"year": None, "title": ""},
                     "title_only": {"title": "Target Product Synthesis Enzymatic Cascades"}}.items()}
    return norm(out, tmp)


def snapshot_helpers() -> dict:
    return {
        "doi_safe": {v: fa._doi_to_safe_filename(v) for v in ("10.1/a:b\\c", "", "10.1039/D0GC03729A")},
        "title_tokens": {str(v): sorted(fa._title_tokens(v)) for v in ("The new Role of Enzymes", "", None, "a bc defg")},
        "stopwords": sorted(fa._PDF_STOPWORDS),
    }


# --------------------------------------------------------------------------
# Institutional auth (cache, session, fake selenium)
# --------------------------------------------------------------------------
class FakeSession:
    def __init__(self, text="LOGOUT", raises=None):
        self.text, self.raises = text, raises
        self.headers = {}
        outer = self

        class Cookies(dict):
            def set(self, name, value):
                self[name] = value

            def clear(self):
                outer.cleared = True
                super().clear()
        self.cookies = Cookies()
        self.cleared = False

    def get(self, url, timeout=None):
        if self.raises:
            raise self.raises
        return types.SimpleNamespace(text=self.text)


class FakeSelenium:
    def __init__(self, *, launch_errors=(), fail_at=None, page_source="Welcome LOGOUT",
                 manager="ok", cookies=None):
        self.launch_errors = list(launch_errors)
        self.fail_at, self.page_source, self.manager = fail_at, page_source, manager
        self.cookies = cookies if cookies is not None else [{"name": "sid", "value": "abc"}, {"name": "x", "value": "y"}]
        self.events: list = []

    def install(self, mp):
        outer = self

        class Options:
            def __init__(self):
                self.args = []

            def add_argument(self, a):
                self.args.append(a)

        class Driver:
            current_url = "https://login.example.edu/"

            def __init__(self, options):
                self.options = options
                self.page_source = outer.page_source

            def get(self, url):
                outer.events.append(["get", url])

            def get_cookies(self):
                return outer.cookies

            def quit(self):
                outer.events.append(["quit"])

        class Element:
            def click(self):
                outer.events.append(["click"])
                Driver.current_url = "https://library.example.edu/home"

        def chrome(service=None, options=None):
            idx = sum(1 for e in outer.events if e[0] == "launch")
            outer.events.append(["launch", options.args, service is not None])
            if idx < len(outer.launch_errors) and outer.launch_errors[idx] is not None:
                raise outer.launch_errors[idx]
            return Driver(options)

        class Wait:
            def __init__(self, driver, timeout):
                self.driver = driver

            def until(self, cond):
                res = cond(self.driver)
                if not res:
                    raise RuntimeError("timed out waiting")
                return res

        def element_to_be_clickable(locator):
            outer.events.append(["locator", list(locator)])
            return lambda d: None if outer.fail_at == "button" else Element()

        def url_contains(host):
            outer.events.append(["url_contains", host])
            return lambda d: False if outer.fail_at == "url" else host in d.current_url

        mods = {}

        def mod(name, **attrs):
            m = types.ModuleType(name)
            m.__dict__.update(attrs)
            mods[name] = m
            return m
        webdriver = mod("selenium.webdriver", Chrome=chrome, ChromeOptions=Options)
        by = mod("selenium.webdriver.common.by", By=types.SimpleNamespace(CSS_SELECTOR="css selector"))
        ui = mod("selenium.webdriver.support.ui", WebDriverWait=Wait)
        ec = mod("selenium.webdriver.support.expected_conditions",
                 element_to_be_clickable=element_to_be_clickable, url_contains=url_contains)
        support = mod("selenium.webdriver.support", ui=ui, expected_conditions=ec)
        common = mod("selenium.webdriver.common", by=by)
        service_mod = mod("selenium.webdriver.chrome.service", Service=lambda path: ("service", path))
        chrome_pkg = mod("selenium.webdriver.chrome", service=service_mod)
        selenium = mod("selenium", webdriver=webdriver)
        webdriver.common, webdriver.support, webdriver.chrome = common, support, chrome_pkg
        for name, m in mods.items():
            mp.setitem(sys.modules, name, m)
        if outer.manager == "ok":
            class Manager:
                def install(self):
                    return "/driver/path"
            wm = mod("webdriver_manager.chrome", ChromeDriverManager=Manager)
            mp.setitem(sys.modules, "webdriver_manager", mod("webdriver_manager", chrome=wm))
            mp.setitem(sys.modules, "webdriver_manager.chrome", wm)
        elif outer.manager == "fail":
            class Manager:
                def install(self):
                    raise RuntimeError("no network for driver")
            wm = mod("webdriver_manager.chrome", ChromeDriverManager=Manager)
            mp.setitem(sys.modules, "webdriver_manager", mod("webdriver_manager", chrome=wm))
            mp.setitem(sys.modules, "webdriver_manager.chrome", wm)
        else:
            mp.setitem(sys.modules, "webdriver_manager", None)
            mp.setitem(sys.modules, "webdriver_manager.chrome", None)
        _ = selenium
        return self


def snapshot_auth(mp, tmp: Path) -> dict:
    out = {}
    cache = tmp / "cookies.json"
    mp.setattr(fa.InstitutionalLibraryAuth, "COOKIE_CACHE_FILE", str(cache))
    mp.setattr(fa.InstitutionalLibraryAuth, "SESSION_CHECK_URL", "https://library.example.edu/")
    mp.setattr(fa.InstitutionalLibraryAuth, "LOGIN_URL", "https://library.example.edu/login/")
    auth = fa.InstitutionalLibraryAuth()

    out["cache_missing"] = call(auth._load_cached_cookies)
    out["cache_save"] = call(auth._save_cookie_cache, {"sid": "한글", "b": "2"})
    saved = json.loads(cache.read_text(encoding="utf-8"))
    out["cache_saved_shape"] = {"keys": sorted(saved), "cookies": saved["cookies"]}
    out["cache_fresh"] = call(auth._load_cached_cookies)
    now = datetime.datetime.now()
    for name, payload in {
        "stale": {"saved_at": (now - datetime.timedelta(hours=7)).isoformat(), "cookies": {"a": "1"}},
        "just_fresh": {"saved_at": (now - datetime.timedelta(hours=5)).isoformat(), "cookies": {"a": "1"}},
        "no_saved_at": {"cookies": {"a": "1"}},
        "bad_cookies": {"saved_at": now.isoformat(), "cookies": ["x"]},
        "bad_date": {"saved_at": "yesterday", "cookies": {}},
    }.items():
        cache.write_text(json.dumps(payload), encoding="utf-8")
        out[f"cache_{name}"] = call(auth._load_cached_cookies, _trunc=36)
    cache.write_text("{not json", encoding="utf-8")
    out["cache_corrupt"] = call(auth._load_cached_cookies, _trunc=36)
    mp.setattr(fa.InstitutionalLibraryAuth, "COOKIE_CACHE_FILE", str(tmp / "no_such_dir" / "deep" / "c.json"))
    out["cache_save_creates_dirs"] = call(auth._save_cookie_cache, {"k": "v"})
    out["cache_dirs_created"] = (tmp / "no_such_dir" / "deep" / "c.json").exists()
    mp.setattr(fa.InstitutionalLibraryAuth, "COOKIE_CACHE_FILE", str(tmp))  # a directory -> write fails
    out["cache_save_fails"] = call(auth._save_cookie_cache, {"k": "v"}, _trunc=26)
    mp.setattr(fa.InstitutionalLibraryAuth, "COOKIE_CACHE_FILE", str(cache))

    for key, sess in {"logout": FakeSession("<a>LOGOUT</a>"), "korean": FakeSession("로그아웃"),
                      "login": FakeSession("LOGIN"), "raises": FakeSession(raises=OSError("down"))}.items():
        out[f"valid_{key}"] = call(auth.is_session_valid, sess)

    # refresh_if_expired: valid -> untouched; expired -> re-login via (patched) selenium
    valid = FakeSession("LOGOUT")
    valid.cookies["old"] = "1"
    out["refresh_valid"] = {"call": call(lambda: auth.refresh_if_expired(valid) is valid),
                            "cookies": dict(valid.cookies)}
    expired = FakeSession("LOGIN")
    expired.cookies["old"] = "1"
    mp.setattr(fa.InstitutionalLibraryAuth, "_selenium_login", lambda self: {"new": "2"})
    mp.setattr(fa.InstitutionalLibraryAuth, "COOKIE_CACHE_FILE", str(tmp / "refresh.json"))
    res = call(lambda: auth.refresh_if_expired(expired) is expired)
    out["refresh_expired"] = {"warnings": res["warnings"], "cookies": dict(expired.cookies),
                              "cleared": expired.cleared,
                              "cache_cookies": json.loads((tmp / "refresh.json").read_text(encoding="utf-8"))["cookies"]}

    # get_session with a fake requests module
    fake_requests = types.SimpleNamespace(Session=FakeSession)
    mp.setitem(sys.modules, "requests", fake_requests)
    mp.setattr(fa.InstitutionalLibraryAuth, "COOKIE_CACHE_FILE", str(cache))
    cache.write_text(json.dumps({"saved_at": now.isoformat(), "cookies": {"sid": "cached"}}), encoding="utf-8")
    sess = auth.get_session()
    out["get_session_cached"] = {"cookies": dict(sess.cookies), "ua_prefix": sess.headers.get("User-Agent", "")[:20]}
    cache.write_text(json.dumps({"saved_at": (now - datetime.timedelta(hours=9)).isoformat(),
                                 "cookies": {"sid": "old"}}), encoding="utf-8")
    mp.setattr(fa.InstitutionalLibraryAuth, "_selenium_login", lambda self: {"sid": "fresh"})
    sess = auth.get_session()
    out["get_session_relogin"] = {"cookies": dict(sess.cookies),
                                  "cache": json.loads(cache.read_text(encoding="utf-8"))["cookies"]}
    mp.setitem(sys.modules, "requests", None)
    out["get_session_no_requests"] = call(auth.get_session)
    mp.undo()
    return norm(out, tmp)


def _clean_events(events):
    """The Windows branch expands %LOCALAPPDATA% only on Windows; keep what is OS-independent."""
    cleaned = []
    for ev in events:
        if ev[0] == "launch":
            args = []
            for a in ev[1]:
                if a.startswith("--user-data-dir="):
                    tail = a.split("=", 1)[1].replace(chr(92), "/")
                    a = "--user-data-dir=<WIN>" if tail.endswith("Google/Chrome/User Data") else                         "--user-data-dir=" + tail
                args.append(a)
            ev = [ev[0], args, ev[2]]
        cleaned.append(ev)
    return cleaned


def snapshot_selenium(mp, tmp: Path) -> dict:
    out = {}
    mp.setattr(fa.InstitutionalLibraryAuth, "SESSION_CHECK_URL", "https://library.example.edu/")
    mp.setattr(fa.InstitutionalLibraryAuth, "LOGIN_URL", "https://library.example.edu/login/")
    import platform
    import time
    mp.setattr(time, "sleep", lambda *_: None)
    mp.setenv("LOCALAPPDATA", str(tmp / "local"))
    mp.setenv("HOME", str(tmp / "fakehome"))
    mp.setenv("USERPROFILE", str(tmp / "fakehome"))
    locked = RuntimeError("session not created: user data directory is already in use")
    scenarios = {
        "ok_default_manager": dict(),
        "ok_linux": dict(system="Linux"),
        "manager_missing": dict(manager="missing"),
        "manager_fails": dict(manager="fail"),
        "default_locked_profile1_ok": dict(launch_errors=[locked, None]),
        "default_other_error": dict(launch_errors=[RuntimeError("chromedriver mismatch")]),
        "both_locked": dict(launch_errors=[locked, locked]),
        "default_locked_profile1_other": dict(launch_errors=[locked, RuntimeError("nope")]),
        "button_never_appears": dict(fail_at="button"),
        "redirect_never_happens": dict(fail_at="url"),
        "no_logout_marker": dict(page_source="please sign in"),
        "korean_logout_marker": dict(page_source="환영합니다 로그아웃"),
        "no_cookies": dict(cookies=[]),
    }
    for key, kw in scenarios.items():
        system = kw.pop("system", "Windows")
        mp.setattr(platform, "system", lambda s=system: s)
        fs = FakeSelenium(**kw).install(mp)
        out[key] = {"call": call(fa.InstitutionalLibraryAuth()._selenium_login), "events": _clean_events(fs.events)}
    mp.setitem(sys.modules, "selenium", None)
    mp.setitem(sys.modules, "selenium.webdriver", None)
    out["selenium_missing"] = call(fa.InstitutionalLibraryAuth()._selenium_login)
    return norm(out, tmp)


# --------------------------------------------------------------------------
# EZproxy
# --------------------------------------------------------------------------
REAL_BASE = "https://ezproxy.example.edu/link.n2s?url="
PROXY_HOST = "ezproxy.example.edu"


import httpx as _httpx  # noqa: E402

REAL_HTTPX_CLIENT = _httpx.Client


def R(status=200, **kw):
    """A route returning a fresh httpx.Response per request."""
    import httpx
    return lambda request: httpx.Response(status, **kw)


class MockedHttpx:
    """Patch httpx.Client so EZproxy requests go through a scripted MockTransport."""

    def __init__(self, mp, routes):
        import httpx
        self.requests = []
        self.client_kwargs = []
        outer = self

        def handler(request: httpx.Request) -> httpx.Response:
            outer.requests.append({"url": str(request.url), "cookie": request.headers.get("cookie"),
                                   "ua": request.headers.get("user-agent", "")[:12]})
            route = routes.get(str(request.url))
            if route is None:
                return httpx.Response(404, text="nope")
            if isinstance(route, BaseException):
                raise route
            return route(request)

        real = REAL_HTTPX_CLIENT   # never the previous scenario's patched factory

        def factory(**kw):
            outer.client_kwargs.append({k: (sorted(kw[k]) if k == "headers" else kw[k])
                                        for k in ("follow_redirects", "timeout", "headers") if k in kw})
            kw.pop("transport", None)
            return real(transport=httpx.MockTransport(handler), **kw)
        mp.setattr(httpx, "Client", factory)


def snapshot_ezproxy(mp, tmp: Path) -> dict:
    import httpx
    out = {}
    mp.setattr(socket, "getaddrinfo", lambda *a, **k: (_ for _ in ()).throw(socket.gaierror("no dns")))
    EZ = fa.EZproxyPdfDownloader

    # cookie file loading
    out["load_missing"] = call(fa.load_netscape_cookies, str(tmp / "none.txt"))
    good = tmp / "cookies.txt"
    good.write_text("# Netscape HTTP Cookie File\n"
                    ".ezproxy.example.edu\tTRUE\t/\tTRUE\t0\tEZPROXY\tSECRET\n", encoding="utf-8")
    jar = fa.load_netscape_cookies(str(good))
    out["load_good"] = [[c.name, c.value, c.domain] for c in jar]
    bad = tmp / "bad.txt"
    bad.write_text("not a cookie file\n", encoding="utf-8")
    out["load_bad"] = call(fa.load_netscape_cookies, str(bad))
    out["load_bad"]["raised"][1] = out["load_bad"]["raised"][1].split(" does not")[-1]   # message starts with the path
    out["guidance"] = fa.EZPROXY_COOKIE_GUIDANCE.format(cookie_file="<F>")

    mp.setattr(EZ, "PROXY_BASE", "https://ezproxy.your-institution.edu/link.n2s?url=")
    placeholder = EZ()
    out["placeholder_required"] = call(placeholder._require_configured)
    out["placeholder_download"] = call(placeholder.download, "10.1/x", tmp / "p.pdf")
    out["placeholder_get_pdf_url"] = call(placeholder.get_pdf_url, "10.1/x")

    mp.setattr(EZ, "PROXY_BASE", REAL_BASE)
    ez = EZ(cookie_file=str(good))
    out["configured"] = call(ez._require_configured)
    out["proxy_url"] = ez._build_proxy_url("10.1021/abc")
    out["cookie_dict_legacy"] = call(ez._get_cookie_dict)
    jar2 = ez._cookie_jar(PROXY_HOST)
    heads = {}
    for url in ("https://ezproxy.example.edu/x", "https://pubs-acs-org-ssl.ezproxy.example.edu/y",
                "https://evil.example.net/x", "https://ezproxy.example.edu.evil.net/x"):
        req = httpx.Request("GET", url)
        jar2.set_cookie_header(req)
        heads[url] = req.headers.get("cookie")
    out["cookie_jar_scope"] = heads
    out["cookie_dict_missing_file"] = call(EZ(cookie_file=str(tmp / "absent.txt"))._get_cookie_dict)

    # auth mode
    class FakeAuth:
        def __init__(self):
            self.calls = []
            self.session = types.SimpleNamespace(cookies={"sid": "A"})

        def get_session(self):
            self.calls.append("get_session")
            return self.session

        def refresh_if_expired(self, session):
            self.calls.append("refresh")
            return session
    fauth = FakeAuth()
    ez_auth = EZ(auth=fauth)
    out["auth_first"] = call(ez_auth._get_cookie_dict)
    out["auth_second"] = call(ez_auth._get_cookie_dict)
    out["auth_calls"] = fauth.calls

    # link gating and extraction
    urls = ["https://pubs-acs-org-ssl.ezproxy.example.edu/doi/pdf/10.1/x", "https://ezproxy.example.edu/pdf/x",
            "https://www.nature.com/articles/x.pdf", "https://evil.example.net/x.pdf",
            "https://ezproxy.example.edu.evil.net/x.pdf", "file:///etc/passwd", "http://127.0.0.1:8777/x.pdf",
            "http://169.254.169.254/latest", None, "", "https://EZPROXY.example.edu./pdf"]
    out["accept"] = {str(u): call(ez._accept_pdf_url, u, PROXY_HOST) for u in urls}
    htmls = {
        "dot_pdf": '<a href="/files/paper.pdf">x</a>',
        "download_word": "<a href='https://pubs.acs.org/doi/download/10.1/x'>x</a>",
        "skips_fragment": '<a href="#pdf">a</a><a href="javascript:pdf()">b</a><a href="mailto:pdf@x">c</a>'
                          '<a href="/real/pdf/view">d</a>',
        "none": "<a href='/about'>about</a>",
        "ftp_ignored": '<a href="ftp://h/x.pdf">x</a>',
        "case_insensitive": '<A HREF="/DOWNLOAD/Paper">x</A>',
        "relative_base": '<a href="paper.pdf">x</a>',
        "query_pdf": '<a href="/get?file=x.pdf&v=2">x</a>',
    }
    out["extract"] = {k: ez._extract_pdf_link(h, "https://ezproxy.example.edu/a/b/page") for k, h in htmls.items()}

    # get_pdf_url over a mocked transport
    proxy_url = ez._build_proxy_url("10.1/x")
    pdf = pdf_bytes(GOOD_TEXT)
    html_ok = R(200, headers={"content-type": "text/html; charset=utf-8"},
                             text='<a href="https://pubs-acs-org-ssl.ezproxy.example.edu/doi/pdf/10.1/x">PDF</a>')
    scenarios = {
        "pdf_content_type": {proxy_url: R(200, headers={"content-type": "application/pdf"}, content=pdf)},
        "html_with_link": {proxy_url: html_ok},
        "html_evil_link": {proxy_url: R(200, headers={"content-type": "text/html"},
                                                     text='<a href="https://evil.example.net/x.pdf">x</a>')},
        "html_no_link": {proxy_url: R(200, headers={"content-type": "text/html"}, text="<p>nothing</p>")},
        "other_content_type": {proxy_url: R(200, headers={"content-type": "text/plain"}, text="x")},
        "http_404": {},
        "transport_error": {proxy_url: OSError("connection reset")},
        "redirect_to_proxy_subdomain": {proxy_url: R(
            302, headers={"location": "https://pubs-acs-org-ssl.ezproxy.example.edu/doi/pdf/10.1/x"}),
            "https://pubs-acs-org-ssl.ezproxy.example.edu/doi/pdf/10.1/x": R(
                200, headers={"content-type": "application/pdf"}, content=pdf)},
    }
    out["get_pdf_url"] = {}
    for key, routes in scenarios.items():
        mocked = MockedHttpx(mp, routes)
        limiter_calls = []
        limiter = types.SimpleNamespace(wait=lambda url, extra_delay=0.0, _c=limiter_calls: _c.append([url, extra_delay]))
        out["get_pdf_url"][key] = {"call": call(ez.get_pdf_url, "10.1/x", rate_limiter=limiter, _trunc=90),
                                   "requests": mocked.requests, "clients": mocked.client_kwargs,
                                   "limiter": limiter_calls}

    # download over a mocked transport
    final_pdf_url = "https://pubs-acs-org-ssl.ezproxy.example.edu/doi/pdf/10.1/x"
    proxy_dl = ez._build_proxy_url("10.1234/test")
    base_routes = {proxy_dl: html_ok}
    dl_cases = {
        "ok": ({**base_routes, final_pdf_url: R(200, content=pdf)}, EXPECTED),
        "ok_no_expected": ({**base_routes, final_pdf_url: R(200, content=pdf)}, None),
        "suspect": ({**base_routes, final_pdf_url: R(200, content=pdf_bytes(SUSPECT_TEXT))}, EXPECTED),
        "mismatch": ({**base_routes, final_pdf_url: R(200, content=pdf_bytes(MISMATCH_TEXT))}, EXPECTED),
        "html_instead": ({**base_routes, final_pdf_url: R(200, content=b"<html>" + b"x" * 2000)}, EXPECTED),
        "too_small": ({**base_routes, final_pdf_url: R(200, content=b"%PDF-")}, EXPECTED),
        "size_700": ({**base_routes, final_pdf_url: R(200, content=b"%PDF-" + b"x" * 695)}, EXPECTED),
        "size_1024": ({**base_routes, final_pdf_url: R(200, content=b"%PDF-" + b"x" * 1019)}, EXPECTED),
        "score4": ({**base_routes, final_pdf_url: R(200, content=pdf_bytes(SCORE4_TEXT))}, EXPECTED),
        "score5": ({**base_routes, final_pdf_url: R(200, content=pdf_bytes(SCORE5_TEXT))}, EXPECTED),
        "stream_http_error": ({**base_routes, final_pdf_url: R(403, text="no")}, EXPECTED),
        "unresolved": ({proxy_dl: R(200, headers={"content-type": "text/html"}, text="none")}, EXPECTED),
    }
    out["download"] = {}
    for key, (routes, expected) in dl_cases.items():
        mocked = MockedHttpx(mp, routes)
        dest = tmp / "dl" / key / "paper.pdf"
        limiter_calls = []
        limiter = types.SimpleNamespace(wait=lambda url, extra_delay=0.0, _c=limiter_calls: _c.append([url, extra_delay]))
        res = call(ez.download, "10.1234/test", dest, rate_limiter=limiter, expected=expected, _trunc=110)
        listing = sorted(p.name for p in dest.parent.iterdir()) if dest.parent.exists() else None
        out["download"][key] = {"call": res, "files": listing, "limiter": limiter_calls,
                                "clients": mocked.client_kwargs}
    missing_cookie = EZ(cookie_file=str(tmp / "absent.txt"))
    out["download_cookie_missing"] = call(missing_cookie.download, "10.1/x", tmp / "dl" / "c.pdf")
    return norm(out, tmp)


def snapshot_libkey() -> dict:
    lk = fa.LibKeyNomadProvider()
    return {"available": lk.is_available(), "check": fa.LibKeyNomadProvider._check_chrome_mcp(),
            "url": lk.get_pdf_url("10.1/x"), "bases": [fa.LibKeyNomadProvider.PUBMED_BASE,
                                                       fa.LibKeyNomadProvider.DOI_BASE]}


# --------------------------------------------------------------------------
# PdfDownloader waterfall
# --------------------------------------------------------------------------
class StubSource:
    def __init__(self, url=None, raises=None):
        self.url, self.raises, self.calls = url, raises, []

    def get_oa_pdf_url(self, doi):
        self.calls.append(doi)
        if self.raises:
            raise self.raises
        return self.url

    get_pmc_pdf_url = get_oa_pdf_url
    get_pdf_url = get_oa_pdf_url


class StubEz:
    def __init__(self, result):
        self.result, self.calls = result, []

    def download(self, doi, dest, rate_limiter=None, expected=None):
        self.calls.append([doi, Path(dest).name, expected])
        return dict(self.result)


def snapshot_downloader(tmp: Path) -> dict:
    out = {}
    good, suspect = pdf_bytes(GOOD_TEXT), pdf_bytes(SUSPECT_TEXT)
    mismatch = pdf_bytes(MISMATCH_TEXT)
    record = {"doi": "10.1234/test", "authors": ["Jane Doe", "John Smith"], "year": 2020,
              "title": "Target Product Synthesis Enzymatic Cascades", "journal": "Journal of Chemistry Catalysis",
              "pdf_links": ["https://pub.example.com/a.pdf", "https://pub.example.com/b.pdf"]}
    scenarios = {
        "crossref_first_link": dict(streams={"https://pub.example.com/a.pdf": good}),
        "crossref_second_link": dict(streams={"https://pub.example.com/b.pdf": good}),
        "crossref_suspect": dict(streams={"https://pub.example.com/a.pdf": suspect}),
        "crossref_mismatch_then_unpaywall": dict(
            streams={"https://pub.example.com/a.pdf": mismatch, "https://pub.example.com/b.pdf": b"x" * 10,
                     "https://oa.example.com/p.pdf": good}, unpaywall="https://oa.example.com/p.pdf"),
        "pmc": dict(streams={"https://pmc.example.com/p.pdf": good}, pmc="https://pmc.example.com/p.pdf"),
        "libkey": dict(streams={"https://libkey.example.com/p.pdf": good}, libkey_url="https://libkey.example.com/p.pdf",
                       use_libkey=True),
        "libkey_disabled": dict(streams={}, libkey_url="https://libkey.example.com/p.pdf", use_libkey=False),
        "ezproxy_ok": dict(streams={}, use_ezproxy=True,
                           ez={"downloaded_path": "x", "download_source": "ezproxy", "download_status": "ok"}),
        "ezproxy_fail": dict(streams={}, use_ezproxy=True,
                             ez={"downloaded_path": None, "download_source": "ezproxy", "download_status": "nope"}),
        "ezproxy_not_enabled": dict(streams={}, use_ezproxy=False,
                                    ez={"downloaded_path": "x", "download_source": "ezproxy", "download_status": "ok"}),
        "all_fail_plain": dict(streams={}),
        "all_fail_flags": dict(streams={}, use_libkey=True, use_ezproxy=True,
                               ez={"downloaded_path": None, "download_source": "ezproxy", "download_status": "no"}),
        "stream_errors": dict(streams={"https://pub.example.com/a.pdf": OSError("reset"),
                                       "https://pub.example.com/b.pdf": ScrapeError("403")}),
        "size_700_then_unpaywall": dict(streams={"https://pub.example.com/a.pdf": b"%PDF-" + b"x" * 695,
                                                 "https://pub.example.com/b.pdf": b"%PDF-" + b"x" * 1019,
                                                 "https://oa.example.com/p.pdf": good},
                                        unpaywall="https://oa.example.com/p.pdf"),
        "size_700_single_link": dict(streams={"https://pub.example.com/a.pdf": b"%PDF-" + b"x" * 695},
                                     links=["https://pub.example.com/a.pdf"]),
        "score4_crossref": dict(streams={"https://pub.example.com/a.pdf": pdf_bytes(SCORE4_TEXT)}),
        "score5_crossref": dict(streams={"https://pub.example.com/a.pdf": pdf_bytes(SCORE5_TEXT)}),
        "html_page": dict(streams={"https://pub.example.com/a.pdf": b"<html>" + b"x" * 3000,
                                   "https://pub.example.com/b.pdf": b"<html>" + b"y" * 3000}),
        "unpaywall_raises": dict(streams={}, unpaywall_raises=RuntimeError("unpaywall down")),
    }
    for key, sc in scenarios.items():
        client = FakeClient(streams=sc["streams"])
        up = StubSource(sc.get("unpaywall"), raises=sc.get("unpaywall_raises"))
        pmc = StubSource(sc.get("pmc"))
        libkey = StubSource(sc.get("libkey_url")) if "libkey_url" in sc else None
        ez = StubEz(sc["ez"]) if "ez" in sc else None
        dest_dir = tmp / key
        dl = fa.PdfDownloader(client=client, unpaywall=up, pmc=pmc, dest_dir=dest_dir,
                              use_ezproxy=sc.get("use_ezproxy", False), ezproxy=ez,
                              use_libkey=sc.get("use_libkey", False), libkey=libkey)
        rec = dict(record, pdf_links=sc["links"]) if "links" in sc else record
        res = call(dl.download, rec)
        out[key] = {"call": res, "files": sorted(p.name for p in dest_dir.iterdir()),
                    "client": client.calls, "unpaywall": up.calls, "pmc": pmc.calls,
                    "libkey": libkey.calls if libkey else None, "ez": ez.calls if ez else None}
    # record variants and hostile filename parts
    variants = {
        "no_doi": {"authors": ["Jane Doe"], "year": 2020, "pdf_links": ["https://pub.example.com/a.pdf"]},
        "no_authors_no_year": {"doi": "10.1/x", "pdf_links": ["https://pub.example.com/a.pdf"]},
        "empty_author_string": {"doi": "10.1/x", "authors": [""], "year": 1999,
                                "pdf_links": ["https://pub.example.com/a.pdf"]},
        "hostile": {"doi": "10.1/../../etc:passwd", "authors": ["Eve ../../Evil"], "year": "20/20",
                    "pdf_links": ["https://pub.example.com/a.pdf"]},
        "empty_record": {},
    }
    for key, rec in variants.items():
        client = FakeClient(streams={"https://pub.example.com/a.pdf": good})
        dest_dir = tmp / f"variant_{key}"
        dl = fa.PdfDownloader(client=client, unpaywall=StubSource(), pmc=StubSource(), dest_dir=dest_dir)
        res = call(dl.download, rec)
        files = sorted(str(p.relative_to(tmp)) for p in tmp.rglob("*") if p.is_file() and f"variant_{key}" in str(p))
        out[f"variant_{key}"] = {"call": res, "files": files, "escaped": [str(p.name) for p in tmp.iterdir()
                                                                       if p.is_file()]}
    out["init_defaults"] = {
        "ezproxy_default_class": type(fa.PdfDownloader(FakeClient(), StubSource(), StubSource(), tmp / "init1",
                                                       use_ezproxy=True)._ezproxy).__name__,
        "ezproxy_none": fa.PdfDownloader(FakeClient(), StubSource(), StubSource(), tmp / "init2")._ezproxy is None,
        "libkey_default_class": type(fa.PdfDownloader(FakeClient(), StubSource(), StubSource(), tmp / "init3",
                                                      use_libkey=True)._libkey).__name__,
        "dest_created": (tmp / "init3").is_dir(),
    }
    return norm(out, tmp)


# --------------------------------------------------------------------------
# arXiv / bioRxiv
# --------------------------------------------------------------------------
def fake_arxiv_module(papers=None, raises=None, calls=None):
    calls = calls if calls is not None else []

    class Client:
        def results(self, search):
            calls.append(["results", search.query, search.max_results, search.sort_by])
            if raises:
                raise raises
            yield from (papers or [])

    class Search:
        def __init__(self, query, max_results, sort_by):
            self.query, self.max_results, self.sort_by = query, max_results, sort_by

    return types.SimpleNamespace(Client=Client, Search=Search,
                                 SortCriterion=types.SimpleNamespace(SubmittedDate="submittedDate"))


def fake_paper(i, *, published=True, pdf=True, doi="10.48550/arXiv.2401.0001"):
    return types.SimpleNamespace(
        title=f"Paper {i}", authors=[types.SimpleNamespace(name="A. One"), types.SimpleNamespace(name="B. Two")],
        published=datetime.datetime(2024, 1, 2) if published else None, doi=doi if i % 2 == 0 else None,
        get_short_id=lambda i=i: f"2401.000{i}v1", summary="sum", entry_id=f"http://arxiv.org/abs/2401.000{i}",
        pdf_url=f"http://arxiv.org/pdf/2401.000{i}" if pdf else None, categories=["cs.LG", "q-bio.QM"])


def snapshot_arxiv(mp) -> dict:
    out = {}
    calls: list = []
    mp.setitem(sys.modules, "arxiv", fake_arxiv_module([fake_paper(1), fake_paper(2, published=False, pdf=False)],
                                                       calls=calls))
    out["ok"] = call(fa.ArxivProvider().search, "enzyme cascade", 5)
    out["calls"] = _jsonable(calls)
    out["name"] = fa.ArxivProvider.name
    mp.setitem(sys.modules, "arxiv", fake_arxiv_module(raises=RuntimeError("503")))
    out["error"] = call(fa.ArxivProvider().search, "x", 1)
    mp.setitem(sys.modules, "arxiv", fake_arxiv_module([]))
    out["empty"] = call(fa.ArxivProvider().search, "x", 1)
    mp.setitem(sys.modules, "arxiv", None)
    out["missing_package"] = call(fa.ArxivProvider)
    return out


BIORXIV_PAYLOAD = {"messages": [{"status": "ok", "count": 2}], "collection": [
    {"title": "T1", "authors": "A; B", "date": "2024-03-05", "doi": "10.1101/2024.03.05.1", "category": "genomics"},
    {"title": "T2", "authors": None, "date": None, "doi": None, "category": None},
    {}]}


def snapshot_biorxiv() -> dict:
    out = {}
    root = fa.BiorxivProvider.API_ROOT
    for server in ("biorxiv", "medrxiv"):
        client = FakeClient(texts={f"{root}/details/{server}/10.1101/x": json.dumps(BIORXIV_PAYLOAD),
                                   f"{root}/details/{server}/30": json.dumps({"collection": []}),
                                   f"{root}/details/{server}/bad": "<html>"})
        bp = fa.BiorxivProvider(client, server=server)
        out[server] = {"doi": call(bp.lookup_doi, "10.1101/x"), "recent": call(bp.recent, "30"),
                       "non_json": call(bp._fetch, f"{root}/details/{server}/bad"),
                       "no_fixture": call(bp.recent, "7"), "calls": client.calls, "server": bp.server}
    out["name"] = fa.BiorxivProvider.name
    return _jsonable(out)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def run_cli(argv, tmp: Path) -> dict:
    out, err = io.StringIO(), io.StringIO()
    cwd = os.getcwd()
    code = None
    saved_argv = sys.argv
    sys.argv = ["fetch_academic.py"]          # argparse prog name must not depend on the runner
    try:
        os.chdir(tmp)
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            try:
                code = fa.main(argv)
            except SystemExit as exc:
                code = exc.code
            except BaseException as exc:  # noqa: BLE001
                code = f"raised {type(exc).__name__}: {exc}"
    finally:
        os.chdir(cwd)
        sys.argv = saved_argv
    stdout = out.getvalue()
    parsed = None
    try:
        parsed = json.loads(stdout)
    except ValueError:
        pass
    return {"code": code, "stdout": parsed if parsed is not None else stdout,
            "stderr": err.getvalue().splitlines()[-1:] if err.getvalue() else [],
            "warnings": sorted({str(x.message) for x in w if not issubclass(x.category, ResourceWarning)})}


def snapshot_cli(mp, tmp: Path) -> dict:
    out = {}
    mp.setattr(socket, "getaddrinfo", lambda *a, **k: (_ for _ in ()).throw(socket.gaierror("no dns")))
    mp.setattr(RateLimiter, "wait", lambda self, url, extra_delay=0.0: None)
    root = fa.BiorxivProvider.API_ROOT
    texts = {f"{root}/details/biorxiv/10.1101/x": json.dumps(BIORXIV_PAYLOAD),
             f"{root}/details/medrxiv/14": json.dumps({"messages": [], "collection": BIORXIV_PAYLOAD["collection"][:1]})}

    def get_text(self, url, use_cache=True):
        if url in texts:
            return texts[url]
        raise ScrapeError(f"no fixture: {url}")
    good = pdf_bytes(GOOD_TEXT)
    streams = {"https://x.example.com/a.pdf": good}

    def stream_to_file(self, url, dest, chunk_size=65536, max_bytes=None):
        if url not in streams:
            raise ScrapeError(f"no stream: {url}")
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(streams[url])
        return Path(dest)
    mp.setattr(PoliteHttpClient, "get_text", get_text)
    mp.setattr(PoliteHttpClient, "stream_to_file", stream_to_file)
    mp.setattr(fa.UnpaywallProvider, "get_oa_pdf_url", lambda self, doi: None)
    mp.setattr(fa.PmcPdfLocator, "get_pmc_pdf_url", lambda self, doi: None)

    mp.setitem(sys.modules, "habanero", FakeHabanero(works_result={"message": CROSSREF_ITEM}).module())
    out["crossref_doi"] = run_cli(["--source", "crossref", "--doi", "10.1234/test"], tmp)
    mp.setitem(sys.modules, "habanero", FakeHabanero(works_result={"message": {"items": [CROSSREF_ITEM, {}]}}).module())
    out["crossref_query"] = run_cli(["--source", "crossref", "--query", "enzyme", "-n", "2"], tmp)
    out["crossref_nothing"] = run_cli(["--source", "crossref"], tmp)
    mp.setitem(sys.modules, "habanero", FakeHabanero(raises=RuntimeError("404")).module())
    out["crossref_lookup_error"] = run_cli(["--source", "crossref", "--doi", "10.1/none"], tmp)
    mp.setitem(sys.modules, "habanero", FakeHabanero(works_result={"message": CROSSREF_ITEM}).module())
    out["crossref_download_ok"] = run_cli(["--source", "crossref", "--doi", "10.1234/test", "--download",
                                          "--download-dir", str(tmp / "dl_ok")], tmp)
    out["crossref_download_files"] = sorted(p.name for p in (tmp / "dl_ok").iterdir())
    mp.setitem(sys.modules, "habanero", FakeHabanero(works_result={"message": CROSSREF_ITEM_NOLINK}).module())
    out["crossref_download_ezproxy_unconfigured"] = run_cli(
        ["--source", "crossref", "--doi", "10.1234/test", "--download", "--ezproxy", "--libkey",
         "--download-dir", str(tmp / "dl_ez"), "--cookie-file", str(tmp / "nocookies.txt")], tmp)
    out["crossref_download_auto_login"] = run_cli(
        ["--source", "crossref", "--doi", "10.1234/test", "--download", "--auto-login",
         "--download-dir", str(tmp / "dl_auto")], tmp)
    mp.setitem(sys.modules, "habanero", FakeHabanero(works_result={"message": CROSSREF_ITEM}).module())
    out["crossref_output_file"] = run_cli(["--source", "crossref", "--doi", "10.1234/test", "-o", str(tmp / "o" / "r.json")], tmp)
    out["crossref_output_content"] = norm(json.loads((tmp / "o" / "r.json").read_text(encoding="utf-8")), tmp)

    mp.setitem(sys.modules, "arxiv", fake_arxiv_module([fake_paper(1)]))
    out["arxiv_query"] = run_cli(["--source", "arxiv", "--query", "enzyme", "-n", "1"], tmp)
    out["arxiv_nothing"] = run_cli(["--source", "arxiv"], tmp)
    out["biorxiv_doi"] = run_cli(["--source", "biorxiv", "--doi", "10.1101/x"], tmp)
    out["biorxiv_recent_medrxiv"] = run_cli(["--source", "biorxiv", "--server", "medrxiv", "--recent", "14"], tmp)
    out["biorxiv_nothing"] = run_cli(["--source", "biorxiv"], tmp)
    out["biorxiv_missing_fixture"] = run_cli(["--source", "biorxiv", "--recent", "99"], tmp)
    out["bad_source"] = run_cli(["--source", "pubmed"], tmp)
    out["no_args"] = run_cli([], tmp)

    parser = fa._build_parser()
    actions = {}
    for a in parser._actions:
        actions[a.dest] = {"flags": list(a.option_strings), "default": a.default if not callable(a.default) else "callable",
                           "choices": list(a.choices) if a.choices else None, "required": a.required,
                           "type": getattr(a.type, "__name__", None), "nargs": a.nargs}
    out["parser"] = actions
    out["parser_description"] = parser.description
    return norm(out, tmp)


# --------------------------------------------------------------------------
# Public surface
# --------------------------------------------------------------------------
def snapshot_surface() -> dict:
    names = sorted(n for n in dir(fa) if not (n.startswith("__") and n.endswith("__")))
    classes = {}
    for n in names:
        obj = getattr(fa, n)
        if inspect.isclass(obj) and getattr(obj, "__module__", "") .split(".")[-1] != "builtins" and n in {
                "CrossrefProvider", "UnpaywallProvider", "PmcPdfLocator", "InstitutionalLibraryAuth",
                "CookieNotFoundError", "EZproxyPdfDownloader", "LibKeyNomadProvider", "PdfDownloader",
                "ArxivProvider", "BiorxivProvider"}:
            members = {}
            for m, v in sorted(vars(obj).items()):
                if m.startswith("__") and m.endswith("__") and m != "__init__":
                    continue
                if callable(v) or isinstance(v, (staticmethod, classmethod)):
                    fn = v.__func__ if isinstance(v, (staticmethod, classmethod)) else v
                    try:
                        members[m] = str(inspect.signature(fn))
                    except (TypeError, ValueError):
                        members[m] = "?"
                else:
                    members[m] = (repr(sorted(v)) if isinstance(v, (frozenset, set))
                                  else repr(v) if isinstance(v, (str, int, float, tuple)) else type(v).__name__)
            classes[n] = members
    functions = {}
    for n in names:
        obj = getattr(fa, n)
        if inspect.isfunction(obj):
            functions[n] = str(inspect.signature(obj))
    return norm({"names": names, "classes": classes, "functions": functions}, None)


def build_all(mp, tmp: Path) -> dict:
    """Run every group; `mp` is a pytest MonkeyPatch (undone by the caller)."""
    mp.setattr(socket, "getaddrinfo", lambda *a, **k: (_ for _ in ()).throw(socket.gaierror("no dns")))
    groups = {
        "surface": snapshot_surface(),
        "helpers": snapshot_helpers(),
        "crossref": snapshot_crossref(mp),
        "unpaywall": snapshot_unpaywall(),
        "pmc": snapshot_pmc(),
        "libkey": snapshot_libkey(),
        "arxiv": snapshot_arxiv(mp),
        "biorxiv": snapshot_biorxiv(),
    }
    sub = tmp / "auth"
    sub.mkdir()
    inner = mp.__class__()
    try:
        groups["auth"] = snapshot_auth(inner, sub)
    finally:
        inner.undo()
    sub = tmp / "selenium"
    sub.mkdir()
    inner = mp.__class__()
    try:
        groups["selenium"] = snapshot_selenium(inner, sub)
    finally:
        inner.undo()
    groups.update(pdf_groups(mp, tmp))
    sub = tmp / "cli"
    sub.mkdir()
    inner = mp.__class__()
    try:
        groups["cli"] = snapshot_cli(inner, sub)
    finally:
        inner.undo()
    return groups


def pdf_groups(mp, tmp: Path) -> dict:
    """Groups that need pypdf (identity verdicts on real PDF bytes)."""
    out = {}
    sub = tmp / "identity"
    sub.mkdir()
    out["identity"] = snapshot_identity(sub)
    sub = tmp / "ezproxy"
    sub.mkdir()
    inner = mp.__class__()
    try:
        out["ezproxy"] = snapshot_ezproxy(inner, sub)
    finally:
        inner.undo()
    sub = tmp / "downloader"
    sub.mkdir()
    out["downloader"] = snapshot_downloader(sub)
    return out


PDF_GROUPS = ("identity", "ezproxy", "downloader")
