#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
축소판 탐지기 — 스킬을 고쳐 쓴 뒤 *능력이 빠지지 않았는지* 구조적으로 대조한다.

무엇을 푸는가
-------------
스킬 문서를 정화(도메인 예시 제거)하거나 리팩토링한 뒤 "괜찮아 보인다"는 판단은
믿을 수 없다. 축소판도 잘 쓰인 문서로 보이기 때문이다. 2026-06-27 정화 작업이
`update_notion.py` 를 15.9KB → 7.4KB 로 만들었을 때 파일은 멀쩡히 존재했고
exit code 는 0이었으며, 그 결과 자동화가 4주간 조용히 무산출이었다.

LLM 품질 비교(blind comparator 등)는 "어느 쪽이 더 나은 글인가"를 본다.
이 도구는 다른 축을 본다: **원본이 하던 일을 새 버전도 할 수 있는가.**
둘은 대체 관계가 아니라 보완 관계다.

무엇을 세는가
-------------
문서가 "할 수 있다고 말하는 것"의 대리 지표 넷:
  · 섹션 제목 (##/###)   — 다루는 주제
  · 파일/경로 참조        — 딸려 있는 자산
  · 실행 명령            — 실제로 돌릴 수 있는 것
  · 전체 분량            — 위 셋으로 안 잡히는 서술 소실

이름이 바뀐 것은 소실이 아니다. 정화의 목적이 바로 이름 치환이므로,
동일 개수가 유지되면 통과시킨다 — 여기서 오탐이 나면 도구가 쓸모없어진다.

사용
----
    python scripts/capability_diff.py OLD NEW           # 파일 두 개 비교
    python scripts/capability_diff.py --skill docx --baseline <dir>
    exit 0 = 소실 없음 / 1 = 소실 의심 (내용은 stdout)
"""
from __future__ import annotations

import sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path

# 분량이 이 비율보다 더 줄면 경고한다. 260727 사례는 0.53 이었다.
DEFAULT_SHRINK_LIMIT = 0.30

_SECTION_RE = re.compile(r"^#{2,4}\s+(.+?)\s*$", re.MULTILINE)
# `scripts/foo.py`, references/bar.md 처럼 확장자를 가진 경로형 토큰
_REF_RE = re.compile(r"[\w./-]+\.(?:py|md|json|ya?ml|sh|ps1|txt|csv|html)\b")
# 코드펜스 안팎의 실행 명령 — 인터프리터/러너로 시작하는 줄
_CMD_RE = re.compile(
    r"^\s*(?:\$\s*)?((?:python3?|bash|sh|npx|node|pytest|pwsh|powershell)\s+[\w./\\-]+)",
    re.MULTILINE)

# 소실 판정에서 제외할 흔한 토큰 — 문서 어디에나 나오고 능력과 무관하다.
_REF_NOISE = frozenset({
    "requirements.txt", "readme.md", "license.txt", "setup.py",
    "package.json", "config.json", "settings.json",
})


def _norm(s: str) -> str:
    """비교용 정규화: 대소문자·공백·강조기호를 무시한다."""
    return re.sub(r"[\s*`_]+", " ", s).strip().lower()


def _sections(text: str) -> list[str]:
    return [m.group(1) for m in _SECTION_RE.finditer(text)]


def _refs(text: str) -> list[str]:
    out = []
    for m in _REF_RE.finditer(text):
        tok = m.group(0).lstrip("./")
        if tok.lower() in _REF_NOISE:
            continue
        out.append(tok)
    return out


def _commands(text: str) -> list[str]:
    return [m.group(1).strip() for m in _CMD_RE.finditer(text)]


def _lost(old_items: list[str], new_items: list[str]) -> list[str]:
    """old 에만 있고 new 에 없는 항목.

    개수 기반이 아니라 정규화된 값 기반으로 본다. 다만 '이름만 바뀐 경우'를
    소실로 오판하지 않도록, 전체 개수가 유지되면 빈 리스트를 돌려준다 —
    정화는 본질적으로 이름 치환이고, 그것까지 막으면 이 도구를 끄게 된다.
    """
    if len(new_items) >= len(old_items):
        new_norm = {_norm(i) for i in new_items}
        missing = [i for i in old_items if _norm(i) not in new_norm]
        # 개수가 유지됐다면 치환으로 본다.
        return [] if len(new_items) == len(old_items) else missing
    new_norm = {_norm(i) for i in new_items}
    return [i for i in old_items if _norm(i) not in new_norm]


@dataclass
class CapabilityReport:
    lost_sections: list[str] = field(default_factory=list)
    lost_refs: list[str] = field(default_factory=list)
    lost_commands: list[str] = field(default_factory=list)
    shrink_ratio: float = 0.0
    shrank: bool = False
    old_len: int = 0
    new_len: int = 0

    @property
    def ok(self) -> bool:
        return not (self.lost_sections or self.lost_refs
                    or self.lost_commands or self.shrank)

    def render(self, label: str = "") -> str:
        head = f"[{'OK  ' if self.ok else 'LOST'}] {label}".rstrip()
        lines = [f"{head}  ({self.old_len} → {self.new_len} chars, "
                 f"{self.shrink_ratio:+.0%})"]
        for title, items in (("사라진 섹션", self.lost_sections),
                             ("사라진 참조", self.lost_refs),
                             ("사라진 명령", self.lost_commands)):
            if items:
                shown = ", ".join(items[:5])
                more = f" (+{len(items) - 5})" if len(items) > 5 else ""
                lines.append(f"    {title}: {shown}{more}")
        if self.shrank:
            lines.append(f"    분량이 {self.shrink_ratio:.0%} 줄었다 — 축소판 의심")
        return "\n".join(lines)


def diff_capabilities(old: str, new: str,
                      shrink_limit: float = DEFAULT_SHRINK_LIMIT) -> CapabilityReport:
    """원본 대비 새 버전에서 사라진 능력을 찾는다."""
    old_len, new_len = len(old), len(new)
    ratio = (new_len - old_len) / old_len if old_len else 0.0
    return CapabilityReport(
        lost_sections=_lost(_sections(old), _sections(new)),
        lost_refs=_lost(_refs(old), _refs(new)),
        lost_commands=_lost(_commands(old), _commands(new)),
        shrink_ratio=ratio,
        shrank=ratio < -abs(shrink_limit),
        old_len=old_len,
        new_len=new_len,
    )


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def compare_trees(old_root: Path, new_root: Path,
                  shrink_limit: float = DEFAULT_SHRINK_LIMIT
                  ) -> dict[str, CapabilityReport]:
    """두 스킬 트리를 파일 단위로 대조한다(원본 기준, 새로 생긴 파일은 무시)."""
    reports: dict[str, CapabilityReport] = {}
    for old_file in sorted(old_root.rglob("*")):
        if not old_file.is_file() or old_file.suffix.lower() not in {
                ".md", ".py", ".sh", ".json", ".txt"}:
            continue
        rel = old_file.relative_to(old_root)
        new_file = new_root / rel
        if not new_file.exists():
            rep = CapabilityReport(lost_sections=[f"<파일 자체가 사라짐: {rel}>"],
                                   old_len=old_file.stat().st_size, new_len=0,
                                   shrink_ratio=-1.0, shrank=True)
        else:
            rep = diff_capabilities(_read(old_file), _read(new_file), shrink_limit)
        reports[str(rel).replace("\\", "/")] = rep
    return reports


def main() -> int:
    ap = argparse.ArgumentParser(
        description="스킬을 고쳐 쓴 뒤 능력이 빠지지 않았는지 대조한다")
    ap.add_argument("old", help="원본 파일 또는 폴더")
    ap.add_argument("new", help="새 버전 파일 또는 폴더")
    ap.add_argument("--shrink-limit", type=float, default=DEFAULT_SHRINK_LIMIT,
                    help=f"축소 경고 임계 (기본 {DEFAULT_SHRINK_LIMIT:.0%})")
    ap.add_argument("--quiet", action="store_true", help="소실만 출력")
    args = ap.parse_args()

    old, new = Path(args.old), Path(args.new)
    if not old.exists():
        print(f"[오류] 원본이 없습니다: {old}")
        return 2
    if not new.exists():
        print(f"[오류] 새 버전이 없습니다: {new}")
        return 2

    if old.is_file():
        reports = {old.name: diff_capabilities(_read(old), _read(new),
                                               args.shrink_limit)}
    else:
        reports = compare_trees(old, new, args.shrink_limit)

    lost = {k: v for k, v in reports.items() if not v.ok}
    for name, rep in reports.items():
        if args.quiet and rep.ok:
            continue
        print(rep.render(name))

    print("-" * 60)
    if lost:
        print(f"소실 의심 {len(lost)} / 검사 {len(reports)}건 — "
              "고친 쪽이 아니라 원본을 다시 보고, 빠진 것을 되돌릴 것.")
        return 1
    print(f"능력 소실 없음 ({len(reports)}건 검사)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
