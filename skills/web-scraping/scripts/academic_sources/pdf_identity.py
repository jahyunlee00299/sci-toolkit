"""Downloaded-file identity verification.

Real incident: a download for one DOI silently resolved to an unrelated paper
(a decades-old humanities article from a different journal/publisher, hundreds
of KB, PDF-shaped). The manifest recorded it as status=success.

The only check at the time was "size > 1 KB", so the wrong file sailed
through - it never even checked the magic bytes (%PDF-). "A file arrived"
and "the requested paper arrived" are not the same claim. If this isn't
caught at download time, catching it later means auditing every file by
hand - so it's enforced here instead.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

_PDF_STOPWORDS = {
    "the", "and", "for", "from", "with", "via", "using", "a", "an", "of", "in",
    "on", "to", "by", "its", "into", "at", "as", "is", "are", "be", "new", "novel",
    "study", "approach", "analysis", "effect", "effects", "role",
}


def _title_tokens(text: str) -> set:
    return {w for w in re.findall(r"[a-z]{4,}", (text or "").lower())
            if w not in _PDF_STOPWORDS}


def _read_pdf_text(path: "Path") -> tuple[Optional[str], Optional[dict]]:
    """First two pages' text, or (None, early verdict) when the file is not usable.

    Early verdicts: not_pdf (unreadable / wrong magic bytes / unparsable) and
    no_text (almost no body text, likely a scanned copy).
    """
    try:
        with path.open("rb") as handle:
            head = handle.read(5)
    except Exception as exc:
        return None, {"verdict": "not_pdf", "score": 0,
                      "reasons": [f"could not open: {type(exc).__name__}"]}
    if head != b"%PDF-":
        return None, {"verdict": "not_pdf", "score": 0,
                      "reasons": [f"magic bytes are not %PDF- ({head!r}) — possibly an error/login page"]}

    try:
        try:
            from pypdf import PdfReader
        except ImportError:                                     # pragma: no cover
            from PyPDF2 import PdfReader                          # type: ignore
        reader = PdfReader(str(path))
        n_pages = len(reader.pages)
        text = " ".join(
            " ".join((reader.pages[i].extract_text() or "").split())
            for i in range(min(2, n_pages))
        )
    except Exception as exc:
        return None, {"verdict": "not_pdf", "score": 0,
                      "reasons": [f"PDF parsing failed: {type(exc).__name__} — corrupted file"]}

    if len(text.strip()) < 200:
        # Might be a scanned copy. Don't auto-decide — hand it to a human.
        return None, {"verdict": "no_text", "score": 0,
                      "reasons": ["almost no body text (likely a scanned copy) — needs visual check"]}
    return text, None


def _identity_score(text: str, doi: str, expected: dict) -> tuple[int, list]:
    """Sum the independent signals: body DOI (+3), title tokens (+3/2/1),
    first author (+2), journal (+1), year (+1)."""
    reasons: list = []
    low = text.lower()
    score = 0

    if doi and doi.lower() in low:
        score += 3
        reasons.append("DOI present in body (+3)")
    elif doi:
        reasons.append("DOI not present in body")

    exp_title = expected.get("title") or ""
    tt = _title_tokens(exp_title)
    if tt:
        overlap = len(tt & _title_tokens(text)) / len(tt)
        if overlap >= 0.6:
            score += 3
        elif overlap >= 0.35:
            score += 2
        elif overlap >= 0.2:
            score += 1
        reasons.append(f"title token overlap {overlap:.0%}")

    fa = (expected.get("first_author") or "").lower()
    if len(fa) >= 3:
        if fa in low:
            score += 2
            reasons.append(f"first author '{fa}' confirmed (+2)")
        else:
            reasons.append(f"first author '{fa}' not present in body")

    jt = _title_tokens(expected.get("journal") or "")
    if jt and len(jt & _title_tokens(text)) / len(jt) >= 0.5:
        score += 1
        reasons.append("journal name matches (+1)")

    yr = expected.get("year")
    if yr and str(yr) in text:
        score += 1
        reasons.append(f"year {yr} confirmed (+1)")
    return score, reasons


def verify_pdf_identity(path: "Path", doi: str = "",
                        expected: Optional[dict] = None) -> dict:
    """Check whether the received PDF is *the requested paper*.

    Never decides on a single signal — a year or journal matching by chance
    alone would otherwise pass. Sums body DOI (+3), title tokens (+3/2/1),
    first author (+2), journal (+1), year (+1); >=5 = ok, 3-4 = suspect,
    below that = mismatch.

    expected = {"title","first_author","journal","year"} (built from the
    Crossref record). If expected is absent, only the magic-bytes/structure
    check runs (weak verification).

    Returns: {"verdict","score","reasons"} — verdict is one of
    ok/suspect/mismatch/not_pdf/no_text.
    """
    text, early = _read_pdf_text(path)
    if early is not None:
        return early

    if not expected:
        return {"verdict": "ok", "score": 0,
                "reasons": ["no expected metadata — only magic bytes/structure checked (weak verification)"]}

    score, reasons = _identity_score(text, doi, expected)
    verdict = "ok" if score >= 5 else ("suspect" if score >= 3 else "mismatch")
    return {"verdict": verdict, "score": score, "reasons": reasons}


def check_downloaded_pdf(dest: Path, doi: str, expected: Optional[dict],
                         source: str, size: int) -> dict:
    """Verify a downloaded file and build the status dict the downloaders return.

    A mismatching or non-PDF file is quarantined (renamed to ``*.REJECTED``),
    never deleted, so it stays diagnosable. Sources 1-3 and EZproxy share this
    gate; size alone proves nothing (a paywall or SSO page is larger than 1 KB).
    """
    ident = verify_pdf_identity(dest, doi=doi, expected=expected)
    if ident["verdict"] in ("mismatch", "not_pdf"):
        quarantine = dest.with_suffix(dest.suffix + ".REJECTED")
        dest.replace(quarantine)      # quarantined, not deleted — must stay diagnosable
        return {
            "downloaded_path": None,
            "download_source": source,
            "download_status": (
                f"identity {ident['verdict']} (score={ident['score']}): "
                + "; ".join(ident["reasons"][:3])
                + f" -> quarantined: {quarantine.name}"
            ),
            "identity": ident,
        }
    return {
        "downloaded_path": str(dest),
        "download_source": source,
        "download_status": "ok" if ident["verdict"] == "ok"
                           else f"ok (identity {ident['verdict']}, score={ident['score']})",
        "size_bytes": size,
        "identity": ident,
    }
