#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Skill drift check — is the toolkit's copy of a shared skill behind the authoring copy?

Why this exists
---------------
Most skills under ``skills/`` are English distribution copies of skills that are
authored elsewhere (the maintainer's runtime skill directory, ``~/.claude/skills``
by default). Measured 2026-09-02: 22 of the 29 shared skills differed between
the two trees, and the differences were content, not path scrubbing — the
2026-08-28 English translation landed only in the toolkit, while a later
publication-figures change landed only in the runtime. Two copies with no
declared direction is how a fix gets lost.

The rule this enforces
----------------------
* The **runtime copy is the authoring SSOT** for a shared skill. Content changes
  go there first and are then ported (translated, scrubbed) into ``skills/``.
* The **toolkit copy is downstream**. Editing a shared skill here first is
  allowed only for translation / sanitization; port anything else back.
* A shared skill whose runtime copy changed AFTER the toolkit copy was last
  touched is **lagging** — that is the failure this script reports.

What it does
------------
For every ``skills/<name>/SKILL.md`` that also exists as ``<runtime>/<name>/SKILL.md``:
  * compares the two files (CRLF-insensitive) → SAME / DRIFT
  * asks git on both sides for the last commit date touching that skill
  * flags LAGGING when they differ and the runtime date is newer

Exit codes: 0 = no lagging skill (or no runtime tree found — a distribution user
has none, and that is fine); 1 = at least one lagging skill; 2 = bad arguments.

Usage
-----
    python scripts/skill_drift.py                   # runtime = ~/.claude/skills
    python scripts/skill_drift.py --runtime <dir>   # another authoring tree
    python scripts/skill_drift.py --json            # machine-readable
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RUNTIME = Path.home() / ".claude" / "skills"


def _norm(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")


def _git_last_date(path: Path):
    """Last commit date (YYYY-MM-DD) touching *path* in its own repo, or None."""
    try:
        real = path.resolve()
        top = subprocess.run(
            ["git", "-C", str(real.parent), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20,
        )
        if top.returncode != 0:
            return None
        top_path = Path(top.stdout.strip())
        rel = real.relative_to(top_path)
        out = subprocess.run(
            ["git", "-C", str(top_path), "log", "-1", "--format=%cs", "--", str(rel)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20,
        )
        return out.stdout.strip() or None
    except Exception:
        return None


#: Sub-trees compared file by file in addition to SKILL.md. Measured 2026-09-02:
#: get-available-resources/scripts/detect_resources.py differed by 2,050 lines
#: (runtime 401, toolkit 1,767) for 26 days while this script, comparing only
#: SKILL.md, reported the skill as SAME. A skill is its scripts as much as its
#: prose.
COMPARED_SUBTREES = ("scripts", "references")
_SKIP_PARTS = {"__pycache__", ".pytest_cache", "downloads"}


def _files(skill_dir: Path):
    """{relative posix path: Path} for every file under the compared sub-trees."""
    out = {}
    for sub in COMPARED_SUBTREES:
        base = skill_dir / sub
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if p.is_file() and not (set(p.relative_to(skill_dir).parts) & _SKIP_PARTS) \
                    and p.suffix not in (".pyc",):
                out[p.relative_to(skill_dir).as_posix()] = p
    return out


def compare_files(toolkit_dir: Path, runtime_dir: Path) -> dict:
    """Per-file verdict: which compared files differ or exist on one side only."""
    t, r = _files(toolkit_dir), _files(runtime_dir)
    drift = sorted(k for k in t.keys() & r.keys() if _norm(t[k]) != _norm(r[k]))
    return {
        "files_compared": len(t.keys() & r.keys()),
        "files_drift": drift,
        "files_toolkit_only": sorted(t.keys() - r.keys()),
        "files_runtime_only": sorted(r.keys() - t.keys()),
    }


def compare(toolkit_skills: Path, runtime: Path):
    rows = []
    for skill_md in sorted(toolkit_skills.glob("*/SKILL.md")):
        name = skill_md.parent.name
        rt = runtime / name / "SKILL.md"
        if not rt.exists():
            rows.append({"skill": name, "status": "TOOLKIT-ONLY"})
            continue
        md_same = _norm(skill_md) == _norm(rt)
        files = compare_files(skill_md.parent, rt.parent)
        files_same = not (files["files_drift"] or files["files_toolkit_only"] or files["files_runtime_only"])
        same = md_same and files_same
        t_date = _git_last_date(skill_md.parent)
        r_date = _git_last_date(rt.parent)
        status = "SAME" if same else "DRIFT"
        lagging = (not same) and bool(t_date) and bool(r_date) and r_date > t_date
        if lagging:
            status = "LAGGING"
        rows.append({"skill": name, "status": status, "skill_md_same": md_same,
                     "toolkit_last": t_date, "runtime_last": r_date, **files})
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="toolkit vs runtime skill drift")
    ap.add_argument("--runtime", default=str(DEFAULT_RUNTIME),
                    help="authoring skill tree (default: ~/.claude/skills)")
    ap.add_argument("--toolkit", default=str(ROOT / "skills"),
                    help="toolkit skills dir (default: <repo>/skills)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    runtime = Path(args.runtime).expanduser()
    toolkit = Path(args.toolkit).expanduser()
    if not toolkit.is_dir():
        print(f"[skill_drift] toolkit skills dir not found: {toolkit}", file=sys.stderr)
        return 2
    if not runtime.is_dir():
        msg = {"runtime": str(runtime), "note": "no authoring tree here (distribution install) - nothing to compare"}
        print(json.dumps(msg) if args.json else f"[skill_drift] {msg['note']}: {runtime}")
        return 0

    rows = compare(toolkit, runtime)
    lag = [r for r in rows if r["status"] == "LAGGING"]
    if args.json:
        print(json.dumps({"rows": rows, "lagging": len(lag)}, ensure_ascii=False, indent=1))
    else:
        print(f"{'skill':32} {'status':13} toolkit_last  runtime_last  files (drift / toolkit-only / runtime-only)")
        for r in rows:
            files = ""
            if r["status"] != "TOOLKIT-ONLY":
                d, to, ro = len(r["files_drift"]), len(r["files_toolkit_only"]), len(r["files_runtime_only"])
                files = f"{d} / {to} / {ro}" if (d or to or ro) else "-"
                if not r.get("skill_md_same", True):
                    files = "SKILL.md + " + files
            print(f"{r['skill']:32} {r['status']:13} {r.get('toolkit_last') or '-':12}  "
                  f"{r.get('runtime_last') or '-':12}  {files}")
            for f in r.get("files_drift", [])[:6]:
                print(f"{'':32} {'':13}   drift: {f}")
            for f in r.get("files_runtime_only", [])[:6]:
                print(f"{'':32} {'':13}   runtime-only: {f}")
            for f in r.get("files_toolkit_only", [])[:6]:
                print(f"{'':32} {'':13}   toolkit-only: {f}")
        n = {s: sum(1 for r in rows if r["status"] == s) for s in ("SAME", "DRIFT", "LAGGING", "TOOLKIT-ONLY")}
        print(f"\nsummary: {n}")
        if lag:
            print("LAGGING = runtime copy changed after the toolkit copy; port the change into skills/ "
                  "(runtime is the authoring SSOT).")
    return 1 if lag else 0


if __name__ == "__main__":
    sys.exit(main())
