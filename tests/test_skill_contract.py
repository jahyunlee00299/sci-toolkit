#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Every SKILL.md must satisfy the Agent Skills structural contract.

Why this exists
---------------
Measured 2026-09-03 against the upstream contract (K-Dense-AI/scientific-agent-
skills `tests/_meta/test_repo_contract.py` + `skills-ref validate`): 8 violations
in 37 skills. One was a real defect — paper-extract kept ten Korean trigger
phrases under a top-level `triggers:` key. The router reads only
`description`, so none of them could ever fire, and nothing in this repo
noticed because nothing checked the frontmatter shape.

The contract (each rule is a measured failure mode, not taste)
----------------------------------------------------------------
  frontmatter      present, parses as YAML, closed key set
                   {name, description, license, allowed-tools, metadata, compatibility}
                   — an unknown key is silently ignored by every harness, so
                   anything placed there (triggers, version) is dead
  name             equals the folder name (install/routing use the folder)
  description      present, non-empty, <= 1024 chars once whitespace-collapsed
                   (spec limit; a longer one is truncated by some harnesses)
  body length      <= 500 lines, advisory for the files grandfathered in
                   tests/test_skill_sizes.py (same three files; that gate holds
                   the byte ratchet, this one only reports)
  local links      every `[text](relative/path)` outside code spans resolves
  scripts          every scripts/*.py compiles (py_compile)
  bytecode         no tracked *.pyc / __pycache__ under skills/

Two groups: `repo` runs the contract on the live tree; `synth` pins each rule
on a throwaway skill folder, both directions (must-fail / must-pass).

Run: python tests/test_skill_contract.py
"""
from __future__ import annotations

import py_compile
import re
import subprocess
import sys
import tempfile
from pathlib import Path

if sys.platform == "win32":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

ROOT = Path(__file__).resolve().parent.parent

ALLOWED_KEYS = {"name", "description", "license", "allowed-tools", "metadata", "compatibility"}
MAX_DESCRIPTION = 1024
MAX_BODY_LINES = 500
# Same files as tests/test_skill_sizes.py GRANDFATHERED: body length is advisory there.
BODY_ADVISORY = {"avoid-ai-writing", "journal-presentation-maker", "literature-review"}

_FM = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n", re.S)
_TOP_KEY = re.compile(r"^([A-Za-z][\w-]*):", re.M)
_LINK = re.compile(r"\[[^\]]*\]\((?!https?://|mailto:|#)([^)\s]+)\)")
_CODE = re.compile(r"`[^`\n]*`")

try:
    import yaml  # type: ignore
except ImportError:  # the contract still runs; YAML parse rule degrades to key scan
    yaml = None


def check_skill(skill_dir: Path) -> list[str]:
    """Return the list of contract violations for one skill folder (empty = clean)."""
    out: list[str] = []
    md = skill_dir / "SKILL.md"
    if not md.is_file():
        return ["no SKILL.md"]
    text = md.read_text(encoding="utf-8", errors="replace")
    m = _FM.match(text)
    if not m:
        return ["no frontmatter block (--- ... ---) at the top"]
    fm, body = m.group(1), text[m.end():]

    keys = _TOP_KEY.findall(fm)
    extra = sorted(set(keys) - ALLOWED_KEYS)
    if extra:
        out.append(f"non-spec frontmatter key(s) {extra} — a harness ignores them, so what they carry is dead "
                   f"(triggers belong in description:, version under metadata:)")
    data = None
    if yaml is not None:
        try:
            data = yaml.safe_load(fm)
        except Exception as exc:  # noqa: BLE001
            out.append(f"frontmatter is not valid YAML: {str(exc).splitlines()[0][:120]}")
    if isinstance(data, dict):
        name = str(data.get("name", "")).strip()
        desc = data.get("description")
    else:
        nm = re.search(r"^name:\s*(.+)$", fm, re.M)
        name = nm.group(1).strip().strip("\"'") if nm else ""
        dm = re.search(r"^description:\s*(.*?)(?=^[A-Za-z][\w-]*:|\Z)", fm, re.S | re.M)
        desc = dm.group(1) if dm else None
    if name != skill_dir.name:
        out.append(f"name {name!r} != folder {skill_dir.name!r}")
    if not desc or not str(desc).strip():
        out.append("description missing or empty")
    else:
        n = len(re.sub(r"\s+", " ", str(desc)).strip())
        if n > MAX_DESCRIPTION:
            out.append(f"description {n} chars > {MAX_DESCRIPTION} (spec limit)")

    n_lines = len(body.splitlines())
    if n_lines > MAX_BODY_LINES and skill_dir.name not in BODY_ADVISORY:
        out.append(f"body {n_lines} lines > {MAX_BODY_LINES} — move long material into references/")

    for link in _LINK.findall(_CODE.sub("", body)):
        target = link.split("#", 1)[0]
        if target and not (skill_dir / target).exists():
            out.append(f"local link does not resolve: {link}")

    for py in sorted(skill_dir.glob("scripts/*.py")):
        try:
            py_compile.compile(str(py), doraise=True, cfile=None)
        except py_compile.PyCompileError as exc:
            out.append(f"{py.relative_to(skill_dir).as_posix()} does not compile: {str(exc).splitlines()[-1][:100]}")
    return out


def tracked_bytecode(root: Path) -> list[str]:
    try:
        files = subprocess.run(["git", "-C", str(root), "ls-files", "skills"],
                               capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.split()
    except OSError:
        return []
    return [f for f in files if f.endswith(".pyc") or "__pycache__" in f]


_results: list[tuple[bool, str]] = []


def check(name: str, cond: bool, note: str = "") -> None:
    _results.append((cond, name))
    tag = "[OK]  " if cond else "[FAIL]"
    print(f"  {tag} {name}" + (f"  {note}" if note and not cond else ""))


# --------------------------------------------------------------------------
print("== repo: every skill against the contract" + ("" if yaml else "  (PyYAML absent: key-scan mode)"))
skills = sorted(p for p in (ROOT / "skills").iterdir() if p.is_dir())
check("skills/ has folders", bool(skills))
advisory: list[str] = []
for sd in skills:
    v = check_skill(sd)
    check(f"{sd.name}", not v, "; ".join(v))
    n = len((sd / "SKILL.md").read_text(encoding="utf-8", errors="replace").splitlines()) if (sd / "SKILL.md").is_file() else 0
    if sd.name in BODY_ADVISORY and n > MAX_BODY_LINES:
        advisory.append(f"{sd.name} ({n} lines)")
bc = tracked_bytecode(ROOT)
check("no tracked bytecode under skills/", not bc, str(bc[:5]))
if advisory:
    print("  [WARN] body > 500 lines, grandfathered (byte ratchet in test_skill_sizes.py): " + ", ".join(advisory))

# --------------------------------------------------------------------------
print("\n== synth: each rule, both directions")


def make(tmp: Path, name: str, fm: str, body: str = "# X\n", scripts: dict[str, str] | None = None) -> Path:
    d = tmp / name
    if d.exists():
        import shutil
        shutil.rmtree(d)
    (d / "scripts").mkdir(parents=True)
    (d / "SKILL.md").write_text(f"---\n{fm}\n---\n{body}", encoding="utf-8")
    for fn, src in (scripts or {}).items():
        (d / "scripts" / fn).write_text(src, encoding="utf-8")
    return d


with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    ok = make(tmp, "good-skill", "name: good-skill\ndescription: Does a thing. 한국어 트리거 — 좋은 일.\nmetadata:\n  version: '1.0'\n",
              "# Good\n\nSee [ref](references/a.md).\n", {"tool.py": "print('hi')\n"})
    (ok / "references").mkdir(); (ok / "references" / "a.md").write_text("x", encoding="utf-8")
    check("clean skill -> no violations", check_skill(ok) == [], str(check_skill(ok)))

    v = check_skill(make(tmp, "trig", "name: trig\ndescription: d\ntriggers:\n  - '논문에서 테이블 추출'\n"))
    check("top-level triggers: -> non-spec key violation", any("non-spec" in x and "triggers" in x for x in v), str(v))
    v = check_skill(make(tmp, "ver", "name: ver\ndescription: d\nversion: 1.2.3\n"))
    check("top-level version: -> non-spec key violation", any("non-spec" in x for x in v), str(v))
    v = check_skill(make(tmp, "meta-ok", "name: meta-ok\ndescription: d\nmetadata:\n  version: 1.2.3\n  triggers: [a, b]\n"))
    check("keys nested under metadata: are allowed", v == [], str(v))
    v = check_skill(make(tmp, "wrong-name", "name: other\ndescription: d\n"))
    check("name != folder -> violation", any("!= folder" in x for x in v), str(v))
    v = check_skill(make(tmp, "nodesc", "name: nodesc\n"))
    check("missing description -> violation", any("description missing" in x for x in v), str(v))
    v = check_skill(make(tmp, "longdesc", "name: longdesc\ndescription: >-\n  " + ("word " * 300) + "\n"))
    check("description > 1024 chars -> violation", any("> 1024" in x for x in v), str(v))
    v = check_skill(make(tmp, "exact", "name: exact\ndescription: " + ("x" * 1024) + "\n"))
    check("description exactly 1024 -> ok", v == [], str(v))
    v = check_skill(make(tmp, "longbody", "name: longbody\ndescription: d\n", "# L\n" + "line\n" * 501))
    check("body > 500 lines -> violation (non-grandfathered)", any("> 500" in x for x in v), str(v))
    v = check_skill(make(tmp, "badlink", "name: badlink\ndescription: d\n", "# B\n[x](references/missing.md)\n"))
    check("dangling local link -> violation", any("does not resolve" in x for x in v), str(v))
    v = check_skill(make(tmp, "codelink", "name: codelink\ndescription: d\n", "# C\nuse `- [label](url) — text` form\n"))
    check("link inside a code span is ignored", v == [], str(v))
    v = check_skill(make(tmp, "extlink", "name: extlink\ndescription: d\n", "# E\n[x](https://example.org) [y](#anchor)\n"))
    check("http and #anchor links are ignored", v == [], str(v))
    v = check_skill(make(tmp, "badpy", "name: badpy\ndescription: d\n", scripts={"broken.py": "def (:\n"}))
    check("non-compiling script -> violation", any("does not compile" in x for x in v), str(v))
    v = check_skill(make(tmp, "nofm", "", ""))
    (tmp / "nofm" / "SKILL.md").write_text("# no frontmatter\n", encoding="utf-8")
    check("missing frontmatter -> violation", any("no frontmatter" in x for x in check_skill(tmp / "nofm")))
    check("missing SKILL.md -> violation", check_skill(tmp / "ghost") == ["no SKILL.md"])

# --------------------------------------------------------------------------
n_fail = sum(1 for ok, _ in _results if not ok)
print(f"\nSUMMARY: {len(_results) - n_fail} passed, {n_fail} failed; {len(skills)} skills checked, "
      f"{len(advisory)} body-length advisories")
sys.exit(1 if n_fail else 0)
