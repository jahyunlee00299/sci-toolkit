#!/usr/bin/env python3
"""논문의 보충자료(SI / Supporting Information)를 공개 경로로만 수집한다.

본문(ref_fetch.py)과 분리한 이유: 본문과 SI는 **접근 가능성이 다르다.**
구독 저널이라도 SI는 페이월 밖에 열려 있는 경우가 있다. 실측(260807),
같은 논문 10.1007/s12010-021-03624-7 (구독 저널)에서:

    SI  media.springernature.com/.../MOESM1_ESM.docx  -> HTTP 200 (인증 불필요)
    본문 link.springer.com/content/pdf/....pdf         -> 303 -> 302 -> 302 (로그인)

그래서 "본문은 못 받아도 SI는 받을 수 있다"가 성립한다.

경로 선택도 실측으로 정했다. 처음에는 출판사 landing page 를 긁으려 했지만
표준 라이브러리로는 되지 않는다:

    출판사 landing page 를 urllib 로 요청     -> Springer 3,036 B 축소 페이지
      (같은 URL 을 curl 로 받으면 372,615 B. UA 3종을 바꿔도 urllib 은 동일 —
       HTTP/2·TLS 지문 수준의 차이라 헤더로는 넘을 수 없다)
    PMC 파일 직링크 (/articles/instance/.../bin/...)  -> 1,817 B
      "Preparing to download ..." JS 인터스티셜. URL 은 맞지만 JS 가 필요하다.

두 경로 모두 브라우저가 있어야 하므로 버렸다. 실제로 되는 것은 **Europe PMC
REST API** 하나다 — urllib 만으로 4.28 MB 아카이브를 그대로 돌려준다:

    GET /europepmc/webservices/rest/{PMCID}/supplementaryFiles  -> application/zip

따라서 이 모듈의 자동 수집 범위는 **PMC 에 있는 논문**이다. 그 밖은 링크만
안내하고 끝낸다 — 우회하지 않는다. 사람이 브라우저로 열면 대개 그냥 받아진다.

규정: 개방된 SI 수집은 대학 도서관 공정이용 규정의 대상이 아니다. 그 규정은
구독 전자자원의 '원문'을 기계적 수단으로 받는 행위를 금지하며, 개방 SI 는
구독 자원이 아니고 프록시를 경유하지도 않는다. 본문 쪽 처리는
institutional_access.py 를 볼 것.

사용:
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

# Europe PMC 아카이브에는 본문 그림(Fig1_HTML.jpg 등)도 함께 들어온다.
# 저자가 올린 보충자료는 관례적으로 파일명에 MOESM / ESM / suppl 이 붙는다.
_SI_NAME_HINTS = ("moesm", "_esm", "suppl", "supplementary", "media")

# landing page 자동 조회가 막힌 출판사. 우회하지 않고 사람에게 넘긴다.
# (SI 가 유료라서가 아니라 봇 차단·JS 때문이다 — 브라우저로는 그냥 받아진다.)
BLOCKED_PREFIXES = {
    "10.1016": ("Elsevier", "linkinghub 가 JS 셸만 반환"),
    "10.1021": ("ACS", "landing page 403"),
    "10.1039": ("RSC", "landing page 403"),
    "10.1002": ("Wiley", "cookieAbsent 리다이렉트"),
    "10.1007": ("Springer", "urllib 로는 축소 페이지만 수신 (curl/브라우저는 정상)"),
    "10.1038": ("Springer Nature", "urllib 로는 축소 페이지만 수신 (curl/브라우저는 정상)"),
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


def doi_to_pmcid(doi: str, email: Optional[str] = None) -> Optional[str]:
    """NCBI ID converter 로 DOI -> PMCID. 없으면 None."""
    url = f"{_NCBI_IDCONV}?ids={urllib.parse.quote(doi)}&format=json"
    data, err = _http_get_json(url, email)
    if err or not data:
        return None
    for rec in data.get("records") or []:
        if rec.get("pmcid"):
            return rec["pmcid"]
    return None


def _fetch_archive(pmcid: str, email: Optional[str], timeout: int = 120) -> tuple[Optional[bytes], Optional[str]]:
    """Europe PMC supplementaryFiles 아카이브를 통째로 받는다."""
    url = _EPMC_SUPPL.format(pmcid=pmcid)
    req = urllib.request.Request(url, headers={"User-Agent": _build_user_agent(email)})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read(), None
    except urllib.error.HTTPError as e:  # type: ignore[attr-defined]
        # 보충자료가 없는 논문은 404 를 준다 — 오류가 아니라 "없음"이다.
        return None, ("not_found" if e.code == 404 else f"HTTP {e.code}")
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def discover_si(doi: str, email: Optional[str] = None) -> SIResult:
    """DOI 하나의 SI 를 찾는다. PMC 에 있으면 목록까지, 없으면 안내로 끝낸다.

    아카이브를 받아야 내용 목록을 알 수 있으므로 discover 단계에서 이미
    내려받는다. 저장 여부는 download_si() 가 정한다.
    """
    doi = normalize_doi(doi)
    pmcid = doi_to_pmcid(doi, email)

    if not pmcid:
        pfx = _prefix(doi)
        if pfx in BLOCKED_PREFIXES:
            name, why = BLOCKED_PREFIXES[pfx]
            return SIResult(
                doi=doi,
                status="blocked",
                note=f"PMC 에 없음. {name}: {why}",
                manual_hint=(
                    f"{name} 는 스크립트 조회를 막습니다(SI 가 유료라서가 아닙니다). "
                    f"브라우저에서 https://doi.org/{doi} 를 열면 보충자료를 그대로 받을 수 있습니다."
                ),
            )
        return SIResult(
            doi=doi,
            status="none",
            note="PMC 에 해당 논문이 없어 자동 수집 경로가 없음",
            manual_hint=f"브라우저에서 https://doi.org/{doi} 를 열어 확인하세요.",
        )

    url = _EPMC_SUPPL.format(pmcid=pmcid)
    blob, err = _fetch_archive(pmcid, email)
    if err == "not_found":
        return SIResult(doi=doi, status="none", pmcid=pmcid, archive_url=url,
                        note=f"{pmcid} 에 보충자료 없음")
    if err or not blob:
        return SIResult(doi=doi, status="error", pmcid=pmcid, archive_url=url,
                        note=f"Europe PMC 조회 실패: {err}")

    buf = io.BytesIO(blob)
    if not zipfile.is_zipfile(buf):
        return SIResult(doi=doi, status="error", pmcid=pmcid, archive_url=url,
                        archive_bytes=len(blob),
                        note="응답이 유효한 아카이브가 아님 (형식 변경 의심)")

    zf = zipfile.ZipFile(buf)
    files = [
        SIFile(name=n, size=zf.getinfo(n).file_size, is_supplementary=_looks_supplementary(n))
        for n in zf.namelist()
    ]
    res = SIResult(doi=doi, status="found", pmcid=pmcid, archive_url=url,
                   archive_bytes=len(blob), files=files)
    res._blob = blob  # type: ignore[attr-defined]  # download 단계에서 재사용 (재요청 방지)
    return res


def download_si(
    result: SIResult,
    out_dir: Path,
    extract: bool = False,
    si_only: bool = True,
) -> SIResult:
    """찾은 SI 를 저장한다. 기본은 아카이브 그대로, --extract 시 파일별로 푼다."""
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
        # 아카이브 내부 경로를 그대로 믿지 않는다 (zip-slip 방지) — 파일명만 쓴다.
        safe_name = Path(f.name).name
        if not safe_name:
            continue
        dest = target_dir / safe_name
        dest.write_bytes(zf.read(f.name))
        f.extracted_path = str(dest)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(
        description="논문 보충자료(SI)를 공개 경로(Europe PMC)로만 수집한다. 페이월 우회 없음.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--doi", required=True, help="DOI (쉼표로 여러 개)")
    ap.add_argument("--download", action="store_true", help="아카이브를 저장")
    ap.add_argument("--extract", action="store_true", help="아카이브를 파일별로 풀기")
    ap.add_argument("--si-only", action="store_true", default=True,
                    help="추출 시 보충자료만 (기본). --all-files 로 해제")
    ap.add_argument("--all-files", action="store_true",
                    help="본문 그림까지 전부 추출")
    ap.add_argument("-o", "--out-dir", default="./si", help="저장 디렉토리 (기본 ./si)")
    ap.add_argument("--email", default=None, help="폴라이트 풀용 연락처 이메일")
    ap.add_argument("--json", default=None, help="결과를 이 경로에 JSON 으로 저장")
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
            print(f"  아카이브 {res.archive_bytes:,} bytes / 파일 {len(res.files)}개 "
                  f"(보충자료로 판별 {len(si)}개)")
            for f in si[:10]:
                line = f"    - {f.name}  ({f.size:,} bytes)"
                if f.extracted_path:
                    line += f"  -> {f.extracted_path}"
                print(line)
            if res.archive_path:
                print(f"  저장: {res.archive_path}")
        if res.manual_hint:
            print(f"  → {res.manual_hint}")

    if args.json:
        Path(args.json).write_text(
            json.dumps([r.to_dict() for r in results], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n[OK] JSON 저장: {args.json}")

    # blocked 는 실패가 아니라 '사람이 할 일'이므로 0 을 준다. 진짜 오류만 1.
    if any(r.status == "error" for r in results):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
