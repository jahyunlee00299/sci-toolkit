# sci-toolkit

**연구실 공용 Claude Code 스킬셋.** 논문 검색·원고 작성·그림 제작·데이터 분석을 AI가
매번 같은 절차로 처리하게 하는 지침 모음. 절차 끝마다 **검증 게이트**를 둬 "일단
돌아갔다"가 아니라 "결과가 맞는지 확인" 후 끝냄.

A shared Claude Code skillset for lab work — literature search, manuscript writing,
figure production, data analysis. Every workflow ends in a **verification gate**:
the artifact isn't done until the gate passes, and the gate is a script, not a
suggestion.

```
스킬 35종 · 회귀 테스트 27종 · 안전 가드 7종
python doctor.py   →   11 OK / 0 FAIL
```

개인 계정·개인정보·연구비 정보는 미포함. 미공개 연구 내용은 기계 검사
(`doctor.py` SENTINEL)로 걸러냄.

| 나는… | 여기부터 |
|---|---|
| 처음이라 뭐가 뭔지 모르겠다 | [docs/00_시작하기](docs/00_시작하기.md) |
| 일단 설치부터 | [QUICKSTART.md](QUICKSTART.md) — 필요한 스킬만 골라 설치 |
| 어떻게 돌아가는지 알고 싶다 | [docs/10_전체_워크플로우_지도](docs/10_전체_워크플로우_지도.md) |
| AI가 자꾸 엉뚱하게 한다 | [AGENTS.md](AGENTS.md) §0 라우팅 표 → "§0대로 해줘" |
| Word/PDF/PPT/Excel 을 다루고 싶다 | 그냥 말하면 처리됨 — Claude Code 기본 기능. 원고 QC 도구는 [모듈 목록](#-word--pdf--ppt--excel) 참조 |
| 쓰다가 불편한 걸 발견했다 | [docs/11_불편한점_남기기](docs/11_불편한점_남기기.md) — 말하면 자동 기록 |
| **Claude Code가 아니라 Codex를 쓴다** | [CODEX.md](CODEX.md) — 훅 미작동 환경, 별도 유의사항 |

---

## sci-toolkit이 뭔가요? / What is sci-toolkit?

`skills/` 아래 폴더 하나하나가 "이럴 때는 이렇게" 정리한 지침, 필요하면 보조
스크립트 동반. 코드가 아니라 문서라 Claude Code가 대화 맥락을 보고 알아서
골라 읽음 — 직접 실행 불필요.

## 무엇이 들어 있나 (스킬 35종)

| 분야 | 스킬 |
|---|---|
| **논문 검색·작성** | `research-search`(진입점) · `research-lookup` · `openalex-database` · `pubmed-database` · `biorxiv-database` · `web-scraping` · `paper-extract` · `literature-review` · `research-ideation` · `manuscript-pipeline` · `academic-term-rules` · `endnote-citation-injection` |
| **분자생물학·실험** | `primer-design` · `experiment-hub` |
| **Figure** | `publication-figures` · `markdown-mermaid-writing` · `generate-image` |
| **데이터·통계** | `stats-workflow` · `statsmodels` · `lab-data-analysis` · `conda-env-manager` · `get-available-resources` |
| **문서 변환** | `markitdown`(PDF·docx·xlsx·이미지OCR → Markdown) · `journal-presentation-maker` |
| **검증·개발 규율** | `scientific-validation` · `spec-first-development` · `test-first-development` · `code-quality` · `avoid-ai-writing` · `git-workflow-manager` · `skill-developer` · `token-efficient-routing` · `debugging-loop` · `test-quality` · `spec-driven-research-dev` |

> **Word · PDF · PPT · Excel** 은 스킬 없이 처리 — Claude Code 기본 기능. 원고
> QC 도구 7종은 `skills/manuscript-pipeline/scripts/` 에 위치.

## 쓰는 법

평소 대화하듯 말하면 됨.

```
"이 주제로 논문 찾아줘"     "primer 설계해줘"      "이 데이터 통계 뭐 써야 해?"
"figure 다시 그려줘"        "원고 표기 검사해줘"    "이 결과 말이 되는지 봐줘"
```

설치는 필요한 것만 골라서:

```bash
python install/install.py --list                      # 카탈로그 확인
python install/install.py --preset paper-writing --apply
python doctor.py                                      # PASS 시 준비 완료
```

---

<details>
<summary><b>📄 Word · PDF · PPT · Excel — 왜 스킬 폴더가 안 보이나</b></summary>

<br>

문서 작업은 스킬 없이도 동작. "이 워드 파일 고쳐줘"라고 하면 평소처럼 처리됨.
해당 스킬을 저장소에 안 넣은 이유는 기능 부재가 아니라, 재배포 금지된 Anthropic
소유 자산이기 때문 ([docs/12](docs/12_문서스킬_직접_준비하기.md)).

PDF·문서를 텍스트로 읽어야 할 때는 `markitdown` 사용. PDF·docx·pptx·xlsx·이미지
(OCR)를 Markdown으로 변환하며, `paper-extract`와 `journal-presentation-maker`도
논문 PDF를 읽을 때 이 경로를 탐.

원고 QC·편집 도구 7종은 랩에서 직접 제작한 것이라 그대로 포함:

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

`scripts/ref_fetch.py`는 공개(OA) 경로 전용. CrossRef·OpenAlex·Unpaywall 교차검증으로
OA PDF를 수집하고, 페이월 논문은 우회 없이 `oa_status: closed`로 표시.

```bash
python scripts/ref_fetch.py --doi 10.1016/j.example.2026.01.001 --download
```

**기관 구독 논문(고려대 도서관 등)** 은 학교 인증 필요, 스크립트 대신 불가.
다음 순서로 직접 수령.

1. `refs_report.json` 에서 `oa_status: closed` 인 DOI 추림
2. **교내망**이거나 도서관 원격접속(EZproxy 등) 로그인 상태에서 해당 DOI 접속
3. 받은 PDF를 작업 폴더에 두고 파일 경로로 안내

> ⚠️ **외부망 접근 제한**
> - 교외에서 기관 구독 논문 링크를 그대로 열면 페이월 화면만 표시. 오류가 아니라
>   인증 미완료 상태 — 먼저 도서관 원격접속 로그인 필요.
> - 원격접속 세션은 시간 경과 시 만료. 여러 편 받다가 중간부터 실패하면
>   대개 세션 만료 — 재로그인 후 계속.
> - 자동 대량 다운로드 금지. 짧은 시간에 여러 편을 긁으면 출판사가 기관 IP 전체를
>   차단할 수 있고, 그 피해는 연구실 전체가 부담. 필요한 편만 사람이 직접 수령.
> - 이 툴킷은 페이월 우회·스크래핑 미지원(`ref_fetch.py` 설계 원칙).
>   AI에게 "우회해서 받아줘" 요청 금지.

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
| `docs/` | 초심자 문서 14종 (시작하기 → 설치 → API/MCP → 토큰·비용 → … → 전체 워크플로우 지도 → Chrome으로 토큰받기) |
| `tests/` | 회귀 테스트 27종 (시크릿·연구마커, 참조 실존, 라우팅 정합, 비파괴 설치, 능력 소실, 훅 양방향, 훅 파일 배선, Codex 훅 어댑터, 설치 후 doctor 자동실행, 피드백 채널·정화 게이트, credentials 이원화 감지, 커넥터 dry-run·`--write` 게이트, 서비스·스킬 라우팅 실체 확인, 도입 규율 스킬 조항 실존, 개발 규율 스킬 조항 실존, 명세주도 4단계 계약 실존). `doctor.py` 가 전부 자동 실행 |
| `doctor.py` | 무결성·환경 점검. `PASS` 가 나와야 준비된 것 |
| `evals/` | 라우팅이 **실제로 발동하는지** headless 측정 (느리고 비용 발생 — 수동 실행) |
| `scripts/capability_diff.py` | 스킬을 고쳐 쓴 뒤 **기능이 조용히 빠지지 않았는지** 구조적으로 대조 |
| `scripts/feedback_log.py` | 불편·오류 기록 (계정·토큰 불필요) |
| `SHA256SUMS` | 전체 파일 해시 — 복사·전송 후 손상 검증 |

</details>

<details>
<summary><b>⚙️ 설치 상세 — 어디에, 어떻게</b></summary>

<br>

스킬은 디렉토리 하나에 불과 — 별도 등록 절차 없음.

```bash
python install/install.py --list                          # 카탈로그·프리셋
python install/install.py --preset paper-writing --apply  # 프리셋 단위
python install/install.py --skills primer-design --apply  # 개별
python install/install.py --skills docx --dest ./my-skills --apply
```

- `--dest` 생략 시 환경 감지 후 자동 배치(Claude Code면 `~/.claude/skills`).
  배치 위치는 출력으로 확인 가능.
- 기존 파일 유지. 같은 이름은 갱신, 대상에만 있던 파일은 보존. 완전 교체 필요 시
  `--force` 명시.
- 폴더 하나만 복사해도 동작 — 전체 설치 불필요.

**베이스 환경**: Claude Code(구독). 대부분 스킬은 API 키 불필요, 일부 외부 DB
조회 스킬만 무료 API나 선택적 키 사용. 각 `SKILL.md`에 명시.

Codex 등 다른 에이전트 사용 시 [CODEX.md](CODEX.md) 선독 권장.

</details>

---

<details>
<summary><b>🔒 안전 공지 — 무엇이 들어 있지 않은가</b></summary>

<br>

- 개인정보·계정정보·연구비 정보 미포함. `.distignore`로 패키징 단계에서 자동 제외,
  `doctor.py`의 SENTINEL 스캔이 시크릿·개인식별정보·미공개 연구 마커를 기계 검사.
- 스킬 직접 추가·수정 시 개인 토큰·이메일·연구비 번호 금지 — 포함 시 `doctor.py`
  FAIL 처리.
- 랩 밖 재배포 전 관리자 확인 필수.
- **라이선스**: 저장소 전체는 MIT([LICENSE](LICENSE))지만 스킬별 자체 라이선스
  존재, 재배포 전 각 `SKILL.md` 앞머리 확인 필요 ([NOTICE.md](NOTICE.md)).
  `docx`·`pdf`·`pptx`·`xlsx`는 Anthropic 소유라 이 저장소 미포함. 다만 문서 작업
  자체는 Claude Code 기본 기능으로 동작.

This distribution ships with no personal data, account credentials, or funding
information: `.distignore` strips it at packaging time, and `doctor.py`'s SENTINEL
scan checks for it mechanically. If you extend it, don't add personal tokens, emails,
or grant numbers — and check with the lab admin before redistributing outside the lab.

</details>
