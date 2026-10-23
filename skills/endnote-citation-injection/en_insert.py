"""
en_insert.py — the one supported way to ADD records to an EndNote 2025 library from Python.

Every INSERT incident this skill has recorded came from a field written without a rule:
reference_type left at a default (260714: 33 Bill + 2 Generic), authors joined with \\n
(bibliography folds them into one name), a raw PubMed journal string (no abbreviation),
a DOI already in the library (duplicate record). This tool makes each of those a refusal
instead of a post-hoc audit finding, then reuses safe_refs_update.py's rehearse-then-apply
pipeline so the live library is only touched after a copy passed.

    python en_insert.py --spec new_refs.json              # validate + rehearse (dry run)
    python en_insert.py --spec new_refs.json --apply      # rehearse, back up, insert, verify
    python en_insert.py --spec new_refs.json --json out.json   # also write the id map

Spec: a JSON list of records.

    [{"type": "Journal Article",
      "authors": ["Woodyer, R.", "van der Donk, W. A.", "Zhao, H."],
      "year": "2006", "title": "...", "journal": "Comb Chem High Throughput Screen",
      "volume": "9", "issue": "4", "pages": "237-245",
      "doi": "10.2174/138620706776843246"}]

Optional keys: url (defaults to https://doi.org/<doi>), publisher, place, date, notes,
access_date, corporate (true -> a single organisation author, stored with EndNote's trailing
comma). Unknown keys are refused.

Rules enforced (exit 2 before anything is written):
  type     required, resolved by NAME through RefTypeTable.xml (en_reftypes); Bill/Generic
           need --allow-type; a code without a verified sort-key name is refused
  authors  "Surname, Given" each, no CR/LF/U+FFFD inside, no bare surname unless corporate
  journal  resolved to the canonical full name (en_journal); reported when it is not in the
           library's Journals term list, because the style then prints it unabbreviated
  doi      normalised; a DOI already in the library is SKIPPED and its id reported

Exit: 0 ok (or nothing to insert) | 1 verification failed | 2 bad spec | 3 EndNote running
"""

import argparse
import json
import os
import re
import shutil
import sqlite3
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import en_journal  # noqa: E402
import en_reftypes  # noqa: E402
from en_make_sort_key import TYPE_NAMES, en_make_sort_key, register  # noqa: E402
from safe_refs_update import DEFAULT_DB, endnote_running, log  # noqa: E402

KEYS = {"type", "authors", "corporate", "year", "title", "journal", "volume", "issue", "pages",
        "doi", "url", "publisher", "place", "date", "notes", "access_date"}
COLUMN = {"title": "title", "volume": "volume", "issue": "number", "pages": "pages",
          "url": "url", "publisher": "publisher", "place": "place_published", "date": "date",
          "notes": "notes", "access_date": "access_date", "year": "year"}
JOURNAL_TYPES = {"Journal Article", "Electronic Article", "Magazine Article", "Newspaper Article"}
BAD_CHARS = re.compile("[\r\n\ufffd]")
# EndNote keeps character formatting in refs.text_styles, not as markup: a tag typed into a
# field prints literally ("CO<sub>2</sub>" in a rendered bibliography, a real incident).
MARKUP = re.compile(r"</?(?:sub|sup|i|b|em|strong|span|scp)\b[^>]*>", re.I)


def norm_doi(d):
    d = (d or "").strip()
    d = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:\s*)", "", d, flags=re.I)
    return d.strip().rstrip(".")


class SpecError(ValueError):
    pass


def check_authors(i, rec):
    authors = rec.get("authors") or []
    if not isinstance(authors, list):
        raise SpecError("#%d authors must be a list (one string per author)" % i)
    if rec.get("corporate"):
        if len(authors) != 1:
            raise SpecError("#%d corporate=true takes exactly one author" % i)
        name = authors[0].strip().rstrip(",")
        return [name + ","]
    out = []
    for a in authors:
        a = (a or "").strip()
        if not a or BAD_CHARS.search(a):
            raise SpecError("#%d author %r is empty or holds CR/LF/U+FFFD" % (i, a))
        if "," not in a:
            raise SpecError("#%d author %r has no 'Surname, Given' comma "
                            "(use corporate=true for an organisation)" % (i, a))
        surname, given = [p.strip() for p in a.split(",", 1)]
        if not surname or not given:
            raise SpecError("#%d author %r lacks a surname or given name — a bare surname "
                            "renders as 'Surname, Journal' (author omission)" % (i, a))
        out.append("%s, %s" % (surname, given))
    return out


