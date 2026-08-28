#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bidirectional regression test for the feedback-sanitization gate.

Background (measured)
----------------------
`scripts/feedback_log.py` posts a student's reported inconvenience as a
GitHub Issue. The issue body carries `what` / `expected` / `actual` / `note`
**verbatim** (feedback_log.to_issue). So if a student pastes an error
message, everything inside it goes up along with it.

The MUST_FLAG cases are **not hypothetical risk — they are leaks that
actually happened in this workspace**. Each entry records its source;
deleting or weakening a case lets the same leak through again from that
moment on.

  · 260628  OPENROUTER_API_KEY leaked in plaintext 15 times across 2 log
            files, stdout -> JSONL (get_keys.py echoed the value instead of
            a bool for whether it existed).
  · 260706  Undisclosed tagatose E-factor research and mentees' real names
            were pushed tracked under research-lookup/sources/ in
            claude-scientific-skills. The same incident also surfaced
            undisclosed MPSP figures ($137.42/$84.09/88.3%).
  · 260807  Distribution v1.2.0's docs claimed "RoGDH was removed," yet it
            shipped with *Ro*GDH, *Rs*GDH, *Lp*NoxV, and the full cascade
            ODE intact, because doctor.py's SENTINEL scan never looked for
            that category in the first place.

MUST_NOT_FLAG runs the opposite direction. Over-blocking gets the scanner
turned off, and a scanner that's off is the same as no scanner. In
particular, **the inconvenience report itself** (an error message hit while
using the toolkit, a skill name, ordinary technical terms) must always pass
— block that, and this feature's whole reason for existing disappears.
Measured 260807: blocking `kdeg,NADH` had the precedent of catching the very
sanitized text that had just been written to report it.
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


