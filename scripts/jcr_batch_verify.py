#!/usr/bin/env python3
"""JCR batch verification — enriches journal_if_cache.json with OpenAlex source/venue data.

Usage:
    python jcr_batch_verify.py
    python jcr_batch_verify.py --cache path/to/journal_if_cache.json
    python jcr_batch_verify.py --cache cache.json --output enriched.json
    python jcr_batch_verify.py --add-journal "Nature Catalysis"
    python jcr_batch_verify.py --add-journal "Nature Catalysis" --cache cache.json

Behavior:
    - processes only verified=false journals (skips already-verified entries, resumable)
    - pulls display_name, issn, 2yr_mean_citedness, h_index, works_count,
      type, homepage_url from the OpenAlex sources API
    - adds openalex_verified=true and a verified_date field
    - rate limit: 10 req/s (OpenAlex's recommendation)
"""

# Windows' default console is cp949, which dies on Korean/symbol output. Force
# UTF-8. Use reconfigure: wrapping in a TextIOWrapper would make it own the
# underlying stream, so once this module is imported, the caller's stdout
# gets closed when the wrapper is later garbage-collected (measured).
import sys as _sys
for _s in (_sys.stdout, _sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
import argparse
import json
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sci_http  # noqa: E402

# Default cache path priority order
_DEFAULT_CACHE_PATHS = [
    Path("~/tmp/review_qc/ref_fulltext_cache/journal_if_cache.json").expanduser(),
    Path("~/.claude/ref_cache/journal_if_cache.json").expanduser(),
]

OPENALEX_SOURCES_BASE = "https://api.openalex.org/sources"
_RATE_LIMIT_DELAY = 0.1  # 10 req/s
VERIFIED_DATE = "2026-04-03"


def _find_default_cache() -> Optional[Path]:
    for p in _DEFAULT_CACHE_PATHS:
        if p.exists():
            return p
    return None


def _load_cache(cache_path: Path) -> dict:
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))
    # Build a new cache structure
    print(f"[INFO] no cache file. Creating new: {cache_path}", file=sys.stderr)
    return {
        "metadata": {
            "created": VERIFIED_DATE,
            "source": "OpenAlex API",
            "note": "2yr_mean_citedness approximates IF. Tier: 1=IF>15, 2=IF 5-15, 3=IF 2-5, 4=IF<2.",
            "journals_count": 0,
        },
        "journals": [],
    }


