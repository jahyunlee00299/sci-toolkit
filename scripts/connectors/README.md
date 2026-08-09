# 외부 서비스 연동 스크립트 (connectors)

메일·GitHub·Asana·Notion 을 명령줄에서 다루는 커넥터 모음입니다.
설계 원칙은 [`docs/05_외부서비스_연동.md`](../../docs/05_외부서비스_연동.md) 및
[`AGENTS.md §9`](../../AGENTS.md) 와 같습니다 — **읽기는 자유, 나가는 건 초안까지만.**

> ⭐ **기본 정책 — MCP 지양**: 아래 네 서비스는 **MCP(앱 연결 버튼)로 연결하지 말고
> 이 커넥터를 쓰세요.** MCP는 계정 전체에 상시로 열리는 통로지만, 커넥터는 실행하는 그
> 명령이 요청한 범위만 건드립니다. 커넥터로 전환했다면 해당 서비스의 MCP 연결은 앱
> 설정에서 **바로 해제**하세요 (계정 설정 변경이라 본인이 직접 하는 동작입니다). MCP는
> 아직 커넥터가 없는 서비스(캘린더·공유 시트, §5 참고 — 임시 방편일 뿐 권장 아님)이거나
> 브라우저 탐색이 꼭 필요한 작업에만, 최후의 수단으로 남겨두세요.

> ⚠️ 이 스크립트들은 **실제 계정을 몰라도 되는 템플릿**입니다. 자격증명은 코드에 없고,
> 실행 시 `config/credentials.json`(또는 환경변수)에서 읽습니다. 실제 키는 배포물·커밋에
> 절대 포함되지 않습니다(`.distignore`/`.gitignore` 제외).

## 0. 준비 — 자격증명

1. `config/credentials.example.json` 을 같은 폴더에 `credentials.json` 으로 복사
2. 본인 계정 정보를 채우기. 실제 키·비밀번호는 `"ENV:이름"` 형태로 두고 환경변수로 주입 권장:
   ```bash
   export SCITK_MAIL_WORK_PASSWORD='...'      # 메일 앱 비밀번호
   export SCITK_GITHUB_TOKEN='...'            # GitHub PAT (최소 권한)
   export SCITK_ASANA_TOKEN='...'
   export SCITK_NOTION_TOKEN='...'
   ```
3. 설정 확인(값은 마스킹되어 출력):
   ```bash
   python scripts/connectors/_credentials.py
   ```

## 1. 메일 — `mail_connector.py` (★ draft-first)

```bash
# 읽기 (안전)
python mail_connector.py list  --account work --n 10
python mail_connector.py read  --account work --uid 1234

# 초안 작성 → 임시보관함(Drafts)에만 저장. 절대 자동 발송 안 함.
python mail_connector.py draft --account work --to a@b.com --subject "제목" --body "내용"
python mail_connector.py reply --account work --uid 1234 --body "답장 내용"

# 실제 발송 = 유일한 경로. --send 플래그 + 터미널에서 'SEND' 타이핑 이중 확인 필요.
python mail_connector.py send  --account work --to a@b.com --subject "제목" --body "내용" --send
```
- `draft`/`reply` 는 SMTP를 아예 호출하지 않습니다 → 발송 불가, 초안 저장만.
- `send` 는 `--send` 없이는 거부되고, 비대화형(파이프/자동화)에서도 거부됩니다.
- 학교/업무 메일 = `--account work`, 개인 = `--account personal`.

## 2. GitHub — `github_connector.py` (read-first, fork-guard)

```bash
# 읽기
python github_connector.py issues --repo owner/name
python github_connector.py prs    --repo owner/name
python github_connector.py repo   --repo owner/name      # fork 여부·upstream 표시

# PR 생성 = 항상 draft, --write 필요. upstream(원본) 대상이면 거부.
python github_connector.py open-pr --repo my-fork/name --head feat --base main \
    --title "..." --body "..." --write
```
- PR은 **항상 draft**로 생성되고, **merge 서브커맨드는 없습니다**.
- 대상 repo가 fork의 원본(upstream)이면 거부 — 내 fork에만 올리세요.

