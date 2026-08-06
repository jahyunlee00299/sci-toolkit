# Manuscript DOCX QC Checklist

원고/SI docx를 "최종본"이라 부르기 전 **매번** 이 전 항목을 전수 확인한다.
도구: python(`python3` 아님) + zipfile로 `word/document.xml` 직접 분석. UTF-8 stdout 가드.
EndNote 필드(`<w:instrText>`, `<w:fldChar begin>..<end>`) 내부는 어떤 치환도 금지.

## A. 구조 무결성 (4단계 preflight — 필수)
1. **ZIP CRC**: `zipfile.ZipFile(p).testzip()` is None.
2. **XML well-formed**: 모든 `.xml`/`.rels`가 `ET.fromstring` 통과.
3. **Comment 무결성**: dangling `commentReference` 0 (id↔comments.xml 정의 1:1).
4. **Word COM ground-truth**: `New-Object -ComObject Word.Application`로 열어 "손상" 없이 OPEN + pages/tables/fields/comments 카운트. **XML well-formed여도 Word가 거부하면 실패** (OOXML 스키마 위반 — 에이전트 docx 편집 시 빈발). pages/tables/fields 보존 확인.

## B. 표 배열·footnote
5. **캡션→표→footnote 순서**: 모든 표가 caption 직후 table, table 직후 footnote. 잘못 떨어진 caption/footnote 색출(과거 Main Table 3가 caption→footnote→…→table로 깨진 사례).
6. **footnote 마커↔정의 1:1**: 셀의 위첨자 마커([a],ᵃ 등)와 footnote 정의가 dangling/orphan 없이 매칭.
7. **두 표 동기화**: 같은 항목이 Main 표 ↔ SI 표 양쪽에 있고 값·entry가 일치(Main Table3 ↔ SI Table S6).

## C. 수치 provenance (단일 진실원천)
8. **rawdata 엑셀 traceback**: 본문/표/figure 동일 수치는 단일 rawdata 파일에서 (`<rawdata>.xlsx`, This work=Efactor_FINAL 시트, 문헌=Lit_Efactor_FINAL 시트).
9. **문헌 비교값 원문 검증**: 남의 논문 sEF/cEF 등은 원문 PDF 조건으로 재계산. **추측값(assumed DCW, abstract yield 등) 금지** — 부피 미기재라도 농도(g/L)로 per-L 질량 계산은 가능; 산출 불가 항목만 n.c./n.a.
10. **단위 환산 검산**: mM↔g/L (MW), yield = product/measured-total-input.

## D. 참조/인용
11. **unformatted 태그 0**: `{Author, Year #N}` 잔재 없는지(Word Update 후). 있으면 사용자 Word "Update Citations" 안내.
12. **author-year → [N]**: 본문에서 "(Akagi 2002)" 식 표기 금지 → EndNote [N] 인용. (단 표 셀의 author-year 라벨은 허용.)
13. **빈 RecNum 금지**: `{Author, Year #}` (RecNum 공백)는 Update 시 깨짐 → EndNote DB(`...My EndNote Library_2025.Data\sdb\sdb.eni` refs 테이블, trash_state=0)에서 조회해 채움.
14. **인용번호 연속성**: [1..max] gap 점검(정상 gap은 허용, 보고).
15. **citation cluster ≤3**, Table N 참조 문단은 cluster 금지.

## E. refs_pdfs 파일 무결성
16. **파일명↔내용 일치**: 각 PDF 1페이지 제목/저자/연도가 파일명·인용과 일치(파일명이 내용과 다르거나 HTML이 PDF로 잘못 저장된 사례 빈발). 깨진 PDF는 `head -c 5`가 `%PDF-`인지.

## F. 이탤릭 (전수)
17. **학명**: genus/binomial(Acetobacter aceti, E. coli 등) 이탤릭, `sp.`는 로만. 긴 run 내부 윈도우 스캔으로 부분이탤릭 오탐 제거.
18. ***ee*** (enantiomeric excess): 물리량 기호 이탤릭.
19. ***E*-factor**: "E-factor"/"E factor"의 E만 이탤릭, sEF/cEF는 roman.
20. **효소 접두**: *Xx*GDH 처럼 species prefix만 이탤릭.

## G. 철자·표기 일관성
21. **철자 통일**: 저널 지정 따라 미국식/영국식 일괄(예: 미국식 = titer/optimize/modeling/isomerization…). field-aware 치환(필드·제목·DOI 보호).
22. **약어 일관성**: 정의 후 표준 약어 일관 사용. 단 효소명(풀네임)·문장 첫 단어·제목·캡션 예외.
23. **숫자 범위 대시**: en-dash(–, U+2013) — hyphen(-) 금지. (인용 [N-M]·DOI·페이지는 EndNote 소관, 건드리지 말 것.)
24. **단위 slash 형식**: g/L, U/mL (superscript ⁻¹ 금지).
25. **화살표**: 본문에서 `X → Y` 금지 → `-to-`/자연어로.

## H. 기본 포매팅
26. **폰트체**: 모든 본문/표 셀/캡션 run의 rFonts = Arial(비-Arial 색출).
27. **폰트 크기**: 본문 sz=24(12pt)/표 셀 sz≈17/캡션 일관(표마다 들쭉날쭉 색출).
28. **줄간격**: 표 셀 line=240 lineRule=auto, 본문은 저널 규정값.
29. **표 테두리**: three-line(외곽 sz12, 구분 sz4) — sz6/8 잔재·좌우/내부 세로선 색출.
30. **정렬(w:jc)**: 캡션/셀 정렬 일관성.

## 작업 원칙
- 수치·데이터 변경은 사용자 승인 없이 금지; 사용자가 답을 제시하면 즉시 수용.
- docx 구조 편집을 에이전트에 위임 시 손상 위험 큼 → **반드시 Word COM으로 검증** 후 채택(에이전트 편집본이 Word에서 "손상"으로 거부되는 사례 빈발).
- 결정은 단일 진실원천 위치(예: `Decision_Log/` 폴더)에 기록.
