# -*- coding: utf-8 -*-
"""
endnote_biblio_check.py — EndNote bibliography integrity checker for Word docx.

재발 방지 검증 장치 (a real incident). Non-destructive: zipfile로
word/document.xml만 읽음 (docx를 Word로 열지 않음, EndNote 필드 미접촉).

잡아내는 오류 7종:
  1. reference_type 오류  — EndNote record가 Journal Article(17) 아닌 Bill/Generic
                            (INSERT 시 reference_type 미지정 → Bill 기본값 → 이탤릭/볼드 소실)
  2. INVALID CITATION     — 본문 렌더(w:t, 복구불가) vs 필드(instrText, Update로 해소) 구분
  3. 저널명 이탤릭 누락    — 참고문헌 문단에 이탤릭 run 없음 (RSC는 저널명 전부 이탤릭)
  4. 저자 누락 의심        — 참고문헌이 "성1개, 저널"처럼 이니셜/공저자 없이 시작
  5. &amp; 엔티티 깨짐     — 이중/미해제 HTML 엔티티
  6. 저널명 비CASSI 축약   — 마침표 없는 PubMed식 축약 or 미축약 풀네임 잔재 (경고)
  7. 참고문헌 목록 결측    — 본문 위첨자 인용번호 최댓값이 참고문헌 목록 항목수보다 큼
                            (실측 사례: 본문 인용 번호가 목록 최대 번호를 초과)

사용:
  python endnote_biblio_check.py <docx>              # 요약 + 오류목록
  python endnote_biblio_check.py <docx> --json       # JSON 출력
  python endnote_biblio_check.py <docx> --strict      # 오류 있으면 exit 1 (CI/gate용)

reference_type 코드 판정은 fldData/instrText blob 안의 <ref-type name="..."> 로.
"""
import sys, zipfile, re, base64, zlib, io, json, argparse

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def _read_document_xml(path):
    with zipfile.ZipFile(path) as z:
        return z.read("word/document.xml").decode("utf-8", "replace")


def _decode_blobs(xml):
    """fldData(base64) + instrText(escaped) 를 모두 디코딩해 EndNote record XML 텍스트로."""
    texts = []
    for m in re.finditer(r"<w:fldData[^>]*>(.*?)</w:fldData>", xml, re.S):
        b = re.sub(r"\s+", "", m.group(1))
        try:
            raw = base64.b64decode(b)
        except Exception:
            continue
        for enc in ("utf-8", "utf-16-le", "latin-1"):
            try:
                texts.append(raw.decode(enc, "replace"))
                break
            except Exception:
                pass
        for wbits in (15, -15, 31):
            try:
                texts.append(zlib.decompress(raw, wbits).decode("utf-8", "replace"))
            except Exception:
                pass
    # instrText 인라인 (unescape). &quot;/&apos; 도 반드시 (일부 EndNote 필드는
    # ref-type name 속성이 &quot;로 이스케이프돼 있어, 누락 시 정규식 미매치→오류 은폐).
    # &amp; 는 항상 마지막에 (이중 unescape 방지).
    texts.append(xml.replace("&lt;", "<").replace("&gt;", ">")
                    .replace("&quot;", '"').replace("&apos;", "'").replace("&amp;", "&"))
    return "\n".join(texts)


def check_reference_types(xml):
    """EndNote record 의 ref-type 분포. Journal Article(17) 아닌 것 = 잠재 오류."""
    blob = _decode_blobs(xml)
    types = re.findall(r'<ref-type name="([^"]+)"', blob)
    from collections import Counter
    dist = Counter(types)
    # Journal Article / Book Section / Report / Web Page / Conference Paper = 정상 타입군
    ok = {"Journal Article", "Book Section", "Report", "Web Page", "Conference Paper"}
    # Bill / Generic 등은 대개 INSERT 시 미지정으로 새어나온 오류
    suspicious = {t: n for t, n in dist.items() if t not in ok}
    return dict(distribution=dict(dist), suspicious=suspicious)


def check_invalid_citations(xml):
    """INVALID CITATION 을 렌더(w:t, 복구불가) vs 필드(instrText, Update로 해소) 구분."""
    rendered = [t for t in re.findall(r"<w:t[^>]*>(.*?)</w:t>", xml, re.S)
                if "INVALID CITATION" in t]
    field = [t for t in re.findall(r"<w:instrText[^>]*>(.*?)</w:instrText>", xml, re.S)
             if "INVALID CITATION" in t]
    return dict(rendered=len(rendered), field=len(field),
                rendered_samples=[re.sub(r"\s+", " ", t).strip()[:70] for t in rendered[:12]])


def _reflist_paragraphs(xml):
    """번호로 시작하고 연도(19xx/20xx) 포함하는 문단 = 참고문헌 항목."""
    out = []
    for p in re.findall(r"<w:p\b.*?</w:p>", xml, re.S):
        txt = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p))
        m = re.match(r"\s*(\d+)\.", txt)
        if not m:
            continue
        num = int(m.group(1))
        if num < 1 or num > 400:
            continue
        if not re.search(r", (19|20)\d{2},", txt):
            continue
        out.append((num, txt.strip(), p))
    return out


