#!/usr/bin/env python3
"""DOI cross-verification tool — a gate script that checks whether a DOI
already placed into a manuscript/document actually exists and whether its
bibliographic data is correct.

Distinct in role from `ref_fetch.py` (for collection: DOI -> bibliographic
data + OA PDF). This script is for **verification**: it grades a DOI already
embedded in a document/BibTeX by checking (a) whether it actually exists,
(b) whether the stated author/year/title matches the real record, and
(c) whether it has been retracted. It is the gate tool named in AGENTS.md §8's
"literature-review / endnote-citation-injection" row — it stops a
hallucinated DOI from making it into a manuscript.

Reuse: the CrossRef/OpenAlex lookup functions, normalization, and cache are
imported directly from `ref_fetch.py`/`ref_cache_manager.py` as-is. Lookup
logic is not rewritten here (a duplicated implementation is how two tools end
up giving different answers).

Verification grades (descending severity):
    HALLUCINATED    — does not exist in either CrossRef or OpenAlex
    RETRACTED       — OpenAlex reports is_retracted=True
    MISMATCH        — exists, but the document's stated author/year/title
                      differs from the real record
    UNCORROBORATED  — existence is confirmed, but there is no title/author/year
                      to check it against, so whether it's "the right paper" is
                      unconfirmed. "exists" != "is the paper I was looking for"
    ONE_SOURCE_ONLY — found in only one of the two sources (never silently
                      passed)
    UNVERIFIED      — the lookup itself failed (network error, etc.) —
                      "couldn't confirm" != "fine"
    OK              — existence confirmed + metadata matches + not retracted

Why UNCORROBORATED exists as its own grade (measured, 260807):
    The LLM-generated 10.1016/j.biortech.2019.122211 does not exist. But
    122213, just +2 away in the same sequential range, is a *real, unrelated
    paper* (a chromium-reduction paper turned up while looking for a catalysis
    paper). In a sequential DOI range (Elsevier j.xxx.YYYY.NNNNNN, Wiley, ACS),
    a single-digit error produces not "a DOI that doesn't exist" but "a
    different paper". A nonexistent DOI fails loudly; this one passes quietly
    — which is why the grade is split out.

exit code:
    2 — at least one HALLUCINATED or RETRACTED item
    1 — (when not 2) at least one MISMATCH/ONE_SOURCE_ONLY/UNVERIFIED item,
        or an UNCORROBORATED item on the strict path (--doi / --doi-source)
    0 — everything else. UNCORROBORATED from a --file bulk scan falls here,
        but the summary must always print "how many items couldn't be
        corroborated" (never a silent pass)

Usage:
    # auto-extract DOIs from a document
    python doi_verify.py --file manuscript.md

    # specify DOIs directly
    python doi_verify.py --doi 10.1038/nature12373,10.9999/nonexistent.12345

    # BibTeX — checks author/year/title too
    python doi_verify.py --bibtex refs.bib

    # check one DOI against the "intended title" — catches a real but
    # unrelated paper
    python doi_verify.py --doi 10.1016/j.biortech.2019.122213 \
        --expect-title "Photocatalytic hydrogen evolution over nitrogen-doped titania"

    # an LLM-generated DOI — cannot even enter the lookup step without a
    # declared title
    python doi_verify.py --doi <DOI> --doi-source model --expect-title "..."

    # ignore the cache and force a re-lookup
    python doi_verify.py --doi 10.1038/nature12373 --refresh

    # contact email for the Unpaywall etc. polite pool (do not hardcode a
    # real email in code)
    python doi_verify.py --bibtex refs.bib --email you@example.com
    # or: export SCITK_CONTACT_EMAIL=you@example.com

Output:
    doi_verify_report.json (grade + rationale per DOI) + a human-readable
    stdout summary (grouped by grade: HALLUCINATED -> RETRACTED -> MISMATCH ->
    ONE_SOURCE_ONLY -> UNVERIFIED -> OK)
"""
from __future__ import annotations

import argparse
import difflib
import io
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Optional

