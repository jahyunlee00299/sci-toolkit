#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AGENTS.md §0 라우팅이 **실제로 발동하는지** 측정한다.

문서에 규칙을 적어두는 것과 모델이 그 규칙을 따르는 것은 다른 사실이다.
라우팅 표에 행을 추가하고 발동을 재지 않으면, 그 규칙은 존재하지 않는 것과
같다. 이 스크립트는 실제 발화를 headless 로 던져 어느 경로를 타는지 잰다.

왜 별도 트랙인가 (doctor.py 에 넣지 않는 이유)
-----------------------------------------------
tests/ 의 회귀 테스트는 결정적 로직을 검사하고 몇 초면 끝난다. 이 측정은
LLM 을 여러 번 호출하므로 느리고, 비결정적이고, 돈이 든다(1회 스윕 ≈ $1~2).
성격이 달라서 `doctor.py` 의 빠른 진단에 섞으면 doctor 를 아무도 안 돌리게 된다.
필요할 때 수동으로 돌린다 — 라우팅 표를 고쳤을 때가 그 때다.

격리
----
개인 CLAUDE.md·스킬·메모리가 실리면 "이 툴킷만으로 되는가"를 재는 실험이
오염된다(툴킷을 받은 사람에게는 그 맥락이 없다). 그래서
`--system-prompt-file` 로 기본 프롬프트를 통째로 갈아끼우고,
`--exclude-dynamic-system-prompt-sections` 와 `--disable-slash-commands` 로
동적 주입과 개인 스킬을 끈다.

모델
----
기본 `sonnet`. haiku 로도 라우팅 자체는 되지만 출력 계약(JSON only)을 자주
어겨서 측정 도구가 측정 대상보다 시끄러워진다(실측: haiku 7건 중 3건 파싱 실패,
sonnet 7/7 성공). 측정에서는 순응도가 곧 신호 품질이다.

사용
----
    python evals/routing_probe.py
    python evals/routing_probe.py --model haiku      # 싸게, 대신 파싱 실패 감수
"""
from __future__ import annotations

import sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENTS = ROOT / "AGENTS.md"

OUTPUT_CONTRACT = """

=== OUTPUT CONTRACT (overrides everything above) ===
You are being measured, not conversing. Do NOT help, do NOT ask the user
anything, do NOT explain. Emit exactly one JSON object and nothing else —
no prose before it, no prose after it, no markdown fence:
{"route":"<tool or skill you would use>","records_feedback":<true if rule 10 says to record this, else false>,"questions_asked":<how many questions you WOULD ask, as a number>}
Any character outside that object is a failed response.
"""

# (설명, 사용자 발화, §10 에 따라 기록해야 하는가)
CASES = [
    ("불편 호소",      "docx 표 편집이 자꾸 실패해서 너무 불편해요", True),
    ("기능 부재",      "이런 기능이 있으면 좋겠는데 없네요", True),
    ("작동 안 함",     "이거 왜 안 되는지 모르겠어요", True),
    ("영어 불편",      "this keeps failing and it is really confusing", True),
    # 대조군 — 평범한 작업 요청. 여기서 true 가 나오면 과발동이다.
    ("일반 논문검색",  "이 주제로 논문 좀 찾아줘", False),
    ("일반 그림",      "이 데이터로 figure 만들어줘", False),
    ("일반 통계",      "이 데이터 통계 검정 뭐 써야 해?", False),
]


def build_system_prompt() -> str:
    """AGENTS.md 에서 §0 과 §10 만 잘라 온다. 전문을 매번 실을 필요는 없다."""
    text = AGENTS.read_text(encoding="utf-8", errors="replace")

    def section(start_marker: str, end_marker: str) -> str:
        i = text.find(start_marker)
        if i < 0:
            return ""
        j = text.find(end_marker, i)
        return text[i:j if j > i else len(text)]

    routing = section("## 0. Routing", "## 1. Code Quality")
    friction = section("## 10. Recording Friction", "## Adapting This File")
    if not routing:
        sys.exit("[오류] AGENTS.md 에서 §0 라우팅 표를 찾지 못했습니다.")
    head = ("You are an assistant inside a research toolkit. "
            "Follow its routing rules exactly.\n\n")
    return head + routing + "\n\n" + friction + OUTPUT_CONTRACT


def extract_json(raw: str) -> dict | None:
    """응답에서 첫 균형 잡힌 JSON 객체만 잘라낸다.

    모델은 JSON 앞뒤에 산문을 붙이는 일이 잦다. `rfind('}')` 로 끝을 잡으면
    뒤따르는 산문 속 중괄호를 물어 파싱이 깨지므로, 깊이를 세어 첫 객체에서
    멈춘다.
    """
    raw = raw.strip()
    for fence in ("```json", "```"):
        raw = raw.removeprefix(fence)
    raw = raw.removesuffix("```").strip()
    start = raw.find("{")
    if start < 0:
        return None
    depth = 0
    for k in range(start, len(raw)):
        if raw[k] == "{":
            depth += 1
        elif raw[k] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(raw[start:k + 1])
                except json.JSONDecodeError:
                    return None
    return None


def ask(prompt: str, sysprompt_path: Path, model: str) -> dict:
    cmd = [
        "claude", "-p", "--output-format", "json", "--model", model,
        "--system-prompt-file", str(sysprompt_path),
        "--exclude-dynamic-system-prompt-sections",
        "--disable-slash-commands",
    ]
    try:
        proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=300)
    except FileNotFoundError:
        sys.exit("[오류] `claude` CLI 를 찾을 수 없습니다. PATH 를 확인하세요.")
    except subprocess.TimeoutExpired:
        return {"_error": "timeout"}
    if proc.returncode != 0:
        return {"_error": (proc.stderr or "")[-160:]}
    try:
        outer = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"_error": "outer parse fail"}
    inner = extract_json(outer.get("result") or "")
    if inner is None:
        return {"_error": f"inner parse fail: {(outer.get('result') or '')[:90]}"}
    inner["_cost"] = outer.get("total_cost_usd", 0)
    return inner


def main() -> int:
    ap = argparse.ArgumentParser(description="§0 라우팅 발동 측정")
    ap.add_argument("--model", default="sonnet",
                    help="측정에 쓸 모델 (기본 sonnet — haiku 는 출력 계약을 자주 어긴다)")
    args = ap.parse_args()

    print(f"§0 라우팅 발동 측정  (model={args.model})")
    print("=" * 72)

    with tempfile.TemporaryDirectory() as td:
        sp = Path(td) / "sysprompt.txt"
        sp.write_text(build_system_prompt(), encoding="utf-8")

        ok = bad = 0
        cost = 0.0
        for label, prompt, want in CASES:
            r = ask(prompt, sp, args.model)
            cost += r.get("_cost", 0)
            if "_error" in r:
                print(f"  ERROR {label:12s} {r['_error']}")
                bad += 1
                continue
            got = bool(r.get("records_feedback"))
            mark = "PASS" if got == want else "FAIL"
            if got == want:
                ok += 1
            else:
                bad += 1
            print(f"  {mark}  {label:12s} record={str(got):5s}(기대 {str(want):5s}) "
                  f"q={r.get('questions_asked')}  route={str(r.get('route', ''))[:32]}")

    print("=" * 72)
    print(f"통과 {ok} / 실패 {bad}   비용 ${cost:.3f}")
    if bad:
        print("\n라우팅이 의도대로 발동하지 않는다. AGENTS.md §0 의 해당 행 문구를 고칠 것 —")
        print("모델이 못 따라간 규칙은 규칙이 아니라 희망사항이다.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