def build_rows(spec, types, jindex, allow_types):
    """Validate the spec and return (rows, report lines). Raises SpecError."""
    if not isinstance(spec, list) or not spec:
        raise SpecError("spec must be a non-empty JSON list")
    rows, notes, seen_doi = [], [], {}
    now = int(time.time())
    for i, rec in enumerate(spec):
        if not isinstance(rec, dict):
            raise SpecError("#%d is not an object" % i)
        extra = set(rec) - KEYS
        if extra:
            raise SpecError("#%d unknown key(s): %s" % (i, sorted(extra)))
        if not rec.get("type"):
            raise SpecError("#%d has no 'type' — a missing type is how Bill records are made" % i)
        try:
            code = en_reftypes.code_for(rec["type"], types)
        except KeyError as exc:
            raise SpecError("#%d %s" % (i, exc.args[0]))
        name = types[code]
        if name in en_reftypes.SUSPECT_NAMES and name.lower() not in allow_types:
            raise SpecError("#%d type %r is refused without --allow-type %r" % (i, name, name))
        if TYPE_NAMES.get(code) != name.upper():
            raise SpecError("#%d type %r (code %d) has no verified sort-key name in "
                            "en_make_sort_key.TYPE_NAMES; create one such record in the "
                            "EndNote GUI, confirm its ro_key_1, then add it" % (i, name, code))
        year = str(rec.get("year") or "").strip()
        if year and not re.fullmatch(r"\d{4}[a-z]?", year):
            raise SpecError("#%d year %r is not a 4-digit year" % (i, year))
        row = {"reference_type": code, "author": "\r".join(check_authors(i, rec)),
               "added_to_library": now, "record_last_updated": now}
        for k, col in COLUMN.items():
            if rec.get(k) not in (None, ""):
                v = str(rec[k]).strip()
                if "\n" in v or "\ufffd" in v:
                    raise SpecError("#%d %s holds LF/U+FFFD" % (i, k))
                if MARKUP.search(v):
                    raise SpecError("#%d %s holds markup %r — EndNote prints tags literally; give "
                                    "plain text (e.g. CO2, NAD+) and set sub/superscript in the GUI"
                                    % (i, k, MARKUP.search(v).group(0)))
                row[col] = v
        doi = norm_doi(rec.get("doi"))
        if doi:
            if doi.lower() in seen_doi:
                raise SpecError("#%d repeats the DOI of #%d" % (i, seen_doi[doi.lower()]))
            seen_doi[doi.lower()] = i
            row["electronic_resource_number"] = doi
            row.setdefault("url", "https://doi.org/" + doi)
        if rec.get("journal"):
            full, src, in_lib = jindex.resolve(rec["journal"])
            row["secondary_title"] = full
            if name in JOURNAL_TYPES:
                if src == "unmatched":
                    notes.append("#%d journal %r matched no term list — stored as typed; the "
                                 "style will print it unabbreviated" % (i, full))
                elif not in_lib:
                    notes.append("#%d journal %r (from %s) is not in the library's Journals "
                                 "term list — add it or abbreviation will not apply" % (i, full, src))
                if full != rec["journal"]:
                    notes.append("#%d journal %r -> %r" % (i, rec["journal"], full))
        elif name in JOURNAL_TYPES:
            raise SpecError("#%d %s needs a 'journal'" % (i, name))
        rows.append(row)
    return rows, notes


def existing_dois(db):
    con = sqlite3.connect("file:%s?mode=ro" % db.replace("\\", "/"), uri=True)
    try:
        return {norm_doi(d).lower(): rid for rid, d in con.execute(
            "SELECT id, electronic_resource_number FROM refs "
            "WHERE electronic_resource_number <> '' AND trash_state = 0")}
    finally:
        con.close()


def insert_into(db, rows, sync_row):
    """INSERT every row in one transaction; returns the new ids in order."""
    con = sqlite3.connect(db)
    register(con)
    ids = []
    try:
        cur = con.cursor()
        for row in rows:
            cols = list(row)
            cur.execute("INSERT INTO refs (%s) VALUES (%s)" % (", ".join(cols), ", ".join("?" * len(cols))),
                        [row[c] for c in cols])
            rid = cur.lastrowid
            ids.append(rid)
            if sync_row:
                cur.execute(
                    "INSERT INTO sync (type, item_id, item_id2, guid, usn, action, status, "
                    "file_timestamp, file_checksum, action_timestamp, changed_membership_timestamp, "
                    "changed_readstatus_timestamp, changed_rating_timestamp, changed_trash_timestamp, "
                    "reserved1, reserved2, reserved3, reserved4) "
                    "VALUES (1, ?, '', ?, 0, 0, 0, 0, 0, ?, 0, 0, 0, 0, 0, 0, 0, '')",
                    (rid, str(uuid.uuid4()), row["added_to_library"]))
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    return ids


