#!/usr/bin/env python3
"""SHA256SUMS 매니페스트가 **다른 사람의 clone 에서도** 맞는지 지킨다.

doctor 의 무결성 검사는 매니페스트를 만든 컴퓨터에서 돌리면 언제나 통과한다 —
같은 워킹트리로 해시를 만들고 같은 워킹트리로 검증하기 때문이다. 그래서 두
종류의 오류가 로컬에서는 보이지 않고 CI 에서만 터졌다 (260807, 실측):

1. **로컬 산출물이 매니페스트에 들어간다.** `out/` 의 실행 결과 6개가 기록돼
   있었고, clone 한 사람에게는 그 파일이 없으므로 "6 missing" 으로 무조건 실패.
   `.gitignore` 에는 `out/*` 가 있었지만 make_checksums 는 `.distignore` 만 읽는다.
2. **줄바꿈이 플랫폼마다 다르다.** Windows 워킹트리가 CRLF 인 채로 매니페스트를
   만들면 LF 로 체크아웃하는 CI/Linux 에서 125건이 어긋난다. `.gitattributes` 는
   `* text=auto eol=lf` 로 이미 못박혀 있었지만 기존 체크아웃이 재정규화되지
   않아 정책과 디스크가 갈라져 있었다.

두 검사 모두 git 을 기준으로 잰다. git 이 없거나 저장소 밖이면 skip 한다 — USB
사본에서 돌릴 수도 있고, 그때 실패로 처리하면 오탐이다.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "SHA256SUMS"

failures: list[str] = []
checks = 0


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(ROOT), *args],
                          capture_output=True, timeout=60)


def in_git_repo() -> bool:
    try:
        return git("rev-parse", "--git-dir").returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def tracked_files() -> set[str]:
    out = git("ls-files", "-z").stdout
    return {p.decode("utf-8", "surrogateescape") for p in out.split(b"\0") if p}


def manifest_paths() -> list[str]:
    paths = []
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        _, _, name = line.partition(" *")
        name = name.strip()
        if name.startswith("./"):
            name = name[2:]
        if name:
            paths.append(name)
    return paths


def check_no_untracked_entries() -> None:
    """매니페스트의 모든 항목이 git 에 커밋돼 있어야 한다."""
    global checks
    checks += 1
    stray = sorted(set(manifest_paths()) - tracked_files())
    if stray:
        failures.append(
            f"매니페스트에 미추적 파일 {len(stray)}개: {stray[:5]}"
            " — clone 한 사람에게는 없는 파일이라 doctor 가 반드시 실패한다")


def check_worktree_eol_matches_policy() -> None:
    """워킹트리 줄바꿈이 .gitattributes 정책과 같아야 한다."""
    global checks
    checks += 1
    out = git("ls-files", "--eol").stdout.decode("utf-8", "surrogateescape")
    bad = [ln for ln in out.splitlines()
           if " w/crlf" in ln and "eol=crlf" not in ln]
    if bad:
        failures.append(
            f"워킹트리가 CRLF 인데 정책은 LF 인 파일 {len(bad)}개"
            " — 이 상태로 매니페스트를 만들면 Linux/CI 에서 전부 불일치한다")


def check_manifest_is_current() -> None:
    """매니페스트가 현재 트리와 일치해야 한다 (make_checksums 가 no-op 이어야)."""
    global checks
    checks += 1
    script = ROOT / "scripts" / "make_checksums.py"
    proc = subprocess.run([sys.executable, str(script)],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=300, cwd=str(ROOT))
    if proc.returncode != 0:
        failures.append(f"make_checksums 가 거부됨 (exit {proc.returncode}) — "
                        f"{(proc.stdout or '').strip().splitlines()[-1:] or ''}")
        return
    text = proc.stdout or ""
    for label in ("[추가]", "[변경]", "[제거]"):
        if label in text:
            failures.append(
                f"SHA256SUMS 가 낡았다 ({label} 항목 있음) — "
                "`python scripts/make_checksums.py --apply` 후 커밋하라")
            break


def main() -> int:
    if not MANIFEST.exists():
        print("SKIP — SHA256SUMS 가 없다")
        return 0
    if not in_git_repo():
        print("SKIP — git 저장소가 아니다 (배포 사본으로 판단)")
        return 0

    check_no_untracked_entries()
    check_worktree_eol_matches_policy()
    check_manifest_is_current()

    if failures:
        print(f"FAIL — {len(failures)}건")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"ALL PASS — 매니페스트 검사 {checks}건 (미추적·줄바꿈·최신성)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
