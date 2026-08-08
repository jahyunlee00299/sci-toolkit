# sci-toolkit

**연구실 공용 Claude Code 스킬셋** — 논문 검색·원고 작성·그림 제작·데이터 분석을
AI가 일관된 절차로 처리하도록 만드는 지침서 모음입니다. 각 절차 끝에는 **검증 게이트**가
붙어 있어, "돌아갔다"가 아니라 "결과가 맞다"를 확인한 뒤에 끝납니다.

A shared Claude Code skillset for lab work — literature search, manuscript writing,
figure production, data analysis. Each route ends in a **verification gate**: the
artifact is not done until the gate passes, and gates are scripts, not advice.

```
스킬 27종 · 회귀 테스트 16종 · 안전 가드 7종
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
| Word/PDF/PPT/Excel 을 다루고 싶다 | 그냥 말하면 됩니다 — Claude Code 기본 기능이 처리합니다. 원고 QC 도구는 [모듈 목록](#-word--pdf--ppt--excel) 참조 |
| 쓰다가 불편한 걸 발견했다 | [docs/11_불편한점_남기기](docs/11_불편한점_남기기.md) — 그냥 말하면 기록됩니다 |
| **Claude Code가 아니라 Codex를 쓴다** | [CODEX.md](CODEX.md) — 훅이 안 도는 환경이라 지켜야 할 것이 다릅니다 |

---

## sci-toolkit이 뭔가요? / What is sci-toolkit?

`skills/` 폴더 하나하나가 **"이럴 때 이렇게 해라"는 지침서**입니다(필요하면 보조
스크립트가 딸려 옵니다). 코드가 아니라 문서라서, Claude Code가 대화 맥락을 보고
알아서 골라 읽습니다 — 직접 실행할 필요가 없습니다.

## 무엇이 들어 있나 (스킬 27종)

| 분야 | 스킬 |
|---|---|
| **논문 검색·작성** | `research-search`(진입점) · `research-lookup` · `openalex-database` · `pubmed-database` · `biorxiv-database` · `paper-extract` · `literature-review` · `research-ideation` · `manuscript-pipeline` · `academic-term-rules` · `endnote-citation-injection` |
| **분자생물학·실험** | `primer-design` · `experiment-hub` |
| **Figure** | `publication-figures` · `markdown-mermaid-writing` · `generate-image` |
| **데이터·통계** | `stats-workflow` · `statsmodels` · `lab-data-analysis` · `conda-env-manager` · `get-available-resources` |
| **문서 변환** | `markitdown`(PDF·docx·xlsx·이미지OCR → Markdown) · `journal-presentation-maker` |
| **검증·개발 규율** | `scientific-validation` · `code-quality` · `git-workflow-manager` · `skill-developer` |

> **Word · PDF · PPT · Excel** 은 스킬 없이 그냥 됩니다 — Claude Code 기본 기능이
> 처리합니다. 원고 QC 도구 7종은 `skills/manuscript-pipeline/scripts/` 에 있습니다.

## 쓰는 법

그냥 평소처럼 말하면 됩니다.

```
"이 주제로 논문 찾아줘"     "primer 설계해줘"      "이 데이터 통계 뭐 써야 해?"
"figure 다시 그려줘"        "원고 표기 검사해줘"    "이 결과 말이 되는지 봐줘"
```

설치는 필요한 것만 골라서:

```bash
python install/install.py --list                      # 뭐가 있는지 보기
python install/install.py --preset paper-writing --apply
python doctor.py                                      # PASS 나오면 준비 끝
```

---

<details>
<summary><b>📄 Word · PDF · PPT · Excel — 왜 스킬 폴더가 안 보이나</b></summary>

<br>

문서 작업은 **그냥 됩니다.** "이 워드 파일 고쳐줘"라고 하면 평소처럼 동작합니다.
해당 스킬을 저장소에 넣지 않은 건 기능이 없어서가 아니라, **재배포가 금지된
Anthropic 소유 자산**이기 때문입니다 ([docs/12](docs/12_문서스킬_직접_준비하기.md)).

**PDF·문서를 텍스트로 읽어야 할 때는 `markitdown`** 을 쓰세요. PDF·docx·pptx·xlsx·
이미지(OCR)를 Markdown으로 바꿔 주며, `paper-extract` 와 `journal-presentation-maker`
가 논문 PDF를 읽을 때 실제로 이 경로를 씁니다.

원고 QC·편집 도구 7종은 랩에서 직접 만든 것이라 그대로 들어 있습니다:

```bash
# 추적변경이 있으면 python-docx 텍스트는 틀린다 — 넣기 전에 반드시 확인
python skills/manuscript-pipeline/scripts/manuscript_text.py MANUSCRIPT.docx --count-only
python skills/manuscript-pipeline/scripts/figure_caption_check.py MANUSCRIPT.docx
python skills/manuscript-pipeline/scripts/word_com_ops.py --help    # Windows + Word
```

</details>

<details>
<summary><b>🔑 논문 원문 받기 — OA 우선, 기관 구독은 교내망에서</b></summary>

<br>

`scripts/ref_fetch.py` 는 **공개(OA) 경로로만** 받습니다. CrossRef·OpenAlex·Unpaywall을
교차검증해 OA PDF를 모으고, 페이월 논문은 우회하지 않고 `oa_status: closed` 로 남깁니다.

```bash
python scripts/ref_fetch.py --doi 10.1016/j.example.2026.01.001 --download
```

**기관 구독 논문(고려대 도서관 등)** 은 학교 인증이 필요해 이 스크립트가 대신
받아주지 않습니다. 다음 순서로 직접 받으세요.

1. `refs_report.json` 에서 `oa_status: closed` 인 DOI를 추린다
2. **교내망**이거나 도서관 원격접속(EZproxy 등)에 로그인한 상태에서 그 DOI를 연다
3. 받은 PDF를 작업 폴더에 두고 파일 경로로 알려준다

> ⚠️ **외부망에서는 접근이 막힙니다 — 읽고 시작하세요**
> - 교외에서 기관 구독 논문 링크를 그대로 열면 페이월 화면만 나옵니다. 오류가 아니라
>   인증이 없는 상태입니다. **먼저 도서관 원격접속에 로그인**하세요.
> - 원격접속 세션은 시간이 지나면 끊깁니다. 여러 편을 받다가 중간부터 실패하면
>   대체로 세션 만료이니 재로그인 후 이어서 받으세요.
> - **자동 대량 다운로드 금지.** 짧은 시간에 여러 편을 긁으면 출판사가 기관 IP 전체를
>   차단할 수 있고, 그 피해는 연구실 전체가 봅니다. 필요한 편만 사람이 직접 받으세요.
> - 이 툴킷은 **페이월 우회·스크래핑을 하지 않습니다**(`ref_fetch.py` 설계 원칙).
>   AI에게 "우회해서 받아줘"라고 시키지 마세요.

</details>

<details>
<summary><b>🧰 패키지 구성 — 무엇이 무엇을 하는가</b></summary>

<br>

| 항목 | 용도 |
|---|---|
| `AGENTS.md` | **AI가 따르는 운영 규칙.** §0 라우팅 표가 "어떤 요청 → 어떤 스킬 → 어떤 검증"을 정한다 |
| `install/install.py` | 선택 설치 — 프리셋/개별 스킬 단위, 의존 스킬 자동 동반, 기존 파일 보존 병합 |
| `config/catalog.json` | 스킬 카탈로그 SSOT (카테고리·의존성·용량·프리셋) |
| `hooks/` | 안전 가드 7종 — 시크릿·강제삭제·위험한 git(fork upstream 포함)·클라우드 재귀스캔 + Windows 환경불일치 3종 |
| `scripts/` | 연구 보조 도구 (HPLC 파서, primer 점검, JCR 검증, `ref_fetch.py` 등) + 외부 연동 커넥터 |
| `docs/` | 초심자 문서 13종 (시작하기 → 설치 → API/MCP → 토큰·비용 → … → 전체 워크플로우 지도) |
| `tests/` | 회귀 테스트 16종 (시크릿·연구마커, 참조 실존, 라우팅 정합, 비파괴 설치, 능력 소실, 훅 양방향). `doctor.py` 가 전부 자동 실행 |
| `doctor.py` | 무결성·환경 점검. `PASS` 가 나와야 준비된 것 |
| `evals/` | 라우팅이 **실제로 발동하는지** headless 측정 (느리고 비용 발생 — 수동 실행) |
| `scripts/capability_diff.py` | 스킬을 고쳐 쓴 뒤 **기능이 조용히 빠지지 않았는지** 구조적으로 대조 |
| `scripts/feedback_log.py` | 불편·오류 기록 (계정·토큰 불필요) |
| `SHA256SUMS` | 전체 파일 해시 — 복사·전송 후 손상 검증 |

</details>

<details>
<summary><b>⚙️ 설치 상세 — 어디에, 어떻게</b></summary>

<br>

스킬은 그냥 디렉토리입니다. 등록 절차가 따로 없습니다.

```bash
python install/install.py --list                          # 카탈로그·프리셋
python install/install.py --preset paper-writing --apply  # 프리셋 단위
python install/install.py --skills primer-design --apply  # 개별
python install/install.py --skills docx --dest ./my-skills --apply
```

- `--dest` 를 생략하면 환경을 감지해 정합니다(Claude Code면 `~/.claude/skills`).
  **어디에 넣는지 출력하니 확인하세요.**
- **기존 파일을 지우지 않습니다.** 같은 이름은 갱신하고, 대상에만 있던 파일은 남깁니다.
  완전 교체가 필요하면 `--force` 를 명시하세요.
- 폴더 하나만 복사해도 동작합니다 — 전체를 넣을 필요는 없습니다.

**베이스 환경**: Claude Code(구독). 대부분의 스킬이 API 키 없이 동작하며, 일부 외부 DB
조회 스킬만 무료 API 또는 선택적 키를 씁니다 — 각 `SKILL.md` 에 명시돼 있습니다.

Codex 등 다른 에이전트를 쓴다면 [CODEX.md](CODEX.md) 를 먼저 읽으세요.

</details>

---

<details>
<summary><b>🔒 안전 공지 — 무엇이 들어 있지 않은가</b></summary>

<br>

- **개인정보·계정정보·연구비 정보가 들어 있지 않습니다.** `.distignore` 로 패키징
  단계에서 자동 제외되고, `doctor.py` 의 SENTINEL 스캔이 시크릿·개인식별정보·
  미공개 연구 마커를 기계 검사합니다.
- 스킬을 직접 추가·수정할 때 개인 토큰·이메일·연구비 번호를 넣지 마세요.
  넣으면 `doctor.py` 가 FAIL 로 잡습니다.
- 랩 밖으로 재배포하기 전에는 관리자에게 확인하세요.
- **라이선스**: 저장소 전체는 MIT([LICENSE](LICENSE))이지만 스킬마다 자체 라이선스가
  있으니 재배포 전 각 `SKILL.md` 앞머리를 확인하세요 ([NOTICE.md](NOTICE.md)).
  `docx`·`pdf`·`pptx`·`xlsx` 는 Anthropic 소유라 이 저장소에 포함되지 않습니다 —
  다만 문서 작업 자체는 Claude Code 기본 기능으로 그대로 됩니다.

This distribution contains no personal data, account credentials, or funding
information — excluded at packaging time via `.distignore`, and machine-checked by
`doctor.py`'s SENTINEL scan. If you extend it, never add personal tokens, emails, or
grant numbers. Check with the lab admin before redistributing outside the lab.

</details>
