"""Tests for the verified-defect fixes: @/ escape, backslashes, git mode, gid format, config details."""
from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from test_lab_record import chain, edit, git, lab, lint, needs_git, rec, run  # noqa: F401
from test_lab_record_catalog import write_catalog  # noqa: F401

from lab_record_lib import config, model  # noqa: E402
from lab_record_lib.cli import main  # noqa: E402
from lab_record_lib.parse import read_text, write_text  # noqa: E402


@pytest.fixture(autouse=True)
def _no_env(monkeypatch):
    monkeypatch.delenv("LAB_RECORD_ROOT", raising=False)


def wcfg(tmp_path, data, name="c.json"):
    p = tmp_path / name
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


@pytest.fixture
def proj(tmp_path):
    root = tmp_path / "lab-records"
    root.mkdir()
    (tmp_path / "Proj" / "sub").mkdir(parents=True)
    (tmp_path / "Proj" / "sub" / "f.csv").write_text("x", encoding="utf-8")
    (tmp_path / "outside.txt").write_text("x", encoding="utf-8")   # reachable via @/../outside.txt
    (tmp_path / "Proj2").mkdir()
    cfg = wcfg(tmp_path, {"root": str(root), "people": {"person1": "J"},
                          "projects": {"pa": {"folder": "../Proj"}}})
    rec(root, "protocols/PROT-001_v1.md", {"id": "PROT-001", "type": "prot", "title": "p",
                                           "version": "v1", "project": "pa"})
    return root, cfg


def exp(root, **extra):
    fm = {"id": "EXP-261001-01", "type": "exp", "title": "e", "protocol": "PROT-001@v1", "project": "pa"}
    fm.update(extra)
    return rec(root, "experiments/2026/EXP-261001-01.md", fm)


# ------------------------------------------------ 1. @/ escape
@pytest.mark.parametrize("bad", ["@/../outside.txt", "@/sub/../../outside.txt", "@//outside.txt",
                                 "@/C:/Windows/win.ini", "@/c:outside.txt"])
def test_at_path_escape_is_rule7(proj, capsys, bad):
    root, cfg = proj
    exp(root, raw_data=[bad])
    code, lines, _ = lint(cfg, capsys)
    assert code == 1 and any(l.startswith("RULE7") and "escapes project folder" in l for l in lines), lines


def test_at_path_inner_dotdot_still_ok(proj, capsys):
    root, cfg = proj
    exp(root, raw_data=["@/sub/../sub/f.csv"])
    assert lint(cfg, capsys)[0] == 0


def test_catalog_at_path_escape_is_rule9(proj, capsys):
    root, cfg = proj
    write_catalog(root, {"sheet": {"S": {"project": "pa", "path": "@/../outside.txt"}}})
    code, lines, _ = lint(cfg, capsys)
    assert code == 1 and any(l.startswith("RULE9") and "escapes project folder" in l for l in lines)


def test_plain_root_relative_may_leave_root(proj, capsys):
    root, cfg = proj
    exp(root, raw_data=["../outside.txt"])
    assert lint(cfg, capsys)[0] == 0


# ------------------------------------------------ 2. backslashes
def test_backslash_record_path_is_rule7(proj, capsys):
    root, cfg = proj
    (root / "data").mkdir()
    (root / "data" / "a.csv").write_text("x", encoding="utf-8")
    exp(root, raw_data=["data\\a.csv"])
    code, lines, _ = lint(cfg, capsys)
    assert code == 1 and any(l.startswith("RULE7") and "use / separators" in l for l in lines)
    exp(root, raw_data=["@/sub\\f.csv"])
    assert any(l.startswith("RULE7") and "use / separators" in l for l in lint(cfg, capsys)[1])


def test_backslash_catalog_path_is_rule9(proj, capsys):
    root, cfg = proj
    write_catalog(root, {"sheet": {"S": {"path": "a\\b.xlsx"}}})
    assert any(l.startswith("RULE9") and "use / separators" in l for l in lint(cfg, capsys)[1])


def test_backslash_project_folder_exit2(tmp_path, capsys):
    root = tmp_path / "r"
    root.mkdir()
    cfg = wcfg(tmp_path, {"root": str(root), "projects": {"pa": {"folder": "..\\Proj"}}})
    assert main(["lint", "--config", str(cfg)]) == 2
    assert "/ separators" in capsys.readouterr().err


# ------------------------------------------------ 3. git mode
@needs_git
def test_nested_in_unrelated_git_tree_uses_hash_baseline(tmp_path, capsys):
    outer = tmp_path / "outer"
    outer.mkdir()
    git(outer, "init", "-q")
    root = outer / "records"
    root.mkdir()
    cfg = wcfg(tmp_path, {"root": str(root), "people": {"person1": "J"}})
    from test_lab_record import build_chain
    build_chain(root)
    assert run(cfg, "close", "EXP-261001-01", capsys=capsys)[0] == 0
    assert (root / ".lab_record" / "hashes.json").is_file()
    path = root / "experiments/2026/EXP-261001-01.md"
    edit(path, lambda fm, b: ({**fm, "outcome_summary": "sneaky"}, b))
    code, lines, _ = lint(cfg, capsys)
    assert code == 1 and any(l.startswith("RULE1 EXP-261001-01") for l in lines)


