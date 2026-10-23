"""Regression tests for the EN_MAKE_SORT_KEY reproduction.

Run:  python tests/test_en_make_sort_key.py
Exit: 0 all passed | 1 a case failed

Two layers:
  1. Fixture cases — every rule that was derived from the live library, pinned as a unit
     test so a later "simplification" cannot silently break one of them. Library-free.
  2. Full-library replay (skipped when the library is absent) — regenerates key_2 for
     every row and compares against what EndNote itself stored. This is the real gate:
     it must stay at 100% of trigger-produced rows.
"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from en_make_sort_key import author_sort_key, en_make_sort_key  # noqa: E402

DB = os.path.expanduser(r"~\Documents\My EndNote Library_2025.Data\sdb\sdb.eni")

# (author field, expected key_2, what the case pins down)
FIXTURES = [
    ("Marlowe, C.\rSanders, T.\rZorn, M.",
     "MARLOWE C   SANDERS T   ZORN M   ",
     "plain surname + single initial, 4-wide padding"),
    ("Salter, M.\rNeville, B.\rKeller, K. D.",
     "SALTER M   NEVILLE B   KELLER KD  ",
     "two initials collapse to KD"),
    ("Wang, Chi-Hao\rWhitman, George M.",
     "WANG C-H WHITMAN GM  ",
     "ASCII hyphen survives into the initials"),
    ("Li, Z.\rGao, X.-D.",
     "LI Z   GAO X-D ",
     "'X.-D.' -> X-D (hyphen joins the previous initial)"),
    ("Tarn, B.Mayer, J. M.",
     "TARN BM  ",
     "period is a token separator, second comma is ignored"),
    ("Clayton, W.W",
     "CLAYTON WW  ",
     "'W.W' -> WW"),
    ("Murphy, TI",
     "MURPHY T   ",
     "run of capitals is ONE token -> single initial"),
    ("Kusş, Nermin Şimsşek".replace("sş", "ş"),
     "KUş NŞ  ",
     "only ASCII a-z are upper-cased; accented letters stay"),
    ("Hubert, A.\rJäger, G.",
     "HUBERT A   JäGER G   ",
     "accented surname keeps its lower-case accented letter"),
    ("Clara De Vries\rJan Bakker",
     "VRIES CD  BAKKER J   ",
     "no comma -> last token is the surname"),
    ("Acme Ingredients",
     "INGREDIENTS A   ",
     "no comma + capitals run"),
    ("Agriculture Organization of the United Nations. Fisheries Department",
     "DEPARTMENT AOOT",
     "initials truncated to 4"),
    ("EFSA Panel on Dietetic Products, Nutrition and Allergies (NDA),",
     "EFSA PANEL ON DIETETIC PRODUCTS NAAN",
     "non-letters are skipped when taking a first letter"),
    ("Rahman, Md Karim\rPark, Hee‐Wang",
     "RAHMAN MK  PARK HW  ",
     "U+2010 HYPHEN separates but does not appear in the key"),
    ("Hwang, Jiawei\nChen, Ziwei\nPark, Wenli",
     "HWANG JC  ",
     "REGRESSION: \\n is NOT an author separator — this is what a broken record looks like"),
    ("", "", "empty author"),
]


def run_fixtures():
    failed = 0
    for author, expected, why in FIXTURES:
        got = author_sort_key(author)
        if got == expected:
            print("  PASS  %s" % why)
        else:
            failed += 1
            print("  FAIL  %s" % why)
            print("        author  : %r" % author)
            print("        expected: %r" % expected)
            print("        got     : %r" % got)
    return failed


def run_library_replay():
    if not os.path.exists(DB):
        print("  SKIP  library not found at %s" % DB)
        return 0
    con = sqlite3.connect("file:%s?mode=ro" % DB.replace("\\", "/"), uri=True)
    c = con.cursor()
    c.execute("SELECT ro_id, ro_key_1, ro_key_2, ro_key_3 FROM refs_ord")
    stored = {r[0]: r[1:] for r in c.fetchall()}
    c.execute("SELECT id, reference_type, author, year FROM refs")
    rows = {r[0]: r[1:] for r in c.fetchall()}
    con.close()

    ok = bad = legacy = 0
    problems = []
    for rid, (rtype, author, year) in rows.items():
        if rid not in stored:
            continue
        k1, k2, k3 = stored[rid]
        if not isinstance(k2, str) or (
            k2 == k2.lower() and k2.lower()[:20] == (author or "").replace("\r", " ").lower()[:20]
        ):
            legacy += 1
            continue
        mine = en_make_sort_key(author, 2)
        if mine == k2:
            ok += 1
        else:
            bad += 1
            if len(problems) < 5:
                problems.append((rid, author, k2, mine))

    total = ok + bad
    print("  key_2 replay: %d/%d trigger-produced rows (%.2f%%) | legacy rows skipped: %d"
          % (ok, total, 100.0 * ok / total if total else 0.0, legacy))
    for rid, author, want, got in problems:
        print("    #%s\n      author  : %r\n      expected: %r\n      got     : %r"
              % (rid, (author or "")[:90], want, got))
    return bad


if __name__ == "__main__":
    print("[fixtures]")
    f = run_fixtures()
    print("\n[full-library replay]")
    f += run_library_replay()
    print("\n%s" % ("ALL PASSED" if f == 0 else "%d FAILURE(S)" % f))
    sys.exit(1 if f else 0)
