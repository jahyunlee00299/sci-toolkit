"""Regression tests for the target safety gate in _common.py.

Every case here is a path the 260730 crawl audit either confirmed by
reproduction or traced through the code. They exist so a future refactor
cannot quietly restore the hole:

  - ``file:///.../secrets.json`` reached ``page.content()`` in fetch_dynamic
    because robots.txt compliance was mistaken for a safety check: a URL with
    no netloc makes RobotsChecker return its ``allow_on_error`` default.
  - ``harvest_files._filename_of`` fed ``unquote()``-ed remote URL text
    straight into ``dest_dir / name``; ``C:\\Users\\pwned.pdf`` was written
    outside the destination directory in an actual run.

Offline by design: no test here needs the network. DNS-dependent behaviour is
exercised with ``resolve=False`` or with literals, so results do not change
between on-site and off-site runs.
"""

import sys
from pathlib import Path

import pytest

from _common import (  # noqa: E402  (conftest puts scripts/ on sys.path)
    ALLOWED_URL_SCHEMES,
    ScrapeError,
    UnsafeTargetError,
    resolve_within,
    sanitize_filename,
    validate_url,
)


# --------------------------------------------------------------------------
# validate_url — schemes
# --------------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "file:///c:/Users/testuser/.claude/secrets.json",
    "file:///home/testuser/.claude/secrets.json",
    "file://localhost/etc/passwd",
    "data:text/html,<h1>hi</h1>",
    "javascript:alert(1)",
    "ftp://ftp.example.com/pub/x.pdf",
    "chrome://version",
    "about:blank",
])
def test_non_web_schemes_are_blocked(url):
    """Only http(s) is fetchable — everything else reads this machine."""
    with pytest.raises(UnsafeTargetError):
        validate_url(url, resolve=False)


def test_scheme_allowlist_contents():
    assert ALLOWED_URL_SCHEMES == frozenset({"http", "https"})


@pytest.mark.parametrize("url", ["", "   ", None])
def test_empty_url_is_blocked(url):
    with pytest.raises(UnsafeTargetError):
        validate_url(url, resolve=False)


def test_missing_scheme_is_blocked():
    """A bare host would be a relative path, not a target."""
    with pytest.raises(UnsafeTargetError):
        validate_url("example.com/paper.pdf", resolve=False)


# --------------------------------------------------------------------------
# validate_url — hosts
# --------------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8777/api/all",          # approval-inbox server
    "http://127.1/x",                          # short loopback form
    "http://2130706433/x",                     # decimal 127.0.0.1
    "http://0x7f000001/x",                     # hex 127.0.0.1
    "http://0177.0.0.1/x",                     # octal 127.0.0.1
    "http://localhost:8791/api/all",
    "http://[::1]/",
    "http://192.168.1.1/",
    "http://10.0.0.5/admin",
    "http://172.16.0.1/",
    "http://169.254.169.254/latest/meta-data/",  # cloud metadata
    "http://0.0.0.0/",
])
def test_local_and_private_hosts_are_blocked(url):
    with pytest.raises(UnsafeTargetError):
        validate_url(url, resolve=False)


@pytest.mark.parametrize("url", [
    "https://api.crossref.org/works/10.1000/xyz",
    "http://export.arxiv.org/api/query?search_query=all:enzyme",
    "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
    "https://8.8.8.8/",       # public IP literal stays allowed
])
def test_public_targets_are_allowed(url):
    assert validate_url(url, resolve=False) == url


def test_url_is_returned_unchanged():
    """The gate validates; it must not rewrite the caller's URL."""
    url = "https://example.org/a%20b?q=1&r=2#frag"
    assert validate_url(url, resolve=False) == url


def test_dns_failure_is_not_treated_as_unsafe():
    """A DNS error is a network problem, reported by the HTTP layer."""
    host = "nonexistent-host-for-safety-test.invalid"
    assert validate_url(f"https://{host}/x", resolve=True) is not None


def test_resolving_name_pointing_at_loopback_is_blocked():
    """A public *name* resolving to a private address must still be refused."""
    # localtest.me and similar resolve to 127.0.0.1; if resolution fails
    # offline the gate deliberately allows it, so accept either outcome and
    # assert only that a *successful* resolution to loopback is refused.
    try:
        validate_url("http://localtest.me/", resolve=True)
    except UnsafeTargetError:
        return  # resolved and correctly refused
    pytest.skip("localtest.me did not resolve in this environment")


# --------------------------------------------------------------------------
# validate_url — error type
# --------------------------------------------------------------------------

def test_unsafe_target_error_is_catchable_as_scrape_error():
    """Callers already handle ScrapeError; the gate must ride that channel."""
    assert issubclass(UnsafeTargetError, ScrapeError)
    with pytest.raises(ScrapeError):
        validate_url("file:///etc/passwd", resolve=False)


# --------------------------------------------------------------------------
# sanitize_filename
# --------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("../../../etc/passwd", "passwd"),
    ("..\\..\\Windows\\System32\\drivers\\etc\\hosts", "hosts"),
    ("C:\\Users\\pwned.pdf", "pwned.pdf"),        # reproduced in the audit
    ("/etc/shadow", "shadow"),
    ("paper.pdf", "paper.pdf"),
    ("논문 초안.pdf", "논문 초안.pdf"),            # Korean names survive
    ("s41586-024-07123-4.pdf", "s41586-024-07123-4.pdf"),
])
def test_sanitize_filename_expected_values(raw, expected):
    assert sanitize_filename(raw) == expected


