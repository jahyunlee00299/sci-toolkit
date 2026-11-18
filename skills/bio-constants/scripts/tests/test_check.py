import tempfile
import unittest
from pathlib import Path

from biodb import check, thermo
from biodb.errors import BlindError

REC = {"mass_da": 44136.0, "length": 401}


def fake_fetch(source, ident):
    if ident == "DOWN":
        raise BlindError("network")
    return dict(REC)


def run_text(text, **kw):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "c.toml"
        p.write_text(text, encoding="utf-8")
        return check.run(p, **kw)


class CheckTests(unittest.TestCase):
    def test_empty_file_is_blind(self):
        code, lines = run_text("")
        self.assertEqual(code, 2)

    def test_unreadable_is_blind(self):
        code, _ = check.run(Path("nope-not-here.toml"))
        self.assertEqual(code, 2)

    def test_mismatch_beats_blind(self):
        txt = ('[[claim]]\nname="a"\nsource="uniprot"\nid="X"\nfield="mass"\nclaimed="45100"\nunit="Da"\n'
               '[[claim]]\nname="b"\nsource="uniprot"\nid="DOWN"\nfield="mass"\nclaimed="1"\nunit="Da"\n')
        code, lines = run_text(txt, fetch=fake_fetch)
        self.assertEqual(code, 1)
        self.assertIn("mismatch=1", lines[-1])
        self.assertIn("blind=1", lines[-1])

    def test_all_match_and_note(self):
        txt = ('[[claim]]\nname="a"\nsource="uniprot"\nid="X"\nfield="mass"\nclaimed="44136"\nunit="Da"\nnote="n1"\n')
        code, lines = run_text(txt, fetch=fake_fetch)
        self.assertEqual(code, 0)
        self.assertIn("# n1", lines[0])

    def test_missing_unit_is_blind_not_pass(self):
        txt = '[[claim]]\nname="a"\nsource="uniprot"\nid="X"\nfield="mass"\nclaimed="44136"\n'
        code, _ = run_text(txt, fetch=fake_fetch)
        self.assertEqual(code, 2)

    def test_thermo_claim(self):
        txt = ('[[claim]]\nname="t"\nreaction="A = B"\npH=7.5\nionic_strength=0.25\ntemperature=298.15\npMg=3.0\n'
               'claimed_keq=0.043\n')
        dg = lambda r, c: {"dg": 7.8, "err": 5.7}
        code, lines = run_text(txt, dg_fn=dg)
        self.assertEqual(code, 0)
        bad = txt.replace("0.043", "0.9")
        code, _ = run_text(bad, dg_fn=dg)
        self.assertEqual(code, 1)

    def test_thermo_missing_condition_is_blind(self):
        txt = '[[claim]]\nname="t"\nreaction="A = B"\npH=7.5\nclaimed_keq=0.043\n'
        code, _ = run_text(txt, dg_fn=lambda r, c: {"dg": 1, "err": 1})
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()


class PackageRouteTests(unittest.TestCase):
    COND = thermo.Conditions(7.5, 0.25, 298.15, 3.0)

    def _run(self, **proc):
        from types import SimpleNamespace
        from unittest import mock
        ok = {"installed": True, "cache_ok": True, "reason": None, "cache_path": "x"}
        with mock.patch.object(thermo, "package_status", return_value=ok), \
                mock.patch.object(thermo, "_python_with_package", return_value="py"), \
                mock.patch.object(thermo.subprocess, "run", return_value=SimpleNamespace(**proc)):
            return thermo.package_dg("A = B", self.COND)

    def test_parses_json_from_child(self):
        r = self._run(returncode=0, stdout='noise\n{"dg": 7.8, "err": 1.2}\n', stderr="")
        self.assertEqual((r["dg"], r["err"]), (7.8, 1.2))

    def test_child_error_is_blind(self):
        with self.assertRaises(BlindError):
            self._run(returncode=1, stdout="", stderr="Traceback\nValueError: bad")

    def test_garbage_stdout_is_blind(self):
        with self.assertRaises(BlindError):
            self._run(returncode=0, stdout="not json", stderr="")
