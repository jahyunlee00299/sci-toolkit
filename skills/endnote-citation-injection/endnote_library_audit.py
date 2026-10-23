"""Library-side quality audit for an EndNote library: author-name notation and DOI accuracy.

WHY THIS EXISTS (the delta over what already shipped, measured 261002)
----------------------------------------------------------------------
`manuscript-pipeline/scripts/reference_validator.py` already covers two neighboring jobs and
this tool deliberately does NOT redo them:
  * Phase 1b `check_author_collapse()` -- glued author names in a docx's RENDERED bibliography.
  * Phase 1c `--endnote-db`            -- the same collapse signature read from the library, but
                                          ONLY the "no \\r separator at all" case.
  * Phase 3  `check_dois()`            -- CrossRef verification of the DOIs that appear IN A DOCX,
                                          with context matching and 'unverified' on network error.

Two gaps follow from that shape:
  1. The DOI pass is DOCX-DRIVEN. A record whose DOI is wrong but which no manuscript currently
     cites is never checked -- and an uncited record today is a citation tomorrow. 261002: the
     library held 475 records, 161 referenced, so 314 DOIs had never been verified by anything.
  2. The author pass detects one defect class. Measured on the same library: a `\\n` separator
     renders the whole author list as one name (silently -- EndNote's UI shows \\r and \\n
     identically), a RIS import can leave U+FFFD where an accented letter was, and a corporate
     author stored in long form stops `{Author, Year #N}` from resolving.

So this tool is library-driven, reuses reference_validator's CrossRef client instead of writing a
second one, and adds OpenAlex as an independent second opinion for the cases CrossRef confirms.

READ-ONLY. It copies sdb.eni and opens the copy with mode=ro; it never writes to the library.
Repairs go through `safe_refs_update.py` (which rehearses, backs up and verifies) -- this tool
only reports, so a false positive can never corrupt anything.

EXIT CODES (the 0/1/2 contract shared with Skill(verification-gates))
  0  clean
  1  findings to review
  2  could not run (library missing/unreadable) -- never read as a pass

USAGE
  "$PY" endnote_library_audit.py                      # author axis + DOI axis (cached)
  "$PY" endnote_library_audit.py --offline             # author axis only, no network
  "$PY" endnote_library_audit.py --doi-limit 40        # verify at most 40 uncached DOIs
  "$PY" endnote_library_audit.py --json out.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

DEFAULT_DB = Path.home() / 'Documents/My EndNote Library_2025.Data/sdb/sdb.eni'
CACHE = Path.home() / '.cache' / 'sci-toolkit' / 'endnote_doi_cache.json'


def _contact_email() -> str:
    """Contact address for the CrossRef / OpenAlex polite pool.

    Resolved at runtime so that no personal address is stored in this
    repository: CROSSREF_EMAIL, then RESEARCH_CONTACT_EMAIL, then the local
    git identity. Returns an empty string when none is set; both APIs still
    answer, just on the common pool instead of the polite one.
    """
    for key in ('CROSSREF_EMAIL', 'RESEARCH_CONTACT_EMAIL'):
        v = os.environ.get(key, '').strip()
        if v:
            return v
    try:
        import subprocess
        v = subprocess.run(['git', 'config', '--get', 'user.email'],
                           capture_output=True, text=True,
                           timeout=5).stdout.strip()
        if v:
            return v
    except Exception:
        pass
    return ''


EMAIL = _contact_email()
UA = ('endnote-library-audit (mailto:' + EMAIL + ')') if EMAIL else 'endnote-library-audit'

# reference_validator owns the CrossRef client; import it rather than writing a second one.
# Installed layout: <skills dir>/endnote-citation-injection/ next to <skills dir>/manuscript-pipeline/.
for _RV in (Path(__file__).resolve().parents[1] / 'manuscript-pipeline' / 'scripts',
            Path.home() / '.claude' / 'skills' / 'manuscript-pipeline' / 'scripts'):
    if _RV.is_dir() and str(_RV) not in sys.path:
        sys.path.insert(0, str(_RV))
try:
    from reference_validator import _crossref_check  # type: ignore
except Exception:                                    # pragma: no cover - reported, not fatal
    _crossref_check = None

JOURNAL_TYPES = {0}          # stock EndNote 2025 RefTypeTable.xml: 0 = Journal Article (17 = Bill); see en_reftypes.py
DOI_RE = re.compile(r'^10\.\d{4,9}/\S+$')

# Registrars whose DOIs are NOT in CrossRef, so a CrossRef miss says nothing about validity.
# 261002: arXiv mints DataCite DOIs under the 10.48550 prefix. Three NeurIPS preprints
# (three records of one library) were reported D2_unresolvable purely
# because api.crossref.org does not hold them. Their DOIs are fine.
NON_CROSSREF_PREFIXES = ('10.48550/',)      # arXiv (DataCite)
CORPORATE_HINT = re.compile(
    r'\b(Organization|Organisation|Administration|Agency|Ministry|Institute|Institution|'
    r'Department|Commission|Council|Association|Foundation|Authority|Panel|Bureau|'
    r'Corporation|Incorporated|Limited|GmbH|Inc\.|Ltd\.|Ingredients)\b', re.I)


def is_organisation(name: str) -> bool:
    """An organization author legitimately has no comma and no given name.

    A 2026-10 run: A6 first fired on IPCC, JECFA and a company name, all of which are CORRECT as
    stored -- EndNote resolves {IPCC, 2023 #N} from exactly that short form, and forcing a
    comma into them would break the citation key. So a single token, an all-caps acronym, or a
    corporate keyword counts as an organization rather than a swallowed given name.
    """
    n = (name or '').strip().rstrip(',')
    if not n:
        return False
    if CORPORATE_HINT.search(n):
        return True
    if ' ' not in n:                       # IPCC, JECFA, Bonumose
        return True
    letters = [c for c in n if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) > 0.7:
        return True                        # FAO, EFSA and other acronym forms
    return False


# ----------------------------------------------------------------- helpers
def open_ro(db: Path):
    tmp = Path(tempfile.gettempdir()) / f'endnote_audit_{int(time.time())}.eni'
    shutil.copy2(db, tmp)
    con = sqlite3.connect(f'file:{tmp}?mode=ro', uri=True)
    con.text_factory = lambda b: b.decode('utf-8', 'replace')
    return con, tmp


def authors_of(field: str) -> list[str]:
    return [a for a in (field or '').split('\r') if a.strip()]


def surname(a: str) -> str:
    return (a.split(',')[0] or '').strip()


def simple(name: str) -> str:
    """Compare surnames without being defeated by punctuation or diacritics.

    A 2026-10 run: "Sobol" vs CrossRef's "Sobol′" (U+2032 prime) and "Christ" vs "N. Christ" both read
    as mismatches before this. Strip accents, drop everything that is not a letter, casefold.
    """
    s = unicodedata.normalize('NFKD', name or '')
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return ''.join(c for c in s if c.isalpha()).casefold()


def norm_doi(d: str) -> str:
    d = (d or '').strip().lower()
    for pre in ('https://doi.org/', 'http://doi.org/', 'doi:'):
        if d.startswith(pre):
            d = d[len(pre):]
    return d.strip()


# ----------------------------------------------------------------- author axis
def audit_authors(rows):
    """Six defect classes, none of which reference_validator's DB pass covers except A1."""
    out = []
    for rid, author, year, title, journal, rtype in rows:
        a = author or ''
        if not a.strip():
            if rtype in JOURNAL_TYPES:
                out.append((rid, 'A0_no_author', repr(a[:40])))
            continue

        # A1 separator missing entirely (the one reference_validator already reports)
        if '\r' not in a and re.search(r'\.\s?[A-Z][a-zÀ-ɏ]{2,},', a):
            out.append((rid, 'A1_no_separator', a[:70]))
        # A2 LF used as the separator -- EndNote folds the list into ONE author, invisibly
        if '\n' in a:
            out.append((rid, 'A2_lf_separator', a[:70].replace('\n', '\\n')))
        # A3 replacement character from a broken RIS/encoding round-trip
        if '�' in a:
            out.append((rid, 'A3_replacement_char', a[:70]))

        parts = authors_of(a)
        # A5 malformed initial -- a lowercase letter where an initial belongs ("S. i." for
        # "S.-I."). A 2026-10 run: this started life as a "mixed initials vs full names in one record"
        # check and was too noisy to keep: one record stores five full given names plus one author the
        # publisher printed as an initial, which is correct, not a defect. Publishers genuinely
        # mix the two. The lowercase-initial malformation is the part that is always wrong.
        for p in parts:
            given = p.split(',', 1)[1].strip() if ',' in p else ''
            if re.search(r'[A-Z]\.\s*[a-z]\.', given) or re.search(r'[A-Z]\.[a-z]\b', given):
                out.append((rid, 'A5_malformed_initial', p[:70]))
                break
        # A4 / A6 -- one rule, split by what the nameless author looks like.
        #
        # The comma is what EndNote uses to decide where a surname ends. A multi-word author with
        # NO comma gets split on the last space, so "U.S. Food and Drug Administration" is read
        # as surname "Administration" -- which is exactly why one manuscript printed
        # "(Administration, 2001)". A single token has no space to split on, so IPCC / JECFA /
        # Bonumose are correct as stored and must not be flagged.
        #
        # Two earlier versions of this check were both wrong and the data said so:
        #   * "any long corporate name" flagged "Food and Agriculture Organization of the
        #     United Nations," and "EFSA Panel ... (NDA)," which carry the trailing comma
        #     and are therefore right.
        #   * adding an uppercase-ratio test for organizations flagged 23 ordinary people --
        #     "Ji, J. H." is 75% uppercase letters.
        # So: no comma at all + contains a space = defect; corporate-looking ones need the
        # trailing comma, the rest have a swallowed given name.
        for p in parts:
            s = p.strip()
            if ',' in s or ' ' not in s or len(s) <= 3:
                continue
            cls = 'A4_corporate_no_trailing_comma' if is_organisation(s) else 'A6_no_comma'
            out.append((rid, cls, s[:70]))
            break
    return out


# ----------------------------------------------------------------- DOI axis
def openalex_check(doi: str):
    url = ('https://api.openalex.org/works/doi:' + urllib.parse.quote(doi)
           + ('?mailto=' + EMAIL if EMAIL else ''))
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            d = json.load(r)
    except Exception as e:
        return {'status': 'unverified', 'why': type(e).__name__}
    auth = [(x.get('author') or {}).get('display_name', '') for x in (d.get('authorships') or [])]
    return {'status': 'ok', 'year': d.get('publication_year'),
            'title': (d.get('title') or '')[:160], 'first_author': auth[0] if auth else ''}


def datacite_ok(doi: str) -> bool:
    """Resolve a DataCite-registered DOI (arXiv's 10.48550/...) at its own registrar.

    Returns True when the DOI exists OR when the lookup could not be made -- a network failure
    must not be reported as a bad DOI. Only a definite 404 answers 'no'.
    """
    url = f'https://api.datacite.org/dois/{urllib.parse.quote(doi, safe="")}'
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status == 200
    except urllib.error.HTTPError as e:
        return e.code != 404
    except Exception:
        return True                      # unreachable -> not evidence of a bad DOI


def save_cache(cache):
    """Atomic write: a kill DURING the write must not leave a truncated cache behind.

    A 2026-10 run: the first version saved the cache once, after the whole DOI pass. A full run was
    killed partway (the host ran low on memory while the session was idle) and every verdict
    except the 12 already on disk was lost -- roughly 300 CrossRef + OpenAlex calls thrown away.
    Writing to a sibling temp file and os.replace() makes the swap atomic on Windows and POSIX,
    so an interrupted save leaves the previous good cache rather than half a JSON document.
    """
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(cache, ensure_ascii=False), encoding='utf-8')
    os.replace(tmp, CACHE)


