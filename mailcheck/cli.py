"""Command line: python -m mailcheck <draft.txt> [--source received.txt] [--recipient person|admin]
[--owner-edited] [--profile profile.json] [--config mailcheck.toml]

Prints Korean findings and exits 0 (no hard finding) or 1 (at least one hard finding). Reads local files only.
"""
from __future__ import annotations

import argparse
import json
import sys

from .config import load_config
from .style import StyleContext, check
from .voice import VoiceProfile


def _read(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(path, encoding="utf-8-sig") as fh:
        return fh.read()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="mailcheck", description="한국어 학술 메일 초안 문체 검사기 (전송/LLM/네트워크 없음)")
    ap.add_argument("draft", help="검사할 초안 텍스트 파일 (표준입력은 -)")
    ap.add_argument("--source", default="", help="받은 메일 텍스트 파일 (숫자/날짜/금액 출처)")
    ap.add_argument("--recipient", choices=("person", "admin"), default="person")
    ap.add_argument("--owner-edited", action="store_true", help="직접 고친 글이면 대부분 권고로 낮춤")
    ap.add_argument("--profile", default="", help="수신자 문체 프로필 JSON (VoiceProfile.to_dict 형식)")
    ap.add_argument("--config", default="", help="mailcheck.toml 경로 (기본: 패키지 내장 파일)")
    args = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    try:
        cfg = load_config(args.config or None)
        body = _read(args.draft)
        source = _read(args.source) if args.source else ""
        profile = None
        if args.profile:
            with open(args.profile, encoding="utf-8-sig") as fh:
                profile = VoiceProfile.from_dict(json.load(fh))
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2
    rep = check(body, StyleContext(source_text=source, recipient_kind=args.recipient), profile,
                owner_edited=args.owner_edited, config=cfg)
    print(rep.render())
    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(main())
