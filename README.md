# sci-toolkit

**연구실 공용 Claude Code 스킬셋** — 논문 검색·원고 작성·그림 제작·데이터 분석을
AI가 일관된 절차로 처리하도록 만드는 지침서 모음입니다. 각 절차 끝에는 **검증 게이트**가
붙어 있어, "돌아갔다"가 아니라 "결과가 맞다"를 확인한 뒤에 끝납니다.

A shared Claude Code skillset for lab work — literature search, manuscript writing,
figure production, data analysis. Each route ends in a **verification gate**: the
artifact is not done until the gate passes, and gates are scripts, not advice.

```
스킬 31종 · 자체 회귀 테스트 9종 · 안전 가드 7종
python doctor.py   →   10 OK / 0 FAIL
```

개인 계정·개인정보·연구비 정보는 포함하지 않습니다.
미공개 연구 내용은 기계 검사(`doctor.py` SENTINEL)로 걸러집니다.

| 나는… | 여기부터 |
|---|---|
| 처음이라 뭐가 뭔지 모르겠다 | [docs/00_시작하기](docs/00_시작하기.md) |
| 일단 설치부터 | [QUICKSTART.md](QUICKSTART.md) — 필요한 스킬만 골라 설치 |
| 어떻게 돌아가는지 알고 싶다 | [docs/10_전체_워크플로우_지도](docs/10_전체_워크플로우_지도.md) |
| AI가 자꾸 엉뚱하게 한다 | [AGENTS.md](AGENTS.md) §0 라우팅 표 → "§0대로 해줘" |
| Word/PDF/PPT/Excel 이 안 된다 | [docs/12](docs/12_문서스킬_직접_준비하기.md) — 그 스킬들은 여기 없습니다(라이선스) |
| 쓰다가 불편한 걸 발견했다 | [docs/11_불편한점_남기기](docs/11_불편한점_남기기.md) — 그냥 말하면 기록됩니다 |

---

## sci-toolkit이 뭔가요? / What is sci-toolkit?

- Claude Code가 특정 작업(논문 검색, 실험 데이터 분석, 서열 설계, figure 제작 등)을 할 때
  참고하는 **스킬(skill) 모음** = `skills/` 폴더 하나하나가 독립된 기능 단위입니다.
- 스킬은 코드가 아니라 "이럴 때 이렇게 해라"는 **지침서 + 필요시 보조 스크립트**입니다.
  Claude Code가 대화 맥락에서 알아서 관련 스킬을 찾아 로드합니다 (수동 실행 불필요).

In short: each folder under `skills/` is a self-contained instruction set (a "skill")
that Claude Code auto-loads when relevant to your request — you don't run them by hand.
This package is the lab's shared skill SSOT with all personal/billing/account-specific
material stripped out.

---

## 모듈 목록 / Module List

### 1. 논문 검색·작성 (Literature search & manuscript writing)
| 스킬 | 용도 |
|---|---|
| `research-search` | 연구/검색 질의의 메인 진입점 — OpenAlex/PubMed/Perplexity/Parallel로 자동 라우팅 |
| `research-lookup` | OpenAlex + PubMed E-utilities 기반 무료 논문/사실 검증 조회 |
| `openalex-database` | OpenAlex 2.4억+ 논문 DB 직접 질의 (저자/기관/인용 분석) |
| `pubmed-database` | PubMed 고급 질의 (MeSH/Boolean/PICO), REST/E-utilities 직접 제어 |
| `paper-extract` | 논문에서 필드 단위 정보 추출 |
| `literature-review` | 여러 DB를 종합해 정식 문헌리뷰 문서 생성 (인용 검증 포함) |
| `research-ideation` | 연구 아이디어 브레인스토밍/토론 |
| `reference-surveyor` | 참고문헌 서베이 |
| `manuscript-pipeline` | 원고 작성 전체 파이프라인 (구조화→집필→자체검토→다듬기, 저널별 스타일 지원) |
| `academic-term-rules` | 생명공학/생화학 용어·표기 표준 (학명 이탤릭체, 유전자/단백질 명명, 단위 표기 등) |
| `endnote-citation-injection` | EndNote 미포맷 인용 삽입 (SQLite 직접 INSERT 안전 절차 포함) |
| `scholar-evaluation` | 정량 루브릭 기반 연구물 평가 |
| `research-grants` | 연구제안서 작성 — NSF·NIH·DOE·DARPA 등 기관별 양식·심사기준·예산 |
| `parallel-web` | 웹 검색·URL 본문 추출·딥리서치 (Parallel API) |
| `perplexity-search` | 실시간 웹 검색 + 출처 인용 응답 (Perplexity via OpenRouter) |

