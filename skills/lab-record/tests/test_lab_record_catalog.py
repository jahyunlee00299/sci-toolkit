"""Tests: catalog.json (enzyme / standard / sheet), catalog links, RULE9, `uses`, `catalog`."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from test_lab_record import chain, edit, lab, lint, rec, run  # noqa: F401

from lab_record_lib import catalog, model  # noqa: E402
from lab_record_lib.cli import main  # noqa: E402


@pytest.fixture(autouse=True)
def _no_env(monkeypatch):
    monkeypatch.delenv("LAB_RECORD_ROOT", raising=False)


@pytest.fixture
def cat(tmp_path):
    """root + sibling project folder + catalog (1 enzyme w/ alias, 1 standard, 1 sheet) + chain."""
    root = tmp_path / "lab-records"
    root.mkdir()
    (tmp_path / "Proj").mkdir()
    (tmp_path / "Proj" / "enz.pdf").write_text("x", encoding="utf-8")
    (tmp_path / "Proj" / "std.csv").write_text("x", encoding="utf-8")
    (tmp_path / "Primers.xlsx").write_text("x", encoding="utf-8")
    cfg = tmp_path / "c.json"
    cfg.write_text(json.dumps({"root": str(root), "people": {"person1": "J"},
                               "projects": {"pa": {"folder": "../Proj"}}}), encoding="utf-8")
    write_catalog(root, {
        "enzyme": {"Lactate DH": {"project": "pa", "path": "@/enz.pdf", "aliases": ["LDH", "ldh-2"], "note": "n"}},
        "standard": {"Std-A": {"project": "pa", "path": "@/std.csv"}},
        "sheet": {"Primers": {"path": "../Primers.xlsx"}}})
    rec(root, "protocols/PROT-001_v1.md", {"id": "PROT-001", "type": "prot", "title": "p", "version": "v1",
                                           "project": "pa", "links": [{"rel": "sheet", "name": "primers"}]})
    rec(root, "experiments/2026/EXP-261001-01.md",
        {"id": "EXP-261001-01", "type": "exp", "title": "run", "protocol": "PROT-001@v1", "project": "pa",
         "links": [{"rel": "enzyme", "name": "ldh"}]})
    rec(root, "discussions/2026/DISC-261002-01.md",
        {"id": "DISC-261002-01", "type": "disc", "title": "talk", "about": ["EXP-261001-01"]})
    return root, cfg


def write_catalog(root: Path, data) -> None:
    (root / "catalog.json").write_text(json.dumps(data), encoding="utf-8")


def set_links(root, rel, items):
    edit(root / rel, lambda fm, b: ({**fm, "links": items}, b))


# ------------------------------------------------------------ load
def test_clean_catalog_lint_zero(cat, capsys):
    assert lint(cat[1], capsys)[0] == 0


def test_absent_catalog_is_empty(chain, capsys):
    root, cfg = chain
    assert not (root / "catalog.json").exists()
    assert lint(cfg, capsys)[0] == 0
    code, out = run(cfg, "catalog", capsys=capsys)
    assert code == 0 and "empty" in out.out


@pytest.mark.parametrize("data", [
    {"enzymes": {}},                                                   # unknown kind
    {"enzyme": {"X": {"project": "nope", "path": "a"}}},               # unknown project key
    {"enzyme": {"X": {"path": ""}}},                                   # empty path
    {"enzyme": {"X": {}}},                                             # missing path
    {"enzyme": {"X": {"path": "a", "aliases": "LDH"}}},                # aliases not a list
    {"enzyme": {"X": {"path": "a", "aliases": ["Y"]}, "Y": {"path": "b"}}},  # ambiguous alias
    {"enzyme": {"X": {"path": "a"}, "x": {"path": "b"}}},              # case-insensitive clash
    {"enzyme": []},
    [1],
])
def test_bad_catalog_exit_2(cat, capsys, data):
    root, cfg = cat
    write_catalog(root, data)
    assert main(["lint", "--config", str(cfg)]) == 2
    assert "catalog.json" in capsys.readouterr().err


def test_malformed_catalog_json_exit_2(cat, capsys):
    root, cfg = cat
    (root / "catalog.json").write_text("{nope", encoding="utf-8")
    assert main(["catalog", "--config", str(cfg)]) == 2


def test_same_name_in_different_kinds_ok(cat, capsys):
    root, cfg = cat
    write_catalog(root, {"enzyme": {"Both": {"path": "../Primers.xlsx"}},
                         "sheet": {"Both": {"path": "../Primers.xlsx"}}})
    assert lint(cfg, capsys)[0] in (0, 1)  # loads; links in `chain` just may not resolve
    assert main(["catalog", "--config", str(cfg)]) == 0


# ------------------------------------------------------------ links (RULE2 family)
def test_link_resolves_name_and_alias_case_insensitive(cat, capsys):
    root, cfg = cat
    set_links(root, "experiments/2026/EXP-261001-01.md",
              [{"rel": "enzyme", "name": "LACTATE dh"}, {"rel": "enzyme", "name": "LDH-2"},
               {"rel": "standard", "name": "std-a"}])
    assert lint(cfg, capsys)[0] == 0


def test_link_unknown_name(cat, capsys):
    root, cfg = cat
    set_links(root, "experiments/2026/EXP-261001-01.md", [{"rel": "enzyme", "name": "Trypsin"}])
    _, lines, _ = lint(cfg, capsys)
    assert any(l.startswith("RULE2 EXP-261001-01") and "'Trypsin' is not in the catalog" in l for l in lines)


def test_link_kind_must_match(cat, capsys):
    root, cfg = cat
    set_links(root, "experiments/2026/EXP-261001-01.md", [{"rel": "standard", "name": "LDH"}])
    assert any("not in the catalog" in l for l in lint(cfg, capsys)[1])


def test_link_without_name(cat, capsys):
    root, cfg = cat
    set_links(root, "experiments/2026/EXP-261001-01.md", [{"rel": "enzyme"}])
    assert any("needs `name`" in l for l in lint(cfg, capsys)[1])


def test_link_with_missing_catalog_path(cat, capsys):
    root, cfg = cat
    (root.parent / "Proj" / "enz.pdf").unlink()
    _, lines, _ = lint(cfg, capsys)
    assert any(l.startswith("RULE2 EXP-261001-01") and "catalog path" in l and "does not exist" in l
               for l in lines)


def test_link_without_any_catalog_file(chain, capsys):
    root, cfg = chain
    set_links(root, "experiments/2026/EXP-261001-01.md", [{"rel": "enzyme", "name": "LDH"}])
    assert any("not in the catalog" in l for l in lint(cfg, capsys)[1])


# ------------------------------------------------------------ RULE9
def test_rule9_missing_path_reported_once_even_if_unused(cat, capsys):
    root, cfg = cat
    (root.parent / "Proj" / "std.csv").unlink()  # Std-A is linked by nobody
    code, lines, _ = lint(cfg, capsys)
    r9 = [l for l in lines if l.startswith("RULE9")]
    assert code == 1 and r9 == ["RULE9 catalog standard:Std-A path missing: @/std.csv"]


def test_rule9_root_relative_sheet_and_multiple(cat, capsys):
    root, cfg = cat
    (root.parent / "Primers.xlsx").unlink()
    (root.parent / "Proj" / "std.csv").unlink()
    r9 = [l for l in lint(cfg, capsys)[1] if l.startswith("RULE9")]
    assert r9 == ["RULE9 catalog sheet:Primers path missing: ../Primers.xlsx",
                  "RULE9 catalog standard:Std-A path missing: @/std.csv"]


def test_rule9_at_path_without_project(cat, capsys):
    root, cfg = cat
    write_catalog(root, {"sheet": {"S": {"path": "@/x.xlsx"}}})
    r9 = [l for l in lint(cfg, capsys)[1] if l.startswith("RULE9")]
    assert len(r9) == 1 and "no project" in r9[0]


# ------------------------------------------------------------ uses
def test_uses_alias_and_lineage(cat, capsys):
    root, cfg = cat
    code, out = run(cfg, "uses", "LDH", capsys=capsys)
    lines = out.out.splitlines()
    assert code == 0 and lines[0] == "uses enzyme:Lactate DH: 1 direct, 1 via lineage"
    assert lines[1].startswith("DIRECT EXP-261001-01") and lines[2].startswith("VIA DISC-261002-01")
    assert "through EXP-261001-01" in lines[2]


def test_uses_prot_expands_to_exp_and_disc(cat, capsys):
    root, cfg = cat
    edit(root / "experiments/2026/EXP-261001-01.md", lambda fm, b: ({**fm, "links": []}, b))
    code, out = run(cfg, "uses", "PRIMERS", capsys=capsys)  # sheet linked by the PROT
    lines = out.out.splitlines()
    assert code == 0 and lines[0] == "uses sheet:Primers: 1 direct, 2 via lineage"
    assert [l.split()[0] for l in lines[1:]] == ["DIRECT", "VIA", "VIA"]


def test_uses_any_record_type_direct(cat, capsys):
    root, cfg = cat
    set_links(root, "discussions/2026/DISC-261002-01.md", [{"rel": "standard", "name": "Std-A"}])
    code, out = run(cfg, "uses", "std-a", capsys=capsys)
    assert code == 0 and "DIRECT DISC-261002-01" in out.out


def test_uses_unlinked_entry_and_unknown_name(cat, capsys):
    root, cfg = cat
    code, out = run(cfg, "uses", "Std-A", capsys=capsys)
    assert code == 0 and out.out.splitlines()[0] == "uses standard:Std-A: 0 direct, 0 via lineage"
    code, out = run(cfg, "uses", "Nonexistent", capsys=capsys)
    assert code == 1 and "not in the catalog" in out.err


# ------------------------------------------------------------ catalog command
def test_catalog_table(cat, capsys):
    root, cfg = cat
    code, out = run(cfg, "catalog", capsys=capsys)
    rows = [l.split("\t") for l in out.out.splitlines()]
    assert code == 0 and rows[0] == ["kind", "name", "project", "path", "exists", "used_by"]
    by = {r[1]: r for r in rows[1:]}
    assert by["Lactate DH"][2] == "pa" and by["Lactate DH"][4:] == ["yes", "1"]
    assert by["Lactate DH"][3].replace("\\", "/").endswith("/Proj/enz.pdf")
    assert by["Primers"][2] == "-" and by["Primers"][5] == "1"
    assert by["Std-A"][5] == "0"


def test_catalog_kind_filter_and_missing(cat, capsys):
    root, cfg = cat
    (root.parent / "Proj" / "std.csv").unlink()
    code, out = run(cfg, "catalog", "--kind", "standard", capsys=capsys)
    rows = out.out.splitlines()
    assert code == 0 and len(rows) == 2 and rows[1].split("\t")[4] == "no"


def test_catalog_bad_kind_rejected(cat):
    with pytest.raises(SystemExit):
        main(["catalog", "--kind", "primer", "--config", str(cat[1])])


def test_catalog_module_resolution(cat):
    root, cfg = cat
    c = catalog.load_catalog(model.resolve_config(None, str(cfg)))
    assert {e.label for e in c.entries} == {"enzyme:Lactate DH", "standard:Std-A", "sheet:Primers"}
    assert c.resolve("enzyme", "ldh-2").name == "Lactate DH" and c.resolve("enzyme", "Std-A") is None
