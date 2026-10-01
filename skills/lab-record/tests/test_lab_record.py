"""Tests for lab-record. Run from the skill directory: python -m pytest tests -q"""
from __future__ import annotations

import datetime as dt
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lab_record_lib import model  # noqa: E402
from lab_record_lib.cli import main  # noqa: E402
from lab_record_lib.parse import compose, read_text, write_text  # noqa: E402

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


# ---------------------------------------------------------------- helpers
def rec(root: Path, rel: str, fm: dict, body: str = "Body text.\n") -> Path:
    base = {"status": "draft", "owner": "person1", "project": "t", "created": "2026-10-01",
            "updated": "2026-10-01", "aliases": [], "supersedes": None, "links": []}
    base.update(fm)
    path = root / rel
    write_text(path, compose(base, body))
    return path


def build_chain(root: Path) -> None:
    """PROT-001 v1 -> v2; EXP-01 (v1), EXP-02 (v2); DISC about EXP-01; DEC from DISC."""
    (root / "data").mkdir(parents=True, exist_ok=True)
    (root / "data" / "a.csv").write_text("x\n", encoding="utf-8")
    rec(root, "protocols/PROT-001_v1.md", {"id": "PROT-001", "type": "prot", "title": "P1",
                                           "version": "v1", "status": "superseded"})
    rec(root, "protocols/PROT-001_v2.md", {"id": "PROT-001", "type": "prot", "title": "P2",
                                           "version": "v2", "changed_from": "v1",
                                           "supersedes": "PROT-001@v1"})
    rec(root, "experiments/2026/EXP-261001-01.md",
        {"id": "EXP-261001-01", "type": "exp", "title": "run one", "protocol": "PROT-001@v1",
         "raw_data": ["data/a.csv"]})
    rec(root, "experiments/2026/EXP-261001-02.md",
        {"id": "EXP-261001-02", "type": "exp", "title": "run two", "protocol": "PROT-001@v2"})
    rec(root, "discussions/2026/DISC-261002-01.md",
        {"id": "DISC-261002-01", "type": "disc", "title": "talk", "about": ["EXP-261001-01"],
         "participants": ["person1"], "context_checklist": {"T": "ok", "pH": "unknown", "E": "n/a"},
         "open_questions": ["why plateau?"]})
    rec(root, "decisions/2026/DEC-261003-01.md",
        {"id": "DEC-261003-01", "type": "dec", "title": "decide", "from": ["DISC-261002-01"],
         "revisit_if": "fit shows inhibition", "next": [{"kind": "protocol", "id": "PROT-001@v2"}]})


@pytest.fixture
def lab(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({"root": str(root), "people": {"person1": "J"}}), encoding="utf-8")
    return root, cfg


@pytest.fixture
def chain(lab):
    root, cfg = lab
    build_chain(root)
    return root, cfg


def run(cfg, *args, capsys=None):
    code = main([*args, "--config", str(cfg)])
    out = capsys.readouterr() if capsys else None
    return code, out


def edit(path: Path, fn) -> None:
    from lab_record_lib.parse import parse
    fm, body = parse(read_text(path))
    fm, body = fn(fm, body)
    write_text(path, compose(fm, body))


def lint(cfg, capsys):
    code, out = run(cfg, "lint", capsys=capsys)
    return code, out.out.splitlines(), out.err


def git(root: Path, *a: str) -> None:
    subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", *a],
                   check=True, capture_output=True)


# ---------------------------------------------------------------- CLI option placement
@pytest.mark.parametrize("before", [True, False])
def test_config_flag_before_or_after_subcommand(lab, capsys, before):
    root, cfg = lab
    args = ["--config", str(cfg), "new", "prot", "--title", "p"] if before \
        else ["new", "prot", "--title", "p", "--config", str(cfg)]
    assert main(args) == 0
    assert (root / "protocols/PROT-001_v1.md").exists()


