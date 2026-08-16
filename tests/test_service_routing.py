#!/usr/bin/env python3
"""문서가 외부 서비스·스킬을 가리킬 때 갈 곳이 실제로 있는지 검사한다.

실행: python tests/test_service_routing.py   (exit 0 = 통과)

왜 이 파일이 필요한가 — 260816 적대검증에서 드러난 두 개의 사각지대
--------------------------------------------------------------------
이 저장소는 "MCP 대신 REST 커넥터" 정책을 문서 여러 곳에 두고 있다. 그런데
그 정책이 지켜지는지 기계적으로 확인하는 장치는 없었다. 실제로 뚫렸다:

`skills/academic-term-rules/.prompt.md` 는 "Notion 페이지를 이렇게 써라"라고
지시하면서 `notion_connector.py` 를 한 번도 언급하지 않았다. MCP 라는 단어가
없어서 문자열 검색에 안 걸렸고, 점으로 시작하는 파일이라 `SKILL.md` 글롭에도
안 걸렸다. 커넥터를 안 알려주는 침묵 자체가 유도다 — 에이전트는 자기가 가진
아무 도구나 쓰게 되고, 그게 MCP다.

같은 자리에서 두 번째 사각지대도 나왔다. `test_skill_references.py` 는
260807에 "skills/ **밖** 문서"를 보도록 확장됐는데, 그 반대편 —
skills/ **안**의 문서가 배포되지 않는 스킬을 가리키는 경우 — 는 여전히
아무도 안 본다. 죽은 스킬 참조는 그 자체로 또 하나의 폴백 유발기다.

검사 2종
--------
A. 커넥터 보유 서비스(mail·GitHub·Asana·Notion)를 **지시문으로** 언급하는
   문서가 커넥터 스크립트를 함께 알려주는가
B. skills/ 안의 문서가 이 저장소에 없는 스킬을 가리키지 않는가

A 는 오탐이 나기 쉬운 검사다(서비스 이름은 렌더링 호환성·예시로도 쓰인다).
그래서 "지시문"으로 좁힌다 — 제목에 서비스명이 들어간 절만 본다. 절 제목은
"이 문서는 이 서비스를 다룬다"는 저자의 선언이라, 지나가는 언급과 구분된다.
"""
import os
import re
import sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_DIR = os.path.join(ROOT, "skills")
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "node_modules", ".venv"}
TEXT_SUFFIXES = (".md", ".txt", ".prompt.md")

# 커넥터가 있는 서비스 → 그 서비스를 다루는 문서가 반드시 언급해야 할 스크립트.
# 캘린더·공유시트는 커넥터가 없으므로(문서화된 예외) 여기 없다.
CONNECTOR_SERVICES = {
    "notion": ("notion_connector.py", "notion_db_connector.py"),
    "asana": ("asana_connector.py",),
    "github": ("github_connector.py",),
}

# 제목에 서비스명이 있다고 다 '접근'은 아니다. "GitHub 에서 Mermaid 가 어떻게
# 보이는가"는 렌더링 호환성이지 API 호출이 아니다. 그래서 제목만으로 판정하지
# 않고, 그 절이 **행동을 지시하는가**를 함께 본다.
#
# 지시 동사가 하나도 없으면 그 절은 설명이지 지시가 아니다 — 에이전트가 그걸
# 읽고 서비스에 접속하려 들 이유가 없으므로 커넥터를 안 알려도 무방하다.
#
# 260816 실측: 첫 판은 본문에서만 행동어를 찾다가 원래 위반을 놓쳤다.
# `.prompt.md` §11 은 제목이 "Notion Page **Writing** Rules" 인데 본문은
# "use `<br>`", "must use public URLs" 라서 write/작성 이 안 걸렸다.
# 지시성은 제목에 실리는 경우가 많다 — 제목+본문을 함께 본다.
ACTION_WORDS = (
    # 영어 — 명령형과 동명사형을 함께 본다("write"는 "writing"도 포함한다)
    "creat", "updat", "writ", "post", "upload", "append", "add ",
    "send", "fetch", "quer", "search", "sync", "log ", "publish",
    "must use", "forbidden", "rules",
    # 한국어
    "생성", "작성", "등록", "업로드", "추가", "전송", "조회", "검색",
    "동기화", "기록", "올린", "올려", "발행", "수정", "삭제", "규칙",
)

# 서비스명이 제목에 있어도 '접근'이 아닌 경우 — 렌더링 호환성, 표기 예시 등.
# 좁게 유지할 것: 여기 추가하는 건 검사를 약화시키는 일이다.
HEADING_ALLOW = (
    "mermaid",        # "GitHub / Notion 에서 Mermaid 가 어떻게 보이는가"
    "markdown",
    "renders", "render",
    "compatib",
    "theme", "directive",
)

_pass = 0
_fail = 0
_failures = []


