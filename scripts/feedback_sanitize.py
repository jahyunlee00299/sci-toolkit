#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
피드백 정화 게이트 — 남긴 기록이 밖으로 나가기 전에 막는다.

왜 필요한가
-----------
`feedback_log.py` 의 `to_issue()` 는 `what` / `expected` / `actual` / `note`
를 **원문 그대로** 이슈 본문에 넣는다. 학생이 에러 메시지를 통째로 붙여넣는
것은 정상적인 신고 방식이고, 바로 그때 파일 경로·미공개 수치·효소명·API 키가
따라 올라간다.

문서(`docs/11_불편한점_남기기.md`)에는 "남기면 안 되는 것" 이 적혀 있었지만
그건 **사람에게 주는 안내문일 뿐 코드가 아니었다.** 이 워크스페이스는 같은
실수를 이미 세 번 했다 — 안내문·표·주석에 "제거했다"고 적어두고 실제로는
담은 채 배포한 것이(260807), 값을 echo 하지 말라고 적어두고 echo 한 것이
(260628), sources/ 를 두지 말라고 적어두고 push 한 것이(260706). 그래서 이
모듈은 문장이 아니라 실행되는 검사다.

설계 원칙
---------
**차단만 하고 고치지 않는다.** 자동 마스킹은 재현에 필요한 정보까지 지우고,
무엇이 지워졌는지 본인도 모른 채 넘어간다. 사람이 직접 고치거나 명시적으로
승인하게 한다.

**과차단은 스캐너를 죽인다.** 걸러야 할 것은 "무슨 데이터로 실패했는가"이지
"무엇이 실패했는가"가 아니다. 버전번호·파일개수·소요시간·상대경로·일반
생화학 표기(kcat, Km, NADH)는 반드시 통과해야 한다. 260807 실측에서
`kdeg,NADH` 를 막았더니 방금 쓴 정화본 자신이 걸린 전례가 있다.

**검증된 패턴은 재사용한다.** 효소약어·속도식·미공개기질·사설저장소명은
`doctor.py` 의 `scan_research_markers()` 가 이미 양방향 테스트
(`tests/test_research_marker_scan.py`)로 보정해 둔 자산이다. 여기서 다시
쓰지 않는다 — 두 벌이 되면 갈라진다.
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
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 이슈 본문에 실리는 필드. env 는 자동수집(OS/Python 버전)이라 제외한다 —
# 거기엔 사람이 쓴 내용이 없고, 버전 문자열이 수치 탐지에 걸리면 모든
# 기록이 차단된다.
SCANNED_FIELDS = ("what", "expected", "actual", "note")


# ── doctor.py 의 검증된 연구마커 스캐너 재사용 ──────────────────────────
def _load_research_scanner():
    """doctor.py 의 scan_research_markers 를 가져온다.

    없으면 None 을 돌려주고, 호출부는 나머지 축만으로 계속 진행한다.
    스캐너 하나가 빠졌다고 게이트 전체가 죽으면 그게 더 위험하다.
    """
    doctor_path = ROOT / "doctor.py"
    if not doctor_path.exists():
        return None
    try:
        spec = importlib.util.spec_from_file_location("doctor", doctor_path)
        mod = importlib.util.module_from_spec(spec)
        # doctor.py 는 @dataclass 를 쓴다. dataclasses 가 sys.modules 에서
        # __module__ 을 되찾으므로 exec 전에 등록해야 한다.
        sys.modules.setdefault("doctor", mod)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod.scan_research_markers
    except Exception:
        return None


_scan_research = _load_research_scanner()


