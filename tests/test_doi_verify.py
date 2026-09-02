#!/usr/bin/env python3
"""doi_verify.py regression test — pure logic that runs offline plus optional network tests.

Run: python tests/test_doi_verify.py   (exit 0 = pass)

Split into two groups:
  1) Parts that run without a network (always executed) — the DOI-extraction
     regex, BibTeX parsing, title similarity, author surname comparison, the
     grade-decision logic (grade_one), and exit-code mapping. Verified by
     injecting fake CrossRef/OpenAlex responses (dicts).
  2) Tests that need a real network — SKIP if there's no network, but must
     print "SKIP" explicitly (never pass silently).
"""
import importlib.util
import socket
import sys
from pathlib import Path

# The doi_verify module itself wraps sys.stdout/stderr from cp949 -> utf-8
# TextIOWrapper at import time (via ref_fetch.py). Wrapping again here would
# double-wrap and raise "I/O operation on closed file" (see the comment at
# the top of doi_verify.py), so this test file does not wrap separately and
# lets the module import handle it.

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

spec = importlib.util.spec_from_file_location("doi_verify", str(SCRIPTS / "doi_verify.py"))
doi_verify = importlib.util.module_from_spec(spec)
sys.modules["doi_verify"] = doi_verify
spec.loader.exec_module(doi_verify)


PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}  {detail}")


def section(title: str) -> None:
    print(f"\n=== {title} ===")


# --------------------------------------------------------------------------- #
# 1) DOI-extraction regex
# --------------------------------------------------------------------------- #

section("DOI extraction (extract_dois_from_text)")

text1 = "See 10.1038/nature12373 and also (10.1021/acs.jchemed.7b00361)."
dois1 = doi_verify.extract_dois_from_text(text1)
check(
    "extracts 2 DOIs wrapped in parens/whitespace",
    dois1 == ["10.1038/nature12373", "10.1021/acs.jchemed.7b00361"],
    f"got={dois1}",
)

text2 = "DOI: 10.1038/nature12373. Another sentence."
dois2 = doi_verify.extract_dois_from_text(text2)
check(
    "trailing period is not swept into the DOI",
    dois2 == ["10.1038/nature12373"],
    f"got={dois2}",
)

text3 = "dup 10.1038/nature12373 dup 10.1038/nature12373 once more"
dois3 = doi_verify.extract_dois_from_text(text3)
check("duplicates removed + order preserved", dois3 == ["10.1038/nature12373"], f"got={dois3}")

text4 = "no dois here at all"
dois4 = doi_verify.extract_dois_from_text(text4)
check("text with no DOI -> empty list", dois4 == [], f"got={dois4}")

text5 = "markdown link [paper](https://doi.org/10.1038/nature12373) end."
dois5 = doi_verify.extract_dois_from_text(text5)
check(
    "DOI inside a markdown link, trailing close-paren stripped",
    dois5 == ["10.1038/nature12373"],
    f"got={dois5}",
)


# --------------------------------------------------------------------------- #
# BibTeX parsing
# --------------------------------------------------------------------------- #

section("BibTeX parsing (parse_bibtex)")

bib_text = """
@article{kucsko2013,
  author = {Kucsko, G. and Maurer, P. C. and Yao, N. Y.},
  title = {Nanometre-scale thermometry in a living cell},
  year = {2013},
  doi = {10.1038/nature12373}
}

@article{noref,
  author = {Someone, A.},
  title = {No DOI here},
  year = {2020}
}
"""
entries = doi_verify.parse_bibtex(bib_text)
check("only the entry with a doi is picked up (1)", len(entries) == 1, f"got={len(entries)}")
if entries:
    e = entries[0]
    check("doi normalized", e["doi"] == "10.1038/nature12373", f"got={e['doi']!r}")
    check("year parsed", e["year"] == 2013, f"got={e['year']!r}")
    check(
        "title parsed",
        e["title"] == "Nanometre-scale thermometry in a living cell",
        f"got={e['title']!r}",
    )
    check(
        "author_raw preserved",
        "Kucsko" in (e["author_raw"] or ""),
        f"got={e['author_raw']!r}",
    )


# --------------------------------------------------------------------------- #
# Title similarity
# --------------------------------------------------------------------------- #

section("Title similarity (title_similarity) — avoid false positives")

