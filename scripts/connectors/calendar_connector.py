#!/usr/bin/env python3
"""Google Calendar connector — free reads, writes gated by --write.

    python calendar_connector.py agenda --days 7
    python calendar_connector.py list --calendar primary --days 30
    python calendar_connector.py calendars
    python calendar_connector.py add-event --summary "Meeting" --start 2026-08-20T14:00 --end 2026-08-20T15:00
    python calendar_connector.py add-event ... --write     # actually creates it

Same design as the other connectors (AGENTS.md §9): reads run immediately;
without --write, a write only shows the payload and sends nothing. stdlib
only — `_google_auth.py` exchanges the refresh token directly for auth.

An event that invites other people is outward
-----------------------------------------------
Adding `--attendee` sends an invitation to that person's calendar. This is
hard to undo and is visible to the recipient immediately, so this script
prints a warning before proceeding whenever attendees are present, even
with --write. There is no delete/edit subcommand at all — this tool should
be structurally incapable of the mistake of deleting someone else's event.
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
import json
import sys
from datetime import datetime, timedelta, timezone

import _credentials as cred
import _google_auth as gauth

API_ROOT = "https://www.googleapis.com/calendar/v3"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _rfc3339(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _fmt_when(ev: dict) -> str:
    """Format start/end as one human-readable line. All-day events use date, timed events use dateTime."""
    s = ev.get("start", {})
    e = ev.get("end", {})
    if "date" in s:                      # all-day
        return f"{s['date']} (all day)"
    st = (s.get("dateTime") or "").replace("T", " ")[:16]
    en = (e.get("dateTime") or "").replace("T", " ")[11:16]
    return f"{st}–{en}" if en else st


def cmd_calendars(args, token):
    data = gauth.api_get(f"{API_ROOT}/users/me/calendarList", token,
                         {"maxResults": 250})
    items = data.get("items", [])
    if not items:
        print("[Result] No accessible calendars.")
        return
    print(f"[{len(items)} calendars]")
    for c in items:
        mark = " *primary" if c.get("primary") else ""
        role = c.get("accessRole", "?")
        print(f"  {c.get('summary','(no title)')}{mark}  [{role}]")
        print(f"    id: {c.get('id')}")


def _list_events(args, token):
    now = _now_utc()
    data = gauth.api_get(
        f"{API_ROOT}/calendars/{args.calendar}/events", token,
        {
            "timeMin": _rfc3339(now),
            "timeMax": _rfc3339(now + timedelta(days=args.days)),
            "singleEvents": "true",       # expand recurring events into their actual occurrences
            "orderBy": "startTime",
            "maxResults": args.max,
        })
    return data.get("items", [])


def cmd_list(args, token):
    events = _list_events(args, token)
    if not events:
        print(f"[Result] No events in the next {args.days} days ({args.calendar}).")
        return
    print(f"[{len(events)} events — next {args.days} days, {args.calendar}]")
    for ev in events:
        print(f"  {_fmt_when(ev):22s} {ev.get('summary','(no title)')}")
        if ev.get("location"):
            print(f"    Location: {ev['location']}")
        atts = ev.get("attendees") or []
        if atts:
            print(f"    {len(atts)} attendees")


def cmd_agenda(args, token):
    """Next N days from today — grouped by day. For weekly planning."""
    events = _list_events(args, token)
    if not events:
        print(f"[Result] No events in the next {args.days} days.")
        return
    by_day: dict[str, list] = {}
    for ev in events:
        s = ev.get("start", {})
        day = s.get("date") or (s.get("dateTime") or "")[:10]
        by_day.setdefault(day, []).append(ev)
    for day in sorted(by_day):
        print(f"\n{day}")
        for ev in by_day[day]:
            print(f"  {_fmt_when(ev):22s} {ev.get('summary','(no title)')}")


def cmd_add_event(args, token):
    attendees = [a.strip() for a in (args.attendee or []) if a.strip()]
    is_outward = bool(attendees)

    def _time_field(v):
        # A date alone means an all-day event; a full time means a timed event.
        return {"date": v} if len(v) == 10 else {"dateTime": v}

    body = {
        "summary": args.summary,
        "start": _time_field(args.start),
        "end": _time_field(args.end),
    }
    if args.description:
        body["description"] = args.description
    if args.location:
        body["location"] = args.location
    if attendees:
        body["attendees"] = [{"email": a} for a in attendees]

    if is_outward:
        print("[Notice] This event has attendees specified -- this is an "
              "outward action that sends invitations.")

    if not args.write:
        print("[DRY-RUN] --write flag not set, not actually executing.")
        print(f"  Target calendar: {args.calendar}")
        print("  Event that would be created:")
        print(json.dumps(body, ensure_ascii=False, indent=2))
        if is_outward:
            print(f"  [Warning] Under --write, invitations will go to {len(attendees)} attendees.")
        print("  Add --write to actually run this.")
        return

    if is_outward:
        print(f"[Notice] Invitations will be sent to {', '.join(attendees)}. "
              "Proceeding (--write given).")

    result = gauth.api_post(
        f"{API_ROOT}/calendars/{args.calendar}/events", token, body)
    print(f"[Done] Event created: {result.get('summary')} "
          f"({result.get('id')})")
    if result.get("htmlLink"):
        print(f"  link: {result['htmlLink']}")


def build_parser():
    p = argparse.ArgumentParser(
        description="Google Calendar connector (free reads / --write for writes)")
    sub = p.add_subparsers(dest="command")

    sp = sub.add_parser("calendars", help="list accessible calendars")
    sp.set_defaults(func=cmd_calendars)

    for name, fn, helptext in (
            ("list", cmd_list, "list upcoming events"),
            ("agenda", cmd_agenda, "view upcoming events grouped by day")):
        sp = sub.add_parser(name, help=helptext)
        sp.add_argument("--calendar", default="primary", help="calendar ID (default primary)")
        sp.add_argument("--days", type=int, default=7, help="how many days ahead (default 7)")
        sp.add_argument("--max", type=int, default=50, help="maximum number of results (default 50)")
        sp.set_defaults(func=fn)

    sp = sub.add_parser("add-event", help="create an event (requires --write)")
    sp.add_argument("--calendar", default="primary")
    sp.add_argument("--summary", required=True, help="event title")
    sp.add_argument("--start", required=True,
                    help="start (2026-08-20 or 2026-08-20T14:00:00)")
    sp.add_argument("--end", required=True, help="end (same format as --start)")
    sp.add_argument("--description")
    sp.add_argument("--location")
    sp.add_argument("--attendee", action="append",
                    help="attendee email (repeatable) -- specifying this sends invitations")
    sp.add_argument("--write", action="store_true",
                    help="Actually create it. Preview only without this")
    sp.set_defaults(func=cmd_add_event)
    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    if not getattr(args, "command", None):
        parser.print_help()
        print("\n[Notice] Reads (calendars/list/agenda) run immediately. "
              "Writes (add-event) require --write to run.")
        return
    # Allow a dry-run (a write command without --write) to preview without a token.
    is_dryrun_write = hasattr(args, "write") and not args.write
    token = None if is_dryrun_write else gauth.access_token()
    args.func(args, token)


if __name__ == "__main__":
    main()
