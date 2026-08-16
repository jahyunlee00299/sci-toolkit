# 외부 서비스 연동 스크립트 (connectors)

메일·GitHub·Asana·Notion·캘린더·공유 시트를 명령줄에서 다루는 커넥터 모음입니다.
설계 원칙은 [`docs/05_외부서비스_연동.md`](../../docs/05_외부서비스_연동.md) 및
[`AGENTS.md §9`](../../AGENTS.md) 와 같습니다 — **읽기는 자유, 나가는 건 초안까지만.**

> ⭐ **기본 정책 — MCP 지양**: 아래 여섯 서비스는 **MCP(앱 연결 버튼)로 연결하지 말고
> 이 커넥터를 쓰세요.** MCP는 계정 전체에 상시로 열리는 통로지만, 커넥터는 실행하는 그
> 명령이 요청한 범위만 건드립니다. 커넥터로 전환했다면 해당 서비스의 MCP 연결은 앱
> 설정에서 **바로 해제**하세요 (계정 설정 변경이라 본인이 직접 하는 동작입니다). MCP는
> 브라우저 탐색처럼 API로 대체할 수 없는 작업에만, 최후의 수단으로 남겨두세요.
>
> 260816 부로 캘린더·공유 시트에도 커넥터가 생겨 **"커넥터 없는 서비스" 예외는
> 없어졌습니다.** 구글 두 서비스는 최초 1회 OAuth 동의가 필요하지만(§5·§6),
> 그 뒤로는 나머지와 똑같이 stdlib 만으로 돕니다.

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

## 5. 캘린더 — `calendar_connector.py` (read-first)

```bash
# 읽기 (안전)
python calendar_connector.py calendars                    # 접근 가능한 캘린더 목록
python calendar_connector.py agenda --days 7              # 날짜별로 묶어 보기
python calendar_connector.py list --calendar primary --days 30

# 일정 생성 = --write. 참석자를 넣으면 초대장이 나가므로 경고가 먼저 뜬다.
python calendar_connector.py add-event --summary "미팅"     --start 2026-08-20T14:00:00 --end 2026-08-20T15:00:00 --write
```
- 날짜만 주면(`2026-08-20`) 종일 일정, 시각까지 주면 시간 일정.
- `--attendee` 는 **outward** — 남의 캘린더에 초대장이 갑니다. dry-run 이 몇 명에게
  가는지 먼저 알려줍니다.
- **수정·삭제 서브커맨드는 없습니다.** 남의 일정을 지우는 실수를 이 도구로 낼 수
  없어야 합니다.

## 6. 공유 시트 — `sheets_connector.py` (append-only)

```bash
# 읽기 (안전)
python sheets_connector.py info --sheet <ID>              # 탭 목록·크기
python sheets_connector.py read --sheet <ID> --range "Sheet1!A1:D20"

# 행 추가 = --write. 기존 셀은 절대 건드리지 않습니다.
python sheets_connector.py append --sheet <ID> --range "Sheet1!A:D"     --row 'a,"b,c",d' --write
```
- 시트 ID 는 URL 에서: `docs.google.com/spreadsheets/d/<ID>/edit`
- `--row` 는 CSV 규칙 — 값 안에 쉼표가 있으면 `"..."` 로 감쌉니다.
- **`update`/`delete` 는 제공하지 않습니다.** 공유 시트의 기존 셀을 덮어쓰면 남이
  넣은 값이 사라지고 되돌릴 방법이 사실상 없습니다(Notion 커넥터가 additive-only 인
  것과 같은 이유). 기존 값 수정은 사람이 브라우저에서 합니다.

### 구글 인증 — 최초 1회만 브라우저, 그 다음은 자동

다른 커넥터와 달리 구글은 OAuth 라 토큰 발급 단계가 하나 더 있습니다. 다만
**refresh token 을 한 번 받아두면 그 뒤로는 라이브러리 없이 자동 갱신**되므로,
평소 사용은 나머지 커넥터와 똑같습니다(`_google_auth.py`, stdlib 전용).

