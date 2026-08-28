#!/usr/bin/env python3
"""Pins the contract for adopted skills (units adapted in from an external repo).

`analysis-code-testing` and `data-quality-checks` were brought in by
**adapting**, not copying, units from wshobson/agents (MIT). For "adapting"
to hold true, three things have to stay true, and all three are the kind
that can silently break:

  1. **Attribution** — MIT requires keeping the copyright notice. Both the
     table in NOTICE.md and the `upstream:` line in SKILL.md front matter
     must stay alive. If front matter gets swapped out during a skill
     refactor, that becomes a license defect that nothing was watching for.
  2. **Model neutrality** — the upstream unit carries routing fields like
     `model: sonnet`. Skills in this repo are model-neutral, so that field
     must never come along. The next time something more gets pulled from
     upstream, a wholesale copy is exactly how this field rides in.
  3. **No upstream residue** — stripping out warehouse/web-service-only
     tooling (Great Expectations, dbt, freezegun, Airflow, ...) was the
     whole point of adapting. If that name shows up again, "adapting" has
     regressed back into "vendoring."

Run:
    python tests/test_adopted_skills.py     # exit 0 = pass
"""
from __future__ import annotations

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

# skill -> upstream unit path (the value to check against NOTICE.md's table and front matter)
ADOPTED = {
    "analysis-code-testing":
        "plugins/python-development/skills/python-testing-patterns",
    "data-quality-checks":
        "plugins/data-engineering/skills/data-quality-frameworks",
}
UPSTREAM_REPO = "https://github.com/wshobson/agents"

# Tools that existed upstream but must never carry over here. Pins the fact
# that they were stripped out.
#
# This catches **use**, not a **mention** of the name. A sentence like
# "upstream uses Great Expectations but we don't" is exactly the kind of
# adaptation note that should stay, and treating it as a failure would mean
# deleting a useful sentence just to pass the check (a classic path to
# weakening a gate). So this only catches an import/install/invocation
# shape — that alone is a real dependency.
VENDOR_USAGE = [
    (r"^\s*import\s+great_expectations", "import great_expectations"),
    (r"^\s*import\s+(dbt|airflow)\b", "import dbt/airflow"),
    (r"\bfrom\s+freezegun\s+import", "from freezegun import"),
    (r"@freeze_time\b", "@freeze_time decorator"),
    (r"\bgx\.get_context\s*\(", "gx.get_context()"),
    (r"\bpip\s+install\s+(great_expectations|dbt-|apache-airflow|freezegun)",
     "pip install (a warehouse/web-only dependency)"),
    (r"^\s*great_expectations\s+\w+", "great_expectations CLI invocation"),
]

# Model/agent routing fields — must not appear in front matter.
MODEL_FIELDS = ("model:", "agent-type:", "agent_type:", "subagent_type:")

_fail = 0
_pass = 0


def check(ok: bool, label: str, detail: str = "") -> None:
    global _fail, _pass
    if ok:
        _pass += 1
    else:
        _fail += 1
        print(f"  FAIL  {label}" + (f"\n        {detail}" if detail else ""))


def front_matter(text: str) -> str:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    return m.group(1) if m else ""


def main() -> int:
    print("Adopted skill contract check (attribution / model neutrality / upstream residue)")
    print("=" * 60)

    notice = (ROOT / "NOTICE.md").read_text(encoding="utf-8")
    check(UPSTREAM_REPO in notice,
          "NOTICE.md states the upstream repo",
          f"{UPSTREAM_REPO} is missing from NOTICE.md — required by MIT notice terms")
    check("Seth Hobson" in notice,
          "NOTICE.md states the upstream copyright holder",
          "MIT requires keeping the copyright notice")

    for skill, upstream_path in ADOPTED.items():
        print(f"\n[{skill}]")
        d = ROOT / "skills" / skill
        f = d / "SKILL.md"
        if not f.is_file():
            check(False, "SKILL.md exists", f"{f} is missing")
            continue
        check(True, "SKILL.md exists")

        text = f.read_text(encoding="utf-8")
        fm = front_matter(text)

        check(fm.strip() != "", "front matter is present")
        check(f"name: {skill}" in fm,
              "front matter name matches the folder name",
              f"folder={skill}, 'name: {skill}' missing from front matter")
        check("description:" in fm, "description is present")

        # 1. Attribution
        check(UPSTREAM_REPO in fm,
              "front matter states the upstream repo",
              "the upstream: line is missing — adaptation source untraceable")
        check(upstream_path in fm,
              "front matter states the upstream unit path",
              f"'{upstream_path}' missing from front matter")
        check(upstream_path in notice,
              "NOTICE.md's table lists this skill's upstream unit",
              f"'{upstream_path}' missing from NOTICE.md")
        check(skill in notice,
              "NOTICE.md's table lists this skill's name")
        check("license:" in fm, "license is declared",
              "NOTICE.md states that SKILL.md's license declaration takes precedence")

        # 2. Model neutrality
        for field in MODEL_FIELDS:
            check(field not in fm,
                  f"front matter has no '{field}' (model-neutral)",
                  f"an upstream routing field '{field}' rode along")

        # 3. Upstream residue — only catches use (import/call/install)
        for pattern, label in VENDOR_USAGE:
            hit = re.search(pattern, text, re.M)
            check(hit is None,
                  f"does not use an upstream-only dependency: {label}",
                  f"found '{hit.group(0).strip()}' — this regressed from adapting back "
                  f"into vendoring" if hit else "")

        # Routing wiring: this skill is only reachable if §0 actually points to it
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        sec = re.search(r"^## 0\. Routing.*?(?=^## 1\.)", agents, re.S | re.M)
        check(sec is not None and f"`{skill}`" in sec.group(0),
              "AGENTS.md §0's routing table points to this skill",
              "if it's not in the table, an agent has no path to choosing this skill")

    print("\n" + "=" * 60)
    if _fail:
        print(f"FAIL — pass {_pass} / fail {_fail}")
        return 1
    print(f"ALL PASS — {_pass} checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
