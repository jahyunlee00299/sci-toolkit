#!/usr/bin/env python3
"""scripts/connectors/ 회귀 테스트 — 자격증명 없이, 네트워크 없이.

실행: python tests/test_connectors.py   (exit 0 = 통과)

왜 이 파일이 필요한가
---------------------
커넥터는 이 저장소에서 **바깥으로 나가는 유일한 코드**다(메일 발송, PR 생성,
Asana/Notion 쓰기, 캘린더 초대, 시트 행 추가). 그런데 260816 감사 시점까지 어느 것도 전용 테스트가
없었다 — argparse 표면도, dry-run 페이로드도, --write 게이트도 회귀 안전망 밖에
있었다. 나가는 코드가 조용히 깨지면 되돌리기 어렵다.

무엇을 검사하는가 (전부 오프라인)
--------------------------------
1. 각 커넥터의 argparse 가 실제로 파싱되는가 — 서브커맨드 이름이 문서와 일치하는가
2. 쓰기 명령은 --write 없이 **아무것도 보내지 않는가** (dry-run 격리)
3. --write 가 있으면 실제로 전송 경로를 타는가 (게이트가 반대로 막고 있지 않은가)
4. 토큰이 없을 때의 동작이 명령마다 **의도한 대로** 갈리는가

4번이 이 파일의 핵심이다. 260816 이전에는 github/notion/notion_db 가 --write 없는
미리보기에도 토큰을 요구해서(main() 의 무조건 cred.require) 자격증명 없이는 테스트
자체가 불가능했다. 지금은 asana 와 같은 규칙으로 통일했고, 예외 하나(notion_db
add-row)는 스키마 대조가 미리보기의 존재 이유라 일부러 토큰을 요구한다.

네트워크는 http()/urlopen 을 monkeypatch 해서 차단한다. 테스트가 실수로 실제
요청을 보내면 그 자체를 실패로 잡는다.
"""
import argparse
import importlib.util
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

ROOT = Path(__file__).resolve().parent.parent
CONNECTORS = ROOT / "scripts" / "connectors"

_pass = 0
_fail = 0
_failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global _pass, _fail
    if cond:
        _pass += 1
        print(f"  PASS  {name}")
    else:
        _fail += 1
        _failures.append(name)
        print(f"  FAIL  {name}" + (f" — {detail}" if detail else ""))


def load(module_name: str):
    """커넥터 모듈을 로드한다.

    커넥터는 형제 모듈 `_credentials` 를 평범한 import 로 가져온다 — 스크립트로
    직접 실행될 때를 전제한 구조다. 테스트에서 파일 경로로 로드하면 그 형제를
    못 찾으므로, connectors 디렉토리를 sys.path 에 넣어 준다.
    """
    if str(CONNECTORS) not in sys.path:
        sys.path.insert(0, str(CONNECTORS))
    path = CONNECTORS / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


class NetworkTouched(AssertionError):
    """dry-run 이 네트워크를 건드리면 즉시 실패시킨다."""


def _forbid_network(*a, **k):
    raise NetworkTouched("dry-run 경로가 네트워크를 호출했다")


# ─────────────────────────────────────────────────────────────
print("\n[1] argparse 표면 — 문서에 적힌 서브커맨드가 실제로 파싱되는가")

EXPECTED = {
    "mail_connector":     ["list", "read", "draft", "reply", "send"],
    "github_connector":   ["issues", "prs", "repo", "open-pr"],
    "asana_connector":    ["me", "tasks", "add-task", "add-comment", "add-subtask"],
    "notion_connector":   ["search", "page", "append"],
    "notion_db_connector": ["list-dbs", "schema", "query", "add-row"],
    "calendar_connector": ["calendars", "list", "agenda", "add-event"],
    "sheets_connector":   ["info", "read", "append"],
}

MODS = {}
for name, subcmds in EXPECTED.items():
    try:
        MODS[name] = load(name)
    except Exception as exc:  # noqa: BLE001
        check(f"{name} 로드", False, f"{type(exc).__name__}: {exc}")
        continue
    check(f"{name} 로드", True)

    mod = MODS[name]
    if not hasattr(mod, "build_parser"):
        check(f"{name}.build_parser 존재", False, "함수가 없다")
        continue
    parser = mod.build_parser()
    check(f"{name}.build_parser 존재", isinstance(parser, argparse.ArgumentParser))

    # 서브커맨드 이름을 파서에서 직접 뽑는다 (문서가 아니라 코드가 근거)
    actions = [a for a in parser._actions
               if isinstance(a, argparse._SubParsersAction)]
    got = sorted(actions[0].choices.keys()) if actions else []
    missing = [c for c in subcmds if c not in got]
    check(f"{name} 서브커맨드 {len(subcmds)}종", not missing,
          f"없음: {missing} / 실제: {got}")