# ---------------------------------------------------------------- ID allocation
def test_id_allocation_and_layout(lab, capsys):
    root, cfg = lab
    for expected in ("EXP-261001-01", "EXP-261001-02"):
        code, out = run(cfg, "new", "exp", "--title", "a", "--protocol", "PROT-001@v1",
                        "--date", "261001", capsys=capsys)
        assert code == 0 and Path(out.out.strip()).name == f"{expected}.md"
        assert (root / "experiments" / "2026" / f"{expected}.md").exists()
    run(cfg, "new", "exp", "--title", "b", "--protocol", "PROT-001@v1", "--date", "261002", capsys=capsys)
    assert (root / "experiments/2026/EXP-261002-01.md").exists()
    run(cfg, "new", "prot", "--title", "p", capsys=capsys)
    run(cfg, "new", "prot", "--title", "q", capsys=capsys)
    assert (root / "protocols/PROT-001_v1.md").exists() and (root / "protocols/PROT-002_v1.md").exists()
    run(cfg, "new", "disc", "--title", "d", "--about", "EXP-261001-01", "--date", "261003", capsys=capsys)
    run(cfg, "new", "dec", "--title", "d", "--from", "DISC-261003-01", "--date", "261003", capsys=capsys)
    assert (root / "discussions/2026/DISC-261003-01.md").exists()
    assert (root / "decisions/2026/DEC-261003-01.md").exists()


def test_id_collision_retry(lab, monkeypatch):
    root, cfg = lab
    c = model.resolve_config(str(root), str(cfg))
    from lab_record_lib import commands
    first = commands.new_record(c, "exp", "one", protocol="PROT-001@v1", day=dt.date(2026, 10, 1))
    real, calls = model.scan_ids, []

    def stale(r):  # first scan misses the file another session just wrote
        calls.append(1)
        return set() if len(calls) == 1 else real(r)

    monkeypatch.setattr(model, "scan_ids", stale)
    second = commands.new_record(c, "exp", "two", protocol="PROT-001@v1", day=dt.date(2026, 10, 1))
    assert first.name == "EXP-261001-01.md" and second.name == "EXP-261001-02.md"
    assert len(calls) == 2  # rescanned after the FileExistsError


def test_new_prot_version_and_supersede(lab, capsys):
    root, cfg = lab
    run(cfg, "new", "prot", "--title", "Method", capsys=capsys)
    code, _ = run(cfg, "new", "prot", "--from-prot", "PROT-001", "--reason", "additive moved", capsys=capsys)
    assert code == 0
    v2 = read_text(root / "protocols/PROT-001_v2.md")
    assert "version: v2" in v2 and "changed_from: v1" in v2 and "supersedes: PROT-001@v1" in v2
    assert "status: superseded" in read_text(root / "protocols/PROT-001_v1.md")
    assert lint(cfg, capsys)[0] == 0


# ---------------------------------------------------------------- lint: clean + each rule
def test_clean_chain_passes(chain, capsys):
    _, cfg = chain
    code, lines, err = lint(cfg, capsys)
    assert code == 0 and lines == [], (lines, err)


def test_rule2_unresolved_reference(chain, capsys):
    root, cfg = chain
    edit(root / "decisions/2026/DEC-261003-01.md",
         lambda fm, b: ({**fm, "from": ["DISC-999999-01"]}, b))
    code, lines, _ = lint(cfg, capsys)
    assert code == 1 and any(l.startswith("RULE2 DEC-261003-01 ") for l in lines)


def test_rule2_next_id_and_links(chain, capsys):
    root, cfg = chain
    edit(root / "decisions/2026/DEC-261003-01.md",
         lambda fm, b: ({**fm, "next": [{"kind": "protocol", "id": "PROT-001@v9"}],
                         "links": [{"rel": "see-also", "id": "EXP-000000-00"}]}, b))
    _, lines, _ = lint(cfg, capsys)
    assert sum(l.startswith("RULE2 DEC-261003-01") for l in lines) == 2


def test_rule3_unpinned_protocol(chain, capsys):
    root, cfg = chain
    edit(root / "experiments/2026/EXP-261001-02.md", lambda fm, b: ({**fm, "protocol": "PROT-001"}, b))
    code, lines, _ = lint(cfg, capsys)
    assert code == 1 and any(l.startswith("RULE3 EXP-261001-02 ") for l in lines)


