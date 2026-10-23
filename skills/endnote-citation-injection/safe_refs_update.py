"""
safe_refs_update.py — edit existing rows in an EndNote 2025 library from Python without
corrupting the refs_ord sort index.

The plain `UPDATE refs ...` route fails (`no such collation sequence: ENCIN_ko_KR`) or,
worse, succeeds with an approximated collation and leaves the sort index disagreeing with
EndNote's own ordering. This tool registers the reproduced EN_MAKE_SORT_KEY / ENCIN_ko_KR /
ENCI_Base (see en_make_sort_key.py) and runs the whole edit through a rehearsal-first
pipeline:

    0. refuse if EndNote is running (the library would be locked / half-written)
    1. back up sdb.eni
    2. REHEARSE on a throwaway copy: REINDEX -> UPDATE -> REINDEX -> integrity_check
       and re-derive every sort key; abort if anything disagrees
    3. only then apply the same steps to the live file, VACUUM, verify again
    4. on any post-apply failure, restore the backup automatically

Usage
-----
    python safe_refs_update.py --spec fix.json              # dry run (rehearsal only)
    python safe_refs_update.py --spec fix.json --apply      # rehearse, then apply

Spec format (JSON): record id -> column -> value. A list value for `author` is joined
with \\r, which is the separator EndNote expects.

    {
      "123": {"author": ["Silva, A. M.", "Costa, C.", "Ribeiro, F."]},
      "124": {"author": ["Smith, Anna Maria", "Jones, Peter"]}
    }

Exit codes: 0 ok | 1 verification failed / aborted | 2 bad input | 3 EndNote running
"""

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from en_make_sort_key import en_make_sort_key, register  # noqa: E402

DEFAULT_DB = os.path.expanduser(r"~\Documents\My EndNote Library_2025.Data\sdb\sdb.eni")
ALLOWED_COLUMNS = {"author", "year", "title", "secondary_title", "volume", "number",
                   "pages", "electronic_resource_number", "reference_type"}


def log(msg):
    print(msg, flush=True)


def endnote_running():
    # Decode as bytes, never text=True: on a Korean Windows tasklist emits cp949,
    # and an inherited PYTHONIOENCODING=utf-8 makes the decode raise. The stdout
    # attribute is then None and the membership test below dies with TypeError --
    # i.e. the crash lands INSIDE the "is EndNote open?" safety check, which is the
    # one place a failure must never be silent. Match on bytes to stay codec-free.
    try:
        out = subprocess.run(["tasklist"], capture_output=True, timeout=20).stdout
    except Exception:
        # Cannot tell whether EndNote is open. Assume it IS: refusing to run is the
        # safe direction, since writing to a library Word/EndNote has open corrupts it.
        return True
    if not out:
        return True
    return b"endnote.exe" in out.lower()


def load_spec(path):
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    spec = {}
    for rid, cols in raw.items():
        if not isinstance(cols, dict) or not cols:
            raise ValueError("record %s: expected a non-empty object of columns" % rid)
        clean = {}
        for col, val in cols.items():
            if col not in ALLOWED_COLUMNS:
                raise ValueError("record %s: column %r is not allowed" % (rid, col))
            clean[col] = "\r".join(val) if isinstance(val, list) else val
        spec[int(rid)] = clean
    return spec


def read_targets(db, ids):
    con = sqlite3.connect("file:%s?mode=ro" % db.replace("\\", "/"), uri=True)
    cur = con.cursor()
    found = {}
    for rid in ids:
        cur.execute("SELECT id, trash_state, reference_type, author, year FROM refs WHERE id=?", (rid,))
        row = cur.fetchone()
        if row:
            found[rid] = row
    con.close()
    return found


def apply_to(db, spec):
    """REINDEX -> UPDATE -> REINDEX on `db` (already a copy or the live file)."""
    con = sqlite3.connect(db)
    register(con)
    cur = con.cursor()
    cur.execute("REINDEX refs_ord_keys_index")
    n = 0
    for rid, cols in spec.items():
        sets = ", ".join("%s=?" % c for c in cols)
        cur.execute("UPDATE refs SET %s WHERE id=?" % sets, list(cols.values()) + [rid])
        n += cur.rowcount
    con.commit()
    cur.execute("REINDEX refs_ord_keys_index")
    con.commit()
    con.close()
    return n