### 2. 분자생물학·실험 (Molecular biology & experiments)
| 스킬 | 용도 |
|---|---|
| `primer-design` | iPCR 돌연변이(치환/결실), 제한효소 클로닝, 콜로니 PCR, 발현 분석, 주문서 생성 |
| `experiment-hub` | 실험 프로토콜 관리·조건 최적화·실험 제안·이력 기록·실험 간 비교 |

### 3. Figure (그림/시각화)
| 스킬 | 용도 |
|---|---|
| `publication-figures` | 논문/발표용 모든 그림의 통합 라우터 — AI 생성 스키마틱, HPLC/kinetic/BO 루틴 플롯, 다중패널 유의성 표기, 저수준 matplotlib 커스터마이징 |
| `markdown-mermaid-writing` | Mermaid 다이어그램 표준 — 구조·흐름도·타임라인은 이미지보다 Mermaid 우선 |
| `generate-image` | 범용 이미지 생성·편집(AI) — 사진·일러스트·컨셉아트 (기술 도해는 위 두 스킬 사용) |

### 4. 데이터·통계 (Data & statistics)
| 스킬 | 용도 |
|---|---|
| `stats-workflow` | 3단계 통계 워크플로우 — seaborn 탐색 → 가정 검정 포함 검정 선택 → APA 7판 서식 리포트 |
| `statsmodels` | OLS/GLM/혼합모형/ARIMA 등 구체 모형 클래스 + 상세 진단 |
| `lab-data-analysis` | 실험 데이터 통합 EDA (kinetic·HPLC·클러스터링·gel 등) + 화학 안전정보 조회 |
| `conda-env-manager` | conda 환경 진단·생성·복구, import 스캔, 버전 충돌 해소 |
| `get-available-resources` | CPU/GPU/메모리/디스크 탐지 — 무거운 계산 시작 전 전략 결정 |

### 5. 문서 (문서/파일 변환·작성)
| 스킬 | 용도 |
|---|---|
| `docx` ⚠️외부 | Word 문서 편집 — Anthropic 소유라 미포함([docs/12](docs/12_문서스킬_직접_준비하기.md)). 랩 자체 원고 QC 도구 7종은 `manuscript-pipeline/scripts/` 에 있음 |
| `pptx` ⚠️외부 | 발표자료 편집 — Anthropic 소유라 미포함([docs/12](docs/12_문서스킬_직접_준비하기.md)) |
| `journal-presentation-maker` | 저널클럽·랩미팅 발표자료 자동 작성 및 리뷰 |
| `markitdown` | PDF/DOCX/PPTX/XLSX/이미지(OCR)/오디오(전사) 등을 Markdown으로 변환 |
| `pdf` ⚠️외부 | PDF 조작 — Anthropic 소유라 미포함([docs/12](docs/12_문서스킬_직접_준비하기.md)) |
| `xlsx` ⚠️외부 | 스프레드시트 편집 — Anthropic 소유라 미포함([docs/12](docs/12_문서스킬_직접_준비하기.md)) |

### 6. 검증·개발 규율 (Validation & engineering discipline)
| 스킬 | 용도 |
|---|---|
| `scientific-validation` | fitting/최적화 결과가 논문·보고서에 들어가기 전 최종 타당성 게이트 (질량보존, 물리적 타당성, 부작용 없는 재현 등) |
| `code-quality` | SOLID 원칙·파일 크기 한계·체계적 리팩토링 |
| `git-workflow-manager` | git 워크플로우 — pull 강제, 임시파일 정리, 커밋 규칙 |
| `skill-developer` | 새 스킬 작성·트리거 설정 가이드 (이 툴킷을 직접 확장할 때) |

