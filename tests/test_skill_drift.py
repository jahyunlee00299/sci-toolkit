#!/usr/bin/env python3
"""Self-test for scripts/skill_drift.py (toolkit vs authoring-tree skill drift).

Three behaviours are pinned, each with a fixture built in a temp dir so the
test does not depend on the maintainer's real runtime tree:

  1. no authoring tree → exit 0 and an explicit "nothing to compare" note
     (a distribution user must not see a failure for something they cannot have)
  2. identical SKILL.md on both sides → SAME
  3. differing SKILL.md → DRIFT (dates unknown outside git, so never LAGGING)

Run:
    python tests/test_skill_drift.py
"""
import json
import os
import subprocess
import sys
import tempfile

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "skill_drift.py")


def run(*extra):
    p = subprocess.run([sys.executable, SCRIPT, "--json", *extra],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, p.stdout, p.stderr


fails = []


def check(cond, msg):
    print(("[PASS] " if cond else "[FAIL] ") + msg)
    if not cond:
        fails.append(msg)


with tempfile.TemporaryDirectory() as tmp:
    toolkit = os.path.join(tmp, "toolkit_skills")
    runtime = os.path.join(tmp, "runtime_skills")
    for base, body in ((toolkit, "same\n"), (runtime, "same\n")):
        os.makedirs(os.path.join(base, "alpha"))
        with open(os.path.join(base, "alpha", "SKILL.md"), "w", encoding="utf-8") as f:
            f.write(body)
    os.makedirs(os.path.join(toolkit, "beta"))
    with open(os.path.join(toolkit, "beta", "SKILL.md"), "w", encoding="utf-8") as f:
        f.write("toolkit version\n")
    os.makedirs(os.path.join(runtime, "beta"))
    with open(os.path.join(runtime, "beta", "SKILL.md"), "w", encoding="utf-8") as f:
        f.write("runtime version\n")
    # gamma: identical text, CRLF on one side only -> must count as SAME
    # (the two trees disagree on core.autocrlf; a line-ending diff is not drift)
    os.makedirs(os.path.join(toolkit, "gamma"))
    with open(os.path.join(toolkit, "gamma", "SKILL.md"), "wb") as f:
        f.write(b"line one\r\nline two\r\n")
    os.makedirs(os.path.join(runtime, "gamma"))
    with open(os.path.join(runtime, "gamma", "SKILL.md"), "wb") as f:
        f.write(b"line one\nline two\n")

    # 1. missing authoring tree
    rc, out, err = run("--toolkit", toolkit, "--runtime", os.path.join(tmp, "nope"))
    check(rc == 0, f"missing runtime tree exits 0 (got {rc})")
    check("nothing to compare" in out, "missing runtime tree says so explicitly")

    # 2 & 3. same vs drift
    rc, out, err = run("--toolkit", toolkit, "--runtime", runtime)
    try:
        data = json.loads(out)
    except Exception as e:  # noqa: BLE001
        data = {"rows": []}
        check(False, f"json output parses ({e}); stderr={err[:200]}")
    st = {r["skill"]: r["status"] for r in data.get("rows", [])}
    check(st.get("alpha") == "SAME", f"identical SKILL.md -> SAME (got {st.get('alpha')})")
    check(st.get("beta") == "DRIFT", f"differing SKILL.md -> DRIFT (got {st.get('beta')})")
    check(st.get("gamma") == "SAME", f"CRLF-only difference -> SAME (got {st.get('gamma')})")
    check(rc == 0, f"drift without git dates is not LAGGING, exit 0 (got {rc})")

# 4. file-level drift — a skill is its scripts as much as its SKILL.md.
# Measured 2026-09-02: detect_resources.py differed by 2,050 lines while the
# SKILL.md-only compare reported SAME for 26 days.
with tempfile.TemporaryDirectory() as tmp:
    toolkit = os.path.join(tmp, "toolkit_skills")
    runtime = os.path.join(tmp, "runtime_skills")

    def mk(base, skill, files):
        for rel, body in files.items():
            p = os.path.join(base, skill, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8", newline="") as f:
                f.write(body)

    # delta: SKILL.md identical, one script differs -> DRIFT, file named
    mk(toolkit, "delta", {"SKILL.md": "same\n", "scripts/tool.py": "print(1)\n"})
    mk(runtime, "delta", {"SKILL.md": "same\n", "scripts/tool.py": "print(2)\n"})
    # epsilon: SKILL.md identical, a script exists only in the runtime tree
    mk(toolkit, "epsilon", {"SKILL.md": "same\n"})
    mk(runtime, "epsilon", {"SKILL.md": "same\n", "scripts/extra.py": "x = 1\n"})
    # zeta: everything identical incl. references/, CRLF differs on one script -> SAME
    mk(toolkit, "zeta", {"SKILL.md": "same\n", "scripts/a.py": "a = 1\r\n", "references/r.md": "ref\n"})
    mk(runtime, "zeta", {"SKILL.md": "same\n", "scripts/a.py": "a = 1\n", "references/r.md": "ref\n"})
    # eta: pycache / downloads noise on one side must not count
    mk(toolkit, "eta", {"SKILL.md": "same\n", "scripts/a.py": "a\n"})
    mk(runtime, "eta", {"SKILL.md": "same\n", "scripts/a.py": "a\n",
                        "scripts/__pycache__/a.cpython-313.pyc": "junk", "scripts/downloads/x.json": "{}"})

    rc, out, err = run("--toolkit", toolkit, "--runtime", runtime)
    try:
        rows = {r["skill"]: r for r in json.loads(out)["rows"]}
    except Exception as e:  # noqa: BLE001
        rows = {}
        check(False, f"json output parses ({e}); stderr={err[:200]}")
    check(rows.get("delta", {}).get("status") == "DRIFT", "identical SKILL.md + differing script -> DRIFT")
    check(rows.get("delta", {}).get("files_drift") == ["scripts/tool.py"],
          f"the differing script is named (got {rows.get('delta', {}).get('files_drift')})")
    check(rows.get("delta", {}).get("skill_md_same") is True, "skill_md_same flag says the prose matched")
    check(rows.get("epsilon", {}).get("status") == "DRIFT", "runtime-only script -> DRIFT")
    check(rows.get("epsilon", {}).get("files_runtime_only") == ["scripts/extra.py"],
          f"runtime-only file named (got {rows.get('epsilon', {}).get('files_runtime_only')})")
    check(rows.get("zeta", {}).get("status") == "SAME", "identical scripts+references (CRLF-only diff) -> SAME")
    check(rows.get("zeta", {}).get("files_compared") == 2, f"two files compared for zeta (got {rows.get('zeta', {}).get('files_compared')})")
    check(rows.get("eta", {}).get("status") == "SAME", "__pycache__ and downloads/ noise ignored -> SAME")
    check("drift: scripts/tool.py" in run.__globals__["subprocess"].run(
        [sys.executable, SCRIPT, "--toolkit", toolkit, "--runtime", runtime],
        capture_output=True, text=True, encoding="utf-8", errors="replace").stdout,
        "human table lists the drifting file")

print(f"\n{len(fails)} failure(s)")
sys.exit(1 if fails else 0)