sim_case = doi_verify.title_similarity(
    "Nanometre-scale thermometry in a living cell",
    "Nanometre-scale thermometry in a living cell",
)
check("identical title -> similarity 1.0", sim_case == 1.0, f"got={sim_case}")

sim_punct = doi_verify.title_similarity(
    "Nanometre-scale Thermometry in a Living Cell.",
    "nanometre scale thermometry in a living cell",
)
check(
    "case/punctuation-only difference -> high similarity (>=0.95), does not trigger MISMATCH",
    sim_punct >= 0.95,
    f"got={sim_punct}",
)

sim_diff = doi_verify.title_similarity(
    "Nanometre-scale thermometry in a living cell",
    "Completely unrelated paper about protein folding kinetics",
)
check("completely different title -> low similarity (<0.5)", sim_diff < 0.5, f"got={sim_diff}")


# --------------------------------------------------------------------------- #
# Author surname comparison (the key case for avoiding notation-difference false positives)
# --------------------------------------------------------------------------- #

section("Author surname comparison (compare_metadata) — avoid notation-difference false positives")

crossref_found = {
    "found": True,
    "title": "Nanometre-scale thermometry in a living cell",
    "year": 2013,
    "authors": ["G. Kucsko", "P. C. Maurer", "N. Y. Yao"],
}
openalex_found = {
    "found": True,
    "title": "Nanometre-scale thermometry in a living cell",
    "year": 2013,
    "authors": ["Georg Kucsko", "Peter C. Maurer", "Norman Y. Yao"],
}

expected_matching = {
    "author_raw": "Kucsko, G. and Maurer, P. C. and Yao, N. Y.",
    "year": 2013,
    "title": "Nanometre-scale thermometry in a living cell",
}
reasons_ok = doi_verify.compare_metadata(expected_matching, crossref_found, openalex_found)
check(
    "initials (G. Kucsko) vs full name (Georg Kucsko) alone does not raise MISMATCH",
    reasons_ok == [],
    f"got={reasons_ok}",
)

expected_case_diff = {
    "author_raw": "KUCSKO, Georg and MAURER, Peter",
    "year": 2013,
    "title": "NANOMETRE-SCALE THERMOMETRY IN A LIVING CELL",
}
reasons_case = doi_verify.compare_metadata(expected_case_diff, crossref_found, openalex_found)
check(
    "title case difference alone does not raise MISMATCH",
    reasons_case == [],
    f"got={reasons_case}",
)

expected_wrong_year = {
    "author_raw": "Kucsko, G.",
    "year": 1999,
    "title": "Nanometre-scale thermometry in a living cell",
}
reasons_year = doi_verify.compare_metadata(expected_wrong_year, crossref_found, openalex_found)
check(
    "an actually-different year is caught as a MISMATCH reason",
    any("year mismatch" in r for r in reasons_year),
    f"got={reasons_year}",
)

expected_wrong_author = {
    "author_raw": "Smith, John and Doe, Jane",
    "year": 2013,
    "title": "Nanometre-scale thermometry in a living cell",
}
reasons_author = doi_verify.compare_metadata(expected_wrong_author, crossref_found, openalex_found)
check(
    "zero overlap in author surnames is caught as a MISMATCH reason",
    any("author mismatch" in r for r in reasons_author),
    f"got={reasons_author}",
)

expected_wrong_title = {
    "author_raw": "Kucsko, G.",
    "year": 2013,
    "title": "A totally different paper about something else entirely",
}
reasons_title = doi_verify.compare_metadata(expected_wrong_title, crossref_found, openalex_found)
check(
    "an actually-different title is caught as a MISMATCH reason",
    any("title mismatch" in r for r in reasons_title),
    f"got={reasons_title}",
)


# --------------------------------------------------------------------------- #
# Grade decision logic (grade_one) — MUST DETECT cases
# --------------------------------------------------------------------------- #

section("Grade decision (grade_one) — MUST DETECT")

not_found = {"found": False, "error": "not_found"}
result_halluc = doi_verify.grade_one("10.9999/nonexistent.12345", None, not_found, not_found)
check(
    "a DOI that doesn't exist -> HALLUCINATED",
    result_halluc["grade"] == "HALLUCINATED",
    f"got={result_halluc['grade']}",
)

