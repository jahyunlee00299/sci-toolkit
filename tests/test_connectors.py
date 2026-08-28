#!/usr/bin/env python3
"""Regression test for scripts/connectors/ — no credentials, no network.

Run: python tests/test_connectors.py   (exit 0 = pass)

Why this file exists
---------------------
Connectors are **the only code in this repository that reaches outward**
(sending mail, opening PRs, writing to Asana/Notion, calendar invites,
appending sheet rows). Yet as of the 260816 audit, none of them had a
dedicated test — the argparse surface, the dry-run payload, and the --write
gate all sat outside the regression safety net. When outbound code breaks
silently, it's hard to undo.

What this checks (all offline)
--------------------------------
1. Does each connector's argparse actually parse — do the subcommand names
   match the docs?
2. Does a write command send **absolutely nothing** without --write
   (dry-run isolation)?
3. Does --write actually take the send path (i.e. the gate isn't locked
   backwards)?
4. Does the no-token behavior differ **as intended** per command?

Point 4 is the heart of this file. Before 260816, github/notion/notion_db
required a token even for a preview with no --write (main() called
cred.require unconditionally), which made testing impossible without
credentials. Now the rule is unified with asana's — with one deliberate
exception (notion_db add-row), which requires a token because schema
cross-checking is the entire reason the preview exists.

Network access is blocked by monkeypatching http()/urlopen. If a test
accidentally sends a real request, that itself is caught as a failure.
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
    """Load a connector module.

    Connectors pull in their sibling module `_credentials` with a plain
    import — a structure that assumes it's run directly as a script. Loading
    it in a test by file path wouldn't find that sibling, so add the
    connectors directory to sys.path.
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
    """Immediately fail if a dry-run touches the network."""


def _forbid_network(*a, **k):
    raise NetworkTouched("the dry-run path called the network")


# ─────────────────────────────────────────────────────────────
print("\n[1] argparse surface — do the documented subcommands actually parse")

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
        check(f"{name} load", False, f"{type(exc).__name__}: {exc}")
        continue
    check(f"{name} load", True)

    mod = MODS[name]
    if not hasattr(mod, "build_parser"):
        check(f"{name}.build_parser exists", False, "no such function")
        continue
    parser = mod.build_parser()
    check(f"{name}.build_parser exists", isinstance(parser, argparse.ArgumentParser))

    # Pull the subcommand names directly from the parser (grounded in code, not docs)
    actions = [a for a in parser._actions
               if isinstance(a, argparse._SubParsersAction)]
    got = sorted(actions[0].choices.keys()) if actions else []
    missing = [c for c in subcmds if c not in got]
    check(f"{name} has {len(subcmds)} subcommand(s)", not missing,
          f"missing: {missing} / actual: {got}")


# ─────────────────────────────────────────────────────────────
print("\n[2] dry-run isolation — no network touched without --write")

# (module, function name, args, string that must appear in the preview)
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
    # The Google connectors go out through _google_auth rather than http() — handled separately below.
]

# The two Google connectors: network is blocked at a different point
# (gauth.api_post/api_get), so run them separately.
GOOGLE_DRYRUN = [
    ("calendar_connector", "cmd_add_event",
     dict(calendar="primary", summary="Meeting", start="2026-08-20T14:00:00",
          end="2026-08-20T15:00:00", description=None, location=None,
          attendee=None, write=False),
     "Meeting"),
    ("sheets_connector", "cmd_append",
     dict(sheet="SID", range="S1!A:C", row="a,b,c", write=False),
     "a"),
]

