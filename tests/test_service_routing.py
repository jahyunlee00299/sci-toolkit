#!/usr/bin/env python3
"""Checks that when a document points at an external service or skill, the target actually exists.

Run: python tests/test_service_routing.py   (exit 0 = pass)

Why this file exists — two blind spots surfaced in the 260816 adversarial verification
--------------------------------------------------------------------------------------
This repository states a "REST connector instead of MCP" policy in several
places. But there was no mechanical check that the policy is actually
followed. It was actually broken in practice:

`skills/academic-term-rules/.prompt.md` instructed "write Notion pages like
this" without ever mentioning `notion_connector.py`. It had no occurrence of
the word MCP, so a plain string search missed it, and because the filename
starts with a dot, it also missed the `SKILL.md` glob. The silence itself —
never naming the connector — is what steers an agent toward whatever tool it
already has, which is MCP.

A second blind spot surfaced in the same pass. `test_skill_references.py` was
extended on 260807 to look at documents **outside** skills/, but the reverse
case — a document **inside** skills/ pointing at a skill that isn't actually
shipped — still had nobody looking at it. A dead skill reference is itself
another trigger for the same fallback.

Two checks
----------
A. Does a document that mentions a connector-backed service (mail, GitHub,
   Asana, Notion) **as an instruction** also name the connector script?
B. Does a document inside skills/ avoid pointing at a skill not in this repo?

A is prone to false positives (a service name also shows up for rendering
compatibility or as an example). So it's narrowed to "instruction" — only a
section whose heading names the service. A heading is the author declaring
"this document covers this service," which is distinct from a passing
mention.
"""
import json
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

# A service with a connector -> the script(s) a document covering that
# service must mention. Calendar/shared-sheet have no connector (a
# documented exception) so they aren't listed here.
CONNECTOR_SERVICES = {
    "notion": ("notion_connector.py", "notion_db_connector.py"),
    "asana": ("asana_connector.py",),
    "github": ("github_connector.py",),
}

# A service name in the heading doesn't always mean "access." "How does
# Mermaid render on GitHub" is about rendering compatibility, not an API
# call. So this doesn't judge by heading alone — it also checks **whether
# the section instructs an action**.
#
# If not one action verb is present, the section is descriptive, not
# instructive — an agent reading it has no reason to try connecting to the
# service, so it's fine not to name the connector there.
#
# Measured 260816: the first version only searched the body for action
# words and missed the actual violation. `.prompt.md` §11 has the heading
# "Notion Page **Writing** Rules" but its body says "use `<br>`", "must use
# public URLs" — neither the English "write" nor the Korean equivalent
# appeared in the body. Instructiveness often lives in the heading, so this
# checks heading + body together.
ACTION_WORDS = (
    # English — checks both imperative and gerund forms ("write" also covers "writing")
    "creat", "updat", "writ", "post", "upload", "append", "add ",
    "send", "fetch", "quer", "search", "sync", "log ", "publish",
    "must use", "forbidden", "rules",
    # Korean — these are the input alphabet for detecting instructive Korean
    # prose in scanned docs, not commentary; do not translate.
    "생성", "작성", "등록", "업로드", "추가", "전송", "조회", "검색",
    "동기화", "기록", "올린", "올려", "발행", "수정", "삭제", "규칙",
)

# A service name in the heading that is NOT 'access' — rendering
# compatibility, notation examples, etc. Keep this narrow: adding to it
# weakens the check.
HEADING_ALLOW = (
    "mermaid",        # "How does Mermaid render on GitHub / Notion"
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
print("\n[A] Does a section covering a connector-backed service also name the connector?")

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
            # Pass if the connector is mentioned anywhere in the file (not necessarily the same section).
            if any(s in text for s in scripts):
                continue
            # Does the heading + section body (up to the next heading) instruct an action?
            # If it's purely descriptive, the agent has no reason to access the service — not a violation.
            body = [line]
            for nxt in lines[i:]:
                if nxt.startswith("#"):
                    break
                body.append(nxt)
            body_low = "\n".join(body).lower()
            if not any(w in body_low for w in ACTION_WORDS):
                continue
            violations.append((rel(path), i, line.strip(), svc, scripts))

check("no connector-silence violations", not violations,
      f"{len(violations)} found")
for f, i, head, svc, scripts in violations:
    print(f"        {f}:{i}  {head!r}")
    print(f"          -> instructs {svc} access without naming {'/'.join(scripts)}.")
    print(f"          -> either name the connector, or drop the service name from the heading if it isn't an access instruction.")


# ─────────────────────────────────────────────────────────────
print("\n[B] Does a document inside skills/ avoid pointing at a skill that isn't shipped?")

shipped = {d for d in os.listdir(SKILLS_DIR)
           if os.path.isdir(os.path.join(SKILLS_DIR, d))}

# A skill can be legitimately referenced without having a directory here: the
# Anthropic-provided document skills (docx/xlsx/pdf/pptx) cannot be redistributed
# under their license, so the catalog carries them as `external: true` with
# size_kb 0 and docs/12 tells the user to install them into their own Claude Code
# environment. Those are "not bundled", not "does not exist" — pointing a document
# at `pptx` skill is correct guidance, and flagging it as a dead reference would
# push authors to delete accurate instructions. Measured 260923: journal-ppt's
# style_spec.md cites the `pptx` skill's QA conventions in 5 places and every one
# of them was reported dead. Read them from the catalog rather than hardcoding a
# list, so a future external skill is covered without editing this test.
try:
    with open(os.path.join(ROOT, "config", "catalog.json"), encoding="utf-8") as fh:
        _catalog = json.load(fh)
    shipped |= {name for name, meta in _catalog.get("skills", {}).items()
                if meta.get("external")}
except (OSError, ValueError) as exc:          # missing/corrupt catalog
    # Deliberately not silent: losing the catalog would silently re-flag every
    # external-skill reference, and a test that fails for the wrong reason is
    # worse than one that says why.
    print(f"        [warn] catalog unreadable ({exc}) — external skills not exempted")

# Don't grab every arbitrary kebab-case token — there are too many that
# merely look like a skill name in shape (`x-axis`, `margin-top`,
# `load-bearing`), and chasing that with an allowlist is a losing battle.
# Instead, this only catches **the grammar that names something as a
# skill**: the word skill/스킬 sitting right next to the name, or a
# Skill(...) call form. It only looks where the author explicitly said
# "this is a skill," so false positives are rare, and any miss errs safe.
# NOTE: the literal 스킬 (Korean for "skill") in this regex is detection
# input for scanning Korean-language docs, not commentary — do not translate it.
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

check("no dead skill references", not filtered, f"{len(filtered)} found")
for f, i, tok, line in filtered:
    print(f"        {f}:{i}  '{tok}' — not present in this repository")
    print(f"          {line[:100]}")
print(f"        (checked against {len(shipped)} shipped skill(s))")


# ─────────────────────────────────────────────────────────────
print("\n" + "-" * 60)
print(f"PASS {_pass} / FAIL {_fail}")
if _fail:
    print("\nFAIL — a document points at something that doesn't exist.")
    print("When a target is empty, an agent falls back to whatever other tool it has")
    print("(= MCP instead of a connector). Fix the reference, or reword it if it isn't an instruction.")
    sys.exit(1)
print("ALL PASS — every service/skill reference points at something real")
sys.exit(0)
