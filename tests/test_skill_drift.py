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


NO_DECLS = os.path.join(tempfile.gettempdir(), "skill_drift_no_such_declarations.json")


def run(*extra, json_out=True):
    # Fixtures must never see the repo's real declaration file.
    if "--declarations" not in extra:
        extra = ("--declarations", NO_DECLS, *extra)
    p = subprocess.run([sys.executable, SCRIPT, *(("--json",) if json_out else ()), *extra],
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

# 5. intended-difference declarations. Measured 2026-09-24: 24 of 27 drifting
# skills were NOT ports (license, runtime-only paths, toolkit ahead). The
# judgment must be recordable, and must not outlive the pair it was made on.
REASON = "toolkit keeps the translated copy; runtime wording is maintainer-local"
with tempfile.TemporaryDirectory() as tmp:
    toolkit = os.path.join(tmp, "toolkit_skills")
    runtime = os.path.join(tmp, "runtime_skills")
    decls = os.path.join(tmp, "config", "intended.json")

    def write(base, skill, rel, body):
        p = os.path.join(base, skill, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(body)

    write(toolkit, "theta", "SKILL.md", "toolkit\n")
    write(runtime, "theta", "SKILL.md", "runtime\n")
    write(toolkit, "iota", "SKILL.md", "same\n")
    write(runtime, "iota", "SKILL.md", "same\n")
    D = ("--toolkit", toolkit, "--runtime", runtime, "--declarations", decls)

    def rows_of():
        rc, out, err = run(*D)
        try:
            data = json.loads(out)
        except Exception as e:  # noqa: BLE001
            check(False, f"json parses ({e}); stderr={err[:200]}")
            return rc, {}, []
        return rc, {r["skill"]: r for r in data["rows"]}, data.get("declaration_problems", [])

    # refusals: short reason, identical pair, unknown skill -> exit 2, nothing written
    rc, _, _ = run(*D, "--declare", "theta", "--reason", "intended", json_out=False)
    check(rc == 2, f"--declare with a label-length reason is refused (got {rc})")
    rc, _, _ = run(*D, "--declare", "iota", "--reason", REASON, json_out=False)
    check(rc == 2, f"--declare on identical copies is refused (got {rc})")
    rc, _, _ = run(*D, "--declare", "nosuch", "--reason", REASON, json_out=False)
    check(rc == 2, f"--declare on a skill missing from a tree is refused (got {rc})")
    check(not os.path.exists(decls), "refused declarations write nothing")

    # declare -> INTENDED, exit 0, reason carried
    rc, out, _ = run(*D, "--declare", "theta", "--reason", REASON, json_out=False)
    check(rc == 0 and os.path.exists(decls), f"--declare writes the file (rc {rc})")
    with open(decls, "rb") as f:
        raw = f.read()
    check(b"\r\n" not in raw, "declaration file is written LF-only")
    rc, rows, probs = rows_of()
    check(rows.get("theta", {}).get("status") == "INTENDED", f"declared pair -> INTENDED (got {rows.get('theta', {}).get('status')})")
    check(rows.get("theta", {}).get("reason") == REASON, "reason is carried into the row")
    check(rc == 0 and probs == [], f"current declaration: exit 0, no problems (rc {rc}, {probs})")
    rc2, out2, _ = run(*D, json_out=False)
    check("intended: " + REASON[:40] in out2, "human table shows the reason")

    # runtime side changes -> stale, falls back to DRIFT, names the side
    write(runtime, "theta", "SKILL.md", "runtime v2\n")
    rc, rows, probs = rows_of()
    th = rows.get("theta", {})
    check(th.get("status") == "DRIFT" and th.get("declaration") == "stale",
          f"runtime change -> stale declaration, status DRIFT (got {th.get('status')}/{th.get('declaration')})")
    check(th.get("declaration_changed") == ["runtime"], f"stale names the changed side (got {th.get('declaration_changed')})")
    rc2, out2, _ = run(*D, json_out=False)
    check("declaration STALE (runtime changed since)" in out2, "human table flags the stale declaration")

    # a runtime-only script added counts as a change too (fingerprint covers scripts/)
    run(*D, "--declare", "theta", "--reason", REASON, json_out=False)
    write(runtime, "theta", "scripts/new.py", "x = 1\n")
    _, rows, _ = rows_of()
    check(rows.get("theta", {}).get("declaration") == "stale", "a new runtime script makes the declaration stale")

    # toolkit side changes -> stale too (the judgment was about the PAIR)
    run(*D, "--declare", "theta", "--reason", REASON, json_out=False)
    write(toolkit, "theta", "SKILL.md", "toolkit v2\n")
    _, rows, _ = rows_of()
    check(rows.get("theta", {}).get("declaration_changed") == ["toolkit"], "toolkit change -> stale, side named")

    # CRLF-only change must NOT stale a declaration
    run(*D, "--declare", "theta", "--reason", REASON, json_out=False)
    with open(os.path.join(toolkit, "theta", "SKILL.md"), "wb") as f:
        f.write(b"toolkit v2\r\n")
    _, rows, _ = rows_of()
    check(rows.get("theta", {}).get("status") == "INTENDED", "CRLF-only change keeps the declaration current")

    # copies converge -> declaration unused -> exit 1 (prune it)
    write(runtime, "theta", "SKILL.md", "toolkit v2\n")
    os.remove(os.path.join(runtime, "theta", "scripts", "new.py"))
    rc, rows, probs = rows_of()
    check(rows.get("theta", {}).get("declaration") == "unused", "identical copies -> declaration unused")
    check(rc == 1 and any("unused" in p for p in probs), f"unused declaration fails the run (rc {rc})")

    # malformed file entries are caught even without a runtime tree (CI path)
    with open(decls, "w", encoding="utf-8") as f:
        json.dump({"skills": {"theta": {"reason": "x", "toolkit_fp": "zz", "runtime_fp": ""},
                              "ghost": {"reason": REASON, "toolkit_fp": "0" * 16, "runtime_fp": "0" * 16}}}, f)
    rc, out, _ = run("--toolkit", toolkit, "--runtime", os.path.join(tmp, "nope"), "--declarations", decls)
    probs = json.loads(out).get("declaration_problems", [])
    check(rc == 1, f"malformed declarations fail even with no runtime tree (got {rc})")
    check(any("reason" in p for p in probs) and any("fingerprint" in p for p in probs)
          and any("ghost" in p for p in probs), f"short reason, bad fingerprint, unknown skill all named ({probs})")

    # unreadable file -> exit 1, not a crash
    with open(decls, "w", encoding="utf-8") as f:
        f.write("{not json")
    rc, _, err = run(*D)
    check(rc == 1 and "cannot read" in err, f"corrupt declaration file -> exit 1 with message (rc {rc})")

# 6. the repo's own declaration file is well-formed (runs in CI, no runtime tree needed)
REAL = os.path.join(ROOT, "config", "skill-drift-intended.json")
if os.path.exists(REAL):
    rc, out, err = run("--runtime", os.path.join(tempfile.gettempdir(), "skill_drift_no_runtime"),
                       "--declarations", REAL)
    probs = json.loads(out).get("declaration_problems", []) if out.strip() else [err]
    check(rc == 0 and not probs, f"config/skill-drift-intended.json is well-formed ({probs})")

print(f"\n{len(fails)} failure(s)")
sys.exit(1 if fails else 0)
