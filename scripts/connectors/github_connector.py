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

# Windows' default console is cp949, which dies on Korean/symbol output. Force UTF-8.
# Use reconfigure(): wrapping in a TextIOWrapper would take ownership of the
# underlying stream, so once the wrapper is GC'd after this module is imported,
# it closes the caller's stdout too (measured).
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
    """Minimal urllib-based HTTP helper. Returns parsed JSON, or exits with a friendly error."""
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
            sys.exit(f"[Error] Authentication failed (401). Check your token (github.token). (masked: {cred.mask(token)})")
        if e.code == 403:
            sys.exit("[Error] 403 — could be an API rate limit or insufficient permission.")
        if e.code == 404:
            sys.exit("[Error] 404 — repository/resource not found. Check the --repo owner/name format.")
        detail = ""
        try:
            detail = e.read().decode("utf-8", "ignore")
        except Exception:
            pass
        sys.exit(f"[Error] GitHub API error {e.code}: {detail[:300]}")
    except urllib.error.URLError as e:
        sys.exit(f"[Error] Check your network connection: {e.reason}")


def cmd_issues(args, token):
    url = f"{API_ROOT}/repos/{args.repo}/issues?state={args.state}"
    data = http("GET", url, token)
    items = [d for d in data if "pull_request" not in d]
    print(f"[{args.repo}] {args.state} issue(s): {len(items)}")
    for it in items:
        print(f"  #{it['number']:<5} {it['title']}  (by {it['user']['login']})")


def cmd_prs(args, token):
    url = f"{API_ROOT}/repos/{args.repo}/pulls?state=open"
    data = http("GET", url, token)
    print(f"[{args.repo}] open PR(s): {len(data)}")
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
        print(f"  parent(upstream): {parent.get('full_name', '(unknown)')}")
    print(f"  private: {data.get('private')}")
    print(f"  default_branch: {data.get('default_branch')}")


def cmd_open_pr(args, token):
    # The fork guard needs to look up the repo to decide, which needs a token. A
    # dry-run called without a token shows only the payload, and states plainly
    # that the guard "hasn't run yet" rather than that it "passed." Staying quiet
    # here would make a preview without --write read as if it had confirmed
    # upstream safety.
    fork_checked = token is not None
    if fork_checked:
        repo_url = f"{API_ROOT}/repos/{args.repo}"
        repo_data = http("GET", repo_url, token)
        is_fork = bool(repo_data.get("fork"))
        parent = (repo_data.get("parent") or {}).get("full_name")

        if is_fork and parent and parent == args.repo:
            sys.exit(
                "[Refused] This repository is a fork, and --repo points at its own upstream (parent) repository.\n"
                "  A push/PR against upstream requires an explicit human action.\n"
                "  Open the PR from your own fork instead (e.g. --repo <your-username>/<repo>)."
            )

    body_preview = {
        "title": args.title,
        "head": args.head,
        "base": args.base,
        "body": args.body or "",
        "draft": True,
    }

    if not args.write:
        print("[DRY-RUN] --write flag not set, not actually executing.")
        print(f"  Target repository: {args.repo}")
        print("  PR to be created (draft):")
        print(json.dumps(body_preview, ensure_ascii=False, indent=2))
        if not fork_checked:
            print("  [Caution] No token, so the fork/upstream check has not run yet.")
            print("            On --write it will run first and refuse if the target is upstream.")
        print("  Add --write to execute.")
        return

    print("[Notice] This is an outward, hard-to-undo action — creating a real draft PR on GitHub.")
    url = f"{API_ROOT}/repos/{args.repo}/pulls"
    result = http("POST", url, token, data=body_preview)
    print(f"[Done] Draft PR created: #{result.get('number')} {result.get('html_url')}")


def build_parser():
    p = argparse.ArgumentParser(
        prog="github_connector.py",
        description=(
            "GitHub REST connector (read-first). issues/prs/repo are free reads; "
            "open-pr is the only write action and requires --write. A PR is always created as "
            "draft only, and a fork's upstream target is refused automatically. No merge subcommand exists."
        ),
    )
    sub = p.add_subparsers(dest="command")

    sp = sub.add_parser("issues", help="[READ] list open issues")
    sp.add_argument("--repo", required=True, help="owner/name")
    sp.add_argument("--state", default="open")
    sp.set_defaults(func=cmd_issues)

    sp = sub.add_parser("prs", help="[READ] list open PRs")
    sp.add_argument("--repo", required=True)
    sp.set_defaults(func=cmd_prs)

    sp = sub.add_parser("repo", help="[READ] repository info (fork status/parent)")
    sp.add_argument("--repo", required=True)
    sp.set_defaults(func=cmd_repo)

    sp = sub.add_parser("open-pr", help="[WRITE, requires --write] create a draft PR (includes upstream guard)")
    sp.add_argument("--repo", required=True)
    sp.add_argument("--head", required=True)
    sp.add_argument("--base", required=True)
    sp.add_argument("--title", required=True)
    sp.add_argument("--body", default="")
    sp.add_argument("--write", action="store_true", help="Actually create the PR (dry-run if omitted)")
    sp.set_defaults(func=cmd_open_pr)

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    if not getattr(args, "command", None):
        parser.print_help()
        print("\n[Note] Reads (issues/prs/repo) run immediately. Writes (open-pr) require --write.")
        return
    # A dry-run (a write command without --write) can preview without a token.
    is_dryrun_write = hasattr(args, "write") and not args.write
    token = None if is_dryrun_write else cred.require("github", "token")
    args.func(args, token)


if __name__ == "__main__":
    main()
