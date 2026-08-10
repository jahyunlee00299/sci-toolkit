#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
불편·오류 기록 채널 — 말한 것을 기록으로 남긴다.

왜 필요한가
-----------
툴킷을 쓰다 겪은 불편은 대부분 그 자리에서 우회되고 사라진다. 우회는 개인의
기억에만 남고, 다음 사람이 같은 곳에서 다시 막힌다. 기록이 있어야 고칠 수 있다.

설계 원칙
---------
**설정 없이 동작해야 한다.** 툴킷을 USB로 받은 사람은 GitHub 계정도, 토큰도,
저장소 접근권도 없다. 기록을 남기는 데 그런 게 필요하면 아무도 남기지 않는다.
그래서 기본 목적지는 로컬 파일(JSONL)이고, GitHub Issue 는 토큰이 있는 사람만
쓰는 **선택적 승격 경로**다. 관리자는 나중에 수거해 한 번에 올린다.

**한 번만 묻는다.** 재현 절차를 캐물으면 기록 자체를 포기한다. 필수는 "무엇이
불편했는가" 하나뿐이고, 나머지(어떤 스킬·무엇을 기대했는지·환경)는 있으면 담고
없으면 비워둔다. 불완전한 기록이 없는 기록보다 낫다.

사용
----
    python scripts/feedback_log.py add "docx 표 편집이 계속 실패해요"
    python scripts/feedback_log.py add "..." --skill docx --expected "표가 수정됨" \
                                          --actual "51 matches 로 무한루프"
    python scripts/feedback_log.py list
    python scripts/feedback_log.py export            # 관리자: 이슈 본문으로 변환
    python scripts/feedback_log.py export --github --repo owner/name --write
