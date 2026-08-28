#!/usr/bin/env python3
"""Keeps the spec-first / test-first skills from **existing only as documents**.

These two skills are a discipline, not a script. There is no executable code,
so nothing turns red if they break — a file gets deleted, they drop out of the
§0 routing table, or an edit erases an approval-gate sentence, and doctor
still stays green. That is the typical death of "a feature with no wiring,"
so this measures both the wiring and the core rule sentences.

Checks (each axis here has actually broken once):

1. Both skill folders and SKILL.md exist.
2. Front matter has name/description/license, and name matches the folder name.
   (A mismatched name splits the name an agent calls from the name it installs as.)
3. AGENTS.md §0's routing table points at both skills. §0 is the agent's entry
   point — if a skill isn't there, it never gets invoked even when installed.
4. Registered in config/catalog.json (unregistered = the installer won't ship it).
5. **The core rules of the adoption survive in the body text.** These sentences
   are the reason it was pulled from upstream (obra/superpowers) in the first
   place — the approval gate, the iron law, the no-placeholders rule, the
   obligation to verify red. If a summarization pass drops these, the skill
   keeps its tone but loses its discipline.
6. The upstream source is recorded in NOTICE.md (MIT attribution obligation).

Run:
    python tests/test_development_discipline.py     # exit 0 = pass
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
SKILLS = ("spec-first-development", "test-first-development")
UPSTREAM = "github.com/obra/superpowers"

# Per skill, the rules where "if this sentence disappears, the adoption is
# pointless." The regexes are kept loose about formatting (bold, line breaks)
# but always require the words that carry the rule's **meaning**. Wording may
# be polished freely; the rule itself may not be erased.
REQUIRED_RULES: dict[str, list[tuple[str, str]]] = {
    "spec-first-development": [
        ("approval gate (approval required before code)",
         r"no implementation code until.{0,80}approved|"
         r"until you have told the requester.{0,120}said yes"),
        ("3-path classification (spike/bounded/architectural)",
         r"spike.{0,400}bounded.{0,400}architectural"),
        ("one-way ratchet (path only escalates)",
         r"ratchet is one-way|step \*?up\*? a path|nothing ever steps\s*\n?\s*down"),
        ("no placeholders",
         r"no placeholders|TBD.{0,60}TODO"),
        ("spec/plan self-review",
         r"self-review"),
    ],
    "test-first-development": [
        ("iron law (no implementation code without a test)",
         r"no implementation code without a failing test first"),
        ("obligation to verify RED (watch the failure with your own eyes)",
         r"watch it fail|verify red"),
        ("delete code written before the test",
         r"delete means delete"),
        ("minimal implementation (GREEN)",
         r"minimal code|minimal implementation"),
        ("never weaken a test to make it pass",
         r"weaken|fix the code, not the test"),
        ("test type for numeric research code",
         r"known-answer"),
    ],
}


def front_matter(text: str) -> dict[str, str]:
    """Shallowly read only the top-level key: value pairs of a --- ... --- block (no YAML dependency)."""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if not m:
        return {}
    out: dict[str, str] = {}
    for line in m.group(1).splitlines():
        km = re.match(r"^([a-z_]+):\s*(.*)$", line)
        if km:
            out[km.group(1)] = km.group(2).strip()
    return out


def main() -> int:
    failures: list[str] = []
    checked = 0

    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    m = re.search(r"^## 0\. Routing.*?(?=^## 1\.)", agents, re.S | re.M)
    routing = m.group(0) if m else ""
    if not routing:
        failures.append("AGENTS.md has no '## 0. Routing' section")

    try:
        catalog = json.loads(
            (ROOT / "config" / "catalog.json").read_text(encoding="utf-8"))
        cat_skills = catalog.get("skills", {})
    except (OSError, ValueError) as exc:
        cat_skills = {}
        failures.append(f"could not read config/catalog.json — {exc}")

    for skill in SKILLS:
        path = ROOT / "skills" / skill / "SKILL.md"

        checked += 1
        if not path.is_file():
            failures.append(f"{skill}: SKILL.md is missing — {path}")
            continue
        text = path.read_text(encoding="utf-8")

        fm = front_matter(text)
        for key in ("name", "description", "license"):
            checked += 1
            if not fm.get(key):
                failures.append(f"{skill}: front matter is missing '{key}'")
        checked += 1
        if fm.get("name") and fm["name"] != skill:
            failures.append(
                f"{skill}: front matter name='{fm['name']}' differs from the folder name "
                "— splits the name an agent calls from the name it installs as")

        checked += 1
        if f"`{skill}`" not in routing:
            failures.append(
                f"{skill}: not referenced by AGENTS.md §0's routing table "
                "— §0 is the entry point, so without it the skill is never invoked even when installed")

        checked += 1
        if skill not in cat_skills:
            failures.append(
                f"{skill}: missing from config/catalog.json's skills "
                "— the installer will not ship it")

        low = text.lower()
        for label, pattern in REQUIRED_RULES[skill]:
            checked += 1
            if not re.search(pattern, low, re.S):
                failures.append(
                    f"{skill}: a core rule has disappeared from the body text — {label}")

    checked += 1
    notice = (ROOT / "NOTICE.md").read_text(encoding="utf-8")
    if UPSTREAM not in notice:
        failures.append(
            f"NOTICE.md is missing the upstream source ({UPSTREAM}) — MIT attribution obligation")
    checked += 1
    if not all(s in notice for s in SKILLS):
        failures.append(
            "NOTICE.md does not name both skills as upstream derivatives")

    if failures:
        print(f"FAIL — {len(failures)} development-discipline skill wiring/rule issue(s) or more")
        for f in failures:
            print(f"  - {f}")
        return 1

    print(f"ALL PASS — {len(SKILLS)} development-discipline skill(s), {checked} check(s) "
          "(wiring, front matter, core rules, attribution)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
