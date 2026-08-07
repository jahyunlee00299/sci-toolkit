#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
install.py 가 기존 설치본을 파괴하지 않는지 검증한다.

배경 (실측, 2026-08-07):
  install.py 는 대상 스킬 폴더가 이미 있으면 `shutil.rmtree(dst)` 로 통째로 지운 뒤
  copytree 했다. 그 결과 사용자의 런타임에만 있던 파일 —
    manuscript-pipeline/scripts/ 7종, endnote-citation-injection/ 3종
    (safe_refs_update.py 포함), scientific-validation/scripts/ 3종 —
  이 설치 한 번으로 전부 삭제됐다.

  260727 사건(incident_pii_sanitize_killed_runtime_skill)과 같은 유형이다:
  "덮어쓴다"가 사실은 "지우고 새로 만든다"였고, 아무도 그걸 측정하지 않았다.

이 테스트가 지키는 계약:
  1. 배포판에 없고 대상에만 있던 파일은 설치 후에도 남아 있어야 한다.
  2. 배포판에 있는 파일은 대상에 반영되어야 한다(설치가 no-op이면 안 된다).
  3. 양쪽에 같은 이름이 있으면 배포판 것이 이긴다(갱신이 목적이므로).
  4. --force 를 주면 1번을 포기하고 옛 동작(완전 교체)을 한다 — 명시적일 때만.

