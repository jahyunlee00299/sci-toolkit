"""Resolve a GitHub repo URL or a PyPI package name into requirement specs.

GitHub path tries pyproject.toml, then requirements.txt, then setup.cfg, on
raw.githubusercontent.com — unauthenticated, no rate limit (confirmed in
prior research). setup.py is out of scope for this unit (would need AST
parsing to be safe; deferred).

PyPI path reads info.requires_dist from the package's JSON API.

fetch_requirements() distinguishes "found nothing" from "found an empty
list" by raising FetchError instead of ever returning []. Callers must not
confuse an empty return with runner.probe_all([]), which is a "no
requirements, trivially ok" result — this module never emits an empty list.
"""
from __future__ import annotations

import configparser
import json
import re
import tomllib
import urllib.error
import urllib.request
from dataclasses import dataclass


class FetchError(Exception):
    """Raised when a source could not be resolved to any requirements."""


@dataclass
class GitHubRef:
    owner: str
    repo: str
    branch: str | None  # None = try main, then master


_GITHUB_URL_RE = re.compile(
    r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?"
    r"(?:/(?:tree|blob)/(?P<branch>[^/]+))?/?$"
)

_CANDIDATE_FILES = ("pyproject.toml", "requirements.txt", "setup.cfg")
_BRANCH_FALLBACKS = ("main", "master")
_USER_AGENT = "compat-check/0.1 (+https://github.com/)"
_REQUEST_TIMEOUT = 15


def _http_get(url: str) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise FetchError(f"HTTP {e.code} fetching {url}") from e
    except urllib.error.URLError as e:
        raise FetchError(f"network error fetching {url}: {e.reason}") from e


def parse_github_url(source: str) -> GitHubRef | None:
    m = _GITHUB_URL_RE.match(source.strip())
    if not m:
        return None
    return GitHubRef(owner=m.group("owner"), repo=m.group("repo"), branch=m.group("branch"))


def _parse_pyproject_toml(text: str) -> list[str]:
    data = tomllib.loads(text)
    project = data.get("project", {})
    deps = list(project.get("dependencies", []))
    # optional-dependencies groups are extras, not base requirements — skipped intentionally.
    return deps


def _parse_requirements_txt(text: str) -> list[str]:
    reqs = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(("-r ", "-e ", "--")):
            continue  # nested includes / editable installs / pip flags out of scope
        reqs.append(line)
    return reqs


def _parse_setup_cfg(text: str) -> list[str]:
    parser = configparser.ConfigParser()
    parser.read_string(text)
    if not parser.has_option("options", "install_requires"):
        return []
    raw = parser.get("options", "install_requires")
    return [line.strip() for line in raw.splitlines() if line.strip()]


_PARSERS = {
    "pyproject.toml": _parse_pyproject_toml,
    "requirements.txt": _parse_requirements_txt,
    "setup.cfg": _parse_setup_cfg,
}


def _fetch_from_github(ref: GitHubRef) -> list[str]:
    branches = [ref.branch] if ref.branch else list(_BRANCH_FALLBACKS)
    tried = []
    for branch in branches:
        for filename in _CANDIDATE_FILES:
            url = f"https://raw.githubusercontent.com/{ref.owner}/{ref.repo}/{branch}/{filename}"
            tried.append(url)
            text = _http_get(url)
            if text is None:
                continue
            try:
                reqs = _PARSERS[filename](text)
            except Exception as e:
                raise FetchError(f"failed to parse {url}: {e}") from e
            if reqs:
                return reqs
            # file exists but declares no dependencies — keep searching other files/branches
    raise FetchError(
        f"no pyproject.toml/requirements.txt/setup.cfg with dependencies found for "
        f"{ref.owner}/{ref.repo} (tried: {', '.join(tried)})"
    )


def _fetch_from_pypi(package_name: str) -> list[str]:
    url = f"https://pypi.org/pypi/{package_name}/json"
    text = _http_get(url)
    if text is None:
        raise FetchError(f"PyPI package not found: {package_name}")
    data = json.loads(text)
    requires_dist = data.get("info", {}).get("requires_dist") or []
    # drop extras-only markers (e.g. 'foo; extra == "dev"') — base install only.
    base = [r for r in requires_dist if "extra ==" not in r]
    if not base:
        raise FetchError(f"PyPI package {package_name} declares no base requires_dist")
    return base


def fetch_requirements(source: str) -> list[str]:
    """Resolve `source` (GitHub URL or PyPI package name) to requirement specs.

    Raises FetchError if nothing could be resolved. Never returns [] —
    that return value is reserved for callers of runner.probe_all() to mean
    "no requirements, trivially ok", which this function must not be
    confused with.
    """
    ref = parse_github_url(source)
    if ref is not None:
        return _fetch_from_github(ref)
    return _fetch_from_pypi(source)
