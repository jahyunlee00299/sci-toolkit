#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
피드백 정화 게이트 양방향 회귀 테스트.

배경 (실측)
-----------
`scripts/feedback_log.py` 는 학생이 남긴 불편을 GitHub Issue 로 올린다. 이슈
본문에는 `what` / `expected` / `actual` / `note` 가 **원문 그대로** 들어간다
(feedback_log.to_issue). 즉 학생이 에러 메시지를 붙여넣으면 그 안에 있던
것이 전부 따라 올라간다.

MUST_FLAG 의 케이스는 **추측한 위험이 아니라 이 워크스페이스에서 실제로
일어난 유출**이다. 각 항목에 출처를 적어둔다 — 케이스를 지우거나 약화시키면
그 순간 같은 유출이 다시 통과한다.

  · 260628  OPENROUTER_API_KEY 가 stdout → JSONL 로그 2파일에 15회 평문 노출.
            (get_keys.py 가 존재여부 bool 이 아니라 값을 echo 했다)
  · 260706  claude-scientific-skills 의 research-lookup/sources/ 에 미공개
            tagatose E-factor 조사와 멘티 실명이 tracked 상태로 push 됨.
            같은 건에서 미공개 MPSP 수치($137.42/$84.09/88.3%)도 함께 발견.
  · 260807  배포판 v1.2.0 이 "RoGDH 를 제거했다"고 문서에 적어두고도 실제로는
            *Ro*GDH·*Rs*GDH·*Lp*NoxV 와 cascade ODE 전문을 담은 채 나갔다.
            doctor.py 의 SENTINEL 스캔이 그 유형을 애초에 안 봤기 때문이다.

MUST_NOT_FLAG 는 반대 방향이다. 과차단은 스캐너를 끄게 만들고, 꺼진 스캐너는
없는 것과 같다. 특히 **불편 신고 그 자체**(툴킷 사용 중 겪은 에러 메시지,
스킬 이름, 일반 기술용어)는 반드시 통과해야 한다 — 그걸 막으면 이 기능의
존재 이유가 사라진다. 260807 실측에서 `kdeg,NADH` 를 막았더니 방금 쓴 정화본
자신이 걸린 전례가 있다.
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

_spec = importlib.util.spec_from_file_location(
    "feedback_sanitize", ROOT / "scripts" / "feedback_sanitize.py")
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules["feedback_sanitize"] = _mod
_spec.loader.exec_module(_mod)

scan = _mod.scan_text
scan_entry = _mod.scan_entry