# ── 축 1: 자격증명 ───────────────────────────────────────────────────────
# 260628 실측 — OPENROUTER_API_KEY(`sk-or-...`)가 stdout 으로 새어 JSONL
# 로그 2파일에 15회 남았다. prefix 가 분명한 것들은 오탐이 사실상 없다.
CREDENTIAL_PATTERNS = [
    ("API 키/토큰",
     re.compile(r"\b(?:sk-[A-Za-z0-9\-]{16,}"
                r"|ghp_[A-Za-z0-9]{20,}|gho_[A-Za-z0-9]{20,}"
                r"|github_pat_[A-Za-z0-9_]{20,}"
                r"|xox[baprs]-[A-Za-z0-9\-]{10,}"
                r"|AKIA[0-9A-Z]{16}"
                r"|AIzaSy[A-Za-z0-9_\-]{20,})")),
    ("자격증명 대입문",
     re.compile(r"(?:api[_-]?key|apikey|secret[_-]?key|access[_-]?token"
                r"|auth[_-]?token|client[_-]?secret|password|passwd)"
                r"\s*[:=]\s*[\"']?[A-Za-z0-9_\-.]{12,}[\"']?",
                re.IGNORECASE)),
    ("Tailscale IP",
     re.compile(r"\b100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}\b")),
]

# 대입문 축에서 명백한 자리표시자는 통과시킨다. 문서와 예제가 걸리면
# "설정이 안 돼요" 라는 가장 흔한 신고를 아무도 못 남긴다.
#
# 🔴 반드시 **값 쪽**에만 적용할 것. 대입문 전체를 검사하면 `api_key` 라는
# 키 이름의 `_key` 가 `_KEY\b` 에 걸려, 값이 진짜 키여도 자리표시자로
# 오판한다 — 260807 이 테스트에서 실측된 구멍이다. doctor.py 가
# `_split_value()` 를 따로 둔 것도 같은 이유다.
_CREDENTIAL_PLACEHOLDER = re.compile(
    r"your|example|placeholder|changeme|dummy|fake|sample|여기|입력|발급"
    r"|xxx+|\.\.\.|<|os\.environ|getenv"
    r"|^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+$",   # 값이 ENV 변수명 그 자체인 경우
    re.IGNORECASE,
)


def _assignment_value(matched: str) -> str:
    """대입문 매치에서 값 부분만 떼어낸다 (`api_key = "abc"` → `abc`)."""
    _, sep, value = matched.partition("=")
    if not sep:
        _, sep, value = matched.partition(":")
    return value.strip().strip("\"'") if sep else matched


# ── 축 2: 미공개 연구 수치 ───────────────────────────────────────────────
# 260706 실측 — 미공개 MPSP($112.76/$98.58)와 수율(91.9%)이 스킬 파일에
# 남아 push 됐다. 판별 기준은 "숫자"가 아니라 **연구 단위가 붙은 숫자**다.
# 버전번호(3.11)·개수(3개)·시간(10분)·메모리(8GB)는 반드시 통과해야 한다.
RESEARCH_UNIT_RE = re.compile(
    r"""(?<![A-Za-z0-9])
    \d+(?:\.\d+)?\s*
    (?:
        g/L|mg/mL|g/l|mg/ml|µg/mL|ug/mL          # 농도(질량)
      | mM|μM|uM|nM|M\b                          # 농도(몰)
      | U/mg|U/mL|U/ml|IU/mg                     # 비활성
      | mol%|wt%|w/w%|v/v%                       # 조성
      | h⁻¹|s⁻¹|min⁻¹|/h\b|/s\b                  # 속도상수
      | kcal/mol|kJ/mol                          # 에너지
      | °C(?=\s*(?:에서|조건|반응|배양))          # 온도는 조건 서술일 때만
    )
    """,
    re.VERBOSE,
)

