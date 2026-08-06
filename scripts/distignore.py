#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
`.distignore` 규칙의 단일 출처 (SSOT).

왜 별도 모듈인가:
  이 규칙은 원래 `make_checksums.py` 안에만 있었고, `install.py` 와 `doctor.py`
  는 `.distignore` 를 **읽지 않았다**. 그래서 "배포하면 안 되는 파일"이라는
  선언은 SHA256SUMS 매니페스트 범위에만 적용됐고, 실제 설치 경로에는
  아무 효력이 없었다 — 규칙이 있는데 배선되지 않은 상태였다(2026-08-07 실측).

  두 곳에 같은 fnmatch 로직을 복사하면 한쪽만 고쳐지는 드리프트가 생긴다.
  패턴 해석은 여기 한 곳에서만 하고, 호출자는 루트 경로만 넘긴다.

사용:
    from distignore import load_patterns, is_excluded
    pats = load_patterns(toolkit_root)
    if is_excluded("skills/foo/secrets.json", pats): ...
"""
from __future__ import annotations

import fnmatch
from pathlib import Path

# `.distignore` 에 없더라도 항상 제외한다 (생성물 / 캐시).
# 배포 트리에 들어갈 이유가 없고, 사람이 규칙을 빠뜨려도 새지 않아야 한다.
ALWAYS_EXCLUDE_DIRS = {
    ".git", "__pycache__", ".cache", ".pytest_cache",
    "node_modules", ".ipynb_checkpoints",
}


def load_patterns(root: Path) -> list[str]:
    """`<root>/.distignore` 의 유효 패턴을 읽는다. 없으면 빈 리스트."""
    path = Path(root) / ".distignore"
    if not path.exists():
        return []
    out: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def is_excluded(rel_posix: str, patterns: list[str]) -> bool:
    """루트 기준 상대경로(POSIX 구분자)가 배포 제외 대상인지 판정한다."""
    candidates = (rel_posix, f"/{rel_posix}")
    for pat in patterns:
        for cand in candidates:
            if fnmatch.fnmatch(cand, pat):
                return True
        # `**/foo/**` 형태는 경로 조각 단위로도 확인한다.
        core = pat.strip("*/")
        if core and f"/{core}/" in f"/{rel_posix}/":
            return True
    return False


def ignore_factory(src_root: Path, patterns: list[str]):
    """`shutil.copytree(ignore=...)` 에 넘길 콜백을 만든다.

    copytree 는 (디렉토리, 그 안의 이름들) 을 주고 "빼야 할 이름들"을 돌려받는다.
    여기서 각 항목의 루트 기준 상대경로를 복원해 `.distignore` 로 판정한다.
    """
    src_root = Path(src_root).resolve()

    def _ignore(directory: str, names: list[str]) -> set[str]:
        skipped: set[str] = set()
        here = Path(directory).resolve()
        for name in names:
            if name in ALWAYS_EXCLUDE_DIRS or name.endswith(".pyc"):
                skipped.add(name)
                continue
            try:
                rel = (here / name).relative_to(src_root).as_posix()
            except ValueError:
                continue
            if is_excluded(rel, patterns):
                skipped.add(name)
        return skipped

    return _ignore
