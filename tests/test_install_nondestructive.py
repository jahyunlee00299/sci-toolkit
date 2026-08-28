#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Verify that install.py does not destroy an existing installation.

Background (measured, 2026-08-07):
  When the target skill folder already existed, install.py wiped it entirely
  with `shutil.rmtree(dst)` before running copytree. As a result, files that
  existed only in the user's runtime —
    7 files under manuscript-pipeline/scripts/, 3 under
    endnote-citation-injection/ (including safe_refs_update.py), 3 under
    scientific-validation/scripts/ —
  were all deleted by a single install.

  Same failure class as the 260727 incident
  (incident_pii_sanitize_killed_runtime_skill): "overwrite" actually meant
  "delete and recreate", and nobody had measured that.

The contract this test enforces:
  1. A file that exists only at the destination, not in the distribution,
     must still be there after install.
  2. A file that exists in the distribution must land at the destination
     (install must not be a no-op).
  3. When both sides have the same name, the distribution's copy wins (since
     the point is to update).
  4. --force gives up guarantee 1 and reverts to the old behavior (full
     replace) — only when explicitly requested.

The cases come from the contract above, not from the implementation. Do not
fix the implementation to make a case pass — only change this file when the
contract itself changes.
"""
from __future__ import annotations

import sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

import importlib.util
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALLER = ROOT / "install" / "install.py"

_fail = 0
_pass = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global _fail, _pass
    if cond:
        _pass += 1
        print(f"  PASS  {name}")
    else:
        _fail += 1
        print(f"  FAIL  {name}" + (f"  — {detail}" if detail else ""))


def run_installer(dest: Path, skills: str, *extra: str) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(INSTALLER), "--skills", skills,
           "--dest", str(dest), "--apply", *extra]
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=180)


def seed_destination(dest: Path, skill: str) -> tuple[Path, Path]:
    """Plant 2 files at the destination that 'the user already had'.

    - local_only: not in the distribution -> must survive
    - shared:     also in the distribution -> must be updated to the distribution's content
    """
    skill_dir = dest / skill
    (skill_dir / "scripts").mkdir(parents=True, exist_ok=True)
    local_only = skill_dir / "scripts" / "user_local_tool.py"
    local_only.write_text("# A script that exists only in the user's runtime\n", encoding="utf-8")
    shared = skill_dir / "SKILL.md"
    shared.write_text("STALE — must be replaced with the distribution's content\n", encoding="utf-8")
    return local_only, shared


def main() -> int:
    if not INSTALLER.exists():
        print(f"[error] Installer not found: {INSTALLER}")
        return 1

    # Pin to a skill this package actually distributes, with no dependencies.
    # (xlsx used to be used here, but it's Anthropic-owned and was dropped
    #  from the package — testing against an external skill would break this
    #  test even when the package itself is fine.)
    skill = "code-quality"
    src_skill_md = ROOT / "skills" / skill / "SKILL.md"
    if not src_skill_md.exists():
        print(f"[error] Test target skill is missing: {src_skill_md}")
        return 1

    print("install.py non-destructive install verification")
    print("=" * 60)

    # ── Cases 1-3: a default install must be non-destructive ────────────
    print("\n[default install] preserves existing files + applies the distribution's content")
    with tempfile.TemporaryDirectory() as td:
        dest = Path(td) / "skills"
        local_only, shared = seed_destination(dest, skill)
        proc = run_installer(dest, skill)

        check("installer exits cleanly", proc.returncode == 0,
              f"exit={proc.returncode} stderr={proc.stderr[-300:]}")

        # Contract 1 — a file that existed only at the destination survives
        check("an existing file not in the distribution is preserved", local_only.exists(),
              f"deleted: {local_only}")

        # Contract 2 — a distribution file actually lands
        installed = dest / skill / "SKILL.md"
        check("distribution file is installed at the destination", installed.exists())

        # Contract 3 — same name: the distribution wins
        if installed.exists():
            got = installed.read_text(encoding="utf-8", errors="replace")
            check("a same-name file is updated to the distribution's content",
                  "STALE" not in got,
                  "old content is still there (install was a no-op)")

    # ── Case 5: does .distignore also apply to the install path? ────────
    # .distignore used to be read only by make_checksums.py, not install.py.
    # In other words, a "do not distribute" declaration only scoped the
    # manifest and had no effect on the actual copy — the rule was declared
    # but never wired in.
    print("\n[.distignore] a do-not-distribute file must not get installed")
    planted = ROOT / "skills" / skill / "secrets.json"
    planted_existed = planted.exists()
    if not planted_existed:
        planted.write_text('{"token": "should-never-be-installed"}\n', encoding="utf-8")
    try:
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "skills"
            proc = run_installer(dest, skill)
            check("installer exits cleanly (.distignore path)", proc.returncode == 0,
                  f"exit={proc.returncode} stderr={proc.stderr[-300:]}")
            check("secrets.json is not installed",
                  not (dest / skill / "secrets.json").exists(),
                  ".distignore does not apply to the install path")
            check("a normal file from the same skill is still installed",
                  (dest / skill / "SKILL.md").exists(),
                  "the exclusion rule over-matched and dropped a normal file too")
    finally:
        if not planted_existed and planted.exists():
            planted.unlink()

    # ── Case 4: --force reverts to the old behavior (full replace) ──────
    print("\n[--force] full replace only when explicitly requested")
    with tempfile.TemporaryDirectory() as td:
        dest = Path(td) / "skills"
        local_only, _ = seed_destination(dest, skill)
        proc = run_installer(dest, skill, "--force")

        check("--force install exits cleanly", proc.returncode == 0,
              f"exit={proc.returncode} stderr={proc.stderr[-300:]}")
        check("--force removes the existing file", not local_only.exists(),
              "still present despite --force")

    # ── Case 6: environment-appropriate default when --dest is omitted ──
    # It used to be unconditionally ~/.claude/skills. That folder means
    # nothing to a Codex user (no concept of a skill registry there), so it
    # would silently install into the wrong place.
    print("\n[--dest omitted] decide from the environment, and say where it went")
    spec = importlib.util.spec_from_file_location("installer", INSTALLER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["installer"] = mod
    try:
        spec.loader.exec_module(mod)
    except SystemExit:
        pass
    if hasattr(mod, "default_dest"):
        dest, why = mod.default_dest()
        check("returns a path", bool(str(dest)), f"dest={dest}")
        check("returns the reasoning along with it", bool(why), "no explanation for why that path")
        check("last path component is skills", Path(dest).name == "skills", f"dest={dest}")
    else:
        check("default_dest exists", False, "install.py has no such function")

    proc = subprocess.run(
        [sys.executable, str(INSTALLER), "--skills", skill],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    check("exits cleanly even when omitted", proc.returncode == 0, proc.stderr[-200:])
    check("prints where it installed to", "자동 결정" in proc.stdout,
          "the user proceeds without knowing where it was installed")

    print("=" * 60)
    print(f"passed {_pass} / failed {_fail}")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
