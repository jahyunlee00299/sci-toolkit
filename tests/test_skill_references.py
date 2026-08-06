#!/usr/bin/env python3
"""스킬 문서가 가리키는 대상이 실제로 존재하는지 검사한다.

배포판에서 가장 흔한 고장은 코드 오류가 아니라 **죽은 참조**다. 스킬 문서가
"`scripts/foo.py` 를 실행하라" / "`bar` 스킬을 써라" 라고 지시하는데 그 파일이나
스킬이 패키지에 없으면, 사용자는 지시를 따르다 실패한다. doctor.py 가 잡는
무결성(해시)·시크릿과는 다른 축이라 별도 검사가 필요하다.

실행:
    python tests/test_skill_references.py           # exit 0 = 통과
    python tests/test_skill_references.py --verbose # 확인한 참조까지 전부 출력

검사 대상:
1. 스킬 폴더 내부 파일 참조 (`scripts/x.py`, `references/y.md`, `assets/z.json`)
   - **대소문자까지** 비교한다. Windows 에서는 통과하지만 Linux/WSL 에서 깨지는
     `REFERENCE.md` vs `reference.md` 같은 불일치를 잡기 위함이다.
   - `<other-skill>` 를 함께 언급한 줄은 교차 스킬 참조로 보고 그 스킬 폴더에서도 찾는다.
2. 다른 스킬 이름 참조 (``foo`` skill / `foo` 스킬)
   - `deprecated/` 로 표시된 이력 서술은 제외한다(통합되어 사라진 이름을 기록한 것).
"""
import argparse
import io
import os
import re
import sys

# Windows 기본 콘솔은 cp949 라서 한글/기호 출력에서 죽는다. UTF-8로 맞춘다.
# TextIOWrapper 대신 reconfigure — 래퍼는 원본 스트림을 소유해서,
# import 후 GC 되면 호출자의 stdout 까지 닫아버린다(실측).
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_DIR = os.path.join(ROOT, "skills")

# scripts/foo.py, references/bar.md, assets/.env.example ...
FILE_REF_RE = re.compile(
    r"(?<![\w/.-])((?:scripts|references|assets|templates)/[A-Za-z0-9_./-]+)")
# `foo` skill / `foo` 스킬 / **foo** skill
SKILL_REF_RE = re.compile(
    r"[`*]{1,2}([a-z][a-z0-9-]{3,40})[`*]{1,2}\s*(?:skill|스킬)"
    r"|(?:skill|스킬)\s*[`*]{1,2}([a-z][a-z0-9-]{3,40})[`*]{1,2}")

# 백틱 없이 산문에 등장하는 스크립트 이름도 잡는다.
# "see body_typo_lint.py for the enforcement side" 처럼 코드 표시 없이 쓰인
# 파일명은 위의 FILE_REF_RE(경로 접두어 필요)와 백틱 기반 스캔 양쪽을 빠져나가,
# 실제로 존재하지 않는 도구 2개가 문서에 남아 있었다(2026-07-23 발견).
BARE_SCRIPT_RE = re.compile(r"(?<![\w/.-])([a-z][a-z0-9_]{3,60}\.py)\b")

TEXT_SUFFIXES = (".md", ".txt")
SKIP_DIRS = {"__pycache__", ".git", "node_modules"}

