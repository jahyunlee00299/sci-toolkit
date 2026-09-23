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

Intended differences
--------------------
Not every difference is a port waiting to happen. Measured 2026-09-24: of 27
drifting skills only 3 were real ports; the rest were license terms, runtime-only
paths, environment-bound scripts, or the toolkit being AHEAD. Without a place to
record that judgment, every session re-reviews the same 27 and a bulk sync would
break the distribution.

``config/skill-drift-intended.json`` records it — one entry per skill, each with a
``reason`` and the fingerprints of BOTH copies as they were when the judgment was
made. The declaration covers exactly that pair: change either side and the entry
goes stale, the skill falls back to DRIFT / LAGGING, and it has to be looked at
again. A declaration therefore cannot silence a future runtime change — that is
the difference between a recorded judgment and a rubber stamp (same rule as
``BARE_SCRIPT_ALLOWLIST`` in tests/test_skill_references.py: an entry without a
reason is not allowed).

    python scripts/skill_drift.py --declare <skill> --reason "<why the copies differ on purpose>"

writes the entry with the current fingerprints. A declaration on a skill that is
now SAME, or on a skill the toolkit no longer ships, is reported as unused.

Exit codes: 0 = no lagging skill (or no runtime tree found — a distribution user
has none, and that is fine); 1 = at least one lagging skill, or a malformed /
unused declaration; 2 = bad arguments.

Usage
-----
    python scripts/skill_drift.py                   # runtime = ~/.claude/skills
    python scripts/skill_drift.py --runtime <dir>   # another authoring tree
    python scripts/skill_drift.py --json            # machine-readable
    python scripts/skill_drift.py --declare <skill> --reason "<text>"