# ── Leaks that actually happened — all of these must be blocked ─────────
# (description, text) — the description is printed as-is on failure.
# NOTE: the text values are the actual test input exercising Korean-language
# PII/leak detection patterns in scripts/feedback_sanitize.py — they stay in
# Korean on purpose (load-bearing test fixtures). Only the description
# labels and comments are prose and get translated.
MUST_FLAG = [
    # ── 260628 API key plaintext exposure family ────────────────────────
    ("OpenRouter key (shape of the actually-leaked prefix)",
     "스크립트가 sk-or-v1-4f3a9c2b8e7d16054a2b9c8d7e6f5041 로 죽어요"),
    ("GitHub PAT",
     "ghp_A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8 를 넣으니 401 이 납니다"),
    ("api_key assignment statement",
     'config 에 api_key = "9f3ab21c77de40b8a1c2" 넣었는데 안 먹어요'),

    # ── 260706 undisclosed-figure family (MPSP, yield) ──────────────────
    ("undisclosed MPSP dollar figure",
     "MPSP 가 $137.42 으로 나오는데 이 계산이 맞는지 모르겠어요"),
    ("undisclosed yield percentage",
     "전환율 88.3% 데이터를 넣으면 피팅이 발산합니다"),
    ("titer g/L",
     "titer 12.4 g/L 인 run 에서만 실패해요"),
    # 🔴 The shape that actually got through the 260807 adversarial check.
    # An E-factor/yield-ratio value is a bare decimal with no unit and no
    # $/% sign, so a draft that only watched for currency/percentages let it
    # through. One of the values leaked on 260706 has exactly this shape.
    ("context word + bare decimal (E-factor)",
     "E-factor 가 0.71 으로 나옵니다"),
    # 🔴 A bare **integer** must be caught too. An earlier draft excluded
    # integers on the judgment that "integers explode with false positives,"
    # but measured (24 cases) that choice let 4/7 leaks through. What
    # separates a value from a quantity isn't digit count — it's the word
    # that follows. The four below are values; MUST_NOT_FLAG's "3rd line,"
    # "2 items," "5 minutes" are quantities.
    ("context word + bare integer (yield)", "수율이 92 였습니다"),
    ("context word + bare integer (conversion)", "전환율 88 로 나옵니다"),
    ("context word + bare integer (MPSP)", "MPSP 는 97 입니다"),
    ("context word + bare integer (titer)", "역가 15 정도 나왔어요"),
    # 🔴 A miss where `달` (month) matched the front of `달러` (dollar) and
    # let the whole thing through. Making a short Korean unit-word a prefix
    # match exempts every word that starts with that character — a unit word
    # needs a boundary right after it.
    ("unit-word prefix-match miss (dollar)", "MPSP 120 달러"),
    ("mM concentration",
     "기질 250 mM 조건에서 ODE 가 안 풀립니다"),
    ("specific activity U/mg",
     "비활성 3.7 U/mg 로 계산하면 값이 이상해요"),

    # ── 260706 mentee real-name family ───────────────────────────────────
    # The names here are **pseudonyms**. What actually leaked was two
    # mentees' real names, but transcribing those into a test would make
    # this file the same leak. This file is also exempt from the SENTINEL
    # scan, so a real name here would slip through entirely — all the more
    # reason not to put one here. The contract under test is the shape
    # "Korean name + title + particle," not any specific person.
    ("Korean real name + title (with a trailing particle)",
     "홍길동 학생이 준 파일에서 에러가 납니다"),
    ("Korean real name + '선생님' (teacher)",
     "임꺽정 선생님 데이터로 돌리면 죽어요"),
    ("email address",
     "hong@korea.ac.kr 로 메일이 안 가요"),
    ("phone number",
     "010-1234-5678 로 알림이 안 옵니다"),

    # ── 260807 undisclosed enzyme/rate-equation family (reusing doctor.py's scanner) ──
    ("enzyme abbreviation RsGDH",
     "*Rs*GDH 활성 계산이 자꾸 틀립니다"),
    ("enzyme abbreviation LpNoxV",
     "LpNoxV 파라미터를 넣으면 수렴이 안 돼요"),
    ("rate equation vXR",
     "d[D-Gal]/dt = -vXR 부분에서 부호가 반대인 것 같아요"),
    ("kLa correlation",
     "kLa = α · N^β 식을 어디에 넣어야 하나요"),
    ("undisclosed substrate name tagatose",
     "tagatose 수율 계산 스크립트가 죽습니다"),
    ("private repository name",
     "UDH_Clustering 레포에서 import 가 안 됩니다"),

    # ── absolute path + username ─────────────────────────────────────────
    ("Windows absolute path + username",
     r"C:\Users\researcher01\OneDrive\연구\data.xlsx 를 못 읽어요"),
    # The username used here is **fictional**. The contract under test is
    # the shape "home path + arbitrary username," not a specific account,
    # and there's no reason to leave a real username in a distributed file.
    ("POSIX home path + username",
     "/home/researcher01/secret_project/run.py 에서 실패합니다"),

    # ── combined (multiple axes in one sentence) ─────────────────────────
    ("combined: number + enzyme name",
     "RsGDH 로 12.4 g/L 나온 데이터에서 실패"),
]


