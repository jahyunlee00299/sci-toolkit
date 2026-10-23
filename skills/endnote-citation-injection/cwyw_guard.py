"""
cwyw_guard.py — gates around EndNote's "Update Citations and Bibliography" (CWYW).

Two failures measured on 261002 pass every existing gate (word_validate, docx_preflight,
INVALID CITATION 0, endnote_biblio_check) because each field still holds a well-formed
citation — just the wrong one:

  * RESURRECTION: a citation field deleted with Track Changes on comes back after CWYW
    (merged into a neighbour, or as a live field next to its replacement).
  * SHIFT: every citation in the document renders one position off.

This tool compares what CWYW was asked to do with what it did:

    python cwyw_guard.py precheck  doc.docx [--db sdb.eni]     # refuse unsafe inputs
    python cwyw_guard.py snapshot  doc.docx -o before.json      # record expected citations
    python cwyw_guard.py verify    before.json doc.docx [--db]  # after CWYW: compare

precheck findings (exit 1 when any BLOCK is present):
  BLOCK  deleted-field   an EN.CITE field inside <w:del> — CWYW resurrects it. Remove it
                         untracked first (SKILL.md, "A tracked-DELETED citation field...")
  BLOCK  foreign-db      a cite whose db-id is not this library's — CWYW resolves its
                         RecNum against the WRONG library (another paper with that number)
  BLOCK  orphan          RecNum not in the library (or in the trash)
  WARN   husk-field      an EN.CITE field with no payload whose result is still marker text
  WARN   revisions       other tracked changes present — the SHIFT case was a document with
                         74 revisions; accept them on a copy before trusting CWYW

verify compares the live (non-deleted) citation groups before -> after IN ORDER. Adjacent
groups may merge into one field (CWYW does that legitimately); anything else — a different
record at a position, a deleted record coming back, a group lost — fails. With --db it also
checks that an author-year rendering names each record's first author and year.

Exit: 0 clean | 1 findings | 2 bad input
"""

import argparse
import json
import os
import re
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import en_fields  # noqa: E402

DEFAULT_DB = os.path.expanduser(r"~\Documents\My EndNote Library_2025.Data\sdb\sdb.eni")


# ----------------------------------------------------------------------------- library
class Library:
    def __init__(self, path):
        uri = "file:%s?mode=ro&immutable=1" % path.replace("\\", "/")
        con = sqlite3.connect(uri, uri=True)
        try:
            row = con.execute("SELECT value FROM misc WHERE code=14 AND subcode=0").fetchone()
            v = row[0] if row else b""
            self.db_id = (v.decode() if isinstance(v, bytes) else str(v)).strip()
            self.refs = {rid: (trash, author, year) for rid, trash, author, year in
                         con.execute("SELECT id, trash_state, author, year FROM refs")}
        finally:
            con.close()

    def surname(self, rid):
        a = self.refs.get(rid, (0, "", ""))[1]
        first = a.split("\r")[0]
        return first.split(",")[0].strip() if "," in first else (first.split() or [""])[-1]


# ----------------------------------------------------------------------------- precheck
def has_other_revisions(xml_bytes):
    return len(re.findall(rb"<w:(?:ins|del|moveFrom|moveTo)\b", xml_bytes))


def precheck(docx, lib=None):
    xml = en_fields.read_document_xml(docx)
    cs = en_fields.citations(xml)
    findings = []
    for i, c in enumerate(cs):
        recs = [x["recnum"] for x in c["cites"]]
        if c["deleted"] and c["kind"] == "field":
            findings.append(("BLOCK", "deleted-field", i, "tracked-deleted field %s %r" % (recs, c["rendered"][:40])))
        if c["deleted"]:
            continue
        if c.get("husk"):
            findings.append(("WARN", "husk-field", i, "EN.CITE field with no record payload, result %r "
                             "(260714 fldData husk); CWYW alone turns it into INVALID CITATION — "
                             "cwyw_update.py unlinks it to its marker first"
                             % c["rendered"][:50]))
        for x in c["cites"]:
            if lib and x["db_id"] and x["db_id"] != lib.db_id:
                findings.append(("BLOCK", "foreign-db", i, "#%s %s %s from library %s" % (
                    x["recnum"], x["author"], x["year"], x["db_id"])))
            if lib and x["recnum"] is not None:
                ref = lib.refs.get(x["recnum"])
                if ref is None or ref[0] != 0:
                    findings.append(("BLOCK", "orphan", i, "#%s (%s %s) is %s" % (
                        x["recnum"], x["author"], x["year"], "missing" if ref is None else "in the trash")))
    n_rev = has_other_revisions(xml)
    if n_rev:
        findings.append(("WARN", "revisions", -1, "%d tracked-change element(s); accept them on a "
                         "copy before trusting CWYW (261002 SHIFT case)" % n_rev))
    return cs, findings


