#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
연구마커 스캐너 양방향 회귀 테스트.

배경 (실측, 2026-08-07):
  이 배포판은 "미공개 연구명을 정화했다"고 문서에 적어두고도 실제로는
  RoGDH / RsGDH / LpNoxV / cascade ODE 전문 / scgre3 / 사설 레포명을
  그대로 담은 채 v1.2.0 으로 나갔다. doctor.py 의 SENTINEL 스캔은
  secrets.json · API 키 · Tailscale IP · 한국인 실명만 봤기 때문에
  **이 유형은 애초에 검사 대상이 아니었다.** 그래서 "정화 완료"라는
  자기서술과 디스크의 실제 내용이 갈렸다.

MUST_FLAG 에 들어있는 문자열은 전부 **실제로 배포판에서 발견된 것**이다.
케이스를 지우거나 약화시키면 그 순간 같은 유출이 다시 통과한다.

MUST_NOT_FLAG 는 반대 방향 — 일반 생화학 표기(NADH, NADPH, Km, kcat)와
분류학적 종 접두어 설명은 정상적인 교육 콘텐츠이므로 절대 걸리면 안 된다.
과차단은 스캐너를 끄게 만들고, 꺼진 스캐너는 없는 것과 같다.
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
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location("doctor", ROOT / "doctor.py")
_doctor = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
# doctor.py 는 @dataclass 를 쓴다. dataclasses 는 클래스의 __module__ 을
# sys.modules 에서 되찾으므로, exec_module 전에 등록해두지 않으면
# AttributeError('NoneType' object has no attribute '__dict__') 로 죽는다.
sys.modules["doctor"] = _doctor
_spec.loader.exec_module(_doctor)

scan_research_markers = _doctor.scan_research_markers

# ── 실제로 배포판에서 발견된 유출 (전부 차단되어야 한다) ──────────────────
MUST_FLAG = [
    # 효소 종 접두 + 실제 약어 (domain_abbrev_registry.md:12,14 등 4개 파일)
    ("종 prefix italic: *Ro*GDH, *Rs*GDH", "RoGDH"),
    ("| NADH oxidase | Nox | *Lp*NoxV (engineered variant) |", "LpNoxV"),
    ("**효소 접두**: *Ro*GDH 등 species prefix만 이탤릭", "RoGDH"),
    ("R1 | 효소명: 종 prefix 2글자만 italic (`*Ro*GDH`) |", "RoGDH"),
    ("**효소 약어**: 첫 언급 시 전체 이름 (BsGDH, PsFDH 등)", "BsGDH/PsFDH"),
    # cascade ODE (docx/SKILL.md:1089-1143)
    ("# d[D-Gal]/dt = -vXR", "vXR"),
    ("# d[NAD+]/dt = -vGDH + vNOX", "vGDH/vNOX"),
    ("# vFDH = (Vmax,FDH * [HCOO-]) / (Km,FDH + [HCOO-])", "vFDH"),
    ("para = omath(ddt('D-Gal') + r(' = -') + vsub('XR'))", "vsub('XR')"),
    ("# kLa = α · N^β  (Eq. S5)", "kLa 상관식"),
    ("Vmax,XR -> sub(ri('V'), rp('max,XR'))", "Vmax,XR"),
    ("Km,FDH / KiA,XR / KmB,GDH / KiQ", "KiA,XR"),
    ("kdeg,GDH 는 프로젝트 효소 subscript 라 걸려야 한다", "kdeg,GDH"),
    # 미공개 변이/저장소명
    ("참조 예시: `F_figS2_scgre3_activity/script.py`", "scgre3"),
    ("all git repos (claude-scientific-skills, UDH_Clustering, Kinetic-modeling)", "UDH_Clustering"),
    ("PeakPicker 레포(~/PeakPicker)의 알고리즘을 stdlib only로 포팅", "PeakPicker"),
    # 연구 주제어
    ("tagatose production from D-galactose", "tagatose"),
    ("L-ribose isomerase screening", "L-ribose"),
]

