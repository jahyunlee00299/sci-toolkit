"""Verify the uv/pip auto-selection actually switches when uv is unavailable —
this is the core of the robustness fix (users' machines often lack uv)."""
from unittest import mock


from compat_check.runner import _select_backend


def test_falls_back_to_pip_when_uv_absent():
    with mock.patch("shutil.which", return_value=None):
        backend = _select_backend()
    assert backend.name == "pip"


def test_prefers_uv_when_present():
    with mock.patch("shutil.which", return_value=r"C:\fake\uv.exe"):
        backend = _select_backend()
    assert backend.name == "uv"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            print(f"running {name}...")
            fn()
            print(f"  PASS")
    print("\nall backend-selection tests passed")