# 패키지에 없어도 정상인 스크립트 이름 — 사용자가 자기 프로젝트에서 만들 예시,
# 외부 라이브러리 내부 파일, 또는 일반 명사에 가까운 이름.
# 여기 넣을 때는 "왜 없어도 되는지" 이유를 반드시 함께 적을 것. 이유 없이 추가하면
# 이 검사는 그냥 통과 도장이 된다.
BARE_SCRIPT_ALLOWLIST = {
    # 사용자가 자기 환경에서 만들 스크립트 예시
    "my_analysis.py", "my_job.py",
    "script.py",            # publication-figures: "data.csv + script.py + figure.png" 산출물 규격 설명
    "example_module.py",    # 코드 품질 예시
    # 파이썬 관용/일반 이름 (특정 파일을 가리키지 않음)
    "setup.py", "app.py", "main.py", "train.py", "run.py", "test.py",
    # 외부 라이브러리 내부 구조를 설명하는 디렉토리 트리
    "converter.py",         # markitdown 패키지 내부 구조도 (우리 파일 아님)
    # 사용자가 원하면 만드는 선택적 헬퍼 ("있으면 짝을 맞춰라" 식 서술)
    "manuscript_workdir.py",
    # ── Anthropic 소유 문서 스킬 안의 파일들 (EXTERNAL_SKILLS 참조) ──
    # 이 패키지는 해당 스킬을 재배포할 수 없어 파일이 없다. 그래도 "그 스킬을 쓸 때는
    # 이렇게 하라"는 지식은 유효하므로 서술을 지우지 않는다. 사용자 환경에 스킬이
    # 있으면 그대로 동작하고, 없으면 docs/12 가 안내한다.
    "incremental_edit.py",          # docx: ZIP 무결성 보존 편집 세션
    "docx_preflight.py",            # docx: 구조 검증
    "word_validate.py",             # docx: Word COM ground-truth 검증
    "comment.py",                   # docx: 코멘트 삽입
    "inject_comments_from_csv.py",  # docx: CSV → 코멘트 일괄 삽입
    "pack.py",                      # docx/pptx: OOXML 재패킹
    "unpack.py",                    # docx/pptx: OOXML 해체
    "recalc.py",                    # xlsx: 수식 재계산·오류 스캔
}

# 이 패키지가 의존하지만 재배포할 수 없는 외부 스킬 (Anthropic 소유).
# 이름으로 참조되는 것은 죽은 참조가 아니라 "외부 의존"이다 — doctor.py 의
# EXTERNAL_SKILLS 와 같은 목록을 본다. docs/12 참조.
EXTERNAL_SKILLS = {"docx", "pdf", "pptx", "xlsx"}


def collect(skill_dir):
    """스킬 폴더 안의 모든 파일을 상대경로 집합으로."""
    out = set()
    for dp, dns, fns in os.walk(skill_dir):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for f in fns:
            out.add(os.path.relpath(os.path.join(dp, f), skill_dir).replace("\\", "/"))
    return out


