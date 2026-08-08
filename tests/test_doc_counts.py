#!/usr/bin/env python3
"""문서에 적힌 개수가 실제와 맞는지 검사한다.

README 첫 화면의 `스킬 26종 · 회귀 테스트 12종` 같은 줄은 사용자가 이 패키지를
판단하는 첫 숫자인데, 스킬을 넣고 빼도 아무도 갱신하지 않는다. 260807 실측:
스킬 5개를 빼고 1개를 더한 커밋이 `31 → 26` 으로만 고쳤다(뺀 것만 반영하고 더한
것을 빠뜨림). 실제 동봉 수는 27 이었고, 그 상태로 doctor 10 OK · 테스트 15개
전부 통과 · CI 초록불이었다 — **아무 검사도 개수를 보고 있지 않았기 때문이다.**

각 숫자의 SSOT:

  스킬 N종        = config/catalog.json 중 external 이 아닌 것 = skills/ 폴더 수
                    (둘이 다르면 그 자체가 결함이므로 함께 검사한다)
  회귀 테스트 N종  = tests/test_*.py 파일 수
  안전 가드 N종    = hooks/*.sh 중 러너(_run_hooks_chained.sh) 제외
  초심자 문서 N종  = docs/ 의 번호 붙은 문서(00_ ~ 12_)

숫자를 새로 문서에 쓸 때는 여기에 검사도 같이 추가할 것. 검사 없는 숫자는
반드시 낡는다.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

ROOT = Path(__file__).resolve().parent.parent


def actual_counts() -> dict[str, int]:
    catalog = json.loads((ROOT / "config" / "catalog.json").read_text(encoding="utf-8"))
    skills = catalog["skills"]
    bundled = {k for k, v in skills.items() if not v.get("external")}
    on_disk = {p.name for p in (ROOT / "skills").iterdir() if p.is_dir()}
    hooks = {p.name for p in (ROOT / "hooks").glob("*.sh")
             if not p.name.startswith("_")}
    docs = {p.name for p in (ROOT / "docs").glob("*.md")
            if re.match(r"^\d{2}_", p.name)}
    tests = {p.name for p in (ROOT / "tests").glob("test_*.py")}
    return {
        "catalog_total": len(skills),
        "bundled": len(bundled),
        "on_disk": len(on_disk),
        "tests": len(tests),
        "hooks": len(hooks),
        "docs": len(docs),
        "_bundled_set": bundled,
        "_disk_set": on_disk,
    }


def find_counts(path: Path, pattern: str) -> list[tuple[int, int, str]]:
    """(줄번호, 숫자, 줄) 목록. pattern 은 숫자를 그룹 1로 잡아야 한다."""
    out = []
    rx = re.compile(pattern)
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        for m in rx.finditer(line):
            out.append((i, int(m.group(1)), line.strip()[:80]))
    return out


def main() -> int:
    a = actual_counts()
    failures: list[str] = []
    checked = 0

    # 0) catalog 와 디스크가 같은 스킬 집합을 말하는가
    checked += 1
    only_catalog = sorted(a["_bundled_set"] - a["_disk_set"])
    only_disk = sorted(a["_disk_set"] - a["_bundled_set"])
    if only_catalog or only_disk:
        failures.append(
            f"catalog 와 skills/ 폴더가 불일치 — catalog에만 {only_catalog}, "
            f"디스크에만 {only_disk}")

    # 0.5) tests/ 의 모든 테스트가 doctor 를 통해 실제로 실행되는가
    #
    # doctor 의 SELF_TEST_SCRIPTS 는 하드코딩 목록이고, CI 는 doctor 하나만 부른다.
    # 그래서 tests/ 에 파일을 놓고 등록을 잊으면 그 테스트는 **어디에서도 돌지
    # 않으면서** 존재하는 것처럼 보인다 — 초록불이 실제 감지력보다 커지는 전형적인
    # 방식이다. 지금은 두 개(test_agents_routing·test_skill_references)가 전용
    # check 로 따로 불리므로 등록 목록에는 없지만 실행은 된다. 판정 기준을
    # "SELF_TEST_SCRIPTS 에 있는가" 가 아니라 "doctor.py 가 이 파일을 언급하는가"
    # 로 둔 이유다.
    checked += 1
    doctor_src = (ROOT / "doctor.py").read_text(encoding="utf-8")
    unreached = sorted(p.name for p in (ROOT / "tests").glob("test_*.py")
                       if p.name not in doctor_src)
    if unreached:
        failures.append(
            f"doctor 가 실행하지 않는 테스트 {len(unreached)}개: {unreached}"
            " — doctor.py 의 SELF_TEST_SCRIPTS 에 추가하라. CI 는 doctor 만 부르므로"
            " 등록하지 않으면 이 테스트는 영원히 돌지 않는다")

    # 1) 문서에 적힌 개수
    specs = [
        ("README.md", r"스킬\s+(\d+)종", a["bundled"], "동봉 스킬"),
        ("README.md", r"회귀 테스트\s+(\d+)종", a["tests"], "회귀 테스트"),
        ("README.md", r"안전 가드\s+(\d+)종", a["hooks"], "안전 가드"),
        ("README.md", r"초심자 문서\s+(\d+)종", a["docs"], "초심자 문서"),
        ("QUICKSTART.md", r"스킬\s+(\d+)개와", a["catalog_total"], "설치기 목록"),
        ("QUICKSTART.md", r"동봉\s+(\d+)개", a["bundled"], "동봉 스킬"),
        ("QUICKSTART.md", r"한 번에\s+(\d+)개를", a["bundled"], "동봉 스킬"),
        ("config/catalog.json", r"(\d+)개 스킬 모두", a["catalog_total"], "all 프리셋"),
    ]
    for fname, pat, expect, label in specs:
        p = ROOT / fname
        if not p.exists():
            continue
        hits = find_counts(p, pat)
        if not hits:
            continue          # 그 문구가 없는 것은 결함이 아니다
        for ln, got, ctx in hits:
            checked += 1
            if got != expect:
                failures.append(
                    f"{fname}:{ln}  {label} {got} → 실제 {expect}   ({ctx})")

    if failures:
        print(f"FAIL — 문서 개수 불일치 {len(failures)}건")
        for f in failures:
            print(f"  - {f}")
        print("\n문서를 고치거나, 개수 정의가 바뀌었다면 이 테스트의 SSOT 도 함께 고칠 것.")
        return 1

    print(f"ALL PASS — 문서 개수 {checked}건 "
          f"(동봉 {a['bundled']} · catalog {a['catalog_total']} · "
          f"테스트 {a['tests']} · 가드 {a['hooks']} · 문서 {a['docs']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
