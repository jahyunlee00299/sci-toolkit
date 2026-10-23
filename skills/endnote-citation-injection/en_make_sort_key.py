"""
Reproduction of EndNote 2025's custom SQLite function EN_MAKE_SORT_KEY and of the
ENCIN_ko_KR collation, so that `UPDATE refs ...` can be executed from Python without
corrupting the refs_ord sort index.

WHY THIS EXISTS
---------------
`refs` carries three triggers that maintain the `refs_ord` sort table:

    refs__refs_ord_AI / _AU / _AD
    INSERT INTO refs_ord (ro_trash_state, ro_key_1, ro_key_2, ro_key_3, ro_id)
    VALUES (new.trash_state,
            EN_MAKE_SORT_KEY(new.reference_type, 1, 12),
            EN_MAKE_SORT_KEY(new.author,         2, 12),
            EN_MAKE_SORT_KEY(new.year,           3, 12),
            new.id)

`refs_ord.ro_key_2/3` are declared `COLLATE ENCIN_ko_KR`. Both the function and the
collation live inside EndNote.exe, so a plain `sqlite3.connect()` fails with
`no such collation sequence: ENCIN_ko_KR`, and registering a *wrong* implementation
silently writes sort keys that disagree with EndNote's own ordering.

DERIVATION (260726)
-------------------
Ground truth = the 444 rows already stored in `refs_ord` of the live library. Rules were
refined until every trigger-produced row was reproduced exactly:

    key_1  reference_type code -> upper-case type name (see TYPE_NAMES)
    key_2  author list, see author_sort_key() below
    key_3  year, unchanged

**key_2 rules** (each verified against the stored rows):
  1. Authors are separated by ``\\r`` ONLY. A ``\\n`` is *not* a separator — EndNote then
     treats the whole string as one author, which is exactly how a mis-imported record
     ends up rendering as "Smith, Anna MariaJones, Peter...".
  2. Per author: text before the first comma is the surname, text after it is the given
     name. With no comma at all, the LAST whitespace token is the surname and everything
     before it supplies the initials ("Cassandra De Muynck" -> "MUYNCK CD").
  3. Given names split on whitespace, ``.`` and U+2010 HYPHEN. Each piece contributes its
     first letter; non-letters are skipped ("(NDA)" -> "N").
  4. An ASCII hyphen is preserved inside the initials ("Chi-Huey" -> "C-H"). A piece that
     begins with a hyphen joins the previous initial ("X.-D." -> "X-D").
  5. Initials are truncated to 4 characters, then left-padded to width 4.
  6. Only ASCII a-z are upper-cased; accented and non-Latin characters are left as they
     are ("Jäkel" -> "JäKEL", "Kuş" -> "KUş").
  7. The whole key is truncated to 255 characters.

Result: 431/431 trigger-produced rows reproduced exactly (100%). The 13 excluded rows
store a raw lower-cased author string instead of a sort key — they were inserted without
the trigger ever running (3 empty-author rows + 10 rows added by direct SQL INSERT), and
are a pre-existing defect of those rows, not of this implementation.

ENCIN_ko_KR is BINARY (code-point order); ENCI_Base is provided by the sibling module
``enci_base_collation.py``.

USAGE
-----
    import sqlite3, en_make_sort_key
    con = sqlite3.connect(db_path)
    en_make_sort_key.register(con)      # EN_MAKE_SORT_KEY + ENCIN_ko_KR + ENCI_Base
    ...
Prefer ``safe_refs_update.py`` for actual edits — it wraps this in the
REINDEX -> UPDATE -> REINDEX -> VACUUM -> verify pipeline.
"""

import re

__all__ = ["register", "en_make_sort_key", "author_sort_key", "TYPE_NAMES"]

# reference_type code -> key_1 text, as observed in the live library
TYPE_NAMES = {
    0: "JOURNAL ARTICLE",
    1: "BOOK",
    3: "CONFERENCE PROCEEDINGS",
    7: "BOOK SECTION",
    10: "REPORT",
    12: "AUDIOVISUAL MATERIAL",
    # 15/16 were absent from the live library until 260926 (first Patent / Web Page records).
    # Code order follows EndNote's reference-type table; 10 -> "Report" and 27 -> "Equation"
    # were confirmed against rendered <ref-type name=...> in a manuscript's CWYW fields, and
    # 27 is NOT Report (that is the XML ref-type number, a different numbering).
    15: "PATENT",
    16: "WEB PAGE",
    27: "EQUATION",
    31: "GENERIC",
}

INITIAL_WIDTH = 4
MAX_KEY_LEN = 255

_TOKSEP = re.compile(r"[\s.‐]+")
_WS = re.compile(r"\s+")


def _ascii_upper(s):
    """Upper-case ASCII letters only — accented characters stay as-is (rule 6)."""
    return "".join(ch.upper() if "a" <= ch <= "z" else ch for ch in s)


def _first_letter(tok):
    for ch in tok:
        if ch.isalpha():
            return ch
    return ""


def _initials(given, width=INITIAL_WIDTH):
    out = []
    for piece in _TOKSEP.split(given.strip()):
        if not piece:
            continue
        if piece.startswith("-") and out:            # "X.-D." -> X-D
            tail = _first_letter(piece)
            if tail:
                out[-1] = out[-1] + "-" + tail
            continue
        if "-" in piece:                              # "Chi-Huey" -> C-H
            joined = "-".join(_first_letter(p) for p in piece.split("-") if _first_letter(p))
            out.append(joined)
        else:
            out.append(_first_letter(piece))
    return "".join(out)[:width]


def author_sort_key(author, width=INITIAL_WIDTH, maxlen=MAX_KEY_LEN):
    """EN_MAKE_SORT_KEY(author, 2, 12) — see module docstring for the rules."""
    out = []
    for entry in (author or "").split("\r"):          # \r only (rule 1)
        entry = entry.strip()
        if not entry:
            continue
        if "," in entry:
            parts = entry.split(",")
            surname, given = parts[0].strip(), parts[1].strip()
        else:
            toks = [t for t in _WS.split(entry) if t]
            surname = toks[-1] if toks else ""
            given = " ".join(toks[:-1])
        out.append(_ascii_upper(surname) + " " + _ascii_upper(_initials(given, width)).ljust(width))
    return "".join(out)[:maxlen]


def en_make_sort_key(value, key_index, _param=12):
    """SQLite-facing entry point. key_index: 1=reference_type, 2=author, 3=year."""
    if key_index == 1:
        if value is None or value == "":
            return ""
        try:
            return TYPE_NAMES[int(value)]
        except (KeyError, TypeError, ValueError):
            # Unknown code: fall back to the raw value rather than inventing a name.
            return str(value)
    if key_index == 2:
        return author_sort_key(value)
    if key_index == 3:
        return "" if value is None else str(value)
    return "" if value is None else str(value)


def _encin_ko_kr(a, b):
    """ENCIN_ko_KR behaves as BINARY (code-point order)."""
    a, b = a or "", b or ""
    return (a > b) - (a < b)


def register(con):
    """Register EN_MAKE_SORT_KEY, ENCIN_ko_KR and ENCI_Base on an open connection."""
    con.create_function("EN_MAKE_SORT_KEY", 3, en_make_sort_key)
    con.create_collation("ENCIN_ko_KR", _encin_ko_kr)
    try:
        from enci_base_collation import register as _register_enci
    except ImportError:  # when imported as part of a package
        import os
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from enci_base_collation import register as _register_enci
    _register_enci(con)
    return con
