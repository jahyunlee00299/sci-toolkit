#!/usr/bin/env python3
"""참고문헌(논문) 자동 수집 도구 — DOI 목록을 받아 공개(OA) 경로로만 서지정보/PDF를 모은다.

데이터 소스 (전부 API 키 불필요):
    - CrossRef  https://api.crossref.org/works/{doi}
    - OpenAlex  https://api.openalex.org/works/doi:{doi}
    - Unpaywall https://api.unpaywall.org/v2/{doi}?email=...  (이메일 있을 때만)

캐시는 `ref_cache_manager.py`의 `RefCacheManager`를 그대로 재사용한다
(~/.claude/ref_cache/, DOI SHA256 해시 파일명). 이 스크립트가 캐시에 저장하는
레코드 스키마는 아래 `fetch_one()`이 만드는 dict 그대로다.

페이월 우회·스크래핑은 하지 않는다 — OA 링크가 없으면 그냥 `oa_status: closed`로
기록하고 넘어간다.

사용법:
    # 단일/복수 DOI (쉼표 구분)
    python ref_fetch.py --doi 10.1038/nature12373,10.1021/acs.jchemed.7b00361

    # 파일에서 DOI 읽기 (줄바꿈 구분)
    python ref_fetch.py --doi-file dois.txt

    # stdin에서 DOI 읽기
    cat dois.txt | python ref_fetch.py

    # 제목으로 검색해 DOI 해석 후 진행
    python ref_fetch.py --title "CRISPR gene editing efficiency"

    # PDF까지 다운로드 (OA인 것만)
    python ref_fetch.py --doi 10.1186/s13321-015-0069-3 --download

    # BibTeX 내보내기
    python ref_fetch.py --doi 10.1038/nature12373 --bibtex out.bib

    # 캐시 무시하고 강제 재조회
    python ref_fetch.py --doi 10.1038/nature12373 --refresh

    # Unpaywall 폴라이트 풀 이메일 (실제 이메일을 코드에 넣지 말 것)
    python ref_fetch.py --doi 10.1038/nature12373 --email you@example.com
    # 또는: export SCITK_CONTACT_EMAIL=you@example.com

출력:
    refs_report.json (DOI별 메타데이터·OA상태·교차검증·다운로드 경로) + stdout 요약.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional

# Windows 기본 콘솔은 cp949 라서 한글/기호 출력에서 죽는다. UTF-8로 맞춘다.
# TextIOWrapper 대신 reconfigure — 래퍼는 원본 스트림을 소유해서,
# import 후 GC 되면 호출자의 stdout 까지 닫아버린다(실측).
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

# ref_cache_manager.py 재사용 (같은 scripts/ 폴더)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ref_cache_manager import RefCacheManager  # noqa: E402

CROSSREF_BASE = "https://api.crossref.org/works"
OPENALEX_BASE = "https://api.openalex.org/works"
UNPAYWALL_BASE = "https://api.unpaywall.org/v2"

_TIMEOUT = 20
_MAX_RETRIES = 3
_RETRY_BACKOFF = 1.5  # 초, 시도마다 배수 증가
_RATE_LIMIT_DELAY = 0.5  # 요청 사이 최소 대기 (폴라이트 풀 권장)

_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")


# --------------------------------------------------------------------------- #
# 네트워크 헬퍼 — 타임아웃 + 재시도, User-Agent에 연락처(있을 때만)
# --------------------------------------------------------------------------- #


def _build_user_agent(email: Optional[str]) -> str:
    base = "sci-toolkit-ref_fetch/1.0 (https://github.com/; mailto:CONTACT)"
    if email:
        return base.replace("CONTACT", email)
    return "sci-toolkit-ref_fetch/1.0 (no-contact-provided)"


def _http_get_json(url: str, email: Optional[str], timeout: int = _TIMEOUT) -> tuple[Optional[dict], Optional[str]]:
    """GET 후 JSON 파싱. (data, error) 튜플 반환 — 성공 시 error=None.

    404 등 명확한 "존재하지 않음"은 조용히 (None, "not_found")로,
    그 외 네트워크/서버 오류는 재시도 후에도 실패하면 (None, 에러메시지)로 반환한다.
    """
    headers = {"User-Agent": _build_user_agent(email), "Accept": "application/json"}
    last_err = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                return json.loads(raw), None
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None, "not_found"
            last_err = f"HTTP {e.code}"
        except urllib.error.URLError as e:
            last_err = f"URLError: {e.reason}"
        except json.JSONDecodeError as e:
            last_err = f"JSON parse error: {e}"
        except Exception as e:  # noqa: BLE001 — 네트워크 실패 사유를 다 리포트에 남기기 위해 광범위 캐치
            last_err = f"{type(e).__name__}: {e}"

        if attempt < _MAX_RETRIES:
            time.sleep(_RETRY_BACKOFF * attempt)

    return None, last_err or "unknown_error"


def _http_get_text(url: str, email: Optional[str], timeout: int = _TIMEOUT) -> tuple[Optional[str], Optional[str]]:
    headers = {"User-Agent": _build_user_agent(email)}
    last_err = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace"), None
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None, "not_found"
            last_err = f"HTTP {e.code}"
        except Exception as e:  # noqa: BLE001
            last_err = f"{type(e).__name__}: {e}"

        if attempt < _MAX_RETRIES:
            time.sleep(_RETRY_BACKOFF * attempt)

    return None, last_err or "unknown_error"


def _download_pdf(url: str, dest: Path, email: Optional[str], timeout: int = 60) -> tuple[bool, Optional[str]]:
    """OA PDF 링크를 다운로드한다.

    OA 링크는 종종 실제 PDF가 아니라 랜딩 페이지(HTML)로 리다이렉트되거나
    (예: 발행처가 크롤러를 막고 인간용 페이지를 반환), 접근 제한 안내 페이지를
    돌려줄 수 있다. 파일 크기만으로는 이를 걸러낼 수 없으므로(관측된 실패
    사례: 3KB짜리 HTML이 크기 임계값은 통과) Content-Type 헤더와 PDF magic
    byte(`%PDF-`)를 모두 확인해야 진짜 PDF로 판정한다.
    """
    headers = {"User-Agent": _build_user_agent(email), "Accept": "application/pdf,*/*"}
    last_err = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                content_type = (resp.headers.get("Content-Type", "") or "").lower()
                data = resp.read()

                is_pdf_magic = data[:5] == b"%PDF-"
                is_pdf_content_type = "application/pdf" in content_type
                looks_like_html = content_type.startswith("text/html") or data.lstrip()[:15].lower().startswith(
                    (b"<!doctype html", b"<html")
                )

                if looks_like_html or not (is_pdf_magic or is_pdf_content_type):
                    return False, (
                        f"응답이 PDF가 아님 (Content-Type={content_type or 'unknown'}, "
                        f"magic_byte_ok={is_pdf_magic}, {len(data)} bytes) — 랜딩 페이지로 "
                        f"리다이렉트되었을 가능성"
                    )

                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
                return True, None
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code}"
            if e.code == 404:
                return False, last_err
        except Exception as e:  # noqa: BLE001
            last_err = f"{type(e).__name__}: {e}"

        if attempt < _MAX_RETRIES:
            time.sleep(_RETRY_BACKOFF * attempt)

    return False, last_err or "unknown_error"


# --------------------------------------------------------------------------- #
# DOI 정규화 / 파일명 안전화
# --------------------------------------------------------------------------- #


def normalize_doi(raw: str) -> str:
    """DOI 문자열 정규화 (URL prefix 제거, 소문자, 공백 제거)."""
    doi = raw.strip()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi, flags=re.IGNORECASE)
    doi = re.sub(r"^doi:\s*", "", doi, flags=re.IGNORECASE)
    return doi.strip()


def doi_to_safe_filename(doi: str) -> str:
    """DOI를 ASCII-safe 파일명으로 변환 (Windows cp949 문제 회피)."""
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", doi.strip().lower())
    return safe.strip("_")[:180]  # 과도한 길이 방지


# --------------------------------------------------------------------------- #
# CrossRef / OpenAlex / Unpaywall 조회
# --------------------------------------------------------------------------- #


def query_crossref(doi: str, email: Optional[str]) -> dict[str, Any]:
    url = f"{CROSSREF_BASE}/{urllib.parse.quote(doi)}"
    if email:
        url += f"?mailto={urllib.parse.quote(email)}"
    data, err = _http_get_json(url, email)
    if err == "not_found":
        return {"found": False, "error": "not_found"}
    if err:
        return {"found": False, "error": err}

    msg = (data or {}).get("message", {})
    authors = []
    for a in msg.get("author", []) or []:
        given = a.get("given", "")
        family = a.get("family", "")
        name = f"{given} {family}".strip() or a.get("name", "")
        if name:
            authors.append(name)

    year = None
    for date_field in ("published-print", "published-online", "issued", "created"):
        parts = (msg.get(date_field) or {}).get("date-parts")
        if parts and parts[0]:
            year = parts[0][0]
            break

    title_list = msg.get("title") or []
    return {
        "found": True,
        "title": title_list[0] if title_list else None,
        "authors": authors,
        "year": year,
        "journal": (msg.get("container-title") or [None])[0],
        "publisher": msg.get("publisher"),
        "type": msg.get("type"),
        "volume": msg.get("volume"),
        "issue": msg.get("issue"),
        "page": msg.get("page"),
        "is_referenced_by_count": msg.get("is-referenced-by-count"),
        "url": msg.get("URL"),
    }


def query_openalex(doi: str, email: Optional[str]) -> dict[str, Any]:
    url = f"{OPENALEX_BASE}/doi:{urllib.parse.quote(doi)}"
    if email:
        url += f"?mailto={urllib.parse.quote(email)}"
    data, err = _http_get_json(url, email)
    if err == "not_found":
        return {"found": False, "error": "not_found"}
    if err:
        return {"found": False, "error": err}

    d = data or {}
    authors = []
    for authorship in d.get("authorships", []) or []:
        name = (authorship.get("author") or {}).get("display_name")
        if name:
            authors.append(name)

    primary_loc = d.get("primary_location") or {}
    source = primary_loc.get("source") or {}
    oa = d.get("open_access") or {}
    best_oa = d.get("best_oa_location") or {}

    return {
        "found": True,
        "title": d.get("title"),
        "authors": authors,
        "year": d.get("publication_year"),
        "journal": source.get("display_name"),
        "type": d.get("type"),
        "is_oa": oa.get("is_oa"),
        "oa_status": oa.get("oa_status"),
        "best_oa_pdf_url": best_oa.get("pdf_url"),
        "best_oa_landing_page_url": best_oa.get("landing_page_url"),
        "cited_by_count": d.get("cited_by_count"),
        "openalex_id": d.get("id"),
    }


def query_unpaywall(doi: str, email: str) -> dict[str, Any]:
    url = f"{UNPAYWALL_BASE}/{urllib.parse.quote(doi)}?email={urllib.parse.quote(email)}"
    data, err = _http_get_json(url, email)
    if err == "not_found":
        return {"found": False, "error": "not_found"}
    if err:
        return {"found": False, "error": err}

    d = data or {}
    best_oa = d.get("best_oa_location") or {}
    return {
        "found": True,
        "is_oa": d.get("is_oa"),
        "oa_status": d.get("oa_status"),
        "best_oa_pdf_url": best_oa.get("url_for_pdf") or best_oa.get("url"),
        "best_oa_landing_page_url": best_oa.get("url_for_landing_page"),
        "license": best_oa.get("license"),
        "host_type": best_oa.get("host_type"),
    }


def resolve_doi_from_title(title: str, email: Optional[str]) -> Optional[str]:
    """제목으로 CrossRef bibliographic query를 날려 DOI 하나를 해석한다."""
    params = {"query.bibliographic": title, "rows": 1}
    if email:
        params["mailto"] = email
    url = f"{CROSSREF_BASE}?{urllib.parse.urlencode(params)}"
    data, err = _http_get_json(url, email)
    if err or not data:
        return None
    items = (data.get("message") or {}).get("items") or []
    if not items:
        return None
    return items[0].get("DOI")


# --------------------------------------------------------------------------- #
# 교차 검증
# --------------------------------------------------------------------------- #


def _norm_text(s: Optional[str]) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", s).strip().lower()


def cross_verify(crossref: dict, openalex: dict) -> list[str]:
    """CrossRef vs OpenAlex 필드 불일치를 찾아 사람이 읽을 수 있는 문자열 리스트로 반환.

    조용히 한쪽을 고르지 않는다 — 불일치가 있으면 둘 다 남긴다.
    """
    discrepancies: list[str] = []
    if not crossref.get("found") or not openalex.get("found"):
        return discrepancies

    # 제목 비교 (정규화 후 완전 일치 아니면 flag; 사소한 구두점 차이는 정규화로 흡수)
    cr_title = _norm_text(crossref.get("title"))
    oa_title = _norm_text(openalex.get("title"))
    if cr_title and oa_title and cr_title != oa_title:
        discrepancies.append(
            f"title mismatch — CrossRef: {crossref.get('title')!r} | OpenAlex: {openalex.get('title')!r}"
        )

    # 연도 비교
    cr_year = crossref.get("year")
    oa_year = openalex.get("year")
    if cr_year and oa_year and cr_year != oa_year:
        discrepancies.append(f"year mismatch — CrossRef: {cr_year} | OpenAlex: {oa_year}")

    # 저널명 비교
    cr_journal = _norm_text(crossref.get("journal"))
    oa_journal = _norm_text(openalex.get("journal"))
    if cr_journal and oa_journal and cr_journal != oa_journal:
        discrepancies.append(
            f"journal mismatch — CrossRef: {crossref.get('journal')!r} | OpenAlex: {openalex.get('journal')!r}"
        )

    # 저자 수 비교 (이름 표기가 소스마다 달라 개수만 대략 비교 — 큰 차이만 flag)
    cr_authors = crossref.get("authors") or []
    oa_authors = openalex.get("authors") or []
    if cr_authors and oa_authors and abs(len(cr_authors) - len(oa_authors)) >= 2:
        discrepancies.append(
            f"author count mismatch — CrossRef: {len(cr_authors)}명 {cr_authors} | "
            f"OpenAlex: {len(oa_authors)}명 {oa_authors}"
        )

    return discrepancies


# --------------------------------------------------------------------------- #
# 메인 fetch-one 파이프라인
# --------------------------------------------------------------------------- #


def _reconcile_cached_download(
    cached: dict[str, Any], pdf_dir: Path, email: Optional[str]
) -> Optional[dict[str, Any]]:
    """Make a cache hit's download path true for THIS call's --pdf-dir.

    The cache is keyed by DOI alone, so a hit replays the download record from
    whichever run first populated it. That record names the *earlier* run's
    --pdf-dir. Returning it unchanged reports status "ok" while the directory
    the caller actually asked for stays empty, and a caller that trusts the
    report gets nothing (reproduced: two runs, same DOI, different --pdf-dir).

    Returns the record with download.path pointing inside pdf_dir, or None when
    the cached PDF cannot be recovered and a fresh fetch is required.
    """
    dl = cached.get("download") or {}
    if dl.get("status") != "ok":
        # "skipped" / "failed" promise no file, so they cannot mislead.
        return cached

    dest = pdf_dir / f"{doi_to_safe_filename(cached['doi'])}.pdf"
    if dest.is_file():
        dl["path"] = str(dest)
        return cached

    src = Path(dl.get("path", ""))
    if src.is_file():
        pdf_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        dl["path"] = str(dest)
        dl["reused_from_cache"] = str(src)
        return cached

    # The cached path no longer exists (temp dir cleaned, run on another
    # machine, file deleted). Re-download from the OA URL the cache still holds.
    oa_pdf_url = cached.get("oa_pdf_url")
    if oa_pdf_url:
        pdf_dir.mkdir(parents=True, exist_ok=True)
        ok, err = _download_pdf(oa_pdf_url, dest, email)
        if ok:
            cached["download"] = {"status": "ok", "path": str(dest),
                                  "redownloaded": True}
            return cached
        cached["download"] = {"status": "failed", "error": err,
                              "attempted_url": oa_pdf_url}
        return cached
    return None


def fetch_one(
    doi: str,
    cache: RefCacheManager,
    email: Optional[str],
    refresh: bool,
    download: bool,
    pdf_dir: Path,
) -> dict[str, Any]:
    doi = normalize_doi(doi)

    if not _DOI_RE.match(doi):
        return {
            "doi": doi,
            "status": "error",
            "error": f"DOI 형식이 아님: {doi!r}",
        }

    if not refresh and cache.has(doi):
        cached = cache.get(doi)
        if cached:
            cached["status"] = "cache_hit"
            if download:
                reconciled = _reconcile_cached_download(cached, pdf_dir, email)
                if reconciled is not None:
                    return reconciled
                # Cached PDF is unrecoverable; fall through and fetch afresh.
            else:
                return cached

    crossref = query_crossref(doi, email)
    time.sleep(_RATE_LIMIT_DELAY)
    openalex = query_openalex(doi, email)
    time.sleep(_RATE_LIMIT_DELAY)

    if not crossref.get("found") and not openalex.get("found"):
        record = {
            "doi": doi,
            "status": "not_found",
            "crossref": crossref,
            "openalex": openalex,
            "discrepancies": [],
            "oa_status": "unknown",
            "download": None,
        }
        return record  # 캐시에는 저장하지 않음 — 일시적 오류일 수 있음

    discrepancies = cross_verify(crossref, openalex)

    # OA 링크 해석: Unpaywall(이메일 있을 때) > OpenAlex best_oa_location
    unpaywall = None
    oa_pdf_url = None
    oa_landing_url = None
    oa_status = "closed"

    if email:
        unpaywall = query_unpaywall(doi, email)
        time.sleep(_RATE_LIMIT_DELAY)
        if unpaywall.get("found"):
            if unpaywall.get("is_oa"):
                oa_status = unpaywall.get("oa_status") or "open"
                oa_pdf_url = unpaywall.get("best_oa_pdf_url")
                oa_landing_url = unpaywall.get("best_oa_landing_page_url")

    if not oa_pdf_url and openalex.get("found") and openalex.get("is_oa"):
        oa_status = openalex.get("oa_status") or "open"
        oa_pdf_url = openalex.get("best_oa_pdf_url")
        oa_landing_url = openalex.get("best_oa_landing_page_url")

    record: dict[str, Any] = {
        "doi": doi,
        "status": "fetched",
        "crossref": crossref,
        "openalex": openalex,
        "unpaywall": unpaywall,
        "discrepancies": discrepancies,
        "oa_status": oa_status,
        "oa_pdf_url": oa_pdf_url,
        "oa_landing_page_url": oa_landing_url,
        "download": None,
    }

    if download:
        if oa_pdf_url:
            dest = pdf_dir / f"{doi_to_safe_filename(doi)}.pdf"
            ok, err = _download_pdf(oa_pdf_url, dest, email)
            if ok:
                record["download"] = {"status": "ok", "path": str(dest)}
            else:
                record["download"] = {
                    "status": "failed",
                    "error": err,
                    "attempted_url": oa_pdf_url,
                }
        else:
            record["download"] = {"status": "skipped", "reason": "no_oa_pdf_link (oa_status=closed)"}

    cache.put(doi, record)
    return record


# --------------------------------------------------------------------------- #
# BibTeX 내보내기 (CrossRef application/x-bibtex)
# --------------------------------------------------------------------------- #


def fetch_bibtex(doi: str, email: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    url = f"{CROSSREF_BASE}/{urllib.parse.quote(doi)}/transform/application/x-bibtex"
    headers = {"User-Agent": _build_user_agent(email), "Accept": "application/x-bibtex"}
    last_err = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                return resp.read().decode("utf-8", errors="replace"), None
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None, "not_found"
            last_err = f"HTTP {e.code}"
        except Exception as e:  # noqa: BLE001
            last_err = f"{type(e).__name__}: {e}"
        if attempt < _MAX_RETRIES:
            time.sleep(_RETRY_BACKOFF * attempt)
    return None, last_err or "unknown_error"


# --------------------------------------------------------------------------- #
# 입력 파싱
# --------------------------------------------------------------------------- #


def collect_dois(args: argparse.Namespace, email: Optional[str]) -> list[str]:
    dois: list[str] = []

    if args.doi:
        dois.extend(part.strip() for part in args.doi.split(",") if part.strip())

    if args.doi_file:
        p = Path(args.doi_file)
        if not p.exists():
            print(f"[ERROR] DOI 파일 없음: {p}", file=sys.stderr)
        else:
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    dois.append(line)

    if args.title:
        resolved = resolve_doi_from_title(args.title, email)
        if resolved:
            print(f"[INFO] 제목 검색 결과 DOI: {resolved}", file=sys.stderr)
            dois.append(resolved)
        else:
            print(f"[WARN] 제목으로 DOI를 찾지 못함: {args.title!r}", file=sys.stderr)

    # stdin (파이프로 들어온 경우만, 인자 없을 때)
    if not dois and not sys.stdin.isatty():
        for line in sys.stdin.read().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                dois.append(line)

    # 중복 제거 (순서 보존)
    seen = set()
    unique = []
    for d in dois:
        nd = normalize_doi(d)
        if nd not in seen:
            seen.add(nd)
            unique.append(nd)
    return unique


# --------------------------------------------------------------------------- #
# 사람이 읽는 요약 출력
# --------------------------------------------------------------------------- #


def print_summary(results: list[dict[str, Any]]) -> None:
    print("\n=== ref_fetch 결과 요약 ===")
    print(f"  총 DOI: {len(results)}")

    ok = [r for r in results if r.get("status") in ("fetched", "cache_hit")]
    not_found = [r for r in results if r.get("status") == "not_found"]
    errors = [r for r in results if r.get("status") == "error"]
    open_oa = [r for r in results if r.get("oa_status") not in (None, "closed", "unknown")]
    with_discrepancies = [r for r in results if r.get("discrepancies")]

    print(f"  조회 성공:   {len(ok)}")
    print(f"  존재하지 않음(404 등): {len(not_found)}")
    print(f"  오류(형식/네트워크): {len(errors)}")
    print(f"  OA(공개) 확인: {len(open_oa)}")
    print(f"  교차검증 불일치 있는 항목: {len(with_discrepancies)}")

    for r in results:
        doi = r.get("doi", "?")
        status = r.get("status", "?")
        title = None
        if r.get("crossref", {}).get("found"):
            title = r["crossref"].get("title")
        elif r.get("openalex", {}).get("found"):
            title = r["openalex"].get("title")
        title_str = f" — {title}" if title else ""
        print(f"\n  [{doi}] status={status}{title_str}")

        if status == "error":
            print(f"    오류: {r.get('error')}")
            continue
        if status == "not_found":
            cr_err = r.get("crossref", {}).get("error")
            oa_err = r.get("openalex", {}).get("error")
            print(f"    CrossRef: {cr_err} / OpenAlex: {oa_err}")
            continue

        print(f"    oa_status: {r.get('oa_status')}")
        if r.get("discrepancies"):
            print("    [!] 교차검증 불일치:")
            for d in r["discrepancies"]:
                print(f"        - {d}")
        dl = r.get("download")
        if dl:
            if dl.get("status") == "ok":
                print(f"    PDF 다운로드: {dl.get('path')}")
            elif dl.get("status") == "failed":
                print(f"    PDF 다운로드 실패: {dl.get('error')}")
            elif dl.get("status") == "skipped":
                print(f"    PDF 다운로드 생략: {dl.get('reason')}")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _run_doi_gate(
    doi: str,
    expect_title: str,
    email: Optional[str],
    refresh: bool,
    cache_dir: Optional[str],
) -> int:
    """수집 전 DOI 관문 — doi_verify.py 를 별도 프로세스로 돌리고 exit code 를 읽는다.

    왜 import 가 아니라 subprocess 인가:
      ① doi_verify.py 가 이 모듈(ref_fetch)을 import 한다. 반대로 여기서 import
         하면 순환이 된다.
      ② 이 저장소의 게이트 관례가 "스크립트를 돌리고 종료 코드를 읽는다"이다
         (CLAUDE.md: 눈으로 판단하지 말고 exit code 를 볼 것).

    반환: doi_verify 의 exit code (0=통과, 1=대조 실패류, 2=환각/철회).
    """
    script = Path(__file__).resolve().parent / "doi_verify.py"
    if not script.exists():
        print(f"[WARN] doi_verify.py 를 찾지 못해 관문을 건너뜁니다: {script}", file=sys.stderr)
        return 0

    cmd = [
        sys.executable, str(script),
        "--doi", doi,
        "--expect-title", expect_title,
        "--output", os.devnull,
    ]
    if email:
        cmd += ["--email", email]
    if refresh:
        cmd += ["--refresh"]
    if cache_dir:
        cmd += ["--cache-dir", cache_dir]

    print(f"[GATE] 수집 전 DOI 대조: {doi}", file=sys.stderr)
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (proc.stdout or "") + (proc.stderr or "")
    for line in out.splitlines():
        if any(k in line for k in ("HALLUCINATED", "RETRACTED", "MISMATCH", "UNCORROBORATED", "[PASS]", "[FAIL]", "[WARN]")):
            print(f"       {line.strip()}", file=sys.stderr)
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser(
        description="DOI 목록으로 공개(OA) 경로 서지정보/PDF를 수집한다 (CrossRef+OpenAlex+Unpaywall, API 키 불필요).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--doi", help="쉼표로 구분된 DOI 목록")
    parser.add_argument("--doi-file", help="DOI가 줄바꿈으로 나열된 파일 경로")
    parser.add_argument("--title", help="제목으로 검색해 DOI를 해석한 뒤 진행")
    parser.add_argument(
        "--email",
        default=None,
        help="Unpaywall/폴라이트 풀용 연락처 이메일 (없으면 SCITK_CONTACT_EMAIL 환경변수 사용, "
        "둘 다 없으면 Unpaywall 단계만 건너뜀)",
    )
    parser.add_argument("--download", action="store_true", help="OA PDF를 실제로 다운로드")
    parser.add_argument(
        "--pdf-dir",
        default=None,
        help="PDF 저장 디렉토리 (기본: ./ref_fetch_pdfs/)",
    )
    parser.add_argument("--refresh", action="store_true", help="캐시를 무시하고 강제로 재조회")
    parser.add_argument(
        "--output",
        default="refs_report.json",
        help="결과 JSON 저장 경로 (기본: refs_report.json)",
    )
    parser.add_argument("--bibtex", default=None, help="CrossRef BibTeX를 이 경로로 저장")
    parser.add_argument("--cache-dir", default=None, help="ref_cache_manager 캐시 디렉토리 (기본값 사용 권장)")
    parser.add_argument(
        "--doi-source",
        choices=["human", "model"],
        default=None,
        help="DOI 출처. model(LLM 생성)은 --expect-title 없이 수집에 진입할 수 없다.",
    )
    parser.add_argument(
        "--expect-title",
        default=None,
        help="이 DOI가 가리킬 것으로 의도한 제목. 수집 전 doi_verify 로 대조한다.",
    )
    parser.add_argument(
        "--with-si",
        action="store_true",
        help="보충자료(SI)도 수집한다 (Europe PMC 공개 경로만; 그 밖은 링크 안내).",
    )
    parser.add_argument("--si-dir", default=None, help="SI 저장 디렉토리 (기본: ./ref_fetch_si)")
    parser.add_argument(
        "--institution",
        default=None,
        help="페이월 논문에 기관 도서관 접속 링크를 붙인다 (config/institutions.json 의 키). "
        "링크만 만들며 로그인·다운로드는 하지 않는다.",
    )

    args = parser.parse_args()

    # --- 0단계: DOI 관문 --------------------------------------------------- #
    # LLM이 생성한 DOI는 형식이 완벽해도 실재하는 *무관한* 논문에 착지할 수 있다
    # (doi_verify.py 의 122211/122213 실측). 그래서 수집(네트워크 조회·다운로드)에
    # 들어가기 전에 막는다 — 뒤에서 등급으로 걸러내는 것보다 확실하다.
    if args.doi_source == "model" and not args.expect_title:
        print(
            "[BLOCKED] --doi-source model 은 --expect-title 없이 쓸 수 없습니다.\n"
            "          LLM이 생성한 DOI는 존재 여부만으로 검증되지 않습니다 — "
            "찾으려던 논문 제목을 함께 선언하세요.",
            file=sys.stderr,
        )
        return 2

    email = args.email or os.getenv("SCITK_CONTACT_EMAIL") or None
    if not email:
        print(
            "[INFO] --email / SCITK_CONTACT_EMAIL 없음 — Unpaywall 단계는 건너뛰고 "
            "OpenAlex의 OA 정보만 사용합니다.",
            file=sys.stderr,
        )

    dois = collect_dois(args, email)
    if not dois:
        print("[ERROR] DOI가 없습니다. --doi / --doi-file / --title / stdin 중 하나로 입력하세요.", file=sys.stderr)
        parser.print_help()
        return 1

    # 제목이 선언됐다면 수집 전에 doi_verify 로 대조한다. 통과 못 하면 진입 차단.
    if args.expect_title:
        if len(dois) != 1:
            print(
                "[ERROR] --expect-title 은 DOI 하나에만 붙일 수 있습니다 "
                f"(현재 {len(dois)}건).",
                file=sys.stderr,
            )
            return 1
        gate_rc = _run_doi_gate(dois[0], args.expect_title, email, args.refresh, args.cache_dir)
        if gate_rc != 0:
            print(
                "[BLOCKED] DOI 관문을 통과하지 못해 수집을 중단합니다 "
                f"(doi_verify exit={gate_rc}).",
                file=sys.stderr,
            )
            return gate_rc

    cache = RefCacheManager(cache_dir=args.cache_dir)
    pdf_dir = Path(args.pdf_dir) if args.pdf_dir else Path.cwd() / "ref_fetch_pdfs"
    si_dir = Path(args.si_dir) if args.si_dir else Path.cwd() / "ref_fetch_si"

    institutions = None
    if args.institution:
        from institutional_access import InstitutionRegistry  # 지연 import (선택 기능)

        institutions = InstitutionRegistry.load()

    results: list[dict[str, Any]] = []
    for i, doi in enumerate(dois, 1):
        print(f"[{i}/{len(dois)}] 처리 중: {doi}", file=sys.stderr)
        try:
            record = fetch_one(
                doi=doi,
                cache=cache,
                email=email,
                refresh=args.refresh,
                download=args.download,
                pdf_dir=pdf_dir,
            )
        except Exception as e:  # noqa: BLE001 — 개별 DOI 실패가 전체를 죽이지 않게
            record = {"doi": doi, "status": "error", "error": f"{type(e).__name__}: {e}"}

        # 페이월이면 본문 대신 '사람이 클릭할 링크'를 붙인다. 자동 다운로드는 하지 않는다
        # (구독 원문을 스크립트로 받는 것은 도서관 공정이용 규정 위반이다).
        if institutions is not None and record.get("oa_status") == "closed":
            target = (
                record.get("oa_landing_page_url")
                or (record.get("crossref") or {}).get("url")
                or f"https://doi.org/{doi}"
            )
            link = institutions.build_link(args.institution, target)
            if link:
                record["institutional_access"] = {
                    "institution": link.institution,
                    "url": link.url,
                    "login_note": link.login_note,
                    "fair_use_url": link.fair_use_url,
                    "daily_limits": link.daily_limits,
                    "_note": "사람이 브라우저에서 여는 링크. 자동 다운로드 아님.",
                }
                print(link.human_summary(), file=sys.stderr)

        # SI 는 본문과 접근성이 다르다 — 본문이 페이월이어도 열려 있을 수 있다.
        if args.with_si:
            from si_fetch import discover_si, download_si  # 지연 import

            try:
                si_res = discover_si(doi, email)
                if si_res.status == "found" and args.download:
                    si_res = download_si(si_res, si_dir, extract=True, si_only=True)
                record["supplementary"] = si_res.to_dict()
                n_si = len(si_res.supplementary_files)
                if si_res.status == "found":
                    print(f"  SI: {n_si}개 발견 ({si_res.pmcid})", file=sys.stderr)
                elif si_res.manual_hint:
                    print(f"  SI: {si_res.manual_hint}", file=sys.stderr)
            except Exception as e:  # noqa: BLE001 — SI 실패가 본문 수집을 죽이지 않게
                record["supplementary"] = {"status": "error", "error": f"{type(e).__name__}: {e}"}

        results.append(record)

        if args.bibtex and record.get("status") in ("fetched", "cache_hit"):
            pass  # BibTeX는 아래에서 별도 처리 (실패해도 리포트 흐름 방해 안 함)

    # 출력 리포트 저장
    output_path = Path(args.output)
    report = {
        "generated_by": "ref_fetch.py",
        "dois_requested": len(dois),
        "email_used_for_unpaywall": bool(email),
        "results": results,
    }
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[OK] 리포트 저장: {output_path}", file=sys.stderr)

    # BibTeX 내보내기
    if args.bibtex:
        bib_entries = []
        bib_errors = []
        for doi in dois:
            bib_text, err = fetch_bibtex(doi, email)
            time.sleep(_RATE_LIMIT_DELAY)
            if bib_text:
                bib_entries.append(bib_text.strip())
            else:
                bib_errors.append(f"% {doi}: BibTeX 조회 실패 ({err})")
        bib_path = Path(args.bibtex)
        content = "\n\n".join(bib_entries)
        if bib_errors:
            content += "\n\n" + "\n".join(bib_errors)
        bib_path.write_text(content + "\n", encoding="utf-8")
        print(f"[OK] BibTeX 저장: {bib_path} ({len(bib_entries)}건 성공, {len(bib_errors)}건 실패)", file=sys.stderr)

    print_summary(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
