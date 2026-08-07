#!/usr/bin/env python3
"""si_fetch.py / institutional_access.py / ref_fetch.py 수집 관문 회귀 테스트.

실행: python tests/test_si_institutional.py   (exit 0 = 통과)

기존 test_doi_verify.py 와 같은 규약이다:
  1) 네트워크 없이 도는 부분 (항상 실행)
  2) 네트워크가 필요한 부분 — 없으면 SKIP 하되 반드시 "SKIP"이라고 출력한다
     (조용히 통과 금지)
"""
import importlib.util
import json
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, str(SCRIPTS / f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


si_fetch = _load("si_fetch")
institutional_access = _load("institutional_access")

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}  {detail}")


def section(title: str) -> None:
    print(f"\n=== {title} ===")


# --------------------------------------------------------------------------- #
section("기관 링크 생성 (institutional_access)")

reg = institutional_access.InstitutionRegistry.load()
check("config/institutions.json 이 읽힌다", "korea-univ" in reg.available(),
      f"got={reg.available()}")

link = reg.build_link("korea-univ", "https://example.com/article/1")
check("프록시 링크가 대상 URL을 감싼다",
      link is not None and link.url == "https://oca.korea.ac.kr/link.n2s?url=https://example.com/article/1",
      f"got={link.url if link else None}")

check("규정 링크와 한도가 함께 실린다",
      link is not None and link.fair_use_url and link.daily_limits.get("per_publisher") == 30,
      f"got={link.daily_limits if link else None}")

check("안내문에 '자동 다운로드가 아님'이 명시된다",
      link is not None and "공정이용 위반" in link.human_summary())

check("모르는 기관 키 -> None (조용히 엉뚱한 링크를 만들지 않음)",
      reg.build_link("no-such-institution", "https://example.com") is None)

check("대상 URL이 비면 -> None", reg.build_link("korea-univ", "") is None)

# 자리표시자 없는 템플릿은 링크를 만들면 안 된다 (조용히 깨진 링크 방지).
bad = institutional_access.InstitutionRegistry(
    {"institutions": {"broken": {"proxy_url_template": "https://proxy.example/no-placeholder"}}}
)
check("{url} 자리표시자 없는 템플릿 -> None",
      bad.build_link("broken", "https://example.com/x") is None)

# 설정 파일이 없어도 죽지 않아야 한다 (기관 설정은 선택 기능이다).
missing = institutional_access.InstitutionRegistry.load(Path("does-not-exist-12345.json"))
check("설정 파일이 없으면 빈 레지스트리 (예외 아님)", missing.available() == [])


# --------------------------------------------------------------------------- #
section("SI 파일 판별 / 출판사 분기 (si_fetch)")

check("MOESM 파일은 보충자료로 판별",
      si_fetch._looks_supplementary("13321_2015_69_MOESM1_ESM.docx"))
check("_ESM 파일은 보충자료로 판별",
      si_fetch._looks_supplementary("12010_2021_3624_MOESM2_ESM.pdf"))
check("본문 그림(Fig1_HTML.jpg)은 보충자료가 아님",
      not si_fetch._looks_supplementary("13321_2015_69_Fig1_HTML.jpg"))
check("수식 이미지(Article_IEq1.gif)도 보충자료가 아님",
      not si_fetch._looks_supplementary("13321_2015_69_Article_IEq1.gif"))

check("Elsevier 접두사는 차단 목록에 있다", "10.1016" in si_fetch.BLOCKED_PREFIXES)
check("ACS 접두사는 차단 목록에 있다", "10.1021" in si_fetch.BLOCKED_PREFIXES)
check("Springer 접두사도 차단 목록에 있다 (urllib 로는 축소 페이지만 옴)",
      "10.1007" in si_fetch.BLOCKED_PREFIXES)
check("DOI 접두사 추출", si_fetch._prefix("10.1016/j.biortech.2019.122213") == "10.1016")

# 아카이브 내부 경로를 그대로 믿으면 저장 위치가 지정 디렉토리 밖으로 샌다(zip-slip).
# 가짜 아카이브를 만들어 실제 추출 경로를 확인한다.
import io as _io
import zipfile as _zipfile

_buf = _io.BytesIO()
with _zipfile.ZipFile(_buf, "w") as _z:
    _z.writestr("nested/../../escaped_MOESM1_ESM.txt", "payload")