result_retracted = doi_verify.grade_one(
    "10.1234/retracted.example",
    None,
    crossref_found,
    {**openalex_found, "is_retracted": True},
)
check(
    "is_retracted=True -> RETRACTED",
    result_retracted["grade"] == "RETRACTED",
    f"got={result_retracted['grade']}",
)

result_mismatch = doi_verify.grade_one(
    "10.1038/nature12373",
    expected_wrong_year,
    crossref_found,
    {**openalex_found, "is_retracted": False},
)
check(
    "entry with a different year -> MISMATCH",
    result_mismatch["grade"] == "MISMATCH",
    f"got={result_mismatch['grade']}",
)

result_one_source = doi_verify.grade_one(
    "10.1038/nature12373",
    None,
    crossref_found,
    not_found,
)
check(
    "only one source has it -> ONE_SOURCE_ONLY",
    result_one_source["grade"] == "ONE_SOURCE_ONLY",
    f"got={result_one_source['grade']}",
)

network_fail = {"found": False, "error": "URLError: [Errno -2] Name or service not known"}
result_unverified_both = doi_verify.grade_one("10.1038/nature12373", None, network_fail, network_fail)
check(
    "both sources fail on network error -> UNVERIFIED (not HALLUCINATED)",
    result_unverified_both["grade"] == "UNVERIFIED",
    f"got={result_unverified_both['grade']}",
)

result_unverified_mixed = doi_verify.grade_one("10.1038/nature12373", None, network_fail, not_found)
check(
    "one network failure + one not_found -> UNVERIFIED (does not conclude HALLUCINATED)",
    result_unverified_mixed["grade"] == "UNVERIFIED",
    f"got={result_unverified_mixed['grade']}",
)

result_ok = doi_verify.grade_one(
    "10.1038/nature12373",
    expected_matching,
    crossref_found,
    {**openalex_found, "is_retracted": False},
)
check(
    "existence confirmed + metadata matches -> OK",
    result_ok["grade"] == "OK",
    f"got={result_ok['grade']}",
)

result_ok_no_expected = doi_verify.grade_one(
    "10.1038/nature12373",
    None,
    crossref_found,
    {**openalex_found, "is_retracted": False},
)
# [260807 contract change] Originally "existence confirmed with no expected
# title was still OK". That contract let a real incident through: the
# fabricated 10.1016/j.biortech.2019.122211 doesn't exist, but 122213 (+2)
# *is a real, unrelated paper* (chromium reduction), and passed the --doi
# path as OK/exit 0. This is a tightening, not a relaxation — narrowed
# OK (pass) -> UNCORROBORATED (not cross-checked).
check(
    "no expected title -> UNCORROBORATED, not OK (existing != being that paper)",
    result_ok_no_expected["grade"] == "UNCORROBORATED",
    f"got={result_ok_no_expected['grade']}",
)

invalid_format = doi_verify.grade_one  # placeholder to keep name defined below


# --------------------------------------------------------------------------- #
# verify_one's DOI-format-error path (the regex itself is checked before grade_one is called)
# --------------------------------------------------------------------------- #

section("DOI format error handling (verify_one)")


class _FakeCache:
    """A fake cache standing in for RefCacheManager — has() always returns False."""

    def has(self, key):  # noqa: ANN001
        return False

    def get(self, key):  # noqa: ANN001
        return None

    def put(self, key, value):  # noqa: ANN001
        pass


bad_doi_result = doi_verify.grade_one("not-a-doi", None, not_found, not_found)
# grade_one itself doesn't check the format, so verify this via the verify_one path
if not doi_verify._DOI_RE.match("not-a-doi"):
    check("the DOI regex rejects a malformed string", True)
else:
    check("the DOI regex rejects a malformed string", False)


# --------------------------------------------------------------------------- #
# exit-code mapping
# --------------------------------------------------------------------------- #

section("exit-code mapping (exit_code_for)")

results_halluc = [{"grade": "HALLUCINATED"}, {"grade": "OK"}]
check("HALLUCINATED present -> exit 2", doi_verify.exit_code_for(results_halluc) == 2)

results_retracted = [{"grade": "RETRACTED"}, {"grade": "MISMATCH"}]
check("RETRACTED present (even alongside MISMATCH) -> exit 2 (the more severe grade wins)", doi_verify.exit_code_for(results_retracted) == 2)

results_mismatch = [{"grade": "MISMATCH"}, {"grade": "OK"}]
check("MISMATCH only -> exit 1", doi_verify.exit_code_for(results_mismatch) == 1)

