#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Retry policy of scripts/sci_http.py, pinned without a network — pytest style.

This is the exemplar for converting the script-style checks in tests/ to
pytest: plain ``test_*`` functions with ``assert``, fixtures instead of the
``check()`` accumulator, and no module-level side effects. Both runners
handle it: ``doctor.py`` sniffs ``def test_`` and runs the file under pytest;
``tests/conftest.py`` hands it to pytest's native collector. Run it alone with
``python -m pytest tests/test_sci_http.py -q``.

A fake opener scripts the sequence of outcomes (status codes, URLError,
timeout, success) and a fake sleep records the backoff schedule, so every
branch of the policy is an executable case.
"""
from __future__ import annotations

import importlib.util
import io
import sys
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("sci_http", str(ROOT / "scripts" / "sci_http.py"))
sci_http = importlib.util.module_from_spec(_spec)
sys.modules["sci_http"] = sci_http
_spec.loader.exec_module(sci_http)

URL = "https://api.example.org/works/1"


class _FakeResp:
    def __init__(self, status: int, body: bytes, headers: dict | None = None):
        self.status = status
        self._body = body
        self.headers = headers or {}

    def read(self) -> bytes:
        return self._body

    def getcode(self) -> int:
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _opener(script: list):
    """script items: int status (>=400 -> HTTPError), bytes (200 body),
    Exception instance (raised), or (status, body, headers) tuple.
    Returns (opener, calls)."""
    calls: list[str] = []

    def opener(req, timeout=None):
        calls.append(req.full_url)
        item = script.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, bytes):
            return _FakeResp(200, item)
        if isinstance(item, tuple):
            status, body, hdrs = item
            if status >= 400:
                raise urllib.error.HTTPError(req.full_url, status, "err", hdrs, io.BytesIO(body))
            return _FakeResp(status, body, hdrs)
        if isinstance(item, int):
            raise urllib.error.HTTPError(req.full_url, item, "err", {}, io.BytesIO(b""))
        raise AssertionError(f"bad script item {item!r}")
    return opener, calls


@pytest.fixture
def slept():
    return []


@pytest.fixture
def sleep(slept):
    return slept.append


# --------------------------------------------------------------------------
# request(): retry policy
# --------------------------------------------------------------------------

def test_retries_500_then_succeeds_with_linear_backoff(sleep, slept):
    op, calls = _opener([500, 500, b'{"ok":1}'])
    r = sci_http.request(URL, opener=op, sleep=sleep)
    assert r.status == 200 and r.json() == {"ok": 1}
    assert slept == [1.5, 3.0]
    assert len(calls) == 3


def test_404_raises_immediately_no_retry_no_sleep(sleep, slept):
    op, calls = _opener([404])
    with pytest.raises(sci_http.HttpError) as ei:
        sci_http.request(URL, opener=op, sleep=sleep)
    assert ei.value.status == 404 and len(calls) == 1 and slept == []


def test_403_is_not_retried(sleep):
    op, calls = _opener([403])
    with pytest.raises(sci_http.HttpError) as ei:
        sci_http.request(URL, opener=op, sleep=sleep)
    assert ei.value.status == 403 and len(calls) == 1


def test_429_honours_retry_after_over_backoff(sleep, slept):
    op, _ = _opener([(429, b"", {"Retry-After": "2"}), b"ok"])
    r = sci_http.request(URL, opener=op, sleep=sleep)
    assert r.status == 200 and slept == [2.0]


def test_retry_after_is_capped(sleep, slept):
    op, _ = _opener([(503, b"", {"Retry-After": "600"}), b"ok"])
    sci_http.request(URL, opener=op, sleep=sleep)
    assert slept == [sci_http.MAX_RETRY_AFTER]


def test_urlerror_three_times_is_network_error_with_two_sleeps(sleep, slept):
    op, calls = _opener([urllib.error.URLError("timed out")] * 3)
    with pytest.raises(sci_http.NetworkError) as ei:
        sci_http.request(URL, opener=op, sleep=sleep)
    assert len(calls) == 3 and "timed out" in ei.value.reason
    assert len(slept) == 2, "no sleep after the last attempt"


def test_500_three_times_is_http_error_retries_exhausted(sleep):
    op, _ = _opener([500, 500, 500])
    with pytest.raises(sci_http.HttpError) as ei:
        sci_http.request(URL, opener=op, sleep=sleep)
    assert ei.value.status == 500 and "exhausted" in ei.value.reason


def test_socket_timeout_is_retried(sleep):
    op, calls = _opener([TimeoutError("socket timeout"), b"ok"])
    r = sci_http.request(URL, opener=op, sleep=sleep)
    assert r.status == 200 and len(calls) == 2


def test_retries_zero_rejected():
    with pytest.raises(ValueError):
        sci_http.request(URL, retries=0, opener=_opener([b"ok"])[0], sleep=lambda s: None)


def test_custom_headers_accepted():
    op, calls = _opener([b"ok"])
    sci_http.request(URL, headers={"X-Test": "1"}, opener=op, sleep=lambda s: None)
    assert calls == [URL]


# --------------------------------------------------------------------------
# (value, error) conveniences
# --------------------------------------------------------------------------

@pytest.mark.parametrize("script, expect", [
    ([404], (None, "not_found")),
    ([503, 503, 503], (None, "HTTP 503")),
    ([b'{"a": [1, 2]}'], ({"a": [1, 2]}, None)),
    ([urllib.error.URLError("dns")] * 3, (None, "URLError: dns")),
])
def test_get_json_tuple_shapes(script, expect):
    assert sci_http.get_json(URL, opener=_opener(script)[0], sleep=lambda s: None) == expect


def test_get_json_bad_body_is_parse_error():
    v, err = sci_http.get_json(URL, opener=_opener([b"not json"])[0], sleep=lambda s: None)
    assert v is None and str(err).startswith("JSON parse error")


def test_get_text_decodes_utf8():
    assert sci_http.get_text(URL, opener=_opener(["café".encode("utf-8")])[0], sleep=lambda s: None) == ("café", None)


def test_get_bytes_returns_raw():
    assert sci_http.get_bytes(URL, opener=_opener([b"\x00\x01"])[0], sleep=lambda s: None) == (b"\x00\x01", None)


# --------------------------------------------------------------------------
# user_agent
# --------------------------------------------------------------------------

def test_user_agent_with_email_has_mailto():
    assert "mailto:a@b.c" in sci_http.user_agent("ref_fetch", "a@b.c")


def test_user_agent_without_email():
    ua = sci_http.user_agent("si_fetch")
    assert "no-contact-provided" in ua and ua.startswith("sci-toolkit-si_fetch/")
