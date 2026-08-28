#!/usr/bin/env python3
"""Fetches a paper's supplementary information (SI) using open routes only.

Why this is separate from the body-text fetcher (ref_fetch.py): body text and
SI have **different access levels.** Even in a subscription journal, the SI
can sit outside the paywall. Measured (260807), the same paper
10.1007/s12010-021-03624-7 (a subscription journal):

    SI    media.springernature.com/.../MOESM1_ESM.docx  -> HTTP 200 (no auth needed)
    body  link.springer.com/content/pdf/....pdf          -> 303 -> 302 -> 302 (login)

So "the body is unreachable but the SI isn't" is a real case.

The route itself was also chosen by measurement. The first attempt was to
scrape the publisher's landing page, but the standard library can't do it:

    requesting the publisher landing page via urllib   -> Springer returns a 3,036 B stripped page
      (the same URL via curl returns 372,615 B. Swapping in 3 different UAs
       makes no difference to urllib — the gap is at the HTTP/2/TLS
       fingerprint level, which headers can't get past)
    a direct PMC file link (/articles/instance/.../bin/...)  -> 1,817 B
      a "Preparing to download ..." JS interstitial. The URL is correct but
      it needs JS.

Both routes need a real browser, so they were dropped. The one thing that
actually works is the **Europe PMC REST API** — urllib alone gets back a
4.28 MB archive whole:

    GET /europepmc/webservices/rest/{PMCID}/supplementaryFiles  -> application/zip

So this module's automated coverage is **papers on PMC**. Anything else gets
only a link — no workaround is attempted. A human opening it in a browser
usually just gets it.

Policy: fetching open SI is not covered by a university library's fair-use
policy. That policy forbids fetching the 'full text' of a subscription
e-resource by mechanical means; open SI is not a subscription resource and
does not go through a proxy either. See institutional_access.py for the
body-text handling.

Usage:
    from si_fetch import discover_si, download_si
    res = discover_si("10.1186/s13321-015-0069-3")
    print(res.status, res.archive_url)

CLI:
    python si_fetch.py --doi 10.1186/s13321-015-0069-3
    python si_fetch.py --doi 10.1186/s13321-015-0069-3 --download -o ./si
    python si_fetch.py --doi 10.1186/s13321-015-0069-3 --download --extract --si-only
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ref_fetch import (  # noqa: E402
    _build_user_agent,
    _http_get_json,
    doi_to_safe_filename,
    normalize_doi,
)

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


_NCBI_IDCONV = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
_EPMC_SUPPL = "https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/supplementaryFiles"
_ARCHIVE_MAX_RETRIES = 3
_ARCHIVE_RETRY_BACKOFF = 1.5  # seconds, multiplied per attempt (same pattern as ref_fetch._http_get_json)

# The Europe PMC archive also bundles in body figures (Fig1_HTML.jpg, etc.).
# Author-uploaded supplementary files conventionally carry MOESM / ESM /
# suppl in the filename.
_SI_NAME_HINTS = ("moesm", "_esm", "suppl", "supplementary", "media")

# Publishers whose landing page blocks automated lookup. Handed to a human
# rather than worked around. (Not because the SI is paid — it's bot
# blocking/JS. A browser just gets it.)
BLOCKED_PREFIXES = {
    "10.1016": ("Elsevier", "linkinghub returns only a JS shell"),
    "10.1021": ("ACS", "landing page 403"),
    "10.1039": ("RSC", "landing page 403"),
    "10.1002": ("Wiley", "cookieAbsent redirect"),
    "10.1007": ("Springer", "urllib receives only a stripped page (curl/browser work fine)"),
    "10.1038": ("Springer Nature", "urllib receives only a stripped page (curl/browser work fine)"),
}


@dataclass
class SIFile:
    name: str
    size: int
    is_supplementary: bool
    extracted_path: Optional[str] = None


@dataclass
class SIResult:
    doi: str
    status: str  # "found" | "none" | "blocked" | "error"
    pmcid: Optional[str] = None
    archive_url: Optional[str] = None
    archive_path: Optional[str] = None
    archive_bytes: int = 0
    files: list[SIFile] = field(default_factory=list)
    note: Optional[str] = None
    manual_hint: Optional[str] = None

    @property
    def supplementary_files(self) -> list[SIFile]:
        return [f for f in self.files if f.is_supplementary]

    def to_dict(self) -> dict[str, Any]:
        return {
            "doi": self.doi,
            "status": self.status,
            "pmcid": self.pmcid,
            "archive_url": self.archive_url,
            "archive_path": self.archive_path,
            "archive_bytes": self.archive_bytes,
            "note": self.note,
            "manual_hint": self.manual_hint,
            "files": [
                {
                    "name": f.name,
                    "size": f.size,
                    "is_supplementary": f.is_supplementary,
                    "extracted_path": f.extracted_path,
                }
                for f in self.files
            ],
        }


def _prefix(doi: str) -> str:
    return doi.split("/", 1)[0] if "/" in doi else doi


def _looks_supplementary(name: str) -> bool:
    low = name.lower()
    return any(h in low for h in _SI_NAME_HINTS)


def doi_to_pmcid(doi: str, email: Optional[str] = None) -> tuple[Optional[str], Optional[str]]:
    """DOI -> PMCID via the NCBI ID converter.

    Returns (pmcid, err) — the result after _http_get_json has already
    exhausted its retries. err=None means "genuinely not on PMC" (a normal
    not-found); a non-None err means "the lookup itself failed" (network/
    server error) — these two must not be conflated. Conflating them turns a
    transient CI network failure into a false "the paper isn't on PMC."
    """
    url = f"{_NCBI_IDCONV}?ids={urllib.parse.quote(doi)}&format=json"
    data, err = _http_get_json(url, email)
    if err:
        return None, err
    if not data:
        return None, None
    for rec in data.get("records") or []:
        if rec.get("pmcid"):
            return rec["pmcid"], None
    return None, None


def _fetch_archive(pmcid: str, email: Optional[str], timeout: int = 120) -> tuple[Optional[bytes], Optional[str]]:
    """Fetch the Europe PMC supplementaryFiles archive whole.

    A 404 (no supplementary material) is not retried — it ends immediately
    as "not_found." Only other network/server errors are retried, using the
    same pattern as ref_fetch._http_get_json.
    """
    url = _EPMC_SUPPL.format(pmcid=pmcid)
    req = urllib.request.Request(url, headers={"User-Agent": _build_user_agent(email)})
    last_err: Optional[str] = None
    for attempt in range(1, _ARCHIVE_MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read(), None
        except urllib.error.HTTPError as e:  # type: ignore[attr-defined]
            if e.code == 404:
                return None, "not_found"
            last_err = f"HTTP {e.code}"
        except Exception as e:  # noqa: BLE001
            last_err = f"{type(e).__name__}: {e}"

        if attempt < _ARCHIVE_MAX_RETRIES:
            time.sleep(_ARCHIVE_RETRY_BACKOFF * attempt)

    return None, last_err or "unknown_error"


def discover_si(doi: str, email: Optional[str] = None) -> SIResult:
    """Find the SI for one DOI. Returns the file list if it's on PMC, otherwise a hint.

    The archive has to be fetched to know its contents, so it is already
    downloaded during the discover step. Whether to save it is decided by
    download_si().
    """
    doi = normalize_doi(doi)
    pmcid, lookup_err = doi_to_pmcid(doi, email)

    if lookup_err:
        # All retries failed too — this is "the lookup itself didn't work," not "not on PMC."
        return SIResult(
            doi=doi,
            status="error",
            note=f"PMC ID lookup failed (even after retries): {lookup_err}",
        )

    if not pmcid:
        pfx = _prefix(doi)
        if pfx in BLOCKED_PREFIXES:
            name, why = BLOCKED_PREFIXES[pfx]
            return SIResult(
                doi=doi,
                status="blocked",
                note=f"Not on PMC. {name}: {why}",
                manual_hint=(
                    # NOTE: the Korean clause below ("유료라서가 아닙니다" = "not because it's
                    # paywalled") is asserted on verbatim by tests/test_si_institutional.py —
                    # do not translate/remove it without updating that test too.
                    f"{name} blocks scripted lookup (SI 가 유료라서가 아닙니다 — not because the SI is paywalled). "
                    f"Opening https://doi.org/{doi} in a browser fetches the supplementary material directly."
                ),
            )
        return SIResult(
            doi=doi,
            status="none",
            note="Paper not found on PMC, so there is no automated fetch route",
            manual_hint=f"Open https://doi.org/{doi} in a browser to check.",
        )

    url = _EPMC_SUPPL.format(pmcid=pmcid)
    blob, err = _fetch_archive(pmcid, email)
    if err == "not_found":
        return SIResult(doi=doi, status="none", pmcid=pmcid, archive_url=url,
                        note=f"No supplementary material for {pmcid}")
    if err or not blob:
        return SIResult(doi=doi, status="error", pmcid=pmcid, archive_url=url,
                        note=f"Europe PMC lookup failed: {err}")

    buf = io.BytesIO(blob)
    if not zipfile.is_zipfile(buf):
        return SIResult(doi=doi, status="error", pmcid=pmcid, archive_url=url,
                        archive_bytes=len(blob),
                        note="Response is not a valid archive (format may have changed)")

    zf = zipfile.ZipFile(buf)
    files = [
        SIFile(name=n, size=zf.getinfo(n).file_size, is_supplementary=_looks_supplementary(n))
        for n in zf.namelist()
    ]
    res = SIResult(doi=doi, status="found", pmcid=pmcid, archive_url=url,
                   archive_bytes=len(blob), files=files)
    res._blob = blob  # type: ignore[attr-defined]  # reused at the download step (avoids a re-request)
    return res


def download_si(
    result: SIResult,
    out_dir: Path,
    extract: bool = False,
    si_only: bool = True,
) -> SIResult:
    """Save the SI that was found. By default keeps the archive as-is; unpacks per-file if --extract."""
    if result.status != "found":
        return result
    blob = getattr(result, "_blob", None)
    if blob is None:
        return result

    out_dir.mkdir(parents=True, exist_ok=True)
    stem = doi_to_safe_filename(result.doi)

    archive_path = out_dir / f"{stem}_SI.zip"
    archive_path.write_bytes(blob)
    result.archive_path = str(archive_path)

    if not extract:
        return result

    zf = zipfile.ZipFile(io.BytesIO(blob))
    target_dir = out_dir / stem
    target_dir.mkdir(parents=True, exist_ok=True)
    for f in result.files:
        if si_only and not f.is_supplementary:
            continue
        # Don't trust the archive's internal path as-is (zip-slip prevention) — use only the filename.
        safe_name = Path(f.name).name
        if not safe_name:
            continue
        dest = target_dir / safe_name
        dest.write_bytes(zf.read(f.name))
        f.extracted_path = str(dest)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Fetch a paper's supplementary information (SI) using open routes (Europe PMC) only. No paywall bypass.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--doi", required=True, help="DOI (comma-separated for multiple)")
    ap.add_argument("--download", action="store_true", help="Save the archive")
    ap.add_argument("--extract", action="store_true", help="Unpack the archive per-file")
    ap.add_argument("--si-only", action="store_true", default=True,
                    help="Extract only supplementary material (default). Disable with --all-files")
    ap.add_argument("--all-files", action="store_true",
                    help="Extract everything, including body figures")
    ap.add_argument("-o", "--out-dir", default="./si", help="Output directory (default ./si)")
    ap.add_argument("--email", default=None, help="Contact email for the polite pool")
    ap.add_argument("--json", default=None, help="Save the result as JSON at this path")
    args = ap.parse_args()

    results: list[SIResult] = []
    for raw in args.doi.split(","):
        raw = raw.strip()
        if not raw:
            continue
        res = discover_si(raw, args.email)
        if args.download or args.extract:
            res = download_si(res, Path(args.out_dir), extract=args.extract,
                              si_only=not args.all_files)
        results.append(res)

        print(f"\n[{res.doi}] status={res.status}" + (f" ({res.pmcid})" if res.pmcid else ""))
        if res.note:
            print(f"  note: {res.note}")
        if res.status == "found":
            si = res.supplementary_files
            print(f"  archive {res.archive_bytes:,} bytes / {len(res.files)} file(s) "
                  f"({len(si)} identified as supplementary)")
            for f in si[:10]:
                line = f"    - {f.name}  ({f.size:,} bytes)"
                if f.extracted_path:
                    line += f"  -> {f.extracted_path}"
                print(line)
            if res.archive_path:
                print(f"  saved: {res.archive_path}")
        if res.manual_hint:
            print(f"  → {res.manual_hint}")

    if args.json:
        Path(args.json).write_text(
            json.dumps([r.to_dict() for r in results], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n[OK] JSON saved: {args.json}")

    # blocked is not a failure but "something for a human to do," so it returns 0. Only a real error returns 1.
    if any(r.status == "error" for r in results):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
