# 13. 토큰 발급을 Chrome으로 편하게 받기 (Claude Code + Chrome 확장)

> 한 줄 요약: **Claude가 정확한 설정 화면까지는 데려다주지만, "생성" 버튼 클릭과 값 복사는
> 항상 사용자 본인이 합니다.** 토큰 값은 Claude가 절대 대신 읽거나 저장하지 않습니다.

`docs/07_노션_연동_가이드.md`, `docs/08_아사나_연동_가이드.md`는 메뉴를 하나하나 손으로
찾아가는 방법을 설명합니다. Claude Code에 Chrome MCP 연결이 되어 있다면, 메뉴를 찾는 수고를
줄일 수 있습니다 — 다만 **어디까지 자동화하고 어디서부터는 사람이 직접 해야 하는지**가 중요합니다.

---

## 1. 원칙 — 왜 토큰 값은 Claude가 보지 않는가

- GitHub/Notion/Asana 토큰은 생성 직후 **딱 한 번만** 화면에 보여주고 이후엔 다시 볼 수 없습니다.
- Claude가 화면을 읽어서 그 값을 채팅으로 다시 말하면, **그 순간 토큰이 대화 기록에 남습니다**
  — `docs/05_외부서비스_연동.md` §2가 금지하는 "채팅창에 토큰 붙여넣기"와 결과적으로 같습니다.
- "토큰 생성" 버튼을 누르는 것도 **계정 설정을 바꾸는 동작**이라, Claude가 임의로 눌러도 되는
  종류의 일이 아닙니다.
- **로그인된 계정이 어디 것인지는 Claude가 판단할 수 없습니다.** 화면이 로그인 상태인지는
  스크린샷으로 보이지만, 그 계정이 "나 개인 계정"인지 "랩 공용/마스터 계정"인지는 화면만 봐선
  구분이 안 됩니다 — 이 판단은 항상 본인 몫입니다. 다른 PC(집컴 등)에서 처음 진행할 때 이미
  마스터 계정으로 로그인돼 있는 브라우저를 그대로 쓰면, 그 PC 하나가 마스터 계정 권한 전체를
  들고 있는 토큰을 발급받게 됩니다 — §3 1단계에서 반드시 먼저 확인하세요. GitHub만의
  문제가 아닙니다 — **Notion·Asana는 "계정"이 아니라 "어느 워크스페이스/조직에 들어가
  있는지"** 가 기준이라, 계정은 본인 것이어도 랩 공용 워크스페이스/조직에 들어가 있는
  상태로 발급하면 같은 문제가 생깁니다 — §2 표의 "계정 확인 포인트" 참고.

그래서 역할을 이렇게 나눕니다.

| 단계 | 누가 하나 |
|---|---|
| **로그인된 계정이 본인 개인 계정인지 확인** | **본인** (Claude는 판단 불가) |
| 로그인 상태 확인, 정확한 설정 페이지로 이동 | Claude (Chrome MCP) |
| 스코프/권한 체크박스가 의도대로 선택됐는지 확인 | Claude가 스크린샷으로 확인 + 안내 |
| **"생성(Generate/Create)" 버튼 클릭** | **본인** |
| **토큰 값 복사** | **본인** |
| 값을 `credentials.json`에 등록 | 본인 (`register_token.py` 실행 — 붙여넣기 한 번, 화면엔 안 보임) |
| 등록이 됐는지 확인 (값은 마스킹) | Claude (`_credentials.py`) |

---

## 2. 서비스별 바로가기 URL

| 서비스 | 바로가기 URL | 비고 | 계정 확인 포인트 |
|---|---|---|---|
| GitHub (classic PAT) | `https://github.com/settings/tokens/new?scopes=repo&description=sci-toolkit` | `scopes` 파라미터로 스코프 사전 체크 가능. 저장소 접근만 필요하면 `repo` 로 충분 | 우측 상단 아바타 = 본인 GitHub 아이디인지 |
| GitHub (fine-grained, 더 안전) | `https://github.com/settings/personal-access-tokens/new` | 저장소를 하나씩 골라 최소 권한으로 발급(권장), 다만 스코프 사전 채움은 안 됨 | 위와 동일 |
| Notion | `https://www.notion.so/my-integrations/new` | 생성 후 **대상 데이터베이스에 공유(Connections)** 하는 절차가 별도로 필요 — `docs/07` §3 | 화면 상단의 **워크스페이스 이름**이 본인 개인 워크스페이스인지(랩 공용 워크스페이스에서 만들면 그 워크스페이스 소속 통합(integration)이 됨 — 랩 공용 용도라면 의도한 것인지 재확인) |
| Asana | `https://app.asana.com/0/developer-console` | "새 개인 액세스 토큰 만들기" 버튼이 바로 보이는 화면 | 좌측 상단/프로필 아이콘의 **조직(organization) 이름**이 본인이 속한 조직이 맞는지 — Asana는 조직 전환이 쉬워서 다른 조직에 들어가 있는 채로 진행하기 쉬움 |
| Gmail (앱 비밀번호) | `https://myaccount.google.com/apppasswords` | 2단계 인증이 켜져 있어야 메뉴가 보임. 로그인 비밀번호가 아니라 **앱 비밀번호**를 새로 발급 — §5 참고 | 우측 상단 프로필이 본인 Gmail 계정인지(구글은 다중 로그인이 흔해 엉뚱한 계정 탭일 수 있음) |

