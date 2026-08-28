#!/usr/bin/env python3
"""Google Sheets connector — reading is unrestricted; writing is append-only + gated by --write.

    python sheets_connector.py info   --sheet <ID>
    python sheets_connector.py read   --sheet <ID> --range "Sheet1!A1:D20"
    python sheets_connector.py append --sheet <ID> --range "Sheet1!A:D" --row "a,b,c,d"
    python sheets_connector.py append ... --write        # actually appends

🔴 Why there's only append, and no update
------------------------------------
Overwriting an existing cell in a shared sheet **destroys a value someone
else entered.** There's effectively no way to undo that mistake (a human
has to dig through Google's version history by hand). So this connector
only ever appends rows — the same reason the Notion connector is
additive-only. If an existing value needs fixing, a human does it directly
in the browser. AGENTS.md §9.

The sheet ID comes from the URL:
    https://docs.google.com/spreadsheets/d/<ID goes here>/edit#gid=0
"""
from __future__ import annotations

import sys as _sys

for _s in (_sys.stdout, _sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

import argparse
import csv
import io
import json
import sys

import _credentials as cred
import _google_auth as gauth

API_ROOT = "https://sheets.googleapis.com/v4/spreadsheets"


def _split_row(raw: str) -> list[str]:
    """Turns a --row string into a list of cells, following CSV rules so commas inside quotes are preserved.

    A naive split(",") on `--row 'a,"b,c",d'` produces 4 cells and silently shifts everything.
    """
    return next(csv.reader(io.StringIO(raw)), [])


def cmd_info(args, token):
    data = gauth.api_get(f"{API_ROOT}/{args.sheet}", token,
                         {"fields": "properties.title,sheets.properties"})
    print(f"[Spreadsheet] {data.get('properties', {}).get('title', '(untitled)')}")
    for sh in data.get("sheets", []):
        p = sh.get("properties", {})
        g = p.get("gridProperties", {})
        print(f"  - {p.get('title')}  "
              f"({g.get('rowCount', '?')} rows x {g.get('columnCount', '?')} cols)")


def cmd_read(args, token):
    data = gauth.api_get(
        f"{API_ROOT}/{args.sheet}/values/{args.range}", token,
        {"majorDimension": "ROWS"})
    rows = data.get("values", [])
    if not rows:
        print(f"[Result] No values in range ({args.range}).")
        return
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    # Pad column widths for readability. Google omits trailing empty cells, so row lengths vary.
    width = max(len(r) for r in rows)
    norm = [list(r) + [""] * (width - len(r)) for r in rows]
    colw = [max(len(str(r[i])) for r in norm) for i in range(width)]
    print(f"[{args.range}] {len(rows)} row(s)")
    for r in norm:
        print("  " + " | ".join(str(v).ljust(colw[i]) for i, v in enumerate(r)))


def cmd_append(args, token):
    values = [_split_row(args.row)]
    body = {"values": values}

    if not args.write:
        print("[DRY-RUN] The --write flag is absent, so nothing was actually executed.")
        print(f"  Target sheet: {args.sheet}")
        print(f"  Target range: {args.range}")
        print(f"  Row to append ({len(values[0])} cell(s)):")
        print(json.dumps(values[0], ensure_ascii=False, indent=2))
        print("  Add --write to actually run this.")
        return

    print("[Notice] Appending a row to a shared sheet (additive only, no existing cells are modified/deleted).")
    result = gauth.api_post(
        f"{API_ROOT}/{args.sheet}/values/{args.range}:append", token, body,
        params={
            "valueInputOption": "USER_ENTERED",   # interpret as if a human typed it (dates, formulas)
            "insertDataOption": "INSERT_ROWS",    # never overwrite an existing row, always insert new
        })
    upd = result.get("updates", {})
    print(f"[Done] {upd.get('updatedRows', 0)} row(s) appended "
          f"({upd.get('updatedRange', '?')})")


def build_parser():
    p = argparse.ArgumentParser(
        description="Google Sheets connector (reading unrestricted / appending requires --write, no update or delete)")
    sub = p.add_subparsers(dest="command")

    sp = sub.add_parser("info", help="sheet title, tabs, size")
    sp.add_argument("--sheet", required=True, help="spreadsheet ID (the /d/<ID>/ part of the URL)")
    sp.set_defaults(func=cmd_info)

    sp = sub.add_parser("read", help="read values in a range")
    sp.add_argument("--sheet", required=True)
    sp.add_argument("--range", required=True, help='e.g. "Sheet1!A1:D20"')
    sp.add_argument("--json", action="store_true", help="print JSON instead of an aligned table")
    sp.set_defaults(func=cmd_read)

    sp = sub.add_parser("append", help="append a row (requires --write)")
    sp.add_argument("--sheet", required=True)
    sp.add_argument("--range", required=True, help='target range to append to, e.g. "Sheet1!A:D"')
    sp.add_argument("--row", required=True,
                    help='comma-separated cell values. to include a comma, use "a,\\"b,c\\",d"')
    sp.add_argument("--write", action="store_true",
                    help="actually append. without this, preview only")
    sp.set_defaults(func=cmd_append)
    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    if not getattr(args, "command", None):
        parser.print_help()
        print("\n[Note] Reading (info/read) runs immediately. "
              "Appending (append) requires --write. Update and delete are not provided.")
        return
    # For a dry-run write command (write command but no --write), allow previewing without a token.
    is_dryrun_write = hasattr(args, "write") and not args.write
    token = None if is_dryrun_write else gauth.access_token()
    args.func(args, token)


if __name__ == "__main__":
    main()
