#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GitHub REST API v3 connector — read-first / write-guarded (AGENTS.md §9).

Reads (issues/prs/repo) run freely without any flag. The only write action,
`open-pr`, ALWAYS creates a DRAFT pull request (draft: true) and NEVER merges
anything (no merge subcommand exists in this script at all). It requires the
explicit --write flag, and it refuses outright to open a PR against a fork's
own upstream/parent repository — that requires an explicit human action on
your own fork instead.
"""
from __future__ import annotations

# Windows 기본 콘솔은 cp949 라서 한글/기호 출력에서 죽는다. UTF-8로 맞춘다.
# reconfigure 를 쓴다: TextIOWrapper 로 감싸면 원본 스트림을 소유하게 되어,
# 이 모듈이 import 된 뒤 래퍼가 GC 될 때 호출자의 stdout 까지 닫는다(실측).
import sys as _sys
for _s in (_sys.stdout, _sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

import argparse
import json
import sys
import urllib.error
import urllib.request

import _credentials as cred

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

API_ROOT = "https://api.github.com"


def http(method, url, token, data=None, headers=None):
    """urllib 기반 최소 HTTP 헬퍼. 파싱된 JSON을 반환하거나 친절한 한글 오류로 종료."""
    hdrs = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "sci-toolkit-github-connector",
    }
    if headers:
        hdrs.update(headers)
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        if e.code == 401:
            sys.exit(f"[오류] 인증 실패(401). 토큰(github.token)을 확인하세요. (마스킹: {cred.mask(token)})")
        if e.code == 403:
            sys.exit("[오류] 403 — API 요청 한도 초과 또는 권한 부족일 수 있습니다.")
        if e.code == 404:
            sys.exit("[오류] 404 — 저장소/리소스를 찾을 수 없습니다. --repo owner/name 형식을 확인하세요.")
        detail = ""
        try:
            detail = e.read().decode("utf-8", "ignore")
        except Exception:
            pass
        sys.exit(f"[오류] GitHub API 오류 {e.code}: {detail[:300]}")
    except urllib.error.URLError as e:
        sys.exit(f"[오류] 네트워크 연결을 확인하세요: {e.reason}")


def cmd_issues(args, token):
    url = f"{API_ROOT}/repos/{args.repo}/issues?state={args.state}"
    data = http("GET", url, token)
    items = [d for d in data if "pull_request" not in d]
    print(f"[{args.repo}] {args.state} 이슈 {len(items)}건")
    for it in items:
        print(f"  #{it['number']:<5} {it['title']}  (by {it['user']['login']})")


def cmd_prs(args, token):
    url = f"{API_ROOT}/repos/{args.repo}/pulls?state=open"
    data = http("GET", url, token)
    print(f"[{args.repo}] open PR {len(data)}건")
    for pr in data:
        draft = " (draft)" if pr.get("draft") else ""
        print(f"  #{pr['number']:<5} {pr['title']}{draft}  {pr['head']['ref']} -> {pr['base']['ref']}")


def cmd_repo(args, token):
    url = f"{API_ROOT}/repos/{args.repo}"
    data = http("GET", url, token)
    is_fork = bool(data.get("fork"))
    print(f"[{args.repo}]")
    print(f"  fork: {is_fork}")
    if is_fork:
        parent = data.get("parent", {}) or {}
        print(f"  parent(upstream): {parent.get('full_name', '(알 수 없음)')}")
    print(f"  private: {data.get('private')}")
    print(f"  default_branch: {data.get('default_branch')}")


def cmd_open_pr(args, token):
    # fork 가드는 저장소를 조회해야 판정된다 → 토큰이 필요하다. 토큰 없이 부른
    # dry-run 은 페이로드만 보여주고, 가드를 "통과"한 게 아니라 "아직 못 돌렸다"고
    # 밝힌다. 여기서 조용히 넘어가면 --write 없이 본 미리보기가 upstream 안전을
    # 확인해 준 것처럼 읽힌다.
    fork_checked = token is not None
    if fork_checked:
        repo_url = f"{API_ROOT}/repos/{args.repo}"
        repo_data = http("GET", repo_url, token)
        is_fork = bool(repo_data.get("fork"))
        parent = (repo_data.get("parent") or {}).get("full_name")

        if is_fork and parent and parent == args.repo:
            sys.exit(
                "[거부] 이 저장소는 fork이며 --repo 가 가리키는 대상이 바로 그 upstream(parent) 저장소입니다.\n"
                "  upstream에 대한 push/PR은 명시적인 사람의 직접 조작이 필요합니다.\n"
                "  대신 본인 fork에서 PR을 여세요 (예: --repo <your-username>/<repo>)."
            )

    body_preview = {
        "title": args.title,
        "head": args.head,
        "base": args.base,
        "body": args.body or "",
        "draft": True,
    }

    if not args.write:
        print("[DRY-RUN] --write 플래그가 없어 실제로 실행하지 않습니다.")
        print(f"  대상 저장소: {args.repo}")
        print("  생성될 PR (draft):")
        print(json.dumps(body_preview, ensure_ascii=False, indent=2))
        if not fork_checked:
            print("  [주의] 토큰이 없어 fork/upstream 검사를 아직 돌리지 못했습니다.")
            print("         --write 실행 시 검사 후 upstream 대상이면 거부됩니다.")
        print("  실행하려면 --write 를 추가하세요.")
        return

    print("[알림] 외부로 나가는(outward) 되돌리기 어려운 작업입니다 — GitHub에 실제 draft PR을 생성합니다.")
    url = f"{API_ROOT}/repos/{args.repo}/pulls"
    result = http("POST", url, token, data=body_preview)
    print(f"[완료] draft PR 생성됨: #{result.get('number')} {result.get('html_url')}")


def build_parser():
    p = argparse.ArgumentParser(
        prog="github_connector.py",
        description=(
            "GitHub REST 커넥터 (read-first). issues/prs/repo 는 자유 조회, "
            "open-pr 만 쓰기 동작이며 --write 필요. PR은 항상 draft로만 생성되고, "
            "fork의 upstream 대상은 자동 거부됩니다. merge 서브커맨드는 존재하지 않습니다."
        ),
    )
    sub = p.add_subparsers(dest="command")

    sp = sub.add_parser("issues", help="[READ] open 이슈 목록")
    sp.add_argument("--repo", required=True, help="owner/name")
    sp.add_argument("--state", default="open")
    sp.set_defaults(func=cmd_issues)

    sp = sub.add_parser("prs", help="[READ] open PR 목록")
    sp.add_argument("--repo", required=True)
    sp.set_defaults(func=cmd_prs)

    sp = sub.add_parser("repo", help="[READ] 저장소 정보 (fork 여부/parent)")
    sp.add_argument("--repo", required=True)
    sp.set_defaults(func=cmd_repo)

    sp = sub.add_parser("open-pr", help="[WRITE, --write 필요] draft PR 생성 (upstream 가드 포함)")
    sp.add_argument("--repo", required=True)
    sp.add_argument("--head", required=True)
    sp.add_argument("--base", required=True)
    sp.add_argument("--title", required=True)
    sp.add_argument("--body", default="")
    sp.add_argument("--write", action="store_true", help="실제로 PR을 생성합니다 (없으면 dry-run)")
    sp.set_defaults(func=cmd_open_pr)

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    if not getattr(args, "command", None):
        parser.print_help()
        print("\n[안내] 읽기(issues/prs/repo)는 바로 실행됩니다. 쓰기(open-pr)는 --write 가 있어야 실행됩니다.")
        return
    # dry-run(쓰기 명령인데 --write 없음)은 토큰 없이도 미리보기 가능하게 한다.
    is_dryrun_write = hasattr(args, "write") and not args.write
    token = None if is_dryrun_write else cred.require("github", "token")
    args.func(args, token)


if __name__ == "__main__":
    main()
