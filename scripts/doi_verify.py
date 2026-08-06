#!/usr/bin/env python3
"""DOI 교차검증 도구 — 이미 원고/문서에 들어간 DOI가 실재하는지, 서지정보가
맞는지 확인하는 게이트 스크립트.

`ref_fetch.py`(수집용: DOI → 서지정보+OA PDF)와 역할이 다르다. 이 스크립트는
**검증**용이다: 문서/BibTeX에 이미 박힌 DOI가 (a) 실제로 존재하는지, (b) 적힌
저자/연도/제목과 실제 레코드가 일치하는지, (c) 철회(retracted)되지 않았는지를
확인해 등급을 매긴다. AGENTS.md §8 "literature-review / endnote-citation-injection"
행의 게이트 도구다 — 환각 DOI가 원고에 들어가는 사고를 막는다.

재사용: CrossRef/OpenAlex 조회 함수·정규화·캐시는 `ref_fetch.py`/
`ref_cache_manager.py`를 그대로 import해서 쓴다. 조회 로직을 새로 짜지 않는다
(중복 구현은 두 도구가 다른 답을 내는 사고로 이어진다).

검증 등급 (심각도 내림차순):
    HALLUCINATED    — CrossRef와 OpenAlex 양쪽 모두 존재하지 않음
    RETRACTED       — OpenAlex가 is_retracted=True 로 보고
    MISMATCH        — 존재는 하지만 문서에 적힌 저자/연도/제목이 실제 레코드와 다름
    ONE_SOURCE_ONLY — 두 소스 중 한쪽에서만 조회됨 (조용히 통과시키지 않음)
    UNVERIFIED      — 조회 자체가 실패함 (네트워크 오류 등) — "확인 못 했다" ≠ "괜찮다"
    OK              — 존재 확인 + (메타데이터 제공 시) 일치 + 철회 아님

exit code:
    2 — HALLUCINATED 또는 RETRACTED 가 하나라도 있음
    1 — (2가 아니면서) MISMATCH/ONE_SOURCE_ONLY/UNVERIFIED 가 하나라도 있음
    0 — 전부 OK

사용법:
    # 문서에서 DOI 자동 추출
    python doi_verify.py --file manuscript.md

    # DOI 직접 지정
    python doi_verify.py --doi 10.1038/nature12373,10.9999/nonexistent.12345

    # BibTeX — 저자/연도/제목까지 대조
    python doi_verify.py --bibtex refs.bib

    # 캐시 무시하고 강제 재조회
    python doi_verify.py --doi 10.1038/nature12373 --refresh

    # Unpaywall 등 폴라이트 풀용 이메일 (실제 이메일을 코드에 넣지 말 것)
    python doi_verify.py --bibtex refs.bib --email you@example.com
    # 또는: export SCITK_CONTACT_EMAIL=you@example.com

출력:
    doi_verify_report.json (DOI별 등급·근거) + stdout 사람이 읽는 요약
    (등급별로 묶어서: HALLUCINATED -> RETRACTED -> MISMATCH -> ONE_SOURCE_ONLY
     -> UNVERIFIED -> OK)
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

# ref_fetch.py / ref_cache_manager.py 재사용 (같은 scripts/ 폴더).
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

# Windows 기본 콘솔은 cp949 라서 한글/기호 출력에서 죽는다. UTF-8로 맞춘다.
# TextIOWrapper 대신 reconfigure — 래퍼는 원본 스트림을 소유해서, 이 모듈이
# import 된 뒤 GC 되거나 다른 모듈이 또 감싸면 공유 buffer 가 닫혀
# "I/O operation on closed file" 로 죽는다(실측). reconfigure 는 같은 객체를
# 바꾸므로 몇 번 호출하든, 어떤 순서로 import 하든 안전하다.
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")

# 문서(.md/.txt)에서 DOI를 뽑아내는 정규식. DOI 뒤에 흔히 붙는 문장부호/괄호는
# 잘라낸다 — 안 그러면 "10.1038/nature12373." 처럼 마침표가 DOI에 섞여 조회가
# 항상 실패한다.
_DOI_EXTRACT_RE = re.compile(r"10\.\d{4,9}/[^\s\]\)\"'<>,;]+")
_TRAILING_PUNCT_RE = re.compile(r"[.,;:)\]\"'>]+$")

# BibTeX 항목 하나(중괄호 균형은 무시하고 최상위 필드만 정규식으로 뽑는다 —
# 완전한 BibTeX 파서가 필요할 만큼 복잡한 입력은 대상이 아님)
_BIBTEX_ENTRY_RE = re.compile(r"@\w+\s*\{\s*([^,]+),(.*?)\n\}", re.DOTALL)
_BIBTEX_FIELD_RE = re.compile(r"(\w+)\s*=\s*[{\"](.*?)[}\"]\s*,?\s*$", re.MULTILINE | re.DOTALL)


# --------------------------------------------------------------------------- #
# OpenAlex 철회(retracted) 여부 — ref_fetch.py의 query_openalex()는 이 필드를
# 반환하지 않으므로(가공된 서지정보 dict만 만듦), _http_get_json 저수준 헬퍼만
# 재사용해 원본 응답에서 is_retracted 하나만 얇게 뽑는다. query_openalex 자체를
# 다시 구현하지 않는다 — 이 함수는 순수 부가 정보 하나만 얹는다.
# --------------------------------------------------------------------------- #


def query_openalex_retracted(doi: str, email: Optional[str]) -> Optional[bool]:
    """OpenAlex 원본 응답에서 is_retracted 값만 반환. 조회 실패 시 None."""
    url = f"{OPENALEX_BASE}/doi:{urllib.parse.quote(doi)}"
    if email:
        url += f"?mailto={urllib.parse.quote(email)}"
    data, err = _http_get_json(url, email)
    if err or not data:
        return None
    return bool(data.get("is_retracted", False))


# --------------------------------------------------------------------------- #
# DOI 추출
# --------------------------------------------------------------------------- #


def extract_dois_from_text(text: str) -> list[str]:
    """자유 텍스트(.md/.txt)에서 DOI를 정규식으로 추출한다 (중복 제거, 순서 보존)."""
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
    """BibTeX 항목들을 파싱해 doi/author/year/title 필드를 뽑는다.

    완전한 BibTeX 문법을 지원하지 않는다(중첩 중괄호가 있는 필드 등은
    최선 노력으로만 처리) — 이 도구의 목적은 DOI 존재/메타데이터 대조이지
    BibTeX 파서가 아니다.
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
# 메타데이터 대조 (오탐 방지가 핵심 — 표기 차이만으로 MISMATCH 내지 않는다)
# --------------------------------------------------------------------------- #