def test_rule3_unpinned_in_about_and_next(chain, capsys):
    root, cfg = chain
    edit(root / "discussions/2026/DISC-261002-01.md", lambda fm, b: ({**fm, "about": ["PROT-001"]}, b))
    edit(root / "decisions/2026/DEC-261003-01.md",
         lambda fm, b: ({**fm, "next": [{"kind": "protocol", "id": "PROT-001"}]}, b))
    _, lines, _ = lint(cfg, capsys)
    assert any(l.startswith("RULE3 DISC-261002-01") for l in lines)
    assert any(l.startswith("RULE3 DEC-261003-01") for l in lines)


def test_rule4_orphans(chain, capsys):
    root, cfg = chain
    edit(root / "discussions/2026/DISC-261002-01.md", lambda fm, b: ({**fm, "about": []}, b))
    edit(root / "decisions/2026/DEC-261003-01.md", lambda fm, b: ({**fm, "from": []}, b))
    code, lines, _ = lint(cfg, capsys)
    assert code == 1
    assert any(l.startswith("RULE4 DISC-261002-01") for l in lines)
    assert any(l.startswith("RULE4 DEC-261003-01") for l in lines)


def test_rule4_missing_field_is_orphan(chain, capsys):
    root, cfg = chain
    edit(root / "decisions/2026/DEC-261003-01.md", lambda fm, b: ({k: v for k, v in fm.items() if k != "from"}, b))
    assert any(l.startswith("RULE4 DEC-261003-01") for l in lint(cfg, capsys)[1])


def test_rule5_checklist_values(chain, capsys):
    root, cfg = chain
    edit(root / "discussions/2026/DISC-261002-01.md",
         lambda fm, b: ({**fm, "context_checklist": {"T": "ok", "pH": "maybe", "E": True}}, b))
    _, lines, _ = lint(cfg, capsys)
    assert sum(l.startswith("RULE5 DISC-261002-01") for l in lines) == 2


def test_rule6_people_keys(chain, capsys):
    root, cfg = chain
    edit(root / "experiments/2026/EXP-261001-01.md", lambda fm, b: ({**fm, "owner": "Real Name"}, b))
    edit(root / "discussions/2026/DISC-261002-01.md",
         lambda fm, b: ({**fm, "participants": ["person1", "who@example.org"]}, b))
    _, lines, _ = lint(cfg, capsys)
    assert any(l.startswith("RULE6 EXP-261001-01") for l in lines)
    assert any(l.startswith("RULE6 DISC-261002-01") and "who@example.org" in l for l in lines)


def test_rule7_raw_data_and_legacy_link(chain, capsys):
    root, cfg = chain
    edit(root / "experiments/2026/EXP-261001-01.md",
         lambda fm, b: ({**fm, "raw_data": ["data/a.csv", "data/missing.csv"],
                         "links": [{"rel": "legacy", "path": "old/Notes.md"}]}, b))
    _, lines, _ = lint(cfg, capsys)
    assert sum(l.startswith("RULE7 EXP-261001-01") for l in lines) == 2
    (root / "old").mkdir()
    (root / "old" / "Notes.md").write_text("x", encoding="utf-8")
    (root / "data" / "missing.csv").write_text("x", encoding="utf-8")
    assert lint(cfg, capsys)[0] == 0


# ---------------------------------------------------------------- rule 1 (closed = append-only)
def test_rule1_hash_mode(chain, capsys):
    root, cfg = chain
    assert run(cfg, "close", "EXP-261001-01", capsys=capsys)[0] == 0
    assert (root / ".lab_record" / "hashes.json").is_file()
    assert lint(cfg, capsys)[0] == 0
    path = root / "experiments/2026/EXP-261001-01.md"
    original = read_text(path)

    edit(path, lambda fm, b: ({**fm, "outcome_summary": "changed"}, b))  # frontmatter edit
    code, lines, _ = lint(cfg, capsys)
    assert code == 1 and any(l.startswith("RULE1 EXP-261001-01") for l in lines)

    write_text(path, original.replace("Body text.", "Body TEXT."))  # body edit
    code, lines, _ = lint(cfg, capsys)
    assert code == 1 and any(l.startswith("RULE1 EXP-261001-01") for l in lines)

    write_text(path, original + "\n## Addendum (2026-10-05)\nLate note.\n")  # allowed
    assert lint(cfg, capsys)[0] == 0
    write_text(path, original + "\n## Addendum (2026-10-05)\nLate note.\n\nsneaky\n\n## Addendum (2026-10-06)\nTwo.\n")
    assert lint(cfg, capsys)[0] == 0  # text inside the addendum section is still addendum text
    write_text(path, original + "\nplain appended text\n")  # not under an Addendum heading
    assert lint(cfg, capsys)[0] == 1


