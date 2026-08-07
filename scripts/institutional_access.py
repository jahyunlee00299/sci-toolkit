#!/usr/bin/env python3
"""페이월 논문의 기관 도서관(교외접속) 링크를 만들어 준다 — 링크까지만.

이 모듈은 **의도적으로 로그인도 다운로드도 하지 않는다.** 구독 저널 원문을
스크립트로 받는 행위 자체가 대학 도서관의 공정이용 규정 위반이기 때문이다.
고려대 규정(위반 사례 1번)은 이렇게 적는다:

    "전자적, 기계적 수단(다운로딩 프로그램, 엔진, 로봇, 매크로, RPA 등)으로
     원문을 다운로드하는 행위"

계정 공유(5번)만 금지된 게 아니라 **수단 자체**가 금지 항목이다. 본인 계정으로
정당하게 로그인해도 그 뒤를 스크립트가 받으면 위반이고, 제재는 도서관 서비스
1년 제한 + 민사 책임 1차 부담이다. 그래서 이 툴킷이 하는 일은 여기까지다:
사람이 브라우저에서 클릭할 URL을 만들어 주고, 규정과 한도를 같이 알려준다.

사용:
    from institutional_access import InstitutionRegistry
    reg = InstitutionRegistry.load()                  # config/institutions.json
    link = reg.build_link("korea-univ", "https://www.sciencedirect.com/...")
    print(link.url, link.login_note)

CLI:
    python institutional_access.py --list
    python institutional_access.py --institution korea-univ --url https://...
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

# 기본 위치: 이 파일이 scripts/ 안에 있으므로 저장소 루트의 config/ 를 본다.
_DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config" / "institutions.json"

_PLACEHOLDER = "{url}"


@dataclass(frozen=True)
class InstitutionalLink:
    """사람이 브라우저에서 열어야 하는 링크 하나."""

    institution: str
    display_name: str
    url: str
    login_note: str
    fair_use_url: Optional[str]
    daily_limits: dict[str, Any]

    def human_summary(self) -> str:
        """터미널에 그대로 찍을 수 있는 안내문. 자동 다운로드가 아님을 매번 말한다."""
        lines = [
            f"  기관 접속 링크 ({self.display_name}):",
            f"    {self.url}",
        ]
        if self.login_note:
            lines.append(f"    · {self.login_note}")
        per_pub = self.daily_limits.get("per_publisher")
        per_machine = self.daily_limits.get("per_machine")
        if per_pub or per_machine:
            lines.append(
                f"    · 1일 한도: 동일 출판사 {per_pub}건 / 동일 PC {per_machine}건"
            )
        if self.fair_use_url:
            lines.append(f"    · 공정이용 규정: {self.fair_use_url}")
        lines.append(
            "    · 이 링크는 브라우저에서 사람이 직접 여는 용도다. 스크립트·매크로로 "
            "원문을 내려받는 것은 공정이용 위반이다."
        )
        return "\n".join(lines)


class InstitutionRegistry:
    """config/institutions.json 을 읽어 링크를 만들어 주는 얇은 레지스트리."""

    def __init__(self, data: dict[str, Any], source: Optional[Path] = None) -> None:
        self._institutions: dict[str, Any] = data.get("institutions") or {}
        self._default: Optional[str] = data.get("default_institution")
        self.source = source

    # --- 로딩 ------------------------------------------------------------ #

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "InstitutionRegistry":
        """설정을 읽는다. 파일이 없으면 빈 레지스트리 — 오류가 아니다.

        기관 설정은 선택 사항이다. 없으면 이 기능만 조용히 꺼지고 OA 수집은
        그대로 동작해야 한다 (설정 파일 하나 없다고 도구 전체가 죽으면 안 된다).
        """
        p = Path(path) if path else _DEFAULT_CONFIG
        if not p.exists():
            return cls({}, source=None)
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            # 깨진 설정을 조용히 무시하면 "왜 링크가 안 나오지"로 이어진다.
            print(f"[WARN] 기관 설정을 읽지 못했습니다 ({p}): {e}", file=sys.stderr)
            return cls({}, source=None)
        return cls(data if isinstance(data, dict) else {}, source=p)

    # --- 조회 ------------------------------------------------------------ #

    def available(self) -> list[str]:
        return sorted(self._institutions.keys())

    def resolve_key(self, key: Optional[str]) -> Optional[str]:
        """명시 키 > 설정의 default_institution > (하나뿐이면) 그것."""
        if key:
            return key if key in self._institutions else None
        if self._default and self._default in self._institutions:
            return self._default
        if len(self._institutions) == 1:
            return next(iter(self._institutions))
        return None

    def build_link(self, key: Optional[str], target_url: str) -> Optional[InstitutionalLink]:
        """대상 URL을 기관 프록시 링크로 감싼다. 만들 수 없으면 None."""
        if not target_url:
            return None
        resolved = self.resolve_key(key)
        if not resolved:
            return None
        entry = self._institutions.get(resolved) or {}
        template = entry.get("proxy_url_template")
        if not template or _PLACEHOLDER not in template:
            # 자리표시자가 없는 템플릿은 조용히 엉뚱한 링크를 만든다 — 차라리 만들지 않는다.
            print(
                f"[WARN] '{resolved}' 의 proxy_url_template 에 {_PLACEHOLDER} 자리표시자가 "
                "없습니다 — 링크를 만들지 않습니다.",
                file=sys.stderr,
            )
            return None
        return InstitutionalLink(
            institution=resolved,
            display_name=entry.get("display_name") or resolved,
            url=template.replace(_PLACEHOLDER, target_url),
            login_note=entry.get("login_note") or "",
            fair_use_url=entry.get("fair_use_url"),
            daily_limits=entry.get("daily_limits") or {},
        )


def main() -> int:
    ap = argparse.ArgumentParser(
        description="페이월 논문의 기관 도서관 접속 링크를 만든다 (로그인·다운로드 없음).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--list", action="store_true", help="설정된 기관 목록 출력")
    ap.add_argument("--institution", default=None, help="기관 키 (예: korea-univ)")
    ap.add_argument("--url", default=None, help="원문 landing page URL")
    ap.add_argument("--config", default=None, help="institutions.json 경로 (기본: config/)")
    args = ap.parse_args()

    reg = InstitutionRegistry.load(Path(args.config) if args.config else None)

    if args.list or not args.url:
        keys = reg.available()
        if not keys:
            print("설정된 기관이 없습니다. config/institutions.json 을 확인하세요.")
            return 1
        print("설정된 기관:")
        for k in keys:
            print(f"  - {k}")
        if not args.url:
            return 0
        return 0

    link = reg.build_link(args.institution, args.url)
    if not link:
        print(
            "[ERROR] 링크를 만들지 못했습니다 — 기관 키가 없거나 설정되지 않았습니다.\n"
            f"        사용 가능: {', '.join(reg.available()) or '(없음)'}",
            file=sys.stderr,
        )
        return 1
    print(link.human_summary())
    return 0


if __name__ == "__main__":
    sys.exit(main())