def _normalize_title(s: Optional[str]) -> str:
    if not s:
        return ""
    s = s.lower()
    s = re.sub(r"[^\w\s]", "", s)  # 구두점 제거 (대소문자/구두점 차이 흡수)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def title_similarity(a: Optional[str], b: Optional[str]) -> float:
    """정규화 후 SequenceMatcher 유사도 (0~1). 구두점/대소문자 차이에 강건."""
    na, nb = _normalize_title(a), _normalize_title(b)
    if not na or not nb:
        return 0.0
    return difflib.SequenceMatcher(None, na, nb).ratio()


def _extract_surnames(author_field: Optional[str]) -> list[str]:
    """BibTeX author 필드에서 성(姓)만 뽑는다.

    BibTeX 관례 두 가지를 모두 지원: "Family, Given" 와 "Given Family".
    저자는 " and "로 구분된다. 이름 표기(이니셜 vs 풀네임, 미들네임 유무)는
    소스마다 다르므로(CrossRef vs OpenAlex도 다르다 — ref_fetch.py 관측)
    성만 비교 대상으로 삼는다.
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
    """CrossRef/OpenAlex의 "Given Family" 형태 이름 리스트에서 성만 뽑는다."""
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
    """문서/BibTeX에 적힌 메타데이터 vs 실제 레코드(CrossRef 우선, 없으면
    OpenAlex) 대조. 불일치 사유 문자열 리스트를 반환 (비어있으면 일치).

    오탐 방지 원칙: 제목은 정규화 후 유사도 임계값 이하일 때만, 저자는
    "성(姓) 집합"이 하나도 안 겹칠 때만 flag한다 — 표기 차이(이니셜 vs
    풀네임, 대소문자, 구두점)만으로는 절대 MISMATCH를 내지 않는다.
    """
    reasons: list[str] = []
    record = crossref if crossref.get("found") else openalex
    if not record.get("found"):
        return reasons  # 존재 자체가 안 되면 HALLUCINATED가 이미 처리 — 여기선 스킵

    # 연도 — 정확히 다르면 flag (연도는 표기 변형의 여지가 없다)
    exp_year = expected.get("year")
    rec_year = record.get("year")
    if exp_year and rec_year and int(exp_year) != int(rec_year):
        reasons.append(f"year mismatch — expected: {exp_year} | actual: {rec_year}")

    # 제목 — 정규화 유사도 0.7 미만일 때만 flag
    exp_title = expected.get("title")
    rec_title = record.get("title")
    if exp_title and rec_title:
        sim = title_similarity(exp_title, rec_title)
        if sim < 0.7:
            reasons.append(
                f"title mismatch (similarity={sim:.2f}) — expected: {exp_title!r} | actual: {rec_title!r}"
            )

    # 저자 — 성(姓) 집합이 하나도 안 겹치면 flag (표기 차이는 무시)
    exp_surnames = set(_extract_surnames(expected.get("author_raw")))
    rec_surnames = set(_extract_surnames_from_names(record.get("authors") or []))
    if exp_surnames and rec_surnames and exp_surnames.isdisjoint(rec_surnames):
        reasons.append(
            f"author mismatch — expected surnames: {sorted(exp_surnames)} | "
            f"actual surnames: {sorted(rec_surnames)}"
        )

    return reasons


# --------------------------------------------------------------------------- #
# 등급 결정
# --------------------------------------------------------------------------- #

GRADE_ORDER = ["HALLUCINATED", "RETRACTED", "MISMATCH", "ONE_SOURCE_ONLY", "UNVERIFIED", "OK"]


def grade_one(
    doi: str,
    expected: Optional[dict[str, Any]],
    crossref: dict[str, Any],
    openalex: dict[str, Any],
) -> dict[str, Any]:
    """DOI 하나에 대한 등급 판정. (crossref/openalex는 각각 found + error 등
    ref_fetch.py의 query_crossref/query_openalex 반환 형식.)
    """
    cr_ok = crossref.get("found") is True
    oa_ok = openalex.get("found") is True

    cr_network_fail = not cr_ok and crossref.get("error") not in (None, "not_found")
    oa_network_fail = not oa_ok and openalex.get("error") not in (None, "not_found")

    reasons: list[str] = []

    # 둘 다 네트워크 자체가 실패 (존재 여부를 판정할 수 없음) → UNVERIFIED
    if cr_network_fail and oa_network_fail:
        return {
            "doi": doi,
            "grade": "UNVERIFIED",
            "reasons": [
                f"CrossRef 조회 실패: {crossref.get('error')}",
                f"OpenAlex 조회 실패: {openalex.get('error')}",
            ],
            "crossref": crossref,
            "openalex": openalex,
        }

    # 한쪽은 네트워크 실패, 다른 한쪽은 확실히 not_found → 존재 여부 불확실 → UNVERIFIED
    # (실패한 쪽이 사실 존재했을 수도 있으므로 HALLUCINATED로 단정하지 않는다)
    if cr_network_fail and not oa_ok:
        return {
            "doi": doi,
            "grade": "UNVERIFIED",
            "reasons": [
                f"CrossRef 조회 실패(네트워크): {crossref.get('error')}",
                "OpenAlex: not_found — 두 소스 모두 확정할 수 없어 HALLUCINATED로 단정하지 않음",
            ],
            "crossref": crossref,
            "openalex": openalex,
        }
    if oa_network_fail and not cr_ok:
        return {
            "doi": doi,
            "grade": "UNVERIFIED",
            "reasons": [
                f"OpenAlex 조회 실패(네트워크): {openalex.get('error')}",
                "CrossRef: not_found — 두 소스 모두 확정할 수 없어 HALLUCINATED로 단정하지 않음",
            ],
            "crossref": crossref,
            "openalex": openalex,
        }

    # 양쪽 다 명확히 존재하지 않음 (404 등, 네트워크 실패 아님) → HALLUCINATED
    if not cr_ok and not oa_ok:
        return {
            "doi": doi,
            "grade": "HALLUCINATED",
            "reasons": [
                f"CrossRef: {crossref.get('error', 'not_found')}",
                f"OpenAlex: {openalex.get('error', 'not_found')}",
                "두 소스 모두 이 DOI를 찾지 못함 — 환각(hallucinated) DOI일 가능성이 높음",
            ],
            "crossref": crossref,
            "openalex": openalex,
        }

    # 철회 여부 (OpenAlex is_retracted)
    if oa_ok and openalex.get("is_retracted"):
        reasons.append("OpenAlex: is_retracted=True — 이 논문은 철회(retracted)되었음")
        return {
            "doi": doi,
            "grade": "RETRACTED",
            "reasons": reasons,
            "crossref": crossref,
            "openalex": openalex,
        }

    # 한쪽만 존재
    if cr_ok != oa_ok:
        which = "CrossRef" if cr_ok else "OpenAlex"
        missing = "OpenAlex" if cr_ok else "CrossRef"
        missing_err = (openalex if cr_ok else crossref).get("error", "not_found")
        return {
            "doi": doi,
            "grade": "ONE_SOURCE_ONLY",
            "reasons": [f"{which}에서만 확인됨 ({missing}: {missing_err}) — 조용히 통과시키지 않음"],
            "crossref": crossref,
            "openalex": openalex,
        }

    # 둘 다 존재 — 메타데이터 대조 (expected가 주어졌을 때만)
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

    return {
        "doi": doi,
        "grade": "OK",
        "reasons": ["존재 확인(CrossRef+OpenAlex 양쪽)" + (", 메타데이터 일치" if expected else "")],
        "crossref": crossref,
        "openalex": openalex,
    }


# --------------------------------------------------------------------------- #
# 메인 verify-one 파이프라인 (캐시 재사용)
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
            "reasons": [f"DOI 형식이 아님: {doi!r} — 형식부터 실재하지 않는 값일 가능성"],
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

    # 존재가 확인된 경우에만 철회(retracted) 여부를 추가 조회 — 불필요한
    # 네트워크 호출을 늘리지 않는다.
    if openalex.get("found"):
        is_retracted = query_openalex_retracted(doi, email)
        time.sleep(_RATE_LIMIT_DELAY)
        openalex = dict(openalex)
        openalex["is_retracted"] = is_retracted

    # 조회 결과(존재/미존재 판정에 필요한 원본)는 캐시에 저장 — 네트워크 실패
    # 결과(UNVERIFIED로 이어질 것)는 캐시하지 않는다(일시적 오류일 수 있음).
    cr_network_fail = not crossref.get("found") and crossref.get("error") not in (None, "not_found")
    oa_network_fail = not openalex.get("found") and openalex.get("error") not in (None, "not_found")
    if not (cr_network_fail or oa_network_fail):
        cache.put(cache_key, {"crossref": crossref, "openalex": openalex})

    result = grade_one(doi, expected, crossref, openalex)
    result["from_cache"] = False
    return result


# --------------------------------------------------------------------------- #
# 입력 수집
# --------------------------------------------------------------------------- #


def collect_targets(args: argparse.Namespace) -> list[dict[str, Any]]:
    """검증 대상 목록을 만든다. 각 항목은 최소 {"doi": ...}, BibTeX 입력이면
    author_raw/year/title도 포함.
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
                _add(part)

    if args.file:
        p = Path(args.file)
        if not p.exists():
            print(f"[ERROR] 파일 없음: {p}", file=sys.stderr)
        else:
            text = p.read_text(encoding="utf-8", errors="replace")
            for doi in extract_dois_from_text(text):
                _add(doi)

    if args.bibtex:
        p = Path(args.bibtex)
        if not p.exists():
            print(f"[ERROR] 파일 없음: {p}", file=sys.stderr)
        else:
            text = p.read_text(encoding="utf-8", errors="replace")
            entries = parse_bibtex(text)
            if not entries:
                print(f"[WARN] BibTeX에서 doi 필드가 있는 항목을 찾지 못함: {p}", file=sys.stderr)
            for e in entries:
                _add(
                    e["doi"],
                    expected={"author_raw": e.get("author_raw"), "year": e.get("year"), "title": e.get("title")},
                )

    return targets