# 금액·백분율·맨소수는 그 자체로는 흔하다. 미공개 연구값으로 보는 것은 연구
# 문맥어가 함께 있을 때뿐이다 — 이 조합이 260706 에 실제로 유출된 형태다.
#
# 🔴 맨 소수(단위·기호 없는 `0.83`)를 포함해야 한다. 260706 에 유출된
# E-factor 가 정확히 그 형태였고, `$`/`%` 만 보던 초안은 적대검사에서
# `E-factor 가 0.83` 을 통과시켰다. 정수를 제외하는 것은 의도적이다 —
# 개수·에러코드·연도와 겹쳐 오탐이 폭발한다.
MONEY_PCT_RE = re.compile(
    r"(?:\$\s*\d+(?:\.\d+)?"          # 금액
    r"|\d+(?:\.\d+)?\s*%"             # 백분율
    r"|(?<![\d.])\d+\.\d+(?![\d.]))"  # 맨 소수 (버전번호 3.11.5 는 제외됨)
)
RESEARCH_CONTEXT_RE = re.compile(
    r"MPSP|수율|전환율|역가|titer|yield|conversion|selectivity|선택도"
    r"|E-factor|순도|purity|생산성|productivity|비용|단가",
    re.IGNORECASE,
)


# ── 축 3: 사람 식별 정보 ─────────────────────────────────────────────────
# 260706 실측 — 멘티 2명의 실명이 스킬 코드 주석과 SKILL.md 에 남은 채
# 원격에 push 됐다(이름 자체는 여기 옮겨 적지 않는다 — 그러면 이 파일이
# 같은 유출이 된다). 한글 이름은 일반명사와 섞이므로 **호칭이 붙은 경우로
# 한정**한다. 넓히면 "학생 여러분" 같은 표현까지 걸려 신고를 막는다.
PERSON_PATTERNS = [
    ("이메일", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    ("전화번호", re.compile(r"\b01[0-9][-\s]?\d{3,4}[-\s]?\d{4}\b")),
    # 🔴 호칭 뒤에 조사가 붙는 것이 한국어의 정상 형태다("○○○ 학생이 준").
    # negative lookahead 를 걸면 조사에 막혀 매치가 통째로 실패한다 —
    # 260807 실측: `○○○ 선생님 데이터`(뒤가 공백)는 잡히고
    # `○○○ 학생이`(뒤가 조사)는 통과해버렸다. 대신 호칭 뒤에 올 수 있는
    # 조사를 명시적으로 허용한다.
    ("실명+호칭",
     re.compile(r"[가-힣]{2,4}\s*(?:교수|박사|선생님|학생|연구원|조교|님)"
                r"(?:님)?(?:이|가|은|는|을|를|과|와|의|께|에게|한테)?(?![가-힣])")),
]

# 호칭으로 끝나지만 사람을 가리키지 않는 역할어. doctor.py 의
# PERSONAL_NAME_ALLOWLIST 와 같은 취지 — 여기선 피드백 문맥에 맞춰 넓힌다.
_PARTICLE_RE = re.compile(r"(?:이|가|은|는|을|를|과|와|의|께|에게|한테)$")


def _strip_particle(text: str) -> str:
    """공백·조사·존칭 `님` 을 떼어 역할어와 대조할 형태로 만든다.

    `담당교수님께` → `담당교수`. 역할어에 `님` 이 붙는 것은 정상 존대이지
    사람 이름이 아니다. 이걸 안 떼면 "담당교수님께 제출할" 같은 흔한
    문장이 실명으로 오탐된다(260807 실측).
    """
    stripped = _PARTICLE_RE.sub("", text.replace(" ", ""))
    # `님` 하나만 남는 경우(=호칭 자체)는 떼지 않는다.
    if stripped.endswith("님") and len(stripped) > 1:
        stripped = stripped[:-1]
    return stripped


PERSON_ALLOWLIST = frozenset({
    "지도교수", "담당교수", "책임교수", "주임교수", "겸임교수", "객원교수",
    "부교수", "정교수", "조교수", "석좌교수", "명예교수", "교수",
    "지도박사", "담당박사", "박사", "선생님", "담당선생님", "학과선생님",
    "학생", "연구원", "조교", "님", "대학원생", "학부생", "참여연구원",
})


# ── 축 4: 절대경로 + 사용자명 ────────────────────────────────────────────
# 경로 자체는 재현에 유용하지만, 절대경로는 사용자명과 연구 폴더명을
# 드러낸다. 상대경로(scripts/foo.py)와 파일명(data.xlsx)은 통과시킨다.
PATH_PATTERNS = [
    ("Windows 절대경로", re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s\"']+", re.IGNORECASE)),
    ("POSIX 홈 경로", re.compile(r"/(?:home|Users)/[^/\s\"']+")),
    ("OneDrive 경로", re.compile(r"OneDrive[^\s\"']*[\\/][^\s\"']+")),
]