# ── Normal inconvenience reports — all of these must pass through ────────
# Block these and a student just gives up on reporting at all. The exact
# phrasing forms the docs (§11) recommend are represented here.
# NOTE: these strings are the actual test input exercising Korean-language
# detection logic — they stay in Korean on purpose (load-bearing test
# fixtures). Only the comments around them are prose and get translated.
MUST_NOT_FLAG = [
    # the correct shape taught by the docs' §"what not to leave in a report"
    "HPLC csv 파일에서 실패합니다",
    "엑셀 파일을 읽을 때 인코딩 오류가 납니다",
    # a complaint about the toolkit itself — this feature's actual purpose
    "docx 표 안에서 find-replace 가 계속 실패합니다",
    "51 matches 라는 메시지만 반복되고 안 끝나요",
    "표 셀 값이 바뀌길 기대했는데 아무 일도 안 일어납니다",
    "primer-design 스킬이 뭘 요구하는지 모르겠어요",
    "설치할 때 install.py 가 권한 오류로 죽습니다",
    "doctor.py 를 돌리면 FAIL 이 뜨는데 뭘 고쳐야 할지 모르겠어요",
    "pdf 스킬로 표를 뽑으면 열이 밀립니다",
    # ordinary biochemistry/kinetics notation (educational content — not project-specific)
    "kcat/Km 계산이 맞는지 확인하고 싶어요",
    "NADH 와 NADPH 표기가 자꾸 바뀝니다",
    "Michaelis-Menten 피팅이 수렴하지 않습니다",
    "Vmax 와 Km 을 어떻게 넣어야 하나요",
    # role titles — not a person's name (same family as doctor.py's ALLOWLIST)
    "지도교수에게 보여드릴 표를 만들고 싶습니다",
    "담당교수님께 제출할 보고서 양식이 필요해요",
    # version/count/duration are numeric but not a research value
    "Python 3.11 에서 실행하면 오류가 납니다",
    "파일 3개를 한꺼번에 처리하면 느려집니다",
    "10분 정도 걸리는데 정상인가요",
    "1000줄짜리 csv 를 넣으면 멈춥니다",
    "메모리 8GB 인 노트북에서 죽습니다",
    # 🔴 From here on is the false-positive defense line for bare-integer
    # detection. A sentence carrying a research context word (yield, MPSP,
    # titer, ...) where the number is actually a count/ordinal/duration — the
    # most common shape in real inconvenience reports. Measured 260807:
    # catching an integer with no quantity-word exclusion blocked 13/13 of
    # this type (= the report feature would be dead).
    # Trimming COUNTER_WORD_RE breaks here first.
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
    # 🔴 The four below are false positives that actually surfaced in
    # adversarial testing after integer detection was added. Without
    # allowing a **particle or a sentence-final ending** after the unit
    # word, all of them get blocked again (`2개로`, `3행에서`, `7개가`,
    # `3번째입니다`).
    "MPSP 표가 2열로 나옵니다",
    "수율 데이터가 3행에서 잘립니다",
    "E-factor 항목 7개가 비어 있습니다",
    "전환율 시트 5장을 합치면 느려요",
    # an identifier (`#42`) and the boundary value 0 are not measurements.
    "수율 관련 이슈 #42 참고해주세요",
    "생산성 그래프 축이 0 부터 시작 안 해요",
    # relative paths/filenames are needed for reproduction and don't expose a username
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
    """A per-entry scan must catch a hit regardless of which field it's in.

    to_issue() puts expected/actual/note into the issue body along with
    what. Checking only what leaves the other three fields completely
    unguarded — and in practice a student is most likely to paste the raw
    error text into actual.
    """
    print("\n[FIELD] fields other than what must also be scanned")
    for field in ("what", "expected", "actual", "note"):
        entry = {"what": "표 편집이 실패합니다"}
        entry[field] = "MPSP $137.42 에서 실패"
        hits = scan_entry(entry)
        check(f"field {field} scanned", bool(hits),
              f"missed the undisclosed figure placed in {field}")

    # env is an auto-collected field (OS/Python version), not a scan
    # target. It carries a version string, and if numeric detection catches
    # that, every single record gets blocked.
    entry = {"what": "표 편집이 실패합니다",
             "env": {"os": "Windows 10", "python": "3.11.5"}}
    check("no false positive on env", not scan_entry(entry),
          f"false positive on the env auto-collected field: {scan_entry(entry)}")


def main() -> int:
    print("Bidirectional verification of the feedback-sanitization gate")
    print("=" * 62)

    print(f"\n[MUST FLAG] {len(MUST_FLAG)} real-leak type(s) — all must be blocked")
    for label, text in MUST_FLAG:
        hits = scan(text)
        check(f"blocked: {label}", bool(hits), f"let it through -> {text[:52]!r}")

    print(f"\n[MUST NOT FLAG] {len(MUST_NOT_FLAG)} normal report(s) — all must pass")
    for text in MUST_NOT_FLAG:
        hits = scan(text)
        check(f"allowed: {text[:42]}", not hits, f"false positive {hits}")

    test_entry_level()

    print("=" * 62)
    print(f"PASS {_pass} / FAIL {_fail}")
    if _fail:
        print("\nThe gate does not satisfy the contract. Fix the gate — do not delete the case.")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
