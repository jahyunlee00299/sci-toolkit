#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Notion DATABASE API connector — read-first / write-guarded (AGENTS.md §9).

`list-dbs`, `schema`, `query` are free reads. `add-row` is the only write
action and requires the explicit --write flag; without it, only a dry-run
preview of the page payload is printed. This script is strictly additive —
there is no delete/archive subcommand at all (Notion "delete" is really an
archive; we simply never call it here).

⚠️ 가장 흔한 함정: 이 스크립트가 쓰는 Integration 토큰이 있어도, 그 Integration을
**대상 데이터베이스에 먼저 공유(Connections)해주지 않으면** list-dbs 에도 안 잡히고
schema/query 도 404 로 실패합니다. Notion에서 해당 데이터베이스 페이지를 열고
우측 상단 "..." 메뉴 → 연결(Connections) → 사용 중인 Integration 을 선택해
공유해주세요. (docs/07_노션_연동_가이드.md 참고)
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

API_ROOT = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def http(method, url, token, data=None, headers=None):
    """urllib 기반 최소 HTTP 헬퍼. 파싱된 JSON을 반환하거나 친절한 한글 오류로 종료."""
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
                f"[오류] 인증 실패(401). 토큰(notion.token)을 확인하세요. "
                f"(마스킹: {cred.mask(token)})"
            )
        if e.code == 403:
            sys.exit(
                "[오류] 403 — 권한 부족입니다. 이 데이터베이스에 Integration이 "
                "공유(Connections)되지 않았을 수 있습니다. Notion에서 DB 페이지 우측 "
                "'...' → 연결 → Integration 선택 후 다시 시도하세요."
            )
        if e.code == 404:
            sys.exit(
                "[오류] 404 — 데이터베이스를 찾을 수 없습니다. --db 값(32자리 id)을 "
                "확인하거나, 이 데이터베이스에 Integration이 아직 공유되지 않았을 수 "
                "있습니다('...' → 연결 → Integration 선택). list-dbs 로 보이는 목록에 "
                "있는지 먼저 확인하세요."
            )
        if e.code == 400:
            detail = ""
            try:
                detail = e.read().decode("utf-8", "ignore")
            except Exception:
                pass
            sys.exit(
                "[오류] 400 — 요청이 잘못됐습니다. 속성 이름/타입이 실제 데이터베이스와 "
                "다를 수 있습니다. 먼저 `schema --db <id>` 로 정확한 속성명과 타입을 "
                f"확인한 뒤 --prop 값을 맞춰서 다시 시도하세요.\n  상세: {detail[:300]}"
            )
        detail = ""
        try:
            detail = e.read().decode("utf-8", "ignore")
        except Exception:
            pass
        sys.exit(f"[오류] Notion API 오류 {e.code}: {detail[:300]}")
    except urllib.error.URLError as e:
        sys.exit(f"[오류] 네트워크 연결을 확인하세요: {e.reason}")


def _title_of(props: dict) -> str:
    """properties dict 에서 title 타입 속성의 평문 텍스트를 뽑아낸다."""
    for v in props.values():
        if v.get("type") == "title" and v.get("title"):
            return "".join(t.get("plain_text", "") for t in v["title"])
    return "(제목 없음)"


def _status_of(props: dict) -> str:
    """properties dict 에서 status 또는 select 타입 값을 사람이 읽기 쉽게 뽑아낸다."""
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
    print(f"연결(Connections)된 데이터베이스 {len(results)}건")
    if not results:
        print(
            "  (없음) → 이 Integration에 아직 공유된 데이터베이스가 없을 수 있습니다.\n"
            "  Notion에서 대상 DB 페이지 우측 '...' → 연결(Connections) → Integration "
            "선택으로 공유해주세요."
        )
        return
    for r in results:
        title = "(제목 없음)"
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
    title = "(제목 없음)"
    if data.get("title"):
        title = "".join(t.get("plain_text", "") for t in data["title"])
    print(f"데이터베이스: {title} (id={data.get('id')})")
    props = data.get("properties", {})
    print(f"속성 {len(props)}개:")
    for name, v in props.items():
        print(f"  - {name}  [{v.get('type')}]")


