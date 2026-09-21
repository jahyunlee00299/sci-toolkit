"""Integration tests for compat_check.cache — real probe_all() calls, real SQLite file."""
import tempfile
import time
from pathlib import Path


from compat_check.cache import cached_probe_all, make_cache_key


def test_cache_key_ignores_requirement_order():
    a = make_cache_key(["requests>=2.0", "numpy==1.0"], "3.11", "pip")
    b = make_cache_key(["numpy==1.0", "requests>=2.0"], "3.11", "pip")
    assert a == b


def test_cache_key_differs_by_python_version():
    a = make_cache_key(["requests>=2.0"], "3.11", "pip")
    b = make_cache_key(["requests>=2.0"], "3.12", "pip")
    assert a != b


def test_first_call_misses_second_call_hits_and_is_faster():
    with tempfile.TemporaryDirectory(prefix="compat_check_cache_test_") as tmp:
        db_path = Path(tmp) / "history.db"

        t0 = time.monotonic()
        first = cached_probe_all(["numpy==0.0.1"], db_path=db_path)
        first_elapsed = time.monotonic() - t0
        assert first["cache_hit"] is False
        assert first["ok"] is False

        t0 = time.monotonic()
        second = cached_probe_all(["numpy==0.0.1"], db_path=db_path)
        second_elapsed = time.monotonic() - t0
        assert second["cache_hit"] is True
        assert second["ok"] == first["ok"]
        assert second["failures"] == first["failures"]

        # cache hit must be substantially faster than a real dry-run probe
        assert second_elapsed < first_elapsed / 5, (
            f"cache hit ({second_elapsed:.3f}s) not much faster than miss ({first_elapsed:.3f}s)"
        )


def test_expired_entry_forces_a_fresh_probe():
    with tempfile.TemporaryDirectory(prefix="compat_check_cache_test_") as tmp:
        db_path = Path(tmp) / "history.db"

        first = cached_probe_all(["numpy==0.0.1"], db_path=db_path, ttl_seconds=0)
        assert first["cache_hit"] is False

        # ttl_seconds=0 means any elapsed time expires it immediately
        time.sleep(0.01)
        second = cached_probe_all(["numpy==0.0.1"], db_path=db_path, ttl_seconds=0)
        assert second["cache_hit"] is False


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            print(f"running {name}...")
            fn()
            print("  PASS")
    print("\nall tests passed")
