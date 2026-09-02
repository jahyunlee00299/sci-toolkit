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

print(f"\n{len(fails)} failure(s)")
sys.exit(1 if fails else 0)
