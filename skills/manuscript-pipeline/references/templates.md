# Templates — Cover Letter / Reviewer Response / Revision (manuscript-pipeline reference)

## Cover Letter Template
```
Dear [Editor Name],

We submit [Title] for consideration in [Journal].

[1 paragraph: what we did and the key finding]

[1 paragraph: why this is significant for the field]

[1 paragraph: why this fits the journal scope]

All authors have approved the manuscript.
No conflicts of interest to declare.

Sincerely,
[Corresponding Author]
```

## Reviewer Response (quick)
```
We thank Reviewer X for their constructive comments.

**Comment 1:** [quote reviewer]
**Response:** [explanation]
**Revision:** [what changed, line numbers]
```

---

## Phase 5 — Revision Response Mode (`revise-response`)

리뷰어 코멘트를 받아 point-by-point 응답을 구조화한다.

### Input
- 리뷰어 원문 (이메일/PDF/텍스트) — 보통 reviewer 1, reviewer 2... 로 구분
- 원고 현재 버전 (DOCX 또는 텍스트)

### Workflow
1. **Parse comments**: reviewer별·코멘트별로 분리. 각 코멘트에 ID 부여 (`R1.1`, `R1.2`, `R2.1`...).
2. **Classify**: each comment → one of `factual` / `clarification` / `additional-experiment` / `literature` / `style` / `structural`
3. **Draft response per comment**:
   ```
   Comment R1.1: [원문]
   Classification: clarification
   Response: [답변 — 인정/반박/타협]
   Manuscript change: [수정사항 + 라인 번호 또는 "no change"]
   ```
4. **Tone policy**: "기존이 못한 것" 프레임 금지 → "보완/추가" 프레임.
5. **Output formats**: JSON (재처리 가능) / Markdown table (사람용) / DOCX response letter (제출용)

### Output structure (JSON)
```json
{
  "reviewers": [
    {
      "id": "R1",
      "comments": [
        {
          "id": "R1.1",
          "original": "...",
          "classification": "clarification",
          "response": "...",
          "manuscript_change": "Lines 145-152, added paragraph on...",
          "status": "addressed | partial | rebutted"
        }
      ]
    }
  ]
}
```

### DOCX response letter format (IJBM/Elsevier style — based on 250718_IJBM_Revision_response.docx)

```
Response to Reviewers' Comments

Journal: <Journal Name>
Manuscript Number: <Number>
Manuscript title: <Title>

We sincerely thank the editor and all reviewers for their thorough and
constructive comments. We have addressed each comment in detail below,
and the corresponding changes in the manuscript are highlighted in red.
We respectfully request that our revised manuscript be reconsidered for
publication in <Journal Name>.

<Reviewer #1>

Reviewer #1: <개관/총평 인용>

Comment 1. <원문 인용>
Response: Thank you for this <valuable | constructive | important> comment.
<답변: 인정/반박/타협. 명확히 무엇을 어떻게 처리했는지>

[Revision: lines 445-446]
<수정된 본문 인용 — italics 또는 따옴표로 둘러쌈>

Comment 2. <원문 인용>
Response: Thank you for this <suggestion>.
...
```

**핵심 규칙** (사용자 실전 사례에서):
1. 응답 첫 문장은 항상 "Thank you for this <형용사> comment/suggestion/feedback."
2. 모든 manuscript change는 `[Revision: lines XXX-YYY]` 태그 + 실제 수정된 본문 인용
3. 인정 → 설명 → 수정 → 인용 순서
4. 반박할 때도 먼저 "We agree that..." 으로 부분 인정 후 "However, ..." 로 진행
5. 빨간색 하이라이트는 본문에서, response letter는 일반 텍스트
6. 제출 마지막 문장: "We respectfully request that our revised manuscript be reconsidered for publication"

---

## Discuss Mode — 결과 해석 + 고려사항 추천

사용자가 결과를 보여주며 "어떻게 해석?" / "Discussion 어떻게 쓸까?" / "이거 의미 있어?" 라고 물을 때 사용.

### Workflow
1. **Context gathering** (가정 금지, 모르면 질문): 실험 조건(온도·pH·농도·시간), 비교 대상(이전 실험·문헌·이론값), 측정 방법 + 오차 범위
2. **Three-tier interpretation**: **Primary**(data-supported) / **Alternative**(배제 불가) / **Excluded**(명시적 배제 + 이유)
3. **Comment categories**:
   - `[MECHANISM]` — 분자/효소 수준 메커니즘 가설
   - `[CONFOUND]` — 결과를 흐릴 수 있는 교란 변수
   - `[REPLICATION]` — 재현성·N 수·통계
   - `[COMPARISON]` — 문헌 대비 위치 (better/worse/comparable + 조건 차이)
   - `[FOLLOWUP]` — 다음에 해야 할 실험·분석
   - `[LIMITATION]` — 명시해야 할 한계점
4. **Output**: 7-step Discussion outline (핵심 발견 → 해석 → 문헌 비교 → 기여/의의 → 한계 → 향후 연구 → 결론) + 카테고리별 코멘트 박스