def verify(db, spec):
    """integrity_check under the real collations + sort keys match a fresh derivation."""
    con = sqlite3.connect("file:%s?mode=ro" % db.replace("\\", "/"), uri=True)
    register(con)
    cur = con.cursor()
    problems = []

    cur.execute("PRAGMA integrity_check")
    res = [r[0] for r in cur.fetchall()]
    if res != ["ok"]:
        problems.append("integrity_check: %s" % res[:3])

    cur.execute("SELECT COUNT(*) FROM refs")
    n_refs = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM refs_ord")
    n_ord = cur.fetchone()[0]
    if n_refs != n_ord:
        problems.append("refs=%d but refs_ord=%d" % (n_refs, n_ord))

    for rid, cols in spec.items():
        cur.execute("SELECT trash_state, reference_type, author, year FROM refs WHERE id=?", (rid,))
        row = cur.fetchone()
        if not row:
            problems.append("#%s vanished" % rid)
            continue
        trash, rtype, author, year = row
        for col, want in cols.items():
            cur.execute("SELECT %s FROM refs WHERE id=?" % col, (rid,))
            got = cur.fetchone()[0]
            if got != want:
                problems.append("#%s.%s not written" % (rid, col))
        cur.execute("SELECT ro_trash_state, ro_key_1, ro_key_2, ro_key_3 FROM refs_ord WHERE ro_id=?", (rid,))
        ord_row = cur.fetchone()
        if not ord_row:
            problems.append("#%s missing from refs_ord" % rid)
            continue
        expect = (trash, en_make_sort_key(rtype, 1), en_make_sort_key(author, 2), en_make_sort_key(year, 3))
        if tuple(ord_row) != expect:
            problems.append("#%s sort key mismatch:\n      stored %r\n      expect %r" % (rid, tuple(ord_row), expect))
    con.close()
    return problems, n_refs


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", required=True, help="JSON file: id -> column -> value")
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--apply", action="store_true", help="write to the live library (default: rehearsal only)")
    args = ap.parse_args()

    if not os.path.exists(args.db):
        log("[ERR] library not found: %s" % args.db)
        return 2
    try:
        spec = load_spec(args.spec)
    except Exception as exc:
        log("[ERR] bad spec: %s" % exc)
        return 2
    if not spec:
        log("[no-op] spec is empty — nothing to do")
        return 0
    if endnote_running():
        log("[ERR] EndNote.exe is running. Close EndNote first (the library must be unlocked).")
        return 3

    targets = read_targets(args.db, spec)
    missing = sorted(set(spec) - set(targets))
    if missing:
        log("[ERR] record id(s) not in the library: %s" % missing)
        return 2

    log("=== plan (%d record(s)) ===" % len(spec))
    for rid in sorted(spec):
        _, _, rtype, author, year = targets[rid]
        log("  #%s  (%s)" % (rid, year))
        for col, want in spec[rid].items():
            cur_val = author if col == "author" else None
            if col == "author":
                log("     before: %r" % (cur_val or "")[:88])
                log("     after : %s" % " | ".join(want.split("\r")))
            else:
                log("     %s -> %r" % (col, want))

    stamp = time.strftime("%y%m%d_%H%M%S")
    rehearsal = args.db + ".rehearsal_%s" % stamp
    shutil.copy2(args.db, rehearsal)
    log("\n=== rehearsal on a copy ===")
    try:
        n = apply_to(rehearsal, spec)
        problems, n_refs = verify(rehearsal, spec)
    except Exception as exc:
        log("[ABORT] rehearsal raised: %s" % exc)
        os.remove(rehearsal)
        return 1
    log("  rows updated: %d | refs: %d" % (n, n_refs))
    if problems:
        log("[ABORT] rehearsal verification failed:")
        for p in problems:
            log("    - %s" % p)
        os.remove(rehearsal)
        return 1
    log("  integrity_check: ok | sort keys re-derived and matching")
    os.remove(rehearsal)

    if not args.apply:
        log("\nDRY RUN — the live library was not touched. Re-run with --apply to commit.")
        return 0

    backup = args.db + ".bak_%s" % stamp
    shutil.copy2(args.db, backup)
    log("\n=== applying to the live library ===")
    log("  backup: %s" % backup)
    try:
        n = apply_to(args.db, spec)
        con = sqlite3.connect(args.db)
        register(con)
        con.execute("VACUUM")
        con.close()
        problems, n_refs = verify(args.db, spec)
    except Exception as exc:
        log("[FAIL] %s — restoring backup" % exc)
        shutil.copy2(backup, args.db)
        return 1
    if problems:
        log("[FAIL] post-apply verification failed — restoring backup:")
        for p in problems:
            log("    - %s" % p)
        shutil.copy2(backup, args.db)
        return 1

    log("  rows updated: %d | refs: %d | integrity_check: ok | sort keys verified" % (n, n_refs))
    log("\nDONE. Open EndNote to confirm, then re-run Word ▸ EndNote ▸ Update Citations and Bibliography.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
