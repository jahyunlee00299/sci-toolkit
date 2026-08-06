# Academic QC Mode — 규칙·순회 패턴 (manuscript-pipeline reference)

> `academic-qc` 모드의 상세 규칙·순회 코드.
> **표기 규칙의 단일 진실원천(SSOT)은 `academic-term-rules` 스킬** — 아래 R1~R13은
> 그 규칙들을 docx QC 작업에 매핑한 운영 표일 뿐, 규칙 정의 자체는 academic-term-rules를 따른다.

학술 표기 규칙 전수 교정. "학술 규칙 수정해줘", "표기 통일" 요청 시 사용.

## 출력 구조
```
corrections/
  step0_original.docx      원본 복사 (손대지 않음)
  step1_enzyme_italic.docx R1: 효소명 italic   (본문 + 표 셀 + 캡션)
  step2_abbrev.docx        R2: 약어 통일       (본문 + 표 셀 + 캡션)
  step3_units.docx         R5: 단위 표기        (본문 + 표 셀 + 캡션)
  step4_species_italic.docx R6: 종명 italic     (본문 + 표 셀 + 캡션)
  step5_comments.docx      R3/R4/R8/R9/R12: 플래그 코멘트 삽입
  step6_final.docx         최종 통합본
  QC_REPORT.md             R7/R10/R11/R13 진단 + 폰트·캡션·표 검증 결과표
```

## 진단 우선 (수정 전 필수): 검증 리포트
직접 수정(step1~4) 전에 **읽기 전용 진단 리포트**를 먼저 생성한다. 표 셀·캡션·폰트는
오탐(false positive)이 많으므로 일괄 자동수정보다 리포트 → 사용자 확인 → 선별 수정이 안전.
리포트 항목: A.폰트크기 일관성(본문 mode sz / 표 셀 sz / 캡션 sz), B.캡션 표기(R12),
C.표 셀 본문(R1/R2/R5/R6/R10 위반), D.three-line table(R7). 각 위반에 위치(표 N 행/열, 캡션 앞 30자, para index) 명시.

## 적용 규칙 목록 (정의는 academic-term-rules §N)

| 규칙 | 내용 | academic-term-rules | 처리 방식 | 적용 범위 |
|------|------|------|----------|----------|
| R1 | 효소명: 종 prefix 2글자만 italic (`*Xx*GDH`) | §2 | 직접 수정 | 본문 + **표 셀** + 캡션 |
| R2 | 약어 통일 (domain registry 기준) | §3, domain_abbrev_registry.md | 직접 수정 | 본문 + **표 셀** + 캡션 |
| R3 | Fig./Table 번호 역순 참조 | §7 | `[NUMBERING]` 코멘트 | 본문 + 캡션 |
| R4 | 인용 번호 문장 끝으로 이동 | — | `[CITATION-LOC]` 코멘트 | 본문 |
| R4b | 인용 번호는 **구두점 뒤** (`word.³³`, 마침표 밖) — numeric-superscript 저널(RSC/ACS/Nature). `word³³.` 위반. EndNote RSC style이면 자동 처리 → 미포맷 `[N].`은 format 권고 | §8a | `[CITATION-LOC]` 코멘트 | 본문 |
| R5 | 단위 표기: slash 형식(g/L, g/g, U/mL), superscript ⁻¹ 금지, 숫자+단위 공백 | §4 | 직접 수정 | 본문 + **표 셀** + 캡션 |
| R6 | 생물 종명 italic (*E. coli*) | §1 | 직접 수정 | 본문 + **표 셀** + 캡션 |
| R7 | Three-line table | §13 | `[FIGURE-FORMAT]` 코멘트 | **표** |
| R8 | 약어 첫 정의 누락 | §3 | `[ABBREV]` 코멘트 | 본문 |
| R9 | 문장 숫자 시작 | §6 | `[GRAMMAR]` 코멘트 | 본문 + 캡션 |
| R10 | *K*eq → 이탤릭 K + 아래첨자 eq | §5, §11 | `[NOTATION]` 코멘트 | 본문 + **표 셀** + 캡션 |
| R11 | 폰트 크기 일관성 | — | `[FONT-SIZE]` 코멘트 또는 직접 통일 | 본문 + **표 셀** + 캡션 |
| R12 | 캡션 표기 (`Figure N.`/`Table SN.` 라벨·번호·bold·마침표) | §7, §13 | `[CAPTION]` 코멘트 | 캡션 |
| R13 | 표 셀 화살표(→): Scheme/식/표 허용, 본문만 위반 | — | 카운트 보고 | **표** / 본문 |
| R14 | American spelling (titer/optimize/…), 고유명사·인용제목 보존 | §15 | 직접 수정 | 본문 + **표 셀** + 캡션 |
| R15 | *E*-factor (E만 italic), sEF/cEF roman, 그린메트릭 표기 | §16 | 직접 수정 + `[NOTATION]` | 본문 + **표 셀** + 캡션 |