FLUSH_EVERY = 20

# Classes that are REPORTED but do not set the exit code. A gate has to mean something: the
# library holds 30 records with no DOI (a data-entry backlog, not a wrong record) and 39 whose
# year differs from OpenAlex by exactly one (the ordinary online-first vs issue-year split).
# Letting those 69 rows force exit 1 would mean the gate never goes green and stops being read.
INFORMATIONAL = {'D0_missing_doi', 'D7_year_online_first'}


def audit_dois_real(recs, offline, limit, cache):
    out, checked = [], 0
    for rid, r in recs.items():
        doi = norm_doi(r['doi'])
        if not doi:
            if r['rtype'] in JOURNAL_TYPES:
                out.append((rid, 'D0_missing_doi', f"{surname(authors_of(r['author'])[0]) if authors_of(r['author']) else '?'} {r['year']}"))
            continue
        if not DOI_RE.match(doi):
            out.append((rid, 'D1_malformed', doi[:60]))
            continue
        if doi.startswith(NON_CROSSREF_PREFIXES):
            # Verified against the registrar that actually holds it, or not at all -- never
            # reported as unresolvable on the strength of a CrossRef miss.
            if not offline and not datacite_ok(doi):
                out.append((rid, 'D6_datacite_unresolvable', doi[:60]))
            continue
        if offline:
            continue
        key = doi
        if key in cache:
            verdict = cache[key]
        else:
            if limit is not None and checked >= limit:
                continue
            checked += 1
            # _crossref_check's contract, learned the hard way 261002: ctx_surnames must be a
            # SET (it intersects, so a list raises TypeError) of LOWERCASED surnames (it
            # lowercases only the CrossRef side, so mixed case makes every record look like
            # 'mismatch_weak' -- 9 of 9 correct DOIs were flagged before this line was fixed).
            sur = {surname(a).lower() for a in authors_of(r['author'])[:3] if surname(a)}
            yrs = {str(r['year'])} if str(r['year']).isdigit() else set()
            cr = (_crossref_check(doi, EMAIL, ctx_surnames=sur, ctx_years=yrs)
                  if _crossref_check else {'status': 'unverified', 'why': 'client_unavailable'})
            oa = openalex_check(doi)
            verdict = {'crossref': cr, 'openalex': oa, 'ts': int(time.time())}
            cache[key] = verdict
            # persist as we go, so an interrupted run resumes instead of restarting (see
            # save_cache's docstring for the run this rule was paid for)
            if checked % FLUSH_EVERY == 0:
                save_cache(cache)
                print(f"  ... {checked} verified, cache flushed ({len(cache)} verdicts)",
                      flush=True)
            time.sleep(0.12)                      # polite pool
        cr, oa = verdict.get('crossref', {}), verdict.get('openalex', {})
        st = str(cr.get('status', '')).lower()

        # CrossRef answers ONE question here: does the DOI resolve. Author/year judgement is
        # taken from OpenAlex, which returns them as structured fields.
        #
        # A 2026-10 run: letting _crossref_check decide the context produced 16 'mismatch_weak'
        # findings whose titles all matched, i.e. zero real mis-citations. Its author test is
        # `ctx_surnames & cr_families`, which cannot work when CrossRef holds NO author list at
        # all -- true for institutional reports (FAO, EFSA) -- nor when
        # CrossRef stores initials inside `family` ("N. Christ") or a prime ("Sobol′"), nor for
        # a corporate author whose counterpart is the full 100-name drafting team (IPCC).
        # Its year test is exact equality, so the routine online-first/issue-year split (ten of
        # the sixteen) read as a mismatch too.
        if 'not_found' in st or '404' in st or st == 'missing':
            out.append((rid, 'D2_unresolvable', doi[:60]))
            continue
        if st in ('unverified', 'unreachable', ''):
            out.append((rid, 'D4_unverified', f"{doi[:40]} :: {cr.get('why', 'no_status')}"))
            continue

        if oa.get('status') != 'ok':
            continue
        oay, recy = oa.get('year'), str(r['year'])
        if oay and recy.isdigit():
            gap = abs(int(oay) - int(recy))
            if gap > 1:
                out.append((rid, 'D3b_year_disagrees',
                            f"record {recy} vs OpenAlex {oay} :: {doi[:36]}"))
            elif gap == 1:
                # one year apart is the normal online-first vs issue-year split, not an error
                out.append((rid, 'D7_year_online_first',
                            f"record {recy} vs OpenAlex {oay} :: {doi[:36]}"))
        rec_sur = surname(authors_of(r['author'])[0]) if authors_of(r['author']) else ''
        oa_first = (oa.get('first_author') or '').split()[-1] if oa.get('first_author') else ''
        if rec_sur and oa_first and not is_organisation(rec_sur) and not is_organisation(oa_first):
            if simple(rec_sur) != simple(oa_first):
                out.append((rid, 'D3_first_author_differs',
                            f"record '{rec_sur}' vs OpenAlex '{oa_first}' :: {doi[:30]}"))
    return out, checked