# ─────────────────────────────────────────────────────────────
print("\n[2] dry-run 격리 — --write 없으면 네트워크를 건드리지 않는다")

# (모듈, 함수명, args, 미리보기에 반드시 등장해야 하는 문자열)
DRYRUN_CASES = [
    ("github_connector", "cmd_open_pr",
     dict(repo="me/myrepo", head="feat", base="main",
          title="T", body="B", write=False),
     "myrepo"),
    ("notion_connector", "cmd_append",
     dict(page_id="pid-123", text="hello", write=False),
     "hello"),
    ("asana_connector", "cmd_add_task",
     dict(workspace="ws-1", name="task name", notes="n",
          assignee=None, write=False),
     "task name"),
    # 구글 커넥터는 http() 가 아니라 _google_auth 를 통해 나간다 — 아래에서 별도 처리.
]

# 구글 2종: 네트워크 차단 지점이 다르므로(gauth.api_post/api_get) 따로 돌린다.
GOOGLE_DRYRUN = [
    ("calendar_connector", "cmd_add_event",
     dict(calendar="primary", summary="회의", start="2026-08-20T14:00:00",
          end="2026-08-20T15:00:00", description=None, location=None,
          attendee=None, write=False),
     "회의"),
    ("sheets_connector", "cmd_append",
     dict(sheet="SID", range="S1!A:C", row="a,b,c", write=False),
     "a"),
]

for mod_name, fn_name, kwargs, must_contain in DRYRUN_CASES:
    mod = MODS.get(mod_name)
    if mod is None or not hasattr(mod, fn_name):
        check(f"{mod_name}.{fn_name} dry-run", False, "함수 없음")
        continue

    args = argparse.Namespace(**kwargs)
    buf = io.StringIO()
    try:
        # http 를 폭탄으로 바꿔서, 호출되면 테스트가 실패하게 만든다
        with mock.patch.object(mod, "http", _forbid_network):
            with redirect_stdout(buf):
                mod.__dict__[fn_name](args, None)   # token=None
        out = buf.getvalue()
        ok = "[DRY-RUN]" in out and must_contain in out
        check(f"{mod_name}.{fn_name} — 토큰 없이 미리보기", ok,
              f"출력에 '[DRY-RUN]'/{must_contain!r} 없음: {out[:160]!r}")
    except NetworkTouched as exc:
        check(f"{mod_name}.{fn_name} — 토큰 없이 미리보기", False, str(exc))
    except Exception as exc:  # noqa: BLE001
        check(f"{mod_name}.{fn_name} — 토큰 없이 미리보기", False,
              f"{type(exc).__name__}: {exc}")


# ─────────────────────────────────────────────────────────────
print("\n[2b] 구글 커넥터 dry-run — 토큰 조회조차 하지 않는다")

# 구글 2종은 인증이 파일 읽기라, dry-run 이 access_token() 을 부르면 토큰 파일이
# 없는 사람에게서 미리보기가 죽는다. 그래서 '네트워크 안 탐'보다 강한 조건 —
# access_token() 자체를 부르지 않는가 — 를 본다.
for mod_name, fn_name, kwargs, must_contain in GOOGLE_DRYRUN:
    mod = MODS.get(mod_name)
    if mod is None or not hasattr(mod, fn_name):
        check(f"{mod_name}.{fn_name} dry-run", False, "함수 없음")
        continue

    touched = []

    def _spy_token(*a, _t=touched, **k):
        _t.append("access_token")
        raise AssertionError("dry-run 이 토큰을 조회했다")

    args = argparse.Namespace(**kwargs)
    buf = io.StringIO()
    try:
        with mock.patch.object(mod.gauth, "access_token", _spy_token), \
             mock.patch.object(mod.gauth, "api_post", _forbid_network), \
             mock.patch.object(mod.gauth, "api_get", _forbid_network):
            with redirect_stdout(buf):
                mod.__dict__[fn_name](args, None)
        out = buf.getvalue()
        ok = "[DRY-RUN]" in out and must_contain in out and not touched
        check(f"{mod_name}.{fn_name} — 토큰 없이 미리보기", ok,
              f"touched={touched} out={out[:140]!r}")
    except NetworkTouched as exc:
        check(f"{mod_name}.{fn_name} — 토큰 없이 미리보기", False, str(exc))
    except Exception as exc:  # noqa: BLE001
        check(f"{mod_name}.{fn_name} — 토큰 없이 미리보기", False,
              f"{type(exc).__name__}: {exc}")

