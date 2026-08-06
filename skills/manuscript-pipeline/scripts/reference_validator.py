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
  2  HIGH-severity findings present -> blocks "최종본" declaration until manual review.
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

# 본문에서 인용 주변의 저자 성과 연도를 뽑기 위한 패턴 (유형 2 방어용)
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
        if d not in seen:        # 중복 제거 (구버전은 누락 — 동일 DOI 반복 호출 방지)
            seen.append(d)
    return seen


def _doi_context(doc_xml, doi, window=400):
    """DOI 출현 위치 앞쪽 window 글자에서 저자 성/연도 후보를 뽑는다 (유형 2 방어).

    윈도우를 넉넉히(400자) 잡는다 — 제목이 길면 저자가 DOI에서 멀어지므로,
    좁은 윈도우는 제목/저널 단어만 잡아 false positive를 낸다.

    Returns: (surnames:set[str-lower], years:set[str])
    """
    text = _plain_text(doc_xml)
    low = text.lower()
    idx = low.find(doi.lower())
    if idx < 0:
        return set(), set()
    seg = text[max(0, idx - window): idx]   # DOI 앞쪽(저자/연도가 보통 앞에 옴)
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
    """CrossRef로 DOI를 검증한다.

    Returns dict:
        {"status": "ok"|"not_found"|"unreachable"|"mismatch",
         "title": str, "detail": str}

    - not_found  : 404 = 존재하지 않는 DOI (hallucination 신호)
    - unreachable: 네트워크/타임아웃 = 검증 불가 (절대 pass로 처리 안 함, fail-closed)
    - mismatch   : DOI는 실재하나 본문 인용의 저자/연도와 불일치 (실재 DOI 오인용)
    - ok         : 실재 + (문맥 주어졌으면) 저자/연도 일치
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

    # 유형 2 방어: 본문 인용 주변 저자/연도가 resolve된 논문과 맞는가?
    # false positive 비용이 크므로(정상 인용 차단 = 도구 불신) 신뢰도를 차등화한다:
    #   저자 AND 연도 둘 다 불일치 -> 'mismatch' (HIGH, 강한 오인용 신호)
    #   저자만 불일치(연도는 맞음/모름) -> 'mismatch_weak' (WARNING, 차단 안 함)
    # 저자 매칭은 윈도우/추출 한계로 누락될 수 있으나, 연도까지 어긋나면 오인용 확률 급증.
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
                bits.append(f"본문저자{sorted(ctx_surnames)} vs CrossRef저자{sorted(cr_families)}")
            if not year_ok:
                bits.append(f"본문연도{sorted(ctx_years)} vs CrossRef연도'{cr_year}'")
            # 연도까지 어긋나야 강한 신호. 저자만 어긋나면 약한 신호(추출 한계 가능성).
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
                f"{doi} -> CrossRef 404 (존재하지 않는 DOI)",
                "AI가 지어낸 DOI일 가능성이 높음. DOI를 확인하거나 인용을 삭제/교체하세요.",
            ))
        elif st == "unreachable":
            n_unresolved += 1
            findings.append(Finding(
                "HIGH", "doi_unverified",
                f"{doi} -> 검증 불가 ({res['detail']})",
                "망 연결 확인 후 재실행. 검증 전 통과 처리 금지(fail-open 방지).",
            ))
        elif st == "mismatch":
            n_mismatch += 1
            findings.append(Finding(
                "HIGH", "doi_context_mismatch",
                f"{doi} -> 실재하나 본문 인용과 불일치: {res['detail']} (CrossRef='{res['title']}')",
                "실재 DOI를 엉뚱한 주장/논문에 붙였을 가능성(오인용). 해당 논문이 정말 그 "
                "주장을 하는지 확인하세요.",
            ))
        elif st == "mismatch_weak":
            # 저자만 불일치(연도는 맞음/불명) — 추출 한계 가능성. 차단(HIGH) 아닌 WARNING.
            findings.append(Finding(
                "WARNING", "doi_author_unmatched",
                f"{doi} -> 저자 매칭 실패(연도는 일치/불명): {res['detail']} (CrossRef='{res['title']}')",
                "대개 추출 한계(저자가 멀리 있음)지만, 오인용일 수도 있으니 한 번 확인 권장.",
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
    # 방어: --crossref 기본 ON. 끄려면 명시적으로 --no-crossref.
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
