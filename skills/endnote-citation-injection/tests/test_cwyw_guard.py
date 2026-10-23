"""Adversarial tests for en_fields.py and cwyw_guard.py on synthetic documents.

Run:  python tests/test_cwyw_guard.py
Exit: 0 all pass | 1 a detector missed its case

Each 261002 failure (SHIFT, RESURRECTION) is rebuilt as a tiny docx so the detector is proven
on the exact shape it must catch, plus the cases that must NOT fire (legitimate merges).
"""

import base64
import os
import sqlite3
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import cwyw_guard  # noqa: E402
import en_fields  # noqa: E402

DB_ID = "testlibrary000"
REFS = {1: ("Alpha, A.", "2001"), 2: ("Beta, B.\rGamma, G.", "2002"), 3: ("Delta, D.", "2003"),
        4: ("Epsilon, E.", "2004"), 9: ("Trashed, T.", "2009")}
failures = []


def check(label, ok, detail=""):
    print("  [%s] %s%s" % ("PASS" if ok else "FAIL", label, ("  — %s" % detail) if detail and not ok else ""))
    if not ok:
        failures.append(label)


def payload(recs, db=DB_ID):
    cites = "".join("<Cite><Author>%s</Author><Year>%s</Year><RecNum>%d</RecNum><record><rec-number>%d"
                    "</rec-number><foreign-keys><key app=\"EN\" db-id=\"%s\">%d</key></foreign-keys>"
                    "</record></Cite>" % (REFS.get(r, ("X, X.", "1999"))[0].split(",")[0],
                                          REFS.get(r, ("", "1999"))[1], r, r, db, r) for r in recs)
    return "<EndNote>%s</EndNote>" % cites


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def field(recs, rendered, nested=False, deleted=False, db=DB_ID):
    it = "w:delInstrText" if deleted else "w:instrText"
    tt = "w:delText" if deleted else "w:t"
    if nested:
        data = base64.b64encode(payload(recs, db).encode()).decode()
        instr = ('<w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><%s> ADDIN EN.CITE </%s></w:r>'
                 '<w:r><w:fldChar w:fldCharType="begin"><w:fldData>%s</w:fldData></w:fldChar></w:r>'
                 '<w:r><%s> ADDIN EN.CITE.DATA </%s></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r>'
                 % (it, it, data, it, it))
    else:
        instr = ('<w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><%s> ADDIN EN.CITE %s</%s></w:r>'
                 % (it, esc(payload(recs, db)), it))
    body = (instr + '<w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><%s>%s</%s></w:r>'
            '<w:r><w:fldChar w:fldCharType="end"/></w:r>' % (tt, esc(rendered), tt))
    return '<w:del w:id="1" w:author="t">%s</w:del>' % body if deleted else body


def text(s, inserted=False):
    r = "<w:r><w:t xml:space=\"preserve\">%s</w:t></w:r>" % esc(s)
    return '<w:ins w:id="2" w:author="t">%s</w:ins>' % r if inserted else r


def docx(*paras):
    xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="%s"><w:body>%s'
           '</w:body></w:document>' % (en_fields.W, "".join("<w:p>%s</w:p>" % p for p in paras)))
    fd, path = tempfile.mkstemp(suffix=".docx")
    os.close(fd)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", xml)
    return path


def library():
    fd, path = tempfile.mkstemp(suffix=".eni")
    os.close(fd)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE misc(code INTEGER, subcode INTEGER, value BLOB)")
    con.execute("INSERT INTO misc VALUES (14, 0, ?)", (DB_ID.encode(),))
    con.execute("CREATE TABLE refs(id INTEGER PRIMARY KEY, trash_state INTEGER, author TEXT, year TEXT)")
    for rid, (a, y) in REFS.items():
        con.execute("INSERT INTO refs VALUES (?,?,?,?)", (rid, 1 if rid == 9 else 0, a, y))
    con.commit()
    con.close()
    return cwyw_guard.Library(path)


LIB = library()
tmp = []


def D(*p):
    tmp.append(docx(*p))
    return tmp[-1]


print("parser")
cs = en_fields.docx_citations(D(text("A ") + field([1], "(Alpha, 2001)") + text(" b ")
                               + field([2, 3], "(Beta and Gamma, 2002; Delta, 2003)", nested=True)
                               + text(" c {Epsilon, 2004 #4} d")))
check("three citations in order", [c["kind"] for c in cs] == ["field", "field", "marker"], cs)
check("inline payload decoded", [x["recnum"] for x in cs[0]["cites"]] == [1])
check("nested EN.CITE.DATA payload decoded", [x["recnum"] for x in cs[1]["cites"]] == [2, 3])
check("rendered result captured", cs[1]["rendered"].startswith("(Beta"))
check("marker parsed", [x["recnum"] for x in cs[2]["cites"]] == [4])
cs = en_fields.docx_citations(D(field([1], "(Alpha, 2001)", deleted=True) + text("{Delta, 2003 #3}", inserted=True)))
check("tracked-deleted field flagged", cs[0]["deleted"] and cs[0]["cites"][0]["recnum"] == 1)
check("inserted marker flagged", cs[1]["kind"] == "marker" and cs[1]["inserted"])

