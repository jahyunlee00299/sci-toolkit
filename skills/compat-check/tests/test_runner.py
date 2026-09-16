"""Integration tests for compat_check.runner — these call real `uv` and hit PyPI."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from compat_check.runner import probe_all


def test_all_ok_reports_resolved_packages():
    result = probe_all(["requests>=2.0"])
    assert result["ok"] is True
    assert result["failures"] == []
    assert any(p.startswith("requests==") for p in result["resolved"])


def test_empty_requirements_is_ok():
    result = probe_all([])
    assert result["ok"] is True
    assert result["failures"] == []
    assert result["resolved"] == []


def test_single_unsatisfiable_version():
    result = probe_all(["numpy==0.0.1"])
    assert result["ok"] is False
    assert len(result["failures"]) == 1
    assert result["failures"][0]["package"] == "numpy"


def test_two_simultaneous_failures_both_surfaced():
    result = probe_all(["requests>=2.0", "numpy==0.0.1", "scipy==999.999.999"])
    assert result["ok"] is False
    failing_pkgs = {f["package"] for f in result["failures"]}
    assert failing_pkgs == {"numpy", "scipy"}


def test_mutually_conflicting_constraints():
    result = probe_all(["numpy>=2.0", "numpy<1.20"])
    assert result["ok"] is False
    assert result["failures"][0]["package"] == "numpy"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            print(f"running {name}...")
            fn()
            print(f"  PASS")
    print("\nall tests passed")
