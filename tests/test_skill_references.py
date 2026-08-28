#!/usr/bin/env python3
"""Checks that what a skill's docs point at actually exists.

The most common failure in a distribution isn't a code bug — it's a **dead
reference**. A skill's doc says "run `scripts/foo.py`" / "use the `bar`
skill," but if that file or skill isn't in the package, the user fails
following the instruction. This is a different axis from the integrity
(hashes)/secrets that doctor.py catches, so it needs its own check.

Run:
    python tests/test_skill_references.py           # exit 0 = pass
    python tests/test_skill_references.py --verbose # also print every reference checked

What is checked:
1. In-skill-folder file references (`scripts/x.py`, `references/y.md`, `assets/z.json`)
   - Compared **case-sensitively too**. This catches a mismatch like
     `REFERENCE.md` vs `reference.md` that passes on Windows but breaks on
     Linux/WSL.
   - A line that also mentions `<other-skill>` is treated as a cross-skill
     reference and is also looked up in that skill's folder.
2. References to other skill names (``foo`` skill / `foo` skill)
   - History notes marked `deprecated/` are excluded (they record a name that
     was merged away and no longer exists).
"""
import argparse
import io
import json
import os
import re
import sys

# Windows' default console is cp949, which dies on Korean/symbol output. Force UTF-8.
# reconfigure instead of TextIOWrapper — a wrapper takes ownership of the
# underlying stream, so once it's GC'd after import it closes the caller's
# stdout too (measured).
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_DIR = os.path.join(ROOT, "skills")

# scripts/foo.py, references/bar.md, assets/.env.example ...
FILE_REF_RE = re.compile(
    r"(?<![\w/.-])((?:scripts|references|assets|templates)/[A-Za-z0-9_./-]+)")
# `foo` skill / `foo` 스킬 / **foo** skill
# NOTE: this regex's literal "스킬" is Korean-language detection logic (it
# matches the Korean word for "skill" appearing in prose across the repo's
# docs) — do not translate it. See CLAUDE.md's Repository Language section,
# category 2.
SKILL_REF_RE = re.compile(
    r"[`*]{1,2}([a-z][a-z0-9-]{3,40})[`*]{1,2}\s*(?:skill|스킬)"
    r"|(?:skill|스킬)\s*[`*]{1,2}([a-z][a-z0-9-]{3,40})[`*]{1,2}")

# Also catch a script name that appears in prose without backticks.
# A filename written without code formatting, like "see body_typo_lint.py for
# the enforcement side," slips past both FILE_REF_RE above (which requires a
# path prefix) and the backtick-based scan — 2 tools that don't actually
# exist were left sitting in the docs this way (found 2026-07-23).
BARE_SCRIPT_RE = re.compile(r"(?<![\w/.-])([a-z][a-z0-9_]{3,60}\.py)\b")

# A list item in an "Integration with Other Skills"-style section — `- **foo**: description`.
# SKILL_REF_RE requires the word "skill"/"스킬" to follow, but in a list like
# this the section heading already says "Skills," so individual items don't
# repeat the word. That let 9 undistributed skills slip past the check
# entirely (measured 260807: pydeseq2, scanpy, anndata, scientific-slides,
# latex-posters, brand-guidelines, internal-comms, plus matplotlib and
# seaborn, which aren't skills at all).
#
# The judgment applies **only inside a section whose heading says it's a
# skill list.** Treating every `**foo**` in the whole document as a skill
# would also catch JSON field names, matplotlib arguments, and mermaid
# keywords — 383 candidates surfaced that way, which is noise, not a check.
# NOTE: this regex's literal "스킬" is the same Korean-detection case as
# SKILL_REF_RE above — do not translate it.
SKILL_SECTION_RE = re.compile(r"^#{1,6}\s+.*\b(skills?|스킬)\b", re.I)
SKILL_LIST_ITEM_RE = re.compile(
    r"^\s*[-*]\s*[`*]{1,2}([a-z][a-z0-9-]{2,40})[`*]{1,2}\s*[:：]")