# Reuse ref_fetch.py / ref_cache_manager.py (same scripts/ folder).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ref_cache_manager import RefCacheManager  # noqa: E402
from ref_fetch import (  # noqa: E402
    OPENALEX_BASE,
    _RATE_LIMIT_DELAY,
    _http_get_json,
    normalize_doi,
    query_crossref,
    query_openalex,
)
import urllib.parse  # noqa: E402

# Windows' default console is cp949, which dies on Korean/symbol output. Force
# UTF-8. reconfigure instead of TextIOWrapper — a wrapper owns the underlying
# stream, so if this module is later GC'd or another module wraps it again,
# the shared buffer gets closed and it dies with "I/O operation on closed
# file" (measured). reconfigure mutates the same object in place, so it's
# safe no matter how many times it's called or in what import order.
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")

# Regex that pulls DOIs out of a document (.md/.txt). Trailing punctuation/
# brackets commonly attached after a DOI are stripped — otherwise something
# like "10.1038/nature12373." ends up with the period folded into the DOI
# and the lookup always fails.
_DOI_EXTRACT_RE = re.compile(r"10\.\d{4,9}/[^\s\]\)\"'<>,;]+")
_TRAILING_PUNCT_RE = re.compile(r"[.,;:)\]\"'>]+$")

# One BibTeX entry (brace balance is ignored — only top-level fields are
# pulled out with a regex; input complex enough to need a full BibTeX parser
# is out of scope)
_BIBTEX_ENTRY_RE = re.compile(r"@\w+\s*\{\s*([^,]+),(.*?)\n\}", re.DOTALL)
_BIBTEX_FIELD_RE = re.compile(r"(\w+)\s*=\s*[{\"](.*?)[}\"]\s*,?\s*$", re.MULTILINE | re.DOTALL)


# --------------------------------------------------------------------------- #
# OpenAlex retracted status — ref_fetch.py's query_openalex() doesn't return
# this field (it only builds a processed bibliographic dict), so this reuses
# just the low-level _http_get_json helper to thinly pull is_retracted out of
# the raw response. query_openalex itself is not reimplemented — this
# function layers on exactly one piece of extra information.
# --------------------------------------------------------------------------- #


def query_openalex_retracted(doi: str, email: Optional[str]) -> Optional[bool]:
    """Return just the is_retracted value from the raw OpenAlex response. None on lookup failure."""
    url = f"{OPENALEX_BASE}/doi:{urllib.parse.quote(doi)}"
    if email:
        url += f"?mailto={urllib.parse.quote(email)}"
    data, err = _http_get_json(url, email)
    if err or not data:
        return None
    return bool(data.get("is_retracted", False))


# --------------------------------------------------------------------------- #
# DOI extraction
# --------------------------------------------------------------------------- #


def extract_dois_from_text(text: str) -> list[str]:
    """Extract DOIs out of free text (.md/.txt) with a regex (dedup, order preserved)."""
    found = []
    seen = set()
    for m in _DOI_EXTRACT_RE.finditer(text):
        raw = m.group(0)
        cleaned = _TRAILING_PUNCT_RE.sub("", raw)
        doi = normalize_doi(cleaned)
        if doi and doi not in seen:
            seen.add(doi)
            found.append(doi)
    return found


def parse_bibtex(text: str) -> list[dict[str, Any]]:
    """Parse BibTeX entries and pull out the doi/author/year/title fields.

    Full BibTeX syntax is not supported (a field with nested braces, etc. is
    handled only best-effort) — this tool's purpose is checking DOI
    existence/metadata, not being a BibTeX parser.
    """
    entries = []
    for m in _BIBTEX_ENTRY_RE.finditer(text):
        key = m.group(1).strip()
        body = m.group(2)
        fields: dict[str, str] = {}
        for fm in _BIBTEX_FIELD_RE.finditer(body):
            fname = fm.group(1).strip().lower()
            fval = re.sub(r"\s+", " ", fm.group(2)).strip()
            fields[fname] = fval

        doi = fields.get("doi")
        if not doi:
            continue
        doi = normalize_doi(doi)

        year = None
        year_str = fields.get("year", "")
        ym = re.search(r"\d{4}", year_str)
        if ym:
            year = int(ym.group(0))

        entries.append(
            {
                "key": key,
                "doi": doi,
                "author_raw": fields.get("author"),
                "year": year,
                "title": fields.get("title"),
            }
        )
    return entries