def cmd_query(args, token):
    body = {"page_size": args.limit}
    if args.sort:
        prop, _, direction = args.sort.partition(":")
        direction = direction or "ascending"
        if direction not in ("ascending", "descending"):
            sys.exit(f"[오류] --sort 방향은 ascending/descending 중 하나여야 합니다: {direction}")
        body["sorts"] = [{"property": prop, "direction": direction}]
    if args.status:
        # 스키마를 먼저 조회해 Status 속성 실제 타입(status/select)을 확인
        schema = _get_schema(args.db, token)
        props = schema.get("properties", {})
        status_prop_name = None
        status_prop_type = None
        for name, v in props.items():
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
            print("[안내] status/select 타입 속성을 찾지 못해 --status 필터를 건너뜁니다.")

    data = http("POST", f"{API_ROOT}/databases/{args.db}/query", token, data=body)
    results = data.get("results", [])
    print(f"조회 결과 {len(results)}건 (limit={args.limit})")
    for r in results:
        props = r.get("properties", {})
        title = _title_of(props)
        status = _status_of(props)
        print(f"  - [{status}] {title}  (id={r.get('id')})")


def _build_property_payload(prop_type, name, raw_value):
    """스키마에서 확인된 property TYPE에 맞춰 Notion API 페이로드 조각을 만든다."""
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
            sys.exit(f"[오류] '{name}' 은 number 타입인데 숫자로 변환할 수 없습니다: {raw_value}")
        return {"number": num}
    if prop_type == "date":
        return {"date": {"start": raw_value}}
    if prop_type == "checkbox":
        truthy = raw_value.strip().lower() in ("true", "1", "yes", "y", "예", "체크")
        return {"checkbox": truthy}
    sys.exit(
        f"[오류] '{name}' 속성 타입 '{prop_type}' 은 이 스크립트가 아직 지원하지 않습니다. "
        "지원 타입: title, rich_text, select, multi_select, status, number, date, checkbox"
    )


def cmd_add_row(args, token):
    # add-row 의 dry-run 은 실제 스키마를 읽어야 성립한다 — 속성명이 존재하는지,
    # 타입이 무엇인지 모르면 미리보기가 "이 페이로드가 맞다"고 말해줄 수 없다.
    # 그래서 이 명령만은 dry-run 에도 토큰을 요구한다. 토큰 없이 만든 미리보기를
    # 보여주는 편이 친절해 보이지만, 검증되지 않은 페이로드를 검증된 것처럼
    # 보여주는 셈이라 더 나쁘다.
    if token is None:
        sys.exit(
            "[오류] add-row 는 --write 없이도 Notion 토큰이 필요합니다.\n"
            "  미리보기가 속성명·타입을 실제 스키마와 대조해야 의미가 있기 때문입니다.\n"
            "  토큰 설정: python scripts/connectors/register_token.py"
        )
    schema = _get_schema(args.db, token)
    props_schema = schema.get("properties", {})

    title_prop_name = None
    for name, v in props_schema.items():
        if v.get("type") == "title":
            title_prop_name = name
            break
    if title_prop_name is None:
        sys.exit("[오류] 이 데이터베이스에서 title 속성을 찾지 못했습니다.")

    page_props = {
        title_prop_name: _build_property_payload("title", title_prop_name, args.title)
    }

    for raw in args.prop or []:
        if "=" not in raw:
            sys.exit(f"[오류] --prop 형식이 잘못됐습니다 (NAME=VALUE 형태 필요): {raw}")
        name, value = raw.split("=", 1)
        name = name.strip()
        if name not in props_schema:
            available = ", ".join(sorted(props_schema.keys()))
            sys.exit(
                f"[오류] '{name}' 은 이 데이터베이스에 없는 속성입니다.\n"
                f"  `schema --db {args.db}` 로 실제 속성명을 먼저 확인하세요.\n"
                f"  사용 가능한 속성: {available}"
            )
        prop_type = props_schema[name].get("type")
        page_props[name] = _build_property_payload(prop_type, name, value)

    body_preview = {
        "parent": {"database_id": args.db},
        "properties": page_props,
    }

    if not args.write:
        print("[DRY-RUN] --write 플래그가 없어 실제로 실행하지 않습니다.")
        print(f"  대상 데이터베이스: {args.db}")
        print("  생성될 페이지(properties):")
        print(json.dumps(body_preview, ensure_ascii=False, indent=2))
        print("  실행하려면 --write 를 추가하세요.")
        return

    print("[알림] 데이터베이스에 새 항목(페이지)을 추가합니다 (additive only, 삭제/보관 기능 없음).")
    result = http("POST", f"{API_ROOT}/pages", token, data=body_preview)
    print(f"[완료] 항목 생성됨 (id={result.get('id')})")
    if result.get("url"):
        print(f"  url: {result.get('url')}")


