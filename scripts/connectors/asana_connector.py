#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Asana REST API connector — read-first / write-guarded (AGENTS.md §9).

`me` and `tasks` are free reads. Writes (`add-task`, `add-comment`,
`add-subtask`) all require the explicit --write flag; without it, only a
dry-run preview is printed. Assigning to someone other than 'me' prints an
outward-action notice. There is no complete/delete subcommand.

형식 규칙(사용자가 겪던 '형식 이상' 방지 — 랩 검증):
- 모든 요청은 ensure_ascii=False + charset=utf-8 → 한글 안 깨짐.
- 서식 댓글/설명(--html / --html-notes)은 sanitize_html() 이 강제: <body> 래핑,
  <p> 금지(xml_parsing_error), 줄바꿈은 실제 개행(\n) 그대로, '→' 문자 금지.
  (&#10; 엔티티는 Asana sanitizer 가 &amp;#10; 로 재이스케이프해 리터럴 노출 —
  issue #4 실측. 레거시 입력의 &#10; 은 자동으로 실제 개행으로 복원한다.)
- 기본 댓글/설명은 plain text (짧은 글엔 이게 안전).
"""
from __future__ import annotations

# Windows 기본 콘솔은 cp949 라서 한글/기호 출력에서 죽는다. UTF-8로 맞춘다.
# reconfigure 를 쓴다: TextIOWrapper 로 감싸면 원본 스트림을 소유하게 되어,
# 이 모듈이 import 된 뒤 래퍼가 GC 될 때 호출자의 stdout 까지 닫는다(실측).
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
    """urllib 기반 최소 HTTP 헬퍼. 파싱된 JSON을 반환하거나 친절한 한글 오류로 종료."""
    hdrs = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "sci-toolkit-asana-connector",
    }
    if headers:
        hdrs.update(headers)
    body = None
    if data is not None:
        # ensure_ascii=False 필수 — 한글/비ASCII가 \uXXXX 로 깨지지 않게 (랩 검증 규칙).
        # charset=utf-8 명시 — 댓글·하위작업의 한글 본문 보존.
        body = json.dumps({"data": data}, ensure_ascii=False).encode("utf-8")
        hdrs["Content-Type"] = "application/json; charset=utf-8"
    req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        if e.code == 401:
            sys.exit(f"[오류] 인증 실패(401). 토큰(asana.token)을 확인하세요. (마스킹: {cred.mask(token)})")
        if e.code == 403:
            sys.exit("[오류] 403 — API 요청 한도 초과 또는 권한 부족일 수 있습니다.")
        if e.code == 404:
            sys.exit("[오류] 404 — 리소스를 찾을 수 없습니다. gid/workspace 값을 확인하세요.")
        detail = ""
        try:
            detail = e.read().decode("utf-8", "ignore")
        except Exception:
            pass
        sys.exit(f"[오류] Asana API 오류 {e.code}: {detail[:300]}")
    except urllib.error.URLError as e:
        sys.exit(f"[오류] 네트워크 연결을 확인하세요: {e.reason}")


def cmd_me(args, token):
    data = http("GET", f"{API_ROOT}/users/me", token)
    me = data.get("data", {})
    print(f"이름: {me.get('name')}")
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
        print("[안내] --workspace gid 가 필요합니다. 사용 가능한 workspace:")
        for w in ws:
            print(f"  - {w.get('name')} (gid={w.get('gid')})")
        print("예: asana_connector.py tasks --workspace <gid>")
        return
    url = f"{API_ROOT}/tasks?assignee=me&workspace={args.workspace}&opt_fields=name,completed,due_on"
    data = http("GET", url, token)
    items = data.get("data", [])
    print(f"내 작업 {len(items)}건 (workspace={args.workspace})")
    for t in items:
        status = "완료" if t.get("completed") else "진행중"
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
        print("[알림] 남에게 배정되는 작업입니다 — 외부로 나가는(outward) 동작입니다.")

    if not args.write:
        print("[DRY-RUN] --write 플래그가 없어 실제로 실행하지 않습니다.")
        print("  생성될 작업:")
        print(json.dumps(body_preview, ensure_ascii=False, indent=2))
        print("  실행하려면 --write 를 추가하세요.")
        return

    if is_outward:
        print(f"[알림] {args.assignee} 에게 작업이 배정됩니다. 계속 진행합니다 (--write 지정됨).")

    result = http("POST", f"{API_ROOT}/tasks", token, data=body_preview)
    created = result.get("data", {})
    print(f"[완료] 작업 생성됨: {created.get('name')} (gid={created.get('gid')})")


# Asana html_text/html_notes 허용 태그 (이 밖의 태그, 특히 <p> 는 xml_parsing_error).
_ALLOWED_HTML_TAGS = ("body", "strong", "em", "u", "s", "code",
                      "a", "ul", "ol", "li", "h1", "h2", "table", "tr", "td")


def sanitize_html(html):
    """Asana html_text 형식 규칙을 강제/점검한다 (사용자가 겪던 '형식 이상' 방지).

    규칙(랩 검증): ①<body>...</body> 래핑 필수 ②<p> 금지(xml_parsing_error)
    ③줄바꿈은 실제 개행 문자(\\n) 그대로 — &#10; 엔티티는 Asana sanitizer 가
    &amp;#10; 로 재이스케이프해 화면에 리터럴 노출된다(issue #4 실측)
    ④'→' 화살표 문자 금지(XML 파싱 에러).
    위반이 자동교정 불가하면 오류로 알려 준다.
    """
    if "→" in html:
        sys.exit("[형식 오류] html_text 에 '→' 문자는 XML 파싱 오류를 냅니다. "
                 "'->' 또는 단어로 바꾸세요.")
    if "<p>" in html or "</p>" in html:
        sys.exit("[형식 오류] <p> 태그는 Asana 에서 xml_parsing_error 를 냅니다. "
                 "줄바꿈은 실제 개행 문자를 그대로 쓰세요.")
    # <body> 래핑 자동 보정
    if "<body>" not in html:
        html = f"<body>{html}</body>"
    # 개행 정규화: CRLF → LF. 레거시 &#10; 입력(과거 도움말이 안내하던 형식)은
    # 실제 개행으로 복원한다 — Asana 는 html_text 안의 진짜 LF 만 줄바꿈으로 렌더링.
    html = html.replace("\r\n", "\n").replace("&#10;", "\n")
    return html


def cmd_add_comment(args, token):
    """작업에 댓글(story)을 단다. 기본은 plain text, --html 이면 형식 검증 후 html_text."""
    if args.html:
        payload = {"html_text": sanitize_html(args.text)}
        kind = "html_text (형식 검증됨)"
    else:
        payload = {"text": args.text}
        kind = "text (일반)"

    if not args.write:
        print("[DRY-RUN] --write 플래그가 없어 실제로 실행하지 않습니다.")
        print(f"  대상 작업 gid: {args.task}")
        print(f"  댓글 형식: {kind}")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print("  실행하려면 --write 를 추가하세요.")
        return

    print("[알림] 댓글은 남에게 보이는 외부 동작입니다.")
    result = http("POST", f"{API_ROOT}/tasks/{args.task}/stories", token, data=payload)
    story = result.get("data", {})
    print(f"[완료] 댓글 등록됨 (gid={story.get('gid')})")

    # 등록 직후 자체 검증 (issue #4 회귀 방지): 재조회한 html_text 에 &#10; 이
    # 남아 있으면 개행이 리터럴로 노출되고 있는 것 — 실패로 알린다.
    if args.html and story.get("gid"):
        try:
            fetched = http("GET",
                           f"{API_ROOT}/stories/{story['gid']}?opt_fields=html_text",
                           token)
            html_text = (fetched.get("data") or {}).get("html_text") or ""
            if "#10;" in html_text:
                sys.exit("[검증 실패] 등록된 댓글에 &#10; 리터럴이 남아 있습니다 "
                         "(줄바꿈 미적용). issue #4 회귀 — 코드를 확인하세요.")
            print("[검증] 재조회 결과 &#10; 리터럴 없음 — 줄바꿈 정상.")
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001 — 댓글 자체는 이미 등록됨
            print(f"[주의] 등록 후 재조회 검증 실패(댓글은 등록됨): {exc}")


def cmd_add_subtask(args, token):
    """부모 작업 아래 하위작업을 만든다 (/tasks/{parent}/subtasks 전용 엔드포인트)."""
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
        print("[알림] 하위작업이 남에게 배정됩니다 — 외부로 나가는(outward) 동작입니다.")

    if not args.write:
        print("[DRY-RUN] --write 플래그가 없어 실제로 실행하지 않습니다.")
        print(f"  부모 작업 gid: {args.parent}")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print("  실행하려면 --write 를 추가하세요.")
        return

    result = http("POST", f"{API_ROOT}/tasks/{args.parent}/subtasks", token, data=payload)
    created = result.get("data", {})
    print(f"[완료] 하위작업 생성됨: {created.get('name')} (gid={created.get('gid')})")


def build_parser():
    p = argparse.ArgumentParser(
        prog="asana_connector.py",
        description=(
            "Asana REST 커넥터 (read-first). me/tasks 는 자유 조회, "
            "add-task 만 쓰기 동작이며 --write 필요. 남에게 배정 시 outward 알림 표시. "
            "complete/delete 서브커맨드는 존재하지 않습니다."
        ),
    )
    sub = p.add_subparsers(dest="command")

    sp = sub.add_parser("me", help="[READ] 내 프로필/워크스페이스")
    sp.set_defaults(func=cmd_me)

    sp = sub.add_parser("tasks", help="[READ] 내 작업 목록")
    sp.add_argument("--workspace", default=None, help="workspace gid (없으면 목록 안내)")
    sp.set_defaults(func=cmd_tasks)

    sp = sub.add_parser("add-task", help="[WRITE, --write 필요] 작업 생성")
    sp.add_argument("--workspace", required=True)
    sp.add_argument("--name", required=True)
    sp.add_argument("--notes", default="")
    sp.add_argument("--assignee", default=None, help="'me' 또는 다른 사람 gid/email (미지정 시 배정 안함)")
    sp.add_argument("--write", action="store_true", help="실제로 작업을 생성합니다 (없으면 dry-run)")
    sp.set_defaults(func=cmd_add_task)

    sp = sub.add_parser("add-comment", help="[WRITE, --write 필요] 작업에 댓글 달기")
    sp.add_argument("--task", required=True, help="댓글을 달 작업 gid")
    sp.add_argument("--text", required=True, help="댓글 내용")
    sp.add_argument("--html", action="store_true",
                    help="서식 있는 댓글(html_text). <body>자동래핑·<p>금지·실제개행(\\n)줄바꿈·→금지 검증됨")
    sp.add_argument("--write", action="store_true", help="실제로 댓글을 답니다 (없으면 dry-run)")
    sp.set_defaults(func=cmd_add_comment)

    sp = sub.add_parser("add-subtask", help="[WRITE, --write 필요] 하위작업 생성")
    sp.add_argument("--parent", required=True, help="부모 작업 gid")
    sp.add_argument("--name", required=True, help="하위작업 이름")
    sp.add_argument("--notes", default="", help="설명(기본 plain, --html-notes 시 서식)")
    sp.add_argument("--html-notes", dest="html_notes", action="store_true",
                    help="설명을 html_notes 로(형식 검증 동일 적용)")
    sp.add_argument("--assignee", default=None, help="'me' 또는 다른 사람 gid (미지정 시 배정 안함)")
    sp.add_argument("--workspace", default=None, help="workspace gid (필요 시)")
    sp.add_argument("--write", action="store_true", help="실제로 생성합니다 (없으면 dry-run)")
    sp.set_defaults(func=cmd_add_subtask)

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    if not getattr(args, "command", None):
        parser.print_help()
        print("\n[안내] 읽기(me/tasks)는 바로 실행됩니다. 쓰기(add-task/add-comment/add-subtask)는 --write 가 있어야 실행됩니다.")
        return
    # dry-run(쓰기 명령인데 --write 없음)은 토큰 없이도 미리보기 가능하게 한다.
    is_dryrun_write = hasattr(args, "write") and not args.write
    token = None if is_dryrun_write else cred.require("asana", "token")
    args.func(args, token)


if __name__ == "__main__":
    main()