# --------------------------------------------------------------------------- #
# Metadata comparison (avoiding false positives is the core concern — never
# raise a MISMATCH from a notation difference alone)
# --------------------------------------------------------------------------- #


def _normalize_title(s: Optional[str]) -> str:
    if not s:
        return ""
    s = s.lower()
    s = re.sub(r"[^\w\s]", "", s)  # strip punctuation (absorbs case/punctuation differences)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def title_similarity(a: Optional[str], b: Optional[str]) -> float:
    """SequenceMatcher similarity after normalization (0-1). Robust to punctuation/case differences."""
    na, nb = _normalize_title(a), _normalize_title(b)
    if not na or not nb:
        return 0.0
    return difflib.SequenceMatcher(None, na, nb).ratio()


def _extract_surnames(author_field: Optional[str]) -> list[str]:
    """Extract only surnames from a BibTeX author field.

    Supports both BibTeX conventions: "Family, Given" and "Given Family".
    Authors are separated by " and ". Name notation (initials vs. full name,
    presence of a middle name) varies by source (CrossRef vs. OpenAlex differ
    too — observed in ref_fetch.py), so only the surname is used for
    comparison.
    """
    if not author_field:
        return []
    surnames = []
    for part in author_field.split(" and "):
        part = part.strip()
        if not part:
            continue
        if "," in part:
            surname = part.split(",", 1)[0].strip()
        else:
            tokens = part.split()
            surname = tokens[-1].strip() if tokens else ""
        if surname:
            surnames.append(surname.lower())
    return surnames


def _extract_surnames_from_names(names: list[str]) -> list[str]:
    """Extract only surnames from a CrossRef/OpenAlex "Given Family" name list."""
    surnames = []
    for name in names:
        tokens = name.strip().split()
        if tokens:
            surnames.append(tokens[-1].lower())
    return surnames


def compare_metadata(
    expected: dict[str, Any],
    crossref: dict[str, Any],
    openalex: dict[str, Any],
) -> list[str]:
    """Compare the metadata stated in the document/BibTeX against the real
    record (CrossRef first, OpenAlex if not found there). Returns a list of
    mismatch-reason strings (empty means it matches).

    False-positive-avoidance principle: a title is flagged only when the
    normalized similarity falls below the threshold, and an author only when
    the "surname sets" don't overlap at all — a notation difference alone
    (initials vs. full name, case, punctuation) never produces a MISMATCH.
    """
    reasons: list[str] = []
    record = crossref if crossref.get("found") else openalex
    if not record.get("found"):
        return reasons  # non-existence is already handled by HALLUCINATED — skip here

    # year — flag if it's exactly different (a year has no room for notation variance)
    exp_year = expected.get("year")
    rec_year = record.get("year")
    if exp_year and rec_year and int(exp_year) != int(rec_year):
        reasons.append(f"year mismatch — expected: {exp_year} | actual: {rec_year}")

    # title — flag only when normalized similarity is below 0.7
    exp_title = expected.get("title")
    rec_title = record.get("title")
    if exp_title and rec_title:
        sim = title_similarity(exp_title, rec_title)
        if sim < 0.7:
            reasons.append(
                f"title mismatch (similarity={sim:.2f}) — expected: {exp_title!r} | actual: {rec_title!r}"
            )

    # author — flag only when the surname sets don't overlap at all (ignore notation differences)
    exp_surnames = set(_extract_surnames(expected.get("author_raw")))
    rec_surnames = set(_extract_surnames_from_names(record.get("authors") or []))
    if exp_surnames and rec_surnames and exp_surnames.isdisjoint(rec_surnames):
        reasons.append(
            f"author mismatch — expected surnames: {sorted(exp_surnames)} | "
            f"actual surnames: {sorted(rec_surnames)}"
        )

    return reasons


# --------------------------------------------------------------------------- #
# Grade determination
# --------------------------------------------------------------------------- #