for mod_name, fn_name, kwargs, must_contain in DRYRUN_CASES:
    mod = MODS.get(mod_name)
    if mod is None or not hasattr(mod, fn_name):
        check(f"{mod_name}.{fn_name} dry-run", False, "no such function")
        continue

    args = argparse.Namespace(**kwargs)
    buf = io.StringIO()
    try:
        # Turn http into a bomb, so the test fails if it's ever called
        with mock.patch.object(mod, "http", _forbid_network):
            with redirect_stdout(buf):
                mod.__dict__[fn_name](args, None)   # token=None
        out = buf.getvalue()
        ok = "[DRY-RUN]" in out and must_contain in out
        check(f"{mod_name}.{fn_name} — preview without a token", ok,
              f"missing '[DRY-RUN]'/{must_contain!r} in output: {out[:160]!r}")
    except NetworkTouched as exc:
        check(f"{mod_name}.{fn_name} — preview without a token", False, str(exc))
    except Exception as exc:  # noqa: BLE001
        check(f"{mod_name}.{fn_name} — preview without a token", False,
              f"{type(exc).__name__}: {exc}")


# ─────────────────────────────────────────────────────────────
print("\n[2b] Google connector dry-run — doesn't even look up a token")

# For the two Google connectors, auth is a file read, so if dry-run calls
# access_token() the preview would crash for anyone without a token file.
# So the bar here is stronger than "doesn't touch the network" — it checks
# that access_token() itself is never called.
for mod_name, fn_name, kwargs, must_contain in GOOGLE_DRYRUN:
    mod = MODS.get(mod_name)
    if mod is None or not hasattr(mod, fn_name):
        check(f"{mod_name}.{fn_name} dry-run", False, "no such function")
        continue

    touched = []

    def _spy_token(*a, _t=touched, **k):
        _t.append("access_token")
        raise AssertionError("the dry-run looked up a token")

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
        check(f"{mod_name}.{fn_name} — preview without a token", ok,
              f"touched={touched} out={out[:140]!r}")
    except NetworkTouched as exc:
        check(f"{mod_name}.{fn_name} — preview without a token", False, str(exc))
    except Exception as exc:  # noqa: BLE001
        check(f"{mod_name}.{fn_name} — preview without a token", False,
              f"{type(exc).__name__}: {exc}")

# A calendar invite is an outward-facing action — the preview must say so explicitly.
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
    check("calendar add-event — warns 'outward' when there's an attendee", "outward" in out,
          "an invite is going out but the preview doesn't warn about it")

# Sheets must stay additive-only — a modify/delete subcommand would be a policy violation.
_sh = MODS.get("sheets_connector")
if _sh is not None:
    subs = [a for a in _sh.build_parser()._actions
            if isinstance(a, argparse._SubParsersAction)]
    names = set(subs[0].choices) if subs else set()
    banned = names & {"update", "delete", "clear", "set", "write-cell"}
    check("sheets — no modify/delete subcommand (additive-only)", not banned,
          f"a forbidden subcommand appeared: {sorted(banned)}")


print("\n[3] --write gate — actually takes the send path when present")

# If the gate is locked backwards (always dry-run), the connector goes
# silently inert. Here we fake out http and check only "was it called" —
# nothing is actually sent.
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
        check(f"{mod_name}.{fn_name} --write", False, "no such function")
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
        check(f"{mod_name}.{fn_name} — --write triggers a send call", wrote,
              f"no write method was called: {calls}")
        check(f"{mod_name}.{fn_name} — --write leaves no DRY-RUN text",
              "[DRY-RUN]" not in buf.getvalue())
    except Exception as exc:  # noqa: BLE001
        check(f"{mod_name}.{fn_name} — --write triggers a send call", False,
              f"{type(exc).__name__}: {exc}")


# ─────────────────────────────────────────────────────────────
print("\n[4] token gating — main() requires it differently per command type")

# Before 260816: github/notion/notion_db called cred.require unconditionally
# in main(), so even a preview without --write required a token. Only asana
# had the exception handled. Now there's a single rule — "write command +
# no --write" means no token is required.
TOKEN_FREE_DRYRUN = [
    ("github_connector", ["open-pr", "--repo", "me/r", "--head", "h",
                          "--base", "main", "--title", "t"]),
    ("notion_connector", ["append", "--page-id", "p", "--text", "x"]),
    ("asana_connector",  ["add-task", "--workspace", "ws-1", "--name", "n"]),
]