# ── 실제로 일어난 유출 — 전부 차단되어야 한다 ────────────────────────────
# (설명, 텍스트) — 설명은 실패 출력에 그대로 찍힌다.
MUST_FLAG = [
    # ── 260628 API 키 평문 노출 계열 ────────────────────────────────────
    ("OpenRouter 키 (실제 유출된 prefix 형태)",
     "스크립트가 sk-or-v1-4f3a9c2b8e7d16054a2b9c8d7e6f5041 로 죽어요"),
    ("GitHub PAT",
     "ghp_A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8 를 넣으니 401 이 납니다"),
    ("api_key 대입문",
     'config 에 api_key = "9f3ab21c77de40b8a1c2" 넣었는데 안 먹어요'),

    # ── 260706 미공개 수치 계열 (MPSP·수율) ─────────────────────────────
    ("미공개 MPSP 달러 수치",
     "MPSP 가 $137.42 으로 나오는데 이 계산이 맞는지 모르겠어요"),
    ("미공개 수율 퍼센트",
     "전환율 88.3% 데이터를 넣으면 피팅이 발산합니다"),
    ("역가 g/L",
     "titer 12.4 g/L 인 run 에서만 실패해요"),
    # 🔴 260807 적대검사에서 실제로 뚫린 형태. E-factor·수율비는 단위도
    # $·% 도 없는 맨 소수라, 금액/백분율만 보던 초안이 통과시켰다.
    # 260706 에 유출된 값 중 하나가 정확히 이 모양이다.
    ("문맥어 + 맨 소수 (E-factor)",
     "E-factor 가 0.71 으로 나옵니다"),
    # 🔴 맨 **정수**도 잡아야 한다. "정수는 오탐이 폭발한다"고 판단해 초안이
    # 제외했으나, 실측(케이스 24건)에서 그 선택은 유출 4/7 을 통과시켰다.
    # 값과 수량을 가르는 것은 자릿수가 아니라 뒤따르는 말이다 — 아래 넷은
    # 값이고, MUST_NOT_FLAG 의 "3번째 줄"·"2개"·"5분"은 수량이다.
    ("문맥어 + 맨 정수 (수율)", "수율이 92 였습니다"),
    ("문맥어 + 맨 정수 (전환율)", "전환율 88 로 나옵니다"),
    ("문맥어 + 맨 정수 (MPSP)", "MPSP 는 97 입니다"),
    ("문맥어 + 맨 정수 (역가)", "역가 15 정도 나왔어요"),
    # 🔴 `달`(개월)이 `달러`의 앞부분에 매치돼 통째로 통과했던 미탐.
    # 짧은 한글 단위어를 접두 매치로 두면 그 글자로 시작하는 모든 단어가
    # 면제된다 — 단위어 뒤에는 반드시 경계가 필요하다.
    ("단위어 접두 매치 미탐 (달러)", "MPSP 120 달러"),
    ("mM 농도",
     "기질 250 mM 조건에서 ODE 가 안 풀립니다"),
    ("비활성 U/mg",
     "비활성 3.7 U/mg 로 계산하면 값이 이상해요"),

    # ── 260706 멘티 실명 계열 ───────────────────────────────────────────
    # 이름은 **가명**이다. 실제 유출된 것은 멘티 2명의 실명이지만, 그것을
    # 테스트에 옮겨 적으면 이 파일이 같은 유출이 된다. 이 파일은 SENTINEL
    # 면제 대상이라 스캔도 지나가므로 더더욱 실명을 두면 안 된다.
    # 검사하려는 계약은 "한글 이름 + 호칭 + 조사"라는 형태이지 특정인이 아니다.
    ("한글 실명 + 호칭 (뒤에 조사)",
     "홍길동 학생이 준 파일에서 에러가 납니다"),
    ("한글 실명 + 선생님",
     "임꺽정 선생님 데이터로 돌리면 죽어요"),
    ("이메일 주소",
     "hong@korea.ac.kr 로 메일이 안 가요"),
    ("휴대폰 번호",
     "010-1234-5678 로 알림이 안 옵니다"),

    # ── 260807 미공개 효소·속도식 계열 (doctor.py 스캐너 재사용) ────────
    ("효소 약어 RsGDH",
     "*Rs*GDH 활성 계산이 자꾸 틀립니다"),
    ("효소 약어 LpNoxV",
     "LpNoxV 파라미터를 넣으면 수렴이 안 돼요"),
    ("속도식 vXR",
     "d[D-Gal]/dt = -vXR 부분에서 부호가 반대인 것 같아요"),
    ("kLa 상관식",
     "kLa = α · N^β 식을 어디에 넣어야 하나요"),
    ("미공개 기질명 tagatose",
     "tagatose 수율 계산 스크립트가 죽습니다"),
    ("사설 저장소명",
     "UDH_Clustering 레포에서 import 가 안 됩니다"),

    # ── 절대경로 + 사용자명 ─────────────────────────────────────────────
    ("Windows 절대경로 + 사용자명",
     r"C:\Users\researcher01\OneDrive\연구\data.xlsx 를 못 읽어요"),
    # 사용자명은 **가상의 것**을 쓴다. 검사하려는 계약은 "홈 경로 + 임의의
    # 사용자명"이라는 형태이지 특정 계정이 아니고, 배포판에 실제 사용자명을
    # 남길 이유가 없다.
    ("POSIX 홈 경로 + 사용자명",
     "/home/researcher01/secret_project/run.py 에서 실패합니다"),

    # ── 복합 (여러 축이 한 문장에) ──────────────────────────────────────
    ("복합: 수치 + 효소명",
     "RsGDH 로 12.4 g/L 나온 데이터에서 실패"),
]