HUSK = ('<w:r><w:fldChar w:fldCharType="begin"><w:fldData>PB==</w:fldData></w:fldChar></w:r>'
        '<w:r><w:instrText> ADDIN EN.CITE </w:instrText></w:r>'
        '<w:r><w:fldChar w:fldCharType="begin"><w:fldData>PA==</w:fldData></w:fldChar></w:r>'
        '<w:r><w:instrText> ADDIN EN.CITE.DATA </w:instrText></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r>'
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>{Beta, 2002 #2; Delta, 2003 #3}</w:t></w:r>'
        '<w:r><w:fldChar w:fldCharType="end"/></w:r>')
cs = en_fields.docx_citations(D(text("x ") + HUSK))
check("husk field (1-byte fldData) read from its marker result",
      len(cs) == 1 and cs[0]["husk"] and [x["recnum"] for x in cs[0]["cites"]] == [2, 3], cs)

print("precheck")
_, f = cwyw_guard.precheck(D(HUSK), LIB)
check("husk field warns", any(x[1] == "husk-field" for x in f), f)
_, f = cwyw_guard.precheck(D(field([1], "(Alpha, 2001)", deleted=True) + text("{Delta, 2003 #3}", inserted=True)), LIB)
codes = {x[1] for x in f}
check("deleted field blocks", "deleted-field" in codes)
check("other revisions warn", "revisions" in codes)
_, f = cwyw_guard.precheck(D(field([1], "(Alpha, 2001)", db="otherlib999")), LIB)
check("foreign db-id blocks", any(x[1] == "foreign-db" for x in f))
_, f = cwyw_guard.precheck(D(text("{Nobody, 2000 #77} {Trashed, 2009 #9}")), LIB)
check("missing and trashed records block", sum(x[1] == "orphan" for x in f) == 2, f)
_, f = cwyw_guard.precheck(D(field([1], "(Alpha, 2001)") + text(" {Delta, 2003 #3}")), LIB)
check("clean document passes", f == [], f)

print("verify")
before = D(field([1], "(Alpha, 2001)") + text(" {Beta, 2002 #2}") + text(" {Delta, 2003 #3}")
           + field([4], "(Epsilon, 2004)"))
snap = cwyw_guard.snapshot(before)
good = D(field([1], "(Alpha, 2001)") + field([2], "(Beta and Gamma, 2002)") + field([3], "(Delta, 2003)")
         + field([4], "(Epsilon, 2004)"))
check("faithful CWYW passes", cwyw_guard.verify(snap, good, LIB) == [], cwyw_guard.verify(snap, good, LIB))
merged = D(field([1], "(Alpha, 2001)") + field([3, 2], "(Beta and Gamma, 2002; Delta, 2003)")
           + field([4], "(Epsilon, 2004)"))
check("adjacent markers merged + reordered passes", cwyw_guard.verify(snap, merged, LIB) == [],
      cwyw_guard.verify(snap, merged, LIB))
shifted = D(field([2], "(Beta and Gamma, 2002)") + field([3], "(Delta, 2003)") + field([4], "(Epsilon, 2004)")
            + field([1], "(Alpha, 2001)"))
p = cwyw_guard.verify(snap, shifted, LIB)
check("SHIFT (every citation one position off) fails", any("position" in x for x in p), p)
left = D(field([1], "(Alpha, 2001)") + text(" {Beta, 2002 #2}") + field([3], "(Delta, 2003)")
         + field([4], "(Epsilon, 2004)"))
p = cwyw_guard.verify(snap, left, LIB)
check("unconverted marker fails", any("not converted" in x for x in p), p)
wrong_render = D(field([1], "(Delta, 2003)") + field([2], "(Beta and Gamma, 2002)") + field([3], "(Delta, 2003)")
                 + field([4], "(Epsilon, 2004)"))
p = cwyw_guard.verify(snap, wrong_render, LIB)
check("field rendering another record's author fails", any("does not name 'Alpha'" in x for x in p), p)

before = D(field([1], "(Alpha, 2001)", deleted=True) + text("{Delta, 2003 #3}", inserted=True) + field([4], "(Epsilon, 2004)"))
snap = cwyw_guard.snapshot(before)
check("snapshot records deleted record", snap["deleted_recnums"] == [1])
resurrected = D(field([1, 3], "(Alpha, 2001; Delta, 2003)") + field([4], "(Epsilon, 2004)"))
p = cwyw_guard.verify(snap, resurrected, LIB)
check("RESURRECTION (merged into the replacement) fails", p and p[0].startswith("RESURRECTED"), p)
resurrected = D(field([3], "(Delta, 2003)") + field([1], "(Alpha, 2001)") + field([4], "(Epsilon, 2004)"))
p = cwyw_guard.verify(snap, resurrected, LIB)
check("RESURRECTION (separate live field) fails", p and p[0].startswith("RESURRECTED"), p)
fine = D(field([3], "(Delta, 2003)") + field([4], "(Epsilon, 2004)"))
check("replacement done right passes", cwyw_guard.verify(snap, fine, LIB) == [])

numbered = D(field([3], "1") + field([4], "2"))
check("numbered style skips author check", cwyw_guard.verify(snap, numbered, LIB) == [])

for t in tmp:
    os.remove(t)
print("\n%d failure(s)" % len(failures))
sys.exit(1 if failures else 0)
