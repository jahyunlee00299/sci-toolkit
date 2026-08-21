# Changelog

이 파일은 sci-toolkit 배포판의 버전별 변경 이력을 기록합니다.
형식은 [Keep a Changelog](https://keepachangelog.com/) 를 따르며, 버전은 [유의적 버전(SemVer)](https://semver.org/lang/ko/)을 사용합니다.

## [1.2.34] — 2026-08-22

- feat(skills): add debugging-loop — 재현 루프를 가설보다 먼저 세우는 버그 진단 규율 (mattpocock/skills 의 diagnosing-bugs 에서 채택, MIT)
- feat(skills): add test-quality — 통과해도 검증하지 못하는 테스트 3종(구현과 같은 방식의 기대값 재계산·내부 결합·일괄 선작성)과 seam 선정 (mattpocock/skills 의 tdd 에서 채택, MIT)
- feat(code-quality): 리뷰를 Standards / Spec 2축으로 분리 — 축을 가로지르는 재정렬 금지, 비교 기준점 고정, Spec 부재 시 명시 (mattpocock/skills 의 code-review 에서 채택, MIT)
- feat(skills): add `spec-first-development` and `test-first-development` —
  spec/plan-before-code and test-before-implementation discipline, adapted from
  obra/superpowers (MIT, see `NOTICE.md`). Routed from `AGENTS.md` §0.
- feat(skills): add spec-driven-research-dev — 4단계 명세 흐름(specify→plan→tasks→implement),
  github/spec-kit(MIT)에서 적응. 연구코드용으로 재작성(단위·실패정책·수치 출처 SSOT 반영)
- feat(skills): add `analysis-code-testing` — pytest patterns for analysis code
  (known-answer tests, golden-file regression, float tolerances, seeded
  reproducibility). Adapted from wshobson/agents `python-testing-patterns` (MIT);
  web-service patterns (HTTP mocks, retries, token expiry) dropped.
- feat(skills): add `data-quality-checks` — six-dimension structural check on a
  raw table before analysis. Adapted from wshobson/agents
  `data-quality-frameworks` (MIT); Great Expectations/dbt/warehouse tooling
  replaced with pandas so no extra dependency is required.
- docs(AGENTS): route both skills in §0; record upstream attribution in NOTICE.md.

## [1.2.33] — 2026-08-21

- fix(connectors): preserve real newlines in asana add-comment --html

## [1.2.32] — 2026-08-21

- fix(connectors): asana add-comment --html 이 개행을 &#10; 리터럴로 강등시키던 결함 수정 (#4)
  — 실제 LF 보존, 레거시 &#10; 입력 자동 복원, 등록 후 재조회 자체 검증 추가

## [1.2.31] — 2026-08-17

- fix(web-scraping): resolve CI failures from doctor gate

## [1.2.30] — 2026-08-17

- chore: bump version to 1.2.29 for web-scraping skill addition

## [1.2.29] — 2026-08-17

- feat(skills): add web-scraping skill (lab-shared)

## [1.2.28] — 2026-08-16

- feat(connectors): add Google Calendar and Sheets, stdlib-only

## [1.2.27] — 2026-08-16

- fix(skills): replace retired TeamCreate API with role-based delegation

## [1.2.26] — 2026-08-16

- fix(routing): drop connector-silent Notion steering; gate the class

## [1.2.25] — 2026-08-16

- test(connectors): offline regression suite; unify dry-run token gating

## [1.2.24] — 2026-08-16

- docs(office): route office work per-agent; Codex ships its own bundle

## [1.2.23] — 2026-08-16

- docs(codex): correct stale Codex capability claims; install to ~/.codex/skills

## [1.2.22] — 2026-08-13

- docs: sync remaining skill-count references after avoid-ai-writing add

## [1.2.21] — 2026-08-13

- docs: sync QUICKSTART.md skill counts (28->29 shipped, 32->33 cataloged)

## [1.2.20] — 2026-08-13

- fix: normalize avoid-ai-writing to LF, update skill count to 29

## [1.2.19] — 2026-08-13

- feat(skills): add avoid-ai-writing skill

## [1.2.18] — 2026-08-10

- feat(doctor): detect credentials.json / secrets.json divergence

## [1.2.17] — 2026-08-10

- merge: origin/main (token-guide doc updates, unrelated to feedback-log work)

## [1.2.16] — 2026-08-10

- feat(feedback): auto-assign GitHub issues to the finder, not the maintainer

## [1.2.15] — 2026-08-10

- docs: document MCP preview-confirm silent-failure trap + account-wide connector scope

## [1.2.14] — 2026-08-10

- docs: dedupe repeated CHANGELOG entries from post-commit hook firing during rebase conflict resolution

## [1.2.13] — 2026-08-10

- fix: F2 preprint test reports SKIP (not FAIL) when OA host rate-limits every retry

## [1.2.8] — 2026-08-10

- refactor: replace install.py's hardcoded doctor timeout with doctor.py's own constant

## [1.2.7] — 2026-08-10

- feat: hook-wiring integrity gate + auto doctor run after install

## [1.2.6] — 2026-08-10

- feat(connectors): add register_token.py, close the token-onboarding gap

## [1.2.5] — 2026-08-10

- feat: detect whether hooks can actually run before assuming they do

## [1.2.4] — 2026-08-10

- docs: add Chrome-MCP-assisted token issuance guide

## [1.2.3] — 2026-08-10

- feat(connectors): add --sort to notion_db_connector query

## [1.2.2] — 2026-08-10

- feat: auto version-bump on every commit (post-commit hook)

## [1.2.1] — 2026-08-09

- docs: make REST connectors the default over MCP for mail/GitHub/Asana/Notion

## [1.2.0] — 2026-07-23

### Added
- **문서로만 있던 규칙 3종을 실행 가능한 게이트로 전환.** "실수 비용이 낮으니 문서로
  충분하다"고 판단했던 것들인데, 실제로는 전부 기계 검사가 가능했다. 판정 기준을
  **"되돌리기 어려운가" → "규칙으로 적을 수 있는가"** 로 바꿨다:
  - **`scripts/doi_verify.py`** — DOI가 **실재하는지** CrossRef·OpenAlex 양쪽에 물어
    확인한다. 지어낸 DOI(exit 2)·철회 논문·서지 불일치를 잡는다. `AGENTS.md` §8이
    "환각 DOI가 위험하니 교차검증하라"고 지시하면서도 **그 검증을 실행할 도구가 없어**
    AI가 "확인했다"고 말하면 그만이던 자리다. **네트워크 실패는 통과가 아니라
    UNVERIFIED 로 보고**한다("확인 못 함"과 "확인했더니 괜찮음"은 다르다).
  - **`skills/stats-workflow/scripts/assumption_check.py`** — 정규성(n에 따라
    Shapiro-Wilk / D'Agostino)과 등분산(Levene)을 실제로 검정하고, SKILL.md의 결정
    트리대로 **쓸 검정을 지목**한다. `--run` 이면 APA 7판 서식 + 효과크기까지 출력.
    이전에는 SKILL.md 안의 코드 조각일 뿐이라 "가정을 확인했다"가 검증되지 않았다.
  - **`skills/manuscript-pipeline/scripts/body_typo_lint.py`** — `academic-term-rules`
    SKILL.md §12a가 이 파일을 "enforcement side"라고 **명시적으로 가리키는데 존재하지
    않았다.** 단위·표기 오타(`50ul`, `n=3`, `NAD+`)는 AUTO-FIXABLE, 문장부호 붙음은
    REVIEW-ONLY로 분리(약어·URL·소수점 화이트리스트 통과 후에만 사람이 판단).
- **`tests/test_agents_routing.py`, `test_body_typo_lint.py`, `test_doi_verify.py`,
  `test_assumption_check.py`** — 위 게이트들의 회귀 테스트. `doctor.py` 가 **자체
  테스트 4종을 자동 실행**한다(`Toolkit self-tests` 검사). 게이트가 조용히 고장 나면
  그 게이트가 지키던 산출물이 전부 무검증으로 나가기 때문이다.
- **`AGENTS.md` §0 라우팅 표** — "어떤 요청 → 어떤 스킬 → 어떤 검증"을 표로 못박았다.
  이전에는 운영 원칙(§1–7)과 검증 경로(§8)는 있었지만 **진입 지도가 없어** 에이전트가
  스킬을 임의로 골랐다. 각 경로는 게이트로 끝나며, 🔒 표시된 게이트는 스크립트가
  강제한다(눈으로 판단 금지, 통과시키려고 검사를 약화하는 것 금지).
  `CLAUDE.md` 도 이 표를 가장 먼저 읽도록 갱신.
- **`docs/10_전체_워크플로우_지도.md`** — 사람용 구조도. 세 개의 층(규칙 → 스킬 → 검증),
  요청이 들어왔을 때의 실제 흐름, **무엇을 스크립트로 강제하고 무엇을 문서로 안내하는지
  그 기준**("틀렸을 때 되돌리기 어려운가"), AI가 길을 잃었을 때 할 말까지 정리.
- **`docs/09_원격서버에서_쓰기.md`** — 랩 공용 서버·HPC·클라우드에서 쓰는 법.
  VS Code Remote-SSH, SSH+CLI, tmux/nohup으로 접속이 끊겨도 계속 돌리기, 결과 회수,
  SLURM 주의사항, 보안 수칙. 개인 접속정보는 담지 않는다(사용자가 각자 채움).
- **설치 안내에 VS Code 익스텐션 추가** — 기존에는 데스크톱 앱과 터미널만 있었다.
  이제 세 경로를 나란히 설명하고 "당신은 어느 경우인가" 선택 표를 붙였다.
  세 방식이 `~/.claude/skills/` 를 공유한다는 점도 명시.
- **`tests/test_agents_routing.py`** — §0 라우팅 표가 가리키는 스킬·스크립트가 전부
  실존하는지 검사(대조 대상 40개). `doctor.py` 에 배선되어 자동 실행된다.
  표가 없는 것을 가리키면 에이전트는 실패하거나 그럴듯하게 지어내므로, 이 검사가
  문서 중 가장 먼저 깨지면 안 되는 부분을 지킨다.
- **스킬 14종 추가** (21종 → **35종**). 내부 스킬 저장소에서 배포 적합성(PII/사설 인프라
  미포함) 검사를 통과한 것만 선별해 옮겼다:
  - 문서/발표 — `pptx`, `journal-presentation-maker`
  - 그림 — `markdown-mermaid-writing`, `generate-image`
  - 데이터·통계 — `statsmodels`, `conda-env-manager`, `get-available-resources`
  - 실험 — `experiment-hub`
  - 문헌·검색 — `parallel-web`, `perplexity-search`
  - 논문 — `research-grants`
  - 개발 규율 — `code-quality`, `git-workflow-manager`, `skill-developer`
- README에 **배포판 자체 구성**(install/config/hooks/scripts/docs/doctor) 설명 표를 추가.
  기존 README는 이 폴더들을 "빈 스캐폴드"라고 적고 있었으나 실제로는 모두 채워져 있었다.
- **원고 편집·QC 도구 6종** (`docx` 스킬, Windows/Word COM):
  - `word_live_edit.py` — **사용자가 Word로 열어둔 문서를 실시간 편집**한다.
    이미 열린 인스턴스에 붙어 파일 잠금 충돌이 없고, 편집 지점으로 화면이 스크롤된다.
  - `word_com_ops.py` — 추적변경 확정, run 경계를 넘는 find-replace, 캡션 교체,
    표 이동, 그림/표 삽입.
  - `manuscript_text.py` — **추적변경이 있는 docx 의 텍스트 추출**. python-docx 는
    `<w:ins>` 내용을 조용히 누락해 멀쩡한 원고를 "잘린 문장"으로 보이게 만든다.
    이 도구는 pandoc `--track-changes` 경로를 써서 그 착시를 막는다 (MUST 5b).
  - `manuscript_ref_order.py` — Figure/Table 인용 순서 진단. "번호순 위반"을
    인용 누락 / 캡션 없는 유령 인용 / 초안 상태로 **구분해서** 보고한다.
  - `figure_caption_check.py` — 캡션↔그림 정합 QC, `endnote_biblio_check.py` — 서지 결측 검증.
- **`scripts/ref_fetch.py`** — DOI 목록으로 서지정보와 공개(OA) PDF를 수집한다.
  CrossRef 와 OpenAlex **양쪽에서 받아 교차 검증**하고 불일치를 리포트에 남긴다
  (한쪽을 조용히 고르지 않는다). Unpaywall/OpenAlex 로 OA 링크를 해석하며,
  **오픈액세스로 공개된 것만** 받는다. API 키 불필요, `ref_cache_manager.py` 캐시 재사용,
  BibTeX 내보내기 지원.
- **회귀 테스트 2종** (`tests/`) — `test_doctor_sentinel.py`(시크릿 검사 21케이스),
  `test_skill_references.py`(참조 407건). 둘 다 `doctor.py` 에 배선되어 자동 실행된다.

### Fixed
- **배포 시 누락됐던 스크립트 2종 복원** — 내부 저장소와 파일 단위로 대조해 찾았다.
  - `skills/publication-figures/scripts/lab_plot.py` (487줄) — HPLC·kinetic·
    dose-response·BO-surface·Pareto 루틴 플롯. SKILL.md가 이 파일을 참조하는데
    없어서 **"번들 스크립트가 아니다"라고 문서를 고쳤던 것이 오판**이었다.
    실제로는 존재했고 배포 단계에서 빠진 것이다. 데모 데이터의 미공개 연구명만
    일반 당류로 정화한 뒤 복원했고, `--demo` 로 그림 18개가 정상 생성됨을 확인했다.
  - `skills/research-lookup/scripts/manuscript_packet.py` (754줄, PII 없음) —
    DOI/PMID 추출, 증거 가중치, 출판유형 분류 헬퍼.
  > 교훈: 문서가 가리키는 파일이 없을 때 **먼저 "원본에 있는데 빠진 것인지"를
  > 확인해야 한다.** 문서를 고치는 건 원본에도 없다고 확인한 뒤의 선택지다.
- **`NAD⁺` 정정 규칙이 실제 문장을 거의 못 잡던 문제** — `academic-term-rules`
  §12의 `\bNAD\+\b` 는 `+`가 non-word 문자라 `NAD+ regeneration`처럼 뒤에
  공백·구두점이 오면 `\b`가 성립하지 않아 매치되지 않는다(실측). 즉 원고에 흔한
  형태를 전부 놓치고 `NAD+regeneration` 류만 잡던 죽은 규칙이었다. 뒤쪽 `\b`를
  제거하고 `NADP+`를 먼저 치환하도록 순서를 바로잡아 **SKILL.md와 구현 양쪽**을
  수정했다(하이픈 수식어 `NAD+-dependent` 도 §3에 따라 위첨자가 정답이므로
  정정 대상에 포함). 놓치던 6가지 형태를 회귀 테스트에 넣었다.

전수 스캔으로 **죽은 참조 40건을 찾아 전부 해소**했다(사용자가 문서 지시를 따르면
그대로 실패하던 것들). 이제 `tests/test_skill_references.py` 가 참조 407건을 검사하며,
`doctor.py` 가 이 검사를 자동으로 돌린다.

- **존재하지 않는 파일을 실행하라던 지시 28곳** — 가장 심각한 것은
  `paper-extract` 로, 문서가 전적으로 의존하는 `scripts/extract_paper_assets.py` 가
  아예 없어 **스킬 전체가 동작 불능**이었다. 해당 스크립트를 새로 구현해 넣었다
  (PDF/docx → 표 xlsx + 그림 PNG + 본문 md + 추출 리포트). 나머지는
  `research-grants` 21곳, `research-search`·`journal-presentation-maker`·
  `parallel-web`·`publication-figures` 등의 참조를 실존 파일·스킬로 교정.
- **존재하지 않는 스킬을 쓰라던 지시 12종** — `scientific-schematics`,
  `diagram-design`, `gget`, `citation-management`, `hypothesis-generation`,
  `scientific-critical-thinking`, `scientific-writing`, `agent-guardian`,
  `infographics`, `pptx-reviewer` 등. 전부 배포판에 실존하는 스킬로 매핑했다.
- **`pdf` 스킬의 대소문자 깨진 파일 참조 6곳** — 실제 파일은 `reference.md` / `forms.md`
  인데 `REFERENCE.md` / `FORMS.md` 로 참조하고 있었다. 대소문자를 구분하는
  Linux/WSL 환경에서 참조가 실패한다.
- **Windows 콘솔(cp949)에서 첫 출력에 죽던 스크립트 37개** — `doctor.py`,
  `install/install.py` 를 포함해 한글·em-dash 를 출력하는 스크립트가
  `UnicodeEncodeError` 로 즉시 종료됐다. UTF-8 stdout 가드를 넣어 해소
  (`PYTHONIOENCODING=cp949` 로 실측 검증). import 되어 쓰이는 라이브러리 모듈은
  호출자의 stdout 을 바꾸면 안 되므로 제외했다.
- `manuscript_ref_order.py` 를 인자 없이 실행하면 스택트레이스가 나오던 것을
  사용법 안내로 교체.

### Changed
- **기존 스킬 4종을 최신 내부 버전으로 갱신**(정화 후 병합):
  - `academic-term-rules` 417→596행 — 인용 순서 진단(§7c: "인용 누락"과 "순서 오류"는
    다른 문제), 기타 QC 규칙 보강
  - `endnote-citation-injection` 490→784행 — INSERT 전 DOI 선조회로 중복 삽입 방지,
    orphan citation 복구, reference_type 미지정 시 서지가 조용히 깨지는 함정,
    저널명 정규화, 공유 라이브러리 UPDATE 안전 절차
  - `scientific-validation` 157→183행 — "재현 과정이 부작용을 일으키면 안 된다"(Axis 4a):
    가드를 검증한다며 실제 전송 경로를 호출한 실사례, 이름이 없다고 기능이 없는 게 아님
  - `research-lookup` — 라우팅 표 보강
- `config/catalog.json` 을 v1.2.0으로 재생성 — 신규 14종 등록, 전 스킬 `size_kb` 실측
  재측정, 프리셋(`paper-writing`·`literature`·`data-figures`) 보강.
- **`doctor.py` 시크릿 검사(SENTINEL) 강화** — 실제 구멍 2개를 고쳤다:
  1. 파일당 **첫 매치만** 검사하고 있었다. 파일 앞부분이 플레이스홀더면 그 아래
     진짜 키를 통째로 놓친다. 전체 매치 순회로 바꿨고, 바꾼 직후 실제로 이전에
     가려져 있던 파일이 드러났다.
  2. 플레이스홀더 판정이 **서브스트링 포함**이라, 진짜 키 값에 `project1`/`key-here`
     같은 문자열이 우연히 들어가면 그대로 통과했다(적대 검증에서 실증됨).
     값을 단어 단위로 쪼개 **모든 단어가 filler 일 때만** 플레이스홀더로 보도록 바꿨다.
  3. 위 ②를 고치면서 넣은 방어 로직이 **새 구멍 2개를 만들었다**(2차 적대 검증에서
     발각). 숫자로만 된 값(30자리 숫자 등)을 무조건 filler 로 취급해 통과시켰고,
     SCREAMING_SNAKE_CASE 이기만 하면 뒤에 opaque 한 hex 토큰이 붙어 있어도
     환경변수명으로 봐서 통과시켰다. 짧은 숫자(`key1`, `v2`)만 filler 로
     인정하고, 환경변수명은 **모든 구간이 순수 영문 단어일 때만** 인정하도록 좁혔다.
     (구체적인 우회 문자열은 `tests/test_doctor_sentinel.py` 의 MUST_BLOCK 참조 —
     문서에 키 형태 문자열을 남기면 스캐너 자신이 그걸 잡는다.)
  느슨하게 고쳐 통과시킨 게 아님을 증명하려고 `tests/test_doctor_sentinel.py` 에
  양방향 케이스를 넣었다 — 진짜 키 18종(뚫렸던 우회 11종 포함)은 **반드시 차단**,
  플레이스홀더 13종은 **반드시 통과**. 31케이스 전부 통과.

  > 교훈: 오탐을 줄이려고 넣은 예외가 그대로 우회 경로가 된다. 이 검사를 손댈 때는
  > 반드시 위 테스트를 돌리고, 새로 만든 예외마다 "이 예외로 통과하는 진짜 키"를
  > 한 개 고안해 MUST_BLOCK 에 추가하라.
- `SHA256SUMS` 재생성 및 생성 절차를 `scripts/make_checksums.py` 로 고정
  (이전에는 재생성 방법이 패키지 어디에도 없었다).

### Notes
- 배포 부적합으로 **제외한** 내부 스킬: `web-scraping`(캐시에 실명·이메일 다수),
  `system-inspector`(사설 인프라 전용), `kinetic-bo-pipeline`·`cascade-scheme-renderer`
  (미공개 연구 경로 서술이 스킬 본체).

## [1.1.0] — 2026-07-15

### Changed
- **미사용/중복 스킬 6종 제거** (내부 스킬 저장소 2026-07-14 정리 반영):
  `research-assistant`(research-search와 중복·위임루프 소지),
  `academic-paper-reviewer`(adversarial-verifier와 중복),
  `bgpt-paper-search` · `bioservices`(Claude Science 대체 가능/사내 전용),
  `biopython`(순수 라이브러리 래퍼). 스킬 27종 → **21종**.

### Notes
- 스킬 제거에 맞춰 `config/catalog.json` · `SHA256SUMS`를 재생성했다.

## [1.0.0] — 2026-07-03

연구실 내부 배포용 초기 릴리스. 초심자(AI 에이전트를 처음 쓰는 연구실원)를 대상으로,
Claude Code(+Codex) 위에서 곧바로 쓸 수 있는 과학 연구 툴킷을 올인원으로 구성했다.

### Added
- **스킬 27종** — 논문 검색/작성(literature-review, manuscript-pipeline, paper-extract,
  research-search 등), 분자생물학(primer-design, biopython, bioservices), 그림/시각화
  (publication-figures), 통계(stats-workflow), 문서(docx, xlsx, pdf, markitdown),
  학술 검증(academic-paper-reviewer, scholar-evaluation, scientific-validation),
  용어 규칙(academic-term-rules), 학회 포스터(conference-poster) 등.
- **연구 도구 스크립트** — hplc_parser, primer_structure_check, variant_filter,
  jcr_batch_verify, ref_cache_manager, excel_formula_check, fetch_public_vector,
  advanced_wsl.
- **강제 QC lint 도구** — figure_lint(그림), nomenclature_lint · ai_tells_lint ·
  numeric_consistency_check(원고), visual_check(docx). 산출물 회귀 방지 게이트.
- **초심자 문서 5종** — `docs/00_시작하기` · `01_설치와_첫_명령` · `02_API와_MCP` ·
  `03_토큰과_비용` · `04_AI에게_규칙주기`, 그리고 `README` · `QUICKSTART`.
- **일반화된 AGENTS.md** — Claude Code / Codex 공용 에이전트 지침(사적 인프라·개인 경로
  전면 배제).
- **doctor.py** — 배포판 무결성·환경 점검 스크립트(PASS/FAIL 리포트).
- **SHA256SUMS** — 전체 파일 해시(복사 무결성 검증용).
- **.distignore** — 배포 제외 규칙.

### Security
- 미공개 연구명·실명 경로·소속기관·이메일·secrets 참조를 전량 정화하고,
  placeholder로 치환. 적대적 검증 2회 통과.
- dual-PC 위임·금전·개인 MEMORY·`.git`·사적 인프라 관련 자산은 배포판에서 전면 제외.

### Notes
- API 키 없이 **월 구독(Claude Pro/Max, ChatGPT Plus 이상)** 만으로 동작하도록 설계.
- WSL이 필요 없는 코어 구성. 올인원 수동 배포(USB 등)를 기본 전제로 한다.
