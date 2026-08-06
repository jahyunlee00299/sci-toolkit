#!/usr/bin/env python3
"""DOI 기반 메타데이터 로컬 캐시 관리자.

저장 위치: ~/.claude/ref_cache/ (DOI SHA256 해시 기반 파일명)
파일명: SHA256(lowercase(doi)) 앞 16자리 + ".json"

사용법 (CLI):
    python ref_cache_manager.py get 10.1021/acs.biochem.1c00123
    python ref_cache_manager.py stats
    python ref_cache_manager.py expire --days 365
    python ref_cache_manager.py put --doi 10.1021/xxx --file metadata.json

임포트:
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
    """DOI 메타데이터 로컬 캐시 관리자.

    각 DOI는 독립적인 JSON 파일로 저장된다.
    파일명: sha256(lowercase(doi))[:16].json
    """

    def __init__(self, cache_dir: Optional[Path] = None) -> None:
        self.cache_dir = Path(cache_dir) if cache_dir else _DEFAULT_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # 내부 헬퍼                                                            #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _doi_key(doi: str) -> str:
        """DOI → 16자리 SHA256 헥스 문자열."""
        normalized = doi.strip().lower().lstrip("https://doi.org/")
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]

    def _path(self, doi: str) -> Path:
        return self.cache_dir / f"{self._doi_key(doi)}.json"

    # ------------------------------------------------------------------ #
    # 공개 API                                                             #
    # ------------------------------------------------------------------ #

    def has(self, doi: str) -> bool:
        """캐시에 해당 DOI 항목이 존재하는지 확인한다."""
        return self._path(doi).exists()

    def get(self, doi: str) -> Optional[dict]:
        """캐시에서 메타데이터를 반환한다. 없으면 None."""
        p = self._path(doi)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def put(self, doi: str, metadata: dict) -> None:
        """메타데이터를 캐시에 저장한다 (타임스탬프 자동 추가)."""
        record = dict(metadata)
        record[_TIMESTAMP_KEY] = datetime.now(timezone.utc).isoformat()
        p = self._path(doi)
        p.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    def expire(self, days: int = 365) -> int:
        """N일보다 오래된 캐시 항목을 삭제하고 삭제 수를 반환한다."""
        now = datetime.now(timezone.utc)
        removed = 0
        for p in self.cache_dir.glob("*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                ts_str = data.get(_TIMESTAMP_KEY)
                if not ts_str:
                    continue  # 타임스탬프 없는 파일은 보존
                ts = datetime.fromisoformat(ts_str)
                if (now - ts).days >= days:
                    p.unlink()
                    removed += 1
            except Exception:
                continue
        return removed

    def stats(self) -> dict:
        """캐시 통계를 반환한다."""
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
        """특정 DOI 캐시를 삭제한다. 성공 시 True."""
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
        print(f"캐시 미스: {args.doi}", file=sys.stderr)
        return 1
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


def _cmd_put(args: argparse.Namespace, cache: RefCacheManager) -> int:
    meta_path = Path(args.file)
    if not meta_path.exists():
        print(f"파일 없음: {args.file}", file=sys.stderr)
        return 1
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    cache.put(args.doi, metadata)
    print(f"저장됨: {args.doi} → {cache._path(args.doi)}", file=sys.stderr)
    return 0


def _cmd_has(args: argparse.Namespace, cache: RefCacheManager) -> int:
    exists = cache.has(args.doi)
    print("true" if exists else "false")
    return 0 if exists else 1


def _cmd_expire(args: argparse.Namespace, cache: RefCacheManager) -> int:
    removed = cache.expire(days=args.days)
    print(f"{removed}개 항목 삭제됨 ({args.days}일 초과)")
    return 0


def _cmd_stats(args: argparse.Namespace, cache: RefCacheManager) -> int:
    s = cache.stats()
    print(json.dumps(s, ensure_ascii=False, indent=2))
    return 0


def _cmd_delete(args: argparse.Namespace, cache: RefCacheManager) -> int:
    ok = cache.delete(args.doi)
    if ok:
        print(f"삭제됨: {args.doi}", file=sys.stderr)
        return 0
    else:
        print(f"없음: {args.doi}", file=sys.stderr)
        return 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="DOI 메타데이터 로컬 캐시 관리 (~/.claude/ref_cache/)"
    )
    parser.add_argument(
        "--cache-dir", default=None, help="캐시 디렉토리 경로 (기본: ~/.claude/ref_cache/)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # get
    p_get = sub.add_parser("get", help="DOI 캐시 조회")
    p_get.add_argument("doi", help="DOI 문자열")

    # put
    p_put = sub.add_parser("put", help="메타데이터 저장")
    p_put.add_argument("--doi", required=True, help="DOI 문자열")
    p_put.add_argument("--file", required=True, help="메타데이터 JSON 파일 경로")

    # has
    p_has = sub.add_parser("has", help="DOI 존재 여부 확인 (exitcode: 0=있음, 1=없음)")
    p_has.add_argument("doi", help="DOI 문자열")

    # expire
    p_exp = sub.add_parser("expire", help="오래된 캐시 항목 삭제")
    p_exp.add_argument("--days", type=int, default=365, help="보관 기간 (일, 기본: 365)")

    # stats
    sub.add_parser("stats", help="캐시 통계 출력")

    # delete
    p_del = sub.add_parser("delete", help="특정 DOI 캐시 삭제")
    p_del.add_argument("doi", help="DOI 문자열")

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
