#!/usr/bin/env python3
"""AGENTS.md §0 라우팅 표가 가리키는 대상이 전부 실존하는지 검사한다.

§0 은 에이전트가 가장 먼저 읽고 따르는 표다. 여기에 없는 스킬이나 스크립트가
적혀 있으면, 에이전트는 존재하지 않는 도구를 쓰려다 실패하거나 — 더 나쁘게는 —
그럴듯하게 지어낸다. 문서 중에서 가장 먼저 깨지면 안 되는 부분이라 별도로 검사한다.

실행:
    python tests/test_agents_routing.py           # exit 0 = 통과
    python tests/test_agents_routing.py --verbose
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
AGENTS = os.path.join(ROOT, "AGENTS.md")
SKILLS_DIR = os.path.join(ROOT, "skills")

# 파일이 아니라 개념/출력물 이름으로 등장하는 것들 — 검사 대상 아님
NOT_A_PATH = {
    "refs_report.json",          # ref_fetch.py 가 만들어내는 산출물
    "discrepancies",             # 리포트 안의 필드 이름
    "not_found",
    "PROJECT_STRUCTURE.md",
}
# 이 저장소의 스킬이 아니라 사용자가 설치해 쓰는 실행기 이름. §0 이 게이트 명령으로
# 직접 부르는 것들이라 스킬 이름 패턴(소문자+하이픈)에 걸리지만, `skills/` 아래에
# 있을 이유가 없다. 여기에 추가할 때는 "정말 외부 CLI 인가"를 확인할 것 —
# 오타난 스킬 이름을 여기 넣으면 이 검사가 무력화된다.
RUNNER_COMMANDS = {"pytest"}
# 경로 안에 플레이스홀더가 있으면 실물 대조 불가
PLACEHOLDER_RE = re.compile(r"<[^>]+>")

# 이 패키지가 의존하지만 재배포할 수 없는 Anthropic 소유 스킬.
# §0 이 이들을 가리키는 것은 죽은 참조가 아니라 외부 의존이다 — 사용자 환경에
# 있으면 그대로 동작하고, 없으면 docs/12 가 안내한다. doctor.py 의
# EXTERNAL_SKILLS 와 같은 목록을 유지할 것(한쪽만 고치면 갈라진다).
EXTERNAL_SKILLS = {"docx", "pdf", "pptx", "xlsx"}


def resolve(token, skills):
    """토큰이 가리키는 실제 파일이 있는지 확인. 있으면 그 경로, 없으면 None."""
    cand = token.strip()
    # "python x.py --flag" / "x.py --count-only" -> 실제 경로 부분만
    parts = [p for p in cand.split() if not p.startswith("-")]
    parts = [p for p in parts if p not in ("python", "python3", "bash", "sh")]
    if not parts:
        return "skip"
    cand = parts[0]

    if cand in NOT_A_PATH:
        return "skip"
    if PLACEHOLDER_RE.search(cand):
        return "skip"
    # 외부 스킬 자체(`docx`) 또는 그 안의 경로(`docx/scripts/x.py`)
    if cand in EXTERNAL_SKILLS or cand.split("/")[0] in EXTERNAL_SKILLS:
        return "skip"

    tries = [os.path.join(ROOT, cand)]
    # `docx/scripts/x.py` 처럼 스킬 이름으로 시작하면 skills/ 아래
    head = cand.split("/")[0]
    if head in skills:
        tries.append(os.path.join(SKILLS_DIR, cand))
    # `scripts/x.py` 처럼 스킬 내부 상대경로면 각 스킬 아래에서 찾는다
    if not cand.startswith(("skills/", "scripts/", "tests/", "config/", "install/")):
        tries += [os.path.join(SKILLS_DIR, s, cand) for s in skills]
    elif cand.startswith("scripts/"):
        tries += [os.path.join(SKILLS_DIR, s, cand) for s in skills]

    for t in tries:
        if os.path.exists(t):
            return os.path.relpath(t, ROOT)
    return None


def main():
    ap = argparse.ArgumentParser(description="AGENTS.md §0 라우팅 표 검사")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if not os.path.isfile(AGENTS):
        print(f"오류: AGENTS.md 가 없다 — {AGENTS}")
        return 2
    text = open(AGENTS, encoding="utf-8").read()

    m = re.search(r"^## 0\. Routing.*?(?=^## 1\.)", text, re.S | re.M)
    if not m:
        print("FAIL — AGENTS.md 에 '## 0. Routing' 섹션이 없다. "
              "이 표는 에이전트의 진입점이므로 반드시 있어야 한다.")
        return 1
    section = m.group(0)

    skills = set(os.listdir(SKILLS_DIR))
    tokens = sorted(set(re.findall(r"`([^`]+)`", section)))

    dead_files, dead_skills, ok = [], [], []
    for tok in tokens:
        t = tok.strip()
        looks_like_path = t.endswith((".py", ".json", ".md")) or "/" in t
        if looks_like_path:
            r = resolve(t, skills)
            if r is None:
                dead_files.append(t)
            elif r != "skip":
                ok.append((t, r))
        elif re.fullmatch(r"[a-z][a-z0-9-]{3,40}", t):
            if t in skills:
                ok.append((t, f"skills/{t}"))
            elif t in EXTERNAL_SKILLS:
                ok.append((t, "external (Anthropic-owned, see docs/12)"))
            elif t in RUNNER_COMMANDS:
                ok.append((t, "external runner (user-installed CLI)"))
            elif t not in NOT_A_PATH:
                dead_skills.append(t)

    print(f"§0 라우팅 표: 토큰 {len(tokens)}개 중 대조 대상 "
          f"{len(ok) + len(dead_files) + len(dead_skills)}개")
    if args.verbose:
        for t, r in ok:
            print(f"   OK  {t}  ->  {r}")

    fails = len(dead_files) + len(dead_skills)
    if dead_files:
        print(f"\n=== 실존하지 않는 파일 {len(dead_files)}건 ===")
        for t in dead_files:
            print(f"   {t}")
    if dead_skills:
        print(f"\n=== 실존하지 않는 스킬 {len(dead_skills)}건 ===")
        for t in dead_skills:
            print(f"   {t}")

    if fails:
        print(f"\nFAIL — §0 이 없는 것을 가리킨다 {fails}건. "
              f"에이전트가 이 표를 그대로 따르므로 즉시 고쳐야 한다.")
        return 1
    print("\nALL PASS — §0 의 모든 스킬·스크립트가 실존한다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
