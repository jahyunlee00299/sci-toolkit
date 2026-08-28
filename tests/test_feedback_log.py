#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Feedback-log channel regression test.

The most important thing about this tool's contract is that **it works with
zero configuration**. The moment it requires a token, account, or network,
nobody logs anything anymore — this test guards against that property
breaking.

Contract:
  1. The only required argument is "what's the problem". It logs with
     nothing else.
  2. Environment info (OS/Python) is filled in automatically, never asked for.
  3. One log line = one JSONL entry. If one line breaks, the rest still read.
  4. The issue body must always include provenance (entry ID + timestamp) —
     it must be reproducible.
  5. export uploads nothing without --write (§9 draft-first).
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
import importlib.util
import json
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "feedback_log", ROOT / "scripts" / "feedback_log.py")
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules["feedback_log"] = _mod
_spec.loader.exec_module(_mod)

_fail = 0
_pass = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global _fail, _pass
    if cond:
        _pass += 1
        print(f"  PASS  {name}")
    else:
        _fail += 1
        print(f"  FAIL  {name}" + (f" — {detail}" if detail else ""))


def main() -> int:
    print("Verifying the feedback-log channel")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as td:
        # Swap the path so the real out/feedback.jsonl is never touched.
        _mod.LOG_PATH = Path(td) / "feedback.jsonl"

        # ── 1. Log with minimal input ───────────────────────────────────
        print("\n[Minimal input] log with just one line, no configuration")
        e = _mod.add_entry("Table editing keeps failing")
        check("an entry is created", bool(e.get("id")))
        check("written to the file", _mod.LOG_PATH.exists())
        check("environment is auto-filled",
              bool(e["env"].get("os")) and bool(e["env"].get("python")),
              f"env={e['env']}")
        check("optional fields may be empty", e["skill"] is None and e["expected"] is None)

        # ── 2. Full input ────────────────────────────────────────────────
        print("\n[Full input] with everything known filled in")
        e2 = _mod.add_entry("Find-replace doesn't work inside a cell", kind="bug", skill="docx",
                            expected="The cell value changes", actual="Infinite loop")
        check("kind is reflected", e2["kind"] == "bug")
        check("skill is reflected", e2["skill"] == "docx")

        # ── 3. Reading ─────────────────────────────────────────────────────
        print("\n[Read] JSONL parsing")
        entries = _mod.read_entries()
        check("both entries are read", len(entries) == 2, f"len={len(entries)}")

        # Mixing in a broken line must not take down the rest
        with _mod.LOG_PATH.open("a", encoding="utf-8") as f:
            f.write("{ not a broken line json\n")
        entries = _mod.read_entries()
        check("the rest still read even with a broken line present", len(entries) == 2, f"len={len(entries)}")

        # ── 4. Issue body ────────────────────────────────────────────────
        print("\n[Issue conversion] provenance must always be included")
        title, body = _mod.to_issue(e2)
        check("title is prefixed with the skill scope", title.startswith("[docx]"), title)
        check("body includes the entry ID", e2["id"] in body)
        check("body includes expected/actual",
              "The cell value changes" in body and "Infinite loop" in body)
        check("body includes environment", "Python" in body)

        # An entry with no optional fields must still produce a body
        title1, body1 = _mod.to_issue(e)
        check("a minimal entry also produces a body", bool(title1) and e["id"] in body1)

        # ── 5. exported flag ────────────────────────────────────────────
        print("\n[Promotion flag] what's been uploaded doesn't get uploaded again")
        _mod.mark_exported({e2["id"]})
        after = {x["id"]: x for x in _mod.read_entries()}
        check("an uploaded entry has exported=True", after[e2["id"]]["exported"] is True)
        check("a non-uploaded entry stays as-is", after[e["id"]]["exported"] is False)

        # ── 6. JSONL format ───────────────────────────────────────────────
        print("\n[Format] one line = one entry")
        lines = [l for l in _mod.LOG_PATH.read_text(encoding="utf-8").splitlines()
                 if l.strip()]
        parsed = 0
        for line in lines:
            try:
                json.loads(line)
                parsed += 1
            except json.JSONDecodeError:
                pass
        check("2 valid JSON lines", parsed == 2, f"parsed={parsed}/{len(lines)}")

        # ── 7. Assignee = finder (mocked, no real network) ─────────────────
        print("\n[Assignee] the issue is assigned to whoever found it — not dumped on the maintainer")

        def _run_export(no_assignee=False, assignee=None, fail_lookup=None):
            # fail_lookup: None (success) / "exception" (a generic exception) /
            # "systemexit" (the way the real github_connector.http() fails —
            # sys.exit() is a BaseException subclass, so a plain
            # `except Exception` doesn't catch it. This reproduces the real
            # failure path found during adversarial verification on 260810).
            calls = []

            def fake_http(method, url, token, data=None):
                calls.append((method, url, data))
                if url.endswith("/user"):
                    if fail_lookup == "exception":
                        raise RuntimeError("network down")
                    if fail_lookup == "systemexit":
                        sys.exit("[Error] Check your network connection: mocked offline")
                    return {"login": "finder-account"}
                return {"number": 1}

            mock_gh = mock.MagicMock()
            mock_gh.http = fake_http
            mock_gh.API_ROOT = "https://api.github.com"
            mock_cred = mock.MagicMock()
            mock_cred.get = lambda *a: "fake-token"

            with mock.patch.dict(sys.modules,
                                  {"github_connector": mock_gh, "_credentials": mock_cred}):
                args = argparse.Namespace(
                    github=True, repo="owner/name", label=None,
                    assignee=assignee, no_assignee=no_assignee, write=True, approve=False)
                _mod.cmd_export(args)
            issue_calls = [c for c in calls if c[1].endswith("/issues")]
            return calls, issue_calls

        # Default: when unspecified, assigns to the account looked up via /user
        # (an unexported entry from an earlier section may also ride along, so
        #  we check "all of them" — the contract is that every issue gets the
        #  same assignee, not a specific count.)
        e3 = _mod.add_entry("Assignee test — default")
        calls, issue_calls = _run_export()
        check("default: the /user lookup is called", any(c[1].endswith("/user") for c in calls))
        check("default: every uploaded issue is assigned to the finder (self)",
              len(issue_calls) >= 1 and
              all(c[2].get("assignees") == ["finder-account"] for c in issue_calls),
              f"issue_calls={issue_calls}")

        # --no-assignee: assigns to no one, and skips the /user call too (avoids a needless API call)
        e4 = _mod.add_entry("Assignee test — no-assignee")
        calls, issue_calls = _run_export(no_assignee=True)
        check("--no-assignee: the /user call is skipped", not any(c[1].endswith("/user") for c in calls))
        check("--no-assignee: the assignees field is absent entirely",
              len(issue_calls) == 1 and "assignees" not in issue_calls[0][2])

        # --assignee given explicitly: uses that value as-is, doesn't look up self
        e5 = _mod.add_entry("Assignee test — explicit override")
        calls, issue_calls = _run_export(assignee="someone-else")
        check("--assignee given: the /user lookup is skipped", not any(c[1].endswith("/user") for c in calls))
        check("--assignee given: assigned to the specified person",
              len(issue_calls) == 1 and issue_calls[0][2].get("assignees") == ["someone-else"])

        # Even if the /user lookup fails (e.g. offline), issue creation itself must not die
        e6 = _mod.add_entry("Assignee test — lookup failure (generic exception)")
        calls, issue_calls = _run_export(fail_lookup="exception")
        check("generic exception: the issue is still created even if the /user lookup fails (unassigned)",
              len(issue_calls) == 1 and "assignees" not in issue_calls[0][2])

        # The failure mode the real github_connector.http() actually uses
        # (sys.exit → SystemExit) must honor the same contract — this is the
        # exact path that was found broken in the 260810 adversarial verification.
        e7 = _mod.add_entry("Assignee test — lookup failure (SystemExit, the real failure path)")
        calls, issue_calls = _run_export(fail_lookup="systemexit")
        check("SystemExit: the issue is still created even if the /user lookup fails (unassigned), export doesn't die",
              len(issue_calls) == 1 and "assignees" not in issue_calls[0][2],
              f"issue_calls={issue_calls}")

    print("=" * 60)
    print(f"passed {_pass} / failed {_fail}")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