# ── 정상 교육 콘텐츠 (절대 걸리면 안 된다) ──────────────────────────────
MUST_NOT_FLAG = [
    # 일반 조효소 표기 규칙 (academic-term-rules 의 본체)
    "**Coenzymes**: NAD+, NADH, NADP+, NADPH (superscript+ required)",
    "| nadph | NADPH |",
    "`NAD+-dependent`, `NADH-dependent` — hyphenated modifier",
    "NAD+/NADH ratio, NADP+:NAD+",
    # 일반 동역학 기호
    "kcat/Km 는 이탤릭으로 쓴다",
    "Vmax 와 Km 은 Michaelis-Menten 파라미터다",
    "Report kcat, Km, and kcat/Km with units",
    # 조효소 subscript 는 어느 redox 시스템에나 있다 — 프로젝트 고유가 아니다.
    # 260807 실측: 이걸 막았더니 정화된 대체 텍스트 자신이 스캐너에 걸렸다.
    "kdeg = sub(ri('k'), rp('deg,NADH'))",
    "kdeg,NADH / kcat -> sub(ri('k'), rp('deg,NADH'))",
    # 분류학적 종 접두어 설명 (실제 라틴 학명과 매핑되는 일반 규칙)
    "종 prefix만 italic, 효소 자체는 roman: `*Ec*XylA`",
    "변이체 표기: `*Ec*XylA(G171R/L172R)`",
    "BsGDH (glucose dehydrogenase from *B. subtilis*)" .replace("BsGDH", "XxDH"),
    # 익명화된 예시 (정화 후의 올바른 형태 — 이게 걸리면 정화가 불가능해진다)
    "('MW: Enzyme1 (E1)', 37000.0, 'g/mol', 'SI Fig. S1 (example)')",
    "| Glucose dehydrogenase | GDH | 종 prefix italic: *Xx*GDH |",
    "d[Substrate]/dt = -v1",
    "v1 = (Vmax,E1 * [S]) / (Km,E1 + [S])",
    # 일반 단어로서의 등장
    "This rule applies to all git repos (repo-a, repo-b, etc.)",
    "Peak picking is handled by the bundled parser.",
    # 아래 3종은 260807 스윕에서 오탐으로 판정된 것들이다. 근거를 남긴다 —
    # 다음 사람이 "왜 이건 안 막나"를 다시 조사하지 않도록.
    #  · D-Gal / D-galactose = 문헌에 흔한 상용 당류이고, 스킬들이 "약어와 full name을
    #    섞지 말라"는 일반 규칙을 가르치는 데 정당하게 쓴다. 막으면 정화 자체가 불가능.
    #  · kLa 단독 = 발효공학 표준 기호. 프로젝트를 식별하는 건 kLa 라는 이름이 아니라
    #    그것을 교반속도의 멱함수로 두는 *그 상관식*이다.
    #  · Eq. S5 단독 = SI 상호참조 표기법. 표기 규칙 설명에 반드시 나온다.
    '"D-Gal": "#009E73",   # RESERVED for D-galactose only',
    "check_abbrev_consistency([\"D-Gal\", \"D-Glc\", \"Formate\"])",
    "A fit just produced parameters (kcat, Km, alpha, kLa, ...) or a curve",
    "callouts (Fig. S7, Table S3, SI Note S1, Eq. S6), and generic named parts",
    '"(SI Eq. S2-S8)" when a concrete anchor exists',
]

_fail = 0
_pass = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global _fail, _pass
    if cond:
        _pass += 1
    else:
        _fail += 1
        print(f"  FAIL  {name}" + (f"  — {detail}" if detail else ""))


def main() -> int:
    print("연구마커 스캐너 양방향 검증")
    print("=" * 60)

    print(f"\n[MUST FLAG] 실제 유출 {len(MUST_FLAG)}건 — 전부 차단되어야 함")
    for text, label in MUST_FLAG:
        hits = scan_research_markers(text)
        check(f"차단: {label}", bool(hits),
              f"통과시킴 → {text[:60]!r}")

    print(f"\n[MUST NOT FLAG] 정상 콘텐츠 {len(MUST_NOT_FLAG)}건 — 전부 통과되어야 함")
    for text in MUST_NOT_FLAG:
        hits = scan_research_markers(text)
        check(f"허용: {text[:45]}", not hits,
              f"오탐 {hits} → {text[:60]!r}")

    print("=" * 60)
    print(f"통과 {_pass} / 실패 {_fail}")
    if _fail:
        print("\n스캐너가 계약을 만족하지 않는다. 케이스를 지우지 말고 스캐너를 고칠 것.")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
