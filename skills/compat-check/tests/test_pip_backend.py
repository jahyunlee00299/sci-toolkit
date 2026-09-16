"""Force the pip fallback backend (simulates a machine without uv) and re-run
the same scenarios as test_runner.py — this is the actual robustness proof
the user asked for, not just "it works when uv happens to be installed"."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from compat_check.runner import probe_once, _PipBackend

_PIP = _PipBackend()


def test_pip_all_ok():
    r = probe_once(["requests>=2.0"], backend=_PIP)
    assert r.ok is True
    assert any(p.startswith("requests-") for p in r.resolved_packages), r.resolved_packages


def test_pip_empty_requirements():
    r = probe_once([], backend=_PIP)
    assert r.ok is True


def test_pip_single_unsatisfiable_version():
    r = probe_once(["numpy==0.0.1"], backend=_PIP)
    assert r.ok is False
    assert r.failing_package == "numpy", r.stdout


def test_pip_mutually_conflicting_constraints():
    r = probe_once(["numpy>=2.0", "numpy<1.20"], backend=_PIP)
    assert r.ok is False
    assert r.failing_package == "numpy", r.stdout


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            print(f"running {name}...")
            fn()
            print(f"  PASS")
    print("\nall pip-backend tests passed")
