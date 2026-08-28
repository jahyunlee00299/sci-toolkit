# -*- coding: utf-8 -*-
"""
endnote_biblio_check.py — EndNote bibliography integrity checker for Word docx.

A recurrence-prevention check, built after a real incident. Non-destructive:
only reads word/document.xml via zipfile (never opens the docx in Word,
never touches the EndNote fields).

Catches 7 categories of error:
  1. reference_type error — the EndNote record is Bill/Generic instead of
                             Journal Article(17) (reference_type left
                             unspecified at INSERT time -> defaults to Bill
                             -> italics/bold get lost)
  2. INVALID CITATION      — distinguishes body-rendered (w:t, unrecoverable)
                             from field (instrText, resolved by Update)
  3. missing journal-name italics — no italic run in the reference paragraph
                             (RSC style italicizes the entire journal name)
  4. suspected missing author — a reference starts with "1 surname, journal"
                             with no initials/co-authors
  5. broken &amp; entity    — a double-escaped or unresolved HTML entity
  6. non-CASSI journal abbreviation — a period-less PubMed-style
                             abbreviation, or a leftover unabbreviated full
                             name (warning)
  7. missing reference-list entry — the highest superscript citation number
                             in the body exceeds the reference list's entry
                             count (measured case: a body citation number
                             exceeded the list's highest number)

Usage:
  python endnote_biblio_check.py <docx>              # summary + error list
  python endnote_biblio_check.py <docx> --json       # JSON output
  python endnote_biblio_check.py <docx> --strict      # exit 1 if any errors (for CI/gates)

reference_type codes are read from <ref-type name="..."> inside the
fldData/instrText blob.
"""
import sys, zipfile, re, base64, zlib, io, json, argparse

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def _read_document_xml(path):
    with zipfile.ZipFile(path) as z:
        return z.read("word/document.xml").decode("utf-8", "replace")


def _decode_blobs(xml):
    """Decode both fldData(base64) and instrText(escaped) into EndNote record XML text."""
    texts = []
    for m in re.finditer(r"<w:fldData[^>]*>(.*?)</w:fldData>", xml, re.S):
        b = re.sub(r"\s+", "", m.group(1))
        try:
            raw = base64.b64decode(b)
        except Exception:
            continue
        for enc in ("utf-8", "utf-16-le", "latin-1"):
            try:
                texts.append(raw.decode(enc, "replace"))
                break
            except Exception:
                pass
        for wbits in (15, -15, 31):
            try:
                texts.append(zlib.decompress(raw, wbits).decode("utf-8", "replace"))
            except Exception:
                pass
    # instrText inline (unescape). &quot;/&apos; must be handled too (some
    # EndNote fields have their ref-type name attribute escaped as &quot;,
    # so skipping it means the regex misses it and hides the error).
    # &amp; always goes last (prevents double-unescaping).
    texts.append(xml.replace("&lt;", "<").replace("&gt;", ">")
                    .replace("&quot;", '"').replace("&apos;", "'").replace("&amp;", "&"))
    return "\n".join(texts)


def check_reference_types(xml):
    """Distribution of ref-type across EndNote records. Anything other than Journal Article(17) is a potential error."""
    blob = _decode_blobs(xml)
    types = re.findall(r'<ref-type name="([^"]+)"', blob)
    from collections import Counter
    dist = Counter(types)
    # Journal Article / Book Section / Report / Web Page / Conference Paper = normal type group
    ok = {"Journal Article", "Book Section", "Report", "Web Page", "Conference Paper"}
    # Bill / Generic, etc. are usually an error that leaked in from being unspecified at INSERT
    suspicious = {t: n for t, n in dist.items() if t not in ok}
    return dict(distribution=dict(dist), suspicious=suspicious)


def check_invalid_citations(xml):
    """Distinguish INVALID CITATION rendered in the body (w:t, unrecoverable) from the field form (instrText, resolved by Update)."""
    rendered = [t for t in re.findall(r"<w:t[^>]*>(.*?)</w:t>", xml, re.S)
                if "INVALID CITATION" in t]
    field = [t for t in re.findall(r"<w:instrText[^>]*>(.*?)</w:instrText>", xml, re.S)
             if "INVALID CITATION" in t]
    return dict(rendered=len(rendered), field=len(field),
                rendered_samples=[re.sub(r"\s+", " ", t).strip()[:70] for t in rendered[:12]])


