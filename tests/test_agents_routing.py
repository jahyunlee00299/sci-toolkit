#!/usr/bin/env python3
"""Checks that everything AGENTS.md §0's routing table points to actually exists.

§0 is the table an agent reads and follows first. If it names a skill or
script that isn't here, the agent either fails trying to use a tool that
doesn't exist or — worse — plausibly fabricates one. This is checked
separately because it's the part of the docs that must never be the first
thing to break.

Run:
    python tests/test_agents_routing.py           # exit 0 = pass
    python tests/test_agents_routing.py --verbose
"""
import argparse
import io
import os
import re
import sys

# Windows' default console is cp949 and dies on Korean/symbol output. Force UTF-8.
# Use reconfigure instead of TextIOWrapper — the wrapper takes ownership of the
# underlying stream, so once it's GC'd after import, it closes the caller's
# stdout too (measured).
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENTS = os.path.join(ROOT, "AGENTS.md")
SKILLS_DIR = os.path.join(ROOT, "skills")

# Things that appear as concept/output names, not files — not checked
NOT_A_PATH = {
    "refs_report.json",          # an artifact ref_fetch.py produces
    "discrepancies",             # a field name inside a report
    "not_found",
    "PROJECT_STRUCTURE.md",
}
# Names of runners the user installs themselves, not skills in this repo.
# §0 calls these directly as gate commands, so they match the skill-name
# pattern (lowercase + hyphens) but have no reason to live under `skills/`.
# When adding to this set, confirm it's really an external CLI — dropping a
# misspelled skill name in here would defeat this check.
RUNNER_COMMANDS = {"pytest"}
# A path containing a placeholder can't be checked against a real file
PLACEHOLDER_RE = re.compile(r"<[^>]+>")

# Anthropic-owned skills this package depends on but cannot redistribute.
# §0 pointing at these is an external dependency, not a dead reference — it
# works as-is if present in the user's environment, and docs/12 guides them
# if not. Keep this in sync with doctor.py's EXTERNAL_SKILLS list (editing
# only one side lets them drift apart).
EXTERNAL_SKILLS = {"docx", "pdf", "pptx", "xlsx"}


def resolve(token, skills):
    """Check whether the token points at a real file. Returns its path if so, else None."""
    cand = token.strip()
    # "python x.py --flag" / "x.py --count-only" -> keep only the actual path part
    parts = [p for p in cand.split() if not p.startswith("-")]
    parts = [p for p in parts if p not in ("python", "python3", "bash", "sh")]
    if not parts:
        return "skip"
    cand = parts[0]

    if cand in NOT_A_PATH:
        return "skip"
    if PLACEHOLDER_RE.search(cand):
        return "skip"
    # the external skill itself (`docx`) or a path inside it (`docx/scripts/x.py`)
    if cand in EXTERNAL_SKILLS or cand.split("/")[0] in EXTERNAL_SKILLS:
        return "skip"

    tries = [os.path.join(ROOT, cand)]
    # if it starts with a skill name like `docx/scripts/x.py`, look under skills/
    head = cand.split("/")[0]
    if head in skills:
        tries.append(os.path.join(SKILLS_DIR, cand))
    # a relative path inside a skill like `scripts/x.py` — look under each skill
    if not cand.startswith(("skills/", "scripts/", "tests/", "config/", "install/")):
        tries += [os.path.join(SKILLS_DIR, s, cand) for s in skills]
    elif cand.startswith("scripts/"):
        tries += [os.path.join(SKILLS_DIR, s, cand) for s in skills]

    for t in tries:
        if os.path.exists(t):
            return os.path.relpath(t, ROOT)
    return None


def main():
    ap = argparse.ArgumentParser(description="Checks AGENTS.md §0's routing table")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if not os.path.isfile(AGENTS):
        print(f"Error: AGENTS.md is missing — {AGENTS}")
        return 2
    text = open(AGENTS, encoding="utf-8").read()

    m = re.search(r"^## 0\. Routing.*?(?=^## 1\.)", text, re.S | re.M)
    if not m:
        print("FAIL — AGENTS.md has no '## 0. Routing' section. "
              "This table is the agent's entry point, so it must exist.")
        return 1
    section = m.group(0)

    skills = set(os.listdir(SKILLS_DIR))
    tokens = sorted(set(re.findall(r"`([^`]+)`", section)))

    dead_files, dead_skills, ok = [], [], []
    for tok in tokens:
        t = tok.strip()
        looks_like_path = t.endswith((".py", ".json", ".md")) or "/" in t
        if looks_like_path:
            r = resolve(t, skills)
            if r is None:
                dead_files.append(t)
            elif r != "skip":
                ok.append((t, r))
        elif re.fullmatch(r"[a-z][a-z0-9-]{3,40}", t):
            if t in skills:
                ok.append((t, f"skills/{t}"))
            elif t in EXTERNAL_SKILLS:
                ok.append((t, "external (Anthropic-owned, see docs/12)"))
            elif t in RUNNER_COMMANDS:
                ok.append((t, "external runner (user-installed CLI)"))
            elif t not in NOT_A_PATH:
                dead_skills.append(t)

    print(f"§0 routing table: {len(tokens)} token(s), "
          f"{len(ok) + len(dead_files) + len(dead_skills)} checked against reality")
    if args.verbose:
        for t, r in ok:
            print(f"   OK  {t}  ->  {r}")

    fails = len(dead_files) + len(dead_skills)
    if dead_files:
        print(f"\n=== {len(dead_files)} nonexistent file(s) ===")
        for t in dead_files:
            print(f"   {t}")
    if dead_skills:
        print(f"\n=== {len(dead_skills)} nonexistent skill(s) ===")
        for t in dead_skills:
            print(f"   {t}")

    if fails:
        print(f"\nFAIL — §0 points at {fails} thing(s) that don't exist. "
              f"Agents follow this table literally, so fix it immediately.")
        return 1
    print("\nALL PASS — every skill/script §0 names actually exists")
    return 0


if __name__ == "__main__":
    sys.exit(main())