def check_italic_missing(xml):
    """참고문헌 문단에 이탤릭 run 없음 = 저널명 이탤릭 누락."""
    missing = []
    for num, txt, p in _reflist_paragraphs(xml):
        if not re.search(r"<w:i\b", p):
            missing.append((num, txt[:80]))
    return missing


def check_author_omission(xml):
    """참고문헌이 '성1개, 저널명'처럼 이니셜/공저자 없이 시작 = 저자 누락 의심.
    정상: 'A. B. Surname, ...' 또는 'A. B. Surname and C. D. Surname, ...'
    의심: 숫자.공백 뒤 바로 '대문자단어, 대문자시작저널' (이니셜 'X.' 없음)."""
    suspects = []
    for num, txt, p in _reflist_paragraphs(xml):
        body = re.sub(r"^\s*\d+\.\s*", "", txt)
        # 첫 토큰이 이니셜(예 'A.')로 시작하지 않고, 바로 'Surname,' 형태면 의심
        # 정상 저자블록은 'X. ' (이니셜+점+공백) 패턴을 포함
        first_chunk = body.split(",")[0]
        has_initial = bool(re.search(r"\b[A-Z]\.\s", body[:40]))
        # 'Surname, Journal' — 콤마 앞이 한 단어(이니셜 없음)
        if not has_initial and re.match(r"^[A-Z][a-zA-Z\-]+,", body):
            suspects.append((num, txt[:80]))
    return suspects


def check_entity_breakage(xml):
    """이중 이스케이프된 & 가 렌더 텍스트에 노출되는 것만 잡는다 (260715 fix).

    document.xml 의 <w:t> 안에서 `&amp;` 는 화면에 `&` 로 정상 렌더되는 올바른 단일
    이스케이프다 (오탐 금지 — 260714 스킬 버전이 이걸 오탐해 정상 CRediT/펀딩 문구를
    깨진 것으로 표시했다). 화면에 문자 그대로 `&amp;` 가 보이려면 소스에 `&amp;amp;`
    (이중) 가 있어야 한다. 즉 <w:t> 안에서 `&amp;amp;` (raw 로는 `&amp;amp;amp;`) 만 진짜 버그.
    """
    hits = []
    for t in re.findall(r"<w:t[^>]*>([^<]*)</w:t>", xml):
        # raw XML 조각 t 에서 `&amp;amp;` = 디코드 1단계 후 `&amp;` = 화면에 `&amp;` 노출
        if "&amp;amp;" in t:
            hits.append(t.strip()[:80])
    return hits


def check_missing_reflist_entries(xml):
    """본문/표 위첨자 인용번호 최댓값 vs 참고문헌 목록 항목수 비교 (260715 추가).

    RSC/ACS 등 numeric-superscript 스타일은 포맷된 인용이 <w:vertAlign
    w:val="superscript"/> 런의 <w:t> 안에 숫자(콤마/en-dash 범위 포함, 예 "15,16" "18-20")로
    렌더된다. 본문에서 인용된 최댓값이 참고문헌 목록의 실제 항목수보다 크면 =
    참고문헌이 결측(목록에 없는 번호가 인용됨). 실측 사례에서 본문 인용 번호가
    있는데 목록이 1~14뿐이던 사례로 추가 — reflist 항목수만 세는 기존 체크(#1 reference_type
    등)로는 이 결측을 못 잡는다(목록 자체는 내부적으로 일관돼 보이므로).

    보수적 파싱: 위첨자 run 텍스트가 숫자/쉼표/공백/하이픈/en-dash로만 구성된 것만 인용번호로
    취급(각주 기호 a/b/c, 오타 등은 제외). 범위(18-20, 18–20)는 양끝 다 포함.
    """
    max_cited = 0
    cited_numbers = set()
    for r in re.findall(r"<w:r\b.*?</w:r>", xml, re.S):
        if not re.search(r'<w:vertAlign\s+w:val="superscript"\s*/>', r):
            continue
        txt = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", r)).strip()
        if not txt or not re.fullmatch(r"[\d,\s\-–—]+", txt):
            continue
        for part in re.split(r"[,\s]+", txt):
            if not part:
                continue
            m = re.fullmatch(r"(\d+)[\-–—](\d+)", part)
            if m:
                lo, hi = int(m.group(1)), int(m.group(2))
                if hi >= lo and hi - lo < 200:  # sanity guard against mis-parsed ranges
                    cited_numbers.update(range(lo, hi + 1))
                    max_cited = max(max_cited, hi)
            elif part.isdigit():
                n = int(part)
                cited_numbers.add(n)
                max_cited = max(max_cited, n)

    reflist_numbers = {num for num, _txt, _p in _reflist_paragraphs(xml)}
    max_reflist = max(reflist_numbers) if reflist_numbers else 0
    missing = sorted(n for n in cited_numbers if reflist_numbers and n > max_reflist)
    return dict(
        max_cited=max_cited,
        max_reflist=max_reflist,
        n_reflist_entries=len(reflist_numbers),
        missing_numbers=missing,
    )


