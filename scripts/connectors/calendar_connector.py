#!/usr/bin/env python3
"""Google Calendar 커넥터 — 읽기 자유, 쓰기는 --write 게이트.

    python calendar_connector.py agenda --days 7
    python calendar_connector.py list --calendar primary --days 30
    python calendar_connector.py calendars
    python calendar_connector.py add-event --summary "미팅" --start 2026-08-20T14:00 --end 2026-08-20T15:00
    python calendar_connector.py add-event ... --write     # 실제 생성

설계는 다른 커넥터와 같다(AGENTS.md §9): 읽기는 바로, 쓰기는 --write 없이는
페이로드만 보여주고 아무것도 보내지 않는다. stdlib 만 쓴다 — 인증은
`_google_auth.py` 가 refresh token 을 직접 교환한다.

🔴 남을 초대하는 일정은 outward 다
----------------------------------
`--attendee` 를 붙이면 그 사람 캘린더에 초대장이 날아간다. 되돌리기 어렵고
받는 사람에게 즉시 보이므로, 이 스크립트는 참석자가 있으면 --write 가 있어도
경고를 먼저 출력한다. 삭제·수정 서브커맨드는 아예 제공하지 않는다 —
남의 일정을 지우는 실수는 이 도구로 낼 수 없어야 한다.
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
    """start/end 를 사람이 읽는 한 줄로. 종일 일정은 date, 시간 일정은 dateTime."""
    s = ev.get("start", {})
    e = ev.get("end", {})
    if "date" in s:                      # 종일
        return f"{s['date']} (종일)"
    st = (s.get("dateTime") or "").replace("T", " ")[:16]
    en = (e.get("dateTime") or "").replace("T", " ")[11:16]
    return f"{st}–{en}" if en else st


def cmd_calendars(args, token):
    data = gauth.api_get(f"{API_ROOT}/users/me/calendarList", token,
                         {"maxResults": 250})
    items = data.get("items", [])
    if not items:
        print("[결과] 접근 가능한 캘린더가 없습니다.")
        return
    print(f"[캘린더 {len(items)}개]")
    for c in items:
        mark = " *기본" if c.get("primary") else ""
        role = c.get("accessRole", "?")
        print(f"  {c.get('summary','(제목없음)')}{mark}  [{role}]")
        print(f"    id: {c.get('id')}")


def _list_events(args, token):
    now = _now_utc()
    data = gauth.api_get(
        f"{API_ROOT}/calendars/{args.calendar}/events", token,
        {
            "timeMin": _rfc3339(now),
            "timeMax": _rfc3339(now + timedelta(days=args.days)),
            "singleEvents": "true",       # 반복 일정을 실제 발생 단위로 펼친다
            "orderBy": "startTime",
            "maxResults": args.max,
        })
    return data.get("items", [])


def cmd_list(args, token):
    events = _list_events(args, token)
    if not events:
        print(f"[결과] 앞으로 {args.days}일간 일정이 없습니다 ({args.calendar}).")
        return
    print(f"[일정 {len(events)}건 — 앞으로 {args.days}일, {args.calendar}]")
    for ev in events:
        print(f"  {_fmt_when(ev):22s} {ev.get('summary','(제목없음)')}")
        if ev.get("location"):
            print(f"    장소: {ev['location']}")
        atts = ev.get("attendees") or []
        if atts:
            print(f"    참석자 {len(atts)}명")


def cmd_agenda(args, token):
    """오늘부터 N일 — 날짜별로 묶어서 본다. 주간 계획용."""
    events = _list_events(args, token)
    if not events:
        print(f"[결과] 앞으로 {args.days}일간 일정이 없습니다.")
        return
    by_day: dict[str, list] = {}
    for ev in events:
        s = ev.get("start", {})
        day = s.get("date") or (s.get("dateTime") or "")[:10]
        by_day.setdefault(day, []).append(ev)
    for day in sorted(by_day):
        print(f"\n{day}")
        for ev in by_day[day]:
            print(f"  {_fmt_when(ev):22s} {ev.get('summary','(제목없음)')}")


def cmd_add_event(args, token):
    attendees = [a.strip() for a in (args.attendee or []) if a.strip()]
    is_outward = bool(attendees)

    def _time_field(v):
        # 날짜만 오면 종일 일정, 시각까지 오면 시간 일정.
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
        print("[알림] 참석자가 지정된 일정입니다 — 초대장이 발송되는 "
              "외부로 나가는(outward) 동작입니다.")

    if not args.write:
        print("[DRY-RUN] --write 플래그가 없어 실제로 실행하지 않습니다.")
        print(f"  대상 캘린더: {args.calendar}")
        print("  생성될 일정:")
        print(json.dumps(body, ensure_ascii=False, indent=2))
        if is_outward:
            print(f"  [주의] --write 시 참석자 {len(attendees)}명에게 초대장이 갑니다.")
        print("  실행하려면 --write 를 추가하세요.")
        return

    if is_outward:
        print(f"[알림] {', '.join(attendees)} 에게 초대장이 발송됩니다. "
              "계속 진행합니다 (--write 지정됨).")

    result = gauth.api_post(
        f"{API_ROOT}/calendars/{args.calendar}/events", token, body)
    print(f"[완료] 일정 생성됨: {result.get('summary')} "
          f"({result.get('id')})")
    if result.get("htmlLink"):
        print(f"  link: {result['htmlLink']}")


def build_parser():
    p = argparse.ArgumentParser(
        description="Google Calendar 커넥터 (읽기 자유 / 쓰기 --write)")
    sub = p.add_subparsers(dest="command")

    sp = sub.add_parser("calendars", help="접근 가능한 캘린더 목록")
    sp.set_defaults(func=cmd_calendars)

    for name, fn, helptext in (
            ("list", cmd_list, "다가오는 일정 나열"),
            ("agenda", cmd_agenda, "다가오는 일정을 날짜별로 묶어 보기")):
        sp = sub.add_parser(name, help=helptext)
        sp.add_argument("--calendar", default="primary", help="캘린더 ID (기본 primary)")
        sp.add_argument("--days", type=int, default=7, help="앞으로 며칠 (기본 7)")
        sp.add_argument("--max", type=int, default=50, help="최대 건수 (기본 50)")
        sp.set_defaults(func=fn)

    sp = sub.add_parser("add-event", help="일정 생성 (--write 필요)")
    sp.add_argument("--calendar", default="primary")
    sp.add_argument("--summary", required=True, help="일정 제목")
    sp.add_argument("--start", required=True,
                    help="시작 (2026-08-20 또는 2026-08-20T14:00:00)")
    sp.add_argument("--end", required=True, help="종료 (형식은 --start 와 동일)")
    sp.add_argument("--description")
    sp.add_argument("--location")
    sp.add_argument("--attendee", action="append",
                    help="참석자 이메일 (반복 지정 가능) — 지정 시 초대장 발송")
    sp.add_argument("--write", action="store_true",
                    help="실제 생성. 없으면 미리보기만")
    sp.set_defaults(func=cmd_add_event)
    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    if not getattr(args, "command", None):
        parser.print_help()
        print("\n[안내] 읽기(calendars/list/agenda)는 바로 실행됩니다. "
              "쓰기(add-event)는 --write 가 있어야 실행됩니다.")
        return
    # dry-run(쓰기 명령인데 --write 없음)은 토큰 없이도 미리보기 가능하게 한다.
    is_dryrun_write = hasattr(args, "write") and not args.write
    token = None if is_dryrun_write else gauth.access_token()
    args.func(args, token)


if __name__ == "__main__":
    main()
