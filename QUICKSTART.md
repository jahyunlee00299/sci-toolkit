# QUICKSTART — USB에서 5분 안에 시작하기 (초심자용)

이 문서의 목표는 **초심자**가 sci-toolkit을 USB 드라이브(또는 공유 폴더)에서
받아 Claude Code에서 5분 안에 뭔가 돌아가게 만드는 것입니다. 설치부터 시작하지
마세요 — 순서는 **문서부터 읽고, 필요한 모듈만 고르고, 설치는 마지막**입니다.

Base = **Claude Code + 구독(Pro/Max)을 우선 사용**. 대부분의 모듈은 별도 API
키 없이 바로 동작합니다.

---

## Step 0 — 전제 조건 확인 (30초)

- Claude Code가 이미 설치되어 있고, **구독(Pro/Max 등)에 로그인되어 있어야**
  합니다. 이 배포판은 **구독 기반 사용을 기본(base)으로** 설계되어 있어서,
  대부분의 스킬은 별도 API 키 없이 바로 동작합니다.
- API 키가 필요한 일부 스킬(외부 DB 직접 조회 등)은 핵심 기능(논문 검색,
  figure, 통계, primer 설계 등)에는 필요하지 않습니다. 실제로 필요할 때만 해당
  스킬의 `SKILL.md`를 읽고 준비하세요.

---

## Step 1 — 설치 없이 문서부터 읽기 (2분)

USB를 꽂자마자 복사/설치하지 마세요. 먼저 이 순서로 훑어보세요.

1. `README.md` — 전체 그림과 모듈 목록 (이 문서 바로 옆 파일)
2. 지금 하려는 작업이 아래 표에서 어느 모듈에 해당하는지 확인
3. 그 모듈의 `skills/<name>/SKILL.md`를 한 번 열어본다 (트리거 문구와 사용
   예시 확인)

| 하고 싶은 일 | 영역 (Area) | 모듈 (Module) |
|---|---|---|
| 논문 찾기/요약/리뷰, 원고 작성·다듬기 | 논문검색·작성 | `research-search`, `literature-review`, `manuscript-pipeline`, `academic-term-rules` |
| 원고를 특허 명세서 초안으로 | 논문검색·작성 | `patent-invention-disclosure` |
| primer/서열 설계 | 분자생물학 | `primer-design`, `experiment-hub` |
| 논문/발표용 figure 만들기 | figure | `publication-figures` |
| 어떤 통계 검정을 써야 할지 모를 때 | 통계 | `stats-workflow`, `data-quality-checks` |
| 설치된 도구/환경 상태 확인 | 포털 | `get-available-resources`, `doctor.py` |
| 사용 중 불편했던 점·오류 기록 | 작업로그 | `scripts/feedback_log.py` |
| PDF/문서를 텍스트로 읽기 | (built-in) | `markitdown` |
| 결과가 말이 되는지 검증 | (검증 게이트) | `scientific-validation` |

> 이 단계에서는 아무것도 설치되지 않습니다. "뭘 고를지" 확인하는 단계일
> 뿐입니다.

---

## Step 2 — 필요한 모듈만 설치 (1-2분)

**한 번에 다 설치하지 말고, 지금 당장 쓸 것만** 고르세요. 이 툴킷은
**모듈 선택 설치**(`install/install.py`)를 지원하므로 "나는 원고 작성만
한다"고 하면 관련 스킬만 설치됩니다. 그 스킬이 의존하는 다른 스킬(예:
`manuscript-pipeline`이 필요로 하는 `academic-term-rules`)은 **자동으로 같이
설치**되니 빠뜨릴까 걱정하지 않아도 됩니다.

> `docx`, `pdf`, `pptx`, `xlsx`는 Anthropic 소유라서 이 저장소에 포함되어
> 있지 않습니다. 설치 프로그램이 이 사실을 안내해 주고, 문서 작업 자체는
> Claude Code의 내장 기능으로 그대로 동작합니다.

### 가장 쉬운 방법 — 대화형 (초심자 추천)

`sci-toolkit` 폴더에서 아래를 실행하면 메뉴가 뜹니다. "뭘 하고 싶은지"에
번호로 답하세요.

```
python install/install.py
```

- 먼저 **미리보기**만 보여줍니다(아직 아무것도 바뀌지 않음). 설치될 내용을
  확인했으면 `--apply`를 붙여 다시 실행해서 실제로 설치하세요.
  ```
  python install/install.py --apply
  ```

### 뭐가 있는지 먼저 보고 싶다면

```
python install/install.py --list
```
38개 스킬과 프리셋을 카테고리별로 보여줍니다. 이 중 4개(docx · xlsx · pdf ·
pptx)는 Anthropic 소유라서 이 저장소에 번들되어 있지 않고 안내만 표시됩니다.

