# QUICKSTART — USB에서 5분 안에 시작하기 (초심자용)

이 가이드는 sci-toolkit을 **처음 받은 초심자**가 USB(또는 공유폴더)에서 꺼내
5분 안에 Claude Code로 뭔가를 해보는 것을 목표로 합니다. 설치부터 하지 마세요 —
**먼저 문서를 읽고, 필요한 모듈만 골라서, 마지막에만 설치**하는 순서입니다.

---

## 0단계 — 전제조건 확인 (30초)

- Claude Code가 이미 설치되어 있고, **구독(Claude Pro/Max 등) 로그인이 되어 있어야** 합니다.
  이 배포판은 **구독 기반 사용을 기본값(base)**으로 설계되어 있습니다 — 별도 API 키 발급
  없이 대부분의 스킬이 바로 동작합니다.
- API 키가 필요한 일부 스킬(외부 DB 직접 조회 등)은 없어도 핵심 기능(논문 검색, figure,
  통계, primer 설계 등)에는 지장이 없습니다. 필요해지면 그때 해당 스킬 문서를 보고 준비하세요.

---

## 1단계 — 설치 없이 문서부터 읽기 (2분)

USB를 꽂았다고 바로 복사/설치하지 마세요. 먼저 이 순서로 훑어봅니다:

1. `README.md` — 전체 그림, 모듈 목록 확인 (지금 이 파일의 옆 파일)
2. 지금 하고 싶은 작업이 어느 모듈에 해당하는지 아래 표에서 찾기
3. 그 모듈의 `skills/<이름>/SKILL.md` 한 번 열어보기 (트리거 문구·사용 예시 확인)

| 하고 싶은 일 | 모듈(스킬 폴더) |
|---|---|
| 논문 찾기/요약/리뷰 | `research-search`, `literature-review` |
| 원고(논문) 쓰기/다듬기 | `manuscript-pipeline`, `academic-term-rules` |
| Primer/서열 설계 | `primer-design` |
| 논문/발표용 그림 그리기 | `publication-figures` |
| 통계 검정 뭐 쓸지 모르겠음 | `stats-workflow` |
| PDF·문서를 텍스트로 읽기 | `markitdown` |
| 결과가 말이 되는지 검증 | `scientific-validation` |

> 이 단계에서는 아무것도 설치하지 않습니다. 그냥 "내가 뭘 골라야 하는지"만 확인하는
> 단계입니다.

---

## 2단계 — 필요한 모듈만 골라서 설치 (1~2분)

**전체를 한 번에 설치하지 말고, 지금 당장 쓸 기능만 골라서** 설치하세요.
이 툴킷에는 **골라 담기 설치기**(`install/install.py`)가 들어있어, "나는 논문 작성만
하겠다" 하면 관련 스킬만 설치됩니다. 필요한 다른 스킬(예: `manuscript-pipeline` 에
필요한 `academic-term-rules`)은 **자동으로 함께** 설치되므로 빠뜨릴 걱정이 없습니다.

> `docx`·`pdf`·`pptx`·`xlsx` 는 Anthropic 소유라 이 저장소에 없습니다. 설치기가
> 그 사실을 알려주며, 문서 작업 자체는 Claude Code 기본 기능으로 그대로 됩니다.

### 가장 쉬운 방법 — 대화형 (초심자 추천)

`sci-toolkit` 폴더에서 아래를 실행하면 메뉴가 뜹니다. "무슨 일을 하실 건가요?"에
번호로 답하면 됩니다.

```
python install/install.py
```

- 먼저 **미리보기**만 보여줍니다(아무것도 안 바뀜). 무엇이 설치될지 확인한 뒤,
  실제로 설치하려면 `--apply` 를 붙여 다시 실행하세요:
  ```
  python install/install.py --apply
  ```

### 어떤 기능이 있는지 먼저 보고 싶다면

```
python install/install.py --list
```
스킬 35개와 프리셋 목록이 카테고리별로 나옵니다. 그중 4개(docx·xlsx·pdf·pptx)는
Anthropic 소유라 이 저장소에 동봉되지 않고 안내만 나옵니다 — 실제로 설치되는 것은 30개입니다.