for mod_name, argv in TOKEN_FREE_DRYRUN:
    mod = MODS.get(mod_name)
    if mod is None:
        check(f"{mod_name} main() dry-run needs no token", False, "no such module")
        continue

    required = []

    def _spy_require(*a, _r=required, **k):
        _r.append(a)
        raise SystemExit("[test] a token was required")

    buf = io.StringIO()
    try:
        with mock.patch.object(mod, "http", _forbid_network), \
             mock.patch.object(mod.cred, "require", _spy_require), \
             mock.patch.object(sys, "argv", [mod_name] + argv):
            with redirect_stdout(buf):
                mod.main()
        check(f"{mod_name} main() dry-run needs no token", not required,
              f"cred.require was called: {required}")
    except SystemExit as exc:
        check(f"{mod_name} main() dry-run needs no token", False,
              f"SystemExit: {exc}")
    except NetworkTouched as exc:
        check(f"{mod_name} main() dry-run needs no token", False, str(exc))
    except Exception as exc:  # noqa: BLE001
        check(f"{mod_name} main() dry-run needs no token", False,
              f"{type(exc).__name__}: {exc}")

# The deliberate exception — add-row requires a token because schema
# cross-checking is the entire reason the preview exists.
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
    check("notion_db add-row — refuses even a preview without a token (deliberate exception)", raised,
          "it passed without a token — presenting an unvalidated payload as validated")

# A write command + --write must always require a token (prevents a weakened gate)
print("\n[4b] adversarial case — --write always requires a token")
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
    check(f"{mod_name} --write requires a token", bool(required),
          "entered the write path without a token — the gate has weakened")


# ─────────────────────────────────────────────────────────────
print("\n[5] mail — draft/reply never call SMTP at all")

# The mechanical basis for the draft-first policy (AGENTS.md §9). The moment
# these two commands call SMTP, "stops at draft" is broken.
_mail = MODS.get("mail_connector")
if _mail is None:
    check("mail_connector load", False)
else:
    src = (CONNECTORS / "mail_connector.py").read_text(encoding="utf-8")
    body = src[src.find("def cmd_draft"):src.find("def cmd_send")]
    check("no smtplib call in the cmd_draft/cmd_reply section",
          "smtplib" not in body and "SMTP" not in body,
          "found a trace of SMTP in the draft/reply path")
    check("send requires interactive confirmation", "isatty" in src,
          "looks like it could send even non-interactively")


# ─────────────────────────────────────────────────────────────
print("\n[6] Asana sanitize_html — newlines are preserved as real \\n (issue #4)")

# The &#10; entity gets re-escaped by the Asana sanitizer into &amp;#10;,
# which shows up as a literal on screen (measured 260816). Only a real LF
# byte renders as a line break, so the moment sanitize_html substitutes a
# newline with an entity, this regression comes back.
_asana = MODS.get("asana_connector")
if _asana is None or not hasattr(_asana, "sanitize_html"):
    check("asana_connector.sanitize_html exists", False)
else:
    out = _asana.sanitize_html("line1\nline2\r\nline3")
    check("real newlines are not replaced with &#10;", "&#10;" not in out, repr(out))
    check("newline characters are preserved (CRLF normalized to LF)",
          out == "<body>line1\nline2\nline3</body>", repr(out))
    legacy = _asana.sanitize_html("a&#10;b")
    check("a legacy &#10; input is restored to a real newline",
          legacy == "<body>a\nb</body>", repr(legacy))
    check("<body> auto-wrapping is preserved",
          _asana.sanitize_html("x") == "<body>x</body>")


# ─────────────────────────────────────────────────────────────
print("\n" + "-" * 60)
print(f"passed {_pass} / failed {_fail}")
if _fail:
    print("\nFAIL — failed items:")
    for f in _failures:
        print(f"  - {f}")
    sys.exit(1)
print(f"ALL PASS — {len(EXPECTED)} connector(s) honor the offline contract")
sys.exit(0)
