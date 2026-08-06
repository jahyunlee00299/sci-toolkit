# Manuscript/Word/DOCX 다중 에이전트 워크플로우 규칙 (260529 확정)

**원칙: 분석은 병렬, 한 파일 편집은 한 명이 직렬 (map–reduce).**
manuscript·Word·docx·SI·표·인용·교정 등 **단일 docx 파일을 다루는 모든 작업**에 적용.

## 왜
`word/document.xml`은 단일 XML. 두 에이전트가 같은 파일을 각자 수정·저장하면 last-write-wins로
앞 변경이 소실되고, byte offset이 어긋나 OOXML이 깨진다(Word "파일 손상"). 그래서 **편집 주체는 항상 1명**.

## 표준 3단계

### 1) MAP — 분석/진단 병렬 (느린 부분을 쪼갠다)
여러 에이전트가 **읽기·진단·원문검증·치환안 생성**만 병렬 수행. 영역 분할:
- 표별(Table S1~S2 / S3~S4 / S5~S6 / …), 섹션별(Intro/Methods/Results), 또는 차원별(수치/인용/이탤릭/철자).
- 특히 **원문 PDF 정독·문헌값 재계산**처럼 느린 작업이 병렬화 효과 큼.
- 각 에이전트는 **파일을 수정하지 않고** "수정 패치 명세"만 반환:
  `{대상 표/블록, 찾을 run 텍스트(고유), 바꿀 내용, 사유}` 리스트.

### 2) REDUCE — 편집 직렬 (1명이 패치 취합 적용)
- **fixer(또는 메인) 1명**이 모든 패치를 순서대로 한 `word/document.xml`에 적용.
- zipfile로 document.xml만 교체. EndNote 필드(`<w:instrText>`,`<w:fldChar begin>..<end>`) 불가침.
- 패치 충돌(같은 run 중복 수정) 시 직렬이라 즉시 감지·해소.

### 3) VERIFY — QC 1명 (Word COM 필수)
- 4단계 preflight + **Word COM ground-truth** + 포매팅(폰트/줄간격/테두리/정렬).
- 통과 후에만 OneDrive 원본 교체. 실패 시 fixer에 반려.

## 도구 선택
- **TeamCreate**: 사람이 단계 사이 검토·결정에 개입할 때(분석 결과 보고 → 사용자 결정 → 편집). 대화형.
- **Workflow 도구**: 결정적 파이프라인이 필요하고 사용자가 "workflow" opt-in 했을 때.
  `pipeline(tables, analyze, ...)`로 표별 분석 fan-out → 패치 수집 → 단일 reduce 단계서 편집.
  편집 단계는 반드시 **단일 agent()** (worktree isolation은 docx엔 무의미 — zip 바이너리).

## ★ 변경 추적(Track Changes) + 메모(Comment) 적극 사용 (260529 사용자 지시)

수정을 **사용자가 Word에서 검토·수락/거부**할 수 있게, 가능한 한:
- **본문/표 텍스트 변경 → tracked change**로: 삽입은 `<w:ins w:id=".." w:author="Claude" w:date="..">…<w:r>…</w:r></w:ins>`,
  삭제는 `<w:del …><w:r><w:delText>…</w:delText></w:r></w:del>`. author는 "Claude"로 통일.
- **판단·근거·대안이 필요한 곳 → comment**: commentRangeStart/End + commentReference + comments.xml(+commentsExtended/Ids/Extensible 사이드카). 예: "이 수치는 measured-total 기준임", "ref RecNum #N으로 단 이유", "줄간격 원본부터 2.0".
- 각 결정/수정마다 짧은 comment로 **왜 그렇게 했는지** 남기면 Decision_Log와 이중으로 추적됨.

**DOCX 5대 금지 준수** (docx 무결성): pack.py / del안의 delText 누락 / ins 안의 del 중첩 /
floating delText / comment anchor 오삽입. comment anchor는 id=max+1, commentRangeStart는 w:p 직속 run 경계,
`rfind('<w:del ')` 공백 필수. incremental_edit.py + 4단계 preflight. (상세 → docx 스킬(이 저장소에 없음 — docs/12 참조)(이 저장소에 없음 — docs/12 참조))

**언제 tracked vs 직접 편집:**
- 사용자가 검토할 본문/표/수치/문구 변경 → **tracked + comment 권장**.
- 기계적·구조적(폰트 통일, 마커 형식, ZIP 빌드) → 직접 편집 가능(단 Decision_Log 기록).
- 사용자가 "tracked로/메모 달아서"라 하면 항상 tracked+comment.

## 금지
- 두 에이전트가 동일 docx를 동시에 Write/저장하는 구성 금지.
- docx 편집을 worktree 병렬로 나눠 git merge 시도 금지(바이너리).
- 에이전트 편집본을 Word COM 검증 없이 채택 금지(이번 세션 SI v36 손상 사례).

관련: `manuscript_qc_checklist.md`, docx 스킬(이 저장소에 없음 — docs/12 참조)(preflight·무결성 SSOT).
