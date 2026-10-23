"""Tests for ens_style.py: byte-exact round trip, refusals, and a template edit.

Run:  python tests/test_ens_style.py
Exit: 0 all pass | 1 failure

The round trip covers every style shipped with the local EndNote install (skipped when absent):
an untouched parse -> dump must reproduce the file byte for byte, which is the evidence that
the layout (record header, 0xFB padding, the container-length rule, both byte orders) is fully
understood. The end-to-end proof that EndNote READS an edited file is recorded in SKILL.md
(CWYW rendering with a modified style, 261023); it needs Word and is not repeated here.
"""

import glob
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import ens_style as es  # noqa: E402

failures = []


def check(label, ok, detail=""):
    print("  [%s] %s%s" % ("PASS" if ok else "FAIL", label, ("  — %s" % detail) if detail and not ok else ""))
    if not ok:
        failures.append(label)


def rec(tag, typ, body=b"", fmt=">HHI", value=None):
    if typ == es.INTEGER:
        return struct.pack(fmt, tag, typ, value)
    r = struct.pack(fmt, tag, typ, 8 + len(body)) + body
    return r, b"\xfb" * ((-len(r)) % 4)


def synthetic(fmt=">HHI", enc="utf-16-be", magic=es.MAGIC):
    s1, p1 = rec(0x1010, es.STRING, "Probe".encode(enc), fmt)          # 10 bytes -> 2 pad
    i1 = rec(0x1020, es.INTEGER, fmt=fmt, value=7)
    s2, p2 = rec(0x0020, es.STRING, "abc".encode(enc), fmt)           # last child: pad goes outside
    inner, ip = rec(0x1095, es.CONTAINER, s2, fmt)
    body = s1 + p1 + i1 + inner
    top, tp = rec(0x1000, es.CONTAINER, body, fmt)
    return magic + top + tp


print("format")
for label, args in (("big-endian", ()), ("little-endian", ("<HHI", "utf-16-le", es.MAGIC_LE))):
    data = synthetic(*args)
    root = es.parse(data)
    check("%s synthetic parses" % label, root.find(0x1000, 0x1010).value == "Probe")
    check("%s integer is the length field" % label, root.find(0x1000, 0x1020).value == 7)
    check("%s round trip is byte-identical" % label, es.dump(root) == data)
for bad, needle in ((b"0" * 16, "not an RSFTSTYL"),
                    (es.MAGIC + struct.pack(">HHI", 0x1000, 9, 8), "bad record"),
                    (es.MAGIC + struct.pack(">HHI", 0x1000, 1, 99), "bad record"),
                    (es.MAGIC + b"\x10\x00", "truncated")):
    try:
        es.parse(bad)
        check("refuses %s" % needle, False, "parsed")
    except es.FormatError as exc:
        check("refuses %s" % needle, needle in str(exc), str(exc))

print("editing")
root = es.parse(synthetic())
es.set_text(root.find(0x1000, 0x1010), "A longer probe name")
again = es.parse(es.dump(root))
check("longer string re-pads and re-parses", again.find(0x1000, 0x1010).value == "A longer probe name"
      and again.find(0x1000, 0x1020).value == 7)
run = es.Node(0x0021, es.CONTAINER, children=[es.Node(0x0022, es.CONTAINER, children=[
    es.Node(0x0023, es.INTEGER, 2), es.Node(0x0026, es.INTEGER, 2)])])
rich = es.Node(0x1095, es.CONTAINER, children=[es.Node(0x0020, es.STRING, ". In "), run])
try:
    es.set_text(rich, ". In: ")
    check("length change over an inner formatting run is refused", False, "accepted")
except es.FormatError:
    check("length change over an inner formatting run is refused", True)
es.set_text(rich, ". On ")
check("same-length edit over a run is allowed", rich.text == ". On ")
check("template rendering marks bold/italic",
      es.render_template([{"field": 6, "prefix": "", "suffix": ", ", "bits": 2},
                          {"field": 7, "prefix": "", "suffix": "", "bits": 1},
                          {"field": 0, "prefix": "", "suffix": ".", "bits": 0}],
                         {6: "Journal", 7: "Volume"}) == "*Journal*, **Volume**<end>.")

print("shipped styles")
files = sorted(glob.glob(r"C:\Program Files*\EndNote*\Styles\*.ens"))
if not files:
    print("  [SKIP] no EndNote install")
else:
    bad = []
    for f in files:
        with open(f, "rb") as fh:
            data = fh.read()
        try:
            if es.dump(es.parse(data)) != data:
                bad.append(os.path.basename(f))
        except es.FormatError as exc:
            bad.append("%s (%s)" % (os.path.basename(f), exc))
    check("%d/%d shipped styles round-trip byte-identical" % (len(files) - len(bad), len(files)),
          not bad, bad[:5])
    jt = [f for f in files if os.path.basename(f) == "Numbered.ens"]
    if jt:
        root = es.load(jt[0])
        check("every shipped template has a type code", all(c is not None for c, _ in es.bibliography_templates(root)))

print("\n%d failure(s)" % len(failures))
sys.exit(1 if failures else 0)