> ⚠️ **처음 쓰는 PC(집컴 등)라면 URL을 열기 전에** 브라우저가 어느 계정으로 로그인돼
> 있는지부터 확인하세요 — §1 참고. 마스터/공용 계정이 로그인된 채로 위 URL을 열면
> 그 계정(또는 그 계정이 속한 워크스페이스/조직) 이름으로 토큰이 발급됩니다. Notion·
> Asana는 "계정 자체"가 아니라 **어느 워크스페이스/조직에 들어가 있는 상태인지**가
> 관건이라 GitHub보다 놓치기 쉽습니다 — 위 표의 "계정 확인 포인트" 열 참고.

이 표는 **"토큰 하나로 끝나는" 서비스**(GitHub/Notion/Asana/Gmail 앱 비밀번호)만 다룹니다.
Google Calendar/Drive는 PAT가 아니라 OAuth 로그인 흐름(동의 화면)이라 이 표와 완전히
다른 절차이며, 이 문서가 다루는 범위 밖입니다 — `docs/05_외부서비스_연동.md` §4-4 및
`scripts/connectors/README.md` "캘린더 / 공유 스프레드시트" 절을 따르세요(커넥터 자체가
아직 없어 지금은 MCP 연결 버튼으로 처리).

---

## 3. 진행 순서 (서비스 하나 기준)

1. "OO 토큰 받는 거 도와줘" 라고 요청합니다.
2. Claude가 위 표의 URL로 새 탭을 열고, 로그인된 상태인지 스크린샷으로 확인합니다.
   - 로그인이 안 돼 있으면 Claude는 로그인하지 않고 **직접 로그인해달라고 요청**합니다
     (자격증명 입력은 금지 사항입니다).
   - **로그인이 이미 돼 있다면, 화면 우측 상단(또는 계정 메뉴)의 계정명·아바타를 보고
     "이게 내 개인 계정이 맞는지" 반드시 본인이 확인합니다.** Notion·Asana는 여기서
     한 단계 더 —  **워크스페이스/조직도 본인이 의도한 곳인지** 같이 확인합니다(같은
     계정으로 로그인돼 있어도 랩 공용 워크스페이스/조직에 들어가 있을 수 있음). 처음
     쓰는 PC(집컴, 다른 사람 노트북 등)일수록 랩 공용/마스터 계정이 이미 로그인돼
     있을 위험이 큽니다 — 그 상태로 토큰을 만들면 해당 PC가 마스터 계정(또는 공용
     워크스페이스) 권한을 그대로 들고 있게 됩니다. 계정/워크스페이스가 다르면 전환하거나
     로그아웃 후 본인 것으로 다시 로그인한 뒤 진행하세요.
3. Claude가 화면의 이름/스코프 입력란을 확인하고 "이대로 만들면 됩니다"라고 안내합니다
   (텍스트 입력까지는 Claude가 채워줄 수 있습니다 — 이름·스코프 선택은 비밀값이 아니므로).
4. **"생성" 버튼은 본인이 클릭**합니다.
5. 화면에 뜬 토큰 값을 **본인이 직접 복사**해서, 터미널에서 (Claude에게 시키지 말고
   직접, 예: Claude Code라면 `!` 로 시작하는 명령으로) 실행합니다:
   ```bash
   python scripts/connectors/register_token.py github   # notion / asana 는 서비스명만 바꿔서
   python scripts/connectors/register_token.py notion
   python scripts/connectors/register_token.py asana
   ```
   숨김 입력 프롬프트가 뜨면 값을 붙여넣고 Enter — **입력이 화면에 보이지 않고**,
   `config/credentials.json`의 해당 필드에 바로 기록됩니다. Claude는 이 값을 읽지도,
   대화에 다시 말하지도 않습니다 — 키보드에서 파일로 직행하고 끝입니다.
   (환경변수를 직접 쓰고 싶다면 기존처럼 `export SCITK_GITHUB_TOKEN='...'` 도 여전히 됩니다.)