### 7. 배포판 자체 구성 (Package scaffold)
| 항목 | 용도 |
|---|---|
| `install/install.py` | 선택 설치 프로그램 — 프리셋/개별 스킬 단위로 골라 설치 (의존 스킬 자동 동반) |
| `config/catalog.json` | 스킬 카탈로그 SSOT (카테고리·의존성·용량·프리셋). 설치 프로그램이 이 파일을 읽음 |
| `config/credentials.example.json` | 외부 연동 자격증명 템플릿 (실제 키는 각자 채워 넣고 공유 금지) |
| `hooks/` | 안전 가드 7종 — 시크릿 유출·강제 삭제·위험한 git(fork upstream 포함)·클라우드 재귀 스캔 차단 + Windows 환경불일치 3종 |
| `scripts/` | 연구용 보조 도구 (HPLC 파서, primer 구조 점검, 변이 필터, JCR 검증, 엑셀 수식 점검, `ref_fetch.py`=DOI 기반 공개(OA) 서지정보·PDF 자동 수집+CrossRef/OpenAlex 교차검증 등) + 외부 연동 커넥터 |
| `docs/` | 초심자 문서 13종 (시작하기 → 설치 → API/MCP → 토큰·비용 → 규칙주기 → 외부연동 → 기능별 준비물 → Notion/Asana → 원격서버 → **전체 워크플로우 지도** → 불편한점 남기기 → 문서스킬 준비) |
| `AGENTS.md` | **AI가 따르는 운영 규칙.** §0의 라우팅 표가 "어떤 요청 → 어떤 스킬 → 어떤 검증"을 정한다. AI가 엉뚱하게 갈 때 "§0대로 해줘"라고 하면 된다 |
| `tests/` | 이 패키지 자체의 회귀 테스트 9종 (시크릿·연구마커 검사, 문서 참조 실존, 라우팅 정합, 비파괴 설치, 능력 소실 탐지, 훅 양방향 검증). `doctor.py`가 자동 실행 |
| `doctor.py` / `doctor.ps1` | 배포판 무결성·환경 점검 (PASS/FAIL 리포트) |
| `SHA256SUMS` | 전체 파일 해시 — 복사·전송 후 손상 여부 검증용 |
| `evals/` | 라우팅이 실제로 발동하는지 headless 로 측정 (느리고 비용 발생 — 수동 실행) |
| `scripts/capability_diff.py` | 스킬을 고쳐 쓴 뒤 **기능이 조용히 빠지지 않았는지** 구조적으로 대조 |
| `scripts/feedback_log.py` | 불편·오류 기록 (계정·토큰 불필요) |

> 정확한 각 스킬의 상세 사용법·트리거 문구는 각 `skills/<이름>/SKILL.md`를 확인하세요.

---

## 어떻게 불러오나요? / How to load it

1. 이 폴더 전체(`sci-toolkit/`)를 자신의 Claude Code 스킬 경로에 복사합니다.
   보통 `~/.claude/skills/` 아래에 `skills/` 안의 원하는 스킬 폴더들을 넣거나,
   `skills/` 폴더 전체를 그대로 이어 붙이면 됩니다.
2. Claude Code를 재시작하거나 새 세션을 시작하면 스킬 목록에 자동으로 잡힙니다.
3. 이후는 그냥 평소처럼 대화하면 됩니다 — 예: "이 논문 리뷰해줘", "primer 설계해줘",
   "이 데이터 통계 검정 뭐 써야 해?" 라고 물으면 Claude Code가 관련 스킬을 알아서 찾아 씁니다.
4. 특정 스킬만 필요하면 전체를 복사할 필요 없이 해당 `skills/<이름>/` 폴더 하나만 복사해도 됩니다
   (모듈형 설치, 자세한 건 `QUICKSTART.md` 참고).

Copy the folder(s) you need into your own Claude Code skills path (typically under
`~/.claude/skills/`), restart/start a new session, and just talk to Claude Code normally —
it will pick the relevant skill automatically based on context. You do not need to "run"
a skill manually, and you can install just one skill folder instead of the whole set.

**베이스 환경 / Base requirement**: Claude Code (구독 기반, subscription) 우선.
API 키 발급 없이 구독 로그인만으로 대부분의 스킬이 동작합니다. 일부 스킬(예: 외부 DB 직접
조회)은 무료 API를 쓰거나 선택적으로 API 키를 요구할 수 있습니다 — 해당 스킬의 `SKILL.md`에
명시되어 있습니다.

---

## 안전 공지 / Safety Note

- 이 배포판에는 **개인정보·계정정보·연구비/과제 정보가 전혀 포함되어 있지 않습니다.**
  (`.distignore`에 의해 `research_fund/`, `secrets.json`, `*.credentials.json`, dual-PC 위임
  스크립트, 홈PC 전용 스크립트 등은 패키징 단계에서 자동 제외됩니다.)
- 배포 전 랩 관리자가 `.distignore` 규칙에 따라 필터링을 거친 상태이므로, 받은 그대로
  사용하면 됩니다. 스스로 스킬을 추가/수정할 경우, 개인 계정 토큰·이메일·연구비 번호 등을
  절대 포함하지 마세요.
- 외부(랩 밖)에 재배포하기 전에는 관리자에게 먼저 확인하세요.
- **라이선스**: 저장소 전체는 MIT([LICENSE](LICENSE))이지만 스킬마다 자체 라이선스가
  있습니다. 재배포 전 각 `SKILL.md` 앞머리를 확인하세요 — 자세한 건 [NOTICE.md](NOTICE.md).
  `docx`·`pdf`·`pptx`·`xlsx` 는 Anthropic 소유라 이 저장소에 **포함되지 않습니다**.

This distribution contains **no personal data, no account credentials, and no funding/
billing information** — these are automatically excluded at packaging time per
`.distignore` (`research_fund/`, `secrets.json`, `*.credentials.json`, dual-PC delegation
scripts, home-PC-only scripts, etc.). If you extend this package yourself, never add
personal tokens, emails, or grant/billing numbers to it. Check with the lab admin before
redistributing outside the lab.