def _iter_hits(text: str) -> list[str]:
    """단일 문자열에서 발견된 위험 항목 목록. 빈 목록 = 깨끗함."""
    found: list[str] = []

    def add(label: str, matched: str) -> None:
        entry = f"{label}: {matched.strip()}"
        if entry not in found:
            found.append(entry)

    # 축 1 — 자격증명
    for label, rx in CREDENTIAL_PATTERNS:
        for m in rx.finditer(text):
            hit = m.group(0)
            if label == "자격증명 대입문" and _CREDENTIAL_PLACEHOLDER.search(
                    _assignment_value(hit)):
                continue
            add(label, hit)

    # 축 2 — 연구 단위가 붙은 수치
    for m in RESEARCH_UNIT_RE.finditer(text):
        add("연구 수치", m.group(0))
    # 금액·백분율은 연구 문맥어와 같이 있을 때만
    if RESEARCH_CONTEXT_RE.search(text):
        for m in MONEY_PCT_RE.finditer(text):
            add("연구 수치", m.group(0))

    # 축 3 — 사람 식별 정보
    for label, rx in PERSON_PATTERNS:
        for m in rx.finditer(text):
            hit = m.group(0)
            # 조사를 허용해 매치했으므로, 역할어 대조 전에 조사를 떼야 한다.
            # 떼지 않으면 `지도교수에게` 가 목록에 없어 오탐이 된다.
            if label == "실명+호칭" and _strip_particle(hit) in PERSON_ALLOWLIST:
                continue
            add(label, hit)

    # 축 4 — 절대경로
    for label, rx in PATH_PATTERNS:
        for m in rx.finditer(text):
            add(label, m.group(0))

    # 축 5 — 미공개 연구마커 (doctor.py 재사용)
    if _scan_research is not None:
        for hit in _scan_research(text):
            if hit not in found:
                found.append(hit)

    return found


def scan_text(text: str | None) -> list[str]:
    """문자열 하나를 검사한다. 빈 목록이면 통과."""
    if not text:
        return []
    return _iter_hits(text)


def scan_entry(entry: dict) -> list[str]:
    """기록 하나를 검사한다 — 이슈 본문에 실리는 모든 필드를 본다.

    `what` 만 보면 나머지 세 필드가 무방비가 된다. 학생이 에러 원문을
    붙여넣을 가능성이 가장 높은 곳이 `actual` 이다.
    """
    found: list[str] = []
    for field in SCANNED_FIELDS:
        for hit in scan_text(entry.get(field)):
            tagged = f"[{field}] {hit}"
            if tagged not in found:
                found.append(tagged)
    return found


def format_report(hits: list[str], *, prefix: str = "  ") -> str:
    """차단 사유를 사람이 읽을 수 있게 정리한다."""
    return "\n".join(f"{prefix}· {h}" for h in hits)


if __name__ == "__main__":
    # 표준입력이나 인자로 받은 텍스트를 검사한다. 스크립트를 직접 돌려
    # "이 문장이 걸리나?" 를 확인할 수 있어야 한다.
    text = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else sys.stdin.read()
    hits = scan_text(text)
    if hits:
        print("의심 항목:")
        print(format_report(hits))
        sys.exit(2)
    print("깨끗합니다.")
    sys.exit(0)