6. 확인:
   ```bash
   python scripts/connectors/_credentials.py
   ```
   값이 마스킹된 채로 "설정됨"이라고 나오면 끝입니다.

---

## 5. Gmail 앱 비밀번호는 절차가 조금 다름

Gmail(개인 메일)은 "토큰 생성" 화면이 아니라 **앱 비밀번호** 발급 화면입니다. 위 §2
바로가기(`myaccount.google.com/apppasswords`)로 들어가면 되지만, 두 가지가 다릅니다.

- **2단계 인증이 꺼져 있으면 메뉴 자체가 안 보입니다.** 먼저 Google 계정의 2단계 인증을
  켠 뒤 다시 들어가야 합니다 — 이 설정도 본인이 직접 합니다.
- **등록은 `--account` 로 어느 메일인지 지정합니다.** 개인 메일(Gmail)과 업무/조직
  메일은 `config/credentials.json` 안에서 별도 경로(`mail.accounts.personal.password`
  / `mail.accounts.work.password`)를 쓰기 때문입니다:
  ```bash
  python scripts/connectors/register_token.py mail --account personal   # Gmail
  python scripts/connectors/register_token.py mail --account work       # 업무/조직 메일
  ```
  (`--account` 를 생략하면 기본값은 `work`. 환경변수 방식이 더 간단하면
  `export SCITK_MAIL_PERSONAL_PASSWORD='...'` / `SCITK_MAIL_WORK_PASSWORD` 도
  여전히 됩니다.)
- 업무/조직 메일의 IMAP·SMTP 서버 값(`imap_host`, `smtp_host` 등)은 토큰이 아니라
  소속 기관 IT 안내를 따라 `config/credentials.json`에 직접 채워 넣는 값입니다 —
  비밀값이 아니므로 Claude가 채워도 괜찮습니다.

---

## 4. 자주 막히는 지점 (Windows)

실제로 처음 해보면 아래 세 가지에서 거의 항상 걸립니다 — 미리 알아두세요.

- **`python` 명령이 안 먹는다** ("용어가 인식되지 않습니다"): Windows에 Python을 설치할 때
  "Add to PATH"를 체크하지 않았거나, 아나콘다처럼 기본으로 PATH에 안 잡히는 배포판을
  쓰는 경우 흔합니다. 이럴 땐 `python` 대신 **`py`** 를 먼저 시도하세요 (Windows Python
  설치 시 거의 항상 같이 깔리는 런처라 PATH에 있을 확률이 높습니다):
  ```
  py scripts\connectors\register_token.py github
  ```
  그래도 안 되면 설치 경로를 찾아 전체 경로로 실행하세요 (`where python` 또는
  파일 탐색기에서 Python 설치 폴더 확인).
- **Claude가 메모장/터미널을 대신 열어주려다 실패할 수 있다**: Claude가 `notepad`/
  `explorer` 실행을 먼저 시도하긴 하지만, Claude Code가 실행하는 명령은 화면(데스크톱)
  과 세션이 분리된 환경이 많아 실제로는 안 뜨는 경우가 흔합니다. 잠시 기다려도 창이
  안 보이면 Claude가 "안 열렸다"고 알려주고, 그 즉시 정확한 파일 경로(또는 그 파일이
  들어있는 폴더까지 미리 열어서)를 알려줄 겁니다 — 그 경로를 파일 탐색기 주소창에
  붙여넣거나, Windows 키 → `cmd` 입력 → Enter 로 직접 여세요.
- **파일을 잘못 열기 쉽다**: 컴퓨터에 `credentials.json`이나 `secrets.json` 같은 이름의
  파일이 여러 개(백업, 다른 프로젝트, 예전 버전) 있을 수 있습니다. 검색 대신
  **Claude가 알려준 경로를 파일 탐색기 주소창에 그대로 붙여넣어** 정확한 파일을 여세요.
  저장한 뒤에는 값을 눈으로 재확인하지 말고, `register_token.py`가 등록 직후 보여주는
  마스킹 확인 메시지(`[등록됨] ... = xx****...`)로만 확인하세요.

## 5. 한 줄 요약

- Claude는 **길안내**(정확한 URL로 이동 + 화면 확인)까지만, **생성 버튼과 값 복사는 항상 본인**
- 토큰 값은 Claude가 화면에서 읽어 다시 말하지 않습니다 — 채팅 기록에 남기지 않기 위해서입니다
- **로그인된 계정이 본인 개인 계정인지는 Claude가 판단 못 함 — 매번 본인이 먼저 확인**
  (특히 처음 쓰는 PC)
- 서비스별 바로가기는 위 §2 표 참고, Google Calendar/Drive는 별도 OAuth 흐름