GRADE_ORDER = [
    "HALLUCINATED",
    "RETRACTED",
    "MISMATCH",
    "UNCORROBORATED",
    "ONE_SOURCE_ONLY",
    "UNVERIFIED",
    "OK",
]


def grade_one(
    doi: str,
    expected: Optional[dict[str, Any]],
    crossref: dict[str, Any],
    openalex: dict[str, Any],
) -> dict[str, Any]:
    """Determine the grade for a single DOI. (crossref/openalex are each in
    the found + error, etc. return format of ref_fetch.py's
    query_crossref/query_openalex.)
    """
    cr_ok = crossref.get("found") is True
    oa_ok = openalex.get("found") is True

    cr_network_fail = not cr_ok and crossref.get("error") not in (None, "not_found")
    oa_network_fail = not oa_ok and openalex.get("error") not in (None, "not_found")

    reasons: list[str] = []

    # Both lookups failed at the network level (existence cannot be determined) -> UNVERIFIED
    if cr_network_fail and oa_network_fail:
        return {
            "doi": doi,
            "grade": "UNVERIFIED",
            "reasons": [
                f"CrossRef lookup failed: {crossref.get('error')}",
                f"OpenAlex lookup failed: {openalex.get('error')}",
            ],
            "crossref": crossref,
            "openalex": openalex,
        }

    # One side failed at the network level, the other is a confirmed not_found
    # -> existence is uncertain -> UNVERIFIED
    # (the failed side might actually exist, so this is not asserted as HALLUCINATED)
    if cr_network_fail and not oa_ok:
        return {
            "doi": doi,
            "grade": "UNVERIFIED",
            "reasons": [
                f"CrossRef lookup failed (network): {crossref.get('error')}",
                "OpenAlex: not_found — neither source could confirm it, so not asserted as HALLUCINATED",
            ],
            "crossref": crossref,
            "openalex": openalex,
        }
    if oa_network_fail and not cr_ok:
        return {
            "doi": doi,
            "grade": "UNVERIFIED",
            "reasons": [
                f"OpenAlex lookup failed (network): {openalex.get('error')}",
                "CrossRef: not_found — neither source could confirm it, so not asserted as HALLUCINATED",
            ],
            "crossref": crossref,
            "openalex": openalex,
        }

    # Both sides clearly report non-existence (404, etc.; not a network failure) -> HALLUCINATED
    if not cr_ok and not oa_ok:
        return {
            "doi": doi,
            "grade": "HALLUCINATED",
            "reasons": [
                f"CrossRef: {crossref.get('error', 'not_found')}",
                f"OpenAlex: {openalex.get('error', 'not_found')}",
                "Neither source found this DOI — likely a hallucinated DOI",
            ],
            "crossref": crossref,
            "openalex": openalex,
        }

    # Retracted status (OpenAlex is_retracted)
    if oa_ok and openalex.get("is_retracted"):
        reasons.append("OpenAlex: is_retracted=True — this paper has been retracted")
        return {
            "doi": doi,
            "grade": "RETRACTED",
            "reasons": reasons,
            "crossref": crossref,
            "openalex": openalex,
        }

    # found in only one source
    if cr_ok != oa_ok:
        which = "CrossRef" if cr_ok else "OpenAlex"
        missing = "OpenAlex" if cr_ok else "CrossRef"
        missing_err = (openalex if cr_ok else crossref).get("error", "not_found")
        return {
            "doi": doi,
            "grade": "ONE_SOURCE_ONLY",
            "reasons": [f"confirmed only in {which} ({missing}: {missing_err}) — never silently passed"],
            "crossref": crossref,
            "openalex": openalex,
        }

    # found in both — compare metadata (only when expected is given)
    if expected:
        mismatch_reasons = compare_metadata(expected, crossref, openalex)
        if mismatch_reasons:
            return {
                "doi": doi,
                "grade": "MISMATCH",
                "reasons": mismatch_reasons,
                "crossref": crossref,
                "openalex": openalex,
            }

    # With no metadata to compare against at all, only "it exists" has been
    # confirmed. That must not be called OK — a single-digit error in a
    # sequential DOI range lands on a *real, unrelated paper* (see the
    # 122211/122213 measurement in the module docstring).
    if not expected:
        return {
            "doi": doi,
            "grade": "UNCORROBORATED",
            "reasons": [
                "existence confirmed (both CrossRef+OpenAlex) — but no "
                "title/author/year was given to check against, so whether "
                "this is 'the paper being looked for' is unconfirmed. "
                "Pass the intended title with --expect-title."
            ],
            "crossref": crossref,
            "openalex": openalex,
        }

    return {
        "doi": doi,
        "grade": "OK",
        "reasons": ["existence confirmed (both CrossRef+OpenAlex), metadata matches"],
        "crossref": crossref,
        "openalex": openalex,
    }