def build_parser():
    p = argparse.ArgumentParser(
        prog="notion_db_connector.py",
        description=(
            "Notion DATABASE 커넥터 (read-first). list-dbs/schema/query 는 자유 조회, "
            "add-row 만 쓰기 동작이며 --write 필요(추가만 가능, 삭제/보관 서브커맨드는 없습니다). "
            "대상 데이터베이스에 Integration이 미리 공유(Connections)되어 있어야 합니다."
        ),
    )
    sub = p.add_subparsers(dest="command")

    sp = sub.add_parser("list-dbs", help="[READ] 접근 가능한 데이터베이스 목록")
    sp.set_defaults(func=cmd_list_dbs)

    sp = sub.add_parser("schema", help="[READ] 데이터베이스 속성(스키마) 조회")
    sp.add_argument("--db", required=True, help="database id (32자리)")
    sp.set_defaults(func=cmd_schema)

    sp = sub.add_parser("query", help="[READ] 데이터베이스 행 조회")
    sp.add_argument("--db", required=True, help="database id (32자리)")
    sp.add_argument("--limit", type=int, default=10, help="최대 조회 개수 (기본 10)")
    sp.add_argument(
        "--status", default=None, help="status/select 속성 값으로 간단 필터 (예: 'In progress')"
    )
    sp.add_argument(
        "--sort", default=None,
        help="PROPERTY[:ascending|descending] 형태 정렬 (기본 ascending). "
             "예: --sort 'Date:descending' — 최근 N건 조회에 사용",
    )
    sp.set_defaults(func=cmd_query)

    sp = sub.add_parser("add-row", help="[WRITE, --write 필요] 데이터베이스에 새 항목 추가")
    sp.add_argument("--db", required=True, help="database id (32자리)")
    sp.add_argument("--title", required=True, help="title 속성 값")
    sp.add_argument(
        "--prop",
        action="append",
        default=[],
        help="NAME=VALUE 형태, 반복 가능 (예: --prop Status='In progress' --prop Tags=a,b)",
    )
    sp.add_argument("--write", action="store_true", help="실제로 항목을 추가합니다 (없으면 dry-run)")
    sp.set_defaults(func=cmd_add_row)

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    if not getattr(args, "command", None):
        parser.print_help()
        print(
            "\n[안내] 읽기(list-dbs/schema/query)는 바로 실행됩니다. "
            "쓰기(add-row)는 --write 가 있어야 실행됩니다."
        )
        return
    # dry-run(쓰기 명령인데 --write 없음)은 토큰 없이도 미리보기 가능하게 한다.
    is_dryrun_write = hasattr(args, "write") and not args.write
    token = None if is_dryrun_write else cred.require("notion", "token")
    args.func(args, token)


if __name__ == "__main__":
    main()
