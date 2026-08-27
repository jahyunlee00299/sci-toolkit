#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression tests for doctor.py's dead-automation check.

The failure this guards against: an automation breaks, keeps running, keeps
writing "nothing new" to its log, and nobody notices because zero output is
indistinguishable from a healthy idle state. The check must therefore count
the produced *artifact*, never the log's mtime.

Two directions matter equally and both are pinned here:
  MUST WARN  -- stale, zero-byte, missing, malformed (a real corpse)
  MUST NOT   -- fresh output, an old sibling beside a new file, no config
                at all (false alarms would train the user to ignore doctor)
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import doctor  # noqa: E402


class DeadAutomationCheck(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="sci_deadauto_"))
        (self.tmp / "config").mkdir()
        self.art = self.tmp / "art"
        self.art.mkdir()

    def _cfg(self, entries) -> None:
        (self.tmp / "config" / "automations.json").write_text(
            json.dumps({"automations": entries}, ensure_ascii=False), encoding="utf-8"
        )

    def _run(self):
        return doctor.check_dead_automation(self.tmp)

    def _make(self, name: str, size: int = 100, age_days: float = 0.0) -> Path:
        p = self.art / name
        p.write_text("x" * size, encoding="utf-8")
        if age_days:
            t = time.time() - age_days * 86400
            os.utime(p, (t, t))
        return p

    # ---- must NOT warn (false alarms erode trust in doctor) --------------

    def test_unconfigured_is_ok(self):
        """No config at all: a user who declared nothing has nothing stale."""
        self.assertEqual(self._run().status, doctor.STATUS_OK)

    def test_fresh_artifact_is_ok(self):
        self._make("out.md")
        self._cfg([{"name": "fresh", "artifact": str(self.art / "*.md"), "max_age_days": 7}])
        self.assertEqual(self._run().status, doctor.STATUS_OK)

    def test_newest_wins_over_stale_sibling(self):
        """An old file beside a new one must not read as dead."""
        self._make("old.md", age_days=90)
        self._make("new.md")
        self._cfg([{"name": "mixed", "artifact": str(self.art / "*.md"), "max_age_days": 7}])
        self.assertEqual(self._run().status, doctor.STATUS_OK)

    def test_within_threshold_is_ok(self):
        self._make("out.md", age_days=6)
        self._cfg([{"name": "edge", "artifact": str(self.art / "out.md"), "max_age_days": 7}])
        self.assertEqual(self._run().status, doctor.STATUS_OK)

    # ---- must WARN (the corpses) ----------------------------------------

    def test_stale_artifact_warns(self):
        self._make("out.md", age_days=30)
        self._cfg([{"name": "stale", "artifact": str(self.art / "out.md"), "max_age_days": 7}])
        r = self._run()
        self.assertEqual(r.status, doctor.STATUS_WARN)
        self.assertIn("stale", r.message)

    def test_zero_byte_artifact_warns(self):
        """The 'wired but never fired' signature: file created, never written."""
        (self.art / "sink.log").write_bytes(b"")
        self._cfg([{"name": "sink", "artifact": str(self.art / "sink.log"), "max_age_days": 7}])
        r = self._run()
        self.assertEqual(r.status, doctor.STATUS_WARN)
        self.assertIn("empty", r.message)

    def test_below_min_bytes_warns(self):
        (self.art / "sink.log").write_bytes(b"tiny")
        self._cfg([{"name": "sink", "artifact": str(self.art / "sink.log"),
                    "max_age_days": 7, "min_bytes": 1024}])
        self.assertIn("empty", self._run().message)

    def test_missing_artifact_warns(self):
        self._cfg([{"name": "never ran", "artifact": str(self.tmp / "nope/*.json"),
                    "max_age_days": 3}])
        self.assertIn("missing", self._run().message)

    def test_malformed_entries_warn_individually(self):
        good = self._make("out.md")
        self._cfg([
            {"name": "no artifact", "max_age_days": 3},
            {"name": "bad age", "artifact": str(good), "max_age_days": "soon"},
            {"name": "neg age", "artifact": str(good), "max_age_days": -1},
            "not-an-object",
        ])
        r = self._run()
        self.assertEqual(r.status, doctor.STATUS_WARN)
        self.assertEqual(len(r.details), 4)

    def test_malformed_json_warns_not_crashes(self):
        (self.tmp / "config" / "automations.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(self._run().status, doctor.STATUS_WARN)

    def test_empty_list_warns(self):
        self._cfg([])
        self.assertEqual(self._run().status, doctor.STATUS_WARN)

    def test_never_fails_only_warns(self):
        """A distribution must not FAIL on someone else's broken automation."""
        self._cfg([{"name": "dead", "artifact": str(self.tmp / "nope"), "max_age_days": 1}])
        self.assertNotEqual(self._run().status, doctor.STATUS_FAIL)

    # ---- wiring ----------------------------------------------------------

    def test_check_is_registered_in_doctor(self):
        """A gate that never runs is a gate nobody can trust."""
        results = doctor.run_all_checks(ROOT, quick=True)
        self.assertIn("Dead automation (artifact freshness)", [r.name for r in results])

    def test_example_config_exists_and_parses(self):
        ex = ROOT / "config" / "automations.example.json"
        self.assertTrue(ex.is_file(), "config/automations.example.json missing")
        data = json.loads(ex.read_text(encoding="utf-8"))
        self.assertIsInstance(data.get("automations"), list)
        for item in data["automations"]:
            self.assertIn("artifact", item)
            self.assertIn("max_age_days", item)


if __name__ == "__main__":
    unittest.main(verbosity=2)