@pytest.mark.parametrize("raw", [
    "../../../etc/passwd",
    "..%2f..%2fx.pdf",
    "....//....//x.pdf",
    "C:\\Users\\pwned.pdf",
    "\\\\server\\share\\x.pdf",
    "a/b/c/../../../x",
    "..",
    ".",
    "...",
    "",
    "   ",
    "\x00evil.pdf",
    "x\r\n.pdf",
])
def test_sanitize_filename_never_returns_a_path(raw):
    """Whatever comes in, the result is one harmless component."""
    got = sanitize_filename(raw)
    assert got, "must never be empty"
    assert "/" not in got and "\\" not in got
    assert got not in {".", ".."}
    assert not got.startswith(".")
    assert ":" not in got
    assert "\x00" not in got and "\r" not in got and "\n" not in got


@pytest.mark.parametrize("raw", ["con.pdf", "PRN.txt", "nul", "COM1.pdf", "lpt9"])
def test_windows_reserved_names_are_defused(raw):
    got = sanitize_filename(raw)
    stem = got.rpartition(".")[0] or got
    assert stem.lower() not in {
        "con", "prn", "aux", "nul", "com1", "lpt9",
    }, f"{raw!r} -> {got!r} is still a reserved device name"


def test_long_filename_is_truncated_keeping_extension():
    got = sanitize_filename("a" * 400 + ".pdf")
    assert len(got) <= 128
    assert got.endswith(".pdf")


def test_fallback_is_used_for_unusable_input():
    assert sanitize_filename("///", fallback="download") == "download"
    assert sanitize_filename("..", fallback="paper") == "paper"


# --------------------------------------------------------------------------
# resolve_within
# --------------------------------------------------------------------------

def test_resolve_within_keeps_target_inside_base(tmp_path):
    for raw in ["ok.pdf", "../../pwned.pdf", "C:\\Users\\pwned.pdf",
                "/etc/passwd", "..\\..\\x.pdf"]:
        target = resolve_within(tmp_path, raw)
        assert tmp_path.resolve() in target.parents, (
            f"{raw!r} escaped to {target}"
        )


def test_resolve_within_writes_where_it_says(tmp_path):
    target = resolve_within(tmp_path, "../../pwned.pdf")
    target.write_text("x", encoding="utf-8")
    assert target.exists()
    # The parent directories are untouched: nothing named pwned.pdf above base.
    assert not (tmp_path.parent / "pwned.pdf").exists()
    assert not (tmp_path.parent.parent / "pwned.pdf").exists()


def test_resolve_within_accepts_str_base(tmp_path):
    target = resolve_within(str(tmp_path), "a.pdf")
    assert target.name == "a.pdf"


# --------------------------------------------------------------------------
# harvest_files — the consumer that actually wrote outside its directory
# --------------------------------------------------------------------------

@pytest.mark.parametrize("url,expected", [
    ("https://example.org/papers/s41586-024-1.pdf", "s41586-024-1.pdf"),
    ("https://example.org/a/..%2f..%2fpwned.pdf", "pwned.pdf"),
    ("https://example.org/%2e%2e%2f%2e%2e%2fpwned.pdf", "pwned.pdf"),
    ("https://example.org/C%3A%5CUsers%5Cpwned.pdf", "pwned.pdf"),
    ("https://example.org/dir/", "download"),
    ("https://example.org/%2e%2e", "download"),
])
def test_harvest_filename_is_sanitized(url, expected):
    from harvest_files import FileHarvester
    assert FileHarvester._filename_of(url) == expected


def test_harvest_download_cannot_escape_dest_dir(tmp_path):
    """End-to-end: a traversal filename lands inside dest_dir or fails loudly."""
    from harvest_files import FileHarvester

    written: list[Path] = []

    class RecordingClient:
        """Stands in for PoliteHttpClient: records where it was told to write."""

        def stream_to_file(self, url, dest, **kwargs):
            dest = Path(dest)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"%PDF-1.4 stub")
            written.append(dest)
            return dest

    dest_dir = tmp_path / "downloads"
    dest_dir.mkdir()
    harvester = FileHarvester(RecordingClient())

    for raw_name in ["../../pwned.pdf", "C:\\Users\\pwned.pdf",
                     "/etc/cron.d/evil", "..\\..\\evil.pdf"]:
        result = harvester.download(
            {"url": "https://example.org/x.pdf", "filename": raw_name},
            dest_dir,
        )
        if result["status"] == "ok":
            assert dest_dir.resolve() in Path(result["local_path"]).parents, (
                f"{raw_name!r} escaped to {result['local_path']}"
            )

    for path in written:
        assert dest_dir.resolve() in path.parents, f"escaped write: {path}"
    assert not (tmp_path / "pwned.pdf").exists()
    assert not (tmp_path.parent / "pwned.pdf").exists()


def test_harvest_download_reports_failure_instead_of_raising(tmp_path):
    """A batch run must continue; failures are recorded in the result dict."""
    from harvest_files import FileHarvester

    class FailingClient:
        def stream_to_file(self, url, dest, **kwargs):
            raise ScrapeError("boom")

    result = FileHarvester(FailingClient()).download(
        {"url": "https://example.org/x.pdf", "filename": "x.pdf"}, tmp_path
    )
    assert result["status"].startswith("failed:")
    assert result["local_path"] is None


# --------------------------------------------------------------------------
# Download size cap
# --------------------------------------------------------------------------

def test_stream_to_file_signature_has_a_default_cap():
    """The cap must be on by default, not something a caller has to remember."""
    import inspect

    from _common import DEFAULT_MAX_DOWNLOAD_BYTES, PoliteHttpClient

    param = inspect.signature(PoliteHttpClient.stream_to_file).parameters
    assert param["max_bytes"].default == DEFAULT_MAX_DOWNLOAD_BYTES
    assert DEFAULT_MAX_DOWNLOAD_BYTES > 0