**범위 주의 (핵심):** R1·R2·R5·R6·R10·R11 은 본문 paragraph뿐 아니라 `<w:tbl>` 안의 모든 `<w:tc>` 셀, figure/table caption paragraph 까지 순회 대상. body top-level `<w:p>`만 보면 표 셀·캡션을 빠뜨리기 쉽다.

**★ 다중 에이전트 워크플로우** (`references/docx_multiagent_workflow.md`): 단일 docx를 여러 에이전트로 처리할 때 **분석 병렬 + 편집 직렬(map–reduce)**. ①MAP 진단·검증·치환안 병렬(파일 수정 X) ②REDUCE fixer 1명 직렬 편집 ③VERIFY QC 1명 Word COM. 동시 편집 금지.

**★ 전수 QC 체크리스트** (`references/manuscript_qc_checklist.md`): "최종본" 선언 전 30개 항목. docx 구조 편집 위임 시 **Word COM 검증 후 채택 필수**.

## 통합 절차 (에이전트 필수 준수)

0. **진단 리포트 먼저** (`QC_REPORT.md`) — 본문·표 셀·캡션 전수 스캔, 위반 분류·위치 기록
1. `corrections/` 폴더 생성, `step0_original.docx` 복사
2. 각 규칙 단계별 적용 → `step1~step5`. R1/R2/R5/R6/R10 적용 시 표 셀·캡션 paragraph까지 순회
3. `step6_final.docx` 생성 전 **comment ID 중복 검사**: 기존 max comment ID 확인 → `max_id + 1`부터 할당
4. `step6_final.docx` ZIP 무결성 전수 검증 + **Word COM**
5. PASS 시: 원본 → `_archive/{원본명}_pre_correction.docx` 백업 후 교체
6. FAIL 시: 문제 보고만, 교체 하지 않음

## 순회 대상 패턴 (본문 + 표 셀 + 캡션 전수)

`<w:body>` top-level `<w:p>`만 보면 표 셀·캡션을 놓친다. 텍스트 규칙(R1/R2/R5/R6/R10)과 폰트 검증(R11)은 아래 세 종류 paragraph를 **모두** 순회.

```python
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

def iter_target_paragraphs(root):
    """본문 + 표 셀 모든 w:p 산출 (iter()는 표 셀 안 w:p까지 재귀 포함)."""
    body = root.find(f'{{{W}}}body')
    for p in body.iter(f'{{{W}}}p'):
        yield p

def is_in_table(p):
    anc = p.getparent()
    while anc is not None:
        if anc.tag == f'{{{W}}}tc':
            return True
        anc = anc.getparent()
    return False

def is_caption(p):
    """캡션 휴리스틱: Figure/Table/Fig./Scheme (+ SI는 S 접두) 로 시작."""
    txt = ''.join(t.text or '' for t in p.iter(f'{{{W}}}t')).strip()
    return bool(re.match(r'^(Figure|Table|Fig\.|Scheme)\s*S?\d', txt))

def cell_iter(root):
    """표 단위 순회: (tbl_idx, row_idx, col_idx, tc_element)."""
    body = root.find(f'{{{W}}}body')
    for ti, tbl in enumerate(body.iter(f'{{{W}}}tbl')):
        for ri, tr in enumerate(tbl.findall(f'{{{W}}}tr')):
            for ci, tc in enumerate(tr.findall(f'{{{W}}}tc')):
                yield ti, ri, ci, tc
```

**폰트 크기(R11)**: 본문 mode sz는 `is_in_table=False and not is_caption` paragraph의 run `w:sz/@w:val` 최빈값. 표 셀 sz·캡션 sz는 별도 집계해 mode 대비 이탈 run만 보고. `w:sz` 미지정 run은 styles.xml default sz로 보정.

**Three-line table(R7)**: 각 `<w:tbl>`의 `w:tblPr/w:tblBorders` 와 `w:tc/w:tcPr/w:tcBorders` 에서 `w:left`/`w:right`/`w:insideV` 의 `w:val != "nil"/"none"` 이면 세로줄 위반. (border 두께·order는 academic-term-rules §13.)

## 주의: DOCX 편집은 docx 스킬(이 저장소에 없음 — docs/12 참조) 프로토콜 준수
python-docx `Document().save()` 금지. ZIP 원본 구조 보존 (`incremental_edit.py` 세션). 상세 → docx 스킬(이 저장소에 없음 — docs/12 참조).
