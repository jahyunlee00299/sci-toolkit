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
import subprocess
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
#
# `out` 이 여기 없어서 로컬 실행 산출물 6개가 매니페스트에 들어간 적이 있다
# (260807). 저장소를 clone 한 사람에게는 그 파일이 존재하지 않으므로 doctor 가
# "6 missing" 으로 무조건 실패한다 — 만든 사람의 컴퓨터에서만 통과하는 매니페스트는
# 무결성 검증이 아니다. .gitignore 에는 `out/*` 가 있었지만 이 스크립트는
# .distignore 만 읽으므로 걸리지 않았다.
ALWAYS_EXCLUDE_DIRS = {".git", "__pycache__", ".cache", ".pytest_cache",
                       "node_modules", ".ipynb_checkpoints", "out"}


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
    """매니페스트에 담을 (파일, 상대경로) 를 **플랫폼 무관한 순서**로 낸다.

    `sorted(ROOT.rglob("*"))` 는 Path 객체를 정렬하는데, 그 비교는 OS 마다 다르다.
    Windows 에서는 `CLAUDE.md` 다음에 `config/…` 가 오고 Linux 에서는 `LICENSE` 가
    먼저 온다 — 같은 파일 집합인데 매니페스트 줄 순서가 달라지고, 그러면 CI 가
    "매니페스트가 낡았다"고 계속 보고한다(260807 실측: 62줄 차이, 내용은 동일).
    상대경로 문자열로 정렬하면 어느 OS 에서 만들어도 같은 파일이 나온다.
    """
    entries = []
    for p in ROOT.rglob("*"):
        if p.is_dir():
            continue
        if any(part in ALWAYS_EXCLUDE_DIRS for part in p.parts):
            continue
        rel = p.relative_to(ROOT).as_posix()
        if p.resolve() == MANIFEST.resolve():
            continue
        if is_excluded(rel, patterns):
            continue
        entries.append((rel, p))
    for rel, p in sorted(entries):
        yield p, rel


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def untracked_entries(rels: list[str]) -> list[str] | None:
    """매니페스트에 담긴 것 중 git 이 추적하지 않는 파일을 돌려준다.

    `out` 을 제외 목록에 넣는 것만으로는 다음 산출물 폴더에서 같은 일이 다시
    난다. 배포되는 것은 **저장소에 커밋된 파일**이고, 그것이 곧 다른 사람이
    clone 했을 때 실제로 갖게 되는 집합이다. 그래서 규칙 자체를 그걸로 잰다.

    git 이 없거나 저장소 밖이면 검사를 건너뛴다 (None) — USB 로 복사된 사본에서
    이 스크립트를 돌릴 수도 있고, 그때 검사를 실패로 처리하면 오탐이 된다.
    """
    # `-z` 로 받는다. 기본 출력은 비ASCII 경로를 `"docs/06_\352\270..."` 처럼
    # 따옴표+8진 이스케이프로 내놓기 때문에, 그대로 비교하면 한글 이름의 문서가
    # 전부 "추적되지 않음" 으로 잡힌다 (260807 실측: 문서 7개 오탐). NUL 구분
    # 출력에는 이스케이프가 없다.
    try:
        proc = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"],
                              capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    tracked = {p.decode("utf-8", "surrogateescape")
               for p in proc.stdout.split(b"\0") if p}
    if not tracked:
        return None
    return sorted(r for r in rels if r not in tracked)


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

    stray = untracked_entries([k[2:] for k in new])
    if stray:
        print(f"\n거부 — git 이 추적하지 않는 파일 {len(stray)}개가 매니페스트에 들어간다.")
        for k in stray[:10]:
            print(f"    [미추적] {k}")
        if len(stray) > 10:
            print(f"    [미추적] … 외 {len(stray) - 10}개")
        print("이 파일들은 clone 한 사람에게 없으므로 doctor 가 반드시 실패한다.")
        print(".distignore 에 추가하거나, 커밋해야 할 파일이면 커밋한 뒤 다시 실행하라.")
        return 1
    if stray is None:
        print("\n(git 저장소가 아니라 미추적 파일 검사는 건너뛴다)")

    if args.apply:
        MANIFEST.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        print(f"\nWROTE {MANIFEST} ({len(lines)} entries)")
    else:
        print("\n(미리보기 — 실제로 쓰려면 --apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