# ── 정상적인 불편 신고 — 전부 통과되어야 한다 ────────────────────────────
# 이걸 막으면 학생이 신고 자체를 포기한다. 문서(11번)가 권장하는 바로 그
# 표현 형태들이 여기 들어있다.
MUST_NOT_FLAG = [
    # 문서 §"남기면 안 되는 것" 이 가르치는 올바른 형태
    "HPLC csv 파일에서 실패합니다",
    "엑셀 파일을 읽을 때 인코딩 오류가 납니다",
    # 툴킷 자체에 대한 불편 — 이 기능의 본래 목적
    "docx 표 안에서 find-replace 가 계속 실패합니다",
    "51 matches 라는 메시지만 반복되고 안 끝나요",
    "표 셀 값이 바뀌길 기대했는데 아무 일도 안 일어납니다",
    "primer-design 스킬이 뭘 요구하는지 모르겠어요",
    "설치할 때 install.py 가 권한 오류로 죽습니다",
    "doctor.py 를 돌리면 FAIL 이 뜨는데 뭘 고쳐야 할지 모르겠어요",
    "pdf 스킬로 표를 뽑으면 열이 밀립니다",
    # 일반 생화학·동역학 표기 (교육 콘텐츠 — 프로젝트 고유가 아니다)
    "kcat/Km 계산이 맞는지 확인하고 싶어요",
    "NADH 와 NADPH 표기가 자꾸 바뀝니다",
    "Michaelis-Menten 피팅이 수렴하지 않습니다",
    "Vmax 와 Km 을 어떻게 넣어야 하나요",
    # 역할 호칭 — 사람 이름이 아니다 (doctor.py ALLOWLIST 계열)
    "지도교수에게 보여드릴 표를 만들고 싶습니다",
    "담당교수님께 제출할 보고서 양식이 필요해요",
    # 버전·개수·시간은 수치지만 연구값이 아니다
    "Python 3.11 에서 실행하면 오류가 납니다",
    "파일 3개를 한꺼번에 처리하면 느려집니다",
    "10분 정도 걸리는데 정상인가요",
    "1000줄짜리 csv 를 넣으면 멈춥니다",
    "메모리 8GB 인 노트북에서 죽습니다",
    # 🔴 여기부터가 맨 정수 탐지의 오탐 방어선이다. 연구 문맥어(수율·MPSP·
    # titer…)가 문장에 있으면서 숫자는 수량·순서·시간인 경우 — 실제 불편
    # 신고에서 가장 흔한 형태다. 260807 실측: 수량어 제외 없이 정수를 잡으면
    # 이 유형 13/13 이 전부 차단됐다(= 신고 기능 사망).
    # COUNTER_WORD_RE 를 줄이면 여기서 먼저 깨진다.
    "수율 계산 스크립트가 3번째 줄에서 죽어요",
    "수율 컬럼이 2개로 중복돼 있습니다",
    "MPSP 계산에 5분 넘게 걸립니다",
    "전환율 그래프에서 x축 라벨 10개가 겹칩니다",
    "순도 관련 함수가 Python 3.11 에서 오류가 납니다",
    "titer 파일 4개를 한꺼번에 열면 멈춥니다",
    "yield 시트가 2번 탭에 있는데 못 읽어요",
    "E-factor 문서 12쪽 표가 깨집니다",
    "생산성 리포트가 500 에러를 냅니다",
    "비용 항목이 2026 년치만 안 나옵니다",
    "단가 열이 1번째가 아니라 3번째입니다",
    "순도 검사 로그가 1000줄 넘어가면 느려요",
    # 🔴 아래 넷은 정수 탐지 도입 후 적대검사에서 실제로 터진 오탐이다.
    # 단위어 뒤 **조사·종결어미**를 허용하지 않으면 전부 다시 막힌다
    # (`2개로`·`3행에서`·`7개가`·`3번째입니다`).
    "MPSP 표가 2열로 나옵니다",
    "수율 데이터가 3행에서 잘립니다",
    "E-factor 항목 7개가 비어 있습니다",
    "전환율 시트 5장을 합치면 느려요",
    # 식별자(`#42`)와 경계값 0 은 측정값이 아니다.
    "수율 관련 이슈 #42 참고해주세요",
    "생산성 그래프 축이 0 부터 시작 안 해요",
    # 상대경로·파일명은 재현에 필요하고 사용자명을 노출하지 않는다
    "scripts/feedback_log.py 를 실행하면 됩니다",
    "out/feedback.jsonl 이 안 생깁니다",
    "data.xlsx 를 읽을 때만 실패해요",
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


def test_entry_level() -> None:
    """항목 단위 스캔은 어느 필드에 있든 잡아야 한다.

    to_issue() 는 what 뿐 아니라 expected/actual/note 도 본문에 넣는다.
    what 만 검사하면 나머지 세 필드가 통째로 무방비가 된다 — 실제로
    학생은 에러 원문을 actual 에 붙여넣을 가능성이 가장 높다.
    """
    print("\n[FIELD] what 이외의 필드도 검사되어야 함")
    for field in ("what", "expected", "actual", "note"):
        entry = {"what": "표 편집이 실패합니다"}
        entry[field] = "MPSP $137.42 에서 실패"
        hits = scan_entry(entry)
        check(f"필드 {field} 검사됨", bool(hits),
              f"{field} 에 넣은 미공개 수치를 놓침")

    # env 는 자동수집 필드(OS/Python 버전)라 검사 대상이 아니다. 여기에
    # 버전 문자열이 들어있는데 수치 탐지가 걸리면 모든 기록이 차단된다.
    entry = {"what": "표 편집이 실패합니다",
             "env": {"os": "Windows 10", "python": "3.11.5"}}
    check("env 는 오탐 안 남", not scan_entry(entry),
          f"env 자동수집 필드에서 오탐: {scan_entry(entry)}")


def main() -> int:
    print("피드백 정화 게이트 양방향 검증")
    print("=" * 62)

    print(f"\n[MUST FLAG] 실제 유출 유형 {len(MUST_FLAG)}건 — 전부 차단되어야 함")
    for label, text in MUST_FLAG:
        hits = scan(text)
        check(f"차단: {label}", bool(hits), f"통과시킴 → {text[:52]!r}")

    print(f"\n[MUST NOT FLAG] 정상 신고 {len(MUST_NOT_FLAG)}건 — 전부 통과되어야 함")
    for text in MUST_NOT_FLAG:
        hits = scan(text)
        check(f"허용: {text[:42]}", not hits, f"오탐 {hits}")

    test_entry_level()

    print("=" * 62)
    print(f"통과 {_pass} / 실패 {_fail}")
    if _fail:
        print("\n게이트가 계약을 만족하지 않는다. 케이스를 지우지 말고 게이트를 고칠 것.")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
