#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pin down that the spec-driven-research-dev skill actually holds the 4-phase flow.

This skill is **prompt + templates**, not a script. There is no executable
code, so "run it and see" does not apply — instead this checks whether the
structure that makes this flow a flow is still there. That structure is what
was carried over from github/spec-kit, and if a phase quietly drops out while
someone is editing the docs, the other three become meaningless without
anyone noticing (plan reads spec, tasks reads plan, implement reads tasks).

Contract:
  1. All 4 phases (specify/plan/tasks/implement) are present in SKILL.md.
  2. All 4 template files actually exist — SKILL.md instructs the user to
     "copy and use" them, so a missing one means following the instruction
     fails.
  3. The spec template carries the rule that forbids implementation detail.
     This rule is the core of the flow (Phase 1 must exclude tech choices so
     what hasn't been agreed on becomes visible) — without it, spec is just a
     design document and there's no reason to adopt this skill.
  4. The tasks template's checklist format ([ID] [P] [Story] + file path) is
     intact. A task missing an ID or file path can't be honestly executed or
     checked off.
  5. The upstream source (github/spec-kit) and its license are recorded in
     NOTICE.md — MIT permits reuse but conditions it on attribution.
  6. AGENTS.md §0 points at this skill. An unwired skill is the same as one
     that doesn't exist (the routing table is the agent's entry point).

Run:
    python tests/test_spec_driven_workflow.py           # exit 0 = pass
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Windows' default console is cp949, which dies on Korean/symbol output. Force UTF-8.
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = ROOT / "skills" / "spec-driven-research-dev"
SKILL_MD = SKILL_DIR / "SKILL.md"
TEMPLATES = SKILL_DIR / "templates"

PHASES = ("specify", "plan", "tasks", "implement")
TEMPLATE_FILES = (
    "spec-template.md",
    "plan-template.md",
    "tasks-template.md",
    "checklist-template.md",
)


def check_skill_md(failures: list[str]) -> str:
    if not SKILL_MD.is_file():
        failures.append(f"SKILL.md is missing — {SKILL_MD.relative_to(ROOT)}")
        return ""
    text = SKILL_MD.read_text(encoding="utf-8")

    # 1) are all 4 phases mentioned
    missing = [p for p in PHASES if p not in text.lower()]
    if missing:
        failures.append(
            f"phase(s) missing from SKILL.md: {missing} — the 4 phases read "
            f"each other, so a missing phase leaves the rest without grounding")

    # do the phases exist as headings (distinct from the word merely passing through the body)
    headings = re.findall(r"^##+\s*(.+)$", text, re.M)
    joined = " | ".join(headings).lower()
    no_heading = [p for p in PHASES if p not in joined]
    if no_heading:
        failures.append(
            f"SKILL.md has no heading for phase(s): {no_heading} — appearing only "
            f"as a word means the agent can't recognize it as an execution unit")
    return text


def check_templates(failures: list[str]) -> None:
    for name in TEMPLATE_FILES:
        p = TEMPLATES / name
        if not p.is_file():
            failures.append(
                f"template missing: templates/{name} — SKILL.md instructs the "
                f"user to copy and use it, so a missing file breaks that instruction")

    spec_t = TEMPLATES / "spec-template.md"
    if spec_t.is_file():
        t = spec_t.read_text(encoding="utf-8")
        # 3) the "no implementation detail" rule — the core constraint of this flow
        if not re.search(r"No language, library, file layout", t):
            failures.append(
                "the 'no implementation detail' rule is gone from the spec "
                "template — Phase 1 must exclude tech choices for what hasn't "
                "been agreed on to surface. Without this rule, spec is just a "
                "design document and there's no reason to use this skill")
        for section in ("Success Criteria", "Assumptions", "Independent Test"):
            if section not in t:
                failures.append(f"spec template has no '{section}' section")

    tasks_t = TEMPLATES / "tasks-template.md"
    if tasks_t.is_file():
        t = tasks_t.read_text(encoding="utf-8")
        # 4) is the checklist format still intact
        if not re.search(r"-\s*\[\s*\]\s*T###", t):
            failures.append(
                "tasks template has no `- [ ] T###` format definition — a task "
                "without an ID can't be honestly ordered or checked off")
        if "exact path" not in t and "파일 경로" not in t:
            failures.append(
                "tasks template does not require an 'exact file path' — a task "
                "without a path can neither be executed nor confirmed complete")
        for marker in ("[P]", "[US#]"):
            if marker not in t:
                failures.append(f"tasks template has no explanation of the {marker} marker")


def check_attribution(failures: list[str]) -> None:
    notice = ROOT / "NOTICE.md"
    if not notice.is_file():
        failures.append("NOTICE.md is missing")
        return
    t = notice.read_text(encoding="utf-8")
    if "github/spec-kit" not in t:
        failures.append(
            "NOTICE.md has no upstream attribution (github/spec-kit) — MIT "
            "permits reuse but conditions it on attribution. A missing "
            "attribution is a license violation")
    # the MIT mark must be in the same paragraph as the attribution to mean anything
    m = re.search(r"github/spec-kit.{0,400}", t, re.S)
    if m and "MIT" not in m.group(0):
        failures.append("NOTICE.md's spec-kit entry has no license (MIT) mark")


def check_wiring(failures: list[str]) -> None:
    agents = ROOT / "AGENTS.md"
    if not agents.is_file():
        failures.append("AGENTS.md is missing")
        return
    text = agents.read_text(encoding="utf-8")
    m = re.search(r"^## 0\. Routing.*?(?=^## 1\.)", text, re.S | re.M)
    if not m:
        failures.append("AGENTS.md has no §0 Routing section")
        return
    if "spec-driven-research-dev" not in m.group(0):
        failures.append(
            "AGENTS.md §0 routing table does not point at "
            "spec-driven-research-dev — an unwired skill is the same as one "
            "that doesn't exist (§0 is the entry point)")

    catalog = ROOT / "config" / "catalog.json"
    if catalog.is_file():
        import json
        d = json.loads(catalog.read_text(encoding="utf-8"))
        if "spec-driven-research-dev" not in d.get("skills", {}):
            failures.append(
                "not registered in config/catalog.json — the installer "
                "can't see this skill as something to install")


def main() -> int:
    failures: list[str] = []
    check_skill_md(failures)
    check_templates(failures)
    check_attribution(failures)
    check_wiring(failures)

    if failures:
        print(f"FAIL — {len(failures)} spec-driven-research-dev contract violation(s)")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("ALL PASS — 4-phase flow, 4 templates, attribution, and §0 wiring all confirmed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