# 캘린더 초대는 남에게 나가는 동작이다 — 미리보기가 그 사실을 반드시 알려야 한다.
_cal = MODS.get("calendar_connector")
if _cal is not None:
    buf = io.StringIO()
    with mock.patch.object(_cal.gauth, "api_post", _forbid_network):
        with redirect_stdout(buf):
            _cal.cmd_add_event(argparse.Namespace(
                calendar="primary", summary="s", start="2026-08-20",
                end="2026-08-21", description=None, location=None,
                attendee=["a@b.com"], write=False), None)
    out = buf.getvalue()
    check("calendar add-event — 참석자 있으면 outward 경고", "outward" in out,
          "초대장이 나가는데 미리보기가 경고하지 않는다")

# 시트는 additive-only 여야 한다 — 수정/삭제 서브커맨드가 생기면 정책 위반.
_sh = MODS.get("sheets_connector")
if _sh is not None:
    subs = [a for a in _sh.build_parser()._actions
            if isinstance(a, argparse._SubParsersAction)]
    names = set(subs[0].choices) if subs else set()
    banned = names & {"update", "delete", "clear", "set", "write-cell"}
    check("sheets — 수정/삭제 서브커맨드 없음(additive-only)", not banned,
          f"금지 서브커맨드가 생겼다: {sorted(banned)}")


print("\n[3] --write 게이트 — 있으면 전송 경로를 실제로 탄다")

# 게이트가 반대로 잠겨(항상 dry-run) 있으면 커넥터가 조용히 무력해진다.
# 여기서는 http 를 가짜로 바꿔 '호출됐는가'만 본다 — 실제 전송은 없다.
WRITE_CASES = [
    ("github_connector", "cmd_open_pr",
     dict(repo="me/myrepo", head="feat", base="main",
          title="T", body="B", write=True),
     {"number": 1, "html_url": "http://example.invalid/pr/1"}),
    ("notion_connector", "cmd_append",
     dict(page_id="pid-123", text="hello", write=True),
     {"results": [{"id": "b1"}]}),
]

for mod_name, fn_name, kwargs, fake_reply in WRITE_CASES:
    mod = MODS.get(mod_name)
    if mod is None or not hasattr(mod, fn_name):
        check(f"{mod_name}.{fn_name} --write", False, "함수 없음")
        continue

    calls = []

    def _fake_http(method, url, token, data=None, _calls=calls):
        _calls.append((method, url))
        return fake_reply

    args = argparse.Namespace(**kwargs)
    buf = io.StringIO()
    try:
        with mock.patch.object(mod, "http", _fake_http):
            with redirect_stdout(buf):
                mod.__dict__[fn_name](args, "FAKE-TOKEN")
        wrote = any(m in ("POST", "PATCH", "PUT") for m, _ in calls)
        check(f"{mod_name}.{fn_name} — --write 시 전송 호출됨", wrote,
              f"쓰기 메서드 호출 없음: {calls}")
        check(f"{mod_name}.{fn_name} — --write 시 DRY-RUN 문구 없음",
              "[DRY-RUN]" not in buf.getvalue())
    except Exception as exc:  # noqa: BLE001
        check(f"{mod_name}.{fn_name} — --write 시 전송 호출됨", False,
              f"{type(exc).__name__}: {exc}")


# ─────────────────────────────────────────────────────────────
print("\n[4] 토큰 게이팅 — main() 이 명령 종류에 따라 다르게 요구한다")

# 260816 이전: github/notion/notion_db 는 main() 에서 무조건 cred.require 를 불러
# --write 없는 미리보기조차 토큰을 요구했다. asana 만 예외 처리가 있었다.
# 지금은 규칙이 하나다 — "쓰기 명령 + --write 없음" 이면 토큰을 요구하지 않는다.
TOKEN_FREE_DRYRUN = [
    ("github_connector", ["open-pr", "--repo", "me/r", "--head", "h",
                          "--base", "main", "--title", "t"]),
    ("notion_connector", ["append", "--page-id", "p", "--text", "x"]),
    ("asana_connector",  ["add-task", "--workspace", "ws-1", "--name", "n"]),
]

for mod_name, argv in TOKEN_FREE_DRYRUN:
    mod = MODS.get(mod_name)
    if mod is None:
        check(f"{mod_name} main() dry-run 토큰 불필요", False, "모듈 없음")
        continue

    required = []

    def _spy_require(*a, _r=required, **k):
        _r.append(a)
        raise SystemExit("[테스트] 토큰을 요구했다")

    buf = io.StringIO()
    try:
        with mock.patch.object(mod, "http", _forbid_network), \
             mock.patch.object(mod.cred, "require", _spy_require), \
             mock.patch.object(sys, "argv", [mod_name] + argv):
            with redirect_stdout(buf):
                mod.main()
        check(f"{mod_name} main() dry-run 토큰 불필요", not required,
              f"cred.require 가 불렸다: {required}")
    except SystemExit as exc:
        check(f"{mod_name} main() dry-run 토큰 불필요", False,
              f"SystemExit: {exc}")
    except NetworkTouched as exc:
        check(f"{mod_name} main() dry-run 토큰 불필요", False, str(exc))
    except Exception as exc:  # noqa: BLE001
        check(f"{mod_name} main() dry-run 토큰 불필요", False,
              f"{type(exc).__name__}: {exc}")