# --------------------------------------------------------------------------- #
# Main verify-one pipeline (reuses the cache)
# --------------------------------------------------------------------------- #


def verify_one(
    doi: str,
    expected: Optional[dict[str, Any]],
    cache: RefCacheManager,
    email: Optional[str],
    refresh: bool,
) -> dict[str, Any]:
    doi = normalize_doi(doi)

    if not _DOI_RE.match(doi):
        return {
            "doi": doi,
            "grade": "HALLUCINATED",
            "reasons": [f"not a DOI-shaped string: {doi!r} — likely fabricated from the format up"],
            "crossref": {"found": False, "error": "invalid_format"},
            "openalex": {"found": False, "error": "invalid_format"},
        }

    cache_key = f"doi_verify:{doi}"
    if not refresh and cache.has(cache_key):
        cached = cache.get(cache_key)
        if cached:
            crossref = cached.get("crossref", {})
            openalex = cached.get("openalex", {})
            result = grade_one(doi, expected, crossref, openalex)
            result["from_cache"] = True
            return result

    crossref = query_crossref(doi, email)
    time.sleep(_RATE_LIMIT_DELAY)
    openalex = query_openalex(doi, email)
    time.sleep(_RATE_LIMIT_DELAY)

    # Only look up retracted status when existence is confirmed — avoids
    # adding unnecessary network calls.
    if openalex.get("found"):
        is_retracted = query_openalex_retracted(doi, email)
        time.sleep(_RATE_LIMIT_DELAY)
        openalex = dict(openalex)
        openalex["is_retracted"] = is_retracted

    # Cache the lookup result (the raw data needed to judge existence) — do
    # not cache a network-failure result (which would lead to UNVERIFIED),
    # since it could be a transient error.
    cr_network_fail = not crossref.get("found") and crossref.get("error") not in (None, "not_found")
    oa_network_fail = not openalex.get("found") and openalex.get("error") not in (None, "not_found")
    if not (cr_network_fail or oa_network_fail):
        cache.put(cache_key, {"crossref": crossref, "openalex": openalex})

    result = grade_one(doi, expected, crossref, openalex)
    result["from_cache"] = False
    return result


# --------------------------------------------------------------------------- #
# Input collection
# --------------------------------------------------------------------------- #


def collect_targets(args: argparse.Namespace) -> list[dict[str, Any]]:
    """Build the list of verification targets. Each item is at minimum
    {"doi": ...}; for BibTeX input it also includes author_raw/year/title.
    """
    targets: list[dict[str, Any]] = []
    seen_dois: set[str] = set()

    def _add(doi: str, expected: Optional[dict[str, Any]] = None) -> None:
        nd = normalize_doi(doi)
        if nd in seen_dois:
            return
        seen_dois.add(nd)
        targets.append({"doi": nd, "expected": expected})

    if args.doi:
        for part in args.doi.split(","):
            part = part.strip()
            if part:
                _add(part, {"title": args.expect_title} if getattr(args, "expect_title", None) else None)

    if args.file:
        p = Path(args.file)
        if not p.exists():
            print(f"[ERROR] file not found: {p}", file=sys.stderr)
        else:
            text = p.read_text(encoding="utf-8", errors="replace")
            for doi in extract_dois_from_text(text):
                _add(doi)

    if args.bibtex:
        p = Path(args.bibtex)
        if not p.exists():
            print(f"[ERROR] file not found: {p}", file=sys.stderr)
        else:
            text = p.read_text(encoding="utf-8", errors="replace")
            entries = parse_bibtex(text)
            if not entries:
                print(f"[WARN] no entry with a doi field found in BibTeX: {p}", file=sys.stderr)
            for e in entries:
                _add(
                    e["doi"],
                    expected={"author_raw": e.get("author_raw"), "year": e.get("year"), "title": e.get("title")},
                )

    return targets


