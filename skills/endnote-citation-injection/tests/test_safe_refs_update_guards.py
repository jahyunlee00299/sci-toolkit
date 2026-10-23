"""Adversarial tests for safe_refs_update.py — every guard must actually fire.

Run:  python tests/test_safe_refs_update_guards.py
Exit: 0 all guards fired | 1 a guard is missing

None of these cases write to the live library: they are rejected before the rehearsal,
or (the valid-spec case) stop at the dry-run boundary.
"""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(os.path.dirname(HERE), "safe_refs_update.py")
DB = os.path.expanduser(r"~\Documents\My EndNote Library_2025.Data\sdb\sdb.eni")



def first_record_id():
    """Any record id that exists in the library (the guards must not depend on a fixed id)."""
    import sqlite3
    con = sqlite3.connect("file:%s?mode=ro" % DB.replace("\\", "/"), uri=True)
    try:
        row = con.execute("SELECT MIN(id) FROM refs").fetchone()
    finally:
        con.close()
    return str(row[0]) if row and row[0] is not None else None


def build_cases(rid):
    return [
        ("unknown record id", {"999999999": {"author": ["Nobody, A."]}}, 2, "not in the library"),
        ("column not on the allow-list", {rid: {"trash_state": 1}}, 2, "not allowed"),
        ("empty spec", {}, 0, "no-op"),
        ("empty column object", {rid: {}}, 2, "bad spec"),
    ]


def run(spec_obj, extra=None):
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(spec_obj, fh)
    try:
        cmd = [sys.executable, TOOL, "--spec", path] + (extra or [])
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        # encoding must be forced: the tool prints non-cp949 characters (accents, ▸)
        # and the default Windows codec would raise while capturing.
        p = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=300,
                           encoding="utf-8", errors="replace")
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    finally:
        os.remove(path)


def main():
    if not os.path.exists(DB):
        print("SKIP — library not present")
        return 0
    rid = first_record_id()
    if rid is None:
        print("SKIP — library has no records")
        return 0
    failed = 0

    for name, spec, want_code, want_text in build_cases(rid):
        code, out = run(spec)
        ok = code == want_code and want_text.lower() in out.lower()
        print("  %s  %-32s (exit %s)" % ("PASS" if ok else "FAIL", name, code))
        if not ok:
            failed += 1
            print("        expected exit %s containing %r" % (want_code, want_text))
            print("        got: %s" % out.strip()[:300])

    # malformed JSON
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write("{ this is not json ")
    p = subprocess.run([sys.executable, TOOL, "--spec", path], capture_output=True, text=True,
                       env=dict(os.environ, PYTHONIOENCODING="utf-8"), timeout=300,
                       encoding="utf-8", errors="replace")
    os.remove(path)
    ok = p.returncode == 2 and "bad spec" in (p.stdout + p.stderr).lower()
    print("  %s  %-32s (exit %s)" % ("PASS" if ok else "FAIL", "malformed JSON", p.returncode))
    failed += 0 if ok else 1

    # a valid spec must stop at the dry-run boundary and leave the library untouched
    before = os.path.getmtime(DB)
    code, out = run({rid: {"author": ["Silva, A. M.", "Costa, C."]}})
    after = os.path.getmtime(DB)
    ok = code == 0 and "DRY RUN" in out and before == after
    print("  %s  %-32s (exit %s)" % ("PASS" if ok else "FAIL", "dry run leaves library intact", code))
    if not ok:
        failed += 1
        print("        mtime changed: %s" % (before != after))

    # no stray rehearsal copies left behind
    leftovers = [f for f in os.listdir(os.path.dirname(DB)) if ".rehearsal_" in f]
    ok = not leftovers
    print("  %s  %-32s" % ("PASS" if ok else "FAIL", "no rehearsal copies left behind"))
    if not ok:
        failed += 1
        print("        leftovers: %s" % leftovers)

    print("\n%s" % ("ALL GUARDS FIRED" if failed == 0 else "%d GUARD(S) MISSING" % failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
