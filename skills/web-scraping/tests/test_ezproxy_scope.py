"""Regression tests for the EZproxy credential + identity gates.

Three findings from the 260730 crawl audit are pinned here.

1. Cookie scope (fetch_academic.py:914 / :995). ``httpx.Client(cookies=<mapping>)``
   registers each cookie with an empty domain, and httpx then attaches it to any
   host — measured on httpx 0.28.1: an ``EZPROXY_SESSION`` value was sent to
   ``evil.example.net``. Both call sites used ``follow_redirects=True`` with a
   PDF URL scraped out of page HTML, so an institutional credential could leave
   for an unrelated server. That is a library-access-policy violation as much as
   a security bug.

2. Placeholder configuration (fetch_academic.py:769). ``PROXY_BASE`` defaulted to
   ``ezproxy.your-institution.edu`` and nothing checked it, so with
   ``EZPROXY_BASE`` unset requests were assembled against a non-existent host and
   the failure was reported as an ordinary "PDF URL not resolved" — the same
   message a genuinely unavailable paper produces.

3. Identity gate asymmetry (fetch_academic.py:1004). Sources 1-3 must clear
   ``verify_pdf_identity`` before reporting "ok"; the EZproxy path checked only
   ``size >= 1024``, which any paywall or SSO page clears.

Offline by design: no network access, no cookie file, no real proxy.
"""

import warnings
from pathlib import Path

import pytest

from _common import ScrapeError  # noqa: E402
from fetch_academic import EZproxyPdfDownloader  # noqa: E402

REAL_BASE = "https://ezproxy.example.edu/link.n2s?url="


@pytest.fixture
def configured(monkeypatch):
    """A downloader whose PROXY_BASE is a real (non-placeholder) host."""
    monkeypatch.setattr(EZproxyPdfDownloader, "PROXY_BASE", REAL_BASE)
    return EZproxyPdfDownloader()


def _cookie_header(jar, url):
    """The Cookie header httpx would actually send to ``url``."""
    import httpx

    request = httpx.Request("GET", url)
    jar.set_cookie_header(request)
    return request.headers.get("cookie")


# --------------------------------------------------------------------------
# 1. Cookie scope
# --------------------------------------------------------------------------

def test_bare_mapping_leaks_to_any_host():
    """Documents the defect being fixed, so the fix cannot be misread as noise."""
    import httpx

    leaky = httpx.Cookies({"EZPROXY_SESSION": "SECRET"})
    assert _cookie_header(leaky, "https://evil.example.net/x") is not None


def test_cookie_jar_is_bound_to_the_proxy_host(configured, monkeypatch):
    monkeypatch.setattr(
        EZproxyPdfDownloader, "_get_cookie_dict",
        lambda self: {"EZPROXY_SESSION": "SECRET"},
    )
    jar = configured._cookie_jar("ezproxy.example.edu")

    # Sent where it belongs: the proxy itself and the publisher hosts EZproxy
    # rewrites into its own domain.
    assert _cookie_header(jar, "https://ezproxy.example.edu/x") is not None
    assert _cookie_header(
        jar, "https://pubs-acs-org-ssl.ezproxy.example.edu/doi/pdf/10.1/x"
    ) is not None

    # Withheld everywhere else.
    for url in ["https://evil.example.net/x",
                "http://127.0.0.1:8777/api/all",
                "https://www.nature.com/articles/x.pdf",
                "https://ezproxy.example.edu.evil.net/x"]:
        assert _cookie_header(jar, url) is None, f"cookie leaked to {url}"


# --------------------------------------------------------------------------
# 2. Placeholder configuration
# --------------------------------------------------------------------------

def test_placeholder_base_is_refused():
    downloader = EZproxyPdfDownloader()   # default PROXY_BASE = placeholder
    with pytest.raises(ScrapeError) as excinfo:
        downloader._require_configured()
    assert "not configured" in str(excinfo.value)


def test_placeholder_download_reports_configuration_not_absence(tmp_path):
    """The status must say "not configured", never look like "paper missing"."""
    downloader = EZproxyPdfDownloader()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = downloader.download("10.1234/x", tmp_path / "out.pdf")
    assert result["downloaded_path"] is None
    assert "not configured" in result["download_status"]
    assert "not resolved" not in result["download_status"]


def test_configured_base_is_accepted(configured):
    assert configured._require_configured() == "ezproxy.example.edu"


# --------------------------------------------------------------------------
# 3. Extracted-link host gating
# --------------------------------------------------------------------------

@pytest.mark.parametrize("url,accepted", [
    ("https://pubs-acs-org-ssl.ezproxy.example.edu/doi/pdf/10.1/x", True),
    ("https://ezproxy.example.edu/pdf/x", True),
    ("https://www.nature.com/articles/x.pdf", True),        # SUBSCRIBED_DOMAINS
    ("https://onlinelibrary.wiley.com/doi/pdf/10.1/x", True),
    ("https://evil.example.net/x.pdf", False),
    ("https://ezproxy.example.edu.evil.net/x.pdf", False),   # suffix trick
    ("file:///c:/Users/testuser/.claude/secrets.json", False),
    ("http://127.0.0.1:8777/x.pdf", False),
    ("http://169.254.169.254/latest/meta-data/", False),
    (None, False),
    ("", False),
])
def test_extracted_pdf_link_host_gating(configured, url, accepted):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        got = configured._accept_pdf_url(url, "ezproxy.example.edu")
    assert (got is not None) is accepted, f"{url!r} -> {got!r}"


def test_rejected_link_warns_so_it_is_diagnosable(configured):
    with pytest.warns(UserWarning):
        configured._accept_pdf_url("https://evil.example.net/x.pdf",
                                   "ezproxy.example.edu")


# --------------------------------------------------------------------------
# 4. Identity gate on the EZproxy path
# --------------------------------------------------------------------------

def test_ezproxy_download_accepts_expected_record():
    """The gate is only real if the caller can pass identity criteria."""
    import inspect

    params = inspect.signature(EZproxyPdfDownloader.download).parameters
    assert "expected" in params, (
        "download() must accept `expected`, otherwise verify_pdf_identity can "
        "only check magic bytes"
    )


def test_pdf_downloader_passes_expected_to_ezproxy():
    """AST check on the call site — the audit finding was an unpassed argument."""
    import ast

    source = Path(__file__).resolve().parent.parent / "scripts" / "fetch_academic.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))

    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "download"
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == "_ezproxy"
    ]
    assert calls, "no self._ezproxy.download(...) call site found"
    for call in calls:
        passed = {kw.arg for kw in call.keywords if kw.arg}
        assert "expected" in passed, (
            f"line {call.lineno}: identity criteria not passed to EZproxy "
            f"download; the gate would only see magic bytes"
        )


def test_filenames_are_sanitized_at_every_source():
    """first_author / year are as untrusted as the DOI, which was sanitized."""
    import ast

    source = Path(__file__).resolve().parent.parent / "scripts" / "fetch_academic.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))

    # Every f-string that builds a *.pdf filename must be wrapped in
    # sanitize_filename(...). Find bare assignments of the form
    # `<name>_filename = f"..."` which is how the unsanitized versions read.
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            if not target.id.endswith("filename"):
                continue
            if isinstance(node.value, ast.JoinedStr):   # raw f-string
                offenders.append((node.lineno, target.id))
    assert not offenders, (
        f"filenames built from untrusted record fields without "
        f"sanitize_filename: {offenders}"
    )
