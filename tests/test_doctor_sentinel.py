#!/usr/bin/env python3
"""doctor.py SENTINEL 검사 회귀 테스트 — must-block AND must-not-block 양방향.

실행: python tests/test_doctor_sentinel.py   (exit 0 = 통과)

느슨하게 고쳐서 통과시킨 게 아닌지 확인한다.
"""
import importlib.util, sys
from pathlib import Path

# Windows 기본 콘솔은 cp949 라서 한글/기호 출력에서 죽는다. UTF-8로 맞춘다.
# TextIOWrapper 대신 reconfigure — 래퍼는 원본 스트림을 소유해서, 이 모듈이
# import 된 뒤 GC 되면 호출자의 stdout 까지 닫아버린다. 이 파일이 래퍼를 쓰던
# 동안 `pytest tests/` 는 수집 도중 통째로 죽었다(ValueError: I/O operation on
# closed file — 실측 2026-08-08). doctor.py 는 각 테스트를 subprocess 로 돌려서
# 이 고장이 보이지 않았고, 새로 clone 한 사람이 가장 먼저 치는 명령에서만
# 드러났다. 나머지 테스트 파일은 이미 reconfigure 를 쓰고 있었다.
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

spec = importlib.util.spec_from_file_location(
    "doctor", str(Path(__file__).resolve().parent.parent / "doctor.py"))
doctor = importlib.util.module_from_spec(spec)
sys.modules["doctor"] = doctor   # dataclass needs the module registered
spec.loader.exec_module(doctor)

MUST_BLOCK = [  # 진짜 유출 — 반드시 탐지돼야 함
    ('api_key = "sk-or-v1-9f3ab21c77de40b8a1e6c5d4f0928374"', "real openrouter-style key"),
    ('API_KEY="AKIA5FJ39DKS02MXZQ7B"', "AWS-style access key"),
    ("apikey: 'a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6'", "32-char literal"),
    ('secret_key="hunter2hunter2hunter2hunter2"', "secret_key literal"),
    ('sk-abcdefghijklmnopqrstuvwxyz012345', "bare sk- token"),
    ('ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', "github PAT"),
    ('access_token = "ya29.a0ARrdaM_realish_token_value_here123"', "oauth token"),
    # --- 아래 4개는 적대 검증에서 실제로 뚫렸던 우회 입력이다 (2026-07-23).
    # 플레이스홀더 마커를 '서브스트링'으로 검사하던 시절, 진짜 키 값 안에
    # 마커 문자열이 우연히 들어가기만 하면 통과해버렸다. 절대 지우지 말 것.
    ('api_key="my-real-project1-secret-abcdefghijklmno"', "우회: 값에 'project1' 포함"),
    ('api_key="THIS-IS-KEY-HERE-BUT-ALSO-REAL-abcd1234"', "우회: 값에 'key-here' 포함"),
    ('api_key="example-a83f2c9d41b7e6058fa2"', "우회: 값에 'example' 포함"),
    ('api_key="test_9f3ab21c77de40b8a1e6c5d4"', "우회: 값에 'test' 포함"),
    # --- 2차 적대 검증(2026-07-23)에서 뚫린 우회. 1차 수정이 만든 새 구멍이었다.
    # ① 숫자만으로 된 값을 무조건 filler 로 봤다(`w.isdigit()` 무제한 예외).
    # ② SCREAMING_SNAKE_CASE 면 뒤에 opaque 토큰이 붙어도 환경변수명으로 봤다.
    # 방어 로직 자체가 새 우회 경로를 만든 사례이므로 절대 지우지 말 것.
    ('secret_key = "123456789012345678901234567890"', "우회: 30자리 순수 숫자"),
    ('api_key="98765432109876543210"', "우회: 20자리 순수 숫자"),
    ('access_token = "1234567890123456"', "우회: 16자리 숫자"),
    ('api_key = "MY_SECRET_KEY_VALUE_ABCD1234"', "우회: SCREAMING_SNAKE + opaque 토큰"),
    ('api_key="AUTH_TOKEN_9F3AB21C77DE40B8"', "우회: SCREAMING_SNAKE + hex 토큰"),
    ('api_key="sk-1234567890123456789012"', "우회: sk- 접두사 뒤 숫자"),
    ('api_key="sk-or-v1-000000000000000000"', "우회: 벤더 접두사 뒤 숫자"),
]
MUST_NOT_BLOCK = [  # 오탐이면 안 되는 것 — 문서/코드 관용구
    ('OPENROUTER_API_KEY=your-api-key-here', "placeholder hyphenated"),
    ('api_key="PARALLEL_API_KEY"', "value is env-var NAME"),
    ('api_key = OPENROUTER_API_KEY', "unquoted env-var name"),
    ("if line.startswith('OPENROUTER_API_KEY='):\n    api_key = line.split('=', 1)[1]",
     "regex spanning newline into code"),
    ('api_key="your_api_key_here"', "underscore placeholder"),
    ('api_key = os.environ.get("OPENROUTER_API_KEY")', "os.environ read"),
    ('client = Parallel(api_key="...")', "ellipsis placeholder"),
    ('sk-or-v1-your-api-key-here', ".env.example line"),
    # 벤더 접두사(sk-or-v1-)가 붙은 플레이스홀더. 접두사만 보고 "진짜 키"로
    # 판정하면 문서 전체가 오탐이 된다 (2026-07-23 실측).
    ("export OPENROUTER_API_KEY='sk-or-v1-your-key-here'", "벤더 접두사 + 플레이스홀더"),
    ('OPENROUTER_API_KEY=sk-or-v1-your-api-key-here', "벤더 접두사 (따옴표 없음)"),
    # 숫자 판정을 좁힐 때(위 MUST_BLOCK 참조) 짧은 인덱스 접미사까지 잡으면
    # 문서가 통째로 오탐이 된다. 짧은 숫자는 여전히 filler 여야 한다.
    ('api_key="your-key-2"', "짧은 숫자 접미사 (인덱스)"),
    ('api_key = "example_key_1"', "짧은 숫자 접미사 (언더스코어)"),
    ('api_key="PARALLEL_API_KEY"', "순수 환경변수명 (숫자 없음)"),
]

def detected(text):
    """doctor의 두 검사 중 하나라도 걸리면 True."""
    import re
    hard = re.compile(r"api_key\s*=\s*['\"][^'\"]{8,}['\"]", re.IGNORECASE)
    a = any(not doctor._is_placeholder(m.group(0))
            for m in doctor.API_KEY_RE.finditer(text))
    b = any(not doctor._is_placeholder(m.group(0)) for m in hard.finditer(text))
    return a or b

fails = 0
print("=== MUST BLOCK (진짜 키 — 탐지 필수) ===")
for text, label in MUST_BLOCK:
    ok = detected(text)
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    if not ok:
        fails += 1
        print(f"        놓침: {text[:70]!r}")

print("\n=== MUST NOT BLOCK (플레이스홀더 — 오탐 금지) ===")
for text, label in MUST_NOT_BLOCK:
    ok = not detected(text)
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    if not ok:
        fails += 1
        print(f"        오탐: {text[:70]!r}")

print(f"\n{'ALL PASS' if fails == 0 else str(fails) + ' FAILURE(S)'}")
sys.exit(1 if fails else 0)