def check(name, cond, detail=""):
    global _pass, _fail
    if cond:
        _pass += 1
        print(f"  PASS  {name}")
    else:
        _fail += 1
        _failures.append(name)
        print(f"  FAIL  {name}" + (f" — {detail}" if detail else ""))


def walk_text(base):
    for dp, dns, fns in os.walk(base):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for f in fns:
            if f.lower().endswith(TEXT_SUFFIXES):
                yield os.path.join(dp, f)


def rel(p):
    return os.path.relpath(p, ROOT).replace("\\", "/")


# ─────────────────────────────────────────────────────────────
print("\n[A] 커넥터 보유 서비스를 다루는 절이 커넥터를 알려주는가")

violations = []
for path in walk_text(SKILLS_DIR):
    try:
        text = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        continue

    lines = text.splitlines()
    for i, line in enumerate(lines, 1):
        if not line.startswith("#"):
            continue
        low = line.lower()
        if any(a in low for a in HEADING_ALLOW):
            continue
        for svc, scripts in CONNECTOR_SERVICES.items():
            if svc not in low:
                continue
            # 파일 어디에서든 커넥터를 언급하면 통과 (같은 절 안일 필요는 없다).
            if any(s in text for s in scripts):
                continue
            # 제목 + 절 본문(다음 제목 전까지)이 행동을 지시하는가.
            # 설명뿐이면 에이전트가 서비스에 접속할 이유가 없으므로 위반이 아니다.
            body = [line]
            for nxt in lines[i:]:
                if nxt.startswith("#"):
                    break
                body.append(nxt)
            body_low = "\n".join(body).lower()
            if not any(w in body_low for w in ACTION_WORDS):
                continue
            violations.append((rel(path), i, line.strip(), svc, scripts))

check("커넥터 침묵 위반 없음", not violations,
      f"{len(violations)}건")
for f, i, head, svc, scripts in violations:
    print(f"        {f}:{i}  {head!r}")
    print(f"          → {svc} 접근을 지시하면서 {'/'.join(scripts)} 를 알려주지 않는다.")
    print(f"          → 커넥터를 명시하거나, 접근 지시가 아니면 제목에서 서비스명을 빼라.")


# ─────────────────────────────────────────────────────────────
print("\n[B] skills/ 안의 문서가 없는 스킬을 가리키지 않는가")

shipped = {d for d in os.listdir(SKILLS_DIR)
           if os.path.isdir(os.path.join(SKILLS_DIR, d))}

# 임의의 케밥 토큰을 다 줍지 않는다 — `x-axis`·`margin-top`·`load-bearing` 처럼
# 스킬과 형태만 같은 말이 너무 많고, 허용목록으로 쫓아가는 건 지는 싸움이다.
# 대신 **스킬로 호명하는 문법**만 잡는다: 이름 바로 옆에 skill/스킬 이라고
# 적혀 있거나, Skill(...) 로 호출하는 형태. 저자가 "이건 스킬이다"라고 말한
# 자리만 보므로 오탐이 거의 없고, 놓치더라도 안전한 쪽으로 놓친다.
NAMED_SKILL = re.compile(
    r"""(?:
          `([a-z][a-z0-9-]*)`\s*(?:스킬|skill\b)     # `foo` 스킬 / `foo` skill
        | (?:스킬|skill)\s*[:：]?\s*`([a-z][a-z0-9-]*)`  # 스킬 `foo`
        | Skill\(\s*['"]?([a-z][a-z0-9-]*)           # Skill("foo")
        )""",
    re.I | re.X,
)

filtered = []
for path in walk_text(SKILLS_DIR):
    try:
        text = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        continue
    for i, line in enumerate(text.splitlines(), 1):
        for groups in NAMED_SKILL.findall(line):
            tok = next((g for g in groups if g), None)
            if not tok or tok in shipped:
                continue
            filtered.append((rel(path), i, tok, line.strip()))

check("죽은 스킬 참조 없음", not filtered, f"{len(filtered)}건")
for f, i, tok, line in filtered:
    print(f"        {f}:{i}  '{tok}' — 이 저장소에 없다")
    print(f"          {line[:100]}")
print(f"        (배포 스킬 {len(shipped)}종 기준)")


# ─────────────────────────────────────────────────────────────
print("\n" + "-" * 60)
print(f"통과 {_pass} / 실패 {_fail}")
if _fail:
    print("\nFAIL — 문서가 실체 없는 곳을 가리킨다.")
    print("에이전트는 가리킨 곳이 비어 있으면 자기가 가진 다른 수단으로 넘어간다")
    print("(= 커넥터 대신 MCP). 참조를 고치거나, 지시가 아니면 표현을 바꿀 것.")
    sys.exit(1)
print("ALL PASS — 서비스·스킬 참조가 전부 실체를 가리킨다")
sys.exit(0)
