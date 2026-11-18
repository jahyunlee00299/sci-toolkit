import contextlib
import io
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from biodb import bio_const, compare, http, pdb, uniprot  # noqa: E402
from biodb.errors import BlindError  # noqa: E402
import fixture_transport as ft  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self._t, self._i = http.TRANSPORT, http.MIN_INTERVAL_S
        http.TRANSPORT, http.MIN_INTERVAL_S = ft.replay, 0.0

    def tearDown(self):
        http.TRANSPORT, http.MIN_INTERVAL_S = self._t, self._i


class TestHttp(unittest.TestCase):
    def setUp(self):
        self._t, self._i = http.TRANSPORT, http.MIN_INTERVAL_S
        http.MIN_INTERVAL_S = 0.0

    def tearDown(self):
        http.TRANSPORT, http.MIN_INTERVAL_S = self._t, self._i

    def test_retry_once_then_blind(self):
        calls = []

        def boom(u, h, t):
            calls.append(u)
            raise OSError("down")
        http.TRANSPORT = boom
        with self.assertRaises(BlindError):
            http.get("https://x.example/a")
        self.assertEqual(len(calls), 2)

    def test_retry_recovers(self):
        seq = iter([OSError("x"), (200, {}, b"ok")])

        def flaky(u, h, t):
            v = next(seq)
            if isinstance(v, Exception):
                raise v
            return v
        http.TRANSPORT = flaky
        self.assertEqual(http.get("https://x.example/a").body, b"ok")

    def test_redirect_chain_recorded(self):
        pages = {"https://a.example/1": (303, {"location": "/2"}, b""),
                 "https://a.example/2": (200, {}, b"done")}
        http.TRANSPORT = lambda u, h, t: pages[u]
        r = http.get("https://a.example/1")
        self.assertEqual((r.status, r.url, r.chain), (200, "https://a.example/2",
                                                      [(303, "https://a.example/1")]))

    def test_user_agent_and_timeout_sent(self):
        seen = {}

        def spy(u, h, t):
            seen.update(h=h, t=t)
            return 200, {}, b""
        http.TRANSPORT = spy
        http.get("https://x.example/u")
        self.assertIn("biodb", seen["h"]["User-Agent"])
        self.assertEqual(seen["t"], 30)

    def test_throttle_one_per_second_per_host(self):
        http.MIN_INTERVAL_S = 1.0
        http._last_request.clear()
        slept = []
        orig = http.time.sleep
        http.time.sleep = slept.append
        try:
            http.TRANSPORT = lambda u, h, t: (200, {}, b"")
            http.get("https://t.example/1")
            http.get("https://t.example/2")
        finally:
            http.time.sleep = orig
        self.assertEqual(len(slept), 1)
        self.assertGreater(slept[0], 0.5)


class TestUniprot(Base):
    def test_seq_mass_reproduces_uniprot_within_1_da(self):
        for acc in ("P33160", "P61889", "A0A0G3HLV0", "A0A0G3I6S6", "P69905", "P00533", "P0AES4"):
            r = uniprot.fetch(acc)
            self.assertLess(abs(r["mass_check_da"] - r["mass_da"]), 1.0, acc)

    def test_p33160(self):
        r = uniprot.fetch("P33160")
        self.assertEqual((r["length"], r["mass_da"], r["taxon_id"]), (401, 44136, 33067))
        self.assertEqual(r["ec"], ["1.17.1.9"])
        self.assertTrue(r["reviewed"])
        self.assertEqual(r["chains"][0]["start"], 2)       # initiator Met removed
        self.assertAlmostEqual(r["chains"][0]["mass_da_computed"], 44004.97, places=1)
        self.assertTrue(any("mature chain" in n for n in r["notes"]))

    def test_p61889_is_mdh(self):
        r = uniprot.fetch("P61889")
        self.assertEqual((r["gene"], r["ec"], r["taxon_id"]), ("mdh", ["1.1.1.37"], 83333))

    def test_well_known_accessions(self):
        self.assertEqual(uniprot.fetch("P69905")["length"], 142)
        self.assertEqual(uniprot.fetch("P69905")["mass_da"], 15258)
        self.assertEqual(uniprot.fetch("P00533")["mass_da"], 134277)
        self.assertEqual(uniprot.fetch("P0AES4")["gene"], "gyrA")

    def test_unreviewed_flag(self):
        self.assertFalse(uniprot.fetch("A0A0G3I6S6")["reviewed"])

    def test_isoform(self):
        r = uniprot.fetch("P04637-2")
        self.assertTrue(r["isoform"])
        self.assertEqual(r["length"], 341)
        self.assertTrue(any("isoform" in n for n in r["notes"]))

    def test_demerged_is_blind(self):
        with self.assertRaises(BlindError) as c:
            uniprot.fetch("P01922")
        self.assertIn("P69905", str(c.exception))

    def test_merged_reports_merged_to_synthetic(self):
        # SYNTHETIC document in the live shape (no live MERGED accession was found).
        d = {"entryType": "Inactive", "primaryAccession": "Q00001",
             "inactiveReason": {"inactiveReasonType": "MERGED", "mergeDemergeTo": ["Q00002"]}}
        r = uniprot.parse_entry(d, "Q00001")
        self.assertEqual((r["status"], r["merged_to"]), ("inactive", "Q00002"))

    def test_deleted_is_blind(self):
        d = {"entryType": "Inactive", "inactiveReason": {"inactiveReasonType": "DELETED"}}
        with self.assertRaises(BlindError):
            uniprot.parse_entry(d, "Q00001")

    def test_404_and_bad_format_blind(self):
        with self.assertRaises(BlindError):
            uniprot.fetch("P12345-2")
        with self.assertRaises(BlindError):
            uniprot.fetch("not-an-accession")

    def test_ambiguous_residues_give_none_mass(self):
        self.assertIsNone(uniprot.seq_mass("AXG"))