results_one_source = [{"grade": "ONE_SOURCE_ONLY"}]
check("ONE_SOURCE_ONLY only -> exit 1", doi_verify.exit_code_for(results_one_source) == 1)

results_unverified = [{"grade": "UNVERIFIED"}]
check("UNVERIFIED only -> exit 1 (a network failure is not treated as a pass)", doi_verify.exit_code_for(results_unverified) == 1)

results_ok = [{"grade": "OK"}, {"grade": "OK"}]
check("all OK -> exit 0", doi_verify.exit_code_for(results_ok) == 0)

# UNCORROBORATED's exit code depends on which path it came in through.
#   Arriving via --doi for a specific DOI: "existence confirmed only" is not
#   verification -> 1.
#   A --file bulk scan has no way to obtain a title, so nearly everything
#   ends up UNCORROBORATED. Assigning it 1 there would make it permanently
#   yellow, and a gate that's always yellow gets ignored.
results_uncorr = [{"grade": "UNCORROBORATED"}, {"grade": "OK"}]
check(
    "UNCORROBORATED, strict (the --doi path) -> exit 1",
    doi_verify.exit_code_for(results_uncorr, strict_uncorroborated=True) == 1,
)
check(
    "UNCORROBORATED, non-strict (--file bulk scan) -> exit 0 (avoids alert fatigue)",
    doi_verify.exit_code_for(results_uncorr, strict_uncorroborated=False) == 0,
)
check(
    "regardless of strict mode, HALLUCINATED is always exit 2",
    doi_verify.exit_code_for(
        [{"grade": "UNCORROBORATED"}, {"grade": "HALLUCINATED"}],
        strict_uncorroborated=False,
    )
    == 2,
)
check(
    "default is non-strict (doesn't change behavior for existing --file callers)",
    doi_verify.exit_code_for(results_uncorr) == 0,
)


# --------------------------------------------------------------------------- #
# 2) Tests that need a network — SKIP if unavailable (never pass silently)
# --------------------------------------------------------------------------- #

section("Network tests")


_CROSSREF_PROBE = "https://api.crossref.org/works/10.1038/nature12373"


def _upstream_available() -> tuple[bool, str]:
    """(ok, reason). A TCP handshake is not enough — the host can accept the
    connection while the REST service answers 5xx (measured on Europe PMC
    2026-09-02). Probe the endpoint the tests call; a 5xx/429 is the other
    side's outage and skips the network group instead of failing it."""
    import os
    import urllib.error
    import urllib.request
    if os.environ.get("SCI_TOOLKIT_OFFLINE") == "1":
        return False, "network tests disabled by SCI_TOOLKIT_OFFLINE=1 (doctor.py --offline)"
    try:
        socket.create_connection(("api.crossref.org", 443), timeout=5).close()
    except OSError as exc:
        return False, f"no network connection ({exc.__class__.__name__})"
    try:
        with urllib.request.urlopen(urllib.request.Request(
                _CROSSREF_PROBE, headers={"User-Agent": "sci-toolkit-selftest"}), timeout=15) as r:
            return (r.status == 200), f"HTTP {r.status}"
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return True, "HTTP 404 (service up; record lookup is what the tests check)"
        return False, f"CrossRef upstream returned HTTP {exc.code}"
    except (urllib.error.URLError, OSError) as exc:
        return False, f"CrossRef unreachable ({exc.__class__.__name__}: {exc})"


_NET_OK, _NET_WHY = _upstream_available()

