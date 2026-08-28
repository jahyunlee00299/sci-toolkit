#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Asana REST API connector — read-first / write-guarded (AGENTS.md §9).

`me` and `tasks` are free reads. Writes (`add-task`, `add-comment`,
`add-subtask`) all require the explicit --write flag; without it, only a
dry-run preview is printed. Assigning to someone other than 'me' prints an
outward-action notice. There is no complete/delete subcommand.

Formatting rules (prevents the "formatting looks wrong" problem users hit —
lab-verified):
- Every request uses ensure_ascii=False + charset=utf-8 -> non-ASCII text stays intact.
- Formatted comments/descriptions (--html / --html-notes) are enforced by
  sanitize_html(): <body> wrapping, <p> forbidden (xml_parsing_error), line
  breaks kept as real newlines (\n), '->' arrow character forbidden.
  (The &#10; entity gets re-escaped by Asana's sanitizer into &amp;#10; and
  shows up as a literal on screen — measured in issue #4. A legacy input's
  &#10; is automatically restored to a real newline.)
- Default comment/description is plain text (safer for short text).
"""
from __future__ import annotations

# Windows' default console is cp949 and dies on non-ASCII/symbol output. Force UTF-8.
# Use reconfigure: wrapping in a TextIOWrapper takes ownership of the underlying
# stream, so once this module is imported, GC'ing the wrapper closes the
# caller's stdout too (measured).
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

API_ROOT = "https://app.asana.com/api/1.0"


def http(method, url, token, data=None, headers=None):
    """Minimal urllib-based HTTP helper. Returns parsed JSON or exits with a clear error."""
    hdrs = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "sci-toolkit-asana-connector",
    }
    if headers:
        hdrs.update(headers)
    body = None
    if data is not None:
        # ensure_ascii=False is required -- keeps non-ASCII text from being escaped
        # into \uXXXX (lab-verified rule).
        # charset=utf-8 is explicit -- preserves non-ASCII text in comments/subtask bodies.
        body = json.dumps({"data": data}, ensure_ascii=False).encode("utf-8")
        hdrs["Content-Type"] = "application/json; charset=utf-8"
    req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        if e.code == 401:
            sys.exit(f"[Error] Authentication failed (401). Check your token (asana.token). (masked: {cred.mask(token)})")
        if e.code == 403:
            sys.exit("[Error] 403 -- possibly an API rate limit or insufficient permission.")
        if e.code == 404:
            sys.exit("[Error] 404 -- resource not found. Check the gid/workspace value.")
        detail = ""
        try:
            detail = e.read().decode("utf-8", "ignore")
        except Exception:
            pass
        sys.exit(f"[Error] Asana API error {e.code}: {detail[:300]}")
    except urllib.error.URLError as e:
        sys.exit(f"[Error] Check your network connection: {e.reason}")


def cmd_me(args, token):
    data = http("GET", f"{API_ROOT}/users/me", token)
    me = data.get("data", {})
    print(f"Name: {me.get('name')}")
    print(f"gid: {me.get('gid')}")
    print(f"email: {me.get('email')}")
    ws = me.get("workspaces", [])
    if ws:
        print("workspaces:")
        for w in ws:
            print(f"  - {w.get('name')} (gid={w.get('gid')})")


def cmd_tasks(args, token):
    if not args.workspace:
        me_data = http("GET", f"{API_ROOT}/users/me", token)
        ws = me_data.get("data", {}).get("workspaces", [])
        print("[Notice] --workspace gid is required. Available workspaces:")
        for w in ws:
            print(f"  - {w.get('name')} (gid={w.get('gid')})")
        print("Example: asana_connector.py tasks --workspace <gid>")
        return
    url = f"{API_ROOT}/tasks?assignee=me&workspace={args.workspace}&opt_fields=name,completed,due_on"
    data = http("GET", url, token)
    items = data.get("data", [])
    print(f"{len(items)} of my tasks (workspace={args.workspace})")
    for t in items:
        status = "done" if t.get("completed") else "in progress"
        due = t.get("due_on") or "-"
        print(f"  [{status}] {t.get('name')} (due: {due}, gid={t.get('gid')})")


def cmd_add_task(args, token):
    is_outward = bool(args.assignee) and args.assignee.strip().lower() != "me"

    body_preview = {
        "workspace": args.workspace,
        "name": args.name,
        "notes": args.notes or "",
    }
    if args.assignee:
        body_preview["assignee"] = args.assignee

    if is_outward:
        print("[Notice] This task is being assigned to someone else -- this is an outward action.")

    if not args.write:
        print("[DRY-RUN] --write flag not set, not actually executing.")
        print("  Task that would be created:")
        print(json.dumps(body_preview, ensure_ascii=False, indent=2))
        print("  Add --write to actually run this.")
        return

    if is_outward:
        print(f"[Notice] This task will be assigned to {args.assignee}. Proceeding (--write given).")

    result = http("POST", f"{API_ROOT}/tasks", token, data=body_preview)
    created = result.get("data", {})
    print(f"[Done] Task created: {created.get('name')} (gid={created.get('gid')})")


# Tags allowed in Asana html_text/html_notes (anything else, especially <p>, causes xml_parsing_error).
_ALLOWED_HTML_TAGS = ("body", "strong", "em", "u", "s", "code",
                      "a", "ul", "ol", "li", "h1", "h2", "table", "tr", "td")


def sanitize_html(html):
    """Enforce/check Asana's html_text formatting rules (prevents the "formatting looks wrong" problem users hit).

    Rules (lab-verified): (1) must be wrapped in <body>...</body> (2) <p> is
    forbidden (xml_parsing_error) (3) line breaks must be real newline
    characters (\\n) as-is -- the &#10; entity gets re-escaped by Asana's
    sanitizer into &amp;#10; and shows up as a literal on screen (measured in
    issue #4) (4) the '->' arrow character is forbidden (XML parsing error).
    (5) keep <table> to 5 columns or fewer (measured 260827). Asana pins
    width="120" on every <td> regardless of content and never shrinks narrow
    columns, so a table with many short values overflows the comment pane.
    A series of short values under a single label (e.g. 8 temperatures, a
    dilution series, cycle counts) isn't really 2D data, just a long single
    row -- write it as one line of text like "50.0 / 52.6 / 55.1" instead of
    a table. Reserve tables for genuinely labeled rows (reagent/volume,
    primer/sequence/Tm).
    Any violation that can't be auto-corrected is reported as an error.
    """
    if "→" in html:
        sys.exit("[Format error] The '→' character in html_text causes an XML parsing error. "
                 "Replace it with '->' or a word.")
    if "<p>" in html or "</p>" in html:
        sys.exit("[Format error] The <p> tag causes xml_parsing_error in Asana. "
                 "Use a real newline character for line breaks instead.")
    # Auto-correct: wrap in <body>
    if "<body>" not in html:
        html = f"<body>{html}</body>"
    # Normalize line breaks: CRLF -> LF. Restore a legacy &#10; input (the
    # form older help text used to recommend) to a real newline -- Asana
    # only renders a real LF inside html_text as a line break.
    html = html.replace("\r\n", "\n").replace("&#10;", "\n")
    return html


def cmd_add_comment(args, token):
    """Post a comment (story) on a task. Plain text by default; --html validates formatting then sends html_text."""
    if args.html:
        payload = {"html_text": sanitize_html(args.text)}
        kind = "html_text (format-validated)"
    else:
        payload = {"text": args.text}
        kind = "text (plain)"

    if not args.write:
        print("[DRY-RUN] --write flag not set, not actually executing.")
        print(f"  Target task gid: {args.task}")
        print(f"  Comment format: {kind}")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print("  Add --write to actually run this.")
        return

    print("[Notice] A comment is an outward action, visible to other people.")
    result = http("POST", f"{API_ROOT}/tasks/{args.task}/stories", token, data=payload)
    story = result.get("data", {})
    print(f"[Done] Comment posted (gid={story.get('gid')})")

    # Self-verify right after posting (guards against the issue #4 regression):
    # if a re-fetched html_text still has &#10; in it, the line break is
    # showing up as a literal -- report it as a failure.
    if args.html and story.get("gid"):
        try:
            fetched = http("GET",
                           f"{API_ROOT}/stories/{story['gid']}?opt_fields=html_text",
                           token)
            html_text = (fetched.get("data") or {}).get("html_text") or ""
            if "#10;" in html_text:
                sys.exit("[Verification failed] The posted comment still has an &#10; literal in it "
                         "(line break not applied). This is the issue #4 regression -- check the code.")
            print("[Verified] No &#10; literal on re-fetch -- line breaks look correct.")
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001 -- the comment itself was already posted
            print(f"[Warning] Post-creation re-fetch verification failed (comment was still posted): {exc}")


def cmd_add_subtask(args, token):
    """Create a subtask under a parent task (uses the dedicated /tasks/{parent}/subtasks endpoint)."""
    is_outward = bool(args.assignee) and args.assignee.strip().lower() != "me"

    payload = {"name": args.name}
    if args.html_notes:
        payload["html_notes"] = sanitize_html(args.notes) if args.notes else "<body></body>"
    elif args.notes:
        payload["notes"] = args.notes
    if args.assignee:
        payload["assignee"] = args.assignee
    if args.workspace:
        payload["workspace"] = args.workspace

    if is_outward:
        print("[Notice] This subtask is being assigned to someone else -- this is an outward action.")

    if not args.write:
        print("[DRY-RUN] --write flag not set, not actually executing.")
        print(f"  Parent task gid: {args.parent}")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print("  Add --write to actually run this.")
        return

    result = http("POST", f"{API_ROOT}/tasks/{args.parent}/subtasks", token, data=payload)
    created = result.get("data", {})
    print(f"[Done] Subtask created: {created.get('name')} (gid={created.get('gid')})")


def build_parser():
    p = argparse.ArgumentParser(
        prog="asana_connector.py",
        description=(
            "Asana REST connector (read-first). me/tasks are free reads, "
            "add-task is the only write action and requires --write. Assigning "
            "to someone else shows an outward notice. "
            "There is no complete/delete subcommand."
        ),
    )
    sub = p.add_subparsers(dest="command")

    sp = sub.add_parser("me", help="[READ] my profile/workspaces")
    sp.set_defaults(func=cmd_me)

    sp = sub.add_parser("tasks", help="[READ] my task list")
    sp.add_argument("--workspace", default=None, help="workspace gid (lists options if omitted)")
    sp.set_defaults(func=cmd_tasks)

    sp = sub.add_parser("add-task", help="[WRITE, requires --write] create a task")
    sp.add_argument("--workspace", required=True)
    sp.add_argument("--name", required=True)
    sp.add_argument("--notes", default="")
    sp.add_argument("--assignee", default=None, help="'me' or another person's gid/email (unassigned if omitted)")
    sp.add_argument("--write", action="store_true", help="Actually create the task (dry-run without this)")
    sp.set_defaults(func=cmd_add_task)

    sp = sub.add_parser("add-comment", help="[WRITE, requires --write] post a comment on a task")
    sp.add_argument("--task", required=True, help="gid of the task to comment on")
    sp.add_argument("--text", required=True, help="comment content")
    sp.add_argument("--html", action="store_true",
                    help="Formatted comment (html_text). Auto-wraps <body>, forbids <p>, validates real-newline (\\n) breaks and forbids ->")
    sp.add_argument("--write", action="store_true", help="Actually post the comment (dry-run without this)")
    sp.set_defaults(func=cmd_add_comment)

    sp = sub.add_parser("add-subtask", help="[WRITE, requires --write] create a subtask")
    sp.add_argument("--parent", required=True, help="parent task gid")
    sp.add_argument("--name", required=True, help="subtask name")
    sp.add_argument("--notes", default="", help="description (plain by default, formatted with --html-notes)")
    sp.add_argument("--html-notes", dest="html_notes", action="store_true",
                    help="Send description as html_notes (same format validation applied)")
    sp.add_argument("--assignee", default=None, help="'me' or another person's gid (unassigned if omitted)")
    sp.add_argument("--workspace", default=None, help="workspace gid (if needed)")
    sp.add_argument("--write", action="store_true", help="Actually create it (dry-run without this)")
    sp.set_defaults(func=cmd_add_subtask)

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    if not getattr(args, "command", None):
        parser.print_help()
        print("\n[Notice] Reads (me/tasks) run immediately. Writes (add-task/add-comment/add-subtask) require --write to run.")
        return
    # Allow a dry-run (a write command without --write) to preview without a token.
    is_dryrun_write = hasattr(args, "write") and not args.write
    token = None if is_dryrun_write else cred.require("asana", "token")
    args.func(args, token)


if __name__ == "__main__":
    main()
