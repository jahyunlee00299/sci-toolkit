"""Regression tests: an upstream GitHub failure must not read as "no new items".

The 260730 audit traced a two-step disguise:

  - ``fetch_github.run_fields`` caught every ``HTTPStatusError`` — including 401
    and 403 — and turned it into ``{"n": 0, "repos": [], "error": "HTTP 401"}``,
    then ``main`` returned 0 regardless.
  - ``github_monitor.sh``'s digest reader skipped any field with no repos and
    never looked at the ``error`` key, so the output said "no new items since
    last run".

Net effect: an expired PAT rendered identically to a quiet day, on a job that
runs daily by cron. Nobody would notice until someone asked why nothing had been
found for a while.

The distinction these tests pin:
  - 422 (one malformed query) stays a per-field skip — one bad qualifier must not
    kill the run.
  - 401 / 403 (credential or quota) escalates, because it will hit every field
    identically; a per-field record would be repeated noise, not information.
"""

import sys

import httpx
import pytest

import fetch_github  # noqa: E402
from _common import ScrapeError  # noqa: E402


class _FakeResponse:
    def __init__(self, status_code, message="Bad credentials"):
        self.status_code = status_code
        self._message = message

    def json(self):
        return {"message": self._message}

    @property
    def text(self):
        return self._message


class _FakeClient:
    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


@pytest.fixture
def state():
    return {"fields": {}, "seen_releases": {}, "seen_issues": {}}


@pytest.fixture
def defaults():
    return {"since_days": 7, "min_stars": 1, "limit": 10}


def _patch_search(monkeypatch, status_code):
    def _raise(client, **kwargs):
        raise httpx.HTTPStatusError(
            "boom", request=None, response=_FakeResponse(status_code)
        )
    monkeypatch.setattr(fetch_github, "search_repos", _raise)


@pytest.mark.parametrize("status", [401, 403])
def test_auth_failure_escalates(monkeypatch, state, defaults, status):
    """A credential/quota failure must abort, not become a zero-result field."""
    _patch_search(monkeypatch, status)
    with pytest.raises(ScrapeError) as excinfo:
        fetch_github.run_fields(
            _FakeClient(), [{"name": "f1", "query": "q"}], state, defaults
        )
    message = str(excinfo.value)
    assert str(status) in message
    # The message must name the real cause, so the reader does not go hunting
    # for a missing repo.
    assert "authentication" in message.lower() or "quota" in message.lower()


def test_malformed_query_still_skips(monkeypatch, state, defaults):
    """422 is genuinely per-field: the run continues and records the error."""
    _patch_search(monkeypatch, 422)
    out = fetch_github.run_fields(
        _FakeClient(),
        [{"name": "bad", "query": "q1"}, {"name": "bad2", "query": "q2"}],
        state, defaults,
    )
    assert len(out) == 2
    assert all(field["error"] == "HTTP 422" for field in out)
    assert all(field["n"] == 0 for field in out)


def test_failed_field_is_recorded_not_swallowed(monkeypatch, state, defaults):
    """The error key must exist — the digest now depends on reading it."""
    _patch_search(monkeypatch, 422)
    out = fetch_github.run_fields(
        _FakeClient(), [{"name": "f", "query": "q"}], state, defaults
    )
    assert "error" in out[0]


def test_partial_failure_does_not_exit_zero(monkeypatch, tmp_path, capsys):
    """main() must signal partial failure; it returned 0 unconditionally before."""
    _patch_search(monkeypatch, 422)
    monkeypatch.setattr(fetch_github, "load_state", lambda path: {
        "fields": {}, "seen_releases": {}, "seen_issues": {}})
    monkeypatch.setattr(fetch_github, "save_state", lambda path, state: None)
    monkeypatch.setattr(fetch_github, "load_token", lambda: "tok")

    report = tmp_path / "report.json"
    code = fetch_github.main([
        "--query", "enzyme", "--new",
        "--state", str(tmp_path / "state.json"),
        "-o", str(report),
    ])
    assert code == 3, f"expected exit 3 for a failed field, got {code}"
    # A partial report is still written — it names which field failed.
    assert report.exists()


def test_auth_failure_exits_nonzero_and_writes_no_report(monkeypatch, tmp_path):
    """On 401 no report is written: an empty report is what hid this."""
    _patch_search(monkeypatch, 401)
    monkeypatch.setattr(fetch_github, "load_state", lambda path: {
        "fields": {}, "seen_releases": {}, "seen_issues": {}})
    monkeypatch.setattr(fetch_github, "save_state", lambda path, state: None)
    monkeypatch.setattr(fetch_github, "load_token", lambda: "tok")

    report = tmp_path / "report.json"
    code = fetch_github.main([
        "--query", "enzyme", "--new",
        "--state", str(tmp_path / "state.json"),
        "-o", str(report),
    ])
    assert code == 4, f"expected exit 4 for auth failure, got {code}"
    assert not report.exists(), "a report on auth failure re-creates the disguise"
