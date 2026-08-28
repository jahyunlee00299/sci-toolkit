#!/usr/bin/env python3
"""Builds an institutional library (off-campus access) link for a paywalled paper — a link, and nothing more.

This module **deliberately never logs in or downloads.** Fetching the full
text of a subscription journal via script is itself a violation of a
university library's fair-use policy. Korea University's policy (violation
example #1) states it this way:

    "Downloading full text by electronic or mechanical means (a download
     program, engine, robot, macro, RPA, etc.)"

It's not just account sharing (#5) that's banned — the **means itself** is
a banned item. Even a legitimate login on the user's own account is a
violation once a script picks up after it, and the sanction is a one-year
library-service suspension plus first-line civil liability. So this is as
far as this toolkit goes: it builds the URL a human clicks in a browser,
and states the policy and the limits alongside it.

Usage:
    from institutional_access import InstitutionRegistry
    reg = InstitutionRegistry.load()                  # config/institutions.json
    link = reg.build_link("korea-univ", "https://www.sciencedirect.com/...")
    print(link.url, link.login_note)

CLI:
    python institutional_access.py --list
    python institutional_access.py --institution korea-univ --url https://...
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

# Default location: this file lives in scripts/, so it looks at config/ under the repo root.
_DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config" / "institutions.json"

_PLACEHOLDER = "{url}"


@dataclass(frozen=True)
class InstitutionalLink:
    """A single link meant to be opened by a human in a browser."""

    institution: str
    display_name: str
    url: str
    login_note: str
    fair_use_url: Optional[str]
    daily_limits: dict[str, Any]

    def human_summary(self) -> str:
        """A notice suitable for printing directly to a terminal. States every time that this is not an auto-download."""
        lines = [
            f"  Institutional access link ({self.display_name}):",
            f"    {self.url}",
        ]
        if self.login_note:
            lines.append(f"    · {self.login_note}")
        per_pub = self.daily_limits.get("per_publisher")
        per_machine = self.daily_limits.get("per_machine")
        if per_pub or per_machine:
            lines.append(
                f"    · Daily limit: {per_pub} per publisher / {per_machine} per machine"
            )
        if self.fair_use_url:
            lines.append(f"    · Fair-use policy: {self.fair_use_url}")
        lines.append(
            "    · This link is meant to be opened by a human in a browser. Downloading "
            "the full text via script or macro is a 공정이용 위반 (fair-use violation)."
        )
        return "\n".join(lines)


class InstitutionRegistry:
    """A thin registry that reads config/institutions.json and builds links."""

    def __init__(self, data: dict[str, Any], source: Optional[Path] = None) -> None:
        self._institutions: dict[str, Any] = data.get("institutions") or {}
        self._default: Optional[str] = data.get("default_institution")
        self.source = source

    # --- Loading ------------------------------------------------------------ #

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "InstitutionRegistry":
        """Reads the config. If the file is absent, returns an empty registry — not an error.

        Institutional config is optional. Without it, only this feature quietly
        turns off and OA collection must keep working normally (missing one
        config file must never take down the whole tool).
        """
        p = Path(path) if path else _DEFAULT_CONFIG
        if not p.exists():
            return cls({}, source=None)
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            # Silently ignoring a broken config leads straight to "why is no link showing up".
            print(f"[WARN] Could not read the institutional config ({p}): {e}", file=sys.stderr)
            return cls({}, source=None)
        return cls(data if isinstance(data, dict) else {}, source=p)

    # --- Lookup ------------------------------------------------------------ #

    def available(self) -> list[str]:
        return sorted(self._institutions.keys())

    def resolve_key(self, key: Optional[str]) -> Optional[str]:
        """Explicit key > config's default_institution > (if there's only one) that one."""
        if key:
            return key if key in self._institutions else None
        if self._default and self._default in self._institutions:
            return self._default
        if len(self._institutions) == 1:
            return next(iter(self._institutions))
        return None

    def build_link(self, key: Optional[str], target_url: str) -> Optional[InstitutionalLink]:
        """Wraps the target URL in the institution's proxy link. Returns None if it can't be built."""
        if not target_url:
            return None
        resolved = self.resolve_key(key)
        if not resolved:
            return None
        entry = self._institutions.get(resolved) or {}
        template = entry.get("proxy_url_template")
        if not template or _PLACEHOLDER not in template:
            # A template with no placeholder would silently produce a broken link — refuse to build one instead.
            print(
                f"[WARN] '{resolved}'s proxy_url_template has no {_PLACEHOLDER} "
                "placeholder — not building a link.",
                file=sys.stderr,
            )
            return None
        return InstitutionalLink(
            institution=resolved,
            display_name=entry.get("display_name") or resolved,
            url=template.replace(_PLACEHOLDER, target_url),
            login_note=entry.get("login_note") or "",
            fair_use_url=entry.get("fair_use_url"),
            daily_limits=entry.get("daily_limits") or {},
        )


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Builds an institutional library access link for a paywalled paper (no login, no download).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--list", action="store_true", help="print the list of configured institutions")
    ap.add_argument("--institution", default=None, help="institution key (e.g. korea-univ)")
    ap.add_argument("--url", default=None, help="the full-text landing-page URL")
    ap.add_argument("--config", default=None, help="path to institutions.json (default: config/)")
    args = ap.parse_args()

    reg = InstitutionRegistry.load(Path(args.config) if args.config else None)

    if args.list or not args.url:
        keys = reg.available()
        if not keys:
            print("No institutions configured. Check config/institutions.json.")
            return 1
        print("Configured institutions:")
        for k in keys:
            print(f"  - {k}")
        if not args.url:
            return 0
        return 0

    link = reg.build_link(args.institution, args.url)
    if not link:
        print(
            "[ERROR] Could not build a link — the institution key is missing or unconfigured.\n"
            f"        Available: {', '.join(reg.available()) or '(none)'}",
            file=sys.stderr,
        )
        return 1
    print(link.human_summary())
    return 0


if __name__ == "__main__":
    sys.exit(main())
