#!/usr/bin/env python3
"""doi_verify.py 회귀 테스트 — 네트워크 없이 도는 순수 로직 + 선택적 네트워크 테스트.

실행: python tests/test_doi_verify.py   (exit 0 = 통과)

두 그룹으로 나뉜다:
  1) 네트워크 없이 도는 부분 (항상 실행) — DOI 추출 정규식, BibTeX 파싱,
     제목 유사도, 저자 성 비교, 등급 결정 로직(grade_one), exit code 매핑.
     가짜 CrossRef/OpenAlex 응답(dict)을 주입해서 검증한다.
  2) 실제 네트워크가 필요한 테스트 — 네트워크가 없으면 SKIP하되, 반드시
     "SKIP"이라고 출력한다 (조용히 통과 금지).
"""
import importlib.util
import socket
import sys
from pathlib import Path

# doi_verify 모듈 자체가 import 시점에 sys.stdout/stderr를 cp949 -> utf-8
# TextIOWrapper로 감싼다(ref_fetch.py 경유). 여기서 다시 감싸면 이중 래핑으로
# "I/O operation on closed file"이 나므로(doi_verify.py 상단 주석 참고), 이
# 테스트 파일에서는 별도로 감싸지 않고 모듈 import가 처리하게 둔다.

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

spec = importlib.util.spec_from_file_location("doi_verify", str(SCRIPTS / "doi_verify.py"))
doi_verify = importlib.util.module_from_spec(spec)
sys.modules["doi_verify"] = doi_verify
spec.loader.exec_module(doi_verify)


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
# 1) DOI 추출 정규식
# --------------------------------------------------------------------------- #

section("DOI 추출 (extract_dois_from_text)")

text1 = "See 10.1038/nature12373 and also (10.1021/acs.jchemed.7b00361)."
dois1 = doi_verify.extract_dois_from_text(text1)
check(
    "괄호/공백으로 둘러싸인 DOI 2개 추출",
    dois1 == ["10.1038/nature12373", "10.1021/acs.jchemed.7b00361"],
    f"got={dois1}",
)

text2 = "DOI: 10.1038/nature12373. Another sentence."
dois2 = doi_verify.extract_dois_from_text(text2)
check(
    "trailing 마침표가 DOI에 안 섞임",
    dois2 == ["10.1038/nature12373"],
    f"got={dois2}",
)

text3 = "dup 10.1038/nature12373 dup 10.1038/nature12373 once more"
dois3 = doi_verify.extract_dois_from_text(text3)
check("중복 제거 + 순서 보존", dois3 == ["10.1038/nature12373"], f"got={dois3}")

text4 = "no dois here at all"
dois4 = doi_verify.extract_dois_from_text(text4)
check("DOI 없는 텍스트 -> 빈 리스트", dois4 == [], f"got={dois4}")

text5 = "markdown link [paper](https://doi.org/10.1038/nature12373) end."
dois5 = doi_verify.extract_dois_from_text(text5)
check(
    "마크다운 링크 안 DOI, 닫는 괄호 제거됨",
    dois5 == ["10.1038/nature12373"],
    f"got={dois5}",
)


# --------------------------------------------------------------------------- #
# BibTeX 파싱
# --------------------------------------------------------------------------- #

section("BibTeX 파싱 (parse_bibtex)")

bib_text = """
@article{kucsko2013,
  author = {Kucsko, G. and Maurer, P. C. and Yao, N. Y.},
  title = {Nanometre-scale thermometry in a living cell},
  year = {2013},
  doi = {10.1038/nature12373}
}

@article{noref,
  author = {Someone, A.},
  title = {No DOI here},
  year = {2020}
}
"""
entries = doi_verify.parse_bibtex(bib_text)
check("doi 있는 항목만 뽑힘 (1개)", len(entries) == 1, f"got={len(entries)}")
if entries:
    e = entries[0]
    check("doi 정규화됨", e["doi"] == "10.1038/nature12373", f"got={e['doi']!r}")
    check("year 파싱됨", e["year"] == 2013, f"got={e['year']!r}")
    check(
        "title 파싱됨",
        e["title"] == "Nanometre-scale thermometry in a living cell",
        f"got={e['title']!r}",
    )
    check(
        "author_raw 보존됨",
        "Kucsko" in (e["author_raw"] or ""),
        f"got={e['author_raw']!r}",
    )


