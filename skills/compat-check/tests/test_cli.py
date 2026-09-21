"""End-to-end tests for the compat-check CLI — exercises the full
fetcher -> cache/runner -> report pipeline, including exit codes."""
import io
from contextlib import redirect_stdout, redirect_stderr
from unittest import mock


from compat_check.cli import main


def _run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = main(argv)
    return rc, out.getvalue(), err.getvalue()


def test_success_exits_zero():
    rc, out, _ = _run(["requests", "--no-cache"])
    assert rc == 0
    assert "OK" in out
    assert "requests" in out


def test_fetch_failure_exits_two():
    rc, _, err = _run(["this-package-definitely-does-not-exist-xyz123"])
    assert rc == 2
    assert "could not resolve" in err


def test_conflicting_requirements_exit_one_and_report_package():
    with mock.patch("compat_check.cli.fetch_requirements",
                     return_value=["numpy>=2.0", "numpy<1.20"]):
        rc, out, _ = _run(["fake-conflicting-package", "--no-cache"])
    assert rc == 1
    assert "PROBLEMS FOUND" in out
    assert "[numpy]" in out


def test_cache_hit_reported_on_second_call():
    _run(["requests"])  # warm the cache
    _, out, _ = _run(["requests"])
    assert "(cached)" in out


def test_tree_flag_shows_source_as_root_with_children():
    rc, out, _ = _run(["https://github.com/pallets/flask", "--no-cache", "--tree"])
    assert rc == 0
    assert "https://github.com/pallets/flask" in out
    assert "markupsafe" in out


def test_tree_flag_on_conflict_reports_unavailable_without_crashing():
    with mock.patch("compat_check.cli.fetch_requirements",
                     return_value=["numpy>=2.0", "numpy<1.20"]):
        rc, out, err = _run(["fake-conflict", "--no-cache", "--tree"])
    assert rc == 1  # the probe_all() failure still drives the exit code
    assert "PROBLEMS FOUND" in out
    assert "tree unavailable" in err


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            print(f"running {name}...")
            fn()
            print(f"  PASS")
    print("\nall CLI tests passed")
