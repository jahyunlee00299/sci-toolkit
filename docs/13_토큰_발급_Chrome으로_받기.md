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

그래서 역할을 이렇게 나눕니다.

| 단계 | 누가 하나 |
|---|---|
| 로그인 상태 확인, 정확한 설정 페이지로 이동 | Claude (Chrome MCP) |
| 스코프/권한 체크박스가 의도대로 선택됐는지 확인 | Claude가 스크린샷으로 확인 + 안내 |
| **"생성(Generate/Create)" 버튼 클릭** | **본인** |
| **토큰 값 복사** | **본인** |
| 값을 환경변수 또는 `credentials.json`에 등록 | 본인 (터미널/에디터에서 직접) |
| 등록이 됐는지 확인 (값은 마스킹) | Claude (`_credentials.py`) |

---

## 2. 서비스별 바로가기 URL

| 서비스 | 바로가기 URL | 비고 |
|---|---|---|
| GitHub (classic PAT) | `https://github.com/settings/tokens/new?scopes=repo&description=sci-toolkit` | `scopes` 파라미터로 스코프 사전 체크 가능. 저장소 접근만 필요하면 `repo` 로 충분 |
| GitHub (fine-grained, 더 안전) | `https://github.com/settings/personal-access-tokens/new` | 저장소를 하나씩 골라 최소 권한으로 발급(권장), 다만 스코프 사전 채움은 안 됨 |
| Notion | `https://www.notion.so/my-integrations/new` | 생성 후 **대상 데이터베이스에 공유(Connections)** 하는 절차가 별도로 필요 — `docs/07` §3 |
| Asana | `https://app.asana.com/0/developer-console` | "새 개인 액세스 토큰 만들기" 버튼이 바로 보이는 화면 |

Google Calendar/Drive는 PAT가 아니라 OAuth 로그인 흐름(동의 화면)이라 이 표와 다릅니다 —
`docs/05_외부서비스_연동.md` §4-4 및 `scripts/connectors/README.md`를 따르세요.

---

## 3. 진행 순서 (서비스 하나 기준)

1. "OO 토큰 받는 거 도와줘" 라고 요청합니다.
2. Claude가 위 표의 URL로 새 탭을 열고, 로그인된 상태인지 스크린샷으로 확인합니다.
   - 로그인이 안 돼 있으면 Claude는 로그인하지 않고 **직접 로그인해달라고 요청**합니다
     (자격증명 입력은 금지 사항입니다).
3. Claude가 화면의 이름/스코프 입력란을 확인하고 "이대로 만들면 됩니다"라고 안내합니다
   (텍스트 입력까지는 Claude가 채워줄 수 있습니다 — 이름·스코프 선택은 비밀값이 아니므로).
4. **"생성" 버튼은 본인이 클릭**합니다.
5. 화면에 뜬 토큰 값을 **본인이 직접 복사**해서:
   ```bash
   export SCITK_GITHUB_TOKEN='...'   # 예: GitHub
   ```
   또는 `config/credentials.json`의 해당 필드에 붙여넣습니다.
6. 확인:
   ```bash
   python scripts/connectors/_credentials.py
   ```
   값이 마스킹된 채로 "설정됨"이라고 나오면 끝입니다.

---

## 4. 한 줄 요약

- Claude는 **길안내**(정확한 URL로 이동 + 화면 확인)까지만, **생성 버튼과 값 복사는 항상 본인**
- 토큰 값은 Claude가 화면에서 읽어 다시 말하지 않습니다 — 채팅 기록에 남기지 않기 위해서입니다
- 서비스별 바로가기는 위 §2 표 참고, Google Calendar/Drive는 별도 OAuth 흐름