TEXT_SUFFIXES = (".md", ".txt")
SKIP_DIRS = {"__pycache__", ".git", "node_modules"}

# Script names it's fine not to have in the package — an example the user
# would create in their own project, an internal file of an external
# library, or a name close to a common noun.
# When adding an entry here, always write down "why it's OK to not have this
# file." Adding one with no reason turns this check into a rubber stamp.
BARE_SCRIPT_ALLOWLIST = {
    # Example script names a user would make in their own environment
    "my_analysis.py", "my_job.py",
    "script.py",            # publication-figures: describes the "data.csv + script.py + figure.png" output convention
    "example_module.py",    # code-quality example
    # Python idiomatic/generic names (don't point at a specific file)
    "setup.py", "app.py", "main.py", "train.py", "run.py", "test.py",
    # A directory tree describing an external library's internal structure
    "converter.py",         # internal structure diagram of the markitdown package (not our file)
    # An optional helper the user builds if they want ("pair it if you have one" style wording)
    "manuscript_workdir.py",
    # ── Files inside Anthropic-owned document skills (see EXTERNAL_SKILLS) ──
    # This package cannot redistribute those skills, so the files don't
    # exist here. The "here's how to use that skill" knowledge is still
    # valid though, so the wording isn't deleted. It works as-is if the
    # user's environment has the skill, and docs/12 guides them if not.
    "incremental_edit.py",          # docx: ZIP-integrity-preserving edit session
    "docx_preflight.py",            # docx: structural validation
    "word_validate.py",             # docx: Word COM ground-truth verification
    "comment.py",                   # docx: comment insertion
    "inject_comments_from_csv.py",  # docx: bulk CSV -> comment insertion
    "pack.py",                      # docx/pptx: OOXML repacking
    "unpack.py",                    # docx/pptx: OOXML unpacking
    "recalc.py",                    # xlsx: formula recalculation / error scan
}

# External skills this package depends on but cannot redistribute (Anthropic-owned).
# Being referenced by name is "an external dependency," not a dead reference
# — see the same EXTERNAL_SKILLS list in doctor.py. See docs/12.
EXTERNAL_SKILLS = {"docx", "pdf", "pptx", "xlsx"}

# ── Skill-name checks in documents outside skills/ (root *.md, docs/) ──────
#
# This check long only walked `skills/`. But the place where skills actually
# get added and removed by edits is README/QUICKSTART/docs. Measured
# 260807: reviving two undistributed skills in the README table still showed
# `ALL PASS`, and 42% (111) of skill-name references had never once been
# checked (README 27, AGENTS 25, docs 28, QUICKSTART 12, ...).
#
# CHANGELOG is excluded — recording the name of a removed skill is that
# file's job. AGENTS.md's §0 is already cross-checked by
# test_agents_routing.py, but wording outside the table goes unnoticed, so
# it's covered here too.
OUTSIDE_SKIP_FILES = {"CHANGELOG.md"}

# Tokens shaped like a skill name (kebab-case) that are not actually skills.
# Preset names are read from config/catalog.json and auto-allowed, so they
# aren't listed here.
OUTSIDE_ALLOWLIST = {
    # pip package / external library
    "python-docx", "scikit-image", "sci-toolkit", "claude-code",
    # connector CLI subcommands (usage examples in docs/07, 08)
    "list-dbs", "add-row", "add-task", "add-comment", "add-subtask",
    "add-event",  # calendar_connector (docs/05 §4-4)
    "list-tasks", "get-page", "add-page",
    # placeholder examples inside docs
    "key-here", "your-token", "project-id",
}
KEBAB_TOKEN_RE = re.compile(r"[`*]{1,2}([a-z][a-z0-9]*(?:-[a-z0-9]+)+)[`*]{1,2}")


def collect(skill_dir):
    """All files inside a skill folder, as a set of relative paths."""
    out = set()
    for dp, dns, fns in os.walk(skill_dir):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for f in fns:
            out.add(os.path.relpath(os.path.join(dp, f), skill_dir).replace("\\", "/"))
    return out