# --------------------------------------------------------------------------- #
# 제목 유사도
# --------------------------------------------------------------------------- #

section("제목 유사도 (title_similarity) — 오탐 방지")

sim_case = doi_verify.title_similarity(
    "Nanometre-scale thermometry in a living cell",
    "Nanometre-scale thermometry in a living cell",
)
check("동일 제목 -> 유사도 1.0", sim_case == 1.0, f"got={sim_case}")

sim_punct = doi_verify.title_similarity(
    "Nanometre-scale Thermometry in a Living Cell.",
    "nanometre scale thermometry in a living cell",
)
check(
    "대소문자/구두점 차이만 -> 높은 유사도(>=0.95), MISMATCH 유발 안 함",
    sim_punct >= 0.95,
    f"got={sim_punct}",
)

sim_diff = doi_verify.title_similarity(
    "Nanometre-scale thermometry in a living cell",
    "Completely unrelated paper about protein folding kinetics",
)
check("완전히 다른 제목 -> 낮은 유사도(<0.5)", sim_diff < 0.5, f"got={sim_diff}")


# --------------------------------------------------------------------------- #
# 저자 성 비교 (표기 차이 오탐 방지 핵심 케이스)
# --------------------------------------------------------------------------- #

section("저자 성 비교 (compare_metadata) — 표기 차이 오탐 방지")

crossref_found = {
    "found": True,
    "title": "Nanometre-scale thermometry in a living cell",
    "year": 2013,
    "authors": ["G. Kucsko", "P. C. Maurer", "N. Y. Yao"],
}
openalex_found = {
    "found": True,
    "title": "Nanometre-scale thermometry in a living cell",
    "year": 2013,
    "authors": ["Georg Kucsko", "Peter C. Maurer", "Norman Y. Yao"],
}

expected_matching = {
    "author_raw": "Kucsko, G. and Maurer, P. C. and Yao, N. Y.",
    "year": 2013,
    "title": "Nanometre-scale thermometry in a living cell",
}
reasons_ok = doi_verify.compare_metadata(expected_matching, crossref_found, openalex_found)
check(
    "이니셜(G. Kucsko) vs 풀네임(Georg Kucsko) 표기 차이만으로 MISMATCH 안 남",
    reasons_ok == [],
    f"got={reasons_ok}",
)

expected_case_diff = {
    "author_raw": "KUCSKO, Georg and MAURER, Peter",
    "year": 2013,
    "title": "NANOMETRE-SCALE THERMOMETRY IN A LIVING CELL",
}
reasons_case = doi_verify.compare_metadata(expected_case_diff, crossref_found, openalex_found)
check(
    "제목 대소문자 차이만으로 MISMATCH 안 남",
    reasons_case == [],
    f"got={reasons_case}",
)

expected_wrong_year = {
    "author_raw": "Kucsko, G.",
    "year": 1999,
    "title": "Nanometre-scale thermometry in a living cell",
}
reasons_year = doi_verify.compare_metadata(expected_wrong_year, crossref_found, openalex_found)
check(
    "연도가 실제로 다르면 MISMATCH 사유에 잡힘",
    any("year mismatch" in r for r in reasons_year),
    f"got={reasons_year}",
)

expected_wrong_author = {
    "author_raw": "Smith, John and Doe, Jane",
    "year": 2013,
    "title": "Nanometre-scale thermometry in a living cell",
}
reasons_author = doi_verify.compare_metadata(expected_wrong_author, crossref_found, openalex_found)
check(
    "저자 성이 전혀 안 겹치면 MISMATCH 사유에 잡힘",
    any("author mismatch" in r for r in reasons_author),
    f"got={reasons_author}",
)