def _reflist_paragraphs(xml):
    """A paragraph starting with a number and containing a year (19xx/20xx) = a reference-list entry."""
    out = []
    for p in re.findall(r"<w:p\b.*?</w:p>", xml, re.S):
        txt = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p))
        m = re.match(r"\s*(\d+)\.", txt)
        if not m:
            continue
        num = int(m.group(1))
        if num < 1 or num > 400:
            continue
        if not re.search(r", (19|20)\d{2},", txt):
            continue
        out.append((num, txt.strip(), p))
    return out


def check_italic_missing(xml):
    """No italic run in a reference paragraph = missing journal-name italics."""
    missing = []
    for num, txt, p in _reflist_paragraphs(xml):
        if not re.search(r"<w:i\b", p):
            missing.append((num, txt[:80]))
    return missing


def check_author_omission(xml):
    """A reference starting with '1 surname, journal name' with no initials/co-authors = suspected missing author.
    Normal: 'A. B. Surname, ...' or 'A. B. Surname and C. D. Surname, ...'
    Suspect: right after 'number.<space>', a 'Capitalized word, Capitalized journal' with no initial 'X.'."""
    suspects = []
    for num, txt, p in _reflist_paragraphs(xml):
        body = re.sub(r"^\s*\d+\.\s*", "", txt)
        # Suspect if the first token doesn't start with an initial (e.g. 'A.')
        # and goes straight to 'Surname,'. A normal author block contains an
        # 'X. ' pattern (initial + period + space).
        first_chunk = body.split(",")[0]
        has_initial = bool(re.search(r"\b[A-Z]\.\s", body[:40]))
        # 'Surname, Journal' — a single word before the comma (no initial)
        if not has_initial and re.match(r"^[A-Z][a-zA-Z\-]+,", body):
            suspects.append((num, txt[:80]))
    return suspects


def check_entity_breakage(xml):
    """Catches only a double-escaped & that surfaces in rendered text (260715 fix).

    Inside a <w:t> in document.xml, `&amp;` is a correct single escape that
    renders on screen as `&` (do not false-positive on this — the 260714
    skill version did, flagging normal CRediT/funding text as broken). For
    a literal `&amp;` to actually appear on screen, the source needs
    `&amp;amp;` (doubled). In other words, only `&amp;amp;` inside a <w:t>
    (raw form `&amp;amp;amp;`) is a real bug.
    """
    hits = []
    for t in re.findall(r"<w:t[^>]*>([^<]*)</w:t>", xml):
        # `&amp;amp;` in the raw XML fragment t = `&amp;` after one decode pass = `&amp;` exposed on screen
        if "&amp;amp;" in t:
            hits.append(t.strip()[:80])
    return hits


def check_missing_reflist_entries(xml):
    """Compares the highest superscript citation number in body/tables against the reference-list entry count (added 260715).

    In numeric-superscript styles like RSC/ACS, a formatted citation renders
    as a number (including comma/en-dash ranges, e.g. "15,16" "18-20")
    inside the <w:t> of a <w:vertAlign w:val="superscript"/> run. If the
    highest number cited in the body exceeds the reference list's actual
    entry count, that means a reference is missing (a number is cited that
    isn't in the list). Added after a measured case where a body citation
    number existed while the list only went up to 1-14 — the existing
    checks that just count reflist entries (#1 reference_type, etc.) can't
    catch this kind of gap, since the list itself looks internally
    consistent.

    Conservative parsing: only treats a superscript run's text as a
    citation number if it consists solely of digits/commas/spaces/hyphens/
    en-dashes (excludes footnote markers like a/b/c, typos, etc.). A range
    (18-20, 18-20) includes both endpoints.
    """
    max_cited = 0
    cited_numbers = set()
    for r in re.findall(r"<w:r\b.*?</w:r>", xml, re.S):
        if not re.search(r'<w:vertAlign\s+w:val="superscript"\s*/>', r):
            continue
        txt = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", r)).strip()
        if not txt or not re.fullmatch(r"[\d,\s\-–—]+", txt):
            continue
        for part in re.split(r"[,\s]+", txt):
            if not part:
                continue
            m = re.fullmatch(r"(\d+)[\-–—](\d+)", part)
            if m:
                lo, hi = int(m.group(1)), int(m.group(2))
                if hi >= lo and hi - lo < 200:  # sanity guard against mis-parsed ranges
                    cited_numbers.update(range(lo, hi + 1))
                    max_cited = max(max_cited, hi)
            elif part.isdigit():
                n = int(part)
                cited_numbers.add(n)
                max_cited = max(max_cited, n)

    reflist_numbers = {num for num, _txt, _p in _reflist_paragraphs(xml)}
    max_reflist = max(reflist_numbers) if reflist_numbers else 0
    missing = sorted(n for n in cited_numbers if reflist_numbers and n > max_reflist)
    return dict(
        max_cited=max_cited,
        max_reflist=max_reflist,
        n_reflist_entries=len(reflist_numbers),
        missing_numbers=missing,
    )


