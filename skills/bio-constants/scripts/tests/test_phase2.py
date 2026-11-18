import contextlib
import io
import math
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from biodb import bio_const, http, rhea, thermo  # noqa: E402
from biodb.errors import BlindError  # noqa: E402
import fixture_transport as ft  # noqa: E402

RX = "(S)-malate + NAD+ = oxaloacetate + NADH"
COND = thermo.Conditions(7.5, 0.25, 298.15, 3.0)


class Base(unittest.TestCase):
    def setUp(self):
        self._t, self._i = http.TRANSPORT, http.MIN_INTERVAL_S
        http.TRANSPORT, http.MIN_INTERVAL_S = ft.replay, 0.0

    def tearDown(self):
        http.TRANSPORT, http.MIN_INTERVAL_S = self._t, self._i

    def cli(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = bio_const.main(list(argv))
        return code, out.getvalue().strip()


class TestRhea(Base):
    def test_by_rhea_id_matches_documented_record(self):
        (r,) = rhea.fetch(rhea_id="RHEA:21432")
        self.assertEqual(r["equation"], "(S)-malate + NAD(+) = oxaloacetate + NADH + H(+)")
        self.assertEqual(r["ec"], ["1.1.1.37", "1.1.1.299"])
        self.assertEqual(r["chebi"], ["CHEBI:15589", "CHEBI:57540", "CHEBI:16452", "CHEBI:57945", "CHEBI:15378"])
        self.assertEqual((r["status"], r["balanced"], r["transport"]), ("approved", True, False))
        self.assertIn("undirected", r["direction"])

    def test_by_ec_mdh_and_fdh(self):
        self.assertEqual(rhea.fetch(ec="1.1.1.37")[0]["rhea_id"], "RHEA:21432")
        self.assertEqual(rhea.fetch(ec="1.17.1.9")[0]["equation"], "formate + NAD(+) = CO2 + NADH")

    def test_transport_flag(self):
        (r,) = rhea.fetch(ec="7.1.1.1")
        self.assertTrue(r["transport"])
        self.assertIn("(in)", r["equation"])

    def test_directional_and_unknown_are_blind(self):
        for kw in ({"rhea_id": "RHEA:21433"}, {"ec": "9.9.9.9"}):
            with self.assertRaises(BlindError):
                rhea.fetch(**kw)

    def test_bad_input_blind(self):
        for kw in ({"rhea_id": "abc"}, {"ec": "1.2"}, {}, {"rhea_id": "1", "ec": "1.1.1.1"}):
            with self.assertRaises(BlindError):
                rhea.fetch(**kw)

    def test_parse_rejects_malformed_row(self):
        with self.assertRaises(BlindError):
            rhea.parse("h\nRHEA:1\tonly two", '{"results": []}')


class TestThermo(Base):
    def test_keq_from_dg_is_exact_formula(self):
        self.assertAlmostEqual(thermo.keq_from_dg(7.8, 298.15),
                               math.exp(-7.8 / (8.314462618e-3 * 298.15)), places=12)
        self.assertAlmostEqual(thermo.keq_from_dg(0.0, 310.0), 1.0)

    def test_web_reproduces_documented_dg(self):
        r = thermo.web_dg(RX, COND)
        self.assertEqual((r["dg"], r["err"]), (26.5, 0.6))
        self.assertEqual(r["page_conditions"], COND)
        self.assertAlmostEqual(thermo.keq_from_dg(r["dg"], 298.15), 2.28e-5, places=7)

    def test_other_conditions_change_value(self):
        r = thermo.web_dg(RX, thermo.Conditions(7.0, 0.10, 298.15, 3.0))
        self.assertEqual(r["dg"], 30.4)

    def test_condition_mismatch_is_blind(self):
        page = ft.replay(
            "https://equilibrator.weizmann.ac.il/search?query=%28S%29-malate%20%2B%20NAD%2B%20%3D%20"
            "oxaloacetate%20%2B%20NADH&p_h=7.5&p_mg=3.0&ionic_strength=0.25&temperature=298.15",
            {}, 30)
        # serve the pH 7.0 page although pH 7.5 was requested
        other = thermo.Conditions(7.0, 0.10, 298.15, 3.0)
        with mock.patch.object(thermo.http, "get") as g:
            g.return_value = http.Response(200, "u", page[2])
            res_page = thermo.parse_web(page[2].decode())
            self.assertEqual(res_page["page_conditions"], COND)
            with self.assertRaises(BlindError):
                thermo.web_dg(RX, other)

    def test_layout_change_is_blind(self):
        with self.assertRaises(BlindError):
            thermo.parse_web("<html><body>nothing here</body></html>")

    def test_every_output_line_carries_conditions(self):
        line = thermo.format_result("web", RX, 7.8, 5.7, COND)
        for tok in ("pH=7.5", "I=0.25 M", "T=298.15 K", "pMg=3"):
            self.assertIn(tok, line)

    def test_package_feature_check_reports_missing_cache(self):
        # appdirs is optional; stub it so the check does not depend on the host (CI lacks it)
        fake_appdirs = mock.Mock(user_cache_dir=mock.Mock(return_value="cache"))
        with mock.patch.dict(sys.modules, {"appdirs": fake_appdirs}), \
                mock.patch.object(thermo.Path, "exists", return_value=False), \
                mock.patch.object(thermo, "_python_with_package", return_value="python"):
            st = thermo.package_status()
        self.assertFalse(st["cache_ok"])
        self.assertIn("1.34 GB", st["reason"])
        self.assertNotIn("Users", str(st))                 # no absolute home path leaks
        with mock.patch.object(thermo, "package_status", return_value=st):
            with self.assertRaises(BlindError):
                thermo.package_dg(RX, COND)

    def test_cli_thermo_match_and_blind(self):
        args = ("thermo", "--reaction", RX, "--pH", "7.5", "--ionic-strength", "0.25",
                "--temperature", "298.15", "--pMg", "3.0")
        code, out = self.cli(*args, "--claimed-keq", "2.28e-5")
        self.assertEqual(code, 0)
        self.assertIn("MATCH", out)
        self.assertIn("within_1sigma_band=yes", out)
        self.assertEqual(self.cli(*args, "--claimed-keq", "0.5")[0], 1)
        with mock.patch.object(thermo, "package_status",
                               return_value={"reason": "cache missing"}):
            code, out = self.cli(*args, "--source", "package")
        self.assertEqual(code, 2)
        self.assertIn("pH=7.5", out)

    def test_cli_thermo_requires_conditions(self):
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stderr(io.StringIO()):
                bio_const.main(["thermo", "--reaction", RX])

    def test_cli_rhea(self):
        code, out = self.cli("rhea", "--ec", "1.1.1.37")
        self.assertEqual(code, 0)
        self.assertIn("RHEA:21432", out)


if __name__ == "__main__":
    unittest.main()