# --------------------------------------------------------------------------- #
# Human-readable summary output
# --------------------------------------------------------------------------- #


def print_summary(results: list[dict[str, Any]]) -> None:
    print("\n=== doi_verify results summary ===")
    print(f"  total DOIs: {len(results)}")

    by_grade: dict[str, list[dict[str, Any]]] = {g: [] for g in GRADE_ORDER}
    for r in results:
        by_grade.setdefault(r["grade"], []).append(r)

    for grade in GRADE_ORDER:
        items = by_grade.get(grade, [])
        print(f"  {grade}: {len(items)}")

    for grade in GRADE_ORDER:
        items = by_grade.get(grade, [])
        if not items:
            continue
        print(f"\n--- {grade} ({len(items)}) ---")
        for r in items:
            print(f"  [{r['doi']}]")
            for reason in r.get("reasons", []):
                print(f"      - {reason}")


def exit_code_for(results: list[dict[str, Any]], strict_uncorroborated: bool = False) -> int:
    """Grade list -> exit code.

    strict_uncorroborated decides whether UNCORROBORATED (exists but nothing
    to check it against) counts as a failure. Why it differs by path:

      Arriving via --doi to verify a specific DOI, and passing it after only
      confirming "it exists" is effectively not verifying it at all ->
      strict (=exit 1).

      Sweeping a whole manuscript with --file has structurally no way to get
      a title, so nearly every DOI ends up UNCORROBORATED. Making that
      exit 1 turns the gate permanently yellow, and a gate that's always
      yellow gets ignored — which is the same as having no gate ->
      non-strict (=exit 0, but the summary conspicuously states the count
      instead).
    """
    grades = {r["grade"] for r in results}
    if "HALLUCINATED" in grades or "RETRACTED" in grades:
        return 2
    if "MISMATCH" in grades or "ONE_SOURCE_ONLY" in grades or "UNVERIFIED" in grades:
        return 1
    if strict_uncorroborated and "UNCORROBORATED" in grades:
        return 1
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Cross-verify whether a DOI already placed in a "
        "document/BibTeX actually exists and whether its bibliographic data "
        "is correct, checking both CrossRef+OpenAlex (a hallucinated-DOI "
        "gate, no API key required).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--doi", help="comma-separated DOI list (specified directly)")
    parser.add_argument("--file", help="auto-extract DOIs from .md/.txt etc. with a regex")
    parser.add_argument("--bibtex", help="BibTeX file — also checks doi against author/year/title")
    parser.add_argument(
        "--email",
        default=None,
        help="contact email for the polite pool (falls back to the SCITK_CONTACT_EMAIL env var)",
    )
    parser.add_argument("--refresh", action="store_true", help="ignore the cache and force a re-lookup")
    parser.add_argument(
        "--output",
        default="doi_verify_report.json",
        help="path to save the result JSON to (default: doi_verify_report.json)",
    )
    parser.add_argument("--cache-dir", default=None, help="ref_cache_manager cache directory (default recommended)")
    parser.add_argument(
        "--expect-title",
        default=None,
        help="the paper title this DOI is intended to point to. Checked "
        "against the real record to catch a 'real but unrelated paper'. "
        "Use only together with a single --doi.",
    )
    parser.add_argument(
        "--doi-source",
        choices=["human", "model"],
        default=None,
        help="where the DOI came from. human=the user copied it directly "
        "from a browser/PDF, model=an LLM generated it from memory. model "
        "cannot enter without --expect-title.",
    )

    args = parser.parse_args()

    if not (args.doi or args.file or args.bibtex):
        print("[ERROR] one of --doi / --file / --bibtex is required.", file=sys.stderr)
        parser.print_help()
        return 1

    # --- DOI provenance gate ---------------------------------------------- #
    # An LLM-generated DOI can be wrong in content even with a perfect
    # format, and in a sequential range it lands on a real but unrelated
    # paper. So a model-sourced DOI must always declare "what it was trying
    # to find" alongside it, and without that declaration it cannot enter the
    # lookup at all. (Blocking it upstream is more reliable than filtering it
    # out by grade — a grade can be ignored by a human, but an entry block
    # cannot.)
    if args.doi_source == "model" and not args.expect_title:
        print(
            "[BLOCKED] --doi-source model cannot be used without --expect-title.\n"
            "          An LLM-generated DOI cannot be verified by existence "
            "alone — declare the title of the paper you were looking for "
            "alongside it.",
            file=sys.stderr,
        )
        return 2

    if args.expect_title and not args.doi:
        print("[ERROR] --expect-title can only be used together with --doi.", file=sys.stderr)
        return 1

    if args.expect_title and len([p for p in args.doi.split(",") if p.strip()]) != 1:
        print(
            "[ERROR] --expect-title can only be attached to a single DOI "
            "(sharing one title across multiple DOIs makes the comparison meaningless).",
            file=sys.stderr,
        )
        return 1

    email = args.email or os.getenv("SCITK_CONTACT_EMAIL") or None
    if not email:
        print(
            "[INFO] no --email / SCITK_CONTACT_EMAIL — looking up without "
            "the polite pool (may hit rate limits).",
            file=sys.stderr,
        )

    targets = collect_targets(args)
    if not targets:
        print("[ERROR] no DOIs to verify.", file=sys.stderr)
        return 1

    cache = RefCacheManager(cache_dir=args.cache_dir)

    results: list[dict[str, Any]] = []
    for i, t in enumerate(targets, 1):
        doi = t["doi"]
        print(f"[{i}/{len(targets)}] verifying: {doi}", file=sys.stderr)
        try:
            record = verify_one(doi, t.get("expected"), cache, email, args.refresh)
        except Exception as e:  # noqa: BLE001 — one DOI failing must not kill the whole run
            record = {
                "doi": doi,
                "grade": "UNVERIFIED",
                "reasons": [f"exception raised: {type(e).__name__}: {e}"],
                "crossref": {"found": False, "error": "exception"},
                "openalex": {"found": False, "error": "exception"},
            }
        results.append(record)

    output_path = Path(args.output)
    report = {
        "generated_by": "doi_verify.py",
        "dois_checked": len(targets),
        "email_used": bool(email),
        "grade_counts": {g: sum(1 for r in results if r["grade"] == g) for g in GRADE_ORDER},
        "results": results,
    }
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[OK] report saved: {output_path}", file=sys.stderr)

    print_summary(results)

    # Count UNCORROBORATED as a failure if a specific DOI was targeted via
    # --doi or a source was declared. A --file bulk scan has no way to get a
    # title, so nearly everything ends up UNCORROBORATED, and that is not
    # reflected in the exit code (see exit_code_for's docstring).
    strict = bool(args.doi or args.doi_source)
    code = exit_code_for(results, strict_uncorroborated=strict)

    n_uncorr = sum(1 for r in results if r["grade"] == "UNCORROBORATED")

    if code == 2:
        print("\n[FAIL] there are HALLUCINATED or RETRACTED items (exit 2).", file=sys.stderr)
    elif code == 1:
        print(
            "\n[WARN] there are MISMATCH/UNCORROBORATED/ONE_SOURCE_ONLY/UNVERIFIED "
            "items (exit 1).",
            file=sys.stderr,
        )
    elif n_uncorr:
        # Pass, but always say "what wasn't confirmed". A silent pass is
        # exactly the path that lets an existing-but-unrelated DOI into a
        # manuscript.
        print(
            f"\n[PASS] no blocking reason (exit 0) — but {n_uncorr} item(s) "
            "were only confirmed to 'exist', and whether that DOI is the "
            "intended paper was not checked.\n"
            "       To check the title too, pass it via --bibtex, or give "
            "an individual DOI --expect-title.",
            file=sys.stderr,
        )
    else:
        print("\n[PASS] all OK (exit 0).", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
