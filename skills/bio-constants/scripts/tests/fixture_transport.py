"""Record/replay transport for biodb.http.TRANSPORT (public API responses only)."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

FIXDIR = Path(__file__).parent / "fixtures"


def _path(url: str) -> Path:
    return FIXDIR / (hashlib.sha1(url.encode()).hexdigest()[:16] + ".json")


def save(url: str, status: int, headers: dict, body: bytes) -> None:
    FIXDIR.mkdir(exist_ok=True)
    _path(url).write_text(json.dumps({
        "url": url, "status": status,
        "headers": {k: v for k, v in headers.items() if k in ("location", "content-type")},
        "body_b64": base64.b64encode(body).decode()}, indent=1), encoding="utf-8")


def replay(url: str, headers: dict, timeout: float):
    p = _path(url)
    if not p.exists():
        raise AssertionError(f"no fixture for {url}")
    d = json.loads(p.read_text(encoding="utf-8"))
    return d["status"], d["headers"], base64.b64decode(d["body_b64"])


def recorder(real):
    def _rec(url, headers, timeout):
        st, h, body = real(url, headers, timeout)
        save(url, st, h, body)
        return st, h, body
    return _rec
