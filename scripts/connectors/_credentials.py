#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""공통 자격증명 로더 — 모든 외부서비스 연동 스크립트가 이걸 통해 키를 읽는다.

보안 원칙 (AGENTS.md §9):
- 실제 키는 배포물에 절대 포함되지 않는다. config/credentials.json(=gitignore/distignore)
  또는 환경변수에서만 읽는다.
- 값이 "ENV:VARNAME" 형태면 그 환경변수에서 실제 값을 가져온다(키가 파일에도 안 남게).
- 토큰을 화면·로그에 출력하지 않는다(마스킹 헬퍼 제공).

사용:
    from _credentials import load, get, require
    cfg = load()                          # dict 전체
    tok = get("github", "token")          # ENV: 해석까지 끝난 실제 값(없으면 None)
    tok = require("github", "token")      # 없으면 친절한 오류로 종료
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

import json
import os
import sys
from pathlib import Path

# scripts/connectors/_credentials.py → toolkit root
ROOT = Path(__file__).resolve().parent.parent.parent
CRED_PATH = ROOT / "config" / "credentials.json"
EXAMPLE_PATH = ROOT / "config" / "credentials.example.json"


def _resolve_env(value):
    """'ENV:NAME' → os.environ['NAME']; 그 외 값은 그대로. 미설정 env는 None."""
    if isinstance(value, str) and value.startswith("ENV:"):
        return os.environ.get(value[4:])
    return value


def load() -> dict:
    """credentials.json 을 읽어 dict 반환. 없으면 안내 후 빈 dict."""
    if not CRED_PATH.exists():
        print(
            "[안내] 아직 자격증명 파일이 없습니다.\n"
            f"  {EXAMPLE_PATH.name} 를 같은 폴더에 credentials.json 으로 복사한 뒤\n"
            "  본인 계정 정보를 채우세요. 실제 키는 환경변수(ENV:...) 사용을 권장합니다.\n"
            "  (credentials.json 은 배포·커밋에서 제외됩니다.)",
            file=sys.stderr,
        )
        return {}
    with CRED_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def get(*path, cfg: dict | None = None):
    """중첩 키 경로로 값을 읽고 ENV: 를 해석해 실제 값 반환(없으면 None).

    예: get("mail", "accounts", "work", "password")
    """
    node = load() if cfg is None else cfg
    for k in path:
        if not isinstance(node, dict) or k not in node:
            return None
        node = node[k]
    return _resolve_env(node)


def require(*path, cfg: dict | None = None):
    """get() 과 같되, 값이 없으면 어떤 키/환경변수를 채워야 하는지 알려주고 종료."""
    val = get(*path, cfg=cfg)
    if val:
        return val
    key = " → ".join(path)
    sys.exit(
        f"[오류] 자격증명이 없습니다: {key}\n"
        f"  config/credentials.json 의 해당 항목을 채우거나, 값이 'ENV:NAME' 이면\n"
        f"  그 환경변수(NAME)를 설정하세요. 템플릿: config/credentials.example.json"
    )


def mask(secret) -> str:
    """토큰을 로그에 안전하게 찍기 위한 마스킹: 앞2·뒤2만 노출."""
    if not secret or not isinstance(secret, str):
        return "(없음)"
    if len(secret) <= 6:
        return "*" * len(secret)
    return f"{secret[:2]}{'*' * (len(secret) - 4)}{secret[-2:]}"


if __name__ == "__main__":
    # 진단: 어떤 서비스가 자격증명을 갖췄는지 (값은 마스킹) 보여준다.
    c = load()
    if not c:
        sys.exit(0)
    print("설정된 서비스(값은 마스킹):")
    for svc in ("mail", "github", "asana", "notion", "google"):
        node = c.get(svc)
        state = "설정됨" if node else "비어있음"
        print(f"  - {svc:8s}: {state}")
