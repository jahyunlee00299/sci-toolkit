#!/usr/bin/env python3
"""Regression tests for skills/biorxiv-database/scripts/preprint_search.py.

Judgement is DISK-ARTIFACT based, never the script's own success report — a
retrieval route can print "downloaded" while writing nothing, or writing an
HTML error page that merely looks like a PDF (see F2/F3 below).

Two groups:
  offline (always run, no network):
    T-schema     _build_record() carries all four routing fields; a record
                 with neither doi nor arxiv_id is rejected WITH a warning,
                 never silently dropped.
    T-routing    route == "doi" iff doi present; route == "arxiv" iff
                 arxiv_id present and no doi. Peer routes, not a fallback
                 chain — decided once, at record-build time.
    T-no-bypass  fetch_via_doi_route() must invoke scripts/ref_fetch.py.
                 Guards against a future downloader that re-implements OA
                 resolution instead of going through the single OA gateway.

  network (require internet; explicit SKIP on failure, never a silent PASS):
    F2 (Route A — DOI)   ref_fetch.py --doi ... --download must leave a real
                         PDF (%PDF- header, read from disk) behind.
    F3 (Route B — arXiv) the direct arxiv.org/pdf/<id> fetch must leave a
                         real PDF (%PDF- header, read from disk) behind.

Usage:
  python skills/biorxiv-database/tests/test_preprint_search.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

# Windows consoles default to cp949 and die on non-ASCII output.
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))
import preprint_search as ps  # noqa: E402

PASS = "[PASS]"
FAIL = "[FAIL]"
SKIP = "[SKIP]"

# Live network fixtures — verified live against the real APIs while writing this
# test (2026-08-08): DOI resolves via CrossRef as type=posted-content (bioRxiv),
# arXiv ID serves a real %PDF- payload.
F2_DOI = "10.1101/2023.06.10.544439"
F3_ARXIV_ID = "2401.12345"
_NETWORK_PROBE_URL = "https://arxiv.org/pdf/2401.12345"
_NETWORK_PROBE_TIMEOUT = 15


def _print_check(label: str, ok: bool, detail: str = "") -> bool:
    icon = PASS if ok else FAIL
    msg = f"  {icon}  {label}"
    if detail:
        msg += f"  [{detail}]"
    print(msg)
    return ok


def _network_available() -> bool:
    try:
        req = urllib.request.Request(
            _NETWORK_PROBE_URL, headers={"User-Agent": "sci-toolkit-test/1.0"}
        )
        with urllib.request.urlopen(req, timeout=_NETWORK_PROBE_TIMEOUT):
            return True
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# T-schema
# --------------------------------------------------------------------------- #


def test_schema() -> bool:
    print("\n-- T-schema: _build_record() field contract --")
    ok = True

    rec_doi = ps._build_record(
        title="t", authors="a", date="2026-01-01", server="bioRxiv",
        doi="10.1101/2026.01.01.000001", arxiv_id=None, abstract="",
        landing_url="https://doi.org/10.1101/2026.01.01.000001",
        source_api="europepmc",
    )
    for field in ("doi", "arxiv_id", "route", "pdf_url"):
        ok &= _print_check(f"DOI record carries field {field!r}", field in rec_doi)

    # Exercise the reject path through the real run_search() filter rather than
    # duplicating its two-line filter logic here, by feeding it a record with
    # neither identifier through a monkeypatched single-source search.
    bare = ps._build_record(
        title="orphan", authors="a", date="2026-01-01", server="unknown",
        doi=None, arxiv_id=None, abstract="", landing_url="https://example.org",
        source_api="europepmc",
    )
    ok &= _print_check("no-identifier record has route=None", bare["route"] is None)

    with mock.patch.object(ps, "search_europepmc", return_value=([bare], None)), \
         mock.patch.object(ps, "search_arxiv", return_value=([], None)):
        records, warnings, rejected = ps.run_search(
            query="x", max_results=10, source="all", since=None, email=None, enrich=False
        )
    ok &= _print_check("orphan record excluded from records[]", len(records) == 0,
                        f"records={len(records)}")
    ok &= _print_check("orphan record present in rejected[]", len(rejected) == 1,
                        f"rejected={len(rejected)}")
    ok &= _print_check(
        "a warning was raised for the orphan record",
        any("neither DOI nor arXiv ID" in w for w in warnings),
        f"warnings={warnings}",
    )
    return ok


# --------------------------------------------------------------------------- #
# T-routing
# --------------------------------------------------------------------------- #


def test_routing() -> bool:
    print("\n-- T-routing: route decided by identifier presence only --")
    ok = True

    doi_only = ps._build_record(
        title="t", authors="a", date="2026-01-01", server="bioRxiv",
        doi="10.1101/2026.01.01.000001", arxiv_id=None, abstract="",
        landing_url="x", source_api="europepmc",
    )
    ok &= _print_check("doi present -> route == 'doi'", doi_only["route"] == "doi")

    arxiv_only = ps._build_record(
        title="t", authors="a", date="2026-01-01", server="arXiv",
        doi=None, arxiv_id="2401.00001", abstract="",
        landing_url="x", source_api="arxiv",
    )
    ok &= _print_check(
        "arxiv_id present, no doi -> route == 'arxiv'", arxiv_only["route"] == "arxiv"
    )
    ok &= _print_check(
        "arxiv route pdf_url is deterministic from the id",
        arxiv_only["pdf_url"] == "https://arxiv.org/pdf/2401.00001",
        arxiv_only["pdf_url"],
    )

    both = ps._build_record(
        title="t", authors="a", date="2026-01-01", server="arXiv",
        doi="10.1101/2026.01.01.000002", arxiv_id="2401.00002", abstract="",
        landing_url="x", source_api="arxiv",
    )
    ok &= _print_check(
        "doi + arxiv_id both present -> route == 'doi' (doi takes precedence)",
        both["route"] == "doi",
    )

    neither = ps._build_record(
        title="t", authors="a", date="2026-01-01", server="unknown",
        doi=None, arxiv_id=None, abstract="", landing_url="x", source_api="arxiv",
    )
    ok &= _print_check("neither present -> route is None", neither["route"] is None)

    return ok


# --------------------------------------------------------------------------- #
# T-no-bypass
# --------------------------------------------------------------------------- #


def test_no_bypass() -> bool:
    print("\n-- T-no-bypass: Route A must go through scripts/ref_fetch.py --")
    ok = True

    records = [
        ps._build_record(
            title="t", authors="a", date="2026-01-01", server="bioRxiv",
            doi="10.1101/2026.01.01.000003", arxiv_id=None, abstract="",
            landing_url="x", source_api="europepmc",
        )
    ]

    captured_cmd = {}

    class _FakeCompleted:
        returncode = 0
        stdout = ""
        stderr = ""

    def _fake_run(cmd, **kwargs):
        captured_cmd["cmd"] = cmd
        captured_cmd["kwargs"] = kwargs
        return _FakeCompleted()

    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        with mock.patch.object(ps.subprocess, "run", side_effect=_fake_run):
            ps.fetch_via_doi_route(records, out_dir, email=None)

    cmd = captured_cmd.get("cmd") or []
    cmd_str = " ".join(str(c) for c in cmd)
    ok &= _print_check(
        "fetch_via_doi_route() invoked a command containing ref_fetch.py",
        any("ref_fetch.py" in str(c) for c in cmd),
        cmd_str,
    )
    ok &= _print_check(
        "invocation passes --doi and --download (Route A contract)",
        "--doi" in cmd and "--download" in cmd,
        cmd_str,
    )
    kwargs = captured_cmd.get("kwargs") or {}
    ok &= _print_check(
        "subprocess.run() call specifies encoding= (Task 1 regression guard)",
        kwargs.get("encoding") == "utf-8",
        f"encoding={kwargs.get('encoding')!r}",
    )
    return ok


# --------------------------------------------------------------------------- #
# F2 — Route A (DOI) leaves a real PDF on disk
# --------------------------------------------------------------------------- #


_F2_MAX_ATTEMPTS = 3
_F2_RETRY_BACKOFF_SEC = 5


def test_f2_route_a_pdf_on_disk() -> str:
    """F2: ref_fetch.py --doi ... --download must leave a %PDF- file on disk.

    ref_fetch.py caches by DOI under ~/.claude/ref_cache/ and, on a cache hit,
    reports the download path from the run that first populated the cache —
    not the fresh --pdf-dir passed this time. Report-based judgement would
    pass here even though the fresh out_dir has nothing in it (reproduced
    while writing this test). HOME is redirected to a throwaway directory for
    the subprocess only, so every run starts from an empty cache and the
    disk-artifact check is exercising the real download path, not a cache
    lookup that recalls a location from an earlier run.

    A transient HTTP 429 from the OA host (observed while writing this test,
    triggered by re-running the same DOI back to back) is retried a few times
    with backoff — it is a rate-limit, not a routing defect. A failure that
    survives every retry is still reported FAIL, never silently downgraded.
    """
    print(f"\n-- F2 (Route A / DOI): {F2_DOI} --")
    if not _network_available():
        print(f"  {SKIP}  no network reachable — F2 not exercised (NOT a pass)")
        return "skip"

    repo_root = ps.find_repo_root()
    if repo_root is None:
        print(f"  {FAIL}  scripts/ref_fetch.py not found from repo root search")
        return "fail"

    records = [
        ps._build_record(
            title="Mag-Net fixture", authors="", date="2023-06-10", server="bioRxiv",
            doi=F2_DOI, arxiv_id=None, abstract="", landing_url=f"https://doi.org/{F2_DOI}",
            source_api="europepmc",
        )
    ]

    for attempt in range(1, _F2_MAX_ATTEMPTS + 1):
        ok = True
        with tempfile.TemporaryDirectory() as tmpdir, \
             tempfile.TemporaryDirectory() as fake_home:
            out_dir = Path(tmpdir)
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = fake_home
            try:
                result = ps.fetch_via_doi_route(records, out_dir, email=None)
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home
            print(f"  attempt {attempt}/{_F2_MAX_ATTEMPTS}: attempted={result['attempted']} "
                  f"downloaded={result['downloaded']} failures={result['failures']}")

            pdfs = sorted(out_dir.glob("*.pdf"))
            if not pdfs:
                is_rate_limited = any(
                    "429" in str(f.get("error", "")) for f in result.get("failures", [])
                )
                if is_rate_limited and attempt < _F2_MAX_ATTEMPTS:
                    print(f"  {SKIP}  HTTP 429 (rate limit) — retrying in "
                          f"{_F2_RETRY_BACKOFF_SEC}s")
                    time.sleep(_F2_RETRY_BACKOFF_SEC)
                    continue
                _print_check("at least one PDF file exists on disk", False,
                              f"0 file(s) in {out_dir}")
                return "fail"

            _print_check("at least one PDF file exists on disk", True,
                          f"{len(pdfs)} file(s) in {out_dir}")
            for p in pdfs:
                head = p.open("rb").read(5)
                byte_ok = head == b"%PDF-"
                ok &= _print_check(
                    f"disk file {p.name} starts with %PDF- (byte-level, read from disk)",
                    byte_ok, f"header={head!r} size={p.stat().st_size:,}B",
                )
            return "pass" if ok else "fail"

    return "fail"


# --------------------------------------------------------------------------- #
# F3 — Route B (arXiv) leaves a real PDF on disk
# --------------------------------------------------------------------------- #


def test_f3_route_b_pdf_on_disk() -> str:
    """F3: the direct arXiv PDF fetch must leave a %PDF- file on disk."""
    print(f"\n-- F3 (Route B / arXiv): {F3_ARXIV_ID} --")
    if not _network_available():
        print(f"  {SKIP}  no network reachable — F3 not exercised (NOT a pass)")
        return "skip"

    records = [
        ps._build_record(
            title="arXiv fixture", authors="", date="2024-01-01", server="arXiv",
            doi=None, arxiv_id=F3_ARXIV_ID, abstract="", landing_url="x",
            source_api="arxiv",
        )
    ]

    ok = True
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        result = ps.fetch_via_arxiv_route(records, out_dir, email=None)
        print(f"  arXiv route result: attempted={result['attempted']} "
              f"downloaded={result['downloaded']} failures={result['failures']}")

        pdfs = sorted(out_dir.glob("*.pdf"))
        ok &= _print_check("at least one PDF file exists on disk", len(pdfs) > 0,
                            f"{len(pdfs)} file(s) in {out_dir}")
        if not pdfs:
            return "fail"

        for p in pdfs:
            head = p.open("rb").read(5)
            byte_ok = head == b"%PDF-"
            ok &= _print_check(
                f"disk file {p.name} starts with %PDF- (byte-level, read from disk)",
                byte_ok, f"header={head!r} size={p.stat().st_size:,}B",
            )

    return "pass" if ok else "fail"


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #


def main() -> int:
    print("=" * 70)
    print("  preprint_search.py — routing + disk-artifact regression tests")
    print("=" * 70)

    offline_results = [
        ("T-schema", test_schema()),
        ("T-routing", test_routing()),
        ("T-no-bypass", test_no_bypass()),
    ]

    f2 = test_f2_route_a_pdf_on_disk()
    f3 = test_f3_route_b_pdf_on_disk()

    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)

    all_ok = True
    for label, ok in offline_results:
        print(f"  {PASS if ok else FAIL}  {label}")
        all_ok &= ok

    for label, verdict in (("F2 (Route A / DOI)", f2), ("F3 (Route B / arXiv)", f3)):
        if verdict == "skip":
            print(f"  {SKIP}  {label} — network unreachable, not exercised")
        else:
            ok = verdict == "pass"
            print(f"  {PASS if ok else FAIL}  {label}")
            all_ok &= ok

    if not all_ok:
        print(f"\n  {FAIL}  one or more tests failed — see details above")
    else:
        print(f"\n  {PASS}  all exercised tests passed")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
