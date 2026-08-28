#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Measures whether AGENTS.md §0 routing **actually fires**.

Writing a rule down in a document and the model actually following that rule
are two different facts. Add a row to the routing table without measuring
whether it fires, and that rule is effectively nonexistent. This script fires
real utterances headless and measures which path gets taken.

Why a separate track (why not fold this into doctor.py)
---------------------------------------------------------
The regression tests under tests/ check deterministic logic and finish in
seconds. This measurement calls the LLM multiple times, so it's slow,
non-deterministic, and costs money (one sweep ≈ $1-2). The character is
different enough that mixing it into doctor.py's fast diagnostics would mean
nobody runs doctor anymore. Run it by hand when needed — that's whenever the
routing table changes.

Isolation
---------
If a personal CLAUDE.md, skills, or memory get loaded, it contaminates the
experiment measuring "does this work on the toolkit alone" (someone who just
received the toolkit has none of that context). So `--system-prompt-file`
completely replaces the default prompt, and
`--exclude-dynamic-system-prompt-sections` and `--disable-slash-commands`
turn off dynamic injection and personal skills.

Model
-----
Default is `sonnet`. Routing itself still works with haiku, but it frequently
breaks the output contract (JSON only), so the measurement tool ends up
noisier than the thing being measured (measured: haiku failed to parse 3 of 7
cases, sonnet succeeded 7/7). For this measurement, compliance IS signal
quality.

Usage
-----
    python evals/routing_probe.py
    python evals/routing_probe.py --model haiku      # cheaper, at the cost of parse failures
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

# (label, user utterance, should §10 record this)
# NOTE: the label and utterance strings are the probe's actual test input —
# they exercise Korean-language routing per AGENTS.md §0/§10, so they stay in
# Korean on purpose. Translating them would test a different (English) input
# than the one this eval is designed to probe.
CASES = [
    ("불편 호소",      "docx 표 편집이 자꾸 실패해서 너무 불편해요", True),
    ("기능 부재",      "이런 기능이 있으면 좋겠는데 없네요", True),
    ("작동 안 함",     "이거 왜 안 되는지 모르겠어요", True),
    ("영어 불편",      "this keeps failing and it is really confusing", True),
    # control group — an ordinary work request. If this comes back true, that's over-firing.
    ("일반 논문검색",  "이 주제로 논문 좀 찾아줘", False),
    ("일반 그림",      "이 데이터로 figure 만들어줘", False),
    ("일반 통계",      "이 데이터 통계 검정 뭐 써야 해?", False),
]


def build_system_prompt() -> str:
    """Cut just §0 and §10 out of AGENTS.md. No need to load the whole document each time."""
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
        sys.exit("[error] Could not find the §0 routing table in AGENTS.md.")
    head = ("You are an assistant inside a research toolkit. "
            "Follow its routing rules exactly.\n\n")
    return head + routing + "\n\n" + friction + OUTPUT_CONTRACT


def extract_json(raw: str) -> dict | None:
    """Cut out just the first balanced JSON object from the response.

    The model often wraps the JSON in prose before and after it. Grabbing the
    end with `rfind('}')` can catch a brace inside the trailing prose and
    break parsing, so this counts depth and stops at the first complete
    object instead.
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
        sys.exit("[error] Could not find the `claude` CLI. Check your PATH.")
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
    ap = argparse.ArgumentParser(description="Measure §0 routing firing")
    ap.add_argument("--model", default="sonnet",
                    help="model to use for the measurement (default sonnet — haiku often breaks the output contract)")
    args = ap.parse_args()

    print(f"§0 routing firing measurement  (model={args.model})")
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
            print(f"  {mark}  {label:12s} record={str(got):5s}(expected {str(want):5s}) "
                  f"q={r.get('questions_asked')}  route={str(r.get('route', ''))[:32]}")

    print("=" * 72)
    print(f"PASS {ok} / FAIL {bad}   cost ${cost:.3f}")
    if bad:
        print("\nRouting is not firing as intended. Fix the wording of that row in AGENTS.md §0 —")
        print("a rule the model can't follow isn't a rule, it's a wish.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