def check_non_cassi_journal(xml):
    """참고문헌 이탤릭 run(저널명)이 마침표 없는 축약 or 풀네임 잔재 = 비CASSI 경고.
    휴리스틱: 이탤릭 저널명이 여러 단어인데 마침표가 하나도 없으면 PubMed식 무마침표 의심."""
    warns = []
    for num, txt, p in _reflist_paragraphs(xml):
        jnames = []
        for r in re.findall(r"<w:r\b.*?</w:r>", p, re.S):
            if re.search(r"<w:i\b", r):
                rt = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", r))
                if rt.strip():
                    jnames.append(rt.strip())
        j = " ".join(jnames).strip()
        if not j:
            continue
        words = j.split()
        # 2단어 이상인데 마침표 0개 = 무마침표 축약(PubMed) 의심
        # 단, 단일 고유명(Nature/Science/Tetrahedron/ChemCatChem)은 제외
        if len(words) >= 2 and "." not in j and ":" not in j:
            warns.append((num, j[:60]))
    return warns


def run_all(path):
    xml = _read_document_xml(path)
    rt = check_reference_types(xml)
    inv = check_invalid_citations(xml)
    ital = check_italic_missing(xml)
    auth = check_author_omission(xml)
    ent = check_entity_breakage(xml)
    cassi = check_non_cassi_journal(xml)
    missing_refs = check_missing_reflist_entries(xml)
    n_errors = (len(rt["suspicious"]) > 0) + (inv["rendered"] > 0) + (len(ital) > 0) \
        + (len(auth) > 0) + (len(ent) > 0) + (len(missing_refs["missing_numbers"]) > 0)
    return dict(
        file=path,
        reference_types=rt,
        invalid_citations=inv,
        italic_missing=ital,
        author_omission_suspects=auth,
        entity_breakage=ent,
        non_cassi_journal_warnings=cassi,
        missing_reflist_entries=missing_refs,
        error_categories=n_errors,
    )


def _fmt(r):
    L = []
    L.append(f"# EndNote Bibliography Check — {r['file'].split(chr(92))[-1]}")
    rt = r["reference_types"]
    L.append(f"\n## 1. Reference Type 분포")
    for t, n in sorted(rt["distribution"].items(), key=lambda x: -x[1]):
        flag = "  ⚠️ 오류(Journal Article로 변경 필요)" if t in rt["suspicious"] else ""
        L.append(f"   {t}: {n}{flag}")
    if rt["suspicious"]:
        L.append(f"   🔴 의심 타입 {sum(rt['suspicious'].values())}건 — EndNote Find&Replace로 Journal Article 일괄변경")

    inv = r["invalid_citations"]
    L.append(f"\n## 2. INVALID CITATION")
    L.append(f"   렌더(w:t, 복구불가): {inv['rendered']}  |  필드(Update로 해소): {inv['field']}")
    for s in inv["rendered_samples"]:
        L.append(f"     - {s}")

    L.append(f"\n## 3. 저널명 이탤릭 누락: {len(r['italic_missing'])}건")
    for num, t in r["italic_missing"][:40]:
        L.append(f"   [{num}] {t}")

    L.append(f"\n## 4. 저자 누락 의심: {len(r['author_omission_suspects'])}건")
    for num, t in r["author_omission_suspects"]:
        L.append(f"   [{num}] {t}")

    L.append(f"\n## 5. &amp; 엔티티 깨짐: {len(r['entity_breakage'])}건")
    for t in r["entity_breakage"][:10]:
        L.append(f"   - {t}")

    L.append(f"\n## 6. 비CASSI 저널명 경고(무마침표 축약 의심): {len(r['non_cassi_journal_warnings'])}건")
    for num, j in r["non_cassi_journal_warnings"][:40]:
        L.append(f"   [{num}] {j}")

    mr = r["missing_reflist_entries"]
    L.append(f"\n## 7. 참고문헌 목록 결측 (본문 인용번호 최댓값 vs 목록 항목수)")
    L.append(f"   본문 최대 인용번호: {mr['max_cited']}  |  목록 최대 번호: {mr['max_reflist']}  |  목록 항목수: {mr['n_reflist_entries']}")
    if mr["missing_numbers"]:
        L.append(f"   🔴 목록에 없는 인용번호 {len(mr['missing_numbers'])}건: {mr['missing_numbers'][:30]}")

    L.append(f"\n=== 오류 카테고리 {r['error_categories']}/6 (0=clean) ===")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("docx")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true", help="오류 있으면 exit 1")
    a = ap.parse_args()
    r = run_all(a.docx)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print(_fmt(r))
    if a.strict and r["error_categories"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
