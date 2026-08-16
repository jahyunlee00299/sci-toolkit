#!/usr/bin/env python3
"""Google OAuth2 액세스 토큰 — stdlib 전용, 기존 토큰 파일 재사용.

이 패키지의 커넥터는 전부 stdlib(urllib)만 쓴다. 폴더만 복사해도 돌아가는 것이
설계 원칙이고, 구글이라고 예외를 두면 그 원칙이 깨진다. 그래서
`google-api-python-client` 를 쓰지 않고 refresh-token 교환을 직접 한다.

동작
----
액세스 토큰은 1시간이면 만료되지만 **refresh token 은 오래 간다.** 그래서
최초 1회만 브라우저로 발급받고, 그 다음부터는 이 모듈이 갱신을 맡는다 —
라이브러리 없이, 네트워크 호출 한 번으로.

    토큰 파일 읽기 → 아직 유효? → 그대로 사용
                   → 만료됐나? → refresh_token 으로 새로 받아 파일에 갱신 저장

토큰 파일 형식
--------------
구글 OAuth 표준 형식을 그대로 읽는다:

    {"access_token": "...", "refresh_token": "...",
     "expiry_date": 1755300000000, "token_type": "Bearer"}

`expiry_date` 는 **밀리초**다(구글 클라이언트 라이브러리들의 관례). 초로 적힌
파일도 받아들이도록 자릿수를 보고 판별한다 — 여기서 1000배를 틀리면 "항상
만료됨"이 되어 매 호출마다 불필요한 갱신을 하거나, 반대로 만료된 토큰을
계속 쓰게 된다.

이미 다른 도구로 구글 토큰을 만들어 둔 사람은 그 경로를 그대로 가리키면 된다
(`credentials.json` 의 `google.token_cache_path`). 새로 만들 필요가 없다.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import _credentials as cred

TOKEN_URI = "https://oauth2.googleapis.com/token"
_SKEW_SEC = 60  # 만료 직전 갱신 여유


def _expiry_seconds(raw) -> float:
    """expiry 값을 초 단위로 정규화한다.

    구글 계열 도구는 밀리초로 적고, 손으로 만든 파일은 초로 적기도 한다.
    2001년 이후 초 단위 timestamp 는 10자리, 밀리초는 13자리라 자릿수로 가린다.
    """
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return 0.0
    return v / 1000.0 if v > 1e11 else v


def _read_json(path: Path, what: str) -> dict:
    if not path.exists():
        sys.exit(
            f"[오류] {what} 파일이 없습니다: {path}\n"
            f"  config/credentials.json 의 google 항목에서 경로를 확인하세요.\n"
            f"  최초 발급은 브라우저 동의가 필요해 스크립트로 자동화하지 않습니다 —\n"
            f"  scripts/connectors/README.md 의 구글 인증 절을 참고하세요."
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        sys.exit(f"[오류] {what} 파일을 읽지 못했습니다 ({path}): {exc}")


def _post_form(url: str, fields: dict) -> dict:
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:400]
        # invalid_grant = refresh token 폐기(비밀번호 변경·권한 취소·6개월 미사용).
        # 재발급 외에 방법이 없으므로 그렇게 안내한다.
        if "invalid_grant" in body:
            sys.exit(
                "[오류] refresh token 이 더 이상 유효하지 않습니다 (invalid_grant).\n"
                "  비밀번호 변경·권한 취소·장기 미사용 시 폐기됩니다. 재발급이 필요합니다.\n"
                f"  응답: {body}")
        sys.exit(f"[오류] 토큰 갱신 실패 (HTTP {exc.code}): {body}")
    except urllib.error.URLError as exc:
        sys.exit(f"[오류] 토큰 서버에 연결하지 못했습니다: {exc.reason}")


def access_token(cfg: dict | None = None) -> str:
    """유효한 access token 을 돌려준다. 필요하면 갱신하고 파일에 다시 쓴다."""
    token_path = Path(
        cred.require("google", "token_cache_path", cfg=cfg)).expanduser()
    token = _read_json(token_path, "구글 토큰")

    if time.time() < _expiry_seconds(token.get("expiry_date")) - _SKEW_SEC:
        tok = token.get("access_token")
        if tok:
            return tok
        # 만료 전인데 access_token 이 없다 = 파일이 깨졌다. 갱신으로 복구 시도.

    refresh = token.get("refresh_token")
    if not refresh:
        sys.exit(
            f"[오류] 토큰 파일에 refresh_token 이 없습니다: {token_path}\n"
            "  access token 만 있는 파일은 만료되면 되살릴 수 없습니다. 재발급하세요.")

    client_path = Path(
        cred.require("google", "oauth_client_path", cfg=cfg)).expanduser()
    raw = _read_json(client_path, "OAuth 클라이언트")
    # 구글 콘솔이 내려주는 JSON 은 {"installed": {...}} 또는 {"web": {...}} 로 감싼다.
    client = raw.get("installed") or raw.get("web") or raw

    new = _post_form(TOKEN_URI, {
        "client_id": client["client_id"],
        "client_secret": client["client_secret"],
        "refresh_token": refresh,
        "grant_type": "refresh_token",
    })

    token["access_token"] = new["access_token"]
    token["expiry_date"] = int(
        (time.time() + float(new.get("expires_in", 3600))) * 1000)
    try:
        token_path.write_text(
            json.dumps(token, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        # 캐시 저장 실패는 치명적이지 않다 — 이번 호출은 계속 진행한다.
        print(f"[경고] 갱신된 토큰을 저장하지 못했습니다 ({exc}). "
              f"다음 실행 때 다시 갱신합니다.", file=sys.stderr)
    return token["access_token"]


def api_get(url: str, token: str, params: dict | None = None) -> dict:
    """구글 API GET. 읽기 전용 경로에서만 쓴다."""
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:400]
        if exc.code == 403:
            sys.exit(
                f"[오류] 권한이 없습니다 (HTTP 403). 토큰의 scope 를 확인하세요.\n"
                f"  응답: {body}")
        sys.exit(f"[오류] API 호출 실패 (HTTP {exc.code}): {body}")
    except urllib.error.URLError as exc:
        sys.exit(f"[오류] 구글 API 에 연결하지 못했습니다: {exc.reason}")


def api_post(url: str, token: str, body: dict,
             params: dict | None = None, method: str = "POST") -> dict:
    """구글 API 쓰기. 호출부에서 --write 게이트를 이미 통과한 뒤에만 부른다."""
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"), method=method,
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        body_txt = exc.read().decode("utf-8", "replace")[:400]
        if exc.code == 403:
            sys.exit(
                f"[오류] 권한이 없습니다 (HTTP 403). 읽기 전용 scope 로는 쓸 수 없습니다.\n"
                f"  응답: {body_txt}")
        sys.exit(f"[오류] API 쓰기 실패 (HTTP {exc.code}): {body_txt}")
    except urllib.error.URLError as exc:
        sys.exit(f"[오류] 구글 API 에 연결하지 못했습니다: {exc.reason}")


if __name__ == "__main__":
    # 설정 점검용. 토큰 값은 마스킹해서 보여준다.
    tok = access_token()
    print(f"access token OK: {cred.mask(tok)}")