def test_rule1_hash_mode_missing_baseline(chain, capsys):
    root, cfg = chain
    edit(root / "experiments/2026/EXP-261001-01.md", lambda fm, b: ({**fm, "status": "closed"}, b))
    _, lines, _ = lint(cfg, capsys)
    assert any(l.startswith("RULE1 EXP-261001-01") and "no stored hash" in l for l in lines)


@needs_git
def test_rule1_git_mode(chain, capsys):
    root, cfg = chain
    git(root, "init", "-q")
    assert run(cfg, "close", "EXP-261001-01", capsys=capsys)[0] == 0
    assert (root / ".lab_record" / "hashes.json").is_file()  # close ALWAYS writes the hash baseline too
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "baseline")
    assert lint(cfg, capsys)[0] == 0
    path = root / "experiments/2026/EXP-261001-01.md"
    original = read_text(path)

    edit(path, lambda fm, b: ({**fm, "protocol": "PROT-001@v2"}, b))
    code, lines, _ = lint(cfg, capsys)
    assert code == 1 and any(l.startswith("RULE1 EXP-261001-01") for l in lines)

    write_text(path, original.replace("Body text.", "Different."))
    assert lint(cfg, capsys)[0] == 1

    write_text(path, original + "\n## Addendum (2026-10-05)\nLate note.\n")
    assert lint(cfg, capsys)[0] == 0

    edit(path, lambda fm, b: ({**fm, "status": "draft"}, b))  # reopening is also an edit
    assert lint(cfg, capsys)[0] == 1


@needs_git
def test_rule1_git_mode_uncommitted_closed_not_flagged(chain, capsys):
    root, cfg = chain
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "base")
    run(cfg, "close", "EXP-261001-01", capsys=capsys)  # HEAD copy is still draft
    path = root / "experiments/2026/EXP-261001-01.md"
    edit(path, lambda fm, b: ({**fm, "outcome_summary": "ok"}, b))
    assert lint(cfg, capsys)[0] == 0


def test_closed_prot_may_become_superseded(lab, capsys):
    root, cfg = lab
    run(cfg, "new", "prot", "--title", "Method", capsys=capsys)
    run(cfg, "close", "PROT-001@v1", capsys=capsys)
    assert run(cfg, "new", "prot", "--from-prot", "PROT-001", capsys=capsys)[0] == 0
    assert "status: superseded" in read_text(root / "protocols/PROT-001_v1.md")
    code, lines, _ = lint(cfg, capsys)
    assert code == 0, lines


# ---------------------------------------------------------------- trace / impact / open
def test_trace_impact_open(chain, capsys):
    root, cfg = chain
    _, out = run(cfg, "trace", "DEC-261003-01", capsys=capsys)
    t = out.out
    assert t.index("DEC-261003-01") < t.index("DISC-261002-01") < t.index("EXP-261001-01") < t.index("PROT-001@v1")
    assert "raw_data:" in t and "a.csv" in t and "EXP-261001-02" not in t

    _, out = run(cfg, "impact", "PROT-001@v1", capsys=capsys)
    assert "EXP-261001-01" in out.out and "DISC-261002-01" in out.out and "DEC-261003-01" in out.out
    assert "EXP-261001-02" not in out.out
    _, out = run(cfg, "impact", "PROT-001@v2", capsys=capsys)
    assert "EXP-261001-02" in out.out and "DEC-261003-01" not in out.out
    assert run(cfg, "impact", "PROT-001", capsys=capsys)[0] == 1  # must be pinned

    _, out = run(cfg, "open", capsys=capsys)
    assert "DISC-261002-01 open_questions: why plateau?" in out.out
    assert "DEC-261003-01 revisit_if" in out.out
    assert "EXP-261001-02 not discussed" in out.out and "EXP-261001-01 not discussed" not in out.out
    assert run(cfg, "trace", "DEC-000000-00", capsys=capsys)[0] == 1


