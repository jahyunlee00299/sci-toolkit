"""Tests for compat_check.tree — parses uv's text dependency tree into a
nested structure. Real uv calls, no mocks (uv's output format is exactly
what this module depends on being right)."""
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from compat_check.tree import build_tree


def _find(nodes, name):
    for n in nodes:
        if n["name"] == name:
            return n
    return None


def test_flask_tree_has_expected_shape():
    result = build_tree(["flask"])
    assert result["ok"] is True
    assert len(result["roots"]) == 1
    flask = result["roots"][0]
    assert flask["name"] == "flask"

    child_names = {c["name"] for c in flask["children"]}
    assert {"blinker", "click", "itsdangerous", "jinja2", "markupsafe", "werkzeug"} <= child_names

    jinja2 = _find(flask["children"], "jinja2")
    assert _find(jinja2["children"], "markupsafe") is not None


def test_conflicting_requirements_reports_failure_not_crash():
    result = build_tree(["numpy>=2.0", "numpy<1.20"])
    assert result["ok"] is False
    assert result["roots"] == []
    assert "numpy" in result["stderr"]


def test_multiple_top_level_requirements_each_get_a_root():
    result = build_tree(["requests", "flask"])
    assert result["ok"] is True
    names = {r["name"] for r in result["roots"]}
    assert names == {"requests", "flask"}


def test_falls_back_cleanly_without_uv():
    with mock.patch("shutil.which", return_value=None):
        result = build_tree(["requests"])
    assert result["ok"] is False
    assert result["roots"] == []
    assert "uv" in result["stderr"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            print(f"running {name}...")
            fn()
            print(f"  PASS")
    print("\nall tree tests passed")