# 의도된 예외 — add-row 는 스키마 대조가 미리보기의 존재 이유라 토큰을 요구한다.
_ndb = MODS.get("notion_db_connector")
if _ndb is not None:
    buf = io.StringIO()
    raised = False
    try:
        with mock.patch.object(_ndb, "http", _forbid_network):
            with redirect_stdout(buf):
                _ndb.cmd_add_row(
                    argparse.Namespace(db="db1", title="t", prop=[], write=False),
                    None)
    except SystemExit:
        raised = True
    except NetworkTouched:
        raised = False
    check("notion_db add-row — 토큰 없으면 미리보기도 거부(의도된 예외)", raised,
          "토큰 없이 통과했다 — 검증 안 된 페이로드를 검증된 것처럼 보여준다")

# 쓰기 명령 + --write 는 반드시 토큰을 요구해야 한다 (게이트 약화 방지)
print("\n[4b] 적대 케이스 — --write 는 토큰을 반드시 요구한다")
for mod_name, argv in TOKEN_FREE_DRYRUN:
    mod = MODS.get(mod_name)
    if mod is None:
        continue
    required = []

    def _spy_require2(*a, _r=required, **k):
        _r.append(a)
        raise SystemExit("no token")

    buf = io.StringIO()
    try:
        with mock.patch.object(mod, "http", _forbid_network), \
             mock.patch.object(mod.cred, "require", _spy_require2), \
             mock.patch.object(sys, "argv", [mod_name] + argv + ["--write"]):
            with redirect_stdout(buf):
                mod.main()
    except SystemExit:
        pass
    except Exception:  # noqa: BLE001
        pass
    check(f"{mod_name} --write 는 토큰 요구", bool(required),
          "토큰 없이 쓰기 경로로 진입했다 — 게이트가 약해졌다")


# ─────────────────────────────────────────────────────────────
print("\n[5] 메일 — draft/reply 는 SMTP 를 아예 부르지 않는다")

# draft-first 정책(AGENTS.md §9)의 기계적 근거. 이 두 명령이 SMTP 를 부르는
# 순간 '초안까지만'이 무너진다.
_mail = MODS.get("mail_connector")
if _mail is None:
    check("mail_connector 로드", False)
else:
    src = (CONNECTORS / "mail_connector.py").read_text(encoding="utf-8")
    body = src[src.find("def cmd_draft"):src.find("def cmd_send")]
    check("cmd_draft/cmd_reply 구간에 smtplib 호출 없음",
          "smtplib" not in body and "SMTP" not in body,
          "draft/reply 경로에 SMTP 흔적이 있다")
    check("send 는 대화형 확인을 요구", "isatty" in src,
          "비대화형에서도 발송 가능해 보인다")


# ─────────────────────────────────────────────────────────────
print("\n[6] Asana sanitize_html — 개행은 실제 \\n 으로 보존된다 (issue #4)")

# &#10; 엔티티는 Asana sanitizer 가 &amp;#10; 로 재이스케이프해 화면에 리터럴로
# 노출된다(260816 실측). 실제 LF 바이트만 줄바꿈으로 렌더링되므로, sanitize_html
# 이 개행을 엔티티로 치환하는 순간 이 회귀가 재발한다.
_asana = MODS.get("asana_connector")
if _asana is None or not hasattr(_asana, "sanitize_html"):
    check("asana_connector.sanitize_html 존재", False)
else:
    out = _asana.sanitize_html("line1\nline2\r\nline3")
    check("실제 개행이 &#10; 로 치환되지 않음", "&#10;" not in out, repr(out))
    check("개행 문자가 보존됨(CRLF는 LF로 정규화)",
          out == "<body>line1\nline2\nline3</body>", repr(out))
    legacy = _asana.sanitize_html("a&#10;b")
    check("레거시 &#10; 입력은 실제 개행으로 복원",
          legacy == "<body>a\nb</body>", repr(legacy))
    check("<body> 자동 래핑 유지",
          _asana.sanitize_html("x") == "<body>x</body>")


# ─────────────────────────────────────────────────────────────
print("\n" + "-" * 60)
print(f"통과 {_pass} / 실패 {_fail}")
if _fail:
    print("\nFAIL — 실패 항목:")
    for f in _failures:
        print(f"  - {f}")
    sys.exit(1)
print(f"ALL PASS — 커넥터 {len(EXPECTED)}종이 오프라인 계약을 지킨다")
sys.exit(0)