"""
import argparse
import datetime
import hashlib
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


DEFAULT_DECLARATIONS = ROOT / "config" / "skill-drift-intended.json"
#: A reason shorter than this is a label, not a judgment ("intended", "license").
MIN_REASON_CHARS = 30


def fingerprint(skill_dir: Path) -> str:
    """Hash of SKILL.md + every compared file, CRLF-insensitive, path-ordered."""
    h = hashlib.sha256()
    entries = {"SKILL.md": skill_dir / "SKILL.md", **_files(skill_dir)}
    for rel in sorted(entries):
        h.update(rel.encode("utf-8") + b"\0")
        h.update(_norm(entries[rel]).encode("utf-8") + b"\0")
    return h.hexdigest()[:16]


def load_declarations(path: Path) -> dict:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("skills", {})


def declaration_problems(decls: dict, toolkit_skills: Path) -> list:
    """Shape errors that need no runtime tree (checked in CI, too)."""
    out = []
    for name, d in sorted(decls.items()):
        if not (toolkit_skills / name / "SKILL.md").is_file():
            out.append(f"{name}: declared but the toolkit does not ship this skill")
        reason = (d.get("reason") or "").strip()
        if len(reason) < MIN_REASON_CHARS:
            out.append(f"{name}: reason missing or shorter than {MIN_REASON_CHARS} chars")
        for key in ("toolkit_fp", "runtime_fp"):
            fp = d.get(key) or ""
            if len(fp) != 16 or any(c not in "0123456789abcdef" for c in fp):
                out.append(f"{name}: {key} is not a 16-hex fingerprint")
    return out


def compare(toolkit_skills: Path, runtime: Path, decls: dict = None):
    decls = decls or {}
    rows = []
    for skill_md in sorted(toolkit_skills.glob("*/SKILL.md")):
        name = skill_md.parent.name
        rt = runtime / name / "SKILL.md"
        if not rt.exists():
            row = {"skill": name, "status": "TOOLKIT-ONLY"}
            if name in decls:
                row["declaration"] = "unused"
            rows.append(row)
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
        row = {"skill": name, "status": status, "skill_md_same": md_same,
               "toolkit_last": t_date, "runtime_last": r_date, **files}
        d = decls.get(name)
        if d is not None:
            if same:
                row["declaration"] = "unused"
            else:
                changed = [side for side, key, where in (("toolkit", "toolkit_fp", skill_md.parent),
                                                         ("runtime", "runtime_fp", rt.parent))
                           if d.get(key) != fingerprint(where)]
                if changed:
                    row["declaration"] = "stale"
                    row["declaration_changed"] = changed
                else:
                    row["status"] = "INTENDED"
                    row["declaration"] = "current"
                row["reason"] = d.get("reason", "")
        rows.append(row)
    return rows


def declare(name: str, reason: str, toolkit: Path, runtime: Path, path: Path) -> int:
    reason = (reason or "").strip()
    if len(reason) < MIN_REASON_CHARS:
        print(f"[skill_drift] --reason must say WHY the copies differ on purpose "
              f"(>= {MIN_REASON_CHARS} chars)", file=sys.stderr)
        return 2
    t, r = toolkit / name, runtime / name
    if not (t / "SKILL.md").is_file() or not (r / "SKILL.md").is_file():
        print(f"[skill_drift] {name}: needs a SKILL.md in both trees to declare a difference",
              file=sys.stderr)
        return 2
    t_fp, r_fp = fingerprint(t), fingerprint(r)
    if _norm(t / "SKILL.md") == _norm(r / "SKILL.md") and not any(compare_files(t, r)[k] for k in
                                                                    ("files_drift", "files_toolkit_only",
                                                                     "files_runtime_only")):
        print(f"[skill_drift] {name}: the copies are identical - nothing to declare", file=sys.stderr)
        return 2
    data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    data.setdefault("_comment", "Intended toolkit-vs-runtime skill differences. Written by "
                                "`scripts/skill_drift.py --declare`; each entry is pinned to both "
                                "copies' fingerprints and goes stale when either side changes.")
    skills = data.setdefault("skills", {})
    skills[name] = {"reason": reason, "toolkit_fp": t_fp, "runtime_fp": r_fp,
                    "declared": datetime.date.today().isoformat()}
    data["skills"] = dict(sorted(skills.items()))
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"[skill_drift] {name}: declared intended (toolkit {t_fp}, runtime {r_fp})")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="toolkit vs runtime skill drift")
    ap.add_argument("--runtime", default=str(DEFAULT_RUNTIME),
                    help="authoring skill tree (default: ~/.claude/skills)")
    ap.add_argument("--toolkit", default=str(ROOT / "skills"),
                    help="toolkit skills dir (default: <repo>/skills)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--declarations", default=str(DEFAULT_DECLARATIONS),
                    help="intended-difference file (default: config/skill-drift-intended.json)")
    ap.add_argument("--declare", metavar="SKILL",
                    help="record that SKILL's current difference is intended (needs --reason)")
    ap.add_argument("--reason", help="why the two copies differ on purpose")
    args = ap.parse_args()

    runtime = Path(args.runtime).expanduser()
    toolkit = Path(args.toolkit).expanduser()
    decl_path = Path(args.declarations).expanduser()
    if not toolkit.is_dir():
        print(f"[skill_drift] toolkit skills dir not found: {toolkit}", file=sys.stderr)
        return 2
    if args.declare:
        if not runtime.is_dir():
            print(f"[skill_drift] --declare needs the authoring tree: {runtime}", file=sys.stderr)
            return 2
        return declare(args.declare, args.reason, toolkit, runtime, decl_path)
    try:
        decls = load_declarations(decl_path)
    except (ValueError, OSError) as e:
        print(f"[skill_drift] cannot read {decl_path}: {e}", file=sys.stderr)
        return 1
    problems = declaration_problems(decls, toolkit)
    if not runtime.is_dir():
        msg = {"runtime": str(runtime), "note": "no authoring tree here (distribution install) - nothing to compare",
               "declaration_problems": problems}
        print(json.dumps(msg) if args.json else f"[skill_drift] {msg['note']}: {runtime}")
        for p in problems:
            print(f"[skill_drift] declaration: {p}", file=sys.stderr)
        return 1 if problems else 0

    rows = compare(toolkit, runtime, decls)
    lag = [r for r in rows if r["status"] == "LAGGING"]
    problems += [f"{r['skill']}: declaration unused (copies are now "
                 f"{'identical' if r['status'] == 'SAME' else 'not both present'}) - remove it"
                 for r in rows if r.get("declaration") == "unused"]
    if args.json:
        print(json.dumps({"rows": rows, "lagging": len(lag), "declaration_problems": problems},
                         ensure_ascii=False, indent=1))
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
            if r.get("declaration") == "current":
                print(f"{'':32} {'':13}   intended: {r['reason'][:100]}")
                continue
            if r.get("declaration") == "stale":
                print(f"{'':32} {'':13}   declaration STALE ({' + '.join(r['declaration_changed'])} "
                      f"changed since) - re-review, then --declare again or port")
            for f in r.get("files_drift", [])[:6]:
                print(f"{'':32} {'':13}   drift: {f}")
            for f in r.get("files_runtime_only", [])[:6]:
                print(f"{'':32} {'':13}   runtime-only: {f}")
            for f in r.get("files_toolkit_only", [])[:6]:
                print(f"{'':32} {'':13}   toolkit-only: {f}")
        n = {s: sum(1 for r in rows if r["status"] == s)
             for s in ("SAME", "INTENDED", "DRIFT", "LAGGING", "TOOLKIT-ONLY")}
        print(f"\nsummary: {n}")
        if lag:
            print("LAGGING = runtime copy changed after the toolkit copy; port the change into skills/ "
                  "(runtime is the authoring SSOT), or record why not with --declare.")
        for p in problems:
            print(f"declaration problem: {p}")
    return 1 if (lag or problems) else 0


if __name__ == "__main__":
    sys.exit(main())