# ----------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--db', type=Path, default=DEFAULT_DB)
    ap.add_argument('--offline', action='store_true', help='author axis only, no network')
    ap.add_argument('--doi-limit', type=int, default=None,
                    help='verify at most N uncached DOIs this run (cache makes reruns cheap)')
    ap.add_argument('--json', type=Path)
    a = ap.parse_args()

    if not a.db.exists():
        print(f"[2] library not found: {a.db}")
        return 2
    try:
        con, tmp = open_ro(a.db)
    except Exception as e:
        print(f"[2] could not open library read-only: {e}")
        return 2

    # sqlite3.connect is lazy: a file that is not a database opens fine and fails on the FIRST
    # QUERY. 261002 refutation: a junk file exited 1 ("findings to review") instead of 2, which
    # is the one outcome this contract must never produce -- a blind run read as a pass.
    try:
        rows = con.execute(
            "SELECT id, author, year, title, secondary_title, reference_type,"
            " electronic_resource_number, trash_state FROM refs WHERE trash_state=0").fetchall()
    except (sqlite3.Error, sqlite3.DatabaseError) as e:
        print(f"[2] library is not a readable EndNote sqlite file: {e}")
        return 2
    finally:
        con.close()
        tmp.unlink(missing_ok=True)

    recs = {r[0]: dict(author=r[1] or '', year=str(r[2] or ''), title=r[3] or '',
                       journal=r[4] or '', rtype=r[5], doi=r[6] or '') for r in rows}
    print(f"library: {a.db.name} | live records: {len(recs)}"
          f" (trashed records are out of scope)")
    if _crossref_check is None and not a.offline:
        print("  NOTE: reference_validator._crossref_check unavailable -> CrossRef axis degrades "
              "to 'unverified' instead of silently passing")

    author_rows = [(i, r['author'], r['year'], r['title'], r['journal'], r['rtype'])
                   for i, r in recs.items()]
    afind = audit_authors(author_rows)

    cache = {}
    if CACHE.exists():
        try:
            cache = json.loads(CACHE.read_text(encoding='utf-8'))
        except Exception:
            cache = {}
    # The finally is the point: a KeyboardInterrupt or an API blow-up mid-pass must still keep
    # the verdicts already paid for. Periodic flushes happen inside audit_dois_real.
    try:
        dfind, checked = audit_dois_real(recs, a.offline, a.doi_limit, cache)
    finally:
        if not a.offline:
            save_cache(cache)

    groups = defaultdict(list)
    for rid, cls, detail in afind + dfind:
        groups[cls].append((rid, detail))

    print(f"\n=== author axis: {len(afind)} finding(s)")
    for cls in sorted(k for k in groups if k.startswith('A')):
        print(f"  {cls}  ({len(groups[cls])})")
        for rid, det in groups[cls][:8]:
            print(f"     #{rid:4d} {det}")
        if len(groups[cls]) > 8:
            print(f"     ... {len(groups[cls]) - 8} more")

    print(f"\n=== DOI axis: {len(dfind)} finding(s)"
          + (" [offline, skipped]" if a.offline else f" | newly verified this run: {checked}"
             f" | cached verdicts: {len(cache)}"))
    for cls in sorted(k for k in groups if k.startswith('D')):
        print(f"  {cls}  ({len(groups[cls])})")
        for rid, det in groups[cls][:8]:
            print(f"     #{rid:4d} {det}")
        if len(groups[cls]) > 8:
            print(f"     ... {len(groups[cls]) - 8} more")

    if a.json:
        a.json.write_text(json.dumps(
            {'db': str(a.db), 'live_records': len(recs),
             'findings': [{'id': r, 'class': c, 'detail': d} for r, c, d in afind + dfind]},
            ensure_ascii=False, indent=1), encoding='utf-8')
        print(f"\nwrote {a.json}")

    allf = afind + dfind
    actionable = [x for x in allf if x[1] not in INFORMATIONAL]
    info = [x for x in allf if x[1] in INFORMATIONAL]
    print(f"\n=== {len(actionable)} actionable + {len(info)} informational "
          f"({', '.join(sorted(INFORMATIONAL))}) "
          f"-> exit {1 if actionable else 0}  (0 clean / 1 review / 2 blind)")
    return 1 if actionable else 0


if __name__ == '__main__':
    sys.exit(main())
