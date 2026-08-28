#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Friction/error logging channel — turn what was said into a record.

Why this exists
----------------
Most friction hit while using the toolkit gets worked around on the spot and
disappears. The workaround only lives in that one person's memory, and the
next person hits the same wall again. There has to be a record for it to
ever get fixed.

Design principles
------------------
**Must work with zero configuration.** Someone who got the toolkit off a USB
drive has no GitHub account, no token, no repo access. If leaving a record
required any of that, nobody would leave one. So the default destination is
a local file (JSONL), and a GitHub Issue is a **optional promotion path**
only for someone who has a token. A maintainer collects and uploads them
later, in batch.

**Ask only once.** Interrogating for repro steps makes people give up on
logging at all. The only required field is "what was the friction" — the
rest (which skill, what was expected, the environment) is filled in if
available and left blank otherwise. An incomplete record beats no record.

Usage
-----
    python scripts/feedback_log.py add "docx table editing keeps failing"
    python scripts/feedback_log.py add "..." --skill docx --expected "the table gets edited" \
                                          --actual "infinite loop at 51 matches"
    python scripts/feedback_log.py list
    python scripts/feedback_log.py export            # maintainer: convert to issue bodies
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

# ── sanitization gate ────────────────────────────────────────────────────
# The issue body carries what/expected/actual/note verbatim (to_issue).
# This gate keeps that path from carrying unpublished research content,
# credentials, or personal data. Without a gate, the doc's §"what not to
# leave in" section is just a notice that stops nothing — this workspace has
# already leaked that way three times (260628, 260706, 260807).
try:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from feedback_sanitize import format_report, scan_entry  # type: ignore
except ImportError:  # pragma: no cover - a distribution missing the module
    scan_entry = None  # type: ignore[assignment]
    format_report = None  # type: ignore[assignment]


def _gate(entry: dict) -> list[str]:
    """Run one entry through the sanitization gate. An empty return means it's clean."""
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
    """The minimum environment needed for repro. Filled in automatically, without asking the user."""
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
        pass  # the record must still be saved even without the claude CLI
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
            continue  # keep the rest even if one line is corrupted
    return out


