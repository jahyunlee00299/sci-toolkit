"""Tests: compound/reaction kinds, enzyme domain fields, `related`, RDKit lint (RULE12/13), bio-claims."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from test_lab_record import lint  # noqa: F401

from lab_record_lib import bio_claims, catalog, chem  # noqa: E402
from lab_record_lib.cli import main  # noqa: E402

rdkit = pytest.importorskip("rdkit")

# Minimal real chemistry: glycolaldehyde-free toy balance, ethanol + NAD-like pair is overkill;
# use A -> B isomerisation and a redox pair with an explicit proton accounting.
ETHANOL, ACETALDEHYDE = "CCO", "CC=O"


@pytest.fixture(autouse=True)
def _no_env(monkeypatch):
    monkeypatch.delenv("LAB_RECORD_ROOT", raising=False)


def make(tmp_path: Path, data) -> tuple[Path, Path]:
    root = tmp_path / "lab-records"
    root.mkdir(exist_ok=True)
    (tmp_path / "f.pdf").write_text("x", encoding="utf-8")
    (root / "catalog.json").write_text(json.dumps(data), encoding="utf-8")
    cfg = tmp_path / "c.json"
    cfg.write_text(json.dumps({"root": str(root), "people": {"p": "P"}}), encoding="utf-8")
    return root, cfg


def key_of(smiles: str) -> str:
    rd = chem.load_rdkit()
    return chem.inchikey(rd, chem.parse(rd, smiles))


def domain(**over):
    d = {
        "enzyme": {"E1": {"path": "../f.pdf", "organism": "X y", "uniprot": "P00001", "ec": "1.1.1.1",
                          "catalyzes": ["R1"], "cofactor": ["NADH", "NAD+"], "code_ids": ["E1code"]}},
        "compound": {
            "EtOH": {"smiles": ETHANOL, "inchikey": key_of(ETHANOL), "formula": "C2H6O", "cofactor": False},
            "AcH": {"smiles": ACETALDEHYDE, "inchikey": key_of(ACETALDEHYDE)},
            "NAD+": {"cofactor": True},
            "NADH": {"cofactor": True, "regenerated_by": ["R1"]},
        },
        "reaction": {"R1": {"equation": "EtOH + NAD+ = AcH + NADH", "enzyme": "E1",
                            "substrates": [{"name": "EtOH", "coef": 1}],
                            "products": [{"name": "AcH", "coef": 1}],
                            "cofactors": [{"name": "NAD+", "to": "NADH"}], "reversible": True}},
    }
    d.update(over)
    return d


def run_lint(cfg, capsys):
    code = main(["lint", "--config", str(cfg)])
    cap = capsys.readouterr()
    return code, cap.out, cap.err


# ------------------------------------------------------------ loading
def test_old_shaped_catalog_loads(tmp_path, capsys):
    root, cfg = make(tmp_path, {"enzyme": {"A": {"path": "../f.pdf", "aliases": ["a1"]}},
                                "standard": {}, "sheet": {"S": {"path": "../f.pdf"}}})
    code, out, err = run_lint(cfg, capsys)
    assert code == 0 and out == "" and "BLIND" not in err and "WARN " not in err


def test_unknown_kind_warns_and_skips(tmp_path, capsys):
    root, cfg = make(tmp_path, {"cascade": {"C": {}}, "enzyme": {"A": {"path": "../f.pdf"}}})
    code, out, err = run_lint(cfg, capsys)
    assert code == 0 and "WARN" in err and "cascade" in err
    assert main(["catalog", "--config", str(cfg)]) == 0


def test_compound_reaction_resolve_and_no_path_needed(tmp_path, capsys):
    root, cfg = make(tmp_path, domain())
    code, out, err = run_lint(cfg, capsys)
    assert code == 0, out
    assert main(["catalog", "--kind", "reaction", "--config", str(cfg)]) == 0
    assert "R1" in capsys.readouterr().out


def test_path_still_required_for_enzyme(tmp_path, capsys):
    root, cfg = make(tmp_path, {"enzyme": {"A": {"organism": "x"}}})
    assert main(["lint", "--config", str(cfg)]) == 2


@pytest.mark.parametrize("bad", [
    {"compound": {"X": {"cofactor": "yes"}}},
    {"compound": {"X": {"smiles": ""}}},
    {"reaction": {"R": {"keq": {"value": -1}}}},
    {"reaction": {"R": {"substrates": [{"coef": 1}]}}},
    {"reaction": {"R": {"cofactors": [{"name": "A"}]}}},
    {"enzyme": {"A": {"path": "p", "catalyzes": "R1"}}},
    {"enzyme": {"A": {"path": "p", "related": [{"name": "B", "rel": "kinda", "status": "confirmed"}]}}},
])
def test_malformed_domain_fields_exit_2(tmp_path, capsys, bad):
    root, cfg = make(tmp_path, bad)
    assert main(["lint", "--config", str(cfg)]) == 2


# ------------------------------------------------------------ related
def test_related_is_not_an_alias(tmp_path, capsys):
    data = {"enzyme": {"ActDH": {"path": "../f.pdf"},
                       "ProtDH": {"path": "../f.pdf", "related": [
                           {"name": "ActDH", "rel": "probably_same", "status": "unconfirmed", "basis": "b"}]}}}
    root, cfg = make(tmp_path, data)
    cat = catalog.load_catalog(__import__("lab_record_lib.model", fromlist=["x"]).resolve_config(None, str(cfg)))
    assert cat.resolve("enzyme", "ProtDH").name == "ProtDH"
    assert cat.resolve("enzyme", "ActDH").name == "ActDH"
    # a name that exists only inside `related` does not resolve
    data["enzyme"]["ProtDH"]["related"][0]["name"] = "Ghost"
    (root / "catalog.json").write_text(json.dumps(data), encoding="utf-8")
    cat = catalog.load_catalog(__import__("lab_record_lib.model", fromlist=["x"]).resolve_config(None, str(cfg)))
    assert cat.resolve("enzyme", "Ghost") is None
    assert run_lint(cfg, capsys)[1].count("RULE12") == 1  # dangling related


def test_related_member_of_lints_clean(tmp_path, capsys):
    (tmp_path / "f.pdf").write_text("x", encoding="utf-8")
    data = {"enzyme": {"ActDH": {"path": "../f.pdf"},
                       "ProtDH": {"path": "../f.pdf", "related": [
                           {"name": "ActDH", "rel": "member_of", "status": "confirmed", "basis": "b"}]}}}
    root, cfg = make(tmp_path, data)
    assert "RULE12" not in run_lint(cfg, capsys)[1]


def test_related_does_not_trigger_alias_ambiguity(tmp_path, capsys):
    data = {"enzyme": {"A": {"path": "../f.pdf", "related": [
        {"name": "B", "rel": "same", "status": "confirmed"}]}, "B": {"path": "../f.pdf"}}}
    root, cfg = make(tmp_path, data)
    assert run_lint(cfg, capsys)[0] == 0


# ------------------------------------------------------------ RULE12
@pytest.mark.parametrize("edit", [
    lambda d: d["reaction"]["R1"].update(enzyme="Nope"),
    lambda d: d["reaction"]["R1"]["substrates"][0].update(name="Nope"),
    lambda d: d["reaction"]["R1"]["products"][0].update(name="Nope"),
    lambda d: d["reaction"]["R1"]["cofactors"][0].update(to="Nope"),
    lambda d: d["enzyme"]["E1"].update(catalyzes=["Nope"]),
    lambda d: d["enzyme"]["E1"].update(cofactor=["Nope"]),
    lambda d: d["compound"]["NADH"].update(regenerated_by=["Nope"]),
])
def test_dangling_reference_is_error(tmp_path, capsys, edit):
    d = domain()
    edit(d)
    root, cfg = make(tmp_path, d)
    code, out, _ = run_lint(cfg, capsys)
    assert code == 1 and "RULE12" in out and "Nope" in out


# ------------------------------------------------------------ RULE13 (RDKit)
def test_bad_smiles(tmp_path, capsys):
    d = domain()
    d["compound"]["EtOH"] = {"smiles": "C(C"}
    root, cfg = make(tmp_path, d)
    code, out, _ = run_lint(cfg, capsys)
    assert code == 1 and "does not parse" in out


def test_wrong_inchikey(tmp_path, capsys):
    d = domain()
    d["compound"]["EtOH"]["inchikey"] = key_of(ACETALDEHYDE)
    root, cfg = make(tmp_path, d)
    code, out, _ = run_lint(cfg, capsys)
    assert code == 1 and "inchikey" in out


def test_wrong_formula(tmp_path, capsys):
    d = domain()
    d["compound"]["EtOH"]["formula"] = "C2H4O"
    root, cfg = make(tmp_path, d)
    assert "formula" in run_lint(cfg, capsys)[1]


def full_smiles_domain(products_smiles):
    """Ethanol + NAD+ -> product + NADH, with simplified charged cofactor stand-ins."""
    d = domain()
    d["compound"]["NAD+"] = {"smiles": "C[n+]1ccccc1", "cofactor": True}      # charge +1
    d["compound"]["NADH"] = {"smiles": "CN1C=CCC=C1", "cofactor": True}        # one H more, neutral
    d["compound"]["AcH"] = {"smiles": products_smiles}
    d["compound"]["AcH"].pop("inchikey", None)
    return d


def test_balanced_reaction_passes(tmp_path, capsys):
    root, cfg = make(tmp_path, full_smiles_domain(ACETALDEHYDE))
    code, out, err = run_lint(cfg, capsys)
    assert code == 0, out
    assert "BLIND" not in err


def test_unbalanced_reaction_is_error(tmp_path, capsys):
    root, cfg = make(tmp_path, full_smiles_domain("CCC=O"))  # extra carbon
    code, out, _ = run_lint(cfg, capsys)
    assert code == 1 and "not element-balanced" in out and "C 8->9" in out


def test_cofactor_coef_enters_the_balance(tmp_path, capsys):
    """2 NADH + O2 -> 2 NAD+ + 2 H2O balances only with the cofactor coefficient applied."""
    d = full_smiles_domain(ACETALDEHYDE)
    d["compound"].update({"O2": {"smiles": "O=O"}, "H2O": {"smiles": "O"}})
    d["reaction"]["NOX"] = {"substrates": [{"name": "O2"}], "products": [{"name": "H2O", "coef": 2}],
                            "cofactors": [{"name": "NADH", "to": "NAD+", "coef": 2}]}
    root, cfg = make(tmp_path, d)
    assert "NOX" not in run_lint(cfg, capsys)[1]
    d["reaction"]["NOX"]["cofactors"][0]["coef"] = 1
    (root / "catalog.json").write_text(json.dumps(d), encoding="utf-8")
    assert "reaction:NOX" in run_lint(cfg, capsys)[1]


def test_participant_without_smiles_is_blind_not_pass(tmp_path, capsys):
    root, cfg = make(tmp_path, domain())  # cofactors carry no smiles
    code, out, err = run_lint(cfg, capsys)
    assert code == 0 and "BLIND R1" not in out and "BLIND reaction:R1" in err


def test_rdkit_missing_reports_blind(tmp_path, capsys, monkeypatch):
    root, cfg = make(tmp_path, {"compound": {"X": {"smiles": "C(C"}}})  # would be an error with RDKit
    monkeypatch.setattr(chem, "load_rdkit", lambda: None)
    code, out, err = run_lint(cfg, capsys)
    assert code == 0 and "BLIND rdkit is not importable" in err


# ------------------------------------------------------------ bio-claims
def claims(tmp_path, capsys, data):
    root, cfg = make(tmp_path, data)
    assert main(["bio-claims", "--config", str(cfg)]) == 0
    return capsys.readouterr().out


FULL_KEQ = {"value": 0.0425, "pH": 7.5, "ionic_strength": 0.25, "temperature_K": 298.15, "pMg": 3.0,
            "source": "eQuilibrator"}


def test_bio_claims_full_conditions(tmp_path, capsys):
    d = domain()
    d["reaction"]["R1"]["keq"] = FULL_KEQ
    out = claims(tmp_path, capsys, d)
    assert "[[claim]]" in out and "claimed_keq = 0.0425" in out and "temperature = 298.15" in out
    assert 'reaction = "EtOH + NAD+ = AcH + NADH"' in out and "BLIND" not in out
    assert not [ln for ln in out.splitlines() if ln.startswith("# claimed_keq")]


def test_bio_claims_missing_condition_is_commented_blind(tmp_path, capsys):
    d = domain()
    d["reaction"]["R1"]["keq"] = {k: v for k, v in FULL_KEQ.items() if k not in ("temperature_K", "pMg")}
    out = claims(tmp_path, capsys, d)
    assert "# BLIND: reaction:R1 keq is missing temperature_K, pMg" in out
    assert "# claimed_keq = 0.0425" in out
    assert not [ln for ln in out.splitlines() if ln.startswith("[[claim]]")]


def test_bio_claims_uniprot_only_when_value_stated(tmp_path, capsys):
    d = domain()
    out = claims(tmp_path, capsys, d)
    assert "uniprot" not in out.replace("the catalog states no uniprot", "")
    d["enzyme"]["E1"]["mass_da"] = 44136
    out = claims(tmp_path, capsys, d)
    assert 'id = "P00001"' in out and 'field = "mass"' in out and 'unit = "Da"' in out
    assert 'field = "length"' not in out


def test_bio_claims_out_file(tmp_path, capsys):
    root, cfg = make(tmp_path, domain())
    out = tmp_path / "c.toml"
    assert main(["bio-claims", "--out", str(out), "--config", str(cfg)]) == 0
    assert out.read_text(encoding="utf-8").startswith("# Generated by")
    tomllib = pytest.importorskip("tomllib")
    tomllib.loads(out.read_text(encoding="utf-8"))


def test_bio_claims_toml_parses_with_claims(tmp_path):
    tomllib = pytest.importorskip("tomllib")
    d = domain()
    d["reaction"]["R1"]["keq"] = FULL_KEQ
    d["enzyme"]["E1"]["length_aa"] = 401
    assert len(tomllib.loads(bio_claims.build(_cat(tmp_path, d))) ["claim"]) == 2


def _cat(tmp_path, data):
    from lab_record_lib.model import resolve_config
    root, cfg = make(tmp_path, data)
    return catalog.load_catalog(resolve_config(None, str(cfg)))


def test_shipped_catalog_example_lints_clean_apart_from_placeholder_path(tmp_path, capsys):
    example = Path(__file__).resolve().parent.parent / "catalog.example.json"
    data = json.loads(example.read_text(encoding="utf-8"))
    data.pop("_comment")  # a leading comment key would be an unknown kind (WARN), keep the check strict
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "example-fdh.md").write_text("x", encoding="utf-8")
    root, cfg = make(tmp_path, data)
    (root / "notes").mkdir()
    (root / "notes" / "example-fdh.md").write_text("x", encoding="utf-8")
    code, out, err = run_lint(cfg, capsys)
    assert code == 0, out
    assert "BLIND" not in err