expected_wrong_title = {
    "author_raw": "Kucsko, G.",
    "year": 2013,
    "title": "A totally different paper about something else entirely",
}
reasons_title = doi_verify.compare_metadata(expected_wrong_title, crossref_found, openalex_found)
check(
    "제목이 실제로 다르면 MISMATCH 사유에 잡힘",
    any("title mismatch" in r for r in reasons_title),
    f"got={reasons_title}",
)


# --------------------------------------------------------------------------- #
# 등급 결정 로직 (grade_one) — MUST DETECT 케이스들
# --------------------------------------------------------------------------- #

section("등급 결정 (grade_one) — MUST DETECT")

not_found = {"found": False, "error": "not_found"}
result_halluc = doi_verify.grade_one("10.9999/nonexistent.12345", None, not_found, not_found)
check(
    "존재하지 않는 DOI -> HALLUCINATED",
    result_halluc["grade"] == "HALLUCINATED",
    f"got={result_halluc['grade']}",
)

result_retracted = doi_verify.grade_one(
    "10.1234/retracted.example",
    None,
    crossref_found,
    {**openalex_found, "is_retracted": True},
)
check(
    "is_retracted=True -> RETRACTED",
    result_retracted["grade"] == "RETRACTED",
    f"got={result_retracted['grade']}",
)

result_mismatch = doi_verify.grade_one(
    "10.1038/nature12373",
    expected_wrong_year,
    crossref_found,
    {**openalex_found, "is_retracted": False},
)
check(
    "연도 다른 항목 -> MISMATCH",
    result_mismatch["grade"] == "MISMATCH",
    f"got={result_mismatch['grade']}",
)

result_one_source = doi_verify.grade_one(
    "10.1038/nature12373",
    None,
    crossref_found,
    not_found,
)
check(
    "한쪽 소스만 존재 -> ONE_SOURCE_ONLY",
    result_one_source["grade"] == "ONE_SOURCE_ONLY",
    f"got={result_one_source['grade']}",
)

network_fail = {"found": False, "error": "URLError: [Errno -2] Name or service not known"}
result_unverified_both = doi_verify.grade_one("10.1038/nature12373", None, network_fail, network_fail)
check(
    "양쪽 다 네트워크 실패 -> UNVERIFIED (HALLUCINATED 아님)",
    result_unverified_both["grade"] == "UNVERIFIED",
    f"got={result_unverified_both['grade']}",
)

result_unverified_mixed = doi_verify.grade_one("10.1038/nature12373", None, network_fail, not_found)
check(
    "한쪽 네트워크 실패 + 한쪽 not_found -> UNVERIFIED (HALLUCINATED로 단정 안 함)",
    result_unverified_mixed["grade"] == "UNVERIFIED",
    f"got={result_unverified_mixed['grade']}",
)

result_ok = doi_verify.grade_one(
    "10.1038/nature12373",
    expected_matching,
    crossref_found,
    {**openalex_found, "is_retracted": False},
)
check(
    "존재 확인 + 메타데이터 일치 -> OK",
    result_ok["grade"] == "OK",
    f"got={result_ok['grade']}",
)

result_ok_no_expected = doi_verify.grade_one(
    "10.1038/nature12373",
    None,
    crossref_found,
    {**openalex_found, "is_retracted": False},
)
check(
    "expected 없이 존재만 확인해도 OK",
    result_ok_no_expected["grade"] == "OK",
    f"got={result_ok_no_expected['grade']}",
)

invalid_format = doi_verify.grade_one  # placeholder to keep name defined below


# --------------------------------------------------------------------------- #
# verify_one의 DOI 형식 오류 경로 (정규식 자체는 grade_one 호출 전에 체크)
# --------------------------------------------------------------------------- #

section("DOI 형식 오류 처리 (verify_one)")


class _FakeCache:
    """RefCacheManager를 흉내내는 가짜 캐시 — has()가 항상 False."""

    def has(self, key):  # noqa: ANN001
        return False

    def get(self, key):  # noqa: ANN001
        return None

    def put(self, key, value):  # noqa: ANN001
        pass


