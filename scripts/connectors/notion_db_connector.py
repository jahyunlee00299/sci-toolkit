#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Notion DATABASE API connector — read-first / write-guarded (AGENTS.md §9).

`list-dbs`, `schema`, `query` are free reads. `add-row` is the only write
action and requires the explicit --write flag; without it, only a dry-run
preview of the page payload is printed. This script is strictly additive —
there is no delete/archive subcommand at all (Notion "delete" is really an
archive; we simply never call it here).

Warning: the most common trap. Even with a valid Integration token, unless
that Integration has been **shared with the target database first
(Connections)**, it won't show up in list-dbs and schema/query will fail with
404. Open the database page in Notion, use the "..." menu in the top right ->
Connections -> select the Integration you're using, and share it that way.
(See docs/07_노션_연동_가이드.md.)
"""
from __future__ import annotations

# The default Windows console is cp949, which crashes on Korean/symbol
# output. Force UTF-8. Use reconfigure: wrapping with TextIOWrapper makes it
# own the underlying stream, so once this module is imported and the wrapper
# is later garbage collected, it closes the caller's stdout too (measured).
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
    """Minimal urllib-based HTTP helper. Returns parsed JSON, or exits with a friendly error message."""
    hdrs = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Accept": "application/json",
        "User-Agent": "sci-toolkit-notion-db-connector",
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
            sys.exit(
                f"[Error] Authentication failed (401). Check the token (notion.token). "
                f"(masked: {cred.mask(token)})"
            )
        if e.code == 403:
            sys.exit(
                "[Error] 403 — insufficient permissions. This database may not have "
                "the Integration shared to it (Connections). In Notion, open the DB "
                "page's '...' menu -> Connections -> select the Integration, then retry."
            )
        if e.code == 404:
            sys.exit(
                "[Error] 404 — database not found. Check the --db value (32-char id), "
                "or the Integration may not be shared with this database yet "
                "('...' -> Connections -> select the Integration). First confirm it "
                "appears in the list-dbs output."
            )
        if e.code == 400:
            detail = ""
            try:
                detail = e.read().decode("utf-8", "ignore")
            except Exception:
                pass
            sys.exit(
                "[Error] 400 — bad request. The property name/type may not match the "
                "actual database. Run `schema --db <id>` first to confirm the exact "
                f"property names and types, then retry with matching --prop values.\n  Detail: {detail[:300]}"
            )
        detail = ""
        try:
            detail = e.read().decode("utf-8", "ignore")
        except Exception:
            pass
        sys.exit(f"[Error] Notion API error {e.code}: {detail[:300]}")
    except urllib.error.URLError as e:
        sys.exit(f"[Error] Check your network connection: {e.reason}")


def _title_of(props: dict) -> str:
    """Extract the plain text of the title-type property from a properties dict."""
    for v in props.values():
        if v.get("type") == "title" and v.get("title"):
            return "".join(t.get("plain_text", "") for t in v["title"])
    return "(no title)"


def _status_of(props: dict) -> str:
    """Extract the status or select-type value from a properties dict, in human-readable form."""
    for name, v in props.items():
        if v.get("type") == "status" and v.get("status"):
            return v["status"].get("name", "-")
    for name, v in props.items():
        if v.get("type") == "select" and v.get("select"):
            return v["select"].get("name", "-")
    return "-"


def cmd_list_dbs(args, token):
    body = {"filter": {"value": "database", "property": "object"}}
    data = http("POST", f"{API_ROOT}/search", token, data=body)
    results = data.get("results", [])
    print(f"{len(results)} database(s) connected (Connections)")
    if not results:
        print(
            "  (none) -> this Integration may not have any database shared with it yet.\n"
            "  In Notion, share it via the target DB page's '...' -> Connections -> "
            "select the Integration."
        )
        return
    for r in results:
        title = "(no title)"
        title_prop = r.get("title", [])
        if title_prop:
            title = "".join(t.get("plain_text", "") for t in title_prop)
        else:
            title = _title_of(r.get("properties", {}))
        print(f"  - {title}  (id={r.get('id')})")


def _get_schema(db_id, token):
    return http("GET", f"{API_ROOT}/databases/{db_id}", token)


def cmd_schema(args, token):
    data = _get_schema(args.db, token)
    title = "(no title)"
    if data.get("title"):
        title = "".join(t.get("plain_text", "") for t in data["title"])
    print(f"Database: {title} (id={data.get('id')})")
    props = data.get("properties", {})
    print(f"{len(props)} propertie(s):")
    for name, v in props.items():
        print(f"  - {name}  [{v.get('type')}]")


def cmd_query(args, token):
    body = {"page_size": args.limit}
    if args.sort:
        prop, _, direction = args.sort.partition(":")
        direction = direction or "ascending"
        if direction not in ("ascending", "descending"):
            sys.exit(f"[Error] --sort direction must be either ascending or descending: {direction}")
        body["sorts"] = [{"property": prop, "direction": direction}]
    if args.status:
        # Query the schema first to confirm the Status property's actual type (status/select)
        schema = _get_schema(args.db, token)
        props = schema.get("properties", {})
        status_prop_name = None
        status_prop_type = None
        for name, v in props.items():
            # NOTE: "상태" (Korean for "status") is a real property-name value
            # some Notion databases use — kept as literal matching data, not prose.
            if v.get("type") in ("status", "select") and name.lower() in (
                "status",
                "상태",
            ):
                status_prop_name = name
                status_prop_type = v.get("type")
                break
        if status_prop_name is None:
            for name, v in props.items():
                if v.get("type") in ("status", "select"):
                    status_prop_name = name
                    status_prop_type = v.get("type")
                    break
        if status_prop_name:
            body["filter"] = {
                "property": status_prop_name,
                status_prop_type: {"equals": args.status},
            }
        else:
            print("[Note] No status/select-type property found — skipping the --status filter.")

    data = http("POST", f"{API_ROOT}/databases/{args.db}/query", token, data=body)
    results = data.get("results", [])
    print(f"{len(results)} result(s) (limit={args.limit})")
    for r in results:
        props = r.get("properties", {})
        title = _title_of(props)
        status = _status_of(props)
        print(f"  - [{status}] {title}  (id={r.get('id')})")


def _build_property_payload(prop_type, name, raw_value):
    """Build a Notion API payload fragment matching the property TYPE confirmed from the schema."""
    if prop_type == "title":
        return {"title": [{"type": "text", "text": {"content": raw_value}}]}
    if prop_type == "rich_text":
        return {"rich_text": [{"type": "text", "text": {"content": raw_value}}]}
    if prop_type == "select":
        return {"select": {"name": raw_value}}
    if prop_type == "multi_select":
        values = [v.strip() for v in raw_value.split(",") if v.strip()]
        return {"multi_select": [{"name": v} for v in values]}
    if prop_type == "status":
        return {"status": {"name": raw_value}}
    if prop_type == "number":
        try:
            num = float(raw_value)
            if num.is_integer():
                num = int(num)
        except ValueError:
            sys.exit(f"[Error] '{name}' is a number-type property, and this value can't be converted to one: {raw_value}")
        return {"number": num}
    if prop_type == "date":
        return {"date": {"start": raw_value}}
    if prop_type == "checkbox":
        # NOTE: "예" ("yes") / "체크" ("check") are real Korean-language user
        # input values this CLI accepts — kept as literal matching data, not prose.
        truthy = raw_value.strip().lower() in ("true", "1", "yes", "y", "예", "체크")
        return {"checkbox": truthy}
    sys.exit(
        f"[Error] '{name}' has property type '{prop_type}', which this script doesn't support yet. "
        "Supported types: title, rich_text, select, multi_select, status, number, date, checkbox"
    )


def cmd_add_row(args, token):
    # add-row's dry-run only makes sense if it can read the real schema —
    # without knowing whether a property name exists or what type it is, the
    # preview can't say "this payload is correct." So this command alone
    # requires a token even for dry-run. Showing a preview built without a
    # token looks friendlier, but it's actually worse: it presents an
    # unvalidated payload as though it were validated.
    if token is None:
        sys.exit(
            "[Error] add-row requires a Notion token even without --write.\n"
            "  The preview is only meaningful once it's checked against the real schema.\n"
            "  Set up a token: python scripts/connectors/register_token.py"
        )
    schema = _get_schema(args.db, token)
    props_schema = schema.get("properties", {})

    title_prop_name = None
    for name, v in props_schema.items():
        if v.get("type") == "title":
            title_prop_name = name
            break
    if title_prop_name is None:
        sys.exit("[Error] No title property found in this database.")

    page_props = {
        title_prop_name: _build_property_payload("title", title_prop_name, args.title)
    }

    for raw in args.prop or []:
        if "=" not in raw:
            sys.exit(f"[Error] Bad --prop format (must be NAME=VALUE): {raw}")
        name, value = raw.split("=", 1)
        name = name.strip()
        if name not in props_schema:
            available = ", ".join(sorted(props_schema.keys()))
            sys.exit(
                f"[Error] '{name}' is not a property in this database.\n"
                f"  Run `schema --db {args.db}` first to see the real property names.\n"
                f"  Available properties: {available}"
            )
        prop_type = props_schema[name].get("type")
        page_props[name] = _build_property_payload(prop_type, name, value)

    body_preview = {
        "parent": {"database_id": args.db},
        "properties": page_props,
    }

    if not args.write:
        print("[DRY-RUN] no --write flag, so nothing is actually executed.")
        print(f"  Target database: {args.db}")
        print("  Page (properties) that would be created:")
        print(json.dumps(body_preview, ensure_ascii=False, indent=2))
        print("  Add --write to actually run this.")
        return

    print("[Notice] Adding a new item (page) to the database (additive only — no delete/archive feature).")
    result = http("POST", f"{API_ROOT}/pages", token, data=body_preview)
    print(f"[Done] Item created (id={result.get('id')})")
    if result.get("url"):
        print(f"  url: {result.get('url')}")


def build_parser():
    p = argparse.ArgumentParser(
        prog="notion_db_connector.py",
        description=(
            "Notion DATABASE connector (read-first). list-dbs/schema/query are free "
            "reads; add-row is the only write action and requires --write (additive "
            "only — there is no delete/archive subcommand). "
            "The Integration must already be shared (Connections) with the target database."
        ),
    )
    sub = p.add_subparsers(dest="command")

    sp = sub.add_parser("list-dbs", help="[READ] list databases you have access to")
    sp.set_defaults(func=cmd_list_dbs)

    sp = sub.add_parser("schema", help="[READ] view a database's properties (schema)")
    sp.add_argument("--db", required=True, help="database id (32 characters)")
    sp.set_defaults(func=cmd_schema)

    sp = sub.add_parser("query", help="[READ] query rows in a database")
    sp.add_argument("--db", required=True, help="database id (32 characters)")
    sp.add_argument("--limit", type=int, default=10, help="max number of results (default 10)")
    sp.add_argument(
        "--status", default=None, help="simple filter by a status/select property value (e.g. 'In progress')"
    )
    sp.add_argument(
        "--sort", default=None,
        help="Sort as PROPERTY[:ascending|descending] (default ascending). "
             "e.g. --sort 'Date:descending' — use for querying the N most recent items",
    )
    sp.set_defaults(func=cmd_query)

    sp = sub.add_parser("add-row", help="[WRITE, requires --write] add a new item to a database")
    sp.add_argument("--db", required=True, help="database id (32 characters)")
    sp.add_argument("--title", required=True, help="value for the title property")
    sp.add_argument(
        "--prop",
        action="append",
        default=[],
        help="NAME=VALUE form, repeatable (e.g. --prop Status='In progress' --prop Tags=a,b)",
    )
    sp.add_argument("--write", action="store_true", help="actually add the item (dry-run if omitted)")
    sp.set_defaults(func=cmd_add_row)

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    if not getattr(args, "command", None):
        parser.print_help()
        print(
            "\n[Note] Reads (list-dbs/schema/query) run immediately. "
            "Writes (add-row) require --write to run."
        )
        return
    # A dry-run write command (write command but no --write) can still preview without a token.
    is_dryrun_write = hasattr(args, "write") and not args.write
    token = None if is_dryrun_write else cred.require("notion", "token")
    args.func(args, token)


if __name__ == "__main__":
    main()
