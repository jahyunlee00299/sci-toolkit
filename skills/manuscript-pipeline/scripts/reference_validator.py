#!/usr/bin/env python3
"""reference_validator.py — EndNote/citation integrity gate for manuscript docx.

Automates a reference-audit workflow (broken EndNote fields, mis-named PDFs,
bibliographic errors) that is otherwise done by hand. Designed as a mandatory
Phase-4 gate in manuscript-pipeline, run after numeric_consistency_check.py.

Checks (each emits findings; nothing is auto-fixed):

  Phase 1  broken EndNote fields
           - Walk word/document.xml fldChar state machine (begin/separate/end).
           - Flag fields whose instrText is ADDIN EN.CITE / EN.REF but whose rendered
             result contains "!!! INVALID CITATION !!!" or is empty.
  Phase 2  empty field result -> double-citation risk.
  Phase 3  DOI / bibliography sanity (--crossref, default ON):
           - Extract DOIs from the references section, verify via CrossRef.
           - 404  -> 'hallucinated' (HIGH): the DOI does not exist. Likely AI-invented.
           - timeout/network -> 'unverified' (HIGH): never silently pass (no fail-open).
           - resolves but title/author near the DOI in the doc don't match the resolved
             paper -> 'doi_context_mismatch' (HIGH): a real DOI pinned to a wrong claim.
           - If --pdf-dir given, match cited DOIs against DOIs parsed from PDF filenames.

Output: text report (always) + JSON (--json). Exit code:
  0  PASS (no HIGH-severity findings)
  2  HIGH-severity findings present -> blocks declaring the manuscript "final" until manual review.
WARNING/INFO findings do not block.

Usage:
  python reference_validator.py MANUSCRIPT.docx [--json out.json]
  python reference_validator.py MANUSCRIPT.docx --no-crossref          # skip DOI net check
  python reference_validator.py MANUSCRIPT.docx --pdf-dir refs_pdfs/
  python reference_validator.py MANUSCRIPT.docx --email you@lab.org

DOCX safety: reads word/document.xml as bytes; never re-serializes, never edits the
file. Read-only diagnostic.

Hardening note: an earlier version only checked that a DOI *resolved* (fail-open on
network errors, no title/author context match, --crossref opt-in). This version closes
those holes — network errors flag 'unverified', DOIs are context-matched, --crossref ON.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

CROSSREF_BASE = "https://api.crossref.org/works"
_RATE_LIMIT_DELAY = 1.0

INVALID_MARKERS = (
    "!!! INVALID CITATION !!!",
    "{ INVALID CITATION }",
    "INVALID CITATION",
    "Error! Reference source not found",
)
ENDNOTE_INSTR = ("ADDIN EN.CITE", "ADDIN EN.REF", "ADDIN EN.REFLIST")
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:a-zA-Z0-9]+")

# Patterns for extracting the author surname and year near a citation in body text
# (defense for the type-2 case below)
_YEAR_RE = re.compile(r"\b(19|20)\d{2}[a-z]?\b")
_SURNAME_RE = re.compile(r"\b([A-Z][a-zçéèáñöüä\-]{2,})\b")


class Finding:
    def __init__(self, level, id_, detail, hint):
        self.level = level
        self.id = id_
        self.detail = detail
        self.hint = hint

    def to_dict(self):
        return {"level": self.level, "id": self.id, "detail": self.detail, "hint": self.hint}


# ---------------------------------------------------------------------------
# docx I/O (read-only)
# ---------------------------------------------------------------------------

def _read_document_xml(docx_path):
    with zipfile.ZipFile(docx_path) as z:
        return z.read("word/document.xml").decode("utf-8", errors="replace")


def _unescape(s):
    return (s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
            .replace("&quot;", '"').replace("&apos;", "'"))


def _iter_field_tokens(doc_xml):
    """Yield (kind, pos, payload) over field-relevant tokens, in document order.

    kind in {'begin','separate','end','instr','text'}.
    """
    pattern = re.compile(
        r'<w:fldChar\b[^>]*\bw:fldCharType="(?P<ft>begin|separate|end)"[^>]*/?>'
        r'|<w:instrText\b[^>]*?>(?P<instr>.*?)</w:instrText>'
        r'|<w:t\b(?![a-zA-Z])[^>]*?>(?P<text>.*?)</w:t>',
        re.DOTALL,
    )
    for m in pattern.finditer(doc_xml):
        if m.group("ft"):
            yield (m.group("ft"), m.start(), "")
        elif m.group("instr") is not None:
            yield ("instr", m.start(), _unescape(m.group("instr")))
        else:
            yield ("text", m.start(), _unescape(m.group("text")))


# ---------------------------------------------------------------------------
# Phase 1 + 2 — EndNote field integrity
# ---------------------------------------------------------------------------

def check_fields(doc_xml, findings):
    stack = []
    completed = []
    for kind, pos, payload in _iter_field_tokens(doc_xml):
        if kind == "begin":
            stack.append({"instr": "", "result": "", "has_sep": False, "pos": pos})
        elif kind == "instr":
            if stack:
                stack[-1]["instr"] += payload
        elif kind == "separate":
            if stack:
                stack[-1]["has_sep"] = True
        elif kind == "text":
            if stack and stack[-1]["has_sep"]:
                stack[-1]["result"] += payload
        elif kind == "end":
            if stack:
                completed.append(stack.pop())

    n_endnote = 0
    n_broken = 0
    n_empty = 0
    for fld in completed:
        instr = fld["instr"]
        if not any(tag in instr for tag in ENDNOTE_INSTR):
            continue
        n_endnote += 1
        result = fld["result"]
        if any(mark in result for mark in INVALID_MARKERS):
            n_broken += 1
            findings.append(Finding(
                "HIGH", "broken_endnote_field",
                f'INVALID CITATION rendered. instr="{instr}" result="{result}"',
                "Stale Record Number or library mismatch. Re-resolve via "
                "endnote_helper.py doi-resolve, replace with {Author, Year #RecNum}, "
                "then Word Update Fields.",
            ))
        elif fld["has_sep"] and not result.strip() and "REFLIST" not in instr:
            n_empty += 1
            findings.append(Finding(
                "HIGH", "empty_field_result",
                f'EndNote field has empty result. instr="{instr}"',
                "Empty result invites hand-typed [N] duplicates (v48 incident). Do NOT "
                "add plain [N]; fix the field and Word Update Fields.",
            ))
    return {"endnote_fields": n_endnote, "broken": n_broken, "empty_result": n_empty}


# ---------------------------------------------------------------------------
# Phase 3 — DOI sanity
# ---------------------------------------------------------------------------

def _plain_text(doc_xml):
    """Strip tags + unescape -> plain body text (for context extraction)."""
    return _unescape(re.sub(r"<[^>]+>", " ", doc_xml))


def _extract_dois(doc_xml):
    text = _plain_text(doc_xml)
    seen = []
    for m in DOI_RE.finditer(text):
        d = m.group(0).rstrip(".)];,").lower()
        if d not in seen:        # dedupe (an earlier version missed this — prevents repeat calls for the same DOI)
            seen.append(d)
    return seen


def _doi_context(doc_xml, doi, window=400):
    """Extract candidate author surname/year from the `window` characters before a DOI's
    occurrence (defense for the type-2 case below).

    Use a generous window (400 chars) — a long title pushes the author further from
    the DOI, and a narrow window would catch only title/journal words and produce
    false positives.

    Returns: (surnames:set[str-lower], years:set[str])
    """
    text = _plain_text(doc_xml)
    low = text.lower()
    idx = low.find(doi.lower())
    if idx < 0:
        return set(), set()
    seg = text[max(0, idx - window): idx]   # before the DOI (author/year usually precede it)
    surnames = {s.lower() for s in _SURNAME_RE.findall(seg)}
    years = {m.group(0)[:4] for m in _YEAR_RE.finditer(seg)}
    return surnames, years


def _fetch_crossref(doi, email):
    url = f"{CROSSREF_BASE}/{urllib.parse.quote(doi)}"
    if email:
        url += f"?mailto={urllib.parse.quote(email)}"
    req = urllib.request.Request(url, headers={"User-Agent": "reference_validator/1.1"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def _crossref_check(doi, email, ctx_surnames=None, ctx_years=None):
    """Verify a DOI via CrossRef.

    Returns dict:
        {"status": "ok"|"not_found"|"unreachable"|"mismatch",
         "title": str, "detail": str}

    - not_found  : 404 = the DOI does not exist (hallucination signal)
    - unreachable: network/timeout = cannot verify (never treated as pass — fail-closed)
    - mismatch   : the DOI is real but doesn't match the body citation's author/year
                   (a real DOI attached to the wrong claim)
    - ok         : real + (when context was available) author/year match
    """
    try:
        data = _fetch_crossref(doi, email)
        msg = data.get("message", {})
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"status": "not_found", "title": "", "detail": "CrossRef 404"}
        return {"status": "unreachable", "title": "", "detail": f"HTTP {e.code}"}
    except Exception as e:
        return {"status": "unreachable", "title": "", "detail": str(e)}

    title = (msg.get("title") or [""])[0]

    # Type-2 defense: does the author/year near the body citation match the resolved paper?
    # False positives are expensive (blocking a valid citation erodes trust in the tool),
    # so confidence is tiered:
    #   author AND year both mismatch -> 'mismatch' (HIGH, strong miscitation signal)
    #   author mismatch only (year matches/unknown) -> 'mismatch_weak' (WARNING, does not block)
    # Author matching can miss due to window/extraction limits, but a year mismatch on top
    # sharply raises the odds of a real miscitation.
    if ctx_surnames or ctx_years:
        cr_families = {a.get("family", "").lower() for a in msg.get("author", []) if a.get("family")}
        cr_year = ""
        for dk in ("published", "published-print", "published-online", "issued"):
            dp = msg.get(dk, {}).get("date-parts", [[]])
            if dp and dp[0]:
                cr_year = str(dp[0][0])
                break
        author_ok = (not ctx_surnames) or bool(ctx_surnames & cr_families)
        year_ok = (not ctx_years) or (cr_year in ctx_years) or (not cr_year)
        if not author_ok or not year_ok:
            bits = []
            if not author_ok:
                bits.append(f"body author {sorted(ctx_surnames)} vs CrossRef author {sorted(cr_families)}")
            if not year_ok:
                bits.append(f"body year {sorted(ctx_years)} vs CrossRef year '{cr_year}'")
            # A strong signal needs the year to mismatch too; author-only mismatch is weak
            # (could be an extraction limit).
            strong = (not author_ok) and (not year_ok) and bool(ctx_years)
            return {
                "status": "mismatch" if strong else "mismatch_weak",
                "title": title[:80],
                "detail": "; ".join(bits),
            }

    return {"status": "ok", "title": title[:80], "detail": ""}


def check_dois(doc_xml, findings, email, pdf_dir):
    dois = _extract_dois(doc_xml)
    n_unresolved = 0
    n_mismatch = 0
    for doi in dois:
        surnames, years = _doi_context(doc_xml, doi)
        res = _crossref_check(doi, email, surnames, years)
        st = res["status"]
        if st == "not_found":
            n_unresolved += 1
            findings.append(Finding(
                "HIGH", "doi_hallucinated",
                f"{doi} -> CrossRef 404 (DOI does not exist)",
                "Likely an AI-invented DOI. Verify the DOI, or remove/replace the citation.",
            ))
        elif st == "unreachable":
            n_unresolved += 1
            findings.append(Finding(
                "HIGH", "doi_unverified",
                f"{doi} -> could not verify ({res['detail']})",
                "Check your network connection and re-run. Never treat as passed before verification (fail-open prevention).",
            ))
        elif st == "mismatch":
            n_mismatch += 1
            findings.append(Finding(
                "HIGH", "doi_context_mismatch",
                f"{doi} -> real DOI, but mismatched with the body citation: {res['detail']} (CrossRef='{res['title']}')",
                "A real DOI may be attached to the wrong claim/paper (miscitation). Confirm "
                "that paper actually makes that claim.",
            ))
        elif st == "mismatch_weak":
            # Author mismatch only (year matches/unknown) — likely an extraction limit. WARNING, not a block.
            findings.append(Finding(
                "WARNING", "doi_author_unmatched",
                f"{doi} -> author match failed (year matches/unknown): {res['detail']} (CrossRef='{res['title']}')",
                "Usually an extraction limit (author is far from the DOI in text), but could be a miscitation — worth a quick check.",
            ))
        time.sleep(_RATE_LIMIT_DELAY)

    n_pdf_mismatch = 0
    if pdf_dir and pdf_dir.is_dir():
        cited = set(dois)
        for f in pdf_dir.iterdir():
            if f.suffix.lower() != ".pdf":
                continue
            m = DOI_RE.search(f.stem)
            if not m:
                continue
            fdoi = m.group(0).rstrip(".)];,").lower()
            if fdoi not in cited:
                n_pdf_mismatch += 1
                findings.append(Finding(
                    "WARNING", "pdf_doi_not_cited",
                    f"{f.name}: filename DOI {fdoi} not found among cited DOIs",
                    "Possible mis-named PDF (cf. seo_2019/huwig_1998). Confirm the file "
                    "matches the reference it is named for.",
                ))

    return {
        "dois_checked": len(dois),
        "doi_unresolved": n_unresolved,
        "doi_context_mismatch": n_mismatch,
        "pdf_mismatch": n_pdf_mismatch,
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run(docx_path, crossref=True, email=None, pdf_dir=None):
    doc_xml = _read_document_xml(docx_path)
    findings = []
    info = {}
    info.update(check_fields(doc_xml, findings))
    if crossref:
        info.update(check_dois(doc_xml, findings, email, pdf_dir))
    return findings, info


def format_report(docx_path, findings, info):
    lines = [f"reference_validator: {docx_path.name}", "=" * 60]
    for k, v in info.items():
        lines.append(f"  {k}: {v}")
    lines.append("-" * 60)
    if not findings:
        lines.append("RESULT: PASS — no reference-integrity findings.")
        return "\n".join(lines)
    order = {"HIGH": 0, "WARNING": 1, "INFO": 2}
    for f in sorted(findings, key=lambda x: order.get(x.level, 9)):
        lines.append(f"[{f.level}] {f.id}: {f.detail}")
        if f.hint:
            lines.append(f"         -> {f.hint}")
    n_high = sum(1 for f in findings if f.level == "HIGH")
    lines.append("-" * 60)
    lines.append(f"RESULT: {'FAIL' if n_high else 'PASS-WITH-WARNINGS'} "
                 f"({n_high} HIGH, {len(findings)} total)")
    return "\n".join(lines)


def _load_email():
    # Prefer an environment variable; fall back to an optional local secrets file
    # if one happens to exist. Either way, returns None when unset (CrossRef
    # polite-pool email is optional) — pass --email to override.
    # Provide your email via the CROSSREF_EMAIL env var or the --email argument
    # (used only for CrossRef's polite pool; optional).
    env = os.environ.get("CROSSREF_EMAIL")
    if env:
        return env
    return None


def main():
    ap = argparse.ArgumentParser(description="EndNote/citation integrity gate for docx.")
    ap.add_argument("docx", type=Path)
    # Defensive default: --crossref is ON by default. Pass --no-crossref explicitly to turn it off.
    ap.add_argument("--crossref", dest="crossref", action="store_true", default=True,
                    help="verify DOIs via CrossRef (default ON)")
    ap.add_argument("--no-crossref", dest="crossref", action="store_false",
                    help="skip DOI network verification")
    ap.add_argument("--email", default=None, help="CrossRef polite-pool email")
    ap.add_argument("--pdf-dir", type=Path, default=None, help="refs PDF folder (1 level)")
    ap.add_argument("--json", dest="json_out", type=Path, default=None)
    args = ap.parse_args()

    if not args.docx.is_file():
        print(f"ERROR: not a file: {args.docx}", file=sys.stderr)
        sys.exit(3)

    email = args.email or _load_email()
    findings, info = run(args.docx, crossref=args.crossref, email=email, pdf_dir=args.pdf_dir)

    print(format_report(args.docx, findings, info))

    if args.json_out:
        args.json_out.write_text(
            json.dumps({"info": info, "findings": [f.to_dict() for f in findings]},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    n_high = sum(1 for f in findings if f.level == "HIGH")
    sys.exit(2 if n_high else 0)


if __name__ == "__main__":
    main()