# ----------------------------------------------------------------------------- snapshot / verify
def groups(cs):
    """Live citation groups in order: list of tuples of recnums."""
    return [tuple(x["recnum"] for x in c["cites"]) for c in cs if not c["deleted"] and c["cites"]]


def align(before, after):
    """Walk both group lists; allow k>=1 consecutive before-groups to merge into one after-group
    (compared as multisets — CWYW may reorder records inside a group). Returns problems."""
    problems = []
    i = j = 0
    while i < len(before) and j < len(after):
        target = sorted(after[j])
        acc, k, ok = [], i, False
        while k < len(before) and len(acc) < len(target):
            acc += before[k]
            k += 1
            if sorted(acc) == target:
                ok = True
                break
        if ok:
            i, j = k, j + 1
            continue
        problems.append("position %d: expected %s, CWYW produced %s" % (j, list(before[i]), list(after[j])))
        i, j = i + 1, j + 1
    for g in before[i:]:
        problems.append("expected group %s is missing after CWYW" % list(g))
    for g in after[j:]:
        problems.append("unexpected extra group %s after CWYW" % list(g))
    return problems


def rendered_problems(cs, lib):
    out = []
    for c in cs:
        if c["deleted"] or c["kind"] != "field":
            continue
        txt = c["rendered"]
        if not re.search(r"[A-Za-z]{2}", txt):      # numbered style: nothing to compare
            continue
        for x in c["cites"]:
            sur = lib.surname(x["recnum"])
            year = lib.refs.get(x["recnum"], (0, "", ""))[2]
            if sur and sur.lower() not in txt.lower():
                out.append("field %r cites #%s but does not name %r" % (txt[:50], x["recnum"], sur))
            elif year and year[:4] not in txt:
                out.append("field %r cites #%s but lacks its year %s" % (txt[:50], x["recnum"], year))
    return out


def verify(snapshot, docx, lib=None):
    before = [tuple(g) for g in snapshot["groups"]]
    deleted = set(snapshot.get("deleted_recnums", []))
    cs = en_fields.docx_citations(docx)
    left = [c for c in cs if c["kind"] == "marker" and not c["deleted"]]
    after = groups([c for c in cs if c["kind"] == "field"])
    problems = align(before, after)
    still_cited = {r for g in before for r in g}
    back = sorted({r for g in after for r in g} & (deleted - still_cited))
    if back:
        problems.insert(0, "RESURRECTED: record(s) %s were only in deleted citations" % back)
    if left:
        problems.append("%d unformatted marker(s) were not converted: %s" % (
            len(left), [c["rendered"] for c in left[:5]]))
    if lib:
        problems += rendered_problems(cs, lib)
    return problems


def snapshot(docx):
    cs = en_fields.docx_citations(docx)
    return {"docx": os.path.basename(docx), "groups": [list(g) for g in groups(cs)],
            "deleted_recnums": sorted({x["recnum"] for c in cs if c["deleted"] for x in c["cites"]
                                       if x["recnum"] is not None})}


# ----------------------------------------------------------------------------- CLI
def _lib(args):
    path = getattr(args, "db", None)
    if path and os.path.exists(path):
        return Library(path)
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("precheck"); p.add_argument("docx"); p.add_argument("--db", default=DEFAULT_DB)
    p = sub.add_parser("snapshot"); p.add_argument("docx"); p.add_argument("-o", "--out", required=True)
    p = sub.add_parser("verify"); p.add_argument("snapshot"); p.add_argument("docx")
    p.add_argument("--db", default=DEFAULT_DB)
    args = ap.parse_args(argv)

    if args.cmd in ("precheck", "snapshot") and not os.path.exists(args.docx):
        print("[ERR] not found: %s" % args.docx)
        return 2
    if args.cmd == "precheck":
        cs, findings = precheck(args.docx, _lib(args))
        print("citations: %d (%d fields, %d markers)" % (
            len(cs), sum(c["kind"] == "field" for c in cs), sum(c["kind"] == "marker" for c in cs)))
        for level, code, i, msg in findings:
            print("  %-5s %-13s %s" % (level, code, msg))
        blocks = [f for f in findings if f[0] == "BLOCK"]
        print("precheck: %s" % ("BLOCKED (%d)" % len(blocks) if blocks else "ok"))
        return 1 if blocks else 0
    if args.cmd == "snapshot":
        snap = snapshot(args.docx)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(snap, fh, indent=1)
        print("snapshot: %d group(s), %d deleted record(s) -> %s" % (
            len(snap["groups"]), len(snap["deleted_recnums"]), args.out))
        return 0
    with open(args.snapshot, encoding="utf-8") as fh:
        snap = json.load(fh)
    problems = verify(snap, args.docx, _lib(args))
    for p in problems[:40]:
        print("  FAIL " + p)
    print("verify: %s" % ("%d problem(s) — do not trust this CWYW output" % len(problems) if problems else "ok"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
