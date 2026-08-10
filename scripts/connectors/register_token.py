#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Register a freshly-issued API token into config/credentials.json --
without the value ever appearing in a Claude Code conversation.

Why this exists
----------------
docs/13 walks a first-time user through Chrome to the right token page, but
stops at "생성 버튼과 값 복사는 본인이" -- Claude never reads the value back,
because anything Claude reads becomes part of the session transcript. That
principle stays. What used to be missing was the last step: pasting the value
into config/credentials.json by hand (find the file, find the nested key,
match the JSON quoting). This script closes that gap WITHOUT weakening the
principle -- it must be run directly in the user's own terminal (suggest the
`! <command>` prefix in Claude Code), never through a Claude tool call, so the
token goes keyboard -> getpass() -> file and nowhere else.

Usage (run this yourself, not through Claude):
    python scripts/connectors/register_token.py github
    python scripts/connectors/register_token.py notion
    python scripts/connectors/register_token.py asana
    python scripts/connectors/register_token.py mail --account personal
    python scripts/connectors/register_token.py mail --account work
    python scripts/connectors/register_token.py github --field username --value your-handle

If `python` isn't recognized on Windows (common with PATH-less installs), try
`py` instead -- it's the launcher most Windows Python installers register on
PATH even when `python` itself isn't:
    py scripts/connectors/register_token.py github

Google Calendar/Drive use OAuth, not a static token -- not handled here, see
docs/05_외부서비스_연동.md §4-4.
"""
from __future__ import annotations

import argparse
import getpass
import json
import shutil
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

ROOT = Path(__file__).resolve().parent.parent.parent
CRED_PATH = ROOT / "config" / "credentials.json"
EXAMPLE_PATH = ROOT / "config" / "credentials.example.json"

# service -> (nested path to the secret field, human label)
DEFAULT_FIELD = {
    "github": ["github", "token"],
    "notion": ["notion", "token"],
    "asana": ["asana", "token"],
    "mail": ["mail", "accounts", "work", "password"],
}

# mail is keyed by --account too (work/personal), unlike the single-token services
MAIL_ACCOUNTS = ("work", "personal")


def mask(secret: str) -> str:
    if not secret:
        return "(없음)"
    if len(secret) <= 6:
        return "*" * len(secret)
    return f"{secret[:2]}{'*' * (len(secret) - 4)}{secret[-2:]}"


def load_config() -> dict:
    if not CRED_PATH.exists():
        if not EXAMPLE_PATH.exists():
            sys.exit(f"[오류] {EXAMPLE_PATH} 도 없습니다 -- 저장소가 손상된 것 같습니다.")
        shutil.copy(EXAMPLE_PATH, CRED_PATH)
        print(f"[안내] {CRED_PATH.name} 이 없어 예시 템플릿에서 새로 만들었습니다.")
    with CRED_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def set_nested(cfg: dict, path: list[str], value: str) -> None:
    node = cfg
    for key in path[:-1]:
        node = node.setdefault(key, {})
    node[path[-1]] = value


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("service", choices=sorted(DEFAULT_FIELD), help="어떤 서비스 토큰인지")
    ap.add_argument("--account", choices=MAIL_ACCOUNTS, default="work",
                     help="mail 서비스 전용: work(업무) 또는 personal(개인) 중 어느 계정인지 (기본 work)")
    ap.add_argument("--field", nargs="+", default=None,
                     help="기본 필드 대신 다른 중첩 키 경로 (예: --field github username)")
    ap.add_argument("--value", default=None,
                     help="값을 인자로 바로 넘기려면 사용 (경고: 셸 히스토리에 남습니다 -- "
                          "터미널에서 직접 실행할 때만, 절대 Claude 도구 호출로 넘기지 마세요)")
    args = ap.parse_args(argv)

    if args.field:
        field_path = args.field
    elif args.service == "mail":
        field_path = ["mail", "accounts", args.account, "password"]
    else:
        field_path = DEFAULT_FIELD[args.service]
    label = " → ".join(field_path)

    if args.value is not None:
        value = args.value
        print("[경고] --value 는 셸 히스토리에 남습니다. 가능하면 인자 없이 실행해 "
              "숨김 입력을 쓰세요.", file=sys.stderr)
    else:
        value = getpass.getpass(
            f"'{label}' 값을 붙여넣고 Enter 를 누르세요 "
            f"(입력은 화면에 표시되지 않습니다): "
        ).strip()

    if not value:
        sys.exit("[오류] 빈 값입니다 -- 등록하지 않았습니다.")

    cfg = load_config()
    set_nested(cfg, field_path, value)
    with CRED_PATH.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"[등록됨] {label} = {mask(value)}  ({CRED_PATH})")
    print("확인: python scripts/connectors/_credentials.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
