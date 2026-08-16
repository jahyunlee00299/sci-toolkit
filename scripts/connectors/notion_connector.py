#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Notion API connector — read-first / write-guarded (AGENTS.md §9).

`search` and `page` are free reads. `append` is the only write action and
requires the explicit --write flag; without it, only a dry-run preview of
the block that would be appended is printed. append is strictly additive —
this script has no delete/archive subcommand at all.
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
            sys.exit(f"[오류] 인증 실패(401). 토큰(notion.token)을 확인하세요. (마스킹: {cred.mask(token)})")
        if e.code == 403:
            sys.exit("[오류] 403 — 권한 부족(해당 페이지에 integration이 연결되지 않았을 수 있음).")
        if e.code == 404:
            sys.exit("[오류] 404 — 페이지/블록을 찾을 수 없습니다. id 를 확인하세요.")
        detail = ""
        try:
            detail = e.read().decode("utf-8", "ignore")
        except Exception:
            pass
        sys.exit(f"[오류] Notion API 오류 {e.code}: {detail[:300]}")
    except urllib.error.URLError as e:
        sys.exit(f"[오류] 네트워크 연결을 확인하세요: {e.reason}")


def cmd_search(args, token):
    body = {"query": args.query}
    data = http("POST", f"{API_ROOT}/search", token, data=body)
    results = data.get("results", [])
    print(f"검색어 '{args.query}' 결과 {len(results)}건")
    for r in results:
        obj_type = r.get("object")
        title = "(제목 없음)"
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
            print(f"제목({name}): {title}")


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
        print("[DRY-RUN] --write 플래그가 없어 실제로 실행하지 않습니다.")
        print(f"  대상 페이지: {args.page_id}")
        print("  추가될 블록 (paragraph):")
        print(json.dumps(block_body, ensure_ascii=False, indent=2))
        print("  실행하려면 --write 를 추가하세요.")
        return

    print("[알림] 페이지에 블록을 추가합니다 (additive only, 삭제/보관 기능 없음).")
    url = f"{API_ROOT}/blocks/{args.page_id}/children"
    result = http("PATCH", url, token, data=block_body)
    added = result.get("results", [])
    print(f"[완료] 블록 {len(added)}개 추가됨.")


def build_parser():
    p = argparse.ArgumentParser(
        prog="notion_connector.py",
        description=(
            "Notion API 커넥터 (read-first). search/page 는 자유 조회, "
            "append 만 쓰기 동작이며 --write 필요(추가만 가능, 삭제/보관 서브커맨드는 없습니다)."
        ),
    )
    sub = p.add_subparsers(dest="command")

    sp = sub.add_parser("search", help="[READ] 검색")
    sp.add_argument("--query", required=True)
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("page", help="[READ] 페이지 조회")
    sp.add_argument("--id", required=True, help="page id")
    sp.set_defaults(func=cmd_page)

    sp = sub.add_parser("append", help="[WRITE, --write 필요] 페이지에 텍스트 블록 추가")
    sp.add_argument("--page-id", required=True)
    sp.add_argument("--text", required=True)
    sp.add_argument("--write", action="store_true", help="실제로 블록을 추가합니다 (없으면 dry-run)")
    sp.set_defaults(func=cmd_append)

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    if not getattr(args, "command", None):
        parser.print_help()
        print("\n[안내] 읽기(search/page)는 바로 실행됩니다. 쓰기(append)는 --write 가 있어야 실행됩니다.")
        return
    # dry-run(쓰기 명령인데 --write 없음)은 토큰 없이도 미리보기 가능하게 한다.
    is_dryrun_write = hasattr(args, "write") and not args.write
    token = None if is_dryrun_write else cred.require("notion", "token")
    args.func(args, token)


if __name__ == "__main__":
    main()
