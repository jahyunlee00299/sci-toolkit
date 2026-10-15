#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The verification gates are wired into doctor and into the agent routing - pytest style.

A router skill nobody reaches and a doctor check that always says OK are the same
failure: the gate exists on paper. These cases plant the broken state and require
the wiring to notice it.

  planted: no gate tool installed      -> WARN naming each install command, never OK
  planted: one tool missing            -> WARN naming exactly that tool
  all installed                        -> OK
  gate skills not shipped              -> OK (nothing to check)
  verification-gates SKILL.md          -> states exit 2 = BLIND and names all four tool skills
  AGENTS.md section 0                  -> routes "report any number" to verification-gates

Run: python -m pytest tests/test_gate_wiring.py -q
"""
from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from doctor_lib import checks_env  # noqa: E402
from doctor_lib.result import STATUS_OK, STATUS_WARN  # noqa: E402

TOOLS = ["compat_check", "fiducial", "provenance_check", "regress_check"]


def _patch(monkeypatch, installed):
    real = importlib.util.find_spec
    monkeypatch.setattr(checks_env.importlib.util, "find_spec",
                        lambda m, *a, **k: object() if m in installed else (None if m in TOOLS else real(m, *a, **k)))
    monkeypatch.setattr(checks_env.shutil, "which", lambda exe, *a, **k: None)


def test_none_installed_is_warn_not_ok(monkeypatch):
    _patch(monkeypatch, set())
    r = checks_env.check_gate_tools(ROOT)
    assert r.status == STATUS_WARN
    text = " ".join(r.details)
    for skill in ("compat-check", "fiducial", "provenance-check", "regress-check"):
        assert f"{skill} not installed" in text
    assert "pip install" in text


def test_one_missing_names_only_that_tool(monkeypatch):
    _patch(monkeypatch, {"compat_check", "fiducial", "provenance_check"})
    r = checks_env.check_gate_tools(ROOT)
    assert r.status == STATUS_WARN
    assert len(r.details) == 1 and "regress-check" in r.details[0]


def test_all_installed_is_ok(monkeypatch):
    _patch(monkeypatch, set(TOOLS))
    assert checks_env.check_gate_tools(ROOT).status == STATUS_OK


def test_gate_skills_absent_is_ok(tmp_path):
    assert checks_env.check_gate_tools(tmp_path).status == STATUS_OK


def test_router_states_blind_contract_and_names_every_gate():
    text = (ROOT / "skills" / "verification-gates" / "SKILL.md").read_text(encoding="utf-8")
    assert "Exit 2 is never" in text and "BLIND" in text
    for skill in ("compat-check", "provenance-check", "fiducial", "regress-check"):
        assert f"`{skill}`" in text, skill
        assert (ROOT / "skills" / skill / "SKILL.md").is_file(), skill


def test_agents_routes_number_reporting_to_the_router():
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    row = next(l for l in text.splitlines() if l.startswith("| Report any number"))
    assert "`verification-gates`" in row and "BLIND" in row
