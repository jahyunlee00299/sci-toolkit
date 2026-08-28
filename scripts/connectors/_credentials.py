#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared credential loader — every external-service integration script reads its keys through this.

Security principles (AGENTS.md §9):
- Real keys are never included in the distribution. Read only from
  config/credentials.json (gitignore/distignore'd) or environment variables.
- If a value looks like "ENV:VARNAME", the actual value is fetched from that
  environment variable (so the key never even sits in the file).
- Never print a token to the screen or a log (a masking helper is provided).

Usage:
    from _credentials import load, get, require
    cfg = load()                          # the whole dict
    tok = get("github", "token")          # the actual value, ENV: already resolved (None if absent)
    tok = require("github", "token")      # exits with a helpful error if absent
"""
from __future__ import annotations

# Windows' default console is cp949 and dies on Korean/symbol output. Force UTF-8.
# Use reconfigure: wrapping in TextIOWrapper would take ownership of the
# underlying stream, so once this module is imported and the wrapper gets
# GC'd, it closes the caller's stdout too (measured).
import sys as _sys
for _s in (_sys.stdout, _sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

import json
import os
import sys
from pathlib import Path

# scripts/connectors/_credentials.py → toolkit root
ROOT = Path(__file__).resolve().parent.parent.parent
CRED_PATH = ROOT / "config" / "credentials.json"
EXAMPLE_PATH = ROOT / "config" / "credentials.example.json"


def _resolve_env(value):
    """'ENV:NAME' → os.environ['NAME']; any other value passes through unchanged. An unset env var yields None."""
    if isinstance(value, str) and value.startswith("ENV:"):
        return os.environ.get(value[4:])
    return value


def load() -> dict:
    """Reads credentials.json and returns a dict. If absent, prints guidance and returns an empty dict."""
    if not CRED_PATH.exists():
        print(
            "[Note] No credentials file yet.\n"
            f"  Copy {EXAMPLE_PATH.name} to credentials.json in the same folder, then\n"
            "  fill in your own account info. Using an environment variable (ENV:...) for the\n"
            "  real key is recommended. (credentials.json is excluded from distribution and commits.)",
            file=sys.stderr,
        )
        return {}
    with CRED_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def get(*path, cfg: dict | None = None):
    """Reads a value by nested key path and resolves ENV: to the actual value (None if absent).

    Example: get("mail", "accounts", "work", "password")
    """
    node = load() if cfg is None else cfg
    for k in path:
        if not isinstance(node, dict) or k not in node:
            return None
        node = node[k]
    return _resolve_env(node)


def require(*path, cfg: dict | None = None):
    """Same as get(), but if the value is absent, exits after saying exactly which key/env var needs filling in."""
    val = get(*path, cfg=cfg)
    if val:
        return val
    key = " → ".join(path)
    sys.exit(
        f"[Error] Missing credential: {key}\n"
        f"  Fill in the corresponding entry in config/credentials.json, or if the value is 'ENV:NAME',\n"
        f"  set that environment variable (NAME). Template: config/credentials.example.json"
    )


def mask(secret) -> str:
    """Masks a token so it can be safely printed to a log: only the first 2 and last 2 characters shown."""
    if not secret or not isinstance(secret, str):
        return "(none)"
    if len(secret) <= 6:
        return "*" * len(secret)
    return f"{secret[:2]}{'*' * (len(secret) - 4)}{secret[-2:]}"


if __name__ == "__main__":
    # Diagnostic: shows which services have credentials configured (values masked).
    c = load()
    if not c:
        sys.exit(0)
    print("Configured services (values masked):")
    for svc in ("mail", "github", "asana", "notion", "google"):
        node = c.get(svc)
        state = "configured" if node else "empty"
        print(f"  - {svc:8s}: {state}")
