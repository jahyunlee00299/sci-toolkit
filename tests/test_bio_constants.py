#!/usr/bin/env python3
"""bio-constants regression test: the skill's own offline suite plus its router wiring.

The skill ships replays of recorded public API responses, so this test never
touches the network. It also checks that the router names gate 7 and that the
example claims file parses.

Run:
    python -m pytest tests/test_bio_constants.py
"""
from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "bio-constants"


def test_skill_offline_suite_passes():
    r = subprocess.run([sys.executable, "-I", "-m", "unittest", "discover", "-s", str(SKILL / "scripts")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    assert r.returncode == 0, r.stderr[-2000:]
    assert "OK" in r.stderr


def test_example_claims_file_parses_and_carries_units():
    data = tomllib.loads((SKILL / "bio_claims.example.toml").read_text(encoding="utf-8"))
    claims = data["claim"]
    assert claims and all("unit" in c for c in claims)


def test_router_names_gate_seven():
    text = (ROOT / "skills" / "verification-gates" / "SKILL.md").read_text(encoding="utf-8")
    assert "`bio-constants`" in text and "⑦" in text