def test_index_generated(chain, capsys):
    root, cfg = chain
    code, _ = run(cfg, "index", capsys=capsys)
    text = read_text(root / "INDEX.md")
    assert code == 0 and "GENERATED" in text.splitlines()[0]
    assert "PROT-001@v2" in text and "DEC-261003-01" in text
    assert lint(cfg, capsys)[0] == 0  # INDEX.md is not a record


# ---------------------------------------------------------------- Korean, errors, root resolution
def test_korean_title_roundtrip(lab, capsys):
    root, cfg = lab
    title = "포화 cascade, 50 uL: 첨가제 스윕 \"테스트\""
    run(cfg, "new", "prot", "--title", title, capsys=capsys)
    run(cfg, "new", "exp", "--title", title, "--protocol", "PROT-001@v1", capsys=capsys)
    recs, errors = model.scan(root)
    assert not errors and {r.fm["title"] for r in recs} == {title}
    assert lint(cfg, capsys)[0] == 0
    run(cfg, "index", capsys=capsys)
    assert title.split(":")[0] in read_text(root / "INDEX.md")


def test_korean_path_and_raw_data(chain, capsys):
    root, cfg = chain
    (root / "data" / "한글_원본.csv").write_text("x", encoding="utf-8")
    edit(root / "experiments/2026/EXP-261001-01.md",
         lambda fm, b: ({**fm, "raw_data": ["data/한글_원본.csv"]}, b))
    assert lint(cfg, capsys)[0] == 0


def test_malformed_frontmatter_exit_2(chain, capsys):
    root, cfg = chain
    (root / "experiments/2026/EXP-261001-03.md").write_text("---\nid: [unclosed\n---\nbody\n", encoding="utf-8")
    code, _, err = lint(cfg, capsys)
    assert code == 2 and "EXP-261001-03.md" in err


def test_no_frontmatter_and_bad_utf8_exit_2(chain, capsys):
    root, cfg = chain
    (root / "experiments/2026/EXP-261001-03.md").write_text("just text\n", encoding="utf-8")
    assert lint(cfg, capsys)[0] == 2
    (root / "experiments/2026/EXP-261001-03.md").write_bytes(b"---\nid: \xff\xfe\n---\n")
    code, _, err = lint(cfg, capsys)
    assert code == 2 and "unreadable" in err


def test_missing_root_exit_2(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("LAB_RECORD_ROOT", raising=False)
    cfg = tmp_path / "c.json"
    cfg.write_text(json.dumps({"people": {}}), encoding="utf-8")
    assert main(["lint", "--config", str(cfg)]) == 2
    assert main(["lint", "--root", str(tmp_path / "nope"), "--config", str(cfg)]) == 2
    assert main(["lint", "--config", str(tmp_path / "absent.json")]) == 2
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert main(["lint", "--root", str(tmp_path), "--config", str(bad)]) == 2


def test_root_precedence(tmp_path, monkeypatch):
    a, b, c = (tmp_path / n for n in "abc")
    for d in (a, b, c):
        d.mkdir()
    cfg = tmp_path / "c.json"
    cfg.write_text(json.dumps({"root": str(c), "people": {"person1": "x"}}), encoding="utf-8")
    monkeypatch.setenv("LAB_RECORD_ROOT", str(b))
    assert model.resolve_config(str(a), str(cfg)).root == a
    assert model.resolve_config(None, str(cfg)).root == b
    monkeypatch.delenv("LAB_RECORD_ROOT")
    cfgd = model.resolve_config(None, str(cfg))
    assert cfgd.root == c and cfgd.people == {"person1": "x"}


def test_entry_script_subprocess(lab):
    root, cfg = lab
    r = subprocess.run([sys.executable, str(SCRIPTS / "lab_record.py"), "new", "prot",
                        "--title", "한글 제목", "--config", str(cfg)],
                       capture_output=True, encoding="utf-8")
    assert r.returncode == 0 and r.stdout.strip().endswith("PROT-001_v1.md")
    r = subprocess.run([sys.executable, str(SCRIPTS / "lab_record.py"), "lint", "--config", str(cfg)],
                       capture_output=True, encoding="utf-8")
    assert r.returncode == 0
