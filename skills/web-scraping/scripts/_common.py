"""Shared infrastructure for the web-scraping skill.

This module provides reusable, ethically-constrained building blocks used by
every fetch_*.py script:

  - RobotsChecker      : robots.txt compliance (urllib.robotparser based)
  - RateLimiter        : per-domain minimum request spacing
  - ResponseCache      : simple on-disk cache keyed by URL
  - PoliteHttpClient   : httpx wrapper with retry, backoff, Retry-After, UA
  - ProvenanceWriter   : records source URL + timestamp + method for outputs

Design notes (SOLID):
  - Each class has a single responsibility and can be used independently.
  - PoliteHttpClient depends on RobotsChecker / RateLimiter / ResponseCache
    through constructor injection, so any of them can be swapped or disabled.
  - All classes are import-friendly; nothing runs on import.

The defaults err on the side of being a polite, identifiable crawler:
robots.txt is enforced, rate limiting is on (1 req/domain/sec), and the
User-Agent carries a contact address.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import socket
import time
import urllib.robotparser
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

try:
    import httpx
except ImportError as exc:  # pragma: no cover - dependency guard
    raise ImportError(
        "httpx is required. Install skill dependencies:\n"
        "  pip install -r requirements.txt"
    ) from exc


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

# Identifiable User-Agent. The contact address lets site owners reach out
# instead of silently blocking. Researchers should keep this honest rather
# than impersonating a browser (CLAUDE.md: browser disguise is unnecessary
# for academic / public-data use).
DEFAULT_CONTACT = os.environ.get("WEB_SCRAPING_CONTACT", "your-email@example.com")
DEFAULT_USER_AGENT = (
    f"web-scraping-skill/1.0 (research crawler; mailto:{DEFAULT_CONTACT})"
)

# Cache lives under the skill directory by default so it persists and is easy
# to inspect / clear.
DEFAULT_CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------

class ScrapeError(RuntimeError):
    """Raised for unrecoverable fetch failures (blocked, exhausted retries)."""


class UnsafeTargetError(ScrapeError):
    """Raised when a URL or a filename is rejected by the safety gate.

    Distinct from a network failure: nothing was attempted at all, because the
    target is not a legitimate public web resource (wrong scheme, local host,
    private network) or not a safe path component (traversal, absolute path).
    """


# --------------------------------------------------------------------------
# Target safety gate  (SSRF / local-file exfiltration / path traversal)
# --------------------------------------------------------------------------
#
# This is the single place where "is this target legitimate" is decided, so a
# guard added here reaches every consumer that goes through it. Two facts made
# it necessary (260730 audit):
#
#   - robots.txt compliance is NOT a safety check. A URL with no host (e.g.
#     ``file:///.../secrets.json``) makes RobotsChecker return its
#     ``allow_on_error`` default, i.e. *allowed* — and Playwright then renders
#     the local file and hands its content back in the output JSON.
#     httpx refusing ``file://`` with UnsupportedProtocol was luck, not a guard.
#   - a filename taken from a remote URL is attacker-controlled text. After
#     ``unquote()`` it can carry ``..`` or a Windows drive, and ``dest_dir /
#     name`` silently discards ``dest_dir`` for an absolute path.

ALLOWED_URL_SCHEMES = frozenset({"http", "https"})

# Default ceiling for a single streamed download (250 MB). A research PDF or
# dataset is far below it; an unbounded stream is how a hostile or misconfigured
# server fills the disk. Overridable per call and via --max-download-mb.
DEFAULT_MAX_DOWNLOAD_BYTES = 250 * 1024 * 1024

# Names that resolve to this machine without ever touching DNS.
_LOCAL_HOSTNAMES = frozenset({
    "localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback",
})

# Reserved device names on Windows: a file called "con.pdf" is not creatable.
_WINDOWS_RESERVED = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)

# Anything outside this set is stripped from a filename. Deliberately strict:
# a legitimate document name survives it, a payload does not.
_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9가-힣._\- ]+")


def _ip_is_blocked(ip) -> bool:
    """True for any address that is not a public internet destination."""
    return bool(
        ip.is_loopback or ip.is_private or ip.is_link_local
        or ip.is_reserved or ip.is_multicast or ip.is_unspecified
    )


def _as_ip_literal(host: str):
    """Return an ip_address if ``host`` is an IP in ANY literal form, else None.

    ``ipaddress`` only accepts the canonical forms, but the OS resolver and
    every browser also accept the short and numeric variants — ``127.1``,
    ``0x7f000001``, ``2130706433``, ``0177.0.0.1`` — which all reach
    127.0.0.1 while looking like a hostname to a naive parser. Those forms are
    precisely what an SSRF payload uses, so they are normalized here instead of
    being left to the DNS-resolution branch (which callers can turn off).
    """
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        pass
    try:
        return ipaddress.ip_address(socket.inet_aton(host))
    except (OSError, UnicodeEncodeError, ValueError):
        return None


def validate_url(url: str, *, resolve: bool = True) -> str:
    """Return ``url`` unchanged if it is a safe public http(s) target.

    Raises :class:`UnsafeTargetError` otherwise. Checks in order:

      1. scheme is http/https — blocks ``file:``, ``data:``, ``ftp:``,
         ``chrome:``, ``javascript:`` and friends.
      2. a host is present — blocks ``file:///etc/passwd`` style URLs whose
         netloc is empty and which therefore bypass every host-based check.
      3. the host is not loopback / private / link-local, as an IP literal in
         any notation (``127.0.0.1``, ``127.1``, ``2130706433``,
         ``0x7f000001``) or a well-known local name — blocks ``192.168.x.x``
         and ``169.254.169.254`` (cloud metadata) too.
      4. with ``resolve=True`` (default), the resolved addresses are public
         too — catches a public name pointing at an internal address.

    A DNS failure is **not** treated as unsafe: it is a network problem, and
    reporting it is the HTTP layer's job. Only a *successful* resolution to a
    blocked address rejects the URL.
    """
    if not isinstance(url, str) or not url.strip():
        raise UnsafeTargetError("empty URL")

    parsed = urlparse(url.strip())
    scheme = (parsed.scheme or "").lower()
    if scheme not in ALLOWED_URL_SCHEMES:
        raise UnsafeTargetError(
            f"URL scheme {scheme or '(none)'!r} is not allowed: {url}\n"
            f"(only {'/'.join(sorted(ALLOWED_URL_SCHEMES))} are fetchable; "
            f"a local or non-web scheme would read this machine, not the web)"
        )

    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        raise UnsafeTargetError(f"URL has no host: {url}")

    if host in _LOCAL_HOSTNAMES:
        raise UnsafeTargetError(f"refusing to fetch a local host: {url}")

    # IP literal (any notation): decide from the literal itself, no DNS.
    literal = _as_ip_literal(host)
    if literal is not None:
        if _ip_is_blocked(literal):
            raise UnsafeTargetError(
                f"refusing to fetch a non-public address ({host}): {url}"
            )
        return url

    if resolve:
        try:
            infos = socket.getaddrinfo(host, parsed.port or None,
                                       proto=socket.IPPROTO_TCP)
        except (socket.gaierror, socket.herror, UnicodeError, ValueError):
            infos = []  # DNS problem -> let the HTTP layer report it
        for info in infos:
            sockaddr = info[4]
            try:
                addr = ipaddress.ip_address(sockaddr[0])
            except (ValueError, IndexError):
                continue
            if _ip_is_blocked(addr):
                raise UnsafeTargetError(
                    f"host {host} resolves to a non-public address "
                    f"({addr}): {url}"
                )
    return url


def sanitize_filename(name: str, *, fallback: str = "download",
                      max_length: int = 128) -> str:
    """Reduce untrusted text to one safe path component.

    Never returns an empty string, a path separator, a drive letter, ``.`` or
    ``..``. Used for filenames derived from remote URLs or response headers,
    where the value is chosen by whoever controls the server.
    """
    candidate = (name or "").strip()
    # Take the last component under BOTH separator conventions: a POSIX host
    # must not be fooled by "C:\\Users\\pwned.pdf" and vice versa.
    for separator in ("/", "\\"):
        if separator in candidate:
            candidate = candidate.rsplit(separator, 1)[-1]
    # Strip a Windows drive / stream prefix ("C:", "file:") that survives above.
    if ":" in candidate:
        candidate = candidate.rsplit(":", 1)[-1]
    candidate = _UNSAFE_FILENAME_CHARS.sub("_", candidate).strip(". ")

    if not candidate or candidate in {".", ".."}:
        return fallback

    stem, dot, suffix = candidate.rpartition(".")
    if dot and stem and stem.lower() in _WINDOWS_RESERVED:
        candidate = f"{stem}_{suffix}"
    elif not dot and candidate.lower() in _WINDOWS_RESERVED:
        candidate = f"{candidate}_"

    if len(candidate) > max_length:
        stem, dot, suffix = candidate.rpartition(".")
        if dot and len(suffix) <= 16:
            keep = max(1, max_length - len(suffix) - 1)
            candidate = f"{stem[:keep]}.{suffix}"
        else:
            candidate = candidate[:max_length]
    return candidate or fallback


def resolve_within(base_dir: Path, name: str, *,
                   fallback: str = "download") -> Path:
    """Return ``base_dir``/sanitized(``name``), proven to stay under base_dir.

    Sanitizing and containment-checking are kept together because doing only
    the first is the mistake this replaces: a collision-avoiding ``_unique_path``
    prevents overwrites but not traversal.
    """
    base = Path(base_dir).resolve()
    target = (base / sanitize_filename(name, fallback=fallback)).resolve()
    if target != base and base not in target.parents:
        raise UnsafeTargetError(
            f"refusing to write outside {base}: {name!r} -> {target}"
        )
    return target


# --------------------------------------------------------------------------
# robots.txt compliance
# --------------------------------------------------------------------------

class RobotsChecker:
    """Checks whether a URL may be fetched per the target site's robots.txt.

    One parser is cached per domain. If robots.txt cannot be retrieved the
    site is treated as *allowed* (standard convention), but the caller can
    flip ``allow_on_error`` to be strict instead.
    """

    def __init__(self, user_agent: str = DEFAULT_USER_AGENT,
                 allow_on_error: bool = True) -> None:
        self.user_agent = user_agent
        self.allow_on_error = allow_on_error
        self._parsers: dict[str, urllib.robotparser.RobotFileParser] = {}

    def _parser_for(self, url: str) -> Optional[urllib.robotparser.RobotFileParser]:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return None
        domain = f"{parsed.scheme}://{parsed.netloc}"
        if domain in self._parsers:
            return self._parsers[domain]

        parser = urllib.robotparser.RobotFileParser()
        parser.set_url(f"{domain}/robots.txt")
        try:
            parser.read()
        except Exception:
            # Network failure / no robots.txt: leave parser unread.
            parser = None  # type: ignore[assignment]
        self._parsers[domain] = parser  # type: ignore[assignment]
        return parser

    def can_fetch(self, url: str) -> bool:
        """Return True if ``url`` is allowed for our User-Agent."""
        parser = self._parser_for(url)
        if parser is None:
            return self.allow_on_error
        try:
            return parser.can_fetch(self.user_agent, url)
        except Exception:
            return self.allow_on_error

    def crawl_delay(self, url: str) -> Optional[float]:
        """Return the robots.txt Crawl-delay for ``url`` if specified."""
        parser = self._parser_for(url)
        if parser is None:
            return None
        try:
            delay = parser.crawl_delay(self.user_agent)
            return float(delay) if delay is not None else None
        except Exception:
            return None


# --------------------------------------------------------------------------
# Rate limiting
# --------------------------------------------------------------------------

class RateLimiter:
    """Enforces a minimum delay between requests to the same domain.

    State is per-domain so unrelated hosts are not slowed by each other.
    """

    def __init__(self, min_delay: float = 1.0) -> None:
        self.min_delay = max(0.0, min_delay)
        self._last_request: dict[str, float] = {}

    def wait(self, url: str, extra_delay: float = 0.0) -> None:
        """Sleep just long enough to respect the spacing for ``url``'s domain.

        ``extra_delay`` lets a caller honor a robots.txt Crawl-delay that is
        longer than the configured minimum.
        """
        domain = urlparse(url).netloc
        if not domain:
            return
        required = max(self.min_delay, extra_delay)
        last = self._last_request.get(domain)
        if last is not None:
            elapsed = time.monotonic() - last
            if elapsed < required:
                time.sleep(required - elapsed)
        self._last_request[domain] = time.monotonic()


# --------------------------------------------------------------------------
# Response cache
# --------------------------------------------------------------------------

class ResponseCache:
    """Simple on-disk cache of HTTP response bodies keyed by URL.

    Avoids re-hitting servers for identical URLs, which is both polite and
    helps reproducibility. Entries expire after ``ttl_seconds``.
    """

    def __init__(self, cache_dir: Path = DEFAULT_CACHE_DIR,
                 ttl_seconds: float = 86400.0, enabled: bool = True) -> None:
        self.cache_dir = Path(cache_dir)
        self.ttl_seconds = ttl_seconds
        self.enabled = enabled
        if self.enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
        return self.cache_dir / f"{digest}.json"

    def get(self, url: str) -> Optional[str]:
        """Return cached body for ``url`` or None if missing / expired."""
        if not self.enabled:
            return None
        path = self._path_for(url)
        if not path.exists():
            return None
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        if time.time() - entry.get("stored_at", 0) > self.ttl_seconds:
            return None
        return entry.get("body")

    def set(self, url: str, body: str) -> None:
        """Store ``body`` for ``url``."""
        if not self.enabled:
            return
        entry = {"url": url, "stored_at": time.time(), "body": body}
        try:
            self._path_for(url).write_text(
                json.dumps(entry, ensure_ascii=False), encoding="utf-8"
            )
        except OSError:
            pass  # caching is best-effort; never fail the request over it


# --------------------------------------------------------------------------
# HTTP client
# --------------------------------------------------------------------------

@dataclass
class HttpClientConfig:
    """Tunable behavior for PoliteHttpClient."""

    user_agent: str = DEFAULT_USER_AGENT
    timeout: float = 30.0
    max_retries: int = 3
    backoff_factor: float = 1.5
    min_delay: float = 1.0
    respect_robots: bool = True
    use_cache: bool = True
    cache_ttl: float = 86400.0
    max_connections: int = 5
    # Resolve hostnames and reject public names that point at private
    # addresses. Off only for offline/unit-test use, never to "make it work".
    resolve_dns: bool = True


class PoliteHttpClient:
    """httpx-based HTTP client that is polite by construction.

    Combines robots.txt enforcement, per-domain rate limiting, on-disk
    caching, an identifiable User-Agent, and retry with exponential backoff
    that honors HTTP 429 ``Retry-After``.

    Usable as a context manager so the underlying httpx client is closed::

        with PoliteHttpClient() as client:
            html = client.get_text("https://example.com")
    """

    def __init__(self, config: Optional[HttpClientConfig] = None) -> None:
        self.config = config or HttpClientConfig()
        self.robots = RobotsChecker(self.config.user_agent)
        self.limiter = RateLimiter(self.config.min_delay)
        self.cache = ResponseCache(
            ttl_seconds=self.config.cache_ttl, enabled=self.config.use_cache
        )
        self._client = httpx.Client(
            headers={"User-Agent": self.config.user_agent},
            timeout=self.config.timeout,
            follow_redirects=True,
            limits=httpx.Limits(max_connections=self.config.max_connections),
            # Redirects are followed automatically, so checking only the URL we
            # were given would leave a redirect into a private address open.
            # httpx re-runs this hook for every request in the chain.
            event_hooks={"request": [self._guard_request]},
        )

    def _guard_request(self, request: "httpx.Request") -> None:
        """Re-validate every outgoing request, including redirect hops."""
        validate_url(str(request.url), resolve=self.config.resolve_dns)

    # -- context manager ---------------------------------------------------

    def __enter__(self) -> "PoliteHttpClient":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    # -- internal ----------------------------------------------------------

    def _check_allowed(self, url: str) -> None:
        # Safety first, politeness second: --ignore-robots must never also turn
        # off the scheme / private-address gate.
        validate_url(url, resolve=self.config.resolve_dns)
        if self.config.respect_robots and not self.robots.can_fetch(url):
            raise ScrapeError(
                f"robots.txt disallows fetching: {url}\n"
                f"(set respect_robots=False only with explicit authorization)"
            )

    def _request_with_retry(self, method: str, url: str,
                            **kwargs) -> httpx.Response:
        """Issue a request, retrying on 429 / 5xx / transport errors."""
        extra_delay = self.robots.crawl_delay(url) or 0.0
        last_exc: Optional[Exception] = None

        for attempt in range(self.config.max_retries):
            self.limiter.wait(url, extra_delay=extra_delay)
            try:
                response = self._client.request(method, url, **kwargs)
            except httpx.HTTPError as exc:
                last_exc = exc
                time.sleep(self.config.backoff_factor ** attempt)
                continue

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                delay = self._parse_retry_after(retry_after, attempt)
                time.sleep(delay)
                continue
            if 500 <= response.status_code < 600:
                time.sleep(self.config.backoff_factor ** attempt)
                continue

            response.raise_for_status()
            return response

        if last_exc is not None:
            raise ScrapeError(f"Request failed after retries: {url}") from last_exc
        raise ScrapeError(f"Request failed after retries (HTTP errors): {url}")

    def _parse_retry_after(self, value: Optional[str], attempt: int) -> float:
        """Convert a Retry-After header to a delay in seconds."""
        if value:
            try:
                return float(value)
            except ValueError:
                pass  # HTTP-date form: fall through to backoff
        return self.config.backoff_factor ** (attempt + 1)

    # -- public API --------------------------------------------------------

    def get_text(self, url: str, use_cache: bool = True) -> str:
        """Fetch ``url`` and return the decoded body as text.

        Respects robots.txt and the on-disk cache.
        """
        self._check_allowed(url)
        if use_cache:
            cached = self.cache.get(url)
            if cached is not None:
                return cached
        response = self._request_with_retry("GET", url)
        text = response.text
        if use_cache:
            self.cache.set(url, text)
        return text

    def get_response(self, url: str) -> httpx.Response:
        """Fetch ``url`` and return the raw httpx.Response (no caching)."""
        self._check_allowed(url)
        return self._request_with_retry("GET", url)

    def stream_to_file(self, url: str, dest: Path,
                       chunk_size: int = 65536,
                       max_bytes: Optional[int] = DEFAULT_MAX_DOWNLOAD_BYTES
                       ) -> Path:
        """Stream ``url`` to ``dest`` on disk without loading it into memory.

        Returns the path written. Used for large PDFs / datasets.

        ``max_bytes`` caps the write and is enforced while streaming, not only
        from ``Content-Length`` (which a server may understate or omit). On
        breach the partial file is removed rather than left as a truncated
        document that looks like a successful download. Pass ``None`` to lift
        the cap deliberately.
        """
        self._check_allowed(url)
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        self.limiter.wait(url, extra_delay=self.robots.crawl_delay(url) or 0.0)
        with self._client.stream("GET", url) as response:
            response.raise_for_status()
            declared = response.headers.get("Content-Length")
            if max_bytes is not None and declared:
                try:
                    if int(declared) > max_bytes:
                        raise ScrapeError(
                            f"declared size {declared} exceeds the "
                            f"{max_bytes}-byte limit, not downloaded: {url}"
                        )
                except ValueError:
                    pass  # malformed header: fall through to streaming check
            written = 0
            try:
                with open(dest, "wb") as handle:
                    for chunk in response.iter_bytes(chunk_size):
                        written += len(chunk)
                        if max_bytes is not None and written > max_bytes:
                            raise ScrapeError(
                                f"download exceeded the {max_bytes}-byte "
                                f"limit and was aborted: {url}"
                            )
                        handle.write(chunk)
            except BaseException:
                # Never leave a partial file that later looks like a real one.
                try:
                    dest.unlink()
                except OSError:
                    pass
                raise
        return dest


# --------------------------------------------------------------------------
# Provenance
# --------------------------------------------------------------------------

@dataclass
class Provenance:
    """Records where scraped data came from and how (CLAUDE.md policy).

    Attached to every JSON output so results are traceable and reproducible.
    """

    source_url: str
    method: str  # e.g. "fetch_static", "fetch_academic:crossref"
    retrieved_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    tool: str = "web-scraping-skill/1.0"

    def as_dict(self) -> dict:
        return {
            "source_url": self.source_url,
            "method": self.method,
            "retrieved_at": self.retrieved_at,
            "tool": self.tool,
        }


def write_json_output(data: dict, output_path: Optional[str],
                      provenance: Provenance) -> str:
    """Write ``data`` (plus provenance) as JSON to ``output_path`` or stdout.

    Returns the JSON string. ``output_path`` may be None for stdout-only.
    """
    payload = {"provenance": provenance.as_dict(), "data": data}
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if output_path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return text


def build_client_from_args(args) -> PoliteHttpClient:
    """Construct a PoliteHttpClient from a parsed argparse namespace.

    Shared by the CLI of every fetch_*.py script so flag handling is uniform.
    Expects the args added by ``add_common_cli_args``.
    """
    config = HttpClientConfig(
        timeout=getattr(args, "timeout", 30.0),
        max_retries=getattr(args, "retries", 3),
        min_delay=getattr(args, "delay", 1.0),
        respect_robots=not getattr(args, "ignore_robots", False),
        use_cache=not getattr(args, "no_cache", False),
    )
    return PoliteHttpClient(config)


def add_common_cli_args(parser) -> None:
    """Add the shared --delay / --timeout / --retries / robots / cache flags.

    Called by each script's argparse setup to keep the CLI consistent.
    """
    group = parser.add_argument_group("polite-crawling options")
    group.add_argument("--delay", type=float, default=1.0,
                       help="min seconds between requests per domain (default 1.0)")
    group.add_argument("--timeout", type=float, default=30.0,
                       help="request timeout in seconds (default 30)")
    group.add_argument("--retries", type=int, default=3,
                       help="max retries on 429/5xx/transport error (default 3)")
    group.add_argument("--ignore-robots", action="store_true",
                       help="bypass robots.txt (use ONLY with authorization)")
    group.add_argument("--no-cache", action="store_true",
                       help="disable the on-disk response cache")


def ensure_utf8_stdout() -> None:
    """Reconfigure stdout/stderr to UTF-8 on Windows (CP949 default fails on non-ASCII).

    Safe no-op on platforms that already use UTF-8.  Call at the top of each
    CLI main() so JSON output with non-ASCII characters is always printable.
    """
    import sys
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass  # best-effort; do not crash the CLI over encoding setup