### 뭘 설치할지 이미 알고 있다면 (한 줄)

```bash
# 프리셋으로: 논문 작성 세트 (manuscript-pipeline + 의존 스킬 자동 포함)
python install/install.py --preset paper-writing --apply

# 또는 개별 스킬 선택
python install/install.py --skills primer-design,literature-review --apply
```

**프리셋 목록**: `paper-writing`(논문검색·작성) · `literature`(문헌 검색) ·
`molbio`(분자생물학) · `data-figures`(통계·figure) · `documents`(문서 작업)

**올인원(`all` 프리셋)은 수동으로만 실행합니다.** 공용 랩 PC 세팅처럼 정말
전부 필요한 경우가 아니면 권장하지 않으며, 자동으로 걸리지 않습니다 — 아래
Step 4에서 직접 명령을 입력해야 실행됩니다.

- 설치 대상 폴더 기본값은 `~/.claude/skills/`입니다. 다른 경로가 필요하면
  `--dest <path>`로 지정하세요.
- "설치"는 빌드/컴파일이 아니라 **폴더 복사가 곧 설치**입니다. 설치
  프로그램이 그 복사를 대신 해 주고, 필요한 의존 스킬을 빠뜨리지 않도록
  챙겨 줍니다.

---

## Step 3 — 새 세션에서 바로 써보기 (1분)

1. Claude Code를 재시작하거나 새 대화를 엽니다.
2. 평소처럼 자연어로 요청합니다. 예:
   - "이 논문 초록 요약해줘"
   - "이 유전자에 K123A 치환 넣을 primer 설계해줘"
   - "이 HPLC 데이터로 figure 만들어줘"
3. Claude Code가 알아서 관련 스킬을 찾아 로드합니다. 스킬 이름을 직접
   말하지 않아도 되지만, 원하면 "primer-design 스킬 써줘"처럼 지정해도
   됩니다.

여기까지가 초심자가 5분 안에 끝낼 수 있는 최소 경로입니다.

---

## Step 4 (선택) — 전부 설치하거나, 설치 프로그램 없이 수동 복사

**정말로 전부 필요한 경우**(예: 공용 랩 PC 세팅)에는 설치 프로그램의
`all` 프리셋을 씁니다. 38개를 한 번에 다 받으면 뭐가 왜 로드됐는지 알기
어려워지므로, 필요한 것만 고르는 두 단계 방식이 더 나은 출발점입니다.
하지만 정말 전부 필요하다면:

```
python install/install.py --preset all --apply
```

**올인원은 자동 실행되지 않고 항상 수동으로 명령을 입력해야 합니다.** 위
`--preset all --apply`를 직접 치기 전까지는 아무 일도 일어나지 않습니다.

**Python 설치 프로그램을 실행할 수 없는 환경**이라면, 폴더 복사가 곧
설치이므로 손으로 복사해도 됩니다. 이 경우 **의존성은 직접 챙겨야**
합니다(예: `manuscript-pipeline`은 `academic-term-rules`가 있어야 제대로
동작).

```powershell
# 스킬 하나만 (Windows) — 의존성은 직접 확인
Copy-Item -Recurse "E:\sci-toolkit\skills\primer-design" "$env:USERPROFILE\.claude\skills\primer-design"
```

```bash
# 스킬 하나만 (macOS/Linux)
cp -r /Volumes/USB/sci-toolkit/skills/publication-figures ~/.claude/skills/publication-figures
```

설치 후에는 새 세션에서 스킬 목록에 제대로 뜨는지 확인하세요. 안 쓰는
스킬은 나중에 폴더째 지워도 됩니다(스킬끼리는 서로 독립적이라 다른 스킬에
영향 없음). 각 스킬이 뭘 필요로 하는지는 `config/catalog.json`의
`requires` 필드에 나와 있습니다.

---

## 막혔을 때 (Troubleshooting)

- 스킬이 인식되지 않으면: 복사한 경로가
  `~/.claude/skills/<skill-name>/SKILL.md` 구조와 맞는지 확인하세요(불필요한
  감싸는 폴더가 하나 더 있지는 않은지).
- 특정 스킬이 API 키를 요구하면: 해당 스킬의 `SKILL.md`에 필요한 키와 무료
  대안이 적혀 있습니다. 키가 필요 없는 스킬부터 먼저 써보세요.
- 그래도 안 되면: 랩 관리자(배포판 유지 담당자)에게 물어보세요. 이 배포판은
  개인정보가 없는 공용 버전이므로, 개인 설정 문제라면 공용 문서보다 본인의
  Claude Code 환경 설정을 먼저 확인하는 편이 보통 더 빠릅니다.
