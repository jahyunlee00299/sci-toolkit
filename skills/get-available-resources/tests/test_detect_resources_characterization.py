"""Golden tests pinning scripts/detect_resources.py across its split (refactor batch 3).

host_probe_snapshots.py builds deterministic fake hosts and drives
`collect_snapshot` plus every pure parser; the golden file was produced from the
unsplit 1767-line script. A behaviour-preserving split leaves it untouched; a
changed JSON field, warning code, provenance record, CLI flag or exit code fails.
"""
import json

import pytest

import host_probe_snapshots as hps

GOLDEN = json.loads((hps.GOLDEN / "detect_resources.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def snapshot(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    try:
        yield hps.build_all(mp, tmp_path_factory.mktemp("cli"))
    finally:
        mp.undo()


def _norm(value):
    return json.loads(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str))


@pytest.mark.parametrize("group", sorted(GOLDEN))
def test_group_matches_golden(snapshot, group):
    actual = _norm(snapshot[group])
    expected = GOLDEN[group]
    assert sorted(actual) == sorted(expected)
    for key in expected:
        assert actual[key] == expected[key], f"{group}/{key} drifted from the golden snapshot"


def test_scenarios_cover_the_probe_branches():
    codes = {w["code"] for snap in GOLDEN["snapshots"].values() for w in snap["warnings"]}
    for needle in ("CGROUP_MEMBERSHIP_UNKNOWN", "CGROUP_DEPTH_BOUNDED", "DISK_CAPACITY_UNKNOWN",
                   "ACCELERATOR_DEVICE_LIST_BOUNDED", "NVIDIA_OUTPUT_PARSE_FAILED",
                   "AMD_OUTPUT_PARSE_FAILED", "AMD_QUERY_FAILED", "APPLE_SYSCTL_PARSE_FAILED",
                   "APPLE_ACCELERATOR_QUERY_FAILED", "SLURM_ENFORCEMENT_UNKNOWN",
                   "WORKING_DIRECTORY_NOT_WRITABLE", "HOST_PHYSICAL_CPU_UNKNOWN"):
        assert needle in codes, f"scenario for {needle} lost"


def test_public_api_stays_importable_from_detect_resources():
    """CLI entry module keeps exposing the functions callers and tests use."""
    import detect_resources as dr
    for name in ("collect_snapshot", "detect_all_resources", "detect_cgroup_v2", "detect_scheduler",
                 "parse_cpu_list", "parse_nvidia_csv", "parse_amd_json", "parse_apple_profiler_json",
                 "build_parser", "main", "_run_bounded_command", "_container_context",
                 "_effective_cpu", "_visibility_summary", "NVIDIA_QUERY", "SCHEMA_VERSION"):
        assert hasattr(dr, name), name
