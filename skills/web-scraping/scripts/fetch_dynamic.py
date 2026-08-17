"""fetch_dynamic.py - render JavaScript-driven pages with Playwright.

This is the *fallback* path for pages that fetch_static.py cannot handle
because their content is built client-side by JavaScript. Most research and
public-data pages are static, so Playwright is an optional dependency:

    pip install playwright
    playwright install chromium

Playwright is imported lazily inside the methods that need it, so importing
this module (or running fetch_static / fetch_academic) never requires the
browser to be installed.

After rendering, the resulting HTML is handed to StaticScraper from
fetch_static, so text / table / link extraction logic is not duplicated.

Dual use:
  - CLI:    python fetch_dynamic.py URL --mode text --wait-selector "#results"
  - import: from fetch_dynamic import DynamicScraper
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Optional

from _common import (
    DEFAULT_USER_AGENT,
    Provenance,
    RobotsChecker,
    ScrapeError,
    validate_url,
    write_json_output,
    ensure_utf8_stdout,
)
from fetch_static import StaticScraper


PLAYWRIGHT_INSTALL_HINT = (
    "Playwright is not installed. The dynamic mode is optional.\n"
    "  pip install playwright\n"
    "  playwright install chromium"
)


@dataclass
class DynamicConfig:
    """Tunable behavior for DynamicScraper."""

    user_agent: str = DEFAULT_USER_AGENT
    timeout_ms: int = 30000
    wait_selector: Optional[str] = None      # CSS selector to wait for
    wait_until: str = "networkidle"          # load | domcontentloaded | networkidle
    headless: bool = True
    respect_robots: bool = True
    # Reject public names resolving to private addresses. Off only for
    # offline/unit-test use, never to "make a fetch work".
    resolve_dns: bool = True


class DynamicScraper:
    """Renders a page in headless Chromium and returns its post-JS HTML.

    The browser is launched per :meth:`render` call and closed afterwards,
    keeping resource usage bounded. For batch jobs, call render repeatedly
    on one instance; each call is self-contained.
    """

    def __init__(self, config: Optional[DynamicConfig] = None) -> None:
        self.config = config or DynamicConfig()
        self.robots = RobotsChecker(self.config.user_agent)

    def _check_allowed(self, url: str) -> None:
        # Safety gate BEFORE politeness, and independent of --ignore-robots.
        # Chromium will happily render file:///... and return its content, and
        # robots.txt cannot refuse a URL that has no host — so a robots check
        # alone let a local secrets file into the output JSON (260730 audit).
        validate_url(url, resolve=self.config.resolve_dns)
        if self.config.respect_robots and not self.robots.can_fetch(url):
            raise ScrapeError(
                f"robots.txt disallows fetching: {url}\n"
                f"(disable robots checking only with explicit authorization)"
            )

    def _install_navigation_guard(self, page) -> None:
        """Re-check the target on every document navigation, not just the first.

        ``page.goto`` follows redirects, so validating only the URL we were
        given would leave "public URL redirects into the internal network"
        open. Sub-resources (images, CSS) are left alone: they never end up in
        ``page.content()`` and filtering them all costs a round-trip each.
        """
        def handle(route):
            request = route.request
            if not request.is_navigation_request():
                route.continue_()
                return
            try:
                validate_url(request.url, resolve=self.config.resolve_dns)
            except ScrapeError:
                route.abort()
            else:
                route.continue_()

        page.route("**/*", handle)

    def render(self, url: str) -> str:
        """Load ``url`` in headless Chromium and return the rendered HTML."""
        self._check_allowed(url)
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise ScrapeError(PLAYWRIGHT_INSTALL_HINT) from exc

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    headless=self.config.headless
                )
                try:
                    page = browser.new_page(user_agent=self.config.user_agent)
                    self._install_navigation_guard(page)
                    page.goto(url, wait_until=self.config.wait_until,
                              timeout=self.config.timeout_ms)
                    if self.config.wait_selector:
                        page.wait_for_selector(
                            self.config.wait_selector,
                            timeout=self.config.timeout_ms,
                        )
                    return page.content()
                finally:
                    browser.close()
        except ScrapeError:
            raise
        except Exception as exc:  # playwright errors -> uniform ScrapeError
            message = str(exc)
            if "Executable doesn't exist" in message:
                raise ScrapeError(
                    "Chromium browser binary missing. Run:\n"
                    "  playwright install chromium"
                ) from exc
            raise ScrapeError(f"Dynamic render failed for {url}: {exc}") from exc

    def scrape(self, url: str) -> StaticScraper:
        """Render ``url`` and return a StaticScraper over the rendered HTML."""
        html = self.render(url)
        return StaticScraper(html=html, base_url=url)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render a JavaScript page with headless Chromium, "
                    "then extract text / tables / links.",
    )
    parser.add_argument("url", help="page URL to render")
    parser.add_argument(
        "--mode", nargs="+", default=["text"],
        choices=["text", "tables", "links", "html"],
        help="what to extract after rendering (default: text)",
    )
    parser.add_argument("--wait-selector", default=None,
                        help="CSS selector to wait for before extracting")
    parser.add_argument("--wait-until", default="networkidle",
                        choices=["load", "domcontentloaded", "networkidle"],
                        help="navigation wait condition (default networkidle)")
    parser.add_argument("--timeout", type=float, default=30.0,
                        help="render timeout in seconds (default 30)")
    parser.add_argument("--no-headless", action="store_true",
                        help="show the browser window (debugging)")
    parser.add_argument("--ignore-robots", action="store_true",
                        help="bypass robots.txt (use ONLY with authorization)")
    parser.add_argument("-o", "--output", default=None,
                        help="output JSON path (default: stdout)")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    ensure_utf8_stdout()
    args = _build_parser().parse_args(argv)
    config = DynamicConfig(
        timeout_ms=int(args.timeout * 1000),
        wait_selector=args.wait_selector,
        wait_until=args.wait_until,
        headless=not args.no_headless,
        respect_robots=not args.ignore_robots,
    )
    try:
        scraper = DynamicScraper(config).scrape(args.url)
        data: dict = {}
        if "text" in args.mode:
            data["text"] = scraper.extract_text()
        if "tables" in args.mode:
            data["tables"] = scraper.extract_tables()
        if "links" in args.mode:
            data["links"] = scraper.extract_links()
        if "html" in args.mode:
            data["html"] = scraper.html
    except ScrapeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    provenance = Provenance(source_url=args.url, method="fetch_dynamic")
    text = write_json_output(data, args.output, provenance)
    if args.output:
        print(f"Wrote {args.output}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
