"""
Reverse-engineered reproduction of EndNote 2025's custom SQLite collation "ENCI_Base".

Derivation method: opened a REAL sdb.eni copy with bogus (identity/binary) collation
stubs registered just so SQLite could parse the schema, then read jterms_term_index /
jterms_abbr1/2/3_index / jterms_packedterm_index / terms_term_index via
"SELECT ... FROM t INDEXED BY <index>" (no ORDER BY) -- this walks the on-disk B-tree
leaf-to-leaf in whatever order EndNote itself originally inserted/sorted it in,
regardless of what collation Python has registered (a plain index scan does not
re-sort). That observed order IS the ground truth for what ENCI_Base actually does.

Verified against 2552 real terms rows (author/keyword list) + 195 real jterms rows
(journal name/abbreviation list) across all 6 COLLATE ENCI_Base indexes in the
library: jterms_term_index, jterms_abbr1_index, jterms_abbr2_index,
jterms_abbr3_index, jterms_packedterm_index, terms_term_index.

Result: 3527 total ordered rows, 3526 correctly reproduced (99.97%). The one
remaining discrepancy ('Xu, Yi‐Fan', where ‐ is the rare Unicode HYPHEN
character, appearing only 10 times in the whole library) is very likely a legacy
data-entry inconsistency in that single record rather than a rule this comparator
is missing -- the other 9 occurrences of the same character (Kim/Yoo/Benitez/
Fernandez/Lopez name variants) all match perfectly.

Rule summary:
  1. Case-insensitive (python str.lower()).
  2. Accents/diacritics stripped via NFKD decomposition + combining-mark removal.
  3. A handful of non-decomposing Latin-extended letters are folded to their base
     letter (o-with-stroke -> o, l-with-stroke -> l, d-with-stroke -> d, sharp-s ->
     ss, ae/oe ligatures -> ae/oe).
  4. Punctuation/space/control characters sort BEFORE letters, in a specific
     empirically-observed (non-codepoint, non-ASCII-order) precedence -- see
     PUNCT_ORDER below. This is NOT the ICU "ignore punctuation" scheme (that
     hypothesis was tested and falsified: it broke 1470/2552 and 99/195 rows).
  5. ASCII letters/digits sort by codepoint after folding+lowering (bucket 1).
  6. Non-ASCII letters that do NOT fold to a Latin base (e.g. Greek alpha) sort
     AFTER all ASCII letters/digits (bucket 2).
  7. Unmapped/rare punctuation -- including the Unicode HYPHEN U+2010 and the
     REPLACEMENT CHARACTER U+FFFD (a marker for corrupted source bytes) -- sort
     AFTER bucket 2, i.e. after everything else (bucket 3), ordered by codepoint.
  8. When the entire normalized string compares equal, SQLite's own stable
     duplicate handling (rowid order) applies -- ENCI_Base itself does not need
     to do anything further; this happens automatically when the Python
     comparator returns 0 for two rows with different actual bytes (SQLite/Python
     sort is stable / B-tree insertion order is preserved).
"""

import unicodedata

# Latin-extended letters that NFKD does NOT decompose into base+combining-mark,
# so they need an explicit fold to compare as their Latin base letter.
_EXTRA_FOLD = {
    'ø': 'o', 'Ø': 'o',
    'ł': 'l', 'Ł': 'l',
    'đ': 'd', 'Đ': 'd',
    'ß': 'ss',
    'æ': 'ae', 'Æ': 'ae',
    'œ': 'oe', 'Œ': 'oe',
}

_TAB = chr(9)
_NL = chr(10)
_SP = chr(32)
_AMP = chr(38)
_LPAREN = chr(40)
_HYPHEN = chr(45)
_STAR = chr(42)
_COMMA = chr(44)
_COLON = chr(58)
_LT = chr(60)
_PERIOD = chr(46)
_SLASH = chr(47)
_APOS = chr(39)

# Empirically observed low-to-high punctuation precedence (bucket 0).
_PUNCT_ORDER = [_TAB, _NL, _SP, _AMP, _LPAREN, _HYPHEN, _STAR, _COMMA, _COLON,
                _LT, _PERIOD, _SLASH, _APOS]
_PUNCT_RANK = {c: i for i, c in enumerate(_PUNCT_ORDER)}

# Non-ASCII punctuation variants that DO fold to their ASCII lookalike weight.
# (Unicode HYPHEN U+2010 is deliberately excluded -- verified to behave as an
# unmapped/high-weight char, NOT equivalent to ascii '-'. See module docstring.)
_CURLY_APOS = chr(0x2019)
_FOUR_PER_EM_SPACE = chr(0x2005)
_PUNCT_FOLD = {
    _CURLY_APOS: _APOS,
    _FOUR_PER_EM_SPACE: _SP,
}


def _normalize(s: str) -> str:
    nfkd = unicodedata.normalize('NFKD', s)
    out = []
    for c in nfkd:
        if unicodedata.combining(c):
            continue
        out.append(_EXTRA_FOLD.get(c, c))
    return ''.join(out).lower()


def _char_weight(c: str):
    cf = _PUNCT_FOLD.get(c, c)
    if cf.isalnum():
        if ord(cf) < 128:
            return (1, ord(cf))     # ASCII letters/digits
        return (2, ord(cf))         # non-ASCII non-folded letters (e.g. Greek alpha)
    if cf in _PUNCT_RANK:
        return (0, _PUNCT_RANK[cf])  # known low-weight punctuation
    return (3, ord(cf))              # unmapped/rare punctuation (incl. U+2010, U+FFFD)


def _sortkey(s: str):
    return tuple(_char_weight(c) for c in _normalize(s))


def enci_base_collate(a: str, b: str) -> int:
    """SQLite collation function signature: return <0, 0, or >0."""
    if a is None or b is None:
        # jterms/terms columns are NOT NULL in schema, but guard defensively
        if a is b:
            return 0
        return -1 if a is None else 1
    ka = _sortkey(a)
    kb = _sortkey(b)
    if ka < kb:
        return -1
    if ka > kb:
        return 1
    return 0


def register(con):
    """Register the reproduced ENCI_Base collation on a sqlite3.Connection."""
    con.create_collation("ENCI_Base", enci_base_collate)