def main():
    ap = argparse.ArgumentParser(description="스킬 문서의 죽은 참조 검사")
    ap.add_argument("--verbose", action="store_true", help="확인한 참조도 모두 출력")
    args = ap.parse_args()

    if not os.path.isdir(SKILLS_DIR):
        print(f"오류: skills/ 폴더가 없다 — {SKILLS_DIR}")
        return 2

    skills = sorted(d for d in os.listdir(SKILLS_DIR)
                    if os.path.isdir(os.path.join(SKILLS_DIR, d)))
    skillset = set(skills)
    have = {s: collect(os.path.join(SKILLS_DIR, s)) for s in skills}

    # 패키지 전체의 .py 파일 이름(경로 제외) — 산문에 쓰인 스크립트 이름 대조용.
    # 스킬 폴더 밖(scripts/, tests/, install/, 루트)도 포함해야 한다.
    all_py_names = set()
    for dp, dns, fns in os.walk(ROOT):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for f in fns:
            if f.endswith(".py"):
                all_py_names.add(f)

    dead_files, dead_skills, case_only, dead_bare = [], [], [], []
    checked = 0

    for s in skills:
        root = os.path.join(SKILLS_DIR, s)
        lower_map = {h.lower(): h for h in have[s]}
        for dp, dns, fns in os.walk(root):
            dns[:] = [d for d in dns if d not in SKIP_DIRS]
            for f in fns:
                if not f.lower().endswith(TEXT_SUFFIXES):
                    continue
                p = os.path.join(dp, f)
                srcrel = os.path.relpath(p, root).replace("\\", "/")
                try:
                    lines = open(p, encoding="utf-8", errors="ignore").read().splitlines()
                except OSError:
                    continue
                for i, line in enumerate(lines, 1):
                    # --- 백틱 없이 산문에 쓰인 스크립트 이름 ---
                    for m in BARE_SCRIPT_RE.finditer(line):
                        fname = m.group(1)
                        if fname in BARE_SCRIPT_ALLOWLIST:
                            continue
                        checked += 1
                        if fname not in all_py_names:
                            dead_bare.append((s, srcrel, i, fname, line.strip()[:90]))

                    # --- 파일 참조 ---
                    for m in FILE_REF_RE.finditer(line):
                        ref = m.group(1)
                        if "." not in os.path.basename(ref):
                            continue          # 확장자 없는 건 디렉토리 언급으로 본다
                        checked += 1
                        if ref in have[s]:
                            continue
                        # 배포판 루트의 공용 도구(scripts/ref_fetch.py 등)를 가리키는
                        # 것도 정상이다. 스킬 문서가 루트 도구를 쓰는 일은 흔한데,
                        # 이걸 "스킬 폴더 안의 scripts/" 로만 해석하면 문서가 억지로
                        # ../../scripts/ 같은 상대경로를 쓰도록 강요당한다.
                        if os.path.isfile(os.path.join(ROOT, ref)):
                            continue
                        # 다른 스킬을 언급한 문맥이면 교차 스킬 참조로 본다.
                        # 문장이 줄바꿈되며 스킬명과 파일명이 다른 줄에 놓이는 일이
                        # 흔하므로, 판정은 줄 단위가 아니라 앞뒤 2줄 창으로 본다.
                        window = "\n".join(lines[max(0, i - 3):i + 2])
                        others = [o for o in skillset if o != s and o in window]
                        if any(ref in have[o] for o in others):
                            continue
                        alt = lower_map.get(ref.lower())
                        if alt:
                            case_only.append((s, srcrel, i, ref, alt))
                        else:
                            dead_files.append((s, srcrel, i, ref))
                    # --- 스킬 이름 참조 ---
                    if "deprecated" in line.lower():
                        continue
                    for m in SKILL_REF_RE.finditer(line):
                        name = m.group(1) or m.group(2)
                        if not name or name == s:
                            continue
                        checked += 1
                        if name in EXTERNAL_SKILLS:
                            # 재배포할 수 없어 일부러 빠진 스킬. 참조는 유효하다.
                            continue
                        if name not in skillset:
                            dead_skills.append((s, srcrel, i, name, line.strip()[:90]))

    print(f"스킬 {len(skills)}종에서 참조 {checked}건 확인")

    fails = 0
    if case_only:
        fails += len(case_only)
        print(f"\n=== 대소문자 불일치 {len(case_only)}건 "
              f"(Windows는 통과, Linux/WSL에서 깨짐) ===")
        for s, src, ln, ref, alt in case_only:
            print(f"  {s}/{src}:{ln}  {ref}  ->  실제 파일은 {alt}")
    if dead_files:
        fails += len(dead_files)
        print(f"\n=== 존재하지 않는 파일 참조 {len(dead_files)}건 ===")
        for s, src, ln, ref in dead_files:
            print(f"  {s}/{src}:{ln}  {ref}")
    if dead_skills:
        fails += len(dead_skills)
        print(f"\n=== 배포판에 없는 스킬 참조 {len(dead_skills)}건 ===")
        for s, src, ln, name, ctx in dead_skills:
            print(f"  {s}/{src}:{ln}  '{name}'")
            print(f"      {ctx}")
    if dead_bare:
        fails += len(dead_bare)
        print(f"\n=== 존재하지 않는 스크립트를 산문에서 언급 {len(dead_bare)}건 ===")
        print("    (백틱 없이 쓰여 경로 검사를 빠져나간 것들)")
        for s, src, ln, name, ctx in dead_bare:
            print(f"  {s}/{src}:{ln}  {name}")
            print(f"      {ctx}")

    if fails:
        print(f"\nFAIL — 죽은 참조 {fails}건. 사용자가 이 지시를 따르면 실패한다.")
        return 1
    print("\nALL PASS — 모든 참조가 실존한다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
