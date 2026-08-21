# Korean AI-Writing Tells (한국어 AI 문체 패턴) — Reference Supplement

**DETECT-ONLY supplement** for the `avoid-ai-writing` skill, covering Korean-language
tells. English tells are covered exhaustively in `SKILL.md` (which already absorbed the
blader/humanizer taxonomy) — this file adds what `SKILL.md` cannot: patterns specific to
Korean (번역투, 종결어미 리듬, 형식명사, 경어법 일관성 등).

Usage rules:
- FLAG only — never auto-rewrite. When invoked for a deliverable (mail draft, report,
  manuscript-adjacent doc), this file operates under detect mode regardless of the
  skill's default mode (user rule C-62).
- Recipient/author learned voice always wins. If a flagged pattern matches a documented
  voice profile (honorifics, sign-off form, tone learned from Sent mail, or an explicit
  style choice), mark it "voice override" and treat it as informational, not actionable.
- Severity: S1 = critical (near-certain AI tell), S2 = high, S3 = low/corroborating.

Source: [epoko77-ai/im-not-ai](https://github.com/epoko77-ai/im-not-ai)
(`skills/humanize-korean/references/ai-tell-taxonomy.md`, Korean AI Tell Taxonomy v2.0,
MIT License, fetched 2026-08-22). Categories A–J, 71 sub-patterns.

---

## A. 번역투 (Translation-ese) — 19 patterns

- A-1 "~에 대하여/대해서" 남발 [S1] — "AI 규제**에 대해** 논의할 필요가 있다"
- A-2 "~를 통하여/통해" 남발 [S2] — "데이터 분석**을 통해** 인사이트를 얻는다"
- A-3 "~에 있어(서)" [S1] — "이 문제**에 있어서** 중요한 것은"
- A-4 "~라는 점에서" [S2] — "확장성이 뛰어나**다는 점에서** 의미가 있다"
- A-5 "~와 관련하여/관련된" [S2] — "보안**과 관련하여** 주의해야 한다"
- A-6 "~에 기반하여"/"~을 바탕으로" 남발 [S2] — "데이터**에 기반하여** 판단한다"
- A-7 "가지고 있다" (light verb) [S1] — "강한 경쟁력을 **가지고 있다**"
- A-8 이중 피동 "~되어진다"/"~지게 된다" [S1] — "판단**되어진다**"
- A-9 "~에 의해" 피동문 [S2] — "AI**에 의해** 생성된 이미지"
- A-10 "~할 수 있다" 남발 [S2] — "효율을 높**일 수 있다**. 비용을 줄**일 수 있다**."
- A-11 "~을 위해" 목적절 남발 [S2] — "고객 만족**을 위해** 노력한다"
- A-12 "만들어지다"/"이루어지다" [S2] — "합의가 **이루어졌다**"
- A-13 명사 나열 (조사 생략) [S2] — "AI 기술 발전 속도 가속화"
- A-14 접속부사 "그리고" 절 연결 [S2] — "그는 보고했다. **그리고** 자리에 앉았다."
- A-15 추상 주어 + 만능 동사 [S2] — "DeepSeek-V4**의 등장은** ~을 **보여줍니다**"
- A-16 영어 대명사 직역 (그/그녀/그것/그들) [S1] — "존은 피곤했다. **그는** 앉았다. **그는** 한숨을 쉬었다."
- A-17 (보류) 무정물·추상명사 '-들' 부착 [—] — upstream hold 상태(재평가 예정), informational only
- A-18 관계대명사절 직역 — 긴 좌향 수식 [S2] — "**사고를 일으킨 화학물질을 생산한 회사에서 한때 일했던 한 남자를** 만났다."
- A-19 이중 조사 결합 (-에서의·-에로의·-으로의 등) [S2] — "주점의 2층**에서의** 살림"

## B. 영어 인용·용어 과다 — 4 patterns

- B-1 괄호 병기 관습 [S2] — "인공지능**(AI)**은 거대언어모델**(LLM)**과 다르다."
- B-2 불필요한 영어 장식·일회성 jargon [S2] — "사용자에게 **seamless**하고 **robust**한 경험"
- B-3 과도한 영어 인용구 [S2] — 영문 인용문을 번역 없이 박아넣음
- B-4 "~라고 알려진", "~로 일컬어지는" [S3] — "**'AGI'라고 알려진** 범용 인공지능"

## C. 구조적 AI 패턴 (서식·레이아웃) — 12 patterns

- C-1 기계적 병렬 열거 [S2] — "첫째, ~. 둘째, ~. 셋째, ~."
- C-2 과도한 불릿 리스트 [S2] — 3개 이상 연속 불릿
- C-3 반복적 섹션 헤딩 [S2] — "## 도입 ## 본론 ## 결론"
- C-4 문단 첫 문장 요약 공식 [S2] — 매 문단이 topic sentence로 시작
- C-5 이모지 남발 [S1] — "✅ 🚀 💡 ⚠️ 📊" (리스트 머리에)
- C-6 헤딩 아래 한 줄 요약 박스 [S2] — "이 섹션에서는 ~를 다룬다"
- C-7 문단 간 기계적 "먼저·반면·결국" 3단 공식 [S2] — 세 문단이 순서대로 문두 접속사로 시작
- C-8 대칭 대구 공식 "A인가, B인가" 반복 [S1] — "독점**인가**, 확산**인가**"
- C-9 숫자 괄호 인덱싱 "1) 2) 3)" [S2] — "**1)** 표준화된 인프라... **2)** 도메인 특화..."
- C-10 콜론 부제 헤딩 공식 "X: Y" [S2] — "### **서론**: 제조업의 미래, AI에 달려있다"
- C-11 연결어미 뒤 쉼표 [S1] — "AI는 빠르게 발전하**지만,** 기업의 대응은 더디다"
- C-12 쉼표 포함률 (문서 단위) [S2] — 전체 문장 중 50% 이상이 쉼표 포함

## D. AI 특유의 관용구 (Signature Phrases) — 7 patterns

- D-1 종결·요약류 [S1] — "결론적으로", "요약하면", "~라고 할 수 있다"
- D-2 의의·중요성 과장 [S1] — "시사하는 바가 크다", "주목할 만하다"
- D-3 열거 도입 [S1] — "크게 세 가지로 나눌 수 있다"
- D-4 AI 티 특화 (hype 어휘) [S1] — "혁신적인", "획기적인", "**압도적**", "**파격적**"
- D-5 의인화된 추상 주어 [S2] — "**두 지능의 충돌**이 질문을 **던집니다**"
- D-6 완결 공식형 결말 "~할 때입니다 / 시점입니다" [S2] — "~해야 할 **때입니다**"
- D-7 변환 공식 "X에서 Y로 / X을 넘어 Y로" [S2] — "**'규모의 경쟁'에서 '전략의 경쟁'으로**"

## E. 리듬·문장 길이 균일성 — 7 patterns

- E-1 문장 길이 표준편차 낮음 (장문 부재) [S2] — 모든 문장이 30~50자 범위
- E-2 동일 종결어미 반복 [S2] — "~이다. ~이다. ~이다."
- E-3 모든 문단 3~4문장 공식 [S2] — 문단 길이 일정
- E-4 단문 일변도 (복문·중문 부재) [S2] — "AI는 빠르게 발전한다. 기업은 따라가야 한다."
- E-5 쉼표 분절 평균 길이 (긴 절 구조) [S2] — 쉼표 분절이 평균 8어절 이상
- E-6 쉼표 전후 POS 다양성 높음 (구문 복잡도) [S2] — 쉼표가 명사·부사·동사·관형사 뒤 무차별 삽입
- E-7 청자 경어법 일관성 손실 (해라/하게/해요/합쇼체) [S2 · estimated] — 한 대화에서 "합쇼"→"해라" 점프 (upstream이 severity 근거를 잠정치로 표시)

## F. 과도한 수식·중복 — 5 patterns

- F-1 정도부사 중독 [S2] — "**매우**", "**정말**", "**진짜로**"
- F-2 동의어 이중 수식 [S2] — "중요하고 핵심적인 역할"
- F-3 기능+역할 복합구 [S2] — "~로서의 역할과 기능"
- F-4 과잉 접두·접미 (-성·-적·-화·-tion·-ment·-ness·-ity) [S2] — "**근본적 관점**에서 **구조적 변화**"
- F-5 "~적 N" 복합 추상어 체인 [S2] — "에이전트**적** 자율성", "기술**적** 안정성"

## G. 과도한 Hedging (완곡) — 3 patterns

- G-1 추측·관측형 종결 [S2] — "~할 수 있을 것으로 보인다", "~인 것으로 판단된다"
- G-2 이중·삼중 완곡 [S2] — "~할 가능성이 있을 수 있다"
- G-3 안전 균형 lexicon (Safe Balance Score) [S2] — "양쪽 모두", "두 가지 모두", "신중하게"

## H. 접속사 남발 — 4 patterns

- H-1 문두 접속사 과다 [S2] — "또한", "따라서", "즉", "나아가", "아울러"
- H-2 "하지만"과 "그러나" 혼용 남발 [S2] — 역접이 문단마다 등장
- H-3 "이는 ~" 지시 반복; 메타 진입 변종 [S2] — "**이 점에서**", "**이 관점에서 보면**"
- H-4 재정의 접속사 "즉" 남발 [S2] — "AI 민주화, **즉** 경제성 측면에서"

## I. 형식명사·의존명사 과다 — 6 patterns

- I-1 "것이다" 종결 남발 [S2] — "~한 **것이다**", "~일 **것이다**"
- I-2 "점", "바", "수", "데" 반복; "~라는 점에 있다" [S2] — "주목할 **점**은", "X은 ~**라는 점에 있다**"
- I-3 "~라는 것"; "~다는 뜻이다" 결말 변종 [S2] — "변화가 크**다는 것이다**"
- I-4 "~할 필요가 있다"; 권고형 결말 "~해야 한다" [S2] — "~를 **구축해야 한다**" (정책·보고서 5회+)
- I-5 "~이/가 필요하다" [S2] — "혁신이 필요하다", "변화가 필요하다"
- I-6 "~능력" 추상명사 연쇄 [S2] — "사고 **능력**", "워크플로우 수행 **능력**"

## J. 시각 장식 남용 — 4 patterns

- J-1 과도한 **볼드** [S2] — 문장마다 핵심 단어 볼드
- J-2 따옴표 과다 [S2] — "'옥석 가리기'·'금융 슈퍼앱'" (5회+)
- J-3 대시(—) 남용 [S2] — "AI는 도구 — 그 이상도 이하도 아닌 — 이다"
- J-4 괄호 부연 과다 [S2] — "(이는 ~을 의미한다)"

---

## Detect output format (Korean scans)

Report findings as a table — no rewriting, no suggested replacement text:

| Category | Severity | Location | Quoted text | Why it reads as AI |
|----------|----------|----------|-------------|--------------------|
| e.g. A-1 | S1/S2/S3 | line/paragraph | verbatim excerpt | one-line reason naming the pattern |

- Quote the exact offending text; do not paraphrase.
- One row per occurrence (not per pattern type), so frequency stays visible.
- Voice-profile matches get "voice override" in the Why column and count as
  informational.
- End with a one-line summary count by severity (S1/S2/S3).
- Caveats from `SKILL.md` §"What this skill is and isn't" apply equally here:
  these are signals, not proof of authorship. Several patterns (A-10, C-11, H-1,
  I-4) fire on ordinary Korean policy/report registers — weigh density, not
  single hits.

---

## Attribution

- epoko77-ai/im-not-ai — MIT License. https://github.com/epoko77-ai/im-not-ai
  (taxonomy extracted 2026-08-22; detect-only adaptation, rewrite pipeline
  deliberately not adopted)