def verify(db, rows, ids, types):
    con = sqlite3.connect("file:%s?mode=ro" % db.replace("\\", "/"), uri=True)
    register(con)
    problems = []
    try:
        res = [r[0] for r in con.execute("PRAGMA integrity_check")]
        if res != ["ok"]:
            problems.append("integrity_check: %s" % res[:3])
        n_refs = con.execute("SELECT COUNT(*) FROM refs").fetchone()[0]
        n_ord = con.execute("SELECT COUNT(*) FROM refs_ord").fetchone()[0]
        if n_refs != n_ord:
            problems.append("refs=%d but refs_ord=%d" % (n_refs, n_ord))
        for row, rid in zip(rows, ids):
            for col, want in row.items():
                got = con.execute("SELECT %s FROM refs WHERE id=?" % col, (rid,)).fetchone()
                if not got or got[0] != want:
                    problems.append("#%s.%s stored %r, wanted %r" % (rid, col, got and got[0], want))
            o = con.execute("SELECT ro_trash_state, ro_key_1, ro_key_2, ro_key_3 FROM refs_ord "
                            "WHERE ro_id=?", (rid,)).fetchone()
            want = (0, en_make_sort_key(row["reference_type"], 1),
                    en_make_sort_key(row["author"], 2), en_make_sort_key(row.get("year", ""), 3))
            if tuple(o or ()) != want:
                problems.append("#%d refs_ord %r != %r" % (rid, o, want))
            if o and o[1] != types[row["reference_type"]].upper():
                problems.append("#%d key_1 %r does not name type %r" % (rid, o[1], types[row["reference_type"]]))
    finally:
        con.close()
    return problems


def marker(row, rid):
    first = row["author"].split("\r")[0].split(",")[0].strip()
    return "{%s, %s #%d}" % (first, row.get("year", ""), rid)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--types", default=en_reftypes.DEFAULT_TABLE, help="RefTypeTable.xml")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--allow-type", action="append", default=[], help="permit Bill / Generic")
    ap.add_argument("--no-sync-row", action="store_true", help="do not add the sync(type=1) row")
    ap.add_argument("--json", help="write {spec index: id | 'existing:<id>'} here")
    args = ap.parse_args()

    if not os.path.exists(args.db):
        log("[ERR] library not found: %s" % args.db)
        return 2
    try:
        with open(args.spec, encoding="utf-8") as fh:
            spec = json.load(fh)
        types = en_reftypes.load(args.types)
        rows, notes = build_rows(spec, types, en_journal.build(args.db),
                                 {t.lower() for t in args.allow_type})
    except (SpecError, ValueError, OSError) as exc:
        log("[ERR] %s" % exc)
        return 2

    have = existing_dois(args.db)
    result, todo = {}, []
    for i, row in enumerate(rows):
        hit = have.get(row.get("electronic_resource_number", "").lower())
        if hit:
            result[i] = "existing:%d" % hit
            log("  #%d DOI already in library as #%d — skipped (cite it as {..#%d})" % (i, hit, hit))
        else:
            todo.append((i, row))
    for n in notes:
        log("  [note] " + n)
    if not todo:
        log("[no-op] every record is already in the library")
        return _finish(args, result, 0)
    if endnote_running():
        log("[ERR] EndNote.exe is running. Close EndNote first (the library must be unlocked).")
        return 3

    idx, new_rows = [t[0] for t in todo], [t[1] for t in todo]
    stamp = time.strftime("%y%m%d_%H%M%S")
    rehearsal = args.db + ".rehearsal_%s" % stamp
    shutil.copy2(args.db, rehearsal)
    log("\n=== rehearsal on a copy (%d record(s)) ===" % len(new_rows))
    try:
        ids = insert_into(rehearsal, new_rows, not args.no_sync_row)
        problems = verify(rehearsal, new_rows, ids, types)
    except Exception as exc:
        problems, ids = ["rehearsal raised: %s" % exc], []
    finally:
        os.remove(rehearsal)
    if problems:
        log("[ABORT] rehearsal failed — live library untouched:")
        for p in problems:
            log("    - " + p)
        return 1
    for i, row, rid in zip(idx, new_rows, ids):
        log("  #%d -> would be %s  [%s]" % (i, marker(row, rid), types[row["reference_type"]]))
    if not args.apply:
        log("\nDRY RUN — the live library was not touched. Re-run with --apply to insert.")
        return 0

    backup = args.db + ".bak_%s_insert%d" % (stamp, len(new_rows))
    shutil.copy2(args.db, backup)
    log("\n=== inserting into the live library ===\n  backup: %s" % backup)
    try:
        live_ids = insert_into(args.db, new_rows, not args.no_sync_row)
        problems = verify(args.db, new_rows, live_ids, types)
        if live_ids != ids:
            problems.append("live ids %s differ from rehearsal %s (library changed meanwhile?)" % (live_ids, ids))
    except Exception as exc:
        problems = ["%s" % exc]
    if problems:
        log("[FAIL] post-insert verification failed — restoring backup:")
        for p in problems:
            log("    - " + p)
        shutil.copy2(backup, args.db)
        return 1
    for i, row, rid in zip(idx, new_rows, live_ids):
        result[i] = rid
        log("  #%d inserted: %s" % (i, marker(row, rid)))
    log("\nDONE. integrity_check ok, sort keys verified. Open EndNote to confirm.")
    return _finish(args, result, 0)


def _finish(args, result, code):
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({str(k): v for k, v in sorted(result.items())}, fh, indent=1)
    return code


if __name__ == "__main__":
    sys.exit(main())
