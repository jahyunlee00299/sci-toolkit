"""Tests: shared root config, project folders / @/ paths, RULE8, typed links."""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from test_lab_record import SCRIPTS, chain, edit, lab, lint, rec, run  # noqa: F401

from lab_record_lib import commands, model  # noqa: E402
from lab_record_lib.cli import main  # noqa: E402

SHARED = "lab-record.config.json"


def wjson(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _no_env(monkeypatch):
    monkeypatch.delenv("LAB_RECORD_ROOT", raising=False)


# ------------------------------------------------------------ 1. shared config layering
def test_shared_config_merge_local_overrides(tmp_path):
    root = tmp_path / "root"
    wjson(root / SHARED, {"people": {"person1": "Shared One", "person2": "Shared Two"},
                          "projects": {"pa": {"folder": "../A", "asana_project": "123"}}})
    local = wjson(tmp_path / "local.json", {"root": str(root), "people": {"person1": "Mine", "person9": "X"},
                                            "projects": {"pa": {"notion_project": "n"}, "pb": {}}})
    c = model.resolve_config(None, str(local))
    assert c.people == {"person1": "Mine", "person2": "Shared Two", "person9": "X"}
    assert c.projects["pa"] == {"folder": "../A", "asana_project": "123", "notion_project": "n"}
    assert "pb" in c.projects and c.shared_path == root / SHARED


def test_shared_alone_provides_people_for_lint(tmp_path):
    root = tmp_path / "root"
    wjson(root / SHARED, {"people": {"person1": "S"}})
    local = wjson(tmp_path / "l.json", {"root": str(root)})
    rec(root, "protocols/PROT-001_v1.md", {"id": "PROT-001", "type": "prot", "title": "p", "version": "v1"})
    assert main(["lint", "--config", str(local)]) == 0  # owner person1 only known via shared


def test_shared_root_key_ignored_with_warning(tmp_path, capsys):
    root, other = tmp_path / "root", tmp_path / "other"
    other.mkdir()
    wjson(root / SHARED, {"root": str(other), "people": {"a": "A"}})
    local = wjson(tmp_path / "l.json", {"root": str(root)})
    c = model.resolve_config(None, str(local))
    assert c.root == root and c.people == {"a": "A"}
    assert "root" in capsys.readouterr().err


@pytest.mark.parametrize("content", ["{not json", "[1, 2]"])
def test_malformed_shared_exit_2(tmp_path, capsys, content):
    root = tmp_path / "root"
    root.mkdir()
    (root / SHARED).write_text(content, encoding="utf-8")
    local = wjson(tmp_path / "l.json", {"root": str(root)})
    assert main(["lint", "--config", str(local)]) == 2
    assert SHARED in capsys.readouterr().err


def test_cwd_walk_up_discovers_root(tmp_path, monkeypatch):
    root = tmp_path / "root"
    deep = root / "experiments" / "2026"
    deep.mkdir(parents=True)
    wjson(root / SHARED, {"people": {"person1": "S"}})
    local = wjson(tmp_path / "l.json", {"people": {"person1": "Mine"}})  # no root
    monkeypatch.chdir(deep)
    c = model.resolve_config(None, str(local))
    assert c.root == root.resolve() and c.people["person1"] == "Mine"


def test_cwd_walk_up_lowest_precedence(tmp_path, monkeypatch):
    root, a = tmp_path / "root", tmp_path / "a"
    a.mkdir()
    wjson(root / SHARED, {})
    monkeypatch.chdir(root)
    local = wjson(tmp_path / "l.json", {"root": str(a)})
    assert model.resolve_config(None, str(local)).root == a  # local root beats cwd
    assert model.resolve_config(str(a), str(local)).root == a


def test_no_root_anywhere_still_exit_2(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # no shared config in any ancestor of tmp_path
    local = wjson(tmp_path / "l.json", {"people": {}})
    assert main(["lint", "--config", str(local)]) == 2


# ------------------------------------------------------------ 2. folders, @/ and asana_project
@pytest.mark.parametrize("bad", ["abc", "12a", "", "<ASANA_PROJECT_GID>", True, 1.5])
def test_asana_project_bad_value_exit_2(tmp_path, capsys, bad):
    root = tmp_path / "root"
    root.mkdir()
    local = wjson(tmp_path / "l.json", {"root": str(root), "projects": {"p": {"asana_project": bad}}})
    assert main(["lint", "--config", str(local)]) == 2
    assert "asana_project" in capsys.readouterr().err


def test_asana_project_bad_in_shared_exit_2(tmp_path):
    root = tmp_path / "root"
    wjson(root / SHARED, {"projects": {"p": {"asana_project": "x1"}}})
    local = wjson(tmp_path / "l.json", {"root": str(root)})
    assert main(["lint", "--config", str(local)]) == 2


def test_asana_project_digits_and_null_ok(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    local = wjson(tmp_path / "l.json", {"root": str(root), "projects": {
        "a": {"asana_project": "1200000000000001"}, "b": {"asana_project": None}}})
    assert model.resolve_config(None, str(local)).projects["a"]["asana_project"] == "1200000000000001"


def test_bad_folder_exit_2(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    local = wjson(tmp_path / "l.json", {"root": str(root), "projects": {"p": {"folder": 5}}})
    assert main(["lint", "--config", str(local)]) == 2


def test_example_config_loads(tmp_path):
    ex = json.loads((SCRIPTS.parent / "config.example.json").read_text(encoding="utf-8"))
    ex["root"] = str(tmp_path)
    local = wjson(tmp_path / "l.json", ex)
    assert "folder" in next(iter(model.resolve_config(None, str(local)).projects.values()))


@pytest.fixture
def proj(tmp_path):
    root = tmp_path / "lab-records"
    root.mkdir()
    (tmp_path / "9. Proj" / "sub").mkdir(parents=True)
    (tmp_path / "9. Proj" / "sub" / "f.csv").write_text("x", encoding="utf-8")
    cfg = wjson(tmp_path / "c.json", {"root": str(root), "people": {"person1": "J"},
                                      "projects": {"pa": {"folder": "../9. Proj"}, "pnof": {}}})
    rec(root, "protocols/PROT-001_v1.md", {"id": "PROT-001", "type": "prot", "title": "p",
                                           "version": "v1", "project": "pa"})
    return root, cfg


def exp(root, **extra):
    fm = {"id": "EXP-261001-01", "type": "exp", "title": "e", "protocol": "PROT-001@v1", "project": "pa"}
    fm.update(extra)
    return rec(root, "experiments/2026/EXP-261001-01.md", fm)


def test_at_path_resolves_against_project_folder(proj, capsys):
    root, cfg = proj
    exp(root, raw_data=["@/sub/f.csv"], links=[{"rel": "background", "path": "@/sub"}])
    assert lint(cfg, capsys)[0] == 0


def test_at_path_missing_file(proj, capsys):
    root, cfg = proj
    exp(root, raw_data=["@/sub/nope.csv"])
    code, lines, _ = lint(cfg, capsys)
    assert code == 1 and any(l.startswith("RULE7 EXP-261001-01") and "nope.csv" in l for l in lines)


def test_at_path_in_workbook_and_matrix_config(proj, capsys):
    root, cfg = proj
    exp(root, workbook="@/sub/f.csv", matrix_config="@/sub/gone.json")
    _, lines, _ = lint(cfg, capsys)
    assert [l for l in lines if l.startswith("RULE7")] == [
        "RULE7 EXP-261001-01 matrix_config path does not exist: @/sub/gone.json"]


def test_at_path_without_project_is_violation(proj, capsys):
    root, cfg = proj
    exp(root, project=None, raw_data=["@/sub/f.csv"])
    _, lines, _ = lint(cfg, capsys)
    assert any(l.startswith("RULE7") and "no project" in l for l in lines)


def test_at_path_project_without_folder_is_violation(proj, capsys):
    root, cfg = proj
    exp(root, project="pnof", raw_data=["@/sub/f.csv"])
    _, lines, _ = lint(cfg, capsys)
    assert any(l.startswith("RULE7") and "'pnof' has no folder" in l for l in lines)
    exp(root, project="unknown-tag", raw_data=["@/sub/f.csv"])
    assert any("unknown project key" in l for l in lint(cfg, capsys)[1])  # item 6d: separate message


def test_plain_relative_path_still_root_relative(proj, capsys):
    root, cfg = proj
    (root / "data").mkdir()
    (root / "data" / "a.csv").write_text("x", encoding="utf-8")
    exp(root, raw_data=["data/a.csv"])
    assert lint(cfg, capsys)[0] == 0
    exp(root, raw_data=["sub/f.csv"])  # exists only under the project folder, not the root
    assert lint(cfg, capsys)[0] == 1


def test_trace_resolves_at_path(proj, capsys):
    root, cfg = proj
    exp(root, raw_data=["@/sub/f.csv"])
    code, out = run(cfg, "trace", "EXP-261001-01", capsys=capsys)
    assert code == 0 and "9. Proj/sub/f.csv" in out.out.replace("\\", "/")


# ------------------------------------------------------------ 3. RULE8
def test_rule8_conflict_copy_reports_duplicate_and_filename(chain, capsys):
    root, cfg = chain
    src = root / "experiments/2026/EXP-261001-01.md"
    (root / "experiments/2026/EXP-261001-01-DESKTOP-AB12.md").write_bytes(src.read_bytes())
    code, lines, err = lint(cfg, capsys)
    r8 = [l for l in lines if l.startswith("RULE8")]
    assert code == 1 and "ERROR" not in err and "WARNING" not in err  # stderr = root line only
    assert ("RULE8 EXP-261001-01 duplicate id in experiments/2026/EXP-261001-01.md, "
            "experiments/2026/EXP-261001-01-DESKTOP-AB12.md") in r8
    assert ("RULE8 experiments/2026/EXP-261001-01-DESKTOP-AB12.md filename does not match its id "
            "(sync-conflict copy?)") in r8
    assert not any(l.startswith("RULE2") for l in lines)


def test_rule8_space_paren_copy_and_prot(chain, capsys):
    root, cfg = chain
    (root / "experiments/2026/EXP-261001-02 (1).md").write_bytes(
        (root / "experiments/2026/EXP-261001-02.md").read_bytes())
    (root / "protocols/PROT-001_v2 (conflicted copy).md").write_bytes(
        (root / "protocols/PROT-001_v2.md").read_bytes())
    _, lines, _ = lint(cfg, capsys)
    r8 = [l for l in lines if l.startswith("RULE8")]
    assert len(r8) == 4 and sum("duplicate id" in l for l in r8) == 2
    assert any(l.startswith("RULE8 PROT-001@v2 duplicate") for l in r8)


def test_rule8_prot_same_id_different_version_ok(chain, capsys):
    assert lint(chain[1], capsys)[0] == 0  # PROT-001 v1 and v2 coexist


def test_rule8_wrong_name_without_duplicate(chain, capsys):
    root, cfg = chain
    (root / "decisions/2026/DEC-261003-01.md").rename(root / "decisions/2026/decision-notes.md")
    _, lines, _ = lint(cfg, capsys)
    assert [l for l in lines if l.startswith("RULE8")] == [
        "RULE8 decisions/2026/decision-notes.md filename does not match its id (sync-conflict copy?)"]


def test_scan_ids_sees_conflict_copy_names(chain):
    root, _ = chain
    (root / "experiments/2026/EXP-261009-03-DESKTOP-AB12.md").write_text("x", encoding="utf-8")
    (root / "protocols/PROT-005_v2 (1).md").write_text("x", encoding="utf-8")
    ids = model.scan_ids(root)
    assert "EXP-261009-03" in ids and "PROT-005@v2" in ids


def test_new_skips_id_held_by_conflict_copy(lab, capsys):
    root, cfg = lab
    (root / "experiments/2026").mkdir(parents=True)
    (root / "experiments/2026/EXP-261001-01 (1).md").write_text("x", encoding="utf-8")
    code, out = run(cfg, "new", "exp", "--title", "a", "--protocol", "PROT-001@v1",
                    "--date", "261001", capsys=capsys)
    assert code == 0 and Path(out.out.strip()).name == "EXP-261001-02.md"


def test_new_refuses_when_id_exists_elsewhere(lab, monkeypatch):
    root, cfg = lab
    (root / "experiments/2026").mkdir(parents=True)
    (root / "experiments/2026/EXP-261001-01-DESKTOP-AB12.md").write_text("x", encoding="utf-8")
    c = model.resolve_config(str(root), str(cfg))
    monkeypatch.setattr(model, "scan_ids", lambda r: set())  # stale scan hands out a taken id
    with pytest.raises(model.LabRecordError, match="already exists"):
        commands.new_record(c, "exp", "x", protocol="PROT-001@v1", day=dt.date(2026, 10, 1))
    monkeypatch.undo()
    assert main(["new", "exp", "--title", "x", "--protocol", "PROT-001@v1", "--date", "261001",
                 "--config", str(cfg)]) == 0  # real scan skips to -02, no refusal


def test_new_refusal_exits_2_via_cli(lab, monkeypatch):
    root, cfg = lab
    (root / "experiments/2026").mkdir(parents=True)
    (root / "experiments/2026/EXP-261001-01-DESKTOP-AB12.md").write_text("x", encoding="utf-8")
    monkeypatch.setattr(model, "scan_ids", lambda r: set())
    assert main(["new", "exp", "--title", "x", "--protocol", "PROT-001@v1", "--date", "261001",
                 "--config", str(cfg)]) == 2


# ------------------------------------------------------------ 4. typed links
def links(root, items):
    edit(root / "experiments/2026/EXP-261001-01.md", lambda fm, b: ({**fm, "links": items}, b))


def test_asana_links_valid(chain, capsys):
    root, cfg = chain
    links(root, [{"rel": "asana", "task": "1200000000000001"}, {"rel": "asana", "project": "99"},
                 {"rel": "asana", "task": 1234}])
    assert lint(cfg, capsys)[0] == 0


@pytest.mark.parametrize("item", [{"rel": "asana", "task": "12x"}, {"rel": "asana", "project": ""},
                                  {"rel": "asana", "task": "https://app.asana.com/0/1/2"},
                                  {"rel": "asana", "task": True}])
def test_asana_links_bad_digits(chain, capsys, item):
    root, cfg = chain
    links(root, [item])
    _, lines, _ = lint(cfg, capsys)
    assert any(l.startswith("RULE2 EXP-261001-01") and "digits only" in l for l in lines)


def test_asana_link_without_task_or_project(chain, capsys):
    root, cfg = chain
    links(root, [{"rel": "asana"}])
    assert any("needs `task` or `project`" in l for l in lint(cfg, capsys)[1])


def test_background_and_legacy_path_links(chain, capsys):
    root, cfg = chain
    (root / "bg").mkdir()
    (root / "bg" / "review.pdf").write_text("x", encoding="utf-8")
    links(root, [{"rel": "background", "path": "bg/review.pdf"}, {"rel": "legacy", "path": "bg/review.pdf"}])
    assert lint(cfg, capsys)[0] == 0
    links(root, [{"rel": "background", "path": "bg/gone.pdf"}])
    _, lines, _ = lint(cfg, capsys)
    assert any(l.startswith("RULE7") and "background link path does not exist" in l for l in lines)


def test_unknown_rel_needs_id_path_or_gid(chain, capsys):
    root, cfg = chain
    links(root, [{"rel": "mystery"}])
    assert any(l.startswith("RULE2") and "no id, path, task or project" in l for l in lint(cfg, capsys)[1])
    links(root, [{"rel": "mystery", "id": "DISC-261002-01"}])
    assert lint(cfg, capsys)[0] == 0
    links(root, [{"rel": "mystery", "id": "DISC-999999-99"}])
    assert any(l.startswith("RULE2") and "does not resolve" in l for l in lint(cfg, capsys)[1])


def test_cli_cwd_discovery_subprocess(tmp_path):
    root = tmp_path / "lab-records"
    wjson(root / SHARED, {"people": {"person1": "S"}})
    env = {**os.environ, "HOME": str(tmp_path), "USERPROFILE": str(tmp_path)}
    env.pop("LAB_RECORD_ROOT", None)
    r = subprocess.run([sys.executable, str(SCRIPTS / "lab_record.py"), "lint"], cwd=root,
                       capture_output=True, encoding="utf-8", env=env)
    assert r.returncode == 0, r.stderr