@needs_git
def test_git_mode_untracked_closed_record_falls_back_to_hash(chain, capsys):
    root, cfg = chain
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "base")
    # new record never committed: HEAD has no copy
    rec(root, "experiments/2026/EXP-261005-01.md",
        {"id": "EXP-261005-01", "type": "exp", "title": "new", "protocol": "PROT-001@v1"})
    assert run(cfg, "close", "EXP-261005-01", capsys=capsys)[0] == 0
    path = root / "experiments/2026/EXP-261005-01.md"
    edit(path, lambda fm, b: ({**fm, "outcome_summary": "x"}, b))
    code, lines, _ = lint(cfg, capsys)
    assert code == 1 and any(l.startswith("RULE1 EXP-261005-01") for l in lines)


# ------------------------------------------------ 4. gid format
@pytest.mark.parametrize("bad", ["1234\n", "１２３４", "١٢٣٤", "12 3", "", "-5", True, 0, 1.5])
def test_is_digits_rejects(bad):
    assert not config.is_digits(bad)


def test_is_digits_accepts_and_int_warns(capsys):
    assert config.is_digits("0123") and capsys.readouterr().err == ""
    assert config.is_digits(123)
    assert "quote gids as strings" in capsys.readouterr().err


def test_asana_project_newline_rejected_at_load(tmp_path, capsys):
    root = tmp_path / "r"
    root.mkdir()
    cfg = wcfg(tmp_path, {"root": str(root), "projects": {"pa": {"asana_project": "1234\n"}}})
    assert main(["lint", "--config", str(cfg)]) == 2


def test_link_gid_fullwidth_is_rule2(proj, capsys):
    root, cfg = proj
    exp(root, links=[{"rel": "asana", "task": "１２３"}])
    assert any(l.startswith("RULE2") and "digits only" in l for l in lint(cfg, capsys)[1])


# ------------------------------------------------ 6. small items
def test_root_announced_and_empty_root_warned(tmp_path, capsys):
    root = tmp_path / "empty"
    root.mkdir()
    cfg = wcfg(tmp_path, {"root": str(root), "people": {"person1": "J"}})
    main(["lint", "--config", str(cfg)])
    err = capsys.readouterr().err
    assert f"lab-record root: {root}" in err and "none of" in err


def test_root_announced_without_warning_when_populated(chain, capsys):
    _, cfg = chain
    err = lint(cfg, capsys)[2]
    assert "lab-record root:" in err and "none of" not in err


def test_catalog_entry_without_project_message(proj, capsys):
    root, cfg = proj
    write_catalog(root, {"sheet": {"S": {"path": "@/sub/f.csv"}}})
    lines = lint(cfg, capsys)[1]
    assert any(l.startswith("RULE9") and "catalog entry has no project" in l for l in lines)
    assert not any("record has no project" in l for l in lines)


def test_duplicate_alias_inside_same_entry_ignored(proj, capsys):
    root, cfg = proj
    write_catalog(root, {"enzyme": {"LDH": {"path": "../outside.txt", "aliases": ["ldh2", "LDH2", "ldh"]}}})
    assert lint(cfg, capsys)[0] == 0


def test_unknown_project_key_message(proj, capsys):
    root, cfg = proj
    exp(root, project="nope", raw_data=["@/sub/f.csv"])
    lines = lint(cfg, capsys)[1]
    assert any(l.startswith("RULE7") and "unknown project key" in l for l in lines)
    assert not any("has no folder" in l for l in lines)


def test_local_null_folder_keeps_shared(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "lab-record.config.json").write_text(
        json.dumps({"projects": {"pa": {"folder": "../A"}}}), encoding="utf-8")
    local = wcfg(tmp_path, {"root": str(root), "projects": {"pa": {"folder": None}}}, "l.json")
    assert model.resolve_config(None, str(local)).projects["pa"]["folder"] == "../A"


def test_dead_notify_keys_noted_on_stderr(tmp_path, capsys):
    root = tmp_path / "r"
    root.mkdir()
    cfg = wcfg(tmp_path, {"root": str(root), "notify": {"telegram": True},
                          "projects": {"pa": {"notion_project": "x"}}})
    main(["lint", "--config", str(cfg)])
    err = capsys.readouterr().err
    assert "notifications are off by design" in err and "notify" in err and "notion_project" in err


def test_example_config_has_no_dead_keys():
    from pathlib import Path
    text = (Path(__file__).resolve().parents[1] / "config.example.json").read_text(encoding="utf-8")
    assert "notify" not in text and "notion_project" not in text