class TestPdb(Base):
    def test_2nad(self):
        r = pdb.fetch("2NAD")
        self.assertEqual(r["resolution_a"], 2.05)
        self.assertEqual(r["method"], ["X-RAY DIFFRACTION"])
        self.assertEqual(r["polymers"][0]["uniprot"], ["P33160"])
        self.assertEqual({lig["comp_id"] for lig in r["ligands"]}, {"AZI", "SO4", "NAD"})

    def test_missing_entry_blind(self):
        with self.assertRaises(BlindError):
            pdb.fetch("9ZZZ")

    def test_bad_id_blind(self):
        with self.assertRaises(BlindError):
            pdb.fetch("xx")

    def test_no_resolution_is_none(self):
        e = {"rcsb_id": "1XXX", "exptl": [{"method": "SOLUTION NMR"}], "rcsb_entry_info": {}}
        r = pdb.parse(e, [], [])
        self.assertIsNone(r["resolution_a"])


class TestCompare(Base):
    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = bio_const.main(list(argv))
        return code, out.getvalue().strip(), err.getvalue()

    def test_match_kda_and_da_agree(self):
        c1, l1, _ = self.run_cli("compare", "--source", "uniprot", "--id", "P33160", "--field",
                                 "mass", "--claimed", "44136", "--unit", "Da")
        c2, l2, _ = self.run_cli("compare", "--source", "uniprot", "--id", "P33160", "--field",
                                 "mass", "--claimed", "44.136", "--unit", "kDa")
        self.assertEqual((c1, c2), (0, 0))
        self.assertTrue(l1.startswith("MATCH") and "live=44136 Da" in l1)

    def test_mismatch_exit1_with_rel_diff(self):
        c, line, _ = self.run_cli("compare", "--source", "uniprot", "--id", "P33160", "--field",
                                  "mass", "--claimed", "41000", "--unit", "Da", "--rtol", "0.01")
        self.assertEqual(c, 1)
        self.assertIn("MISMATCH", line)
        self.assertIn("rel_diff=-7.105%", line)

    def test_his_tag_value_mismatches_loudly(self):
        # SSOT quotes 45.1 kDa (tag-corrected) against the 44,136 Da UniProt mass
        c, line, _ = self.run_cli("compare", "--source", "uniprot", "--id", "P33160", "--field",
                                  "mass", "--claimed", "45.1", "--unit", "kDa")
        self.assertEqual(c, 1)

    def test_missing_unit_is_blind(self):
        c, line, _ = self.run_cli("compare", "--source", "uniprot", "--id", "P33160", "--field",
                                  "mass", "--claimed", "44136")
        self.assertEqual(c, 2)
        self.assertTrue(line.startswith("BLIND"))

    def test_wrong_unit_for_field_is_blind(self):
        c, line, _ = self.run_cli("compare", "--source", "uniprot", "--id", "P33160", "--field",
                                  "length", "--claimed", "401", "--unit", "Da")
        self.assertEqual(c, 2)

    def test_network_failure_is_blind_not_pass(self):
        http.TRANSPORT = lambda u, h, t: (_ for _ in ()).throw(OSError("offline"))
        c, line, _ = self.run_cli("compare", "--source", "uniprot", "--id", "P33160", "--field",
                                  "mass", "--claimed", "44136", "--unit", "Da")
        self.assertEqual(c, 2)
        self.assertTrue(line.startswith("BLIND"))

    def test_demerged_is_blind(self):
        c, line, _ = self.run_cli("compare", "--source", "uniprot", "--id", "P01922", "--field",
                                  "mass", "--claimed", "15000", "--unit", "Da")
        self.assertEqual(c, 2)

    def test_merged_compare_is_blind_and_names_target(self):
        rec = {"accession": "Q1", "status": "inactive", "reason": "MERGED", "merged_to": "Q2"}
        v = compare.compare("uniprot", "Q1", "mass", rec, "1", "Da", 0.01)
        self.assertEqual((v.code, v.verdict), (2, "BLIND"))
        self.assertIn("Q2", v.line)

    def test_mature_mass_field(self):
        c, line, _ = self.run_cli("compare", "--source", "uniprot", "--id", "P33160", "--field",
                                  "mature_mass", "--claimed", "44005", "--unit", "Da")
        self.assertEqual(c, 0)

    def test_text_fields_and_pdb(self):
        self.assertEqual(self.run_cli("compare", "--source", "uniprot", "--id", "P33160",
                                      "--field", "ec", "--claimed", "1.17.1.9")[0], 0)
        self.assertEqual(self.run_cli("compare", "--source", "pdb", "--id", "2NAD", "--field",
                                      "resolution", "--claimed", "2.05", "--unit", "A")[0], 0)
        self.assertEqual(self.run_cli("compare", "--source", "pdb", "--id", "2NAD", "--field",
                                      "uniprot", "--claimed", "P33160")[0], 0)
        self.assertEqual(self.run_cli("compare", "--source", "pdb", "--id", "2NAD", "--field",
                                      "ligand", "--claimed", "FAD")[0], 1)

    def test_lookup_field_output(self):
        c, out, _ = self.run_cli("uniprot", "P33160", "--field", "mass")
        self.assertEqual((c, out), (0, "44136 Da"))
        c, out, _ = self.run_cli("uniprot", "P33160", "--field", "length")
        self.assertEqual(out, "401 aa")

    def test_lookup_blind_exit2(self):
        c, _, err = self.run_cli("uniprot", "P12345-2")
        self.assertEqual(c, 2)
        self.assertIn("BLIND", err)


if __name__ == "__main__":
    unittest.main()