## 3. Asana — `asana_connector.py` (read-first)

```bash
python asana_connector.py me
python asana_connector.py tasks --workspace <gid>
# 할 일 생성 = --write. 남에게 배정(--assignee)이면 외부행동 경고.
python asana_connector.py add-task --workspace <gid> --name "..." --notes "..." --write
# 댓글 (기본 plain, --html 이면 형식 자동검증)
python asana_connector.py add-comment --task <gid> --text "..." --write
# 하위작업 (/tasks/{parent}/subtasks)
python asana_connector.py add-subtask --parent <gid> --name "..." --write
```
- **형식 자동보정**: `--html` 댓글/`--html-notes` 설명은 Asana 규칙을 강제 —
  `<body>` 자동래핑, `<p>` 금지, 줄바꿈 `&#10;`, `→` 거부. 한글은 `ensure_ascii=False`로
  안 깨짐. (예전 "댓글·하위작업 형식 이상" 문제 해결) 자세히 → [`docs/08_아사나_연동_가이드.md`](../../docs/08_아사나_연동_가이드.md)

## 4. Notion — `notion_connector.py` (read-first)

```bash
python notion_connector.py search --query "키워드"
python notion_connector.py page   --id <page_id>
# 페이지에 문단 추가 = --write (추가 전용, 삭제/archive 없음).
python notion_connector.py append --page-id <id> --text "..." --write
```

## 안전 요약

| 동작 | 기본 | 실제 실행 조건 |
|---|---|---|
| 읽기(list/read/issues/prs/tasks/search) | 바로 실행 | — |
| 메일 초안 | 초안 저장 | — (발송 아님) |
| 메일 발송 | **거부** | `--send` + 터미널 `SEND` 타이핑 |
| GitHub PR | dry-run | `--write` (+ 항상 draft, upstream 거부) |
| Asana/Notion 쓰기 | dry-run | `--write` |
| 삭제·merge·archive | **없음** | 제공하지 않음 |

## 캘린더 / 공유 스프레드시트 — 📌 미제공 (향후 추가 가능)

**지금 상태**: Google Calendar·Sheets 는 **스크립트 커넥터가 아직 없습니다.**
표준 라이브러리(urllib)만으로는 구글 OAuth 인증이 어려워, 다른 커넥터(mail/github/asana/
notion)와 달리 stdlib 전용으로 만들 수 없기 때문입니다.

**당장 쓰는 법 (커넥터 없이)**: 데스크톱 앱의 **MCP 연결(버튼)** 로 이미 읽기·일정 등록·
시트 조회가 됩니다. 이 두 서비스는 위 정책의 **유일한 예외**로, 커넥터가 나올 때까지만
MCP를 씁니다 — [`docs/05_외부서비스_연동.md`](../../docs/05_외부서비스_연동.md) §4-4 참고.

**📌 나중에 커넥터를 직접 만들려면 (TODO — 필요할 때 착수)**:
- 라이브러리: `pip install google-api-python-client google-auth-oauthlib`(캘린더) /
  `pip install gspread`(시트) — stdlib 아님, 별도 설치 필요.
- 인증: OAuth 클라이언트 JSON 또는 서비스계정. `config/credentials.json` 의 `google` 항목
  (`oauth_client_path`, `token_cache_path`)이 이미 자리를 잡아뒀으니 그걸 읽어 쓰면 됩니다.
- 지켜야 할 원칙(다른 커넥터와 동일): **읽기는 자유 / 쓰기는 `--write` 게이트 /
  다른 사람 초대·공유시트 값 변경·삭제는 확인(또는 추가·가역 편집만)** — AGENTS.md §9.
- 파일 위치: `scripts/connectors/calendar_connector.py`, `sheets_connector.py` 로 만들어
  `_credentials.py` 를 공유하면 됩니다.
