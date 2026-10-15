#!/usr/bin/env python3
"""Checks the statusline-usage skill: both implementations print the same line.

The expectation table is shared: statusline.sh (bash) and statusline.ps1
(PowerShell) are each fed every fixture and must print exactly the listed line.
STATUSLINE_TZ_OFFSET_MIN=540 pins the reset times so the result does not depend
on the machine's timezone. An implementation that is not runnable here (no bash,
no PowerShell, or no .ps1 file) is skipped, not failed.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts"))  # shared helper: scripts/_stdio.py
from _stdio import force_utf8  # noqa: E402
force_utf8()

SKILL = Path(__file__).resolve().parents[1] / "skills" / "statusline-usage"
FIXTURES = SKILL / "tests" / "fixtures"

# (fixture file, exact expected line). Single source for every implementation.
EXPECTED = [
    ("stdin_full.json", "Opus 5.5 | ctx 96k/1M 10% | 5h 1% ~21:30 | 7d 53% ~Sat 07:00"),
    ("compact.json", "Opus 5.5 | ctx 96k/1M 10% | 5h 1% ~21:30 | 7d 53% ~Sat 07:00"),
    ("reordered_spaced.json", "Opus 5.5 | ctx 96k/1M 10% | 5h 1% ~21:30 | 7d 53% ~Sat 07:00"),
    ("no_rate_limits.json", "Opus 5.5 | ctx 96k/1M 10%"),
    ("no_context_window.json", "Opus 5.5 | 5h 1% ~21:30 | 7d 53% ~Sat 07:00"),
    ("no_resets_at.json", "Opus 5.5 | ctx 96k/1M 10% | 5h 1% | 7d 53% ~Sat 07:00"),
    ("pct_computed.json", "Opus 5.5 | ctx 50k/200k 25% | 5h 1% ~21:30 | 7d 53% ~Sat 07:00"),
    ("high_usage.json", "Opus 5.5 | !ctx 170k/200k 85% | !5h 80% ~21:30 | !7d 95% ~Sat 07:00"),
    ("float_percentages.json", "Opus 5.5 | ctx 12k/200k 12% | 5h 3% ~21:30 | 7d 79% ~Sat 07:00"),
    ("tokens_small.json", "Opus 5.5 | ctx 950/200k 5%"),
    ("size_only.json", "Opus 5.5 | ctx 500/1k 50%"),
    ("used_zero.json", "Opus 5.5 | ctx 0/1k 0%"),
    ("tokens_1_2M.json", "Opus 5.5 | ctx 1.2M/2M 61%"),
    ("tokens_1_9M.json", "Opus 5.5 | !ctx 1.9M/2M 99%"),
    ("empty.json", "claude"),
    ("invalid.json", "claude"),
]


def _bash_cmd(script: Path) -> list[str] | None:
    bash = shutil.which("bash")
    return [bash, str(script)] if bash else None


def _powershell_cmd(script: Path) -> list[str] | None:
    exe = shutil.which("powershell") or shutil.which("pwsh")
    if not exe or not script.exists():
        return None
    return [exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)]


IMPLEMENTATIONS = {
    "bash": (SKILL / "scripts" / "statusline.sh", _bash_cmd),
    "powershell": (SKILL / "scripts" / "statusline.ps1", _powershell_cmd),
}


def _run(impl: str, stdin_bytes: bytes, extra_env: dict[str, str] | None = None):
    script, builder = IMPLEMENTATIONS[impl]
    cmd = builder(script)
    if cmd is None:
        pytest.skip(f"{impl} implementation not runnable here")
    env = dict(os.environ, STATUSLINE_TZ_OFFSET_MIN="540")
    env.pop("STATUSLINE_WARN_PCT", None)
    env.update(extra_env or {})
    return subprocess.run(cmd, input=stdin_bytes, capture_output=True, env=env, timeout=60)


@pytest.mark.parametrize("impl", sorted(IMPLEMENTATIONS))
@pytest.mark.parametrize("fixture,expected", EXPECTED, ids=[f for f, _ in EXPECTED])
def test_fixture_line(impl, fixture, expected):
    proc = _run(impl, (FIXTURES / fixture).read_bytes())
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    assert proc.stdout.decode("utf-8", "replace").strip() == expected


@pytest.mark.parametrize("impl", sorted(IMPLEMENTATIONS))
def test_warn_threshold_env(impl):
    """STATUSLINE_WARN_PCT moves the '!' threshold (7d 53% warns at 50, not at 80)."""
    data = (FIXTURES / "stdin_full.json").read_bytes()
    proc = _run(impl, data, {"STATUSLINE_WARN_PCT": "50"})
    assert proc.stdout.decode("utf-8", "replace").strip() == (
        "Opus 5.5 | ctx 96k/1M 10% | 5h 1% ~21:30 | !7d 53% ~Sat 07:00")


@pytest.mark.parametrize("impl", sorted(IMPLEMENTATIONS))
@pytest.mark.parametrize("warn", ["80.5", "abc", ""])
def test_invalid_warn_threshold_falls_back_to_80(impl, warn):
    """A non-integer STATUSLINE_WARN_PCT is ignored: 53% stays unmarked, 85% is marked."""
    proc = _run(impl, (FIXTURES / "high_usage.json").read_bytes(), {"STATUSLINE_WARN_PCT": warn})
    assert proc.stdout.decode("utf-8", "replace").strip() == (
        "Opus 5.5 | !ctx 170k/200k 85% | !5h 80% ~21:30 | !7d 95% ~Sat 07:00")


@pytest.mark.parametrize("impl", sorted(IMPLEMENTATIONS))
def test_negative_offset_crosses_day(impl):
    """-600 min east of UTC: 7d reset lands on Fri, 5h reset on 11:30 the same day."""
    data = (FIXTURES / "stdin_full.json").read_bytes()
    proc = _run(impl, data, {"STATUSLINE_TZ_OFFSET_MIN": "-600"})
    assert proc.stdout.decode("utf-8", "replace").strip() == (
        "Opus 5.5 | ctx 96k/1M 10% | 5h 1% ~02:30 | 7d 53% ~Fri 12:00")


def test_bash_script_is_executable_in_git():
    out = subprocess.run(
        ["git", "-C", str(SKILL), "ls-files", "-s", "scripts/statusline.sh"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if out.returncode != 0 or not out.stdout.strip():
        pytest.skip("not inside a git checkout")
    assert out.stdout.startswith("100755"), out.stdout