"""
from __future__ import annotations

import sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

import argparse
import json
import platform
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = ROOT / "out" / "feedback.jsonl"

KINDS = ("bug", "friction", "missing", "docs", "idea")

# ── 정화 게이트 ─────────────────────────────────────────────────────────────
# 이슈 본문에는 what/expected/actual/note 가 원문 그대로 들어간다(to_issue).
# 그 경로에 미공개 연구내용·자격증명·개인정보가 실리지 않도록 막는다.
# 게이트가 없으면 문서 §"남기면 안 되는 것" 은 안내문일 뿐 아무것도 막지
# 못한다 — 이 워크스페이스에서 이미 세 번 그렇게 샜다(260628·260706·260807).
try:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from feedback_sanitize import format_report, scan_entry  # type: ignore
except ImportError:  # pragma: no cover - 모듈이 빠진 배포본
    scan_entry = None  # type: ignore[assignment]
    format_report = None  # type: ignore[assignment]


def _gate(entry: dict) -> list[str]:
    """기록 하나를 정화 게이트에 통과시킨다. 반환값이 비면 깨끗함."""
    if scan_entry is None:
        return []
    return scan_entry(entry)


def _print_hits(hits: list[str]) -> None:
    if format_report is not None:
        print(format_report(hits))
    else:  # pragma: no cover
        for h in hits:
            print(f"  · {h}")


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _environment() -> dict:
    """재현에 필요한 최소 환경. 사용자에게 묻지 않고 자동으로 채운다."""
    env = {
        "os": f"{platform.system()} {platform.release()}",
        "python": platform.python_version(),
    }
    try:
        out = subprocess.run(["claude", "--version"], capture_output=True,
                             text=True, timeout=15)
        if out.returncode == 0:
            env["claude"] = out.stdout.strip().splitlines()[0][:60]
    except Exception:
        pass  # claude CLI 없어도 기록은 남아야 한다
    return env


def add_entry(what: str, *, kind: str = "friction", skill: str | None = None,
              expected: str | None = None, actual: str | None = None,
              note: str | None = None) -> dict:
    entry = {
        "id": uuid.uuid4().hex[:12],
        "ts": _now(),
        "kind": kind,
        "what": what.strip(),
        "skill": skill,
        "expected": expected,
        "actual": actual,
        "note": note,
        "env": _environment(),
        "exported": False,
    }
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def read_entries() -> list[dict]:
    if not LOG_PATH.exists():
        return []
    out = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # 한 줄이 깨져도 나머지는 살린다
    return out


def to_issue(entry: dict) -> tuple[str, str]:
    """기록 하나를 GitHub Issue 의 (제목, 본문)으로 만든다.

    본문에 출처(어디서 나왔는지)를 함께 적는다 — 이슈만 보고도 재현을 시작할 수
    있어야 하고, 나중에 원본 기록과 대조할 수 있어야 한다.
    """
    head = entry["what"].splitlines()[0][:70]
    scope = f"[{entry['skill']}] " if entry.get("skill") else ""
    title = f"{scope}{head}"

    lines = [entry["what"], ""]
    if entry.get("expected") or entry.get("actual"):
        lines += ["## 기대 vs 실제", ""]
        if entry.get("expected"):
            lines.append(f"- 기대: {entry['expected']}")
        if entry.get("actual"):
            lines.append(f"- 실제: {entry['actual']}")
        lines.append("")
    if entry.get("note"):
        lines += ["## 덧붙임", "", entry["note"], ""]

    env = entry.get("env") or {}
    lines += [
        "## 출처",
        "",
        "| 항목 | 값 |",
        "|---|---|",
        f"| 기록 ID | `{entry['id']}` |",
        f"| 기록 시각 | {entry['ts']} |",
        f"| 종류 | {entry['kind']} |",
        f"| 스킬 | {entry.get('skill') or '—'} |",
        f"| OS | {env.get('os', '—')} |",
        f"| Python | {env.get('python', '—')} |",
        f"| Claude Code | {env.get('claude', '—')} |",
        "",
        "> `scripts/feedback_log.py` 가 만든 기록입니다.",
    ]
    return title, "\n".join(lines)


def mark_exported(ids: set[str]) -> None:
    entries = read_entries()
    for e in entries:
        if e["id"] in ids:
            e["exported"] = True
    tmp = LOG_PATH.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    tmp.replace(LOG_PATH)


# ── commands ────────────────────────────────────────────────────────────────
def cmd_add(args) -> int:
    # 기록 전에 먼저 검사한다. 여기서는 **막지 않고 경고만** 한다 —
    # 기록 시점에 차단하면 지친 사람이 신고 자체를 포기하고, 그러면 이
    # 기능의 존재 이유가 사라진다. 대신 맥락이 아직 생생할 때 고칠
    # 기회를 준다. 실제 차단은 밖으로 나가는 export 에서 한다(비대칭).
    draft = {"what": args.what, "expected": args.expected,
             "actual": args.actual, "note": args.note}
    hits = _gate(draft)

    entry = add_entry(args.what, kind=args.kind, skill=args.skill,
                      expected=args.expected, actual=args.actual, note=args.note)
    print(f"기록했습니다 — {entry['id']}  ({LOG_PATH})")
    missing = [k for k in ("skill", "expected", "actual") if not entry.get(k)]
    if missing:
        print("  비어 있는 항목: " + ", ".join(missing)
              + "  (없어도 됩니다. 나중에 채우려면 이 ID로 찾으세요.)")

    if hits:
        print("\n⚠ 밖으로 내보낼 수 없는 내용이 들어 있습니다:")
        _print_hits(hits)
        print("\n  이 기록은 저장됐지만, 이대로는 이슈로 올라가지 않습니다.")
        print("  \"무엇이 실패했는가\"만 남기고 \"무슨 데이터로 실패했는가\"는 빼주세요.")
        print(f"  고치려면 out/feedback.jsonl 에서 {entry['id']} 를 찾아 편집하세요.")
    return 0


def cmd_list(args) -> int:
    entries = read_entries()
    if args.pending:
        entries = [e for e in entries if not e.get("exported")]
    if not entries:
        print("기록이 없습니다." if not args.pending else "아직 올리지 않은 기록이 없습니다.")
        return 0
    for e in entries:
        flag = " " if e.get("exported") else "*"
        scope = f"[{e['skill']}] " if e.get("skill") else ""
        print(f"{flag} {e['id']}  {e['ts'][:16]}  {e['kind']:8s} {scope}{e['what'][:60]}")
    print(f"\n총 {len(entries)}건 (* = 아직 이슈로 올리지 않음)")
    return 0


def cmd_export(args) -> int:
    entries = [e for e in read_entries() if not e.get("exported")]
    if not entries:
        print("올릴 기록이 없습니다.")
        return 0

    # ── 정화 게이트 (하드 차단) ────────────────────────────────────────
    # 미리보기까지 포함해 막는다. 미리보기만 통과시키면 그 출력을 복사해
    # 손으로 올리는 우회가 생기고, 그 경로엔 아무 검사도 없다.
    flagged = [(e, hits) for e in entries if (hits := _gate(e))]
    if flagged and not args.approve:
        print(f"[차단] {len(flagged)}건에 밖으로 내보낼 수 없는 내용이 있습니다.\n")
        for e, hits in flagged:
            print(f"  {e['id']}  {e['what'][:46]}")
            _print_hits(hits)
            print()
        print("고친 뒤 다시 실행하세요 — out/feedback.jsonl 에서 해당 ID를 편집하면 됩니다.")
        print("검사가 틀렸다고 판단되면 --approve 를 붙여 넘길 수 있습니다.")
        print("  (--approve 는 검사 결과를 무시합니다. 내용을 직접 확인한 뒤에만 쓰세요.)")
        return 2

    if flagged and args.approve:
        print(f"[경고] --approve 로 {len(flagged)}건의 검사 결과를 무시하고 진행합니다.\n")

    if not args.github:
        for e in entries:
            title, body = to_issue(e)
            print("=" * 70)
            print(f"TITLE: {title}")
            print("-" * 70)
            print(body)
        print("=" * 70)
        print(f"\n{len(entries)}건. GitHub 이슈로 올리려면:")
        print("  python scripts/feedback_log.py export --github --repo owner/name --write")
        return 0

    if not args.repo:
        print("[오류] --github 를 쓰려면 --repo owner/name 이 필요합니다.")
        return 2

    sys.path.insert(0, str(ROOT / "scripts" / "connectors"))
    try:
        import _credentials as cred  # type: ignore
        import github_connector as gh  # type: ignore
    except ImportError as e:
        print(f"[오류] GitHub 커넥터를 불러올 수 없습니다: {e}")
        return 2

    token = cred.get("github", "token") if hasattr(cred, "get") else None
    if not token:
        print("[안내] GitHub 토큰이 설정되어 있지 않습니다.")
        print("  config/credentials.json 의 github.token 을 채우거나,")
        print("  토큰 없이 쓰려면 --github 없이 실행해 본문만 뽑아 수동으로 올리세요.")
        return 2

    assignee = None
    if not args.no_assignee:
        assignee = args.assignee
        if not assignee:
            # 기본값: 발견자 본인 — 이 토큰으로 인증된 계정에게 자동 할당한다.
            # (관리자에게 몰아주지 않는다 — 발견한 사람이 담당자.)
            # github_connector.http() 는 CLI 단독 실행을 전제로 실패 시
            # sys.exit() 를 호출한다 — SystemExit 은 BaseException 이라
            # 일반 Exception 으로는 안 잡힌다(적대검증 260810에서 발견:
            # 오프라인/401/403/404 상황에서 담당자 조회 실패가 export
            # 전체를 죽여버렸다). 여기서는 "담당자 조회 실패해도 이슈는
            # 만든다"는 계약을 지켜야 하므로 SystemExit 도 함께 잡는다.
            try:
                me = gh.http("GET", f"{gh.API_ROOT}/user", token, None)
                assignee = me.get("login")
            except (Exception, SystemExit) as e:
                print(f"[경고] 담당자 자동 조회 실패 ({e}) — 할당 없이 진행합니다.")

    if not args.write:
        print(f"[미리보기] {len(entries)}건을 {args.repo} 에 올릴 예정입니다.")
        if assignee:
            print(f"  담당자: {assignee}")
        for e in entries:
            print(f"  - {to_issue(e)[0]}")
        print("\n실제로 올리려면 --write 를 붙이세요.")
        return 0

    done = set()
    for e in entries:
        title, body = to_issue(e)
        data = {"title": title, "body": body}
        if args.label:
            data["labels"] = [s.strip() for s in args.label.split(",") if s.strip()]
        if assignee:
            data["assignees"] = [assignee]
        res = gh.http("POST", f"{gh.API_ROOT}/repos/{args.repo}/issues", token, data)
        num = res.get("number")
        print(f"  #{num}  {title}" + (f"  (assignee: {assignee})" if assignee else ""))
        done.add(e["id"])
    mark_exported(done)
    print(f"\n{len(done)}건을 올렸습니다.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="툴킷을 쓰다 겪은 불편·오류를 기록한다 (설정 없이 동작)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("add", help="기록 추가")
    sp.add_argument("what", help="무엇이 불편했는지 (이것만 필수)")
    sp.add_argument("--kind", choices=KINDS, default="friction")
    sp.add_argument("--skill", help="관련 스킬 이름 (알면)")
    sp.add_argument("--expected", help="기대한 결과")
    sp.add_argument("--actual", help="실제 결과")
    sp.add_argument("--note", help="덧붙일 말")
    sp.set_defaults(func=cmd_add)

    sp = sub.add_parser("list", help="기록 보기")
    sp.add_argument("--pending", action="store_true", help="아직 올리지 않은 것만")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("export", help="이슈 본문으로 변환 / 업로드")
    sp.add_argument("--github", action="store_true", help="GitHub 이슈로 올린다")
    sp.add_argument("--repo", help="owner/name")
    sp.add_argument("--label", help="쉼표구분 라벨")
    sp.add_argument("--assignee",
                    help="담당자 GitHub 로그인 (기본값: 발견자 본인 — 이 명령을 실행하는 토큰의 계정)")
    sp.add_argument("--no-assignee", action="store_true",
                    help="아무에게도 할당하지 않는다 (기본 자기-할당을 끈다)")
    sp.add_argument("--write", action="store_true", help="실제로 올린다(없으면 미리보기)")
    sp.add_argument("--approve", action="store_true",
                    help="정화 검사 결과를 무시하고 진행한다 (내용을 직접 확인한 경우에만)")
    sp.set_defaults(func=cmd_export)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
