#!/usr/bin/env python3
"""Google Sheets 커넥터 — 읽기 자유, 쓰기는 append 전용 + --write 게이트.

    python sheets_connector.py info   --sheet <ID>
    python sheets_connector.py read   --sheet <ID> --range "Sheet1!A1:D20"
    python sheets_connector.py append --sheet <ID> --range "Sheet1!A:D" --row "a,b,c,d"
    python sheets_connector.py append ... --write        # 실제 추가

🔴 왜 append 만 있고 update 가 없는가
------------------------------------
공유 시트의 기존 셀을 덮어쓰면 **남이 넣은 값이 사라진다.** 그 실수는 되돌릴
수단이 사실상 없다(구글 버전기록을 사람이 직접 뒤져야 한다). 그래서 이 커넥터는
행 추가만 제공한다 — Notion 커넥터가 additive-only 인 것과 같은 이유다.
기존 값을 고쳐야 하면 사람이 브라우저에서 직접 한다. AGENTS.md §9.

시트 ID 는 URL 에서 딴다:
    https://docs.google.com/spreadsheets/d/<여기가 ID>/edit#gid=0
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
    """--row 문자열을 셀 목록으로. CSV 규칙을 따라 따옴표 안 쉼표를 보존한다.

    `--row 'a,"b,c",d'` 를 단순 split(",") 하면 셀이 4개가 되어 조용히 밀린다.
    """
    return next(csv.reader(io.StringIO(raw)), [])


def cmd_info(args, token):
    data = gauth.api_get(f"{API_ROOT}/{args.sheet}", token,
                         {"fields": "properties.title,sheets.properties"})
    print(f"[스프레드시트] {data.get('properties', {}).get('title', '(제목없음)')}")
    for sh in data.get("sheets", []):
        p = sh.get("properties", {})
        g = p.get("gridProperties", {})
        print(f"  - {p.get('title')}  "
              f"({g.get('rowCount', '?')}행 x {g.get('columnCount', '?')}열)")


def cmd_read(args, token):
    data = gauth.api_get(
        f"{API_ROOT}/{args.sheet}/values/{args.range}", token,
        {"majorDimension": "ROWS"})
    rows = data.get("values", [])
    if not rows:
        print(f"[결과] 범위에 값이 없습니다 ({args.range}).")
        return
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    # 열 너비를 맞춰 읽기 좋게. 구글은 뒤쪽 빈 셀을 생략해 행마다 길이가 다르다.
    width = max(len(r) for r in rows)
    norm = [list(r) + [""] * (width - len(r)) for r in rows]
    colw = [max(len(str(r[i])) for r in norm) for i in range(width)]
    print(f"[{args.range}] {len(rows)}행")
    for r in norm:
        print("  " + " | ".join(str(v).ljust(colw[i]) for i, v in enumerate(r)))


def cmd_append(args, token):
    values = [_split_row(args.row)]
    body = {"values": values}

    if not args.write:
        print("[DRY-RUN] --write 플래그가 없어 실제로 실행하지 않습니다.")
        print(f"  대상 시트: {args.sheet}")
        print(f"  대상 범위: {args.range}")
        print(f"  추가될 행 ({len(values[0])}개 셀):")
        print(json.dumps(values[0], ensure_ascii=False, indent=2))
        print("  실행하려면 --write 를 추가하세요.")
        return

    print("[알림] 공유 시트에 행을 추가합니다 (additive only, 기존 셀 수정/삭제 없음).")
    result = gauth.api_post(
        f"{API_ROOT}/{args.sheet}/values/{args.range}:append", token, body,
        params={
            "valueInputOption": "USER_ENTERED",   # 사람이 입력한 것처럼 해석(날짜·수식)
            "insertDataOption": "INSERT_ROWS",    # 기존 행 덮어쓰기 금지, 항상 새 행
        })
    upd = result.get("updates", {})
    print(f"[완료] {upd.get('updatedRows', 0)}행 추가됨 "
          f"({upd.get('updatedRange', '?')})")


def build_parser():
    p = argparse.ArgumentParser(
        description="Google Sheets 커넥터 (읽기 자유 / 추가는 --write, 수정·삭제 없음)")
    sub = p.add_subparsers(dest="command")

    sp = sub.add_parser("info", help="시트 제목·탭·크기")
    sp.add_argument("--sheet", required=True, help="스프레드시트 ID (URL 의 /d/<ID>/)")
    sp.set_defaults(func=cmd_info)

    sp = sub.add_parser("read", help="범위 값 읽기")
    sp.add_argument("--sheet", required=True)
    sp.add_argument("--range", required=True, help='예: "Sheet1!A1:D20"')
    sp.add_argument("--json", action="store_true", help="정렬 표 대신 JSON 출력")
    sp.set_defaults(func=cmd_read)

    sp = sub.add_parser("append", help="행 추가 (--write 필요)")
    sp.add_argument("--sheet", required=True)
    sp.add_argument("--range", required=True, help='추가 대상 범위, 예: "Sheet1!A:D"')
    sp.add_argument("--row", required=True,
                    help='쉼표로 구분한 셀 값. 쉼표를 넣으려면 "a,\\"b,c\\",d"')
    sp.add_argument("--write", action="store_true",
                    help="실제 추가. 없으면 미리보기만")
    sp.set_defaults(func=cmd_append)
    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    if not getattr(args, "command", None):
        parser.print_help()
        print("\n[안내] 읽기(info/read)는 바로 실행됩니다. "
              "추가(append)는 --write 가 있어야 실행됩니다. 수정·삭제는 제공하지 않습니다.")
        return
    # dry-run(쓰기 명령인데 --write 없음)은 토큰 없이도 미리보기 가능하게 한다.
    is_dryrun_write = hasattr(args, "write") and not args.write
    token = None if is_dryrun_write else gauth.access_token()
    args.func(args, token)


if __name__ == "__main__":
    main()