_fake = si_fetch.SIResult(
    doi="10.9999/zipslip-test",
    status="found",
    files=[si_fetch.SIFile(name="nested/../../escaped_MOESM1_ESM.txt", size=7,
                           is_supplementary=True)],
)
_fake._blob = _buf.getvalue()

with tempfile.TemporaryDirectory() as _td:
    _root = Path(_td)
    _got = si_fetch.download_si(_fake, _root, extract=True, si_only=True)
    _paths = [Path(f.extracted_path) for f in _got.files if f.extracted_path]
    _inside = all(_root.resolve() in p.resolve().parents for p in _paths)
    check("아카이브 내부 경로가 저장 디렉토리를 벗어나지 않는다 (zip-slip 방지)",
          bool(_paths) and _inside,
          f"paths={[str(p) for p in _paths]}")


# --------------------------------------------------------------------------- #
section("수집 관문 (ref_fetch.py CLI) — 네트워크 불필요")

with tempfile.TemporaryDirectory() as td:
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "ref_fetch.py"),
         "--doi", "10.1016/j.biortech.2019.122213",
         "--doi-source", "model",
         "--output", str(Path(td) / "r.json")],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    out = proc.stdout + proc.stderr
    check("model 출처 + 제목 미선언 -> 수집 진입 차단 (exit 2, BLOCKED)",
          proc.returncode == 2 and "BLOCKED" in out,
          f"got exit={proc.returncode}, out={out[-200:]!r}")

    # 관문이 조회 전에 막는지 — 네트워크를 탄 흔적이 없어야 한다.
    check("차단은 조회 '전'에 일어난다 (처리 로그가 찍히지 않음)",
          "처리 중:" not in out,
          f"out={out[-200:]!r}")


# --------------------------------------------------------------------------- #
section("네트워크 테스트")


def _network_available() -> bool:
    try:
        socket.create_connection(("www.ebi.ac.uk", 443), timeout=5).close()
        return True
    except OSError:
        return False


if _network_available():
    print("  네트워크 사용 가능 — 실제 API 호출 테스트 실행")

    # PMC 에 있는 OA 논문: 보충자료 3개가 실재한다 (260807 실측).
    res = si_fetch.discover_si("10.1186/s13321-015-0069-3")
    check("[네트워크] PMC 논문 -> status=found",
          res.status == "found", f"got={res.status} note={res.note}")
    check("[네트워크] PMCID 해석됨", res.pmcid == "PMC4456712", f"got={res.pmcid}")
    check("[네트워크] 아카이브에서 보충자료 3개를 골라낸다",
          len(res.supplementary_files) == 3,
          f"got={len(res.supplementary_files)} / 전체 {len(res.files)}")
    check("[네트워크] 본문 그림은 보충자료로 세지 않는다",
          len(res.files) > len(res.supplementary_files),
          f"files={len(res.files)} si={len(res.supplementary_files)}")

    # 실제로 풀었을 때 파일이 그 형식인지 — 크기만으로 판단하지 않는다.
    with tempfile.TemporaryDirectory() as td:
        got = si_fetch.download_si(res, Path(td), extract=True, si_only=True)
        docx = [f for f in got.supplementary_files if f.name.endswith(".docx")]
        ok = False
        if docx and docx[0].extracted_path:
            import zipfile
            p = Path(docx[0].extracted_path)
            ok = p.exists() and zipfile.is_zipfile(p) and \
                "word/document.xml" in zipfile.ZipFile(p).namelist()
        check("[네트워크] 추출된 .docx 가 실제 Word 문서다 (매직바이트+내부구조)",
              ok, f"docx={[f.name for f in docx]}")

    # 차단 출판사: 실패가 아니라 '사람이 할 일'로 안내되어야 한다.
    blocked = si_fetch.discover_si("10.1016/j.enzmictec.2021.109747")
    check("[네트워크] Elsevier -> status=blocked + 브라우저 안내",
          blocked.status == "blocked" and bool(blocked.manual_hint),
          f"got={blocked.status}")
    check("[네트워크] 안내문이 'SI 가 유료라서가 아님'을 밝힌다",
          "유료라서가 아닙니다" in (blocked.manual_hint or ""))
else:
    print("  [SKIP] 네트워크 연결 불가 — Europe PMC 호출 테스트를 건너뜁니다 "
          "(파일 판별/분기 로직은 위에서 이미 검증됨)")


print(f"\n=== 결과: {PASS} 통과 / {FAIL} 실패 ===")
sys.exit(0 if FAIL == 0 else 1)
