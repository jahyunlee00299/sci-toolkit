"""
en_reftypes.py — the reference-type code <-> name table EndNote actually uses.

`refs.reference_type` is an index into EndNote's reference-type table, which lives per
INSTALLATION (not per library) in ``%APPDATA%\\EndNote\\RefTypeTable.xml``:

    <RefTypes version="22"><RefType id="0" name="Journal Article"> ... <RefType id="17" name="Bill">

Measured 261023: the library's own ``misc`` table holds no type table, and the XML agrees
with every code the live library uses (0 Journal Article, 1 Book, 3 Conference Proceedings,
7 Book Section, 10 Report, 12 Audiovisual Material, 15 Patent, 16 Web Page, 31 Generic).
Code 17 is **Bill** — the "default to 17" advice that used to sit in SKILL.md is exactly how
the 260714 incident created 33 Bill-template records. Never pick a code by number; resolve it
from the name with this module.

``RefTypeX`` entries are types the user has hidden; they are still valid codes.
"""

import os
import re

DEFAULT_TABLE = os.path.join(os.environ.get("APPDATA", ""), "EndNote", "RefTypeTable.xml")

# Codes whose template drops journal italics / volume bold. An INSERT that lands here is
# almost always a missing type, never an intended one (260714: 33 Bill + 2 Generic).
SUSPECT_NAMES = {"Bill", "Generic"}


def load(path=DEFAULT_TABLE):
    """Return {code: name} from RefTypeTable.xml. Raises if the file is missing or empty."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        xml = fh.read()
    table = {int(i): n for i, n in re.findall(r'<RefTypeX? id="(\d+)" name="([^"]+)"', xml)}
    if not table:
        raise ValueError("no <RefType> entries in %s" % path)
    return table


def fields(path=DEFAULT_TABLE):
    """Return {type code: {field id: field label}} — the labels the GUI shows per type
    (field 6 is "Journal" for a Journal Article, "Secondary Title" elsewhere). Style templates
    (.ens) refer to fields by these ids."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        xml = fh.read()
    out = {}
    for code, body in re.findall(r'<RefTypeX? id="(\d+)" name="[^"]*">(.*?)</RefTypeX?>', xml, re.S):
        out[int(code)] = {int(i): n for i, n in re.findall(r'<Field id="(\d+)"[^>]*>([^<]*)</Field>', body)}
    return out


def code_for(name, table):
    """Case-insensitive name -> code. Raises KeyError with the close matches listed."""
    want = name.strip().lower()
    for code, n in table.items():
        if n.lower() == want:
            return code
    near = sorted(n for n in table.values() if want.split()[0] in n.lower()) if want else []
    raise KeyError("unknown reference type %r%s" % (name, (" (did you mean: %s?)" % ", ".join(near)) if near else ""))