def to_issue(entry: dict) -> tuple[str, str]:
    """Turn one record into a GitHub Issue's (title, body).

    The body also states its provenance (where it came from) — reading the
    issue alone must be enough to start reproducing it, and it must be
    possible to cross-reference it against the original record later.
    """
    head = entry["what"].splitlines()[0][:70]
    scope = f"[{entry['skill']}] " if entry.get("skill") else ""
    title = f"{scope}{head}"

    lines = [entry["what"], ""]
    if entry.get("expected") or entry.get("actual"):
        lines += ["## Expected vs actual", ""]
        if entry.get("expected"):
            lines.append(f"- Expected: {entry['expected']}")
        if entry.get("actual"):
            lines.append(f"- Actual: {entry['actual']}")
        lines.append("")
    if entry.get("note"):
        lines += ["## Note", "", entry["note"], ""]

    env = entry.get("env") or {}
    lines += [
        "## Provenance",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Record ID | `{entry['id']}` |",
        f"| Recorded at | {entry['ts']} |",
        f"| Kind | {entry['kind']} |",
        f"| Skill | {entry.get('skill') or '—'} |",
        f"| OS | {env.get('os', '—')} |",
        f"| Python | {env.get('python', '—')} |",
        f"| Claude Code | {env.get('claude', '—')} |",
        "",
        "> A record created by `scripts/feedback_log.py`.",
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
    # Scan before saving. This only **warns, never blocks** — blocking at
    # save time makes an already-tired person give up on reporting at all,
    # which erases the reason this feature exists. Instead it gives a chance
    # to fix it while the context is still fresh. The actual block happens at
    # export, where the content leaves the machine (asymmetric on purpose).
    draft = {"what": args.what, "expected": args.expected,
             "actual": args.actual, "note": args.note}
    hits = _gate(draft)

    entry = add_entry(args.what, kind=args.kind, skill=args.skill,
                      expected=args.expected, actual=args.actual, note=args.note)
    print(f"Recorded — {entry['id']}  ({LOG_PATH})")
    missing = [k for k in ("skill", "expected", "actual") if not entry.get(k)]
    if missing:
        print("  Empty field(s): " + ", ".join(missing)
              + "  (fine to leave blank — look up this ID later to fill it in.)")

    if hits:
        print("\n⚠ This contains content that cannot be sent out:")
        _print_hits(hits)
        print("\n  This record was saved, but will not go to an issue as-is.")
        print("  Keep only \"what failed\" and remove \"what data it failed with\".")
        print(f"  To fix it, find {entry['id']} in out/feedback.jsonl and edit it.")
    return 0


def cmd_list(args) -> int:
    entries = read_entries()
    if args.pending:
        entries = [e for e in entries if not e.get("exported")]
    if not entries:
        print("No records." if not args.pending else "No records left to upload.")
        return 0
    for e in entries:
        flag = " " if e.get("exported") else "*"
        scope = f"[{e['skill']}] " if e.get("skill") else ""
        print(f"{flag} {e['id']}  {e['ts'][:16]}  {e['kind']:8s} {scope}{e['what'][:60]}")
    print(f"\n{len(entries)} total (* = not yet raised as an issue)")
    return 0


def cmd_export(args) -> int:
    entries = [e for e in read_entries() if not e.get("exported")]
    if not entries:
        print("No records to upload.")
        return 0

    # ── sanitization gate (hard block) ──────────────────────────────────
    # Blocks even the preview. Letting only the preview through opens a
    # workaround — copy that output and upload it by hand — and that path
    # has no check at all.
    flagged = [(e, hits) for e in entries if (hits := _gate(e))]
    if flagged and not args.approve:
        print(f"[BLOCKED] {len(flagged)} record(s) contain content that cannot be sent out.\n")
        for e, hits in flagged:
            print(f"  {e['id']}  {e['what'][:46]}")
            _print_hits(hits)
            print()
        print("Fix it and run again — edit that ID in out/feedback.jsonl.")
        print("If you believe the scan is wrong, add --approve to proceed anyway.")
        print("  (--approve ignores the scan result. Use it only after checking the content yourself.)")
        return 2

    if flagged and args.approve:
        print(f"[WARN] proceeding with --approve, ignoring the scan result for {len(flagged)} record(s).\n")

    if not args.github:
        for e in entries:
            title, body = to_issue(e)
            print("=" * 70)
            print(f"TITLE: {title}")
            print("-" * 70)
            print(body)
        print("=" * 70)
        print(f"\n{len(entries)} record(s). To raise them as GitHub issues:")
        print("  python scripts/feedback_log.py export --github --repo owner/name --write")
        return 0

    if not args.repo:
        print("[ERROR] --github requires --repo owner/name.")
        return 2

    sys.path.insert(0, str(ROOT / "scripts" / "connectors"))
    try:
        import _credentials as cred  # type: ignore
        import github_connector as gh  # type: ignore
    except ImportError as e:
        print(f"[ERROR] could not load the GitHub connector: {e}")
        return 2

    token = cred.get("github", "token") if hasattr(cred, "get") else None
    if not token:
        print("[INFO] no GitHub token configured.")
        print("  Fill in github.token in config/credentials.json, or")
        print("  run without --github to extract the body only and upload it manually.")
        return 2

    assignee = None
    if not args.no_assignee:
        assignee = args.assignee
        if not assignee:
            # Default: whoever found it — auto-assign to the account this
            # token authenticates as. (Not dumped on the maintainer — the
            # finder is the owner.) github_connector.http() assumes a
            # standalone CLI run and calls sys.exit() on failure — SystemExit
            # is a BaseException, so a plain `except Exception` doesn't catch
            # it (found in the 260810 adversarial verification: an
            # offline/401/403/404 assignee lookup failure was killing the
            # entire export). Here the contract "the issue still gets
            # created even if the assignee lookup fails" must hold, so
            # SystemExit is caught alongside it.
            try:
                me = gh.http("GET", f"{gh.API_ROOT}/user", token, None)
                assignee = me.get("login")
            except (Exception, SystemExit) as e:
                print(f"[WARN] automatic assignee lookup failed ({e}) — proceeding unassigned.")

    if not args.write:
        print(f"[PREVIEW] about to upload {len(entries)} record(s) to {args.repo}.")
        if assignee:
            print(f"  Assignee: {assignee}")
        for e in entries:
            print(f"  - {to_issue(e)[0]}")
        print("\nAdd --write to actually upload.")
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
    print(f"\nUploaded {len(done)} record(s).")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Record friction/errors hit while using the toolkit (works with zero configuration)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("add", help="add a record")
    sp.add_argument("what", help="what the friction was (the only required field)")
    sp.add_argument("--kind", choices=KINDS, default="friction")
    sp.add_argument("--skill", help="the related skill name (if known)")
    sp.add_argument("--expected", help="what was expected")
    sp.add_argument("--actual", help="what actually happened")
    sp.add_argument("--note", help="anything else to add")
    sp.set_defaults(func=cmd_add)

    sp = sub.add_parser("list", help="view records")
    sp.add_argument("--pending", action="store_true", help="only records not yet uploaded")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("export", help="convert to issue bodies / upload")
    sp.add_argument("--github", action="store_true", help="raise as GitHub issues")
    sp.add_argument("--repo", help="owner/name")
    sp.add_argument("--label", help="comma-separated labels")
    sp.add_argument("--assignee",
                    help="assignee's GitHub login (default: whoever found it — the account this token authenticates as)")
    sp.add_argument("--no-assignee", action="store_true",
                    help="assign to no one (turns off the default self-assignment)")
    sp.add_argument("--write", action="store_true", help="actually upload (preview only if omitted)")
    sp.add_argument("--approve", action="store_true",
                    help="proceed despite the sanitization scan's result (only after checking the content yourself)")
    sp.set_defaults(func=cmd_export)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