if _NET_OK:
    print("  Network available — running real API-call tests")

    valid_result = doi_verify.verify_one(
        "10.1038/nature12373", None, _FakeCache(), None, refresh=True
    )
    # Called with expected=None, so there's no title to cross-check against -> UNCORROBORATED is correct.
    check(
        "[network] valid DOI (10.1038/nature12373), no title -> UNCORROBORATED",
        valid_result["grade"] == "UNCORROBORATED",
        f"got={valid_result['grade']}, reasons={valid_result.get('reasons')}",
    )

    # Giving the same DOI its real title should pass as OK — guards against false positives.
    valid_with_title = doi_verify.verify_one(
        "10.1038/nature12373",
        {"title": "Nanometre-scale thermometry in a living cell"},
        _FakeCache(),
        None,
        refresh=True,
    )
    check(
        "[network] valid DOI + real title -> OK (no false positive)",
        valid_with_title["grade"] == "OK",
        f"got={valid_with_title['grade']}, reasons={valid_with_title.get('reasons')}",
    )

    fake_result = doi_verify.verify_one(
        "10.9999/nonexistent.12345", None, _FakeCache(), None, refresh=True
    )
    check(
        "[network] a DOI that doesn't exist -> HALLUCINATED",
        fake_result["grade"] == "HALLUCINATED",
        f"got={fake_result['grade']}",
    )

    real_expected = {
        "author_raw": "Kucsko, Georg and Maurer, Peter C.",
        "year": 2013,
        "title": "Nanometre-scale thermometry in a living cell",
    }
    real_meta_result = doi_verify.verify_one(
        "10.1038/nature12373", real_expected, _FakeCache(), None, refresh=True
    )
    check(
        "[network] real author-notation differences (e.g. Georg Kucsko) don't false-positive -> OK",
        real_meta_result["grade"] == "OK",
        f"got={real_meta_result['grade']}, reasons={real_meta_result.get('reasons')}",
    )

    # ----------------------------------------------------------------- #
    # Reproduces the 260807 incident: "exists, but is an unrelated paper"
    # The fabricated 10.1016/j.biortech.2019.122211 does not exist. But
    # 122213 (+2) does exist — a chromium-reduction paper unrelated to what
    # was being looked up. This case passed as OK/exit 0 before the patch.
    # Pinned here as a fixture.
    # ----------------------------------------------------------------- #
    UNRELATED_DOI = "10.1016/j.biortech.2019.122213"
    INTENDED = "Photocatalytic hydrogen evolution over nitrogen-doped titanium dioxide"

    unrelated_no_title = doi_verify.verify_one(
        UNRELATED_DOI, None, _FakeCache(), None, refresh=True
    )
    check(
        "[network] a DOI that exists but is unrelated, no title -> UNCORROBORATED (not OK)",
        unrelated_no_title["grade"] == "UNCORROBORATED",
        f"got={unrelated_no_title['grade']}",
    )

    unrelated_with_intent = doi_verify.verify_one(
        UNRELATED_DOI, {"title": INTENDED}, _FakeCache(), None, refresh=True
    )
    check(
        "[network] a DOI that exists but is unrelated + the intended title -> MISMATCH",
        unrelated_with_intent["grade"] == "MISMATCH",
        f"got={unrelated_with_intent['grade']}, reasons={unrelated_with_intent.get('reasons')}",
    )

    # ----------------------------------------------------------------- #
    # CLI gate: a model-sourced DOI can't even enter the lookup without a
    # declared title. Not measurable at the grade_one unit level — it's
    # blocked at the argument-parsing stage.
    # ----------------------------------------------------------------- #
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory() as _td:
        _proc = subprocess.run(
            [
                sys.executable, str(SCRIPTS / "doi_verify.py"),
                "--doi", UNRELATED_DOI,
                "--doi-source", "model",
                "--output", str(Path(_td) / "r.json"),
            ],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
        )
        _combined = _proc.stdout + _proc.stderr
        check(
            "[CLI] --doi-source model + no declared title -> BLOCKED, exit 2",
            _proc.returncode == 2 and "BLOCKED" in _combined,
            f"got exit={_proc.returncode}, out={_combined[-200:]!r}",
        )

        _proc_ok = subprocess.run(
            [
                sys.executable, str(SCRIPTS / "doi_verify.py"),
                "--doi", "10.1038/nature12373",
                "--doi-source", "model",
                "--expect-title", "Nanometre-scale thermometry in a living cell",
                "--output", str(Path(_td) / "r2.json"),
            ],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
        )
        check(
            "[CLI] --doi-source model + correct title -> passes (exit 0, no false positive)",
            _proc_ok.returncode == 0,
            f"got exit={_proc_ok.returncode}, out={(_proc_ok.stdout + _proc_ok.stderr)[-300:]!r}",
        )
else:
    print(f"  [SKIP] {_NET_WHY} — skipping real API-call tests (the UNVERIFIED path is already covered by grade_one unit tests)")


# --------------------------------------------------------------------------- #
# Result summary
# --------------------------------------------------------------------------- #

print(f"\n=== Result: {PASS} passed / {FAIL} failed ===")
sys.exit(0 if FAIL == 0 else 1)
