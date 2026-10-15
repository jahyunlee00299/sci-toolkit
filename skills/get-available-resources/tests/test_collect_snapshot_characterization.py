"""Golden tests pinning how `collect_snapshot` behaves around its output.

test_detect_resources_characterization.py pins the VALUES it returns over fake
hosts. collect_snapshot_trace.py pins what those values cannot show: the order in
which the probes touch the host, that the caller's `environ` is left alone, the
default-argument branches (psutil on demand, os.environ, the clock), that no two
results share a mutable object, and the signature. The golden file was produced
from the single 125-line function; splitting it into stages leaves it untouched.
"""
import json

import pytest

import collect_snapshot_trace as cst

GOLDEN = json.loads((cst.GOLDEN / "collect_snapshot.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def traced():
    mp = pytest.MonkeyPatch()
    try:
        return cst.build_all(mp)
    finally:
        mp.undo()  # the fake host must not stay patched for the rest of the module


def _norm(value):
    return json.loads(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str))


@pytest.mark.parametrize("group", sorted(GOLDEN))
def test_group_matches_golden(traced, group):
    actual = _norm(traced[group])
    expected = GOLDEN[group]
    assert sorted(actual) == sorted(expected)
    for key in expected:
        assert actual[key] == expected[key], f"{group}/{key} drifted from the golden snapshot"


def test_probe_log_covers_every_host_scenario_and_every_probe_kind():
    order = GOLDEN["probe_order"]
    values = json.loads((cst.GOLDEN / "detect_resources.json").read_text(encoding="utf-8"))
    assert sorted(order) == sorted([*values["snapshots"], *values["environment_errors"]]), \
        "every host scenario in the value golden needs a probe log, and no other"
    assert all(entry["environ_unchanged"] for entry in order.values())
    events = [event for entry in order.values() for event in entry["probes"].get("events", [])]
    assert {event[0] for event in events} == {"read", "run"}, \
        "the scenarios no longer exercise both file reads and commands"
    paths = {event[1] for event in events if event[0] == "read"}
    assert "/proc/self/cgroup" in paths and "/proc/meminfo" in paths


def test_default_branches_are_all_exercised():
    defaults = GOLDEN["defaults"]
    imported = [c for c in defaults["psutil_imported_on_demand"]["provenance"]
                if c["component"] == "inventory.psutil"]
    missing = [c for c in defaults["psutil_missing_on_demand"]["provenance"]
               if c["component"] == "inventory.psutil"]
    assert imported[0]["status"] == "ok" and missing[0]["status"] == "unavailable"
    for clock in ("observed_at_from_clock", "empty_observed_at_falls_back_to_clock"):
        assert defaults[clock]["iso_utc_seconds"] and defaults[clock]["within_call_window"]
    assert defaults["environ_from_process_environment"]["scheduler"]["detected"]
    assert not defaults["empty_environ_ignores_process_environment"]["scheduler"]["detected"]


def test_results_are_fresh_objects():
    fresh = GOLDEN["fresh_output"]
    assert fresh["two_calls_equal"] and fresh["emptied_result_does_not_leak_into_next_call"]
