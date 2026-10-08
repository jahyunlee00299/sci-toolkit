"""llm_call (optional helper): API path, claude -p fallback, kill switch, log line."""
import json
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import llm_call as L  # noqa: E402


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.delenv("LLM_CALL_API", raising=False)
    monkeypatch.setenv("LLM_CALL_LOG", str(tmp_path / "log.jsonl"))
    return tmp_path / "log.jsonl"


def _ok(url, headers, body, timeout):
    return {"content": [{"type": "text", "text": "PONG"}], "usage": {"input_tokens": 3, "output_tokens": 1}}


def test_api_path(env, monkeypatch):
    monkeypatch.setattr(L, "_http_post", _ok)
    monkeypatch.setattr(L, "_run_cli", lambda *a: pytest.fail("cli must not run"))
    assert L.complete("x") == "PONG"
    assert json.loads(env.read_text(encoding="utf-8").splitlines()[0])["path"] == "api"


def test_no_key_uses_cli(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    monkeypatch.setattr(L, "_http_post", lambda *a: pytest.fail("no api"))
    monkeypatch.setattr(L, "_run_cli", lambda *a: "CLI")
    assert L.complete("x") == "CLI"


def test_http_error_uses_cli(monkeypatch):
    def boom(*a):
        raise urllib.error.HTTPError("u", 400, "credit", {}, None)
    monkeypatch.setattr(L, "_http_post", boom)
    monkeypatch.setattr(L, "_run_cli", lambda *a: "CLI")
    assert L.complete("x") == "CLI"


def test_kill_switch(monkeypatch):
    monkeypatch.setenv("LLM_CALL_API", "0")
    monkeypatch.setattr(L, "_http_post", lambda *a: pytest.fail("no api"))
    monkeypatch.setattr(L, "_run_cli", lambda *a: "CLI")
    assert L.complete("x") == "CLI"


def test_all_paths_fail(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    def no_cli(*a):
        raise L.LLMCallError("no cli")
    monkeypatch.setattr(L, "_run_cli", no_cli)
    with pytest.raises(L.LLMCallError):
        L.complete("x")
    with pytest.raises(L.LLMCallError):
        L.complete("x", allow_cli=False)
