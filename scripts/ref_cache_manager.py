#!/usr/bin/env python3
"""Local DOI-based metadata cache manager.

Storage location: ~/.claude/ref_cache/ (filenames based on a SHA256 hash of the DOI)
Filename: the first 16 characters of SHA256(lowercase(doi)) + ".json"

Usage (CLI):
    python ref_cache_manager.py get 10.1021/acs.biochem.1c00123
    python ref_cache_manager.py stats
    python ref_cache_manager.py expire --days 365
    python ref_cache_manager.py put --doi 10.1021/xxx --file metadata.json

Import:
    from ref_cache_manager import RefCacheManager
    cache = RefCacheManager()
    record = cache.get("10.1021/xxx")
    cache.put("10.1021/xxx", metadata_dict)
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_DEFAULT_CACHE_DIR = Path("~/.claude/ref_cache").expanduser()
_TIMESTAMP_KEY = "_cached_at"  # ISO8601 UTC


class RefCacheManager:
    """Local DOI metadata cache manager.

    Each DOI is stored as its own independent JSON file.
    Filename: sha256(lowercase(doi))[:16].json
    """

    def __init__(self, cache_dir: Optional[Path] = None) -> None:
        self.cache_dir = Path(cache_dir) if cache_dir else _DEFAULT_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _doi_key(doi: str) -> str:
        """DOI -> a 16-character SHA256 hex string."""
        normalized = doi.strip().lower().lstrip("https://doi.org/")
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]

    def _path(self, doi: str) -> Path:
        return self.cache_dir / f"{self._doi_key(doi)}.json"

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def has(self, doi: str) -> bool:
        """Check whether an entry for this DOI exists in the cache."""
        return self._path(doi).exists()

    def get(self, doi: str) -> Optional[dict]:
        """Return the cached metadata. None if not present."""
        p = self._path(doi)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def put(self, doi: str, metadata: dict) -> None:
        """Store metadata in the cache (a timestamp is added automatically)."""
        record = dict(metadata)
        record[_TIMESTAMP_KEY] = datetime.now(timezone.utc).isoformat()
        p = self._path(doi)
        p.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    def expire(self, days: int = 365) -> int:
        """Delete cache entries older than N days and return the number removed."""
        now = datetime.now(timezone.utc)
        removed = 0
        for p in self.cache_dir.glob("*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                ts_str = data.get(_TIMESTAMP_KEY)
                if not ts_str:
                    continue  # keep files with no timestamp
                ts = datetime.fromisoformat(ts_str)
                if (now - ts).days >= days:
                    p.unlink()
                    removed += 1
            except Exception:
                continue
        return removed

    def stats(self) -> dict:
        """Return cache statistics."""
        files = list(self.cache_dir.glob("*.json"))
        total_size = sum(p.stat().st_size for p in files)
        timestamps = []
        for p in files:
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                ts = data.get(_TIMESTAMP_KEY)
                if ts:
                    timestamps.append(datetime.fromisoformat(ts))
            except Exception:
                continue

        return {
            "count": len(files),
            "total_size_bytes": total_size,
            "total_size_kb": round(total_size / 1024, 1),
            "oldest": min(timestamps).isoformat() if timestamps else None,
            "newest": max(timestamps).isoformat() if timestamps else None,
            "cache_dir": str(self.cache_dir),
        }

    def delete(self, doi: str) -> bool:
        """Delete the cache entry for a specific DOI. Returns True on success."""
        p = self._path(doi)
        if p.exists():
            p.unlink()
            return True
        return False


# ------------------------------------------------------------------ #
# CLI                                                                  #
# ------------------------------------------------------------------ #

def _cmd_get(args: argparse.Namespace, cache: RefCacheManager) -> int:
    record = cache.get(args.doi)
    if record is None:
        print(f"Cache miss: {args.doi}", file=sys.stderr)
        return 1
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


def _cmd_put(args: argparse.Namespace, cache: RefCacheManager) -> int:
    meta_path = Path(args.file)
    if not meta_path.exists():
        print(f"File not found: {args.file}", file=sys.stderr)
        return 1
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    cache.put(args.doi, metadata)
    print(f"Saved: {args.doi} -> {cache._path(args.doi)}", file=sys.stderr)
    return 0


def _cmd_has(args: argparse.Namespace, cache: RefCacheManager) -> int:
    exists = cache.has(args.doi)
    print("true" if exists else "false")
    return 0 if exists else 1


def _cmd_expire(args: argparse.Namespace, cache: RefCacheManager) -> int:
    removed = cache.expire(days=args.days)
    print(f"{removed} entries removed (older than {args.days} days)")
    return 0


def _cmd_stats(args: argparse.Namespace, cache: RefCacheManager) -> int:
    s = cache.stats()
    print(json.dumps(s, ensure_ascii=False, indent=2))
    return 0


def _cmd_delete(args: argparse.Namespace, cache: RefCacheManager) -> int:
    ok = cache.delete(args.doi)
    if ok:
        print(f"Deleted: {args.doi}", file=sys.stderr)
        return 0
    else:
        print(f"Not found: {args.doi}", file=sys.stderr)
        return 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manage the local DOI metadata cache (~/.claude/ref_cache/)"
    )
    parser.add_argument(
        "--cache-dir", default=None, help="cache directory path (default: ~/.claude/ref_cache/)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # get
    p_get = sub.add_parser("get", help="look up a DOI in the cache")
    p_get.add_argument("doi", help="DOI string")

    # put
    p_put = sub.add_parser("put", help="store metadata")
    p_put.add_argument("--doi", required=True, help="DOI string")
    p_put.add_argument("--file", required=True, help="path to a metadata JSON file")

    # has
    p_has = sub.add_parser("has", help="check whether a DOI exists (exit code: 0=present, 1=absent)")
    p_has.add_argument("doi", help="DOI string")

    # expire
    p_exp = sub.add_parser("expire", help="delete old cache entries")
    p_exp.add_argument("--days", type=int, default=365, help="retention period in days (default: 365)")

    # stats
    sub.add_parser("stats", help="print cache statistics")

    # delete
    p_del = sub.add_parser("delete", help="delete the cache entry for a specific DOI")
    p_del.add_argument("doi", help="DOI string")

    args = parser.parse_args()
    cache = RefCacheManager(cache_dir=args.cache_dir)

    dispatch = {
        "get": _cmd_get,
        "put": _cmd_put,
        "has": _cmd_has,
        "expire": _cmd_expire,
        "stats": _cmd_stats,
        "delete": _cmd_delete,
    }
    handler = dispatch.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)
    sys.exit(handler(args, cache))


if __name__ == "__main__":
    main()