# --------------------------------------------------------------------------- #
# 사람이 읽는 요약 출력
# --------------------------------------------------------------------------- #


def print_summary(results: list[dict[str, Any]]) -> None:
    print("\n=== doi_verify 결과 요약 ===")
    print(f"  총 DOI: {len(results)}")

    by_grade: dict[str, list[dict[str, Any]]] = {g: [] for g in GRADE_ORDER}
    for r in results:
        by_grade.setdefault(r["grade"], []).append(r)

    for grade in GRADE_ORDER:
        items = by_grade.get(grade, [])
        print(f"  {grade}: {len(items)}건")

    for grade in GRADE_ORDER:
        items = by_grade.get(grade, [])
        if not items:
            continue
        print(f"\n--- {grade} ({len(items)}건) ---")
        for r in items:
            print(f"  [{r['doi']}]")
            for reason in r.get("reasons", []):
                print(f"      - {reason}")


def exit_code_for(results: list[dict[str, Any]]) -> int:
    grades = {r["grade"] for r in results}
    if "HALLUCINATED" in grades or "RETRACTED" in grades:
        return 2
    if "MISMATCH" in grades or "ONE_SOURCE_ONLY" in grades or "UNVERIFIED" in grades:
        return 1
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def main() -> int:
    parser = argparse.ArgumentParser(
        description="이미 문서/BibTeX에 들어간 DOI가 실재하는지, 서지정보가 맞는지 "
        "CrossRef+OpenAlex 양쪽으로 교차검증한다 (환각 DOI 게이트, API 키 불필요).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--doi", help="쉼표로 구분된 DOI 목록 (직접 지정)")
    parser.add_argument("--file", help=".md/.txt 등에서 DOI를 정규식으로 자동 추출")
    parser.add_argument("--bibtex", help="BibTeX 파일 — doi + author/year/title 대조까지 수행")
    parser.add_argument(
        "--email",
        default=None,
        help="폴라이트 풀용 연락처 이메일 (없으면 SCITK_CONTACT_EMAIL 환경변수 사용)",
    )
    parser.add_argument("--refresh", action="store_true", help="캐시를 무시하고 강제로 재조회")
    parser.add_argument(
        "--output",
        default="doi_verify_report.json",
        help="결과 JSON 저장 경로 (기본: doi_verify_report.json)",
    )
    parser.add_argument("--cache-dir", default=None, help="ref_cache_manager 캐시 디렉토리 (기본값 권장)")

    args = parser.parse_args()

    if not (args.doi or args.file or args.bibtex):
        print("[ERROR] --doi / --file / --bibtex 중 하나는 필요합니다.", file=sys.stderr)
        parser.print_help()
        return 1

    email = args.email or os.getenv("SCITK_CONTACT_EMAIL") or None
    if not email:
        print(
            "[INFO] --email / SCITK_CONTACT_EMAIL 없음 — 폴라이트 풀 없이 조회합니다 "
            "(속도 제한에 걸릴 수 있음).",
            file=sys.stderr,
        )

    targets = collect_targets(args)
    if not targets:
        print("[ERROR] 검증할 DOI가 없습니다.", file=sys.stderr)
        return 1

    cache = RefCacheManager(cache_dir=args.cache_dir)

    results: list[dict[str, Any]] = []
    for i, t in enumerate(targets, 1):
        doi = t["doi"]
        print(f"[{i}/{len(targets)}] 검증 중: {doi}", file=sys.stderr)
        try:
            record = verify_one(doi, t.get("expected"), cache, email, args.refresh)
        except Exception as e:  # noqa: BLE001 — 개별 DOI 실패가 전체를 죽이지 않게
            record = {
                "doi": doi,
                "grade": "UNVERIFIED",
                "reasons": [f"예외 발생: {type(e).__name__}: {e}"],
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
    print(f"\n[OK] 리포트 저장: {output_path}", file=sys.stderr)

    print_summary(results)

    code = exit_code_for(results)
    if code == 2:
        print("\n[FAIL] HALLUCINATED 또는 RETRACTED 항목이 있습니다 (exit 2).", file=sys.stderr)
    elif code == 1:
        print("\n[WARN] MISMATCH/ONE_SOURCE_ONLY/UNVERIFIED 항목이 있습니다 (exit 1).", file=sys.stderr)
    else:
        print("\n[PASS] 전부 OK (exit 0).", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
