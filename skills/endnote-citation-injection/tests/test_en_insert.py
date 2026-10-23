"""Adversarial tests for en_insert.py / en_journal.py / en_reftypes.py.

Run:  python tests/test_en_insert.py
Exit: 0 all pass | 1 a guard or resolution rule failed

Pure cases use a synthetic RefTypeTable and term list. The end-to-end case runs against a
COPY of the live library (skipped when the library is absent); the live file is never opened
for writing.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
sys.path.insert(0, SKILL)
import en_journal  # noqa: E402
import en_reftypes  # noqa: E402
from en_insert import SpecError, build_rows  # noqa: E402

DB = os.path.expanduser(r"~\Documents\My EndNote Library_2025.Data\sdb\sdb.eni")
TYPES_XML = ('<RefTypes version="22"><RefType id="0" name="Journal Article"></RefType>'
             '<RefType id="16" name="Web Page"></RefType><RefType id="17" name="Bill"></RefType>'
             '<RefType id="31" name="Generic"></RefType><RefTypeX id="41" name="Grant"></RefTypeX>'
             '</RefTypes>')

failures = []


def check(label, ok, detail=""):
    print("  [%s] %s%s" % ("PASS" if ok else "FAIL", label, ("  — " + detail) if detail and not ok else ""))
    if not ok:
        failures.append(label)


def types():
    fd, path = tempfile.mkstemp(suffix=".xml")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(TYPES_XML)
    try:
        return en_reftypes.load(path)
    finally:
        os.remove(path)


def jindex():
    idx = en_journal.JournalIndex()
    idx._add("Journal of Organic Chemistry", ["J. Org. Chem.", "J Org Chem"], "library")
    idx._add("J Org Chem", [], "library")                       # polluted library term
    idx._add("Science", [], "install:Medical.txt")
    idx._add("Science (Washington)", ["Science"], "install:BioScience.txt")
    return idx


def refused(label, rec, needle, allow=()):
    try:
        build_rows([rec], T, J, set(allow))
        check(label, False, "accepted")
    except SpecError as exc:
        check(label, needle in str(exc), str(exc))


T, J = types(), jindex()
GOOD = {"type": "Journal Article", "authors": ["Kim, A."], "year": "2025", "title": "t",
        "journal": "J Org Chem", "doi": "https://doi.org/10.1/X"}

print("reference types")
check("17 is Bill, not Journal Article", T[17] == "Bill")
check("hidden RefTypeX entries load", T.get(41) == "Grant")
refused("missing type", {k: v for k, v in GOOD.items() if k != "type"}, "no 'type'")
refused("Bill refused by default", dict(GOOD, type="Bill"), "--allow-type")
refused("Generic refused by default", dict(GOOD, type="Generic"), "--allow-type")
refused("unknown type name", dict(GOOD, type="Journal"), "did you mean")
refused("code without verified sort-key name", dict(GOOD, type="Grant"), "TYPE_NAMES")

print("authors")
refused("LF inside an author", dict(GOOD, authors=["Kim, A.\nLee, B."]), "CR/LF")
refused("U+FFFD inside an author", dict(GOOD, authors=["Gr�o, F."]), "CR/LF")
refused("bare surname", dict(GOOD, authors=["Seo"]), "comma")
refused("surname with empty given name", dict(GOOD, authors=["Seo,"]), "bare surname")
refused("authors not a list", dict(GOOD, authors="Kim, A."), "must be a list")
rows, _ = build_rows([dict(GOOD, authors=["Kim, A.", "Lee, B."])], T, J, set())
check("authors joined with CR", rows[0]["author"] == "Kim, A.\rLee, B.")
rows, _ = build_rows([{"type": "Web Page", "authors": ["FAO"], "corporate": True, "title": "x"}], T, J, set())
check("corporate author gets EndNote's trailing comma", rows[0]["author"] == "FAO,")

print("fields")
refused("unknown key", dict(GOOD, jornal="x"), "unknown key")
refused("journal article without journal", {k: v for k, v in GOOD.items() if k != "journal"}, "needs a 'journal'")
refused("bad year", dict(GOOD, year="25"), "4-digit")
refused("HTML markup in title", dict(GOOD, title="CO<sub>2</sub> fixation"), "markup")
refused("scp markup in title", dict(GOOD, title="<scp>D</scp>-Ribose"), "markup")
try:
    build_rows([GOOD, dict(GOOD, title="other")], T, J, set())
    check("duplicate DOI inside one spec", False, "accepted")
except SpecError as exc:
    check("duplicate DOI inside one spec", "repeats the DOI" in str(exc))
rows, notes = build_rows([GOOD], T, J, set())
check("DOI normalised", rows[0]["electronic_resource_number"] == "10.1/X")
check("url defaults to doi.org", rows[0]["url"] == "https://doi.org/10.1/X")
check("type stored as code 0", rows[0]["reference_type"] == 0)

print("journal resolution")
check("abbreviation expands past a polluted library term",
      J.resolve("J Org Chem")[0] == "Journal of Organic Chemistry")
check("a shipped full name is not expanded", J.resolve("Science")[0] == "Science")
check("entities and PubMed suffix cleaned", en_journal.clean("A &amp;amp; B (Tokyo)") == "A & B")
check("unmatched journal reported", J.resolve("Nowhere Letters")[1] == "unmatched")
check("polluted term listed", ("j org chem", "Journal of Organic Chemistry") in J.polluted_terms())

print("end to end on a library copy")
if not os.path.exists(DB):
    print("  [SKIP] live library absent")
else:
    work = tempfile.mkdtemp()
    try:
        db = os.path.join(work, "sdb.eni")
        shutil.copy2(DB, db)
        spec = os.path.join(work, "spec.json")
        with open(spec, "w", encoding="utf-8") as fh:
            json.dump([dict(GOOD, doi="10.9999/en-insert-test")], fh)
        cmd = [sys.executable, os.path.join(SKILL, "en_insert.py"), "--spec", spec, "--db", db,
               "--apply", "--json", os.path.join(work, "ids.json")]
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env=dict(os.environ, PYTHONIOENCODING="utf-8"), timeout=300)
        out = p.stdout + p.stderr
        if p.returncode == 3:
            print("  [SKIP] EndNote is running")
        else:
            check("insert into copy exits 0", p.returncode == 0, out[-400:])
            check("sort keys verified", "sort keys verified" in out, out[-400:])
            cmd2 = cmd[:-1] + [os.path.join(work, "ids2.json")]
            p2 = subprocess.run(cmd2, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                env=dict(os.environ, PYTHONIOENCODING="utf-8"), timeout=300)
            check("re-running skips the now-existing DOI", "already in library" in p2.stdout and p2.returncode == 0,
                  p2.stdout[-300:])
            # the verifier must fail loudly when the stored row is not what was asked for
            from en_insert import verify
            with open(os.path.join(work, "ids.json"), encoding="utf-8") as fh:
                rid = json.load(fh)["0"]
            rows, _ = build_rows([dict(GOOD, doi="10.9999/en-insert-test")], T, J, set())
            import sqlite3
            con = sqlite3.connect(db)
            stamp = con.execute("SELECT added_to_library FROM refs WHERE id=?", (rid,)).fetchone()[0]
            con.close()
            rows[0].update(added_to_library=stamp, record_last_updated=stamp)
            check("verifier passes the real row", verify(db, rows, [rid], T) == [])
            tampered = [dict(rows[0], title="not what was stored")]
            check("verifier catches a field mismatch", any(".title" in p for p in verify(db, tampered, [rid], T)))
            tampered = [dict(rows[0], author="Other, Z.")]
            check("verifier catches a sort-key mismatch", any("refs_ord" in p for p in verify(db, tampered, [rid], T)))
    finally:
        shutil.rmtree(work, ignore_errors=True)

print("\n%d failure(s)" % len(failures))
sys.exit(1 if failures else 0)
