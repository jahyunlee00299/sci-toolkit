#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Checks whether an adopted "development discipline" skill actually still carries the discipline's substance.

Run: python tests/test_adopted_discipline_skills.py   (exit 0 = pass)

Why this file exists
---------------------
`test_skill_references.py` checks that references actually exist;
`test_doc_counts.py` checks that counts add up. A skill's body can become
an **empty shell** while both still pass — strip out the discipline clauses
and leave only the title and frontmatter, and both checks stay green.

Each discipline skill this repository has adopted exists to prevent "one
failure mode an agent repeatedly falls into." If the sentence that prevents
that failure disappears, the skill is a name with nothing behind it. So this
checks **whether each skill still actually carries the clause that is its
reason for existing**.

Removing a clause from the docs means updating this check too — that
enforcement IS the point. Weakening the check just to make it pass is the
same as erasing the discipline (AGENTS.md §0 rule 2).

Each entry is (description, phrases that represent that clause), and passing
requires **any one** of the phrases to be present. Multiple phrases exist to
leave room for wording tweaks, not to loosen the check — if the clause itself
disappears, every phrase disappears with it.
"""
from __future__ import annotations

import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"

# skill name -> [(clause description, [candidate phrases...]), ...]
REQUIRED_SUBSTANCE: dict[str, list[tuple[str, list[str]]]] = {
    "debugging-loop": [
        ("the ordering rule that the reproduction loop comes before a hypothesis",
         ["before you form", "before forming any theory",
          "before a red-capable command exists",
          "before** proposing a cause", "loop first, a theory second"]),
        ("the loop must verify the symptom the user described, not just 'doesn't crash'",
         ["red-capable", "asserts the *symptom", "symptom the\nuser described",
          "not a signal"]),
        ("hypotheses number 3-5 and each must be falsifiable",
         ["3–5 ranked hypotheses", "3-5 ranked hypotheses", "falsifiable"]),
        ("debug output is tagged so it can be retrieved",
         ["[DBG-", "[DEBUG-", "Tag every debug"]),
        ("re-confirm against the original scenario, not just the minimized repro",
         ["un-minimised", "un-minimized", "original (un-minimis"]),
        ("when there is no correct seam to hang a regression test on, that absence is itself the finding",
         ["no correct seam exists, that is itself the finding",
          "no correct seam exists, that itself is the finding"]),
    ],
    "test-quality": [
        ("the clause against recomputing an expected value the same way the implementation does",
         ["recomputed the way the code computes it",
          "passes by construction"]),
        ("expected values must have a legitimate independent source (hand calc, instrument, literature, etc.)",
         ["come from outside the implementation",
          "hand-worked example", "independent source"]),
        ("the criterion for internally-coupled tests — does it break on refactor",
         ["breaks when you refactor", "coupled to internal",
          "Coupling to internals"]),
        ("writing all tests up front ends up verifying imagined behavior",
         ["imagined", "vertical slices"]),
        ("agree on seams first, and pick the highest seam",
         ["Agree the seams before", "highest seam"]),
        ("the detection-power question — would it still pass on a plausible wrong answer",
         ["plausible wrong answer"]),
        ("a converged fit alone is not a passing test (recover parameters against synthetic ground truth)",
         ["converged fit is not a passing test", "known synthetic ground truth",
          "synthetic ground truth"]),
    ],
    "code-quality": [
        ("review separates the Standards and Spec axes",
         ["Review two axes separately", "two axes separately"]),
        ("findings are not reranked across axes",
         ["do not\nrerank findings across the axes",
          "rerank findings across the axes"]),
        ("the Spec axis distinguishes missing scope, unrequested scope creep, and wrong implementation",
         ["scope creep"]),
        ("pin the comparison baseline first and confirm the diff is non-empty",
         ["pin the comparison point", "diff is non-empty"]),
        ("when there is no Spec, say so rather than substituting one arbitrarily",
         ["report the Spec axis as unavailable",
          "no written spec"]),
    ],
}

# frontmatter fields every skill must have
REQUIRED_FRONTMATTER = ("name:", "description:")


def check_skill(name: str, clauses: list[tuple[str, list[str]]]) -> list[str]:
    problems: list[str] = []
    path = SKILLS / name / "SKILL.md"
    if not path.is_file():
        return [f"{name}: SKILL.md is missing — {path.relative_to(ROOT)}"]

    text = path.read_text(encoding="utf-8")

    if not text.startswith("---"):
        problems.append(f"{name}: no frontmatter (must start with ---)")
    else:
        head = text.split("---", 2)[1]
        for field in REQUIRED_FRONTMATTER:
            if field not in head:
                problems.append(f"{name}: frontmatter is missing {field}")
        # if the name differs from the folder name, the skill loads under a different name
        if f"name: {name}" not in head:
            problems.append(
                f"{name}: frontmatter's name does not match the folder name")

    for label, candidates in clauses:
        if not any(c in text for c in candidates):
            problems.append(
                f"{name}: the '{label}' clause has disappeared from the body "
                f"(no matching phrase found: {candidates[0]!r} or {len(candidates)} variants)")
    return problems


def main() -> int:
    problems: list[str] = []
    checked = 0
    for name, clauses in REQUIRED_SUBSTANCE.items():
        problems += check_skill(name, clauses)
        checked += len(clauses) + len(REQUIRED_FRONTMATTER)

    if problems:
        print(f"FAIL — {len(problems)} missing discipline clause(s) in adopted skills")
        for p in problems:
            print(f"  - {p}")
        print("\nIf you deliberately changed a clause, update this check too. "
              "Deleting only the check leaves the skill a name with nothing behind it.")
        return 1

    print(f"ALL PASS — {len(REQUIRED_SUBSTANCE)} adopted skill(s), "
          f"{checked} clause(s) confirmed present in the body")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
