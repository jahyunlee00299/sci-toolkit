#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sci-toolkit 선택 설치기 (à la carte installer)

원하는 기능(스킬)만 골라서 대상 폴더에 설치합니다.
- 프리셋("논문 작성", "문헌 조사" 등)으로 한 번에 고르거나
- 개별 스킬을 직접 골라 담을 수 있습니다.
- 스킬 간 필수 의존성(예: manuscript-pipeline → docx, academic-term-rules)은
  config/catalog.json 을 근거로 자동으로 함께 설치됩니다.

기본은 미리보기(dry-run)입니다. 실제 복사는 --apply 를 붙여야 실행됩니다.

사용 예:
  python install/install.py                      # 대화형, 미리보기
  python install/install.py --apply              # 대화형, 실제 설치
  python install/install.py --preset paper-writing --dest ~/.claude/skills --apply
  python install/install.py --skills docx,xlsx --dest ./out --apply
  python install/install.py --list               # 카탈로그만 출력
"""
from __future__ import annotations

# Windows 기본 콘솔은 cp949 라서 한글/기호 출력에서 죽는다. UTF-8로 맞춘다.
# reconfigure 를 쓴다: TextIOWrapper 로 감싸면 원본 스트림을 소유하게 되어,
# 이 모듈이 import 된 뒤 래퍼가 GC 될 때 호출자의 stdout 까지 닫는다(실측).
import sys as _sys
for _s in (_sys.stdout, _sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

import argparse
import json
import shutil
import sys
from pathlib import Path

# Windows 콘솔(cp949)에서 한글이 깨지지 않도록 stdout/stdin을 UTF-8로 강제
for _stream in (sys.stdout, sys.stdin, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

ROOT = Path(__file__).resolve().parent.parent          # toolkit root
CATALOG_PATH = ROOT / "config" / "catalog.json"
SKILLS_DIR = ROOT / "skills"


def _shell_env_notice() -> None:
    """Warn before install if this machine can't run the plugin's hooks.

    Only relevant when this repo is loaded as a Claude Code plugin (hooks/hooks.json
    runs `sh ...`) -- the à-la-carte skill copy below works regardless. But a user
    who never sees this warning has no way to know their safety-guard hooks are
    silently inert (see scripts/env_detect.py for the full explanation).
    """
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        import env_detect  # noqa: E402
        r = env_detect.detect()
    except Exception:
        return  # preflight is best-effort; never block install over it
    if r["shell_ok"]:
        return
    print("\n⚠ 이 컴퓨터에서는 이 저장소를 Claude Code 플러그인으로 설치했을 때")
    print("  훅(안전 가드)이 실행되지 않을 수 있습니다:")
    for line in r["advice"]:
        print(f"  {line}")
    print("  (스킬만 개별 설치하는 이 스크립트 자체는 이 문제와 무관하게 정상 동작합니다)\n")


# ── catalog ────────────────────────────────────────────────────────────────
def load_catalog() -> dict:
    if not CATALOG_PATH.exists():
        sys.exit(f"[오류] 카탈로그를 찾을 수 없습니다: {CATALOG_PATH}")
    with CATALOG_PATH.open(encoding="utf-8") as f:
        cat = json.load(f)
    # sanity: every skill folder listed in catalog must exist on disk.
    # `external: true` 스킬은 예외 — 이 저장소가 재배포할 수 없어 일부러 빠져 있고,
    # 의존성 선언을 유지하기 위해서만 카탈로그에 남아 있다.
    missing = [s for s, meta in cat["skills"].items()
               if not meta.get("external") and not (SKILLS_DIR / s).is_dir()]
    if missing:
        sys.exit(f"[오류] 카탈로그에 있으나 실제 폴더가 없는 스킬: {', '.join(missing)}")
    return cat


def all_skill_names(cat: dict) -> list[str]:
    return sorted(cat["skills"].keys())


# ── dependency resolution ───────────────────────────────────────────────────
def resolve(selection: list[str], cat: dict) -> tuple[list[str], dict[str, list[str]]]:
    """Expand a selection to include all hard 'requires' deps (transitive).

    Returns (final_sorted_list, pulled_by) where pulled_by[dep] = [skills that
    pulled it in]. No cycles exist in the catalog, but we guard anyway.
    """
    skills = cat["skills"]
    final: set[str] = set()
    pulled_by: dict[str, list[str]] = {}

    def visit(name: str, chain: tuple[str, ...]) -> None:
        if name not in skills:
            sys.exit(f"[오류] 알 수 없는 스킬: {name}")
        if name in chain:  # cycle guard (catalog has none, but be safe)
            return
        if name in final:
            return
        final.add(name)
        for dep in skills[name].get("requires", []):
            pulled_by.setdefault(dep, [])
            if name not in pulled_by[dep]:
                pulled_by[dep].append(name)
            visit(dep, chain + (name,))

    for s in selection:
        visit(s, ())
    # keep only deps that weren't explicitly chosen by the user
    pulled_by = {d: srcs for d, srcs in pulled_by.items() if d not in selection}
    return sorted(final), pulled_by


# ── selection expansion ─────────────────────────────────────────────────────
def expand_preset(preset_key: str, cat: dict) -> list[str]:
    presets = cat["presets"]
    if preset_key not in presets:
        sys.exit(f"[오류] 알 수 없는 프리셋: {preset_key} "
                 f"(가능: {', '.join(presets)})")
    skills = presets[preset_key]["skills"]
    if skills == ["__ALL__"]:
        return all_skill_names(cat)
    return list(skills)


# ── size helpers ─────────────────────────────────────────────────────────────
def _cat_label(cat: dict, ckey: str) -> str:
    """카테고리 라벨 — 구버전(문자열)/신버전(dict) 모두 지원."""
    c = cat["categories"].get(ckey, ckey)
    return c["label"] if isinstance(c, dict) else c


def fmt_size(kb: int) -> str:
    """KB → 사람이 읽는 크기."""
    if kb >= 1024:
        return f"{kb/1024:.1f} MB"
    return f"{kb} KB"


def total_size_kb(names, cat: dict) -> int:
    return sum(cat["skills"].get(n, {}).get("size_kb", 0) for n in names)


# ── printing ────────────────────────────────────────────────────────────────
def print_catalog(cat: dict) -> None:
    skills = cat["skills"]
    groups = cat.get("groups", {})
    total_kb = total_size_kb(skills.keys(), cat)
    print("\n=== 설치 가능한 스킬 (총 %d개, %s) ===" % (len(skills), fmt_size(total_kb)))

    # 상위 그룹 → 카테고리 → 스킬 (신버전 구조). 그룹 없으면 카테고리만.
    cat_keys = list(cat["categories"].keys())
    if groups:
        for gkey, glabel in groups.items():
            if gkey == "connect":
                continue  # 커넥터는 별도 섹션에서
            print(f"\n▼ {glabel}")
            for ckey in cat_keys:
                c = cat["categories"][ckey]
                if isinstance(c, dict) and c.get("group") != gkey:
                    continue
                _print_category(cat, ckey)
    else:
        for ckey in cat_keys:
            _print_category(cat, ckey)

    # 외부 연동 커넥터
    conns = {k: v for k, v in cat.get("connectors", {}).items() if not k.startswith("_")}
    if conns:
        print(f"\n▼ {groups.get('connect', '외부 연동 (커넥터)')}")
        print("  (scripts/connectors/ — credentials.json 필요, draft-first/write-guard)")
        for name, m in conns.items():
            print(f"  - {name:10s} {m['role']}  [{m.get('needs','')}]")

    print("\n=== 프리셋 ===")
    for pkey, p in cat["presets"].items():
        names = all_skill_names(cat) if p["skills"] == ["__ALL__"] else p["skills"]
        print(f"  - {pkey:16s} {p['label']} — {p['desc']} ({len(names)}개, {fmt_size(total_size_kb(names, cat))})")


def _print_category(cat: dict, ckey: str) -> None:
    skills = cat["skills"]
    members = [n for n, m in skills.items() if m["category"] == ckey]
    if not members:
        return
    print(f"  [{_cat_label(cat, ckey)}]")
    for n in sorted(members):
        req = skills[n].get("requires", [])
        req_note = f"  (필요: {', '.join(req)})" if req else ""
        sz = fmt_size(skills[n].get("size_kb", 0))
        print(f"    - {n:26s} {sz:>8s}  {skills[n]['role']}{req_note}")


# ── interactive menu ────────────────────────────────────────────────────────
def interactive_select(cat: dict) -> list[str]:
    presets = list(cat["presets"].items())
    print("\n무엇을 하실 건가요? 아래에서 고르세요.\n")
    for i, (pkey, p) in enumerate(presets, 1):
        n = str(len(all_skill_names(cat) if p["skills"] == ["__ALL__"] else p["skills"]))
        print(f"  {i}. {p['label']} — {p['desc']} ({n}개)")
    print(f"  {len(presets)+1}. 직접 고르기 (개별 스킬 선택)")
    print()
    while True:
        raw = input("번호 입력 (여러 개면 쉼표, 예: 1,3): ").strip()
        if not raw:
            continue
        try:
            picks = [int(x) for x in raw.replace(" ", "").split(",")]
        except ValueError:
            print("  숫자로 입력해 주세요.")
            continue
        if any(p == len(presets) + 1 for p in picks):
            return interactive_individual(cat)
        chosen: list[str] = []
        ok = True
        for p in picks:
            if 1 <= p <= len(presets):
                chosen += expand_preset(presets[p - 1][0], cat)
            else:
                print(f"  {p}: 범위를 벗어났습니다.")
                ok = False
        if ok and chosen:
            return sorted(set(chosen))


def interactive_individual(cat: dict) -> list[str]:
    names = all_skill_names(cat)
    print("\n=== 개별 스킬 선택 ===")
    for i, n in enumerate(names, 1):
        print(f"  {i:2d}. {n:28s} {cat['skills'][n]['role']}")
    print()
    while True:
        raw = input("설치할 번호들 (쉼표, 예: 1,5,12): ").strip()
        try:
            picks = [int(x) for x in raw.replace(" ", "").split(",") if x]
        except ValueError:
            print("  숫자로 입력해 주세요.")
            continue
        chosen = [names[p - 1] for p in picks if 1 <= p <= len(names)]
        if chosen:
            return sorted(set(chosen))
        print("  하나 이상 골라 주세요.")


# ── copy ────────────────────────────────────────────────────────────────────
# `.distignore` 는 "배포하면 안 되는 것"의 SSOT 다. 예전에는 이 설치기가 그 파일을
# 읽지 않아서, 규칙은 선언돼 있는데 설치 경로에는 아무 효력이 없었다(2026-08-07 실측).
# 패턴 해석은 scripts/distignore.py 한 곳에서만 한다 — 여기에 복사하면 드리프트가 난다.
sys.path.insert(0, str(ROOT / "scripts"))
try:
    from distignore import load_patterns, ignore_factory  # type: ignore
    _DISTIGNORE_OK = True
except ImportError:  # 모듈이 빠진 배포본에서도 설치는 되어야 한다
    _DISTIGNORE_OK = False

_FALLBACK_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".cache")


def _build_ignore():
    """복사 시 제외 콜백. `.distignore` 를 쓰되, 없으면 최소 캐시 제외로 물러선다."""
    if not _DISTIGNORE_OK:
        return _FALLBACK_IGNORE
    return ignore_factory(SKILLS_DIR, load_patterns(ROOT))


def default_dest() -> tuple[Path, str]:
    """설치 대상 기본값을 환경에서 정한다. (경로, 근거) 를 돌려준다.

    `~/.claude/skills` 를 무조건 기본값으로 쓰면 Codex 사용자에게는 아무 의미가
    없는 폴더에 설치된다 — 그쪽은 스킬 등록 개념이 없고 AGENTS.md 가 가리키는
    경로를 읽을 뿐이다. 그래서 무엇이 있는지 보고 정한다.
    """
    home = Path.home()
    claude = home / ".claude"
    codex = home / ".codex"
    if claude.is_dir() and not codex.is_dir():
        return claude / "skills", "Claude Code 환경 감지"
    if codex.is_dir() and not claude.is_dir():
        # Codex 는 스킬 레지스트리가 없다. 현재 폴더에 두고 AGENTS.md 가
        # 가리키게 하는 편이 정직하다 — 자세한 건 CODEX.md.
        return Path.cwd() / "skills", "Codex 환경 감지 (CODEX.md 참조)"
    if claude.is_dir() and codex.is_dir():
        return claude / "skills", "Claude Code·Codex 모두 감지 — Claude 쪽 기본"
    return Path.cwd() / "skills", "에이전트 미감지 — 현재 폴더"


_CATALOG_CACHE: dict | None = None


def _catalog_flag(skill: str, flag: str) -> bool:
    """카탈로그에서 스킬의 불리언 플래그를 읽는다 (없으면 False).

    `external: true` 인 스킬은 이 저장소에 파일이 없다 — Anthropic 소유라
    재배포할 수 없기 때문이다. 카탈로그에서 아예 지우지 않는 이유는,
    `manuscript-pipeline` 등이 이들을 `requires` 로 선언하고 있어서
    지우면 resolve() 가 "알 수 없는 스킬"로 죽기 때문이다. 선언은 남기고
    복사만 건너뛴다.
    """
    global _CATALOG_CACHE
    if _CATALOG_CACHE is None:
        try:
            with CATALOG_PATH.open(encoding="utf-8") as f:
                _CATALOG_CACHE = json.load(f).get("skills", {})
        except Exception:
            _CATALOG_CACHE = {}
    return bool(_CATALOG_CACHE.get(skill, {}).get(flag))


def install(final: list[str], dest: Path, apply: bool, force: bool = False) -> None:
    """스킬을 대상 폴더에 설치한다.

    기본은 **비파괴 병합**이다: 배포판 파일은 대상에 덮어쓰되, 대상에만 있던
    파일은 건드리지 않는다. 이전 버전은 `shutil.rmtree(dst)` 로 대상 폴더를
    통째로 지운 뒤 복사했고, 그 때문에 사용자가 자기 런타임에 직접 넣어둔
    스크립트가 설치 한 번에 사라졌다(2026-08-07 실측: manuscript-pipeline
    scripts 7종, endnote-citation-injection 3종, scientific-validation 3종).

    옛 동작(완전 교체)이 필요하면 force=True 로 명시해야 한다.
    계약과 회귀 테스트는 tests/test_install_nondestructive.py 참조.
    """
    dest_skills = dest / "skills" if dest.name != "skills" else dest
    print(f"\n대상 폴더: {dest_skills}")
    if force:
        print("  ※ --force: 대상 스킬 폴더를 통째로 교체합니다(기존 파일 삭제).")
    ignore_cb = _build_ignore()
    external = [n for n in final if _catalog_flag(n, "external")]
    final = [n for n in final if n not in external]
    for name in final:
        src = SKILLS_DIR / name
        dst = dest_skills / name
        exists = dst.exists()
        if not exists:
            tag = "새로"
        elif force:
            tag = "교체"
        else:
            tag = "병합"
        if apply:
            dest_skills.mkdir(parents=True, exist_ok=True)
            if exists and force:
                shutil.rmtree(dst)
            # dirs_exist_ok=True → 대상에만 있는 파일을 남긴 채 배포판 파일만 덮어쓴다
            shutil.copytree(src, dst, ignore=ignore_cb, dirs_exist_ok=True)
            print(f"  [설치] {name}  ({tag})")
        else:
            print(f"  [미리보기] {name}  ({tag} 설치 예정)")
    if external:
        print("\n── 이 저장소에 없는 스킬 (직접 준비 필요) ──")
        for name in external:
            print(f"  ! {name}")
        print("  Anthropic 이 제공하는 스킬이라 라이선스상 재배포할 수 없어 빠져 있습니다.")
        print("  Claude Code 에서 해당 파일 형식을 다루면 자동으로 쓰이며, 없다면")
        print("  Anthropic 제공 경로로 받아 ~/.claude/skills/ 에 두세요.")
        print("  자세한 안내: docs/12_문서스킬_직접_준비하기.md")

    if not apply:
        print("\n※ 미리보기입니다. 실제로 설치하려면 --apply 를 붙여 다시 실행하세요.")
    else:
        print(f"\n완료: {len(final)}개 스킬을 설치했습니다.")
        _run_doctor_after_install()


def _run_doctor_after_install() -> None:
    """설치 직후 doctor.py 를 자동 실행한다.

    새 컴퓨터에서 설치가 "성공"했다는 출력만 보고 넘어가면, 그 환경에 훅이
    실제로 돌아갈 셸이 있는지(check_shell_env) 같은 문제는 사람이 따로
    `python doctor.py` 를 떠올려 실행하지 않는 한 발견되지 않는다. 설치가
    끝나는 시점이 그 환경 조건을 가장 저렴하게 확인할 수 있는 때이므로 여기서
    바로 돌린다. 실패해도 설치 자체를 롤백하지 않는다 — doctor 는 진단 도구지
    설치를 막는 게이트가 아니다.
    """
    import subprocess
    doctor_path = ROOT / "doctor.py"
    if not doctor_path.is_file():
        return
    print("\n── 설치 후 자동 점검 (doctor.py) ──")
    print("  (환경 점검만 빠르게 — 전체 자체테스트는 `python doctor.py` 로 직접 실행)")
    try:
        proc = subprocess.run(
            [sys.executable, str(doctor_path), "--quick"], cwd=str(ROOT),
            timeout=60)
        if proc.returncode != 0:
            print("  ⚠ doctor.py 가 FAIL 을 보고했습니다 — 위 출력을 확인하세요.")
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"  ⚠ doctor.py 자동 실행 실패: {exc}")
        print(f"  수동으로 실행하세요: python {doctor_path}")


# ── main ────────────────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(
        description="sci-toolkit 선택 설치기 — 원하는 기능만 골라 설치")
    ap.add_argument("--list", action="store_true", help="카탈로그·프리셋만 출력하고 종료")
    ap.add_argument("--preset", help="프리셋 키 (paper-writing/literature/molbio/data-figures/documents/all)")
    ap.add_argument("--skills", help="개별 스킬 쉼표목록 (예: docx,xlsx)")
    ap.add_argument("--dest", default=None,
                    help="설치 대상 폴더 (미지정 시 감지된 에이전트에 맞춰 결정)")
    ap.add_argument("--apply", action="store_true", help="실제로 복사 (없으면 미리보기)")
    ap.add_argument("--force", action="store_true",
                    help="대상 스킬 폴더를 통째로 교체 (대상에만 있던 파일도 삭제). "
                         "기본은 비파괴 병합이며, 이 옵션은 명시적으로 필요할 때만 쓴다.")
    args = ap.parse_args()

    _shell_env_notice()

    cat = load_catalog()

    if args.list:
        print_catalog(cat)
        return

    # 1) 선택 결정
    if args.preset:
        selection = expand_preset(args.preset, cat)
    elif args.skills:
        selection = [s.strip() for s in args.skills.split(",") if s.strip()]
    else:
        selection = interactive_select(cat)

    # 2) 의존성 해소
    final, pulled_by = resolve(selection, cat)

    # 3) 요약
    print("\n── 설치 요약 ──")
    print(f"고른 스킬 ({len(selection)}개): {', '.join(sorted(set(selection)))}")
    if pulled_by:
        print("자동 추가된 필수 의존성:")
        for dep, srcs in sorted(pulled_by.items()):
            print(f"  + {dep}  ← {', '.join(srcs)} 가 필요로 함")
    print(f"최종 설치 대상: {len(final)}개 ({fmt_size(total_size_kb(final, cat))})")

    # 4) 설치
    if args.dest:
        dest = Path(args.dest).expanduser()
    else:
        dest, why = default_dest()
        print(f"\n설치 위치를 지정하지 않아 자동 결정했습니다 — {why}")
        print(f"  {dest}")
        print("  다른 곳에 넣으려면 --dest <경로> 를 쓰세요.")
    install(final, dest, args.apply, force=args.force)


if __name__ == "__main__":
    main()
