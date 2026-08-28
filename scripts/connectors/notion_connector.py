#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Notion API connector — read-first / write-guarded (AGENTS.md §9).

`search` and `page` are free reads. `append` is the only write action and
requires the explicit --write flag; without it, only a dry-run preview of
the block that would be appended is printed. append is strictly additive —
this script has no delete/archive subcommand at all.
"""
from __future__ import annotations

# Windows' default console is cp949, which dies on Korean/symbol output. Force UTF-8.
# Use reconfigure(): wrapping in a TextIOWrapper would take ownership of the
# underlying stream, so once the wrapper is GC'd after this module is imported,
# it closes the caller's stdout too (measured).
import sys as _sys
for _s in (_sys.stdout, _sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

import argparse
import json
import sys
import urllib.error
import urllib.request

import _credentials as cred

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

API_ROOT = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def http(method, url, token, data=None, headers=None):
    """Minimal urllib-based HTTP helper. Returns parsed JSON, or exits with a friendly error."""
    hdrs = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Accept": "application/json",
        "User-Agent": "sci-toolkit-notion-connector",
    }
    if headers:
        hdrs.update(headers)
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        if e.code == 401:
            sys.exit(f"[Error] Authentication failed (401). Check your token (notion.token). (masked: {cred.mask(token)})")
        if e.code == 403:
            sys.exit("[Error] 403 — insufficient permission (the integration may not be connected to this page).")
        if e.code == 404:
            sys.exit("[Error] 404 — page/block not found. Check the id.")
        detail = ""
        try:
            detail = e.read().decode("utf-8", "ignore")
        except Exception:
            pass
        sys.exit(f"[Error] Notion API error {e.code}: {detail[:300]}")
    except urllib.error.URLError as e:
        sys.exit(f"[Error] Check your network connection: {e.reason}")


def cmd_search(args, token):
    body = {"query": args.query}
    data = http("POST", f"{API_ROOT}/search", token, data=body)
    results = data.get("results", [])
    print(f"Query '{args.query}' — {len(results)} result(s)")
    for r in results:
        obj_type = r.get("object")
        title = "(no title)"
        props = r.get("properties", {})
        for v in props.values():
            if v.get("type") == "title" and v.get("title"):
                title = "".join(t.get("plain_text", "") for t in v["title"])
                break
        print(f"  [{obj_type}] {title}  (id={r.get('id')})")


def cmd_page(args, token):
    data = http("GET", f"{API_ROOT}/pages/{args.id}", token)
    print(f"id: {data.get('id')}")
    print(f"url: {data.get('url')}")
    props = data.get("properties", {})
    for name, v in props.items():
        if v.get("type") == "title" and v.get("title"):
            title = "".join(t.get("plain_text", "") for t in v["title"])
            print(f"Title ({name}): {title}")


def cmd_append(args, token):
    block_body = {
        "children": [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {"type": "text", "text": {"content": args.text}}
                    ]
                },
            }
        ]
    }

    if not args.write:
        print("[DRY-RUN] --write flag not set, not actually executing.")
        print(f"  Target page: {args.page_id}")
        print("  Block to be added (paragraph):")
        print(json.dumps(block_body, ensure_ascii=False, indent=2))
        print("  Add --write to execute.")
        return

    print("[Notice] Appending a block to the page (additive only, no delete/archive function).")
    url = f"{API_ROOT}/blocks/{args.page_id}/children"
    result = http("PATCH", url, token, data=block_body)
    added = result.get("results", [])
    print(f"[Done] {len(added)} block(s) added.")


def build_parser():
    p = argparse.ArgumentParser(
        prog="notion_connector.py",
        description=(
            "Notion API connector (read-first). search/page are free reads; "
            "append is the only write action and requires --write (additive only, no delete/archive subcommand)."
        ),
    )
    sub = p.add_subparsers(dest="command")

    sp = sub.add_parser("search", help="[READ] search")
    sp.add_argument("--query", required=True)
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("page", help="[READ] look up a page")
    sp.add_argument("--id", required=True, help="page id")
    sp.set_defaults(func=cmd_page)

    sp = sub.add_parser("append", help="[WRITE, requires --write] append a text block to a page")
    sp.add_argument("--page-id", required=True)
    sp.add_argument("--text", required=True)
    sp.add_argument("--write", action="store_true", help="Actually append the block (dry-run if omitted)")
    sp.set_defaults(func=cmd_append)

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    if not getattr(args, "command", None):
        parser.print_help()
        print("\n[Note] Reads (search/page) run immediately. Writes (append) require --write.")
        return
    # A dry-run (a write command without --write) can preview without a token.
    is_dryrun_write = hasattr(args, "write") and not args.write
    token = None if is_dryrun_write else cred.require("notion", "token")
    args.func(args, token)


if __name__ == "__main__":
    main()