`config/credentials.json` 의 `google` 항목 두 개를 채웁니다:

| 키 | 무엇 |
|---|---|
| `oauth_client_path` | 구글 클라우드 콘솔에서 받은 OAuth 클라이언트 JSON 경로 |
| `token_cache_path` | 발급된 토큰을 둘 파일 경로 (기본 `~/.sci-toolkit/google_token.json`) |

토큰 파일은 구글 표준 형식(`access_token`·`refresh_token`·`expiry_date`)이면
됩니다 — **이미 다른 도구로 구글 토큰을 만들어 둔 사람은 그 경로를 그대로
가리키면 되고, 새로 발급받을 필요가 없습니다.**

최초 발급은 브라우저 동의가 필요해 이 패키지가 자동화하지 않습니다(동의 화면을
스크립트가 대신 눌러선 안 됩니다). 콘솔에서 OAuth 클라이언트를 만들고 필요한
scope 로 한 번 동의하면 됩니다:

- 캘린더 읽기: `.../auth/calendar.readonly` · 일정 생성까지: `.../auth/calendar.events`
- 시트 읽기: `.../auth/spreadsheets.readonly` · 행 추가까지: `.../auth/spreadsheets`

읽기만 할 거면 readonly scope 만 주세요 — 토큰이 새도 쓰기가 안 됩니다.

설정 확인:
```bash
python scripts/connectors/_google_auth.py     # 토큰 정상이면 마스킹된 값 출력
```


## 안전 요약

| 동작 | 기본 | 실제 실행 조건 |
|---|---|---|
| 읽기(list/read/issues/prs/tasks/search) | 바로 실행 | — |
| 메일 초안 | 초안 저장 | — (발송 아님) |
| 메일 발송 | **거부** | `--send` + 터미널 `SEND` 타이핑 |
| GitHub PR | dry-run | `--write` (+ 항상 draft, upstream 거부) |
| Asana/Notion 쓰기 | dry-run | `--write` |
| 캘린더 일정 생성 | dry-run | `--write` (참석자 있으면 outward 경고 선행) |
| 시트 행 추가 | dry-run | `--write` (추가 전용 — 기존 셀 불가침) |
| 삭제·merge·archive·셀 수정 | **없음** | 제공하지 않음 |

### dry-run 은 토큰 없이 돌아갑니다 (예외 1건)

`--write` 없이 부른 쓰기 명령은 **토큰이 없어도** 전송될 페이로드를 보여줍니다.
토큰을 발급받기 전에 "무엇이 나가는지" 먼저 확인할 수 있습니다.

```bash
# 토큰이 없어도 이건 됩니다 — 페이로드만 출력
python github_connector.py open-pr --repo me/r --head feat --base main --title "..."
```

다만 **dry-run 은 예행연습이 아닙니다.** 페이로드를 보여줄 뿐, 그 요청이 수락될지·
대상이 실존하는지·안전검사를 통과했는지는 말해주지 않습니다. 토큰이 없어 검사를
못 돌린 경우 커넥터가 미리보기에 그 사실을 적습니다 — 아무 말이 없다고 "검사 통과"로
읽지 마세요. (예: `open-pr` 의 fork/upstream 검사는 저장소 조회가 필요해서, 토큰이
없으면 `--write` 시점에 수행됩니다.)

**예외 — `notion_db_connector.py add-row`** 는 `--write` 없이도 토큰을 요구합니다.
이 명령의 미리보기는 속성명·타입을 실제 DB 스키마와 대조해야 의미가 있어서, 대조
없이 만든 페이로드를 보여주면 검증된 것처럼 오해되기 때문입니다.

> 회귀 테스트: `python tests/test_connectors.py` (자격증명·네트워크 불필요).
> `doctor.py` 가 자동 실행합니다.
