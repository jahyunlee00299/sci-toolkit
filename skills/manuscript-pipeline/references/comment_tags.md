# Comment Mode — Word 코멘트 삽입 분류 체계 (manuscript-pipeline reference)

실전 저자/멘토 코멘트 패턴을 카테고리화. 코멘트 작성 시 prefix 태그를 붙여 reviewer가 즉시 판별 가능하게 한다.

## Prefix tags (Word 코멘트 첫 단어)

| Tag | 의미 | 예시 |
|---|---|---|
| `[STRUCTURE]` | 큰 그림 — story line, 문단 구성, novelty 위치 | "마지막 문단이 핵심. 여기에 연구 중요성/차별성/접근법이 나와야 함" |
| `[FLOW]` | 문맥/흐름 어색 | "이건 문맥 흐름상 이상한데? 왜 이 문장을 썼지?" |
| `[NOVELTY]` | 차별성/노벨티 명시 요구 | "기존이 못한 것 → 보완/추가 frame으로" |
| `[NUMBERING]` | Figure/Table 번호 중복·순서 | "Table 2 중복: 한쪽을 Table 3으로" |
| `[ABBREV]` | 약어 통일·정의 누락 | "ADP-glucose → ADP-Glc 전체 통일" |
| `[NOMENCLATURE]` | 명명법 (효소 italic, 종 italic) | "EcXylA → *Ec*XylA" |
| `[CITATION-LOC]` | 인용 위치 (문장 끝) | "참고문헌 번호가 문장 시작부 → 끝으로" |
| `[CITATION-MISSING]` | 핵심 선행연구 누락 [Critical] | "You et al. (2013) PNAS 110:7182 추가 필요" |
| `[METHODS-RESULTS]` | Methods vs Results 불일치 | "온도 범위 30-50°C라 했는데 Results는 20°C" |
| `[UNIT]` | 단위 표기 | "mM로 적어주세요" |
| `[FIGURE-FORMAT]` | 그림 번호·subplot 규칙 | "1.1, 1.2 대신 1a, 1b" |
| `[TYPO]` | 오탈자 | "brancing → branching" |
| `[BALANCE]` | 섹션 분량 균형 | "식량위기 부분이 ~25% 차지 → 3-4문장으로 축약" |
| `[DEFINE]` | 용어 정의 명확화 | "Branched starch와 glycogen-like glucan 관계 불명확" |
| `[EXPAND]` | 분량 확장 필요 | "Lignocellulose 섹션 최소 1문단 확장" |
| `[GRAMMAR]` | 한국어 문법 (한국어 논문) | "'며.' → 쉼표 또는 마침표 후 새 문장" |

## Critical 표기

코멘트 끝에 `[Critical]` 접미사를 붙이면 "이걸 안 고치면 reviewer가 거절할 가능성 높음" 표시. 실전 예: 핵심 선행연구 누락, Methods/Results 모순, 노벨티 부재.

## 출력 형식

Word 코멘트 삽입 시 작성자명을 명시 (`Claude` 또는 specific agent name) — 사람(저자/멘토)이 단 코멘트와 구분되도록. comment anchor는 id = 기존 max + 1, commentRangeStart는 `w:p` 직속 run 경계에 삽입.

## 멘토 vs 디테일 코멘트 분리

- **Mentor-style** (큰 그림): `[STRUCTURE]`, `[FLOW]`, `[NOVELTY]`, `[BALANCE]`
- **Detail-style** (구체 액션): `[NUMBERING]`, `[ABBREV]`, `[UNIT]`, `[CITATION-LOC]`, `[TYPO]`
- 한 코멘트에 두 스타일 섞지 말 것 — 분리해서 별도 코멘트로.