케이스는 구현이 아니라 위 계약에서 나왔다. 구현을 고쳐 통과시키지 말고,
계약이 바뀌었을 때만 이 파일을 고칠 것.
"""
from __future__ import annotations

import sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

import importlib.util
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALLER = ROOT / "install" / "install.py"

_fail = 0
_pass = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global _fail, _pass
    if cond:
        _pass += 1
        print(f"  PASS  {name}")
    else:
        _fail += 1
        print(f"  FAIL  {name}" + (f"  — {detail}" if detail else ""))


def run_installer(dest: Path, skills: str, *extra: str) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(INSTALLER), "--skills", skills,
           "--dest", str(dest), "--apply", *extra]
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=180)


def seed_destination(dest: Path, skill: str) -> tuple[Path, Path]:
    """대상에 '사용자가 이미 가지고 있던' 파일 2개를 심는다.

    - local_only: 배포판에 없는 파일 → 반드시 살아남아야 한다
    - shared:     배포판에도 있는 파일 → 배포판 내용으로 갱신되어야 한다
    """
    skill_dir = dest / skill
    (skill_dir / "scripts").mkdir(parents=True, exist_ok=True)
    local_only = skill_dir / "scripts" / "user_local_tool.py"
    local_only.write_text("# 사용자 런타임에만 있는 스크립트\n", encoding="utf-8")
    shared = skill_dir / "SKILL.md"
    shared.write_text("STALE — 반드시 배포판 내용으로 교체되어야 한다\n", encoding="utf-8")
    return local_only, shared


def main() -> int:
    if not INSTALLER.exists():
        print(f"[오류] 설치기를 찾을 수 없습니다: {INSTALLER}")
        return 1

    # 의존성이 없고 이 패키지가 실제로 배포하는 스킬로 고정한다.
    # (예전에는 xlsx 를 썼으나 Anthropic 소유라 패키지에서 빠졌다 — 외부 스킬을
    #  테스트 대상으로 삼으면 패키지가 멀쩡해도 테스트가 깨진다.)
    skill = "code-quality"
    src_skill_md = ROOT / "skills" / skill / "SKILL.md"
    if not src_skill_md.exists():
        print(f"[오류] 테스트 대상 스킬이 없습니다: {src_skill_md}")
        return 1

    print("install.py 비파괴 설치 검증")
    print("=" * 60)

    # ── 케이스 1~3: 기본 설치는 비파괴여야 한다 ──────────────────────────
    print("\n[기본 설치] 기존 파일 보존 + 배포판 내용 반영")
    with tempfile.TemporaryDirectory() as td:
        dest = Path(td) / "skills"
        local_only, shared = seed_destination(dest, skill)
        proc = run_installer(dest, skill)

        check("설치기가 정상 종료", proc.returncode == 0,
              f"exit={proc.returncode} stderr={proc.stderr[-300:]}")

        # 계약 1 — 대상에만 있던 파일은 살아남는다
        check("배포판에 없는 기존 파일이 보존됨", local_only.exists(),
              f"삭제됨: {local_only}")

        # 계약 2 — 배포판 파일이 실제로 들어온다
        installed = dest / skill / "SKILL.md"
        check("배포판 파일이 대상에 설치됨", installed.exists())

        # 계약 3 — 같은 이름은 배포판이 이긴다
        if installed.exists():
            got = installed.read_text(encoding="utf-8", errors="replace")
            check("동명 파일은 배포판 내용으로 갱신됨",
                  "STALE" not in got,
                  "옛 내용이 그대로 남아 있음(설치가 no-op)")

    # ── 케이스 5: .distignore 가 설치 경로에도 적용되는가 ────────────────
    # 예전에는 .distignore 를 make_checksums.py 만 읽었고 install.py 는 읽지
    # 않았다. 즉 "배포 금지" 선언이 매니페스트 범위에만 적용되고 실제 복사에는
    # 아무 효력이 없었다. 규칙이 배선되지 않은 상태였다는 뜻이다.
    print("\n[.distignore] 배포 금지 파일은 설치되지 않아야 함")
    planted = ROOT / "skills" / skill / "secrets.json"
    planted_existed = planted.exists()
    if not planted_existed:
        planted.write_text('{"token": "should-never-be-installed"}\n', encoding="utf-8")
    try:
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "skills"
            proc = run_installer(dest, skill)
            check("설치기가 정상 종료(.distignore 경로)", proc.returncode == 0,
                  f"exit={proc.returncode} stderr={proc.stderr[-300:]}")
            check("secrets.json 이 설치되지 않음",
                  not (dest / skill / "secrets.json").exists(),
                  ".distignore 가 설치 경로에 적용되지 않음")
            check("같은 스킬의 정상 파일은 설치됨",
                  (dest / skill / "SKILL.md").exists(),
                  "제외 규칙이 과하게 걸려 정상 파일까지 빠짐")
    finally:
        if not planted_existed and planted.exists():
            planted.unlink()

    # ── 케이스 4: --force 는 옛 동작(완전 교체) ─────────────────────────
    print("\n[--force] 명시적으로 요청했을 때만 완전 교체")
    with tempfile.TemporaryDirectory() as td:
        dest = Path(td) / "skills"
        local_only, _ = seed_destination(dest, skill)
        proc = run_installer(dest, skill, "--force")

        check("--force 설치가 정상 종료", proc.returncode == 0,
              f"exit={proc.returncode} stderr={proc.stderr[-300:]}")
        check("--force 는 기존 파일을 제거함", not local_only.exists(),
              "--force 인데도 남아 있음")

    # ── 케이스 6: --dest 생략 시 환경에 맞는 기본값 ─────────────────────
    # 예전에는 무조건 ~/.claude/skills 였다. Codex 사용자에게는 아무 의미가 없는
    # 폴더라(스킬 레지스트리 개념이 없다) 조용히 엉뚱한 곳에 설치된다.
    print("\n[--dest 생략] 환경을 보고 결정하고, 어디에 넣는지 알린다")
    spec = importlib.util.spec_from_file_location("installer", INSTALLER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["installer"] = mod
    try:
        spec.loader.exec_module(mod)
    except SystemExit:
        pass
    if hasattr(mod, "default_dest"):
        dest, why = mod.default_dest()
        check("경로를 돌려줌", bool(str(dest)), f"dest={dest}")
        check("근거를 함께 돌려줌", bool(why), "왜 그 경로인지 설명이 없다")
        check("마지막 구성요소가 skills", Path(dest).name == "skills", f"dest={dest}")
    else:
        check("default_dest 가 존재", False, "install.py 에 함수가 없다")

    proc = subprocess.run(
        [sys.executable, str(INSTALLER), "--skills", skill],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    check("생략해도 정상 종료", proc.returncode == 0, proc.stderr[-200:])
    check("어디에 설치할지 출력함", "자동 결정" in proc.stdout,
          "사용자가 설치 위치를 모른 채 진행하게 된다")

    print("=" * 60)
    print(f"통과 {_pass} / 실패 {_fail}")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