def check_non_cassi_journal(xml):
    """A reference's italic run (the journal name) is a period-less abbreviation or leftover full name = non-CASSI warning.
    Heuristic: an italic journal name of two or more words with zero periods is suspected of being a period-less PubMed-style abbreviation."""
    warns = []
    for num, txt, p in _reflist_paragraphs(xml):
        jnames = []
        for r in re.findall(r"<w:r\b.*?</w:r>", p, re.S):
            if re.search(r"<w:i\b", r):
                rt = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", r))
                if rt.strip():
                    jnames.append(rt.strip())
        j = " ".join(jnames).strip()
        if not j:
            continue
        words = j.split()
        # 2+ words but zero periods = suspected period-less (PubMed-style) abbreviation.
        # Excludes a single proper noun though (Nature/Science/Tetrahedron/ChemCatChem).
        if len(words) >= 2 and "." not in j and ":" not in j:
            warns.append((num, j[:60]))
    return warns


def run_all(path):
    xml = _read_document_xml(path)
    rt = check_reference_types(xml)
    inv = check_invalid_citations(xml)
    ital = check_italic_missing(xml)
    auth = check_author_omission(xml)
    ent = check_entity_breakage(xml)
    cassi = check_non_cassi_journal(xml)
    missing_refs = check_missing_reflist_entries(xml)
    n_errors = (len(rt["suspicious"]) > 0) + (inv["rendered"] > 0) + (len(ital) > 0) \
        + (len(auth) > 0) + (len(ent) > 0) + (len(missing_refs["missing_numbers"]) > 0)
    return dict(
        file=path,
        reference_types=rt,
        invalid_citations=inv,
        italic_missing=ital,
        author_omission_suspects=auth,
        entity_breakage=ent,
        non_cassi_journal_warnings=cassi,
        missing_reflist_entries=missing_refs,
        error_categories=n_errors,
    )


def _fmt(r):
    L = []
    L.append(f"# EndNote Bibliography Check — {r['file'].split(chr(92))[-1]}")
    rt = r["reference_types"]
    L.append(f"\n## 1. Reference Type distribution")
    for t, n in sorted(rt["distribution"].items(), key=lambda x: -x[1]):
        flag = "  ⚠️ error (needs to be changed to Journal Article)" if t in rt["suspicious"] else ""
        L.append(f"   {t}: {n}{flag}")
    if rt["suspicious"]:
        L.append(f"   \U0001f534 {sum(rt['suspicious'].values())} suspicious type(s) — bulk-change to Journal Article via EndNote Find&Replace")

    inv = r["invalid_citations"]
    L.append(f"\n## 2. INVALID CITATION")
    L.append(f"   rendered (w:t, unrecoverable): {inv['rendered']}  |  field (resolved by Update): {inv['field']}")
    for s in inv["rendered_samples"]:
        L.append(f"     - {s}")

    L.append(f"\n## 3. Missing journal-name italics: {len(r['italic_missing'])}")
    for num, t in r["italic_missing"][:40]:
        L.append(f"   [{num}] {t}")

    L.append(f"\n## 4. Suspected missing author: {len(r['author_omission_suspects'])}")
    for num, t in r["author_omission_suspects"]:
        L.append(f"   [{num}] {t}")

    L.append(f"\n## 5. Broken &amp; entity: {len(r['entity_breakage'])}")
    for t in r["entity_breakage"][:10]:
        L.append(f"   - {t}")

    L.append(f"\n## 6. Non-CASSI journal-name warnings (suspected period-less abbreviation): {len(r['non_cassi_journal_warnings'])}")
    for num, j in r["non_cassi_journal_warnings"][:40]:
        L.append(f"   [{num}] {j}")

    mr = r["missing_reflist_entries"]
    L.append(f"\n## 7. Missing reference-list entries (highest body citation number vs. list entry count)")
    L.append(f"   highest body citation number: {mr['max_cited']}  |  highest list number: {mr['max_reflist']}  |  list entry count: {mr['n_reflist_entries']}")
    if mr["missing_numbers"]:
        L.append(f"   \U0001f534 {len(mr['missing_numbers'])} citation number(s) not in the list: {mr['missing_numbers'][:30]}")

    L.append(f"\n=== Error categories {r['error_categories']}/6 (0=clean) ===")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("docx")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true", help="exit 1 if any errors are found")
    a = ap.parse_args()
    r = run_all(a.docx)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print(_fmt(r))
    if a.strict and r["error_categories"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
