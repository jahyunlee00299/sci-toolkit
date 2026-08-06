#!/usr/bin/env python3
"""SHA256SUMS 재생성 — 배포판 전체 파일의 해시 매니페스트를 만든다.

USB/공유폴더로 복사한 뒤 파일이 깨지지 않았는지 검증하는 데 쓰인다
(`doctor.py` 의 첫 번째 검사가 이 파일을 읽는다).

사용:
    python scripts/make_checksums.py            # 미리보기 (변경 요약만)
    python scripts/make_checksums.py --apply    # 실제로 SHA256SUMS 갱신

규칙:
- `.distignore` 의 제외 규칙을 그대로 따른다 (배포되지 않을 파일은 매니페스트에도 없음).
- `SHA256SUMS` 자기 자신은 제외한다 (자기 해시는 계산할 수 없다).
- 경로는 `./` 로 시작하는 POSIX 형식으로 통일한다 (Windows/Linux 양쪽 동일).
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import io
import sys
from pathlib import Path

# Windows 기본 콘솔은 cp949 라서 한글/기호 출력에서 죽는다. UTF-8로 맞춘다.
# TextIOWrapper 대신 reconfigure — 래퍼는 원본 스트림을 소유해서,
# import 후 GC 되면 호출자의 stdout 까지 닫아버린다(실측).
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "SHA256SUMS"
DISTIGNORE = ROOT / ".distignore"

# .distignore 에 없더라도 항상 제외 (생성물 / 캐시)
ALWAYS_EXCLUDE_DIRS = {".git", "__pycache__", ".cache", ".pytest_cache",
                       "node_modules", ".ipynb_checkpoints"}


def load_patterns() -> list[str]:
    if not DISTIGNORE.exists():
        return []
    out = []
    for line in DISTIGNORE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def is_excluded(rel_posix: str, patterns: list[str]) -> bool:
    candidates = (rel_posix, f"/{rel_posix}")
    for pat in patterns:
        for cand in candidates:
            if fnmatch.fnmatch(cand, pat):
                return True
        # `**/foo/**` 형태는 경로 조각 단위로도 확인
        core = pat.strip("*/")
        if core and f"/{core}/" in f"/{rel_posix}/":
            return True
    return False


def iter_files(patterns: list[str]):
    for p in sorted(ROOT.rglob("*")):
        if p.is_dir():
            continue
        if any(part in ALWAYS_EXCLUDE_DIRS for part in p.parts):
            continue
        rel = p.relative_to(ROOT).as_posix()
        if p.resolve() == MANIFEST.resolve():
            continue
        if is_excluded(rel, patterns):
            continue
        yield p, rel


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_existing() -> dict[str, str]:
    if not MANIFEST.exists():
        return {}
    out = {}
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, _, name = line.partition(" *")
        if name:
            out[name.strip()] = digest.strip()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="SHA256SUMS 재생성")
    ap.add_argument("--apply", action="store_true", help="실제로 파일에 쓴다")
    args = ap.parse_args()

    patterns = load_patterns()
    old = read_existing()

    lines, new = [], {}
    for path, rel in iter_files(patterns):
        digest = sha256(path)
        new[f"./{rel}"] = digest
        lines.append(f"{digest} *./{rel}")

    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed = sorted(k for k in set(new) & set(old) if new[k] != old[k])

    print(f"매니페스트 대상: {len(new)}개 파일 (이전 {len(old)}개)")
    print(f"  추가 {len(added)} / 변경 {len(changed)} / 제거 {len(removed)}")
    for label, items in (("추가", added), ("변경", changed), ("제거", removed)):
        for k in items[:8]:
            print(f"    [{label}] {k}")
        if len(items) > 8:
            print(f"    [{label}] … 외 {len(items) - 8}개")

    if args.apply:
        MANIFEST.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        print(f"\nWROTE {MANIFEST} ({len(lines)} entries)")
    else:
        print("\n(미리보기 — 실제로 쓰려면 --apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