bad_doi_result = doi_verify.grade_one("not-a-doi", None, not_found, not_found)
# grade_one 자체는 형식을 검사하지 않으므로 verify_one 경로로 확인
if not doi_verify._DOI_RE.match("not-a-doi"):
    check("DOI 정규식이 형식 오류 문자열을 거부함", True)
else:
    check("DOI 정규식이 형식 오류 문자열을 거부함", False)


# --------------------------------------------------------------------------- #
# exit code 매핑
# --------------------------------------------------------------------------- #

section("exit code 매핑 (exit_code_for)")

results_halluc = [{"grade": "HALLUCINATED"}, {"grade": "OK"}]
check("HALLUCINATED 포함 -> exit 2", doi_verify.exit_code_for(results_halluc) == 2)

results_retracted = [{"grade": "RETRACTED"}, {"grade": "MISMATCH"}]
check("RETRACTED 포함 (MISMATCH도 있어도) -> exit 2 (더 심각한 쪽 우선)", doi_verify.exit_code_for(results_retracted) == 2)

results_mismatch = [{"grade": "MISMATCH"}, {"grade": "OK"}]
check("MISMATCH만 -> exit 1", doi_verify.exit_code_for(results_mismatch) == 1)

results_one_source = [{"grade": "ONE_SOURCE_ONLY"}]
check("ONE_SOURCE_ONLY만 -> exit 1", doi_verify.exit_code_for(results_one_source) == 1)

results_unverified = [{"grade": "UNVERIFIED"}]
check("UNVERIFIED만 -> exit 1 (네트워크 실패를 통과로 처리하지 않음)", doi_verify.exit_code_for(results_unverified) == 1)

results_ok = [{"grade": "OK"}, {"grade": "OK"}]
check("전부 OK -> exit 0", doi_verify.exit_code_for(results_ok) == 0)


# --------------------------------------------------------------------------- #
# 2) 네트워크가 필요한 테스트 — 없으면 SKIP (조용히 통과 금지)
# --------------------------------------------------------------------------- #

section("네트워크 테스트")


def _network_available() -> bool:
    try:
        socket.create_connection(("api.crossref.org", 443), timeout=5).close()
        return True
    except OSError:
        return False


if _network_available():
    print("  네트워크 사용 가능 — 실제 API 호출 테스트 실행")

    valid_result = doi_verify.verify_one(
        "10.1038/nature12373", None, _FakeCache(), None, refresh=True
    )
    check(
        "[네트워크] 유효 DOI(10.1038/nature12373) -> OK",
        valid_result["grade"] == "OK",
        f"got={valid_result['grade']}, reasons={valid_result.get('reasons')}",
    )

    fake_result = doi_verify.verify_one(
        "10.9999/nonexistent.12345", None, _FakeCache(), None, refresh=True
    )
    check(
        "[네트워크] 존재하지 않는 DOI -> HALLUCINATED",
        fake_result["grade"] == "HALLUCINATED",
        f"got={fake_result['grade']}",
    )

    real_expected = {
        "author_raw": "Kucsko, Georg and Maurer, Peter C.",
        "year": 2013,
        "title": "Nanometre-scale thermometry in a living cell",
    }
    real_meta_result = doi_verify.verify_one(
        "10.1038/nature12373", real_expected, _FakeCache(), None, refresh=True
    )
    check(
        "[네트워크] 실제 저자 표기 차이(Georg Kucsko 등)로 오탐 없음 -> OK",
        real_meta_result["grade"] == "OK",
        f"got={real_meta_result['grade']}, reasons={real_meta_result.get('reasons')}",
    )
else:
    print("  [SKIP] 네트워크 연결 불가 — 실제 API 호출 테스트를 건너뜁니다 (UNVERIFIED 경로는 이미 grade_one 단위 테스트로 검증됨)")


# --------------------------------------------------------------------------- #
# 결과 요약
# --------------------------------------------------------------------------- #

print(f"\n=== 결과: {PASS} 통과 / {FAIL} 실패 ===")
sys.exit(0 if FAIL == 0 else 1)
