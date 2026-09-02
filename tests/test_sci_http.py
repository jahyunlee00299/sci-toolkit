#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Retry policy of scripts/sci_http.py, pinned without a network.

A fake opener scripts the sequence of outcomes (status codes, URLError,
timeout, success) and a fake sleep records the backoff schedule, so every
branch of the policy is an executable case:

  500,500,200 -> success on the 3rd attempt, two sleeps (1.5s, 3.0s)
  404          -> HttpError immediately, no retry, no sleep
  403          -> HttpError immediately (a 4xx will not change on retry)
  429 + Retry-After: 2 -> sleeps 2.0 (header wins over backoff), then succeeds
  URLError x3  -> NetworkError after 3 attempts, 2 sleeps, none after the last
  500 x3       -> HttpError(500, 'retries exhausted')
  get_json: 404 -> (None, 'not_found'); 503 x3 -> (None, 'HTTP 503');
            bad JSON -> (None, 'JSON parse error: ...'); ok -> (dict, None)
  get_text / get_bytes tuple shapes; user_agent with and without email;
  retries=0 rejected; Retry-After capped at MAX_RETRY_AFTER.

Run: python tests/test_sci_http.py
"""
from __future__ import annotations

import importlib.util
import io
import sys
import urllib.error
from pathlib import Path

if sys.platform == "win32":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("sci_http", str(ROOT / "scripts" / "sci_http.py"))
sci_http = importlib.util.module_from_spec(spec)
sys.modules["sci_http"] = sci_http
spec.loader.exec_module(sci_http)

_results: list[tuple[bool, str]] = []


def check(name: str, cond: bool, note: str = "") -> None:
    _results.append((cond, name))
    tag = "[OK]  " if cond else "[FAIL]"
    print(f"  {tag} {name}" + (f"  {note}" if note and not cond else ""))


def section(title: str) -> None:
    print(f"\n== {title}")


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


def make_opener(script: list):
    """script items: int status (>=400 -> HTTPError), bytes (200 body),
    Exception instance (raised), or (status, body, headers) tuple."""
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


def make_sleep():
    slept: list[float] = []
    return (lambda s: slept.append(s)), slept


URL = "https://api.example.org/works/1"

# --------------------------------------------------------------------------
section("request(): retry policy")

op, calls = make_opener([500, 500, b'{"ok":1}'])
sl, slept = make_sleep()
r = sci_http.request(URL, opener=op, sleep=sl)
check("500,500,200 -> success on 3rd attempt", r.status == 200 and r.json() == {"ok": 1})
check("two sleeps with linear backoff 1.5, 3.0", slept == [1.5, 3.0], str(slept))
check("opener called 3 times", len(calls) == 3)

op, calls = make_opener([404])
sl, slept = make_sleep()
try:
    sci_http.request(URL, opener=op, sleep=sl)
    check("404 -> HttpError", False, "no exception")
except sci_http.HttpError as e:
    check("404 -> HttpError immediately", e.status == 404 and len(calls) == 1 and slept == [], f"{e} calls={len(calls)} slept={slept}")

op, calls = make_opener([403])
sl, slept = make_sleep()
try:
    sci_http.request(URL, opener=op, sleep=sl)
    check("403 -> HttpError", False, "no exception")
except sci_http.HttpError as e:
    check("403 -> HttpError, not retried", e.status == 403 and len(calls) == 1, f"calls={len(calls)}")

op, calls = make_opener([(429, b"", {"Retry-After": "2"}), b"ok"])
sl, slept = make_sleep()
r = sci_http.request(URL, opener=op, sleep=sl)
check("429 with Retry-After: 2 -> sleeps 2.0 (header wins), then succeeds", r.status == 200 and slept == [2.0], str(slept))

op, calls = make_opener([(503, b"", {"Retry-After": "600"}), b"ok"])
sl, slept = make_sleep()
sci_http.request(URL, opener=op, sleep=sl)
check("Retry-After capped at MAX_RETRY_AFTER", slept == [sci_http.MAX_RETRY_AFTER], str(slept))

op, calls = make_opener([urllib.error.URLError("timed out")] * 3)
sl, slept = make_sleep()
try:
    sci_http.request(URL, opener=op, sleep=sl)
    check("URLError x3 -> NetworkError", False, "no exception")
except sci_http.NetworkError as e:
    check("URLError x3 -> NetworkError after 3 attempts", len(calls) == 3 and "timed out" in e.reason, f"{e}")
    check("no sleep after the last attempt", len(slept) == 2, str(slept))

op, calls = make_opener([500, 500, 500])
sl, slept = make_sleep()
try:
    sci_http.request(URL, opener=op, sleep=sl)
    check("500 x3 -> HttpError", False, "no exception")
except sci_http.HttpError as e:
    check("500 x3 -> HttpError(500, retries exhausted)", e.status == 500 and "exhausted" in e.reason, f"{e}")

op, calls = make_opener([TimeoutError("socket timeout"), b"ok"])
sl, slept = make_sleep()
r = sci_http.request(URL, opener=op, sleep=sl)
check("socket TimeoutError is retried", r.status == 200 and len(calls) == 2)

try:
    sci_http.request(URL, retries=0, opener=make_opener([b"ok"])[0], sleep=lambda s: None)
    check("retries=0 rejected", False, "no exception")
except ValueError:
    check("retries=0 rejected with ValueError", True)

op, calls = make_opener([b"ok"])
sci_http.request(URL, headers={"X-Test": "1"}, opener=op, sleep=lambda s: None)
check("custom headers reach the request (no crash on Mapping)", calls == [URL])

# --------------------------------------------------------------------------
section("(value, error) conveniences")

v, err = sci_http.get_json(URL, opener=make_opener([404])[0], sleep=lambda s: None)
check("get_json 404 -> (None, 'not_found')", v is None and err == "not_found", f"{v} {err}")
v, err = sci_http.get_json(URL, opener=make_opener([503, 503, 503])[0], sleep=lambda s: None)
check("get_json 503 x3 -> (None, 'HTTP 503')", v is None and err == "HTTP 503", f"{v} {err}")
v, err = sci_http.get_json(URL, opener=make_opener([b"not json"])[0], sleep=lambda s: None)
check("get_json bad body -> (None, 'JSON parse error: ...')", v is None and str(err).startswith("JSON parse error"), f"{v} {err}")
v, err = sci_http.get_json(URL, opener=make_opener([b'{"a": [1, 2]}'])[0], sleep=lambda s: None)
check("get_json ok -> (dict, None)", v == {"a": [1, 2]} and err is None, f"{v} {err}")
v, err = sci_http.get_json(URL, opener=make_opener([urllib.error.URLError("dns")] * 3)[0], sleep=lambda s: None)
check("get_json network failure -> (None, 'URLError: dns')", v is None and err == "URLError: dns", f"{v} {err}")
v, err = sci_http.get_text(URL, opener=make_opener(["café".encode("utf-8")])[0], sleep=lambda s: None)
check("get_text decodes utf-8", v == "café" and err is None, f"{v!r} {err}")
v, err = sci_http.get_bytes(URL, opener=make_opener([b"\x00\x01"])[0], sleep=lambda s: None)
check("get_bytes returns raw bytes", v == b"\x00\x01" and err is None, f"{v!r} {err}")

# --------------------------------------------------------------------------
section("user_agent")

check("with email -> mailto", "mailto:a@b.c" in sci_http.user_agent("ref_fetch", "a@b.c"))
check("without email -> no-contact-provided", "no-contact-provided" in sci_http.user_agent("ref_fetch"))
check("tool name embedded", sci_http.user_agent("si_fetch").startswith("sci-toolkit-si_fetch/"))

# --------------------------------------------------------------------------
n_fail = sum(1 for ok, _ in _results if not ok)
print(f"\nSUMMARY: {len(_results) - n_fail} passed, {n_fail} failed")
sys.exit(1 if n_fail else 0)
