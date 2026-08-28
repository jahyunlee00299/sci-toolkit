#!/usr/bin/env python3
"""Regression test for doctor.py's credentials-divergence check.

Run: python tests/test_credentials_divergence.py   (exit 0 = pass)

[260810] Issue #3 (from a real installer's report): even after registering
a token in config/credentials.json, automation that reads the pre-existing
shared secrets store never sees that value. doctor.py reported 11/11 OK and
still missed this branch — this check exists specifically to catch that gap.

[260822] The shared store moved from ~/.claude/secrets.json to
~/.secrets/secrets.json (C-66). This test originally **wrote to, deleted,
and restored the user's actual secrets path directly** — it happened to
avoid disaster only because that path was empty at the time; the design
itself was dangerous. Now it redirects Path.home() to a temp directory so
the real home is never touched. Since both candidate paths are checked,
clearing only one of them cannot reproduce the "store absent" branch.
"""
import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path
from unittest import mock

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

spec = importlib.util.spec_from_file_location(
    "doctor", str(Path(__file__).resolve().parent.parent / "doctor.py"))
doctor = importlib.util.module_from_spec(spec)
sys.modules["doctor"] = doctor
spec.loader.exec_module(doctor)

_pass = 0
_fail = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global _pass, _fail
    if cond:
        _pass += 1
        print(f"  PASS  {name}")
    else:
        _fail += 1
        print(f"  FAIL  {name}" + (f" — {detail}" if detail else ""))


def main() -> int:
    print("Regression test for the credentials-divergence check")
    print("=" * 60)

    # Never touch the real home. Redirect the HOME environment variable so
    # both candidate paths doctor checks fall under this fake home — if only
    # one were cleared, a real file sitting at the other would leak in and
    # the "store absent" case couldn't be reproduced.
    # Why redirect HOME/USERPROFILE instead of Path.home(): doctor uses
    # Path("~/...").expanduser(), and expanduser goes through
    # os.path.expanduser -> reads the environment variable directly, not
    # through Path.home().
    with tempfile.TemporaryDirectory() as home_td:
        fake_home = Path(home_td)
        (fake_home / ".claude").mkdir()
        (fake_home / ".secrets").mkdir()
        secrets_paths = [
            fake_home / ".secrets" / "secrets.json",
            fake_home / ".claude" / "secrets.json",
        ]
        # Write to only the canonical (new) path. Leave the old path absent.
        real_secrets = secrets_paths[0]

        def _clear_secrets() -> None:
            for sp in secrets_paths:
                sp.unlink(missing_ok=True)

        fake_env = {"HOME": str(fake_home), "USERPROFILE": str(fake_home)}
        with mock.patch.dict("os.environ", fake_env), \
             tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = root / "config"
            cfg.mkdir()

            print("\n[1] no credentials.json -> OK (nothing to check)")
            r = doctor.check_credentials_divergence(root)
            check("no credentials.json -> OK", r.status == doctor.STATUS_OK, r.message)

            print("\n[2] no registered services (ENV placeholder only) -> OK")
            (cfg / "credentials.json").write_text(
                json.dumps({"notion": {"token": "ENV:SCITK_NOTION_TOKEN_NONEXISTENT_XYZ"}}),
                encoding="utf-8")
            r = doctor.check_credentials_divergence(root)
            check("unset ENV placeholder not counted as registered",
                  r.status == doctor.STATUS_OK, r.message)

            print("\n[3] registered + secrets.json itself absent -> WARN")
            (cfg / "credentials.json").write_text(
                json.dumps({"notion": {"token": "ntn_real_value_not_env"}}),
                encoding="utf-8")
            _clear_secrets()
            r = doctor.check_credentials_divergence(root)
            check("secrets.json absent -> WARN", r.status == doctor.STATUS_WARN, r.message)

            print("\n[4] registered + secrets.json present but missing the matching key -> WARN")
            real_secrets.write_text(json.dumps({"GITHUB_PAT": "x"}), encoding="utf-8")
            r = doctor.check_credentials_divergence(root)
            check("secrets.json missing matching key -> WARN",
                  r.status == doctor.STATUS_WARN, r.message)
            check("WARN message names the correct key mapping",
                  "NOTION_TOKEN" in r.message, r.message)

            print("\n[5] registered + secrets.json has the matching key -> OK")
            real_secrets.write_text(json.dumps({"NOTION_TOKEN": "x"}), encoding="utf-8")
            r = doctor.check_credentials_divergence(root)
            check("matching key present -> OK", r.status == doctor.STATUS_OK, r.message)

            print("\n[6] only some of several services mismatch -> WARN names only the mismatched one")
            (cfg / "credentials.json").write_text(
                json.dumps({
                    "notion": {"token": "ntn_real"},
                    "asana": {"token": "asana_real"},
                }),
                encoding="utf-8")
            real_secrets.write_text(json.dumps({"NOTION_TOKEN": "x"}), encoding="utf-8")
            r = doctor.check_credentials_divergence(root)
            check("partial mismatch -> WARN", r.status == doctor.STATUS_WARN, r.message)
            check("only the missing service is named (notion not flagged)",
                  "asana" in r.message and "notion" not in r.message.split("registered")[0],
                  r.message)

            print("\n[7] malformed JSON -> WARN (without crashing)")
            (cfg / "credentials.json").write_text("{ not valid json", encoding="utf-8")
            r = doctor.check_credentials_divergence(root)
            check("malformed JSON doesn't crash", r.status == doctor.STATUS_WARN, r.message)

            print("\n[8] an ENV variable that is actually set -> counted as registered")
            (cfg / "credentials.json").write_text(
                json.dumps({"github": {"token": "ENV:SCITK_TEST_GH_TOKEN_ZZZ"}}),
                encoding="utf-8")
            _clear_secrets()
            with mock.patch.dict("os.environ", {"SCITK_TEST_GH_TOKEN_ZZZ": "ghp_fake"}):
                r = doctor.check_credentials_divergence(root)
            check("set ENV var counted as registered -> WARN (no secrets.json)",
                  r.status == doctor.STATUS_WARN, r.message)

    # TemporaryDirectory tears down the fake home entirely -- no restore logic needed.

    print("=" * 60)
    print(f"pass {_pass} / fail {_fail}")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
