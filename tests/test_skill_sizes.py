#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SKILL.md size gate — a skill body that outgrows what an agent will actually read.

Why this exists
---------------
Measured 2026-09-02: avoid-ai-writing/SKILL.md was 93.6 KB, journal-
presentation-maker 37.9 KB, literature-review 25.3 KB. A SKILL.md is loaded
whole into the agent's context every time the skill fires; past a few tens
of KB the model skims, and the rules at the bottom stop being followed.
AGENTS.md has had a 32 KiB test since it was split for Codex; SKILL.md had
none, so a hand trim (commit 6be7dda) had nothing to stop regrowth.

The rule
--------
* HARD cap for every SKILL.md: ``HARD_MAX`` bytes (24 KiB). A new or
  ordinary skill over it fails.
* ADVISORY: over ``SOFT_MAX`` (16 KiB) is printed as a warning, exit 0.
* GRANDFATHERED skills already over the cap on the day this gate landed are
  listed in ``GRANDFATHERED`` with their measured size. Each may only
  SHRINK: growing past its recorded size fails; when it drops under
  ``HARD_MAX`` the entry must be removed (the gate says so). These three are
  shared skills whose authoring copy lives in the maintainer's runtime tree,
  so the trim itself goes there first (skill_drift rule) — this gate stops
  the toolkit copy from getting worse in the meantime.

Two groups: ``repo`` evaluates the live tree; ``synth`` feeds the same
``evaluate()`` synthetic size tables so every verdict is pinned without
touching a real SKILL.md.

Run: python tests/test_skill_sizes.py
"""
from __future__ import annotations

import sys
from pathlib import Path

if sys.platform == "win32":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"

HARD_MAX = 24 * 1024
SOFT_MAX = 16 * 1024

# name -> bytes measured 2026-09-02. Only ever lower a number; delete the
# entry once the file is under HARD_MAX. The single allowed exception is a
# spec-conformance edit to the frontmatter, recorded here with date and delta:
#   2026-09-03 avoid-ai-writing 93649 -> 93653 (+4): top-level `version:`
#   moved under `metadata:` (Agent Skills spec, tests/test_skill_contract.py);
#   body untouched.
GRANDFATHERED = {
    "avoid-ai-writing": 93653,
    "literature-review": 25273,
}


def evaluate(sizes: dict[str, int], grandfathered: dict[str, int],
             hard_max: int = HARD_MAX, soft_max: int = SOFT_MAX
             ) -> tuple[list[tuple[str, bool, str]], list[str]]:
    """Return (verdicts, advisories). verdict = (name, ok, reason)."""
    verdicts: list[tuple[str, bool, str]] = []
    advisories: list[str] = []
    for name, n in sizes.items():
        if name in grandfathered:
            cap = grandfathered[name]
            if n > cap:
                verdicts.append((name, False, f"grew {cap} -> {n} B; grandfathered files may only shrink — trim in the authoring tree first, never raise the number"))
            elif n < hard_max:
                verdicts.append((name, False, f"now {n} B < HARD_MAX {hard_max} — remove it from GRANDFATHERED"))
            else:
                verdicts.append((name, True, f"{n} B <= grandfathered {cap} B"))
            continue
        if n > hard_max:
            verdicts.append((name, False, f"{n} B > HARD_MAX {hard_max} B — move the long material into references/ and keep SKILL.md to the rules"))
        else:
            verdicts.append((name, True, f"{n} B <= HARD_MAX"))
            if n > soft_max:
                advisories.append(f"{name} ({n} B)")
    for name in sorted(set(grandfathered) - set(sizes)):
        verdicts.append((name, False, "listed in GRANDFATHERED but no such SKILL.md — drop the entry"))
    return verdicts, advisories


_results: list[tuple[bool, str]] = []


def check(name: str, cond: bool, note: str = "") -> None:
    _results.append((cond, name))
    tag = "[OK]  " if cond else "[FAIL]"
    print(f"  {tag} {name}" + (f"  {note}" if note and not cond else ""))


# --------------------------------------------------------------------------
print("== repo: live SKILL.md sizes")
sizes = {p.parent.name: p.stat().st_size for p in sorted(SKILLS.glob("*/SKILL.md"))}
check("at least one SKILL.md found", bool(sizes), str(SKILLS))
verdicts, advisories = evaluate(sizes, GRANDFATHERED)
for name, ok, reason in verdicts:
    check(f"{name}: {reason}" if ok else f"{name}", ok, reason)
if advisories:
    print("  [WARN] over SOFT_MAX (advisory): " + ", ".join(advisories))

# --------------------------------------------------------------------------
print("\n== synth: every verdict on synthetic size tables")
V = lambda s, g: {n: ok for n, ok, _ in evaluate(s, g)[0]}  # noqa: E731

check("ordinary skill under HARD_MAX -> ok", V({"a": 10_000}, {}) == {"a": True})
check("ordinary skill over HARD_MAX -> fail", V({"a": HARD_MAX + 1}, {}) == {"a": False})
check("ordinary skill exactly HARD_MAX -> ok", V({"a": HARD_MAX}, {}) == {"a": True})
check("over SOFT_MAX but under HARD_MAX -> ok + advisory",
      V({"a": SOFT_MAX + 1}, {}) == {"a": True} and evaluate({"a": SOFT_MAX + 1}, {})[1] == [f"a ({SOFT_MAX + 1} B)"])
check("grandfathered at its recorded size -> ok", V({"g": 50_000}, {"g": 50_000}) == {"g": True})
check("grandfathered shrank but still over cap -> ok", V({"g": 40_000}, {"g": 50_000}) == {"g": True})
check("grandfathered grew by 1 byte -> fail", V({"g": 50_001}, {"g": 50_000}) == {"g": False})
check("grandfathered dropped under HARD_MAX -> fail with 'remove it'",
      V({"g": HARD_MAX - 1}, {"g": 50_000}) == {"g": False}
      and "remove it" in evaluate({"g": HARD_MAX - 1}, {"g": 50_000})[0][0][2])
check("grandfathered entry with no file -> fail 'drop the entry'",
      V({}, {"ghost": 50_000}) == {"ghost": False})
check("empty tree -> no verdicts, no advisories", evaluate({}, {}) == ([], []))

# --------------------------------------------------------------------------
n_fail = sum(1 for ok, _ in _results if not ok)
print(f"\nSUMMARY: {len(_results) - n_fail} passed, {n_fail} failed; "
      f"{len(sizes)} SKILL.md checked, {len(advisories)} over soft cap, {len(GRANDFATHERED)} grandfathered")
sys.exit(1 if n_fail else 0)
