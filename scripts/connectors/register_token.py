#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Register a freshly-issued API token into config/credentials.json --
without the value ever appearing in a Claude Code conversation.

Why this exists
----------------
docs/13 walks a first-time user through Chrome to the right token page, but
stops at "clicking Generate and copying the value is on you" -- Claude never
reads the value back, because anything Claude reads becomes part of the
session transcript. That principle stays. What used to be missing was the
last step: pasting the value into config/credentials.json by hand (find the
file, find the nested key, match the JSON quoting). This script closes that
gap WITHOUT weakening the principle -- it must be run directly in the user's
own terminal (suggest the `! <command>` prefix in Claude Code), never through
a Claude tool call, so the token goes keyboard -> getpass() -> file and
nowhere else.

Usage (run this yourself, not through Claude):
    python scripts/connectors/register_token.py github
    python scripts/connectors/register_token.py notion
    python scripts/connectors/register_token.py asana
    python scripts/connectors/register_token.py mail --account personal
    python scripts/connectors/register_token.py mail --account work
    python scripts/connectors/register_token.py github --field username --value your-handle

If `python` isn't recognized on Windows (common with PATH-less installs), try
`py` instead -- it's the launcher most Windows Python installers register on
PATH even when `python` itself isn't:
    py scripts/connectors/register_token.py github

Google Calendar/Drive use OAuth, not a static token -- not handled here, see
docs/05_외부서비스_연동.md (External Service Integration) §4-4.
"""
from __future__ import annotations

import argparse
import getpass
import json
import shutil
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

ROOT = Path(__file__).resolve().parent.parent.parent
CRED_PATH = ROOT / "config" / "credentials.json"
EXAMPLE_PATH = ROOT / "config" / "credentials.example.json"

# service -> (nested path to the secret field, human label)
DEFAULT_FIELD = {
    "github": ["github", "token"],
    "notion": ["notion", "token"],
    "asana": ["asana", "token"],
    "mail": ["mail", "accounts", "work", "password"],
}

# mail is keyed by --account too (work/personal), unlike the single-token services
MAIL_ACCOUNTS = ("work", "personal")


def mask(secret: str) -> str:
    if not secret:
        return "(none)"
    if len(secret) <= 6:
        return "*" * len(secret)
    return f"{secret[:2]}{'*' * (len(secret) - 4)}{secret[-2:]}"


def load_config() -> dict:
    if not CRED_PATH.exists():
        if not EXAMPLE_PATH.exists():
            sys.exit(f"[error] {EXAMPLE_PATH} is also missing -- the repository looks corrupted.")
        shutil.copy(EXAMPLE_PATH, CRED_PATH)
        print(f"[info] {CRED_PATH.name} was missing, so it was created from the example template.")
    with CRED_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def set_nested(cfg: dict, path: list[str], value: str) -> None:
    node = cfg
    for key in path[:-1]:
        node = node.setdefault(key, {})
    node[path[-1]] = value


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("service", choices=sorted(DEFAULT_FIELD), help="which service's token this is")
    ap.add_argument("--account", choices=MAIL_ACCOUNTS, default="work",
                     help="mail service only: which account, work or personal (default work)")
    ap.add_argument("--field", nargs="+", default=None,
                     help="a different nested key path instead of the default field (e.g. --field github username)")
    ap.add_argument("--value", default=None,
                     help="pass the value directly as an argument (warning: this stays in your shell "
                          "history -- only when running directly in a terminal, never via a Claude tool call)")
    args = ap.parse_args(argv)

    if args.field:
        field_path = args.field
    elif args.service == "mail":
        field_path = ["mail", "accounts", args.account, "password"]
    else:
        field_path = DEFAULT_FIELD[args.service]
    label = " → ".join(field_path)

    if args.value is not None:
        value = args.value
        print("[warning] --value stays in your shell history. Run without it "
              "and use the hidden prompt instead when possible.", file=sys.stderr)
    else:
        value = getpass.getpass(
            f"Paste the value for '{label}' and press Enter "
            f"(input will not be shown on screen): "
        ).strip()

    if not value:
        sys.exit("[error] Empty value -- nothing was registered.")

    cfg = load_config()
    set_nested(cfg, field_path, value)
    with CRED_PATH.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"[registered] {label} = {mask(value)}  ({CRED_PATH})")
    print("Verify: python scripts/connectors/_credentials.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