def _save_cache(data: dict, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data["metadata"]["journals_count"] = len(data["journals"])
    output_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _get(url: str, timeout: int = 15) -> dict:
    """GET JSON with the shared retry policy (429/5xx retried, other 4xx raised at once)."""
    return sci_http.request(
        url, headers={"User-Agent": sci_http.user_agent("jcr_batch_verify"),
                      "Accept": "application/json"},
        timeout=timeout).json()


def _query_openalex_source(journal_name: str) -> Optional[dict]:
    """Look up journal information from the OpenAlex sources API."""
    encoded = urllib.parse.quote(journal_name)
    url = f"{OPENALEX_SOURCES_BASE}?search={encoded}&per_page=1"
    try:
        data = _get(url)
        results = data.get("results", [])
        if not results:
            return None
        src = results[0]
        return {
            "openalex_display_name": src.get("display_name"),
            "openalex_issn": (src.get("issn") or [None])[0],
            "openalex_2yr_citedness": src.get("summary_stats", {}).get(
                "2yr_mean_citedness"
            ),
            "openalex_h_index": src.get("summary_stats", {}).get("h_index"),
            "openalex_works_count": src.get("works_count"),
            "openalex_type": src.get("type"),
            "openalex_homepage_url": src.get("homepage_url"),
            "openalex_id": src.get("id"),
            "openalex_verified": True,
            "verified_date": VERIFIED_DATE,
        }
    except sci_http.HttpError as e:
        print(f"  HTTP error {e.status}: {journal_name}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  lookup failed: {journal_name} — {e}", file=sys.stderr)
        return None


def _assign_tier(citedness: Optional[float]) -> int:
    if citedness is None:
        return 4
    if citedness >= 15:
        return 1
    if citedness >= 5:
        return 2
    if citedness >= 2:
        return 3
    return 4


def verify_batch(
    data: dict, verbose: bool = True
) -> tuple[int, int, int]:
    """Verify unverified journals in the cache against OpenAlex.

    Returns:
        (verified, skipped, failed) count tuple
    """
    journals = data["journals"]
    verified_count = 0
    skipped_count = 0
    failed_count = 0

    for i, entry in enumerate(journals, 1):
        name = entry.get("name", "")
        already = entry.get("openalex_verified", False)

        if already:
            skipped_count += 1
            if verbose:
                print(f"[{i}/{len(journals)}] skipped (already verified): {name}", file=sys.stderr)
            continue

        if verbose:
            print(f"[{i}/{len(journals)}] looking up: {name} ...", end=" ", file=sys.stderr, flush=True)

        result = _query_openalex_source(name)
        if result:
            entry.update(result)
            # update the citedness-based tier (when there is no existing tier or citedness changed)
            citedness = result.get("openalex_2yr_citedness")
            if citedness is not None and entry.get("tier") is None:
                entry["tier"] = _assign_tier(citedness)
            verified_count += 1
            if verbose:
                cf = result.get("openalex_2yr_citedness")
                cf_str = f"IF≈{cf:.2f}" if cf is not None else "IF=N/A"
                print(f"OK ({cf_str})", file=sys.stderr)
        else:
            entry["openalex_verified"] = False
            entry["verified_date"] = VERIFIED_DATE
            failed_count += 1
            if verbose:
                print("failed", file=sys.stderr)

        time.sleep(_RATE_LIMIT_DELAY)

    return verified_count, skipped_count, failed_count


def add_journal(data: dict, journal_name: str, verbose: bool = True) -> bool:
    """Add a new journal to the cache and verify it against OpenAlex."""
    # check for a duplicate
    existing = [j for j in data["journals"] if j.get("name", "").lower() == journal_name.lower()]
    if existing:
        print(f"[INFO] already exists: {journal_name}", file=sys.stderr)
        return False

    if verbose:
        print(f"[ADD] {journal_name} ...", end=" ", file=sys.stderr, flush=True)

    result = _query_openalex_source(journal_name)
    entry: dict = {"name": journal_name}
    if result:
        entry.update(result)
        entry["tier"] = _assign_tier(result.get("openalex_2yr_citedness"))
        if verbose:
            cf = result.get("openalex_2yr_citedness")
            cf_str = f"IF≈{cf:.2f}" if cf is not None else "IF=N/A"
            print(f"added ({cf_str})", file=sys.stderr)
    else:
        entry["openalex_verified"] = False
        entry["verified_date"] = VERIFIED_DATE
        entry["tier"] = 4
        if verbose:
            print("added (lookup failed)", file=sys.stderr)

    data["journals"].append(entry)
    return True


def print_summary(verified: int, skipped: int, failed: int) -> None:
    total = verified + skipped + failed
    print("\n=== results summary ===")
    print(f"  total journals: {total}")
    print(f"  verified:       {verified}")
    print(f"  skipped (existing): {skipped}")
    print(f"  failed:         {failed}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch-enrich journal_if_cache.json with OpenAlex source data."
    )
    parser.add_argument("--cache", "-c", default=None, help="input cache JSON path")
    parser.add_argument("--output", "-o", default=None, help="output JSON path (default: overwrite the input file)")
    parser.add_argument("--add-journal", metavar="NAME", default=None, help="add a new journal")
    parser.add_argument("--quiet", "-q", action="store_true", help="suppress progress output")
    args = parser.parse_args()

    # decide the cache path
    if args.cache:
        cache_path = Path(args.cache)
    else:
        found = _find_default_cache()
        if found:
            cache_path = found
            print(f"[INFO] cache file: {cache_path}", file=sys.stderr)
        else:
            cache_path = Path("~/.claude/ref_cache/journal_if_cache.json").expanduser()
            print(f"[INFO] creating default cache: {cache_path}", file=sys.stderr)

    output_path = Path(args.output) if args.output else cache_path

    data = _load_cache(cache_path)
    verbose = not args.quiet

    if args.add_journal:
        added = add_journal(data, args.add_journal, verbose=verbose)
        if added:
            _save_cache(data, output_path)
            print(f"[OK] saved: {output_path}", file=sys.stderr)
        return

    # batch verification
    verified, skipped, failed = verify_batch(data, verbose=verbose)
    _save_cache(data, output_path)
    if verbose:
        print(f"\n[OK] saved: {output_path}", file=sys.stderr)
    print_summary(verified, skipped, failed)


if __name__ == "__main__":
    main()
