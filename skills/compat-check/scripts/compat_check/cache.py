"""SQLite-backed cache in front of runner.probe_all().

runner.py stays cache-unaware by design (separation of concerns) — this
module wraps it. Keyed on the exact inputs that determine a dry-run's
outcome: requirements, python_version, and backend name (uv vs pip give
different resolvers and can disagree).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path

from compat_check.runner import _select_backend, probe_all

DEFAULT_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days — see docs/feature-connectivity-ledger.md
DEFAULT_DB_PATH = Path.home() / ".cache" / "compat_check" / "history.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS probe_cache (
    cache_key TEXT PRIMARY KEY,
    ok INTEGER NOT NULL,
    failures_json TEXT NOT NULL,
    resolved_json TEXT NOT NULL,
    backend TEXT NOT NULL,
    checked_at REAL NOT NULL
)
"""


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute(_SCHEMA)
    return conn


def make_cache_key(requirements: list[str], python_version: str, backend: str) -> str:
    normalized = json.dumps(
        {"requirements": sorted(requirements), "python_version": python_version, "backend": backend},
        sort_keys=True,
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def cached_probe_all(
    requirements: list[str],
    python_version: str = "3.11",
    max_rounds: int = 20,
    db_path: Path | None = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> dict:
    """probe_all(), but returns a cached result when one exists and hasn't expired.

    Result dict gains one extra key not present in raw probe_all() output:
    "cache_hit": bool.
    """
    db_path = db_path or DEFAULT_DB_PATH
    backend_name = _select_backend().name
    cache_key = make_cache_key(requirements, python_version, backend_name)

    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT ok, failures_json, resolved_json, backend, checked_at "
            "FROM probe_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()

        if row is not None:
            ok, failures_json, resolved_json, backend, checked_at = row
            if time.time() - checked_at < ttl_seconds:
                return {
                    "ok": bool(ok),
                    "backend": backend,
                    "failures": json.loads(failures_json),
                    "resolved": json.loads(resolved_json),
                    "cache_hit": True,
                }

        result = probe_all(requirements, python_version=python_version, max_rounds=max_rounds)
        conn.execute(
            "INSERT OR REPLACE INTO probe_cache "
            "(cache_key, ok, failures_json, resolved_json, backend, checked_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                cache_key,
                int(result["ok"]),
                json.dumps(result["failures"]),
                json.dumps(result["resolved"]),
                result["backend"],
                time.time(),
            ),
        )
        conn.commit()
        return {**result, "cache_hit": False}
    finally:
        conn.close()
