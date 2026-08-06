#!/usr/bin/env python3
"""JCR 배치 검증 — journal_if_cache.json을 OpenAlex source/venue 데이터로 보강한다.

사용법:
    python jcr_batch_verify.py
    python jcr_batch_verify.py --cache path/to/journal_if_cache.json
    python jcr_batch_verify.py --cache cache.json --output enriched.json
    python jcr_batch_verify.py --add-journal "Nature Catalysis"
    python jcr_batch_verify.py --add-journal "Nature Catalysis" --cache cache.json

기능:
    - verified=false 저널만 처리 (이미 검증된 항목 스킵, 재개 가능)
    - OpenAlex sources API로 display_name, issn, 2yr_mean_citedness, h_index,
      works_count, type, homepage_url 추출
    - openalex_verified=true, verified_date 필드 추가
    - Rate limit: 10 req/s (OpenAlex 권장)
"""

# Windows 기본 콘솔은 cp949 라서 한글/기호 출력에서 죽는다. UTF-8로 맞춘다.
# reconfigure 를 쓴다: TextIOWrapper 로 감싸면 원본 스트림을 소유하게 되어,
# 이 모듈이 import 된 뒤 래퍼가 GC 될 때 호출자의 stdout 까지 닫는다(실측).
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
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

# 기본 캐시 경로 우선순위
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
    # 새 캐시 구조 생성
    print(f"[INFO] 캐시 파일 없음. 새로 생성: {cache_path}", file=sys.stderr)
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
    req = urllib.request.Request(
        url, headers={"User-Agent": "jcr_batch_verify/1.0 (research tool)"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _query_openalex_source(journal_name: str) -> Optional[dict]:
    """OpenAlex sources API에서 저널 정보를 조회한다."""
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
    except urllib.error.HTTPError as e:
        print(f"  HTTP 오류 {e.code}: {journal_name}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  조회 실패: {journal_name} — {e}", file=sys.stderr)
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
    """캐시 내 미검증 저널을 OpenAlex로 검증한다.

    Returns:
        (verified, skipped, failed) 카운트 튜플
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
                print(f"[{i}/{len(journals)}] 스킵 (검증됨): {name}", file=sys.stderr)
            continue

        if verbose:
            print(f"[{i}/{len(journals)}] 조회 중: {name} ...", end=" ", file=sys.stderr, flush=True)

        result = _query_openalex_source(name)
        if result:
            entry.update(result)
            # citedness 기반 tier 업데이트 (기존 tier가 없거나 citedness 변경 시)
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
                print("실패", file=sys.stderr)

        time.sleep(_RATE_LIMIT_DELAY)

    return verified_count, skipped_count, failed_count


def add_journal(data: dict, journal_name: str, verbose: bool = True) -> bool:
    """새 저널을 캐시에 추가하고 OpenAlex로 검증한다."""
    # 중복 확인
    existing = [j for j in data["journals"] if j.get("name", "").lower() == journal_name.lower()]
    if existing:
        print(f"[INFO] 이미 존재: {journal_name}", file=sys.stderr)
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
            print(f"추가됨 ({cf_str})", file=sys.stderr)
    else:
        entry["openalex_verified"] = False
        entry["verified_date"] = VERIFIED_DATE
        entry["tier"] = 4
        if verbose:
            print("추가됨 (조회 실패)", file=sys.stderr)

    data["journals"].append(entry)
    return True


def print_summary(verified: int, skipped: int, failed: int) -> None:
    total = verified + skipped + failed
    print("\n=== 결과 요약 ===")
    print(f"  총 저널:     {total}")
    print(f"  검증 완료:   {verified}")
    print(f"  스킵 (기존): {skipped}")
    print(f"  실패:        {failed}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="journal_if_cache.json을 OpenAlex source 데이터로 배치 보강한다."
    )
    parser.add_argument("--cache", "-c", default=None, help="입력 캐시 JSON 경로")
    parser.add_argument("--output", "-o", default=None, help="출력 JSON 경로 (기본: 입력 파일 덮어쓰기)")
    parser.add_argument("--add-journal", metavar="NAME", default=None, help="새 저널 추가")
    parser.add_argument("--quiet", "-q", action="store_true", help="진행 출력 억제")
    args = parser.parse_args()

    # 캐시 경로 결정
    if args.cache:
        cache_path = Path(args.cache)
    else:
        found = _find_default_cache()
        if found:
            cache_path = found
            print(f"[INFO] 캐시 파일: {cache_path}", file=sys.stderr)
        else:
            cache_path = Path("~/.claude/ref_cache/journal_if_cache.json").expanduser()
            print(f"[INFO] 기본 캐시 생성: {cache_path}", file=sys.stderr)

    output_path = Path(args.output) if args.output else cache_path

    data = _load_cache(cache_path)
    verbose = not args.quiet

    if args.add_journal:
        added = add_journal(data, args.add_journal, verbose=verbose)
        if added:
            _save_cache(data, output_path)
            print(f"[OK] 저장: {output_path}", file=sys.stderr)
        return

    # 배치 검증
    verified, skipped, failed = verify_batch(data, verbose=verbose)
    _save_cache(data, output_path)
    if verbose:
        print(f"\n[OK] 저장: {output_path}", file=sys.stderr)
    print_summary(verified, skipped, failed)


if __name__ == "__main__":
    main()
