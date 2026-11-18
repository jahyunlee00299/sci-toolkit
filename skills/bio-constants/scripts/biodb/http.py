"""Polite public-GET layer: User-Agent, 1 request/s per host, one retry, 30 s timeout.

The wire call is isolated in ``TRANSPORT`` so tests can substitute recorded fixtures.
Redirects are followed manually so callers can see the chain (merged UniProt accessions).
"""
from __future__ import annotations

import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from .errors import BlindError

USER_AGENT = "biodb-dev/0.1 (research reconciliation; public GET; contact: lab)"
TIMEOUT_S = 30
MIN_INTERVAL_S = 1.0
MAX_REDIRECTS = 5

_last_request: dict[str, float] = {}


@dataclass
class Response:
    status: int
    url: str                      # final URL
    body: bytes
    headers: dict = field(default_factory=dict)
    chain: list = field(default_factory=list)   # [(status, url), ...] redirect hops

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def _wire(url: str, headers: dict, timeout: float):
    """Single real HTTP GET without redirect following -> (status, headers, body)."""
    req = urllib.request.Request(url, headers=headers)
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req, timeout=timeout) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read()
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read()


TRANSPORT = _wire


def _throttle(host: str) -> None:
    wait = MIN_INTERVAL_S - (time.monotonic() - _last_request.get(host, 0.0))
    if wait > 0:
        time.sleep(wait)
    _last_request[host] = time.monotonic()


def _once(url: str, accept: str):
    host = urllib.parse.urlsplit(url).netloc
    hdr = {"User-Agent": USER_AGENT, "Accept": accept}
    last_exc = None
    for attempt in (1, 2):                       # one retry on transport error / 5xx
        _throttle(host)
        try:
            st, h, body = TRANSPORT(url, hdr, TIMEOUT_S)
            if st >= 500 and attempt == 1:
                continue
            return st, h, body
        except Exception as e:                   # noqa: BLE001 - network layer
            last_exc = e
    raise BlindError(f"network failure for {url}: {last_exc}")


def get(url: str, accept: str = "application/json", follow: bool = True) -> Response:
    chain = []
    cur = url
    for _ in range(MAX_REDIRECTS + 1):
        st, h, body = _once(cur, accept)
        if follow and st in (301, 302, 303, 307, 308) and "location" in h:
            chain.append((st, cur))
            cur = urllib.parse.urljoin(cur, h["location"])
            continue
        return Response(st, cur, body, h, chain)
    raise BlindError(f"too many redirects for {url}")
