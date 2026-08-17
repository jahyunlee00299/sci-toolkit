#!/usr/bin/env python3
"""fetch_github.py — GitHub repo *discovery and monitoring* via the official REST API.

A 5th mode for the web-scraping skill, dedicated to GitHub. Unlike the HTML
scrapers, this talks only to the GitHub REST API (https://api.github.com),
so robots.txt / page rendering are irrelevant. It uses GITHUB_PAT from
~/.secrets/secrets.json for the 5000 req/h authenticated rate limit
(unauthenticated is 60/h and unusable for monitoring).

Not a duplicate of `scripts/connectors/github_connector.py`: that connector
reads/writes issues, PRs, and a specific repo's metadata for a repo you
already know. This script is for *discovery* — finding new/trending repos
matching a search query, or diffing a watchlist's releases/issues over time.
Use the connector for "what's happening in repo X"; use this for "what's out
there matching query Y".

Signals supported
-----------------
- new      : newly-created repositories matching a field query
             (search/repositories?q=... created:>DATE)
- trending : recently-created repos sorted by stars (a stars-based proxy,
             since GitHub has no official trending API)
- watch    : new releases / recent issues for a watchlist of repos
             (diffed against the previous run so only *new* items surface)

Design notes
------------
- Stateful "new since last run": a small state file (--state) stores the last
  run timestamp per field and the set of release/issue ids already seen, so
  repeated runs emit only the delta. This is what makes it a *monitor* rather
  than a one-shot search.
- Output mirrors the rest of the skill: a JSON envelope with `provenance`
  + `data`. Written to -o or stdout.
- Config-driven: pass --config a JSON file describing fields + watchlist, or
  use --query / --repo for ad-hoc one-offs.

Examples
--------
    # ad-hoc: enzyme-engineering repos created in the last 7 days, by stars
    python fetch_github.py --new --query "enzyme engineering OR biocatalysis" \
        --since-days 7 --min-stars 1 -n 20

    # trending: any repo created in last 3 days with >100 stars
    python fetch_github.py --trending --since-days 3 --min-stars 100 -n 30

    # watchlist releases/issues, delta vs last run
    python fetch_github.py --watch --repo anthropics/claude-code \
        --repo BioSTEAMDevelopmentGroup/biosteam --state ~/.cache/gh_monitor_state.json

    # config-driven full monitor (fields + watchlist in one file)
    python fetch_github.py --config monitor_config.json \
        --state gh_state.json -o report.json
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import quote, urlencode

try:
    import httpx
except ImportError:  # pragma: no cover
    sys.stderr.write("httpx is required: pip install -r requirements.txt\n")
    raise SystemExit(1)

# This module talks to the GitHub API directly rather than through
# PoliteHttpClient (robots.txt does not govern an authenticated REST API), but it
# shares the error type so callers can handle failures from any fetch_* script
# uniformly.
from _common import ScrapeError  # noqa: E402

API_ROOT = "https://api.github.com"
TOOL = "web-scraping-skill/fetch_github/1.0"
SECRETS_PATH = Path.home() / ".secrets" / "secrets.json"


# --------------------------------------------------------------------------- #
# Auth + HTTP
# --------------------------------------------------------------------------- #
def load_token() -> Optional[str]:
    """Read GITHUB_PAT from ~/.secrets/secrets.json, or env GITHUB_PAT/GH_TOKEN."""
    for env_key in ("GITHUB_PAT", "GH_TOKEN", "GITHUB_TOKEN"):
        if os.environ.get(env_key):
            return os.environ[env_key]
    try:
        data = json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
        return data.get("GITHUB_PAT") or data.get("GH_TOKEN")
    except (OSError, json.JSONDecodeError):
        return None


class GitHubClient:
    """Thin authenticated GitHub REST client with rate-limit awareness."""

    def __init__(self, token: Optional[str], timeout: float = 30.0) -> None:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "web-scraping-skill (github monitor)",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.authenticated = bool(token)
        self._client = httpx.Client(headers=headers, timeout=timeout,
                                    follow_redirects=True)

    def __enter__(self) -> "GitHubClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self._client.close()

    def get(self, path: str, params: Optional[Dict[str, Any]] = None,
            max_retries: int = 3) -> Any:
        url = path if path.startswith("http") else f"{API_ROOT}{path}"
        for attempt in range(max_retries + 1):
            resp = self._client.get(url, params=params)
            # primary + secondary rate limits both signalled here
            if resp.status_code == 403 and "rate limit" in resp.text.lower():
                reset = resp.headers.get("X-RateLimit-Reset")
                wait = _reset_wait(reset)
                if attempt < max_retries and wait <= 90:
                    sys.stderr.write(f"[rate-limit] sleeping {wait}s...\n")
                    time.sleep(wait)
                    continue
                raise RuntimeError(
                    f"GitHub rate limit hit (reset in ~{wait}s). "
                    "Authenticated requests get 5000/h; check GITHUB_PAT."
                )
            if resp.status_code in (502, 503) and attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            return resp.json()
        raise RuntimeError(f"GET {url} failed after retries")


def _reset_wait(reset_header: Optional[str]) -> int:
    if not reset_header:
        return 60
    try:
        reset = int(reset_header)
        now = int(time.time())
        return max(1, reset - now + 1)
    except (TypeError, ValueError):
        return 60


# --------------------------------------------------------------------------- #
# State (delta tracking)
# --------------------------------------------------------------------------- #
def load_state(path: Optional[Path]) -> Dict[str, Any]:
    if path and path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return {"fields": {}, "seen_releases": {}, "seen_issues": {}}


def save_state(path: Optional[Path], state: Dict[str, Any]) -> None:
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False),
                    encoding="utf-8")


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _since_date(since_days: int) -> str:
    d = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=since_days)
    return d.strftime("%Y-%m-%d")


# --------------------------------------------------------------------------- #
# Signal: new / trending repositories (search API)
# --------------------------------------------------------------------------- #
def _repo_record(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "full_name": item.get("full_name"),
        "html_url": item.get("html_url"),
        "description": item.get("description"),
        "language": item.get("language"),
        "stars": item.get("stargazers_count"),
        "forks": item.get("forks_count"),
        "topics": item.get("topics", []),
        "created_at": item.get("created_at"),
        "pushed_at": item.get("pushed_at"),
        "owner": (item.get("owner") or {}).get("login"),
    }


def search_repos(client: GitHubClient, query: str, since_days: int,
                 min_stars: int, limit: int,
                 sort: str = "stars", mode: str = "new") -> List[Dict[str, Any]]:
    """search/repositories filtered by recency + optional stars floor.

    mode="new"      -> created:>DATE  (newly-created repos)
    mode="trending" -> pushed:>DATE   (recently-active repos of ANY creation
                       date). Key difference: an established tool that only
                       just surged is NOT newly-created, so a created:> filter
                       drops it entirely; pushed:> catches it.
    """
    q = query.strip()
    qualifier = "pushed" if mode == "trending" else "created"
    q += f" {qualifier}:>{_since_date(since_days)}"
    if min_stars > 0:
        q += f" stars:>={min_stars}"
    params = {"q": q, "sort": sort, "order": "desc",
              "per_page": min(limit, 100)}
    data = client.get("/search/repositories", params=params)
    items = data.get("items", [])[:limit]
    return [_repo_record(it) for it in items]


# --------------------------------------------------------------------------- #
# Signal: watchlist releases / issues (delta)
# --------------------------------------------------------------------------- #
def watch_releases(client: GitHubClient, repo: str, state: Dict[str, Any],
                   limit: int = 5) -> List[Dict[str, Any]]:
    seen = set(state["seen_releases"].get(repo, []))
    try:
        rels = client.get(f"/repos/{repo}/releases", params={"per_page": limit})
    except httpx.HTTPStatusError as exc:
        return [{"repo": repo, "error": f"releases: {exc.response.status_code}"}]
    fresh = []
    for r in rels:
        rid = str(r.get("id"))
        if rid in seen:
            continue
        seen.add(rid)
        fresh.append({
            "repo": repo, "tag": r.get("tag_name"), "name": r.get("name"),
            "url": r.get("html_url"), "published_at": r.get("published_at"),
            "prerelease": r.get("prerelease"),
        })
    state["seen_releases"][repo] = sorted(seen)
    return fresh


def watch_issues(client: GitHubClient, repo: str, state: Dict[str, Any],
                 limit: int = 10) -> List[Dict[str, Any]]:
    seen = set(state["seen_issues"].get(repo, []))
    try:
        issues = client.get(
            f"/repos/{repo}/issues",
            params={"state": "open", "sort": "created", "direction": "desc",
                    "per_page": limit},
        )
    except httpx.HTTPStatusError as exc:
        return [{"repo": repo, "error": f"issues: {exc.response.status_code}"}]
    fresh = []
    for it in issues:
        if it.get("pull_request"):  # /issues includes PRs; skip them
            continue
        iid = str(it.get("id"))
        if iid in seen:
            continue
        seen.add(iid)
        fresh.append({
            "repo": repo, "number": it.get("number"), "title": it.get("title"),
            "url": it.get("html_url"), "created_at": it.get("created_at"),
            "labels": [l.get("name") for l in it.get("labels", [])],
        })
    state["seen_issues"][repo] = sorted(seen)
    return fresh


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def run_fields(client: GitHubClient, fields: List[Dict[str, Any]],
               state: Dict[str, Any], defaults: Dict[str, Any]
               ) -> List[Dict[str, Any]]:
    out = []
    for fld in fields:
        name = fld.get("name", fld.get("query", "?"))
        try:
            repos = search_repos(
                client,
                query=fld["query"],
                since_days=fld.get("since_days", defaults["since_days"]),
                min_stars=fld.get("min_stars", defaults["min_stars"]),
                limit=fld.get("limit", defaults["limit"]),
                sort=fld.get("sort", "stars"),
                mode=fld.get("mode", "new"),
            )
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            try:
                detail = (exc.response.json().get("message", "") or "")[:80]
            except Exception:
                detail = (exc.response.text or "")[:80]

            # An auth/quota failure is NOT a per-field problem: it will hit every
            # remaining field identically, and returning {"n": 0, "repos": []}
            # for each one renders as "no new items" in the digest — an expired
            # PAT looked exactly like a quiet day (260730 audit). Fail the run.
            if status in (401, 403):
                raise ScrapeError(
                    f"GitHub authentication/quota failure (HTTP {status}) on "
                    f"field '{name}': {detail}\n"
                    f"This is a credential or rate-limit problem, not an empty "
                    f"result — check GITHUB_TOKEN / GH_TOKEN validity."
                ) from exc

            # A genuinely per-field error (e.g. 422 invalid qualifier) must not
            # kill the run, but it is recorded so downstream can surface it.
            sys.stderr.write(
                f"[skip] field '{name}': HTTP {status} ({detail})\n")
            out.append({"field": name, "query": fld["query"],
                        "n": 0, "repos": [],
                        "error": f"HTTP {status}"})
            continue
        state["fields"][name] = _now_iso()
        out.append({"field": name, "query": fld["query"],
                    "n": len(repos), "repos": repos})
    return out


def run_watch(client: GitHubClient, repos: List[str],
              state: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for repo in repos:
        releases = watch_releases(client, repo, state)
        issues = watch_issues(client, repo, state)
        out.append({"repo": repo, "new_releases": releases,
                    "new_issues": issues})
    return out


def build_envelope(data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "provenance": {
            "source": "github-rest-api",
            "method": "fetch_github",
            "retrieved_at": _now_iso(),
            "tool": TOOL,
        },
        "data": data,
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--new", action="store_true",
                   help="search newly-created repos for --query")
    p.add_argument("--trending", action="store_true",
                   help="recently-created repos sorted by stars (proxy)")
    p.add_argument("--watch", action="store_true",
                   help="new releases/issues for --repo / config watchlist")
    p.add_argument("--query", help="field query (search/repositories qualifiers)")
    p.add_argument("--repo", action="append", default=[],
                   help="owner/name for --watch (repeatable)")
    p.add_argument("--config", type=Path,
                   help="JSON config: {fields:[{name,query,...}], watchlist:[...]}")
    p.add_argument("--state", type=Path, help="delta-tracking state file")
    p.add_argument("--since-days", type=int, default=7)
    p.add_argument("--min-stars", type=int, default=0)
    p.add_argument("-n", "--limit", type=int, default=20)
    p.add_argument("-o", "--output", type=Path, help="write JSON here (else stdout)")
    args = p.parse_args(argv)

    token = load_token()
    if not token:
        sys.stderr.write(
            "[warn] no GITHUB_PAT found (secrets.json / env). "
            "Falling back to 60 req/h unauthenticated — monitoring will throttle.\n"
        )

    state = load_state(args.state)
    defaults = {"since_days": args.since_days, "min_stars": args.min_stars,
                "limit": args.limit}

    fields: List[Dict[str, Any]] = []
    watchlist: List[str] = list(args.repo)

    if args.config:
        cfg = json.loads(args.config.read_text(encoding="utf-8"))
        fields = cfg.get("fields", [])
        watchlist += cfg.get("watchlist", [])
        defaults.update(cfg.get("defaults", {}))

    if args.query:
        mode = "trending" if args.trending else "new"
        fields.append({"name": args.query, "query": args.query,
                       "sort": "stars", "mode": mode})

    result: Dict[str, Any] = {}
    try:
        with GitHubClient(token) as client:
            if fields:
                result["new_repos"] = run_fields(client, fields, state, defaults)
            if (args.watch or watchlist) and watchlist:
                result["watch"] = run_watch(client, watchlist, state)
    except ScrapeError as exc:
        # Auth/quota failure: no report is written, because an empty report is
        # exactly what made this invisible before.
        sys.stderr.write(f"ERROR: {exc}\n")
        return 4

    if not result:
        sys.stderr.write(
            "Nothing to do. Provide --query/--new, --watch + --repo, or --config.\n")
        return 2

    save_state(args.state, state)
    envelope = build_envelope(result)
    text = json.dumps(envelope, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        sys.stderr.write(f"[ok] wrote {args.output}\n")
    else:
        print(text)

    # The report is written either way — a partial result is still useful — but
    # the exit code must not claim success when a field failed. Before 260730
    # this always returned 0, so a cron wrapper had no signal at all.
    failed = [f["field"] for f in result.get("new_repos", []) if f.get("error")]
    if failed:
        sys.stderr.write(
            f"[warn] {len(failed)} field(s) failed: {', '.join(failed)}\n")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