### 이미 뭘 설치할지 아는 경우 (한 줄로)

```
# 프리셋으로: 논문 작성 세트 (manuscript-pipeline + 의존성 자동)
python install/install.py --preset paper-writing --apply

# 개별 스킬만 골라서
python install/install.py --skills primer-design,literature-review --apply
```

**프리셋 목록**: `paper-writing`(논문 작성) · `literature`(문헌 조사) ·
`molbio`(분자생물학) · `data-figures`(데이터·그림) · `documents`(문서 작업) ·
`all`(전체 — 동봉 31개, 외부 4개는 안내만)

- 설치 대상 폴더는 기본이 `~/.claude/skills/`입니다. 다르면 `--dest <경로>` 로 지정하세요.
- 설치라고 해서 빌드/컴파일이 필요한 게 아닙니다 — **폴더 복사가 곧 설치**입니다.
  설치기가 그 복사를 대신 해주면서, 필요한 의존성을 빠뜨리지 않게 챙겨줍니다.

---

## 3단계 — 새 세션에서 바로 써보기 (1분)

1. Claude Code를 재시작하거나 새 대화를 엽니다.
2. 평소처럼 자연어로 요청합니다. 예:
   - "이 논문 초록 요약해줘"
   - "이 유전자에 K123A 치환 넣을 primer 설계해줘"
   - "이 HPLC 데이터로 그림 만들어줘"
3. Claude Code가 알아서 관련 스킬을 찾아 로드합니다. 스킬 이름을 직접 언급할 필요는
   없습니다 (원하면 "primer-design 스킬 써줘"처럼 명시해도 됩니다).

이제 끝입니다 — 여기까지가 초심자가 5분 안에 할 수 있는 최소 경로입니다.

---

## 4단계 (선택) — 전체 설치 & 설치기를 안 쓰고 직접 복사하기

**전체가 정말 필요하다면**(예: 랩 공용 PC 셋업) 설치기의 전체 프리셋을 쓰세요.
초심자가 한 번에 31개를 다 받으면 뭐가 왜 로드됐는지 파악이 어려우니, 필요한 것만
골라 담는 2단계 방식을 먼저 권장합니다. 그래도 전체가 필요하면:

```
python install/install.py --preset all --apply
```

**설치기(Python)를 쓸 수 없는 환경이라면**, 폴더 복사가 곧 설치이므로 직접 복사해도
됩니다. 단, 이 경우 **의존성(예: `manuscript-pipeline`은 `academic-term-rules`가
있어야 제대로 동작)을 직접 챙겨야** 합니다.

```powershell
# 개별 스킬 하나 (Windows) — 의존성은 본인이 확인
Copy-Item -Recurse "E:\sci-toolkit\skills\primer-design" "$env:USERPROFILE\.claude\skills\primer-design"
```

```bash
# 개별 스킬 하나 (macOS/Linux)
cp -r /Volumes/USB/sci-toolkit/skills/publication-figures ~/.claude/skills/publication-figures
```

설치 후에는 새 세션에서 스킬 목록에 잘 잡히는지 한 번 확인하고, 안 쓰는 스킬은 나중에
폴더째 지우면 됩니다 (다른 스킬에 영향 없음 — 스킬은 서로 독립적입니다).
어떤 스킬이 무엇을 필요로 하는지는 `config/catalog.json` 의 `requires` 항목에 있습니다.

---

## 막히면 (Troubleshooting)

- 스킬이 인식이 안 되면: 복사 경로가 `~/.claude/skills/<스킬이름>/SKILL.md` 구조가
  맞는지 확인 (하위 폴더가 한 겹 더 감싸져 있지 않은지).
- 특정 스킬이 API 키를 요구하면: 그 스킬의 `SKILL.md`에 필요한 키/무료 대안이 적혀
  있습니다. 없어도 되는 스킬부터 먼저 써보세요.
- 그래도 안 되면: 랩 관리자(배포판 관리자)에게 문의하세요. 이 배포판은 개인정보가
  없는 공용 버전이므로, 개인 설정 문제는 랩 공용 문서가 아니라 본인 Claude Code
  환경 설정을 먼저 점검하는 게 빠릅니다.