def main():
    ap = argparse.ArgumentParser(description="Check for dead references in skill docs")
    ap.add_argument("--verbose", action="store_true", help="Also print every reference checked")
    args = ap.parse_args()

    if not os.path.isdir(SKILLS_DIR):
        print(f"Error: skills/ folder not found — {SKILLS_DIR}")
        return 2

    skills = sorted(d for d in os.listdir(SKILLS_DIR)
                    if os.path.isdir(os.path.join(SKILLS_DIR, d)))
    skillset = set(skills)
    have = {s: collect(os.path.join(SKILLS_DIR, s)) for s in skills}

    # Every .py filename (no path) across the whole package — to cross-check
    # script names written in prose. Must also include what's outside the
    # skill folders (scripts/, tests/, install/, root).
    all_py_names = set()
    for dp, dns, fns in os.walk(ROOT):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for f in fns:
            if f.endswith(".py"):
                all_py_names.add(f)

    dead_files, dead_skills, case_only, dead_bare = [], [], [], []
    checked = 0

    for s in skills:
        root = os.path.join(SKILLS_DIR, s)
        lower_map = {h.lower(): h for h in have[s]}
        for dp, dns, fns in os.walk(root):
            dns[:] = [d for d in dns if d not in SKIP_DIRS]
            for f in fns:
                if not f.lower().endswith(TEXT_SUFFIXES):
                    continue
                p = os.path.join(dp, f)
                srcrel = os.path.relpath(p, root).replace("\\", "/")
                try:
                    lines = open(p, encoding="utf-8", errors="ignore").read().splitlines()
                except OSError:
                    continue
                in_skill_section = False
                for i, line in enumerate(lines, 1):
                    # --- an item in a skill-list section (`- **foo**: description`) ---
                    if line.startswith("#"):
                        in_skill_section = bool(SKILL_SECTION_RE.match(line))
                    elif in_skill_section:
                        m = SKILL_LIST_ITEM_RE.match(line)
                        if m:
                            name = m.group(1)
                            if (name != s and name not in EXTERNAL_SKILLS
                                    and "deprecated" not in line.lower()):
                                checked += 1
                                if name not in skillset:
                                    dead_skills.append(
                                        (s, srcrel, i, name, line.strip()[:90]))

                    # --- a script name written in prose without backticks ---
                    for m in BARE_SCRIPT_RE.finditer(line):
                        fname = m.group(1)
                        if fname in BARE_SCRIPT_ALLOWLIST:
                            continue
                        checked += 1
                        if fname not in all_py_names:
                            dead_bare.append((s, srcrel, i, fname, line.strip()[:90]))

                    # --- file reference ---
                    for m in FILE_REF_RE.finditer(line):
                        ref = m.group(1)
                        if "." not in os.path.basename(ref):
                            continue          # treat no-extension as a directory mention
                        checked += 1
                        if ref in have[s]:
                            continue
                        # Pointing at a shared tool in the distribution root
                        # (e.g. scripts/ref_fetch.py) is also normal. It's
                        # common for a skill's docs to use a root-level tool
                        # — interpreting this as "only scripts/ inside the
                        # skill folder" would force docs into an awkward
                        # relative path like ../../scripts/.
                        if os.path.isfile(os.path.join(ROOT, ref)):
                            continue
                        # If the surrounding context mentions another skill,
                        # treat it as a cross-skill reference. A sentence
                        # commonly wraps so the skill name and filename land
                        # on different lines, so judge over a +-2-line window
                        # rather than a single line.
                        window = "\n".join(lines[max(0, i - 3):i + 2])
                        others = [o for o in skillset if o != s and o in window]
                        if any(ref in have[o] for o in others):
                            continue
                        alt = lower_map.get(ref.lower())
                        if alt:
                            case_only.append((s, srcrel, i, ref, alt))
                        else:
                            dead_files.append((s, srcrel, i, ref))
                    # --- skill-name reference ---
                    if "deprecated" in line.lower():
                        continue
                    for m in SKILL_REF_RE.finditer(line):
                        name = m.group(1) or m.group(2)
                        if not name or name == s:
                            continue
                        checked += 1
                        if name in EXTERNAL_SKILLS:
                            # A skill deliberately absent because it can't be redistributed. The reference is valid.
                            continue
                        if name not in skillset:
                            dead_skills.append((s, srcrel, i, name, line.strip()[:90]))

    # ── skill-name references in documents outside skills/ ──
    dead_outside = []
    try:
        catalog = json.loads(
            open(os.path.join(ROOT, "config", "catalog.json"),
                 encoding="utf-8").read())
        allowed = set(OUTSIDE_ALLOWLIST) | set(catalog.get("presets", {}))
        allowed |= set(catalog.get("connectors", {}))
        allowed |= set(catalog.get("categories", {}))
    except (OSError, ValueError):
        allowed = set(OUTSIDE_ALLOWLIST)

    outside_files = [os.path.join(ROOT, f) for f in sorted(os.listdir(ROOT))
                     if f.lower().endswith(".md") and f not in OUTSIDE_SKIP_FILES]
    docs_dir = os.path.join(ROOT, "docs")
    if os.path.isdir(docs_dir):
        outside_files += [os.path.join(docs_dir, f)
                          for f in sorted(os.listdir(docs_dir))
                          if f.lower().endswith(".md")]

    for p in outside_files:
        rel = os.path.relpath(p, ROOT).replace("\\", "/")
        try:
            lines = open(p, encoding="utf-8", errors="ignore").read().splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            if "deprecated" in line.lower():
                continue
            for m in KEBAB_TOKEN_RE.finditer(line):
                name = m.group(1)
                if name in allowed:
                    continue          # a token already judged to not be a skill
                checked += 1
                if name in skillset or name in EXTERNAL_SKILLS:
                    continue
                dead_outside.append((rel, i, name, line.strip()[:90]))

    print(f"Checked {checked} reference(s) across {len(skills)} skill(s)")

    fails = 0
    if case_only:
        fails += len(case_only)
        print(f"\n=== {len(case_only)} case mismatch(es) "
              f"(passes on Windows, breaks on Linux/WSL) ===")
        for s, src, ln, ref, alt in case_only:
            print(f"  {s}/{src}:{ln}  {ref}  ->  actual file is {alt}")
    if dead_files:
        fails += len(dead_files)
        print(f"\n=== {len(dead_files)} reference(s) to a nonexistent file ===")
        for s, src, ln, ref in dead_files:
            print(f"  {s}/{src}:{ln}  {ref}")
    if dead_skills:
        fails += len(dead_skills)
        print(f"\n=== {len(dead_skills)} reference(s) to a skill not in the distribution ===")
        for s, src, ln, name, ctx in dead_skills:
            print(f"  {s}/{src}:{ln}  '{name}'")
            print(f"      {ctx}")
    if dead_outside:
        fails += len(dead_outside)
        print(f"\n=== {len(dead_outside)} document(s) outside skills/ pointing at a skill that doesn't exist ===")
        print("    (README/QUICKSTART/docs — a spot where a skill was removed but the doc wasn't updated)")
        for src, ln, name, ctx in dead_outside:
            print(f"  {src}:{ln}  '{name}'")
            print(f"      {ctx}")
    if dead_bare:
        fails += len(dead_bare)
        print(f"\n=== {len(dead_bare)} mention(s) in prose of a script that doesn't exist ===")
        print("    (written without backticks, so they slipped past the path check)")
        for s, src, ln, name, ctx in dead_bare:
            print(f"  {s}/{src}:{ln}  {name}")
            print(f"      {ctx}")

    if fails:
        print(f"\nFAIL — {fails} dead reference(s). Following these instructions would fail for a user.")
        return 1
    print("\nALL PASS — every reference exists")
    return 0


if __name__ == "__main__":
    sys.exit(main())
