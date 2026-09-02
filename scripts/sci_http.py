#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sci_http — the one HTTP GET-with-retry used by the tools under scripts/.

Why this exists
---------------
Measured 2026-09-02: six files carried their own ``for attempt in range(...)``
+ ``urlopen`` loop (ref_fetch twice, si_fetch, jcr_batch_verify, and two
skill scripts). They disagreed on what to retry — one retried every non-404
status including 400/401/403, one retried nothing — and each grew its own
error-string format. A fix to one (e.g. honouring ``Retry-After``) reached
none of the others.

Scope
-----
Stdlib only, GET only, for the tools that live in ``scripts/``. Skill folders
under ``skills/`` install stand-alone and cannot import this module, so their
scripts keep a private copy of the loop; that is deliberate, not an oversight.

Contract
--------
* ``request(url, ...)`` returns a ``Response`` or raises ``HttpError`` (a final
  HTTP status) / ``NetworkError`` (no usable response after retries).
* Retried: 429 and 5xx, ``URLError``, timeouts, connection resets. Not
  retried: any other 4xx (a 400/401/403/404 will not change on retry).
* ``Retry-After`` (seconds) is honoured on 429/503 when present, capped.
* Backoff = ``backoff * attempt`` seconds between attempts, none after the
  last one.
* ``get_json`` / ``get_text`` / ``get_bytes`` return the ``(value, error)``
  tuple the tools already use: ``(None, "not_found")`` on 404, ``(None,
  "HTTP 503")`` / ``(None, "URLError: ...")`` on a final failure, ``(value,
  None)`` on success. Error strings keep the formats existing tests pin.
* ``opener`` and ``sleep`` are injectable so the retry policy is testable
  without a network.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional

DEFAULT_TIMEOUT = 20
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF = 1.5
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_RETRY_AFTER = 30.0  # seconds; a server asking for more than this is treated as an outage


class HttpError(Exception):
    """A final (non-retried or retries-exhausted) HTTP status."""

    def __init__(self, status: int, url: str, reason: str = ""):
        super().__init__(f"HTTP {status} for {url}" + (f" ({reason})" if reason else ""))
        self.status = status
        self.url = url
        self.reason = reason


class NetworkError(Exception):
    """No HTTP response at all after retries (DNS, timeout, reset, ...)."""

    def __init__(self, url: str, reason: str):
        super().__init__(f"{reason} for {url}")
        self.url = url
        self.reason = reason


@dataclass
class Response:
    status: int
    body: bytes
    headers: Mapping[str, str]
    url: str

    def text(self, encoding: str = "utf-8") -> str:
        return self.body.decode(encoding, errors="replace")

    def json(self) -> Any:
        return json.loads(self.text())


def user_agent(tool: str, email: Optional[str] = None, version: str = "1.0") -> str:
    """Polite UA the scholarly APIs (CrossRef, OpenAlex, Unpaywall) ask for."""
    if email:
        return f"sci-toolkit-{tool}/{version} (https://github.com/; mailto:{email})"
    return f"sci-toolkit-{tool}/{version} (no-contact-provided)"


def _retry_after_seconds(headers: Mapping[str, str]) -> Optional[float]:
    raw = None
    for k, v in headers.items():
        if k.lower() == "retry-after":
            raw = v
            break
    if raw is None:
        return None
    try:
        return min(float(raw), MAX_RETRY_AFTER)
    except ValueError:
        return None  # HTTP-date form: ignore, fall back to backoff


def request(url: str, *, headers: Optional[Mapping[str, str]] = None,
            timeout: float = DEFAULT_TIMEOUT, retries: int = DEFAULT_RETRIES,
            backoff: float = DEFAULT_BACKOFF,
            opener: Callable[..., Any] = urllib.request.urlopen,
            sleep: Callable[[float], None] = time.sleep) -> Response:
    """GET ``url`` with retry on 429/5xx/network errors. See module docstring."""
    if retries < 1:
        raise ValueError("retries must be >= 1")
    req = urllib.request.Request(url, headers=dict(headers or {}))
    last_reason = ""
    last_status: Optional[int] = None
    for attempt in range(1, retries + 1):
        wait: Optional[float] = None
        try:
            with opener(req, timeout=timeout) as resp:
                body = resp.read()
                status = getattr(resp, "status", None) or resp.getcode()
                hdrs = dict(resp.headers.items()) if hasattr(resp.headers, "items") else {}
                return Response(status=int(status), body=body, headers=hdrs, url=url)
        except urllib.error.HTTPError as e:
            last_status, last_reason = e.code, f"HTTP {e.code}"
            if e.code not in RETRY_STATUSES:
                raise HttpError(e.code, url, str(e.reason)) from e
            hdrs = dict(e.headers.items()) if getattr(e, "headers", None) is not None else {}
            wait = _retry_after_seconds(hdrs)
        except urllib.error.URLError as e:
            last_status, last_reason = None, f"URLError: {e.reason}"
        except (TimeoutError, ConnectionError, OSError) as e:
            last_status, last_reason = None, f"{type(e).__name__}: {e}"
        if attempt < retries:
            sleep(wait if wait is not None else backoff * attempt)
    if last_status is not None:
        raise HttpError(last_status, url, "retries exhausted")
    raise NetworkError(url, last_reason or "unknown_error")


# --------------------------------------------------------------------------
# (value, error) conveniences — the shape the scripts/ tools already return
# --------------------------------------------------------------------------

def _tuple_error(exc: Exception) -> str:
    if isinstance(exc, HttpError):
        return "not_found" if exc.status == 404 else f"HTTP {exc.status}"
    if isinstance(exc, NetworkError):
        return exc.reason
    return f"{type(exc).__name__}: {exc}"


def get_bytes(url: str, **kw: Any) -> tuple[Optional[bytes], Optional[str]]:
    try:
        return request(url, **kw).body, None
    except (HttpError, NetworkError) as exc:
        return None, _tuple_error(exc)


def get_text(url: str, **kw: Any) -> tuple[Optional[str], Optional[str]]:
    try:
        return request(url, **kw).text(), None
    except (HttpError, NetworkError) as exc:
        return None, _tuple_error(exc)


def get_json(url: str, **kw: Any) -> tuple[Optional[Any], Optional[str]]:
    hdrs = dict(kw.pop("headers", None) or {})
    hdrs.setdefault("Accept", "application/json")
    try:
        return request(url, headers=hdrs, **kw).json(), None
    except json.JSONDecodeError as exc:
        return None, f"JSON parse error: {exc}"
    except (HttpError, NetworkError) as exc:
        return None, _tuple_error(exc)
