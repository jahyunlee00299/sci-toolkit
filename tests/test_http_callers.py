"""Root-level HTTP callers after the move onto scripts/sci_http.py -- pytest style.

The REST connectors (asana/github/notion/notion_db), connectors/_google_auth.py and
scripts/ref_fetch.py used to call urllib directly. These tests drive each of them
against a throw-away server on 127.0.0.1 (no outside network, so they are not
marked `network` and run under `doctor.py --offline` too) and pin the semantics
that must not change:

  * a write (POST/PATCH/DELETE) is attempted exactly ONCE on a 5xx (never replayed);
  * the per-status error messages and the response-body excerpt survive;
  * a refused connection / timeout ends in the caller's own "network" message
    quickly, with no retry loop for the connectors;
  * ref_fetch keeps its retry count on 5xx but no longer retries a 4xx (403)
    and still treats 404 as not_found / HTTP 404.
"""
from __future__ import annotations

import importlib
import json
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "connectors"))

HITS: dict[str, int] = {}
PDF = b"%PDF-1.4\n" + b"0" * 64
BIB = "@article{k, title={café}}".encode("utf-8")


class _H(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silence
        pass

    def _serve(self):
        n = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(n)
        path = self.path.split("?")[0]
        HITS[path] = HITS.get(path, 0) + 1
        code, ctype, body = {
            "/ok": (200, "application/json", json.dumps({"data": {"gid": "1"}}).encode()),
            "/empty": (204, "application/json", b""),
            "/401": (401, "application/json", b"{}"),
            "/403": (403, "application/json", b"{}"),
            "/404": (404, "application/json", b"{}"),
            "/400": (400, "application/json", b'{"message":"bad prop"}'),
            "/503": (503, "application/json", b'{"message":"down"}'),
            "/invalid_grant": (400, "application/json", b'{"error":"invalid_grant"}'),
            "/pdf": (200, "Application/PDF", PDF),
            "/landing": (200, "text/html", b"<!DOCTYPE html><html>login</html>"),
        }.get("/" + path.split("/")[1], (404, "text/plain", b""))
        if path.startswith("/slow"):
            time.sleep(0.8)
            code, ctype, body = 200, "application/json", b"{}"
        if path.startswith("/crossref/") and path.endswith("x-bibtex"):
            code, ctype, body = 200, "application/x-bibtex", BIB
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except OSError:
            pass

    do_GET = do_POST = do_PATCH = do_PUT = do_DELETE = _serve


@pytest.fixture(scope="module")
def base():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


@pytest.fixture(autouse=True)
def _reset_hits():
    HITS.clear()


@pytest.fixture
def dead_base():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()  # nothing listens here any more -> connection refused
    return f"http://127.0.0.1:{port}"


def _short_timeout(monkeypatch, mod, seconds=0.2):
    real = mod.sci_http.request

    def fast(*a, **k):
        k["timeout"] = seconds
        return real(*a, **k)

    monkeypatch.setattr(mod.sci_http, "request", fast)


CONNECTORS = [
    ("asana_connector", "Asana API error 503", "asana.token"),
    ("github_connector", "GitHub API error 503", "github.token"),
    ("notion_connector", "Notion API error 503", "notion.token"),
    ("notion_db_connector", "Notion API error 503", "notion.token"),
]


@pytest.mark.parametrize("name,msg503,tokname", CONNECTORS)
def test_connector_success_and_empty_body(base, name, msg503, tokname):
    mod = importlib.import_module(name)
    assert mod.http("GET", base + "/ok", "tok-secret") == {"data": {"gid": "1"}}
    assert mod.http("DELETE", base + "/empty", "tok-secret") == {}


@pytest.mark.parametrize("name,msg503,tokname", CONNECTORS)
def test_connector_write_on_503_is_attempted_once(base, name, msg503, tokname):
    mod = importlib.import_module(name)
    for method in ("POST", "PATCH", "DELETE"):
        HITS.clear()
        with pytest.raises(SystemExit) as ei:
            mod.http(method, base + "/503", "tok-secret", data={"a": 1} if method != "DELETE" else None)
        assert msg503 in str(ei.value.code) and "down" in str(ei.value.code)
        assert HITS["/503"] == 1, f"{method} was replayed"


@pytest.mark.parametrize("name,msg503,tokname", CONNECTORS)
def test_connector_status_messages_and_token_masking(base, name, msg503, tokname):
    mod = importlib.import_module(name)
    with pytest.raises(SystemExit) as ei:
        mod.http("GET", base + "/401", "tok-secret-1234567890")
    text = str(ei.value.code)
    assert "Authentication failed (401)" in text and tokname in text
    assert "tok-secret-1234567890" not in text  # masked
    with pytest.raises(SystemExit) as ei:
        mod.http("GET", base + "/403", "t")
    assert "403" in str(ei.value.code)
    with pytest.raises(SystemExit) as ei:
        mod.http("GET", base + "/404", "t")
    assert "404" in str(ei.value.code)


def test_notion_db_400_includes_response_detail(base):
    mod = importlib.import_module("notion_db_connector")
    with pytest.raises(SystemExit) as ei:
        mod.http("POST", base + "/400", "t", data={})
    assert "bad prop" in str(ei.value.code)


@pytest.mark.parametrize("name,msg503,tokname", CONNECTORS)
def test_connector_connection_refused_fails_fast_with_network_message(dead_base, name, msg503, tokname):
    mod = importlib.import_module(name)
    t0 = time.time()
    with pytest.raises(SystemExit) as ei:
        mod.http("GET", dead_base + "/ok", "t")
    assert "Check your network connection" in str(ei.value.code)
    assert time.time() - t0 < 5  # one attempt, no backoff loop


@pytest.mark.parametrize("name,msg503,tokname", CONNECTORS)
def test_connector_timeout_is_a_clean_exit_not_a_traceback(base, monkeypatch, name, msg503, tokname):
    mod = importlib.import_module(name)
    _short_timeout(monkeypatch, mod)
    with pytest.raises(SystemExit) as ei:
        mod.http("GET", base + "/slow", "t")
    assert "Check your network connection" in str(ei.value.code)
    assert HITS["/slow"] == 1


def test_google_auth_get_post_and_errors(base):
    g = importlib.import_module("_google_auth")
    assert g.api_get(base + "/ok", "tok", {"q": "1"}) == {"data": {"gid": "1"}}
    assert g.api_post(base + "/empty", "tok", {"a": 1}, method="PATCH") == {}
    with pytest.raises(SystemExit) as ei:
        g.api_get(base + "/503", "tok")
    assert "HTTP 503" in str(ei.value.code) and HITS["/503"] == 1
    with pytest.raises(SystemExit) as ei:
        g.api_post(base + "/403", "tok", {})
    assert "A read-only scope cannot write" in str(ei.value.code) and HITS["/403"] == 1
    HITS.clear()
    with pytest.raises(SystemExit) as ei:
        g.api_post(base + "/503", "tok", {})
    assert "API write failed (HTTP 503)" in str(ei.value.code) and HITS["/503"] == 1
    with pytest.raises(SystemExit) as ei:
        g._post_form(base + "/invalid_grant", {"grant_type": "refresh_token"})
    assert "invalid_grant" in str(ei.value.code) and "Reissue" in str(ei.value.code)


def test_google_auth_refused_connection_message(dead_base):
    g = importlib.import_module("_google_auth")
    with pytest.raises(SystemExit) as ei:
        g.api_get(dead_base + "/ok", "tok")
    assert "Could not connect to the Google API" in str(ei.value.code)
    with pytest.raises(SystemExit) as ei:
        g._post_form(dead_base + "/ok", {})
    assert "Could not connect to the token server" in str(ei.value.code)


@pytest.fixture
def rf(monkeypatch):
    mod = importlib.import_module("ref_fetch")
    monkeypatch.setattr(mod, "_RETRY_BACKOFF", 0)
    return mod


def test_ref_fetch_pdf_ok_html_landing_and_status_handling(base, rf, tmp_path):
    ok, err = rf._download_pdf(base + "/pdf", tmp_path / "a" / "x.pdf", None)
    assert ok and err is None and (tmp_path / "a" / "x.pdf").read_bytes() == PDF  # mixed-case header handled
    ok, err = rf._download_pdf(base + "/landing", tmp_path / "y.pdf", None)
    assert not ok and "response is not a PDF" in err and not (tmp_path / "y.pdf").exists()
    ok, err = rf._download_pdf(base + "/404", tmp_path / "z.pdf", None)
    assert (ok, err) == (False, "HTTP 404") and HITS["/404"] == 1
    # 5xx keeps the full retry budget
    ok, err = rf._download_pdf(base + "/503", tmp_path / "z.pdf", None)
    assert (ok, err) == (False, "HTTP 503") and HITS["/503"] == rf._MAX_RETRIES
    # a blocked publisher (403) used to be retried pointlessly; now once
    ok, err = rf._download_pdf(base + "/403", tmp_path / "z.pdf", None)
    assert (ok, err) == (False, "HTTP 403") and HITS["/403"] == 1


def test_ref_fetch_pdf_timeout_and_refused(base, dead_base, rf, tmp_path):
    ok, err = rf._download_pdf(base + "/slow", tmp_path / "t.pdf", None, timeout=0.2)
    assert not ok and err and HITS["/slow"] == rf._MAX_RETRIES
    ok, err = rf._download_pdf(dead_base + "/pdf", tmp_path / "t.pdf", None)
    assert not ok and err.startswith("URLError")


def test_ref_fetch_bibtex_ok_not_found_and_5xx(base, rf, monkeypatch):
    monkeypatch.setattr(rf, "CROSSREF_BASE", base + "/crossref")
    txt, err = rf.fetch_bibtex("10.1/abc", None)
    assert err is None and "café" in txt
    monkeypatch.setattr(rf, "CROSSREF_BASE", base + "/404")
    assert rf.fetch_bibtex("10.1/abc", None) == (None, "not_found")
    monkeypatch.setattr(rf, "CROSSREF_BASE", base + "/503")
    HITS.clear()
    txt, err = rf.fetch_bibtex("10.1/abc", None)
    assert txt is None and err == "HTTP 503"
    assert sum(HITS.values()) == rf._MAX_RETRIES


def test_ref_fetch_bibtex_timeout(base, rf, monkeypatch):
    monkeypatch.setattr(rf, "CROSSREF_BASE", base + "/slow")
    monkeypatch.setattr(rf, "_TIMEOUT", 0.2)
    txt, err = rf.fetch_bibtex("x", None)
    assert txt is None and err


def test_offline_env_does_not_change_caller_behaviour(dead_base, monkeypatch):
    # SCI_TOOLKIT_OFFLINE only gates the tests' network probes (conftest / doctor);
    # no migrated caller ever read it, so setting it must not alter a caller.
    monkeypatch.setenv("SCI_TOOLKIT_OFFLINE", "1")
    mod = importlib.import_module("github_connector")
    with pytest.raises(SystemExit) as ei:
        mod.http("GET", dead_base + "/ok", "t")
    assert "Check your network connection" in str(ei.value.code)


def test_no_direct_urlopen_left_in_root_code():
    offenders = []
    files = [ROOT / "doctor.py"]
    for d in ("scripts", "doctor_lib", "install", "evals"):
        files += (ROOT / d).rglob("*.py")
    for p in files:
        if p.name == "sci_http.py":
            continue
        if "urlopen(" in p.read_text(encoding="utf-8", errors="replace"):
            offenders.append(str(p.relative_to(ROOT)))
    assert not offenders, f"route HTTP through scripts/sci_http.py: {offenders}"
