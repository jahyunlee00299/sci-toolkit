#!/usr/bin/env python3
"""Google OAuth2 access token — stdlib only, reuses an existing token file.

Every connector in this package uses only the stdlib (urllib). Working just
by copying the folder is the design principle, and making an exception for
Google would break that. So instead of `google-api-python-client`, this
module does the refresh-token exchange itself.

How it works
------------
An access token expires in an hour, but **the refresh token lasts a long
time.** So the browser flow is only needed once, and after that this module
handles renewal — no library, one network call.

    Read the token file -> still valid? -> use as-is
                         -> expired? -> get a new one via refresh_token, save it back to the file

Token file format
------------------
Reads Google's standard OAuth format as-is:

    {"access_token": "...", "refresh_token": "...",
     "expiry_date": 1755300000000, "token_type": "Bearer"}

`expiry_date` is in **milliseconds** (the convention across Google's client
libraries). A file written in seconds is also accepted — the digit count
distinguishes them. Getting the factor-of-1000 wrong here means either
"always expired" (an unnecessary refresh on every call) or the opposite —
continuing to use an already-expired token.

If you've already made a Google token with another tool, just point at that
path (`credentials.json`'s `google.token_cache_path`). No need to make a new one.
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
_SKEW_SEC = 60  # renewal margin just before expiry


def _expiry_seconds(raw) -> float:
    """Normalize an expiry value to seconds.

    Google's own tools write milliseconds; a hand-made file might write
    seconds. Since 2001, a second-based timestamp has 10 digits and a
    millisecond-based one has 13, so the digit count decides.
    """
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return 0.0
    return v / 1000.0 if v > 1e11 else v


def _read_json(path: Path, what: str) -> dict:
    if not path.exists():
        sys.exit(
            f"[Error] {what} file not found: {path}\n"
            f"  Check the path in the google entry of config/credentials.json.\n"
            f"  The initial grant needs browser consent, so it is not automated by script —\n"
            f"  see the Google auth section of scripts/connectors/README.md."
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        sys.exit(f"[Error] Could not read the {what} file ({path}): {exc}")


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
        # invalid_grant = the refresh token was revoked (password change, permission
        # revoked, or 6+ months unused). There is no fix but reissuing it, so say so.
        if "invalid_grant" in body:
            sys.exit(
                "[Error] The refresh token is no longer valid (invalid_grant).\n"
                "  Revoked by a password change, permission revocation, or long disuse. Reissue is required.\n"
                f"  Response: {body}")
        sys.exit(f"[Error] Token refresh failed (HTTP {exc.code}): {body}")
    except urllib.error.URLError as exc:
        sys.exit(f"[Error] Could not connect to the token server: {exc.reason}")


def access_token(cfg: dict | None = None) -> str:
    """Return a valid access token. Refreshes and rewrites the file if needed."""
    token_path = Path(
        cred.require("google", "token_cache_path", cfg=cfg)).expanduser()
    token = _read_json(token_path, "Google token")

    if time.time() < _expiry_seconds(token.get("expiry_date")) - _SKEW_SEC:
        tok = token.get("access_token")
        if tok:
            return tok
        # Not expired, but no access_token = the file is corrupted. Try to recover via refresh.

    refresh = token.get("refresh_token")
    if not refresh:
        sys.exit(
            f"[Error] Token file has no refresh_token: {token_path}\n"
            "  A file with only an access token cannot be revived once expired. Reissue it.")

    client_path = Path(
        cred.require("google", "oauth_client_path", cfg=cfg)).expanduser()
    raw = _read_json(client_path, "OAuth client")
    # The JSON the Google console hands out is wrapped as {"installed": {...}} or {"web": {...}}.
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
        # A cache-save failure is not fatal — this call continues anyway.
        print(f"[Warning] Could not save the refreshed token ({exc}). "
              f"Will refresh again on the next run.", file=sys.stderr)
    return token["access_token"]


def api_get(url: str, token: str, params: dict | None = None) -> dict:
    """Google API GET. Used only on read-only paths."""
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
                f"[Error] Permission denied (HTTP 403). Check the token's scope.\n"
                f"  Response: {body}")
        sys.exit(f"[Error] API call failed (HTTP {exc.code}): {body}")
    except urllib.error.URLError as exc:
        sys.exit(f"[Error] Could not connect to the Google API: {exc.reason}")


def api_post(url: str, token: str, body: dict,
             params: dict | None = None, method: str = "POST") -> dict:
    """Google API write. Called only after the caller has already passed the --write gate."""
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
                f"[Error] Permission denied (HTTP 403). A read-only scope cannot write.\n"
                f"  Response: {body_txt}")
        sys.exit(f"[Error] API write failed (HTTP {exc.code}): {body_txt}")
    except urllib.error.URLError as exc:
        sys.exit(f"[Error] Could not connect to the Google API: {exc.reason}")


if __name__ == "__main__":
    # For config verification. Shows the token value masked.
    tok = access_token()
    print(f"access token OK: {cred.mask(tok)}")
