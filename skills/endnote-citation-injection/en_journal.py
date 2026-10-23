"""
en_journal.py — resolve a journal string from CrossRef / OpenAlex / PubMed to the canonical
FULL name that EndNote's Journals term list can abbreviate.

Why: the bibliography abbreviates a journal only when `refs.secondary_title` matches a
term-list "Full Name" character for character (SKILL.md, "Journal name normalization").
Raw source strings fail that in predictable ways — `J Org Chem` (PubMed abbreviation),
`Green Chemistry` vs a stored `Green Chem.`, `&amp;`, ` (Tokyo)` suffixes.

Resolution order (first hit wins):
  1. the library's own Journals term list (`jterms`), matched on the term or any of abbr1-3
  2. EndNote's shipped term lists (`<install>/Terms Lists/*.txt`, e.g. CASSI `Chemical.txt`)
  3. nothing matched -> the cleaned string is kept and reported as `unmatched`, so the caller
     knows the style will print it as-is

Matching key: case-folded, periods removed, `&`/`and` unified, whitespace collapsed.
"""

import glob
import html
import os
import re
import sqlite3

PUBMED_SUFFIX = re.compile(r"\s*\((?:Tokyo|Amst|Oxf|Basel|Lond|N Y|Weinh|Wash|Berl|Print|Online)\)\s*$"
                           r"|\s+\(?Engl\)?$", re.I)
INSTALL_GLOB = r"C:\Program Files*\EndNote*\Terms Lists\*.txt"


def clean(name):
    """Unescape entities (twice: `&amp;amp;` exists in the wild) and strip PubMed suffixes."""
    s = html.unescape(html.unescape(name or "")).strip()
    s = PUBMED_SUFFIX.sub("", s)
    return re.sub(r"\s+", " ", s).strip()


def key(name):
    s = clean(name).casefold().replace(".", " ")
    s = re.sub(r"\s*&\s*", " and ", s)
    s = re.sub(r"[,:;\-]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


class JournalIndex:
    """key -> candidate (full name, source) list, from the library and the install lists."""

    def __init__(self):
        self._map = {}
        self.library_terms = set()   # keys of full names present in the library's own list

    def _add(self, full, variants, source):
        full = clean(full)
        if not full:
            return
        if source == "library":
            self.library_terms.add(key(full))
        for v in [full] + [x for x in variants if x]:
            k = key(v)
            if k and (full, source) not in self._map.setdefault(k, []):
                self._map[k].append((full, source))

    def add_library(self, con):
        # list_id comes from misc(code=2): the termlist_spec named "Journal List"
        lid = 4
        for (spec,) in con.execute("SELECT value FROM misc WHERE code=2"):
            spec = spec.decode("utf-8", "replace") if isinstance(spec, bytes) else spec
            m = re.search(r'list_id="(\d+)" list_name="Journal', spec or "")
            if m:
                lid = int(m.group(1))
        for term, a1, a2, a3 in con.execute(
                "SELECT term, abbr1, abbr2, abbr3 FROM jterms WHERE list_id=?", (lid,)):
            self._add(term, [a1, a2, a3], "library")
        return self

    def add_install(self, pattern=INSTALL_GLOB):
        for path in sorted(glob.glob(pattern)):
            src = "install:" + os.path.basename(path)
            with open(path, encoding="utf-8-sig", errors="replace") as fh:
                for line in fh:
                    cols = line.rstrip("\r\n").split("\t")
                    if cols and cols[0].strip():
                        self._add(cols[0], cols[1:4], src)
        return self

    def polluted_terms(self):
        """Library 'full names' that are really an abbreviation of another full name
        (e.g. a stored term `ACS Catal` next to `ACS Catalysis`). They make the style print
        the abbreviation in full-name journals and are worth cleaning from jterms."""
        out = []
        for k in sorted(self.library_terms):
            full, _ = self._pick(k)
            if key(full) != k:
                out.append((k, full))
        return out

    def _pick(self, k):
        """Choose among candidates for key k.

        A name that some SHIPPED list carries as a full name stays as it is ("Science" is a
        full name in Medical.txt, so it must not grow into BioScience's "Science (Washington)").
        Otherwise an abbreviation expands to its full name, even when the library stores the
        abbreviation itself as a term (`J Org Chem`). Library candidates win ties."""
        cands = self._map.get(k, [])
        selfs = [c for c in cands if key(c[0]) == k]
        expansions = [c for c in cands if key(c[0]) != k]
        shipped_full = any(src != "library" for _, src in selfs)
        pool = selfs if (shipped_full or not expansions) else expansions
        pool = sorted(pool, key=lambda c: (c[1] != "library", -len(c[0])))
        return pool[0]

    def resolve(self, raw):
        """-> (name to store, source, in_library_list); source 'unmatched' when nothing hit."""
        cleaned = clean(raw)
        k = key(cleaned)
        if k not in self._map:
            return cleaned, "unmatched", False
        full, src = self._pick(k)
        return full, src, key(full) in self.library_terms


def build(db_path=None, install=True):
    idx = JournalIndex()
    if db_path:
        con = sqlite3.connect("file:%s?mode=ro" % db_path.replace("\\", "/"), uri=True)
        try:
            idx.add_library(con)
        finally:
            con.close()
    if install:
        idx.add_install()
    return idx
