"""Characterization snapshots for scripts/detect_resources.py (refactor batch 3).

`detect_resources.py` (1767 lines) was split into the `resource_probes` package.
This module builds deterministic fake hosts (psutil, /proc and cgroup files,
nvidia-smi / amd-smi / system_profiler output, os / platform / shutil probes) and
dumps what `collect_snapshot` and the pure parsers return, so
test_detect_resources_characterization.py can prove the split changed no output.
The golden file (tests/golden/detect_resources.json) was produced from the
unsplit script. Nothing here touches the real machine's inventory.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import sys
import types
from collections import namedtuple
from pathlib import Path

HERE = Path(__file__).resolve().parent
GOLDEN = HERE / "golden"
SCRIPTS = HERE.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import detect_resources as dr  # noqa: E402

OBSERVED = "2026-01-02T03:04:05Z"
ROOT = "/sys/fs/cgroup"


def _jsonable(obj):
    return json.loads(json.dumps(obj, sort_keys=True, default=str))


# --------------------------------------------------------------------------
# fakes
# --------------------------------------------------------------------------
class FakePsutil:
    def __init__(self, physical=8, total=32 * 1024**3, available=20 * 1024**3,
                 swap_total=4 * 1024**3, swap_free=3 * 1024**3, affinity=None,
                 raise_all=False):
        self.physical, self.total, self.available = physical, total, available
        self.swap_total, self.swap_free = swap_total, swap_free
        self.affinity, self.raise_all = affinity, raise_all

    def cpu_count(self, logical=True):
        if self.raise_all:
            raise RuntimeError("boom")
        return self.physical

    def virtual_memory(self):
        if self.raise_all:
            raise OSError("boom")
        return types.SimpleNamespace(total=self.total, available=self.available)

    def swap_memory(self):
        if self.raise_all:
            raise OSError("boom")
        return types.SimpleNamespace(total=self.swap_total, free=self.swap_free)

    def Process(self):  # noqa: N802 - psutil API
        outer = self

        class _P:
            def cpu_affinity(self):
                if outer.raise_all:
                    raise AttributeError("no affinity")
                return outer.affinity or []
        return _P()


def make_read_text(files: dict):
    def read_text(path: Path) -> str:
        key = Path(path).as_posix()
        if key not in files:
            raise FileNotFoundError(key)
        return files[key]
    return read_text


def make_run_command(table: dict):
    """argv tuple -> result dict; anything unlisted is 'not_found'."""
    calls = []

    def run(argv, *, timeout=4.0, maximum=65536):
        calls.append([list(argv), timeout])
        res = table.get(tuple(argv), {"status": "not_found", "stdout": "", "stderr": ""})
        if isinstance(res, Exception):
            raise res
        return dict(res)
    run.calls = calls
    return run


def ok(stdout):
    return {"status": "ok", "returncode": 0, "stdout": stdout, "stderr": ""}


class FakeHost:
    """Patches the stdlib probes detect_resources calls directly."""

    def __init__(self, monkeypatch, *, system, machine, cpu_count=16, affinity=None,
                 process_cpu_count=None, sysconf=None, disk=None, statvfs=None,
                 writable=True):
        mp = monkeypatch
        mp.setattr(platform, "system", lambda: system)
        mp.setattr(platform, "machine", lambda: machine)
        mp.setattr(platform, "python_version", lambda: "3.12.1")
        mp.setattr(os, "cpu_count", lambda: cpu_count)
        if affinity is None:
            mp.delattr(os, "sched_getaffinity", raising=False)
        else:
            mp.setattr(os, "sched_getaffinity", lambda pid: set(range(affinity)), raising=False)
        if process_cpu_count is None:
            mp.delattr(os, "process_cpu_count", raising=False)
        else:
            mp.setattr(os, "process_cpu_count", lambda: process_cpu_count, raising=False)
        if sysconf is None:
            mp.delattr(os, "sysconf", raising=False)
        else:
            mp.setattr(os, "sysconf", sysconf, raising=False)
        Usage = namedtuple("Usage", "total used free")
        if disk is None:
            def boom(path):
                raise OSError("no disk")
            mp.setattr(shutil, "disk_usage", boom)
        else:
            mp.setattr(shutil, "disk_usage", lambda path: Usage(*disk))
        if statvfs is None:
            mp.delattr(os, "statvfs", raising=False)
        else:
            mp.setattr(os, "statvfs", lambda path: types.SimpleNamespace(
                f_bavail=statvfs[0], f_frsize=statvfs[1]), raising=False)
        mp.setattr(os, "access", lambda path, mode: writable)
        # collect_snapshot calls _container_context with its bound default `exists`;
        # a CI container would otherwise see its own /.dockerenv.
        mp.setitem(dr._container_context.__kwdefaults__, "exists", lambda path: False)


GIB = 1024**3


def cgroup_files(chain_limits: dict, controllers=True, membership="0::/kubepods/pod1/c1",
                 cpuset="0-3") -> dict:
    files = {}
    if controllers:
        files[f"{ROOT}/cgroup.controllers"] = "cpu memory"
    if membership is not None:
        files["/proc/self/cgroup"] = membership + "\n"
    for rel, vals in chain_limits.items():
        base = ROOT + (rel if rel else "")
        for name, text in vals.items():
            files[f"{base}/{name}"] = text
    if cpuset is not None:
        files[f"{ROOT}/kubepods/pod1/c1/cpuset.cpus.effective"] = cpuset
    return files


NVIDIA_2 = ("0, NVIDIA A100-SXM4-40GB, 40960, 40000, 535.104.05, 8.0\n"
            "1, NVIDIA A100-SXM4-40GB, 40960, 1024, 535.104.05, 8.0\n")
NVIDIA_5COL = "0, Tesla T4, 15360, 15000, 470.82\n"
AMD_SMI = json.dumps([{"gpu": 0, "asic": {"market_name": "AMD Instinct MI250X"},
                       "vram": {"size": {"value": 64, "unit": "GB"}}, "vram_total": "64 GB"}])
ROCM_SMI = json.dumps({"card0": {"Card series": "Radeon RX 7900", "VRAM Total Memory (B)": "25753026560"},
                       "card1": {"Card series": "Radeon RX 7900", "VRAM Total Memory (B)": "25753026560"}})
APPLE_PROFILER = json.dumps({"SPDisplaysDataType": [
    {"_name": "Apple M2 Pro", "sppci_model": "Apple M2 Pro", "sppci_cores": "19"}]})
SYSCTL_ARM = "12\n10\n17179869184\nApple M2 Pro\n"


def _snap(**kw):
    kw.setdefault("observed_at", OBSERVED)
    return _jsonable(dr.collect_snapshot(**kw))


def snapshot_scenarios(monkeypatch) -> dict:
    out = {}

    # 1. Linux container: psutil, cgroup chain, Slurm, two NVIDIA GPUs.
    FakeHost(monkeypatch, system="Linux", machine="x86_64", cpu_count=64, affinity=8,
             process_cpu_count=8, disk=(500 * GIB, 100 * GIB, 400 * GIB), statvfs=(300 * 1024**2, 1024))
    files = cgroup_files({
        "": {"cpu.max": "max 100000", "memory.max": "max"},
        "/kubepods": {"cpu.max": "800000 100000", "memory.max": str(16 * GIB), "memory.current": str(2 * GIB),
                      "memory.high": "max"},
        "/kubepods/pod1": {"cpu.max": "max 100000", "memory.max": str(12 * GIB), "memory.current": str(GIB)},
        "/kubepods/pod1/c1": {"cpu.max": "200000 100000", "memory.max": str(8 * GIB),
                              "memory.current": str(3 * GIB), "memory.high": str(7 * GIB)},
    })
    env = {"SLURM_JOB_ID": "42", "SLURM_CPUS_PER_TASK": "4", "SLURM_MEM_PER_CPU": "2048",
           "SLURM_NTASKS": "1", "SLURM_GPUS_ON_NODE": "2", "CUDA_VISIBLE_DEVICES": "0,1", "HOME": "/secret"}
    out["linux_container_slurm_nvidia"] = _snap(
        environ=env, psutil_module=FakePsutil(physical=32, affinity=list(range(8))),
        read_text=make_read_text(files),
        run_command=make_run_command({dr.NVIDIA_QUERY: ok(NVIDIA_2)}))

    # 2. Bare Linux without psutil: /proc fallbacks, no cgroup, no GPUs.
    FakeHost(monkeypatch, system="Linux", machine="aarch64", cpu_count=4, affinity=4,
             disk=(100 * GIB, 50 * GIB, 50 * GIB))
    cpuinfo = "\n\n".join(f"processor : {i}\nphysical id : 0\ncore id : {i % 2}" for i in range(4))
    meminfo = ("MemTotal:       16384000 kB\nMemFree: 1000 kB\nMemAvailable:    8192000 kB\n"
               "SwapTotal:       2048000 kB\nSwapFree:        2000000 kB\n")
    out["linux_bare_no_psutil"] = _snap(
        environ={}, psutil_module=None,
        read_text=make_read_text({"/proc/cpuinfo": cpuinfo, "/proc/meminfo": meminfo}),
        run_command=make_run_command({}))

    # 3. Apple silicon.
    FakeHost(monkeypatch, system="Darwin", machine="arm64", cpu_count=12, process_cpu_count=12,
             disk=(1000 * GIB, 400 * GIB, 400 * GIB), statvfs=(100 * 1024**2, 4096))
    out["darwin_arm64"] = _snap(
        environ={}, psutil_module=None, read_text=make_read_text({}),
        run_command=make_run_command({dr.APPLE_SYSCTL_QUERY: ok(SYSCTL_ARM),
                                      dr.APPLE_DISPLAY_QUERY: ok(APPLE_PROFILER)}))

    # 4. Intel Mac: sysctl bad output, system_profiler fails -> no inferred device.
    FakeHost(monkeypatch, system="Darwin", machine="x86_64", cpu_count=8,
             disk=(500 * GIB, 100 * GIB, 100 * GIB))
    out["darwin_intel_probe_failures"] = _snap(
        environ={}, psutil_module=FakePsutil(physical=4), read_text=make_read_text({}),
        run_command=make_run_command({dr.APPLE_SYSCTL_QUERY: ok("8\n4\n"),
                                      dr.APPLE_DISPLAY_QUERY: {"status": "timeout", "stdout": "", "stderr": ""}}))
    out["darwin_arm64_profiler_down_inferred"] = _snap(
        environ={}, psutil_module=None, read_text=make_read_text({}),
        run_command=make_run_command({dr.APPLE_SYSCTL_QUERY: {"status": "error", "stdout": "", "stderr": ""},
                                      dr.APPLE_DISPLAY_QUERY: {"status": "start_error", "stdout": "", "stderr": ""}}))

    # 5. Windows-like: psutil only, AMD via rocm-smi fallback.
    FakeHost(monkeypatch, system="Windows", machine="AMD64", cpu_count=24,
             disk=(2000 * GIB, 500 * GIB, 500 * GIB), writable=False)
    out["windows_rocm_fallback"] = _snap(
        environ={"HIP_VISIBLE_DEVICES": "1"}, psutil_module=FakePsutil(physical=12),
        read_text=make_read_text({}),
        run_command=make_run_command({dr.ROCM_SMI_QUERY: ok(ROCM_SMI)}))
    out["windows_amd_smi"] = _snap(
        environ={"ROCR_VISIBLE_DEVICES": "-1"}, psutil_module=FakePsutil(physical=12),
        read_text=make_read_text({}),
        run_command=make_run_command({dr.AMD_SMI_QUERY: ok(AMD_SMI)}))

    # 6. skip accelerators.
    out["skip_accelerators"] = _snap(
        skip_accelerators=True, environ={"CUDA_VISIBLE_DEVICES": "none", "NVIDIA_VISIBLE_DEVICES": "all"},
        psutil_module=FakePsutil(), read_text=make_read_text({}), run_command=make_run_command({}))

    # 7. Failure modes: nvidia error + fallback ok, garbage amd, psutil raising, no disk.
    FakeHost(monkeypatch, system="Linux", machine="x86_64", cpu_count=8, affinity=2)
    out["nvidia_fallback_amd_garbage_no_disk"] = _snap(
        environ={"CUDA_VISIBLE_DEVICES": "0"}, psutil_module=FakePsutil(raise_all=True),
        read_text=make_read_text({}),
        run_command=make_run_command({
            dr.NVIDIA_QUERY: {"status": "error", "stdout": "", "stderr": "x"},
            dr.NVIDIA_QUERY_FALLBACK: ok(NVIDIA_5COL),
            dr.AMD_SMI_QUERY: ok("{not json"),
        }))
    out["nvidia_garbage_truncated_rocm"] = _snap(
        environ={}, psutil_module=None, read_text=make_read_text({}),
        run_command=make_run_command({
            dr.NVIDIA_QUERY: ok("garbage\n"),
            dr.AMD_SMI_QUERY: {"status": "truncated", "stdout": "", "stderr": ""},
            dr.ROCM_SMI_QUERY: {"status": "timeout", "stdout": "", "stderr": ""},
        }))

    # 8. sysconf memory fallback on an unknown system; 300 GPUs hit the device bound.
    FakeHost(monkeypatch, system="Plan9", machine="x86_64", cpu_count=2,
             sysconf=lambda name: {"SC_PHYS_PAGES": 4194304, "SC_PAGE_SIZE": 4096}[name],
             disk=(10 * GIB, 5 * GIB, 5 * GIB))
    many = "".join(f"{i}, GPU{i}, 1024, 512, 1.0, 7.5\n" for i in range(300))
    out["sysconf_fallback_many_gpus"] = _snap(
        environ={}, psutil_module=None, read_text=make_read_text({}),
        run_command=make_run_command({dr.NVIDIA_QUERY: ok(many)}))

    # 9. cgroup edge cases.
    FakeHost(monkeypatch, system="Linux", machine="x86_64", cpu_count=8, affinity=8,
             disk=(10 * GIB, 5 * GIB, 5 * GIB))
    bad_membership = cgroup_files({"": {"cpu.max": "50000 100000", "memory.max": str(GIB)}},
                                  membership="garbage", cpuset=None)
    out["cgroup_membership_unknown"] = _snap(
        environ={}, psutil_module=None, read_text=make_read_text(bad_membership),
        run_command=make_run_command({}), skip_accelerators=True)
    deep = "0::/" + "/".join(f"d{i}" for i in range(70))
    out["cgroup_depth_bounded_bad_cpuset"] = _snap(
        environ={}, psutil_module=None, skip_accelerators=True,
        read_text=make_read_text(cgroup_files({}, membership=deep, cpuset="9-1")),
        run_command=make_run_command({}))
    out["cgroup_traversal_rejected"] = _snap(
        environ={}, psutil_module=None, skip_accelerators=True,
        read_text=make_read_text(cgroup_files({}, membership="0::/a/../b")),
        run_command=make_run_command({}))

    # 10. amd-smi fails to start -> rocm-smi fallback; psutil total 0 / unbounded available -> /proc/meminfo.
    out["amd_start_error_rocm_ok"] = _snap(
        environ={}, psutil_module=None, read_text=make_read_text({}),
        run_command=make_run_command({dr.AMD_SMI_QUERY: {"status": "start_error", "stdout": "", "stderr": ""},
                                      dr.ROCM_SMI_QUERY: ok(ROCM_SMI)}))
    out["amd_smi_error_rocm_not_found"] = _snap(
        environ={}, psutil_module=None, read_text=make_read_text({}),
        run_command=make_run_command({dr.AMD_SMI_QUERY: {"status": "error", "stdout": "", "stderr": ""}}))
    out["amd_smi_empty_ok_then_no_fallback"] = _snap(
        environ={}, psutil_module=None, read_text=make_read_text({}),
        run_command=make_run_command({dr.AMD_SMI_QUERY: ok("[]"), dr.ROCM_SMI_QUERY: ok(ROCM_SMI)}))
    out["psutil_zero_total_meminfo_fills"] = _snap(
        environ={}, psutil_module=FakePsutil(total=0, available=2**64, swap_total=2**64, swap_free=0),
        read_text=make_read_text({"/proc/meminfo": meminfo}), run_command=make_run_command({}),
        skip_accelerators=True)
    return out


def snapshot_environment_errors(monkeypatch) -> dict:
    """Host probes returning unusable values."""
    out = {}
    FakeHost(monkeypatch, system="", machine="", cpu_count=None,
             disk=(100, 200, 300))
    out["empty_platform_cpu_none_bad_disk"] = _snap(
        environ={}, psutil_module=None, read_text=make_read_text({}),
        run_command=make_run_command({}), skip_accelerators=True)
    return out


# --------------------------------------------------------------------------
# pure helpers
# --------------------------------------------------------------------------
def _try(fn, *a, **kw):
    try:
        return _jsonable(fn(*a, **kw))
    except Exception as exc:  # noqa: BLE001 - type and message are the snapshot
        return ["raised", type(exc).__name__, str(exc)]


SLURM_ENVS = {
    "none": {},
    "unrelated": {"PATH": "x"},
    "per_task_mem_per_cpu": {"SLURM_JOB_ID": "1", "SLURM_CPUS_PER_TASK": "4", "SLURM_MEM_PER_CPU": "2G"},
    "node_mem_single_task": {"SLURM_JOBID": "2", "SLURM_CPUS_ON_NODE": "16", "SLURM_NTASKS_PER_NODE": "1",
                             "SLURM_MEM_PER_NODE": "65536"},
    "node_mem_shared": {"SLURM_JOB_ID": "3", "SLURM_CPUS_ON_NODE": "16", "SLURM_TASKS_PER_NODE": "4(x2)",
                        "SLURM_MEM_PER_NODE": "64G", "SLURM_JOB_CPUS_PER_NODE": "16(x2)"},
    "gpus": {"SLURM_JOB_ID": "4", "SLURM_GPUS_PER_TASK": "gpu:a100:2", "SLURM_GPUS_ON_NODE": "4",
             "SLURM_GPUS": "8", "SLURM_NTASKS": "2"},
    "garbage": {"SLURM_JOB_ID": "5", "SLURM_CPUS_PER_TASK": "lots", "SLURM_MEM_PER_CPU": "0",
                "SLURM_NTASKS": "9" * 12},
    "nonstring": {"SLURM_JOB_ID": 6},
    "tasks_per_node_2_mem_node": {"SLURM_JOB_ID": "7", "SLURM_NTASKS_PER_NODE": "2", "SLURM_MEM_PER_NODE": "8G"},
    "tasks_per_node_1_mem_node": {"SLURM_JOB_ID": "8", "SLURM_NTASKS_PER_NODE": "1", "SLURM_MEM_PER_NODE": "8G",
                                  "SLURM_CPUS_ON_NODE": "8"},
    "mem_per_cpu_without_cpu_count": {"SLURM_JOB_ID": "9", "SLURM_MEM_PER_CPU": "1G", "SLURM_MEM_PER_NODE": "4G"},
}
CPU_LISTS = ["0-3", "0-3,8-11", "5", "0,1,2,3", "3-1", "a", "", "  ", "0-1048576", "0-3,2-9", "1-2,3-4",
             "9" * 5000, 7]
CPU_MAX = ["max 100000", "200000 100000", "100 0", "0 100", "x y", "50000", "150000 100000"]
MEMINFO = ["MemTotal: 100 kB\nMemAvailable: 50 kB\nSwapTotal: 10 kB\nSwapFree: 5 kB\nBogus: 1 kB", "", "MemTotal: x kB"]
NVIDIA_CSVS = [NVIDIA_2, NVIDIA_5COL, "1, a, b\n", "", '0, "A, B", 10, 5, 1.0\n', "99999, G, 1, 1, 1\n",
               "0, GPU, nan, -4, 1.0\n"]
AMD_JSONS = [AMD_SMI, ROCM_SMI, "[]", "{}", "null", json.dumps({"gpu": 3, "product_name": "Solo"}),
             json.dumps({"gpus": [{"gpu": 1, "market_name": "X", "vram_total": "16 GiB"}]}),
             json.dumps([{"asic": {"market_name": "Y"}, "vram": {"total": "8192 MB"}}]), "{"]
APPLE_JSONS = [APPLE_PROFILER, json.dumps({"SPDisplaysDataType": [{"_name": "AMD Radeon Pro 560X"}, 7]}),
               json.dumps({"SPDisplaysDataType": "x"}), "[]", "{"]
VISIBILITY = [{}, {"CUDA_VISIBLE_DEVICES": "0,1,,1"}, {"CUDA_VISIBLE_DEVICES": "-1"},
              {"CUDA_VISIBLE_DEVICES": "ALL"}, {"HIP_VISIBLE_DEVICES": ""},
              {"ROCR_VISIBLE_DEVICES": "x" * 5000}, {"NVIDIA_VISIBLE_DEVICES": "void"}]


def snapshot_pure() -> dict:
    out = {}
    out["parse_cpu_list"] = {repr(v)[:30]: _try(dr.parse_cpu_list, v) for v in CPU_LISTS}
    out["parse_cpu_max"] = {v: _try(dr._parse_cpu_max, v) for v in CPU_MAX}
    out["bounded_nonnegative"] = {repr(v): _try(dr._bounded_nonnegative, v)
                                  for v in (None, True, "12", " 7 ", "-1", "x", 2**63, 2**63 + 1, 3.5)}
    out["safe_text"] = {repr(v)[:20]: _try(dr._safe_text, v, 10)
                        for v in ("  a   b\tc ", "x" * 50, "\x00\x01ok", "", None, 5, 1.5, ["a"])}
    out["slurm_count"] = {repr(v): _try(dr._parse_slurm_count, v)
                          for v in (None, "", "4", "gpu:a100:2", "a:b:3", "9999999", "x", "1" * 200)}
    out["slurm_memory"] = {repr(v): _try(dr._parse_slurm_memory, v)
                           for v in (None, "100", "2G", "2 g", "0", "3T", "x", "9" * 30 + "T")}
    out["slurm_repeated"] = {repr(v): _try(dr._parse_first_repeated_count, v)
                             for v in (None, "4(x2)", " 8", "x", "2000000")}
    out["detect_scheduler"] = {k: _try(dr.detect_scheduler, v) for k, v in SLURM_ENVS.items()}
    out["detect_scheduler_records"] = {}
    for key, env in SLURM_ENVS.items():
        sched_w, sched_p = [], []
        dr.detect_scheduler(env, warnings=sched_w, provenance=sched_p)
        out["detect_scheduler_records"][key] = {"warnings": sched_w, "provenance": sched_p}
    out["meminfo"] = {str(i): _try(dr._parse_linux_meminfo, v) for i, v in enumerate(MEMINFO)}
    out["nvidia_csv"] = {str(i): _try(dr.parse_nvidia_csv, v) for i, v in enumerate(NVIDIA_CSVS)}
    out["amd_json"] = {str(i): _try(dr.parse_amd_json, v) for i, v in enumerate(AMD_JSONS)}
    out["apple_json"] = {f"{i}|{m}": _try(dr.parse_apple_profiler_json, v, machine=m)
                         for i, v in enumerate(APPLE_JSONS) for m in ("arm64", "x86_64")}
    out["visibility"] = {str(i): _try(dr._visibility_summary, v) for i, v in enumerate(VISIBILITY)}
    devices = (dr.parse_nvidia_csv(NVIDIA_2) + dr.parse_amd_json(ROCM_SMI)
               + dr.parse_apple_profiler_json(APPLE_PROFILER, machine="arm64"))
    out["upper_bounds"] = {
        str(i): _try(dr._accelerator_upper_bounds, devices, dr._visibility_summary(v),
                     {"allocation": {"gpus_per_process": g}})
        for i, (v, g) in enumerate(((VISIBILITY[0], None), (VISIBILITY[1], 1), (VISIBILITY[2], 5),
                                    ({"HIP_VISIBLE_DEVICES": "0"}, None)))}
    host = {"logical": 16, "physical": 8}
    out["effective_cpu"] = {
        "all": _try(dr._effective_cpu, host, {"affinity_logical": 8, "python_available_logical": 6},
                    {"cpuset_logical": 4, "cpu_quota_cores": 2.5}, {"allocation": {"cpu_per_process": 3}}),
        "none": _try(dr._effective_cpu, {}, {}, {}, {}),
        "host_only": _try(dr._effective_cpu, host, {}, {}, {}),
        "ties": _try(dr._effective_cpu, host, {"affinity_logical": 4}, {"cpuset_logical": 4}, {}),
        "bool_ignored": _try(dr._effective_cpu, {"logical": True}, {}, {}, {}),
    }
    out["container_context"] = {
        name: _try(dr._container_context, cgroup=cg, exists=ex)
        for name, (cg, ex) in {
            "docker": ({}, lambda p: p.as_posix() == "/.dockerenv"),
            "podman": ({}, lambda p: p.as_posix() == "/run/.containerenv"),
            "cgroup_only": ({"detected": True, "memory_max_bytes": 1}, lambda p: False),
            "cgroup_unlimited": ({"detected": True}, lambda p: False),
            "exists_raises": ({}, lambda p: (_ for _ in ()).throw(OSError("x"))),
        }.items()}
    return out


def snapshot_cgroup_direct() -> dict:
    out = {}
    base = {"controllers": cgroup_files({"": {"cpu.max": "max 100000"}}, membership="0::/")}
    out["root_membership"] = _try(dr.detect_cgroup_v2, read_text=make_read_text(base["controllers"]))
    files = cgroup_files({"/kubepods/pod1/c1": {"memory.max": "1048576", "memory.current": "5242880"}})
    out["usage_above_max"] = _try(dr.detect_cgroup_v2, read_text=make_read_text(files))
    out["unavailable"] = _try(dr.detect_cgroup_v2, read_text=make_read_text({}))
    w, p = [], []
    dr.detect_cgroup_v2(read_text=make_read_text(cgroup_files({}, membership="x")), warnings=w, provenance=p)
    out["records"] = {"warnings": w, "provenance": p}
    bad_cpuset = cgroup_files({}, cpuset="9-1")
    w2, p2 = [], []
    out["bad_cpuset"] = _try(dr.detect_cgroup_v2, read_text=make_read_text(bad_cpuset), warnings=w2, provenance=p2)
    out["bad_cpuset_records"] = {"warnings": w2, "provenance": p2}
    out["relative_path"] = {v: _try(dr._cgroup_relative_path, v) for v in
                            ("0::/", "0::/a/b", "1:name=x:/a\n0::/c", "0::/a/./b", "garbage", "")}
    return out


# --------------------------------------------------------------------------
# command runner (real subprocesses, python itself as the fixed argv)
# --------------------------------------------------------------------------
def snapshot_run_command() -> dict:
    py = sys.executable
    cases = {
        "ok": ((py, "-c", "import sys; print('hi'); sys.stderr.write('e')"), {}),
        "nonzero": ((py, "-c", "import sys; sys.exit(3)"), {}),
        "timeout": ((py, "-c", "import time; time.sleep(30)"), {"timeout": 0.5}),
        "truncated": ((py, "-c", "print('x' * 100000)"), {"maximum": 100}),
        "not_found": (("definitely-not-a-real-binary-xyz",), {}),
    }
    out = {}
    for name, (argv, kw) in cases.items():
        res = dr._run_bounded_command(argv, **kw)
        res = {k: (v.replace("\r\n", "\n") if isinstance(v, str) else v) for k, v in res.items()}
        if name == "truncated":
            res["stdout"] = f"len={len(res['stdout'])}"
        out[name] = _jsonable(res)
    for name, bad in {"list": ["a"], "empty": (), "non_str": ("a", 1), "empty_item": ("a", "")}.items():
        out["bad_argv_" + name] = _try(dr._run_bounded_command, bad)
    return out


def shape(value):
    """Key structure of a JSON value: dict keys recursively; lists and leaves collapsed."""
    if isinstance(value, dict):
        return {k: shape(v) for k, v in sorted(value.items())}
    return "list" if isinstance(value, list) else "v"


# --------------------------------------------------------------------------
# CLI (real subprocess; the machine's own values are reduced to a key shape)
# --------------------------------------------------------------------------
def _cli(args, cwd, env_extra=None):
    import subprocess
    env = dict(os.environ, COLUMNS="100", PYTHONIOENCODING="utf-8")
    env.update(env_extra or {})
    proc = subprocess.run([sys.executable, str(SCRIPTS / "detect_resources.py"), *args],
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          cwd=str(cwd), env=env, timeout=120)
    return proc


def snapshot_cli(tmp: Path) -> dict:
    out = {}
    helped = _cli(["--help"], tmp)
    # argparse prints "options:" or "optional arguments:" depending on the Python version,
    # so pin the usage line, the description and the flag set instead of the whole text.
    import re
    out["help"] = {"rc": helped.returncode, "usage": helped.stdout.splitlines()[0],
                   "description": "Report host inventory and effective process limits as deterministic JSON"
                   in helped.stdout,
                   "flags": sorted(set(re.findall(r"--[a-z-]+", helped.stdout)))}
    proc = _cli(["--skip-accelerators"], tmp)
    out["stdout_run"] = {"rc": proc.returncode, "shape": shape(json.loads(proc.stdout)),
                         "schema_version": json.loads(proc.stdout)["schema_version"]}
    for name, args in {"force_without_output": ["--force"], "path_output": ["--output", "sub/x.json"],
                       "wrong_suffix": ["--output", "x.txt"], "unknown_flag": ["--nope"]}.items():
        r = _cli(args, tmp)
        out[name] = {"rc": r.returncode, "stdout": r.stdout, "stderr": r.stderr.replace(str(tmp), "<TMP>")}
    first = _cli(["--skip-accelerators", "--output", "snap.json"], tmp)
    second = _cli(["--skip-accelerators", "--output", "snap.json"], tmp)
    forced = _cli(["--skip-accelerators", "--output", "snap.json", "--force"], tmp)
    written = json.loads((tmp / "snap.json").read_text(encoding="utf-8"))
    out["output_file"] = {"first": [first.returncode, first.stdout],
                          "second_rc": second.returncode, "second_stderr": second.stderr.replace(str(tmp), "<TMP>"),
                          "forced_rc": forced.returncode, "shape": shape(written)}
    return out


def build_all(monkeypatch, tmp: Path) -> dict:
    return {
        "snapshots": snapshot_scenarios(monkeypatch),
        "environment_errors": snapshot_environment_errors(monkeypatch),
        "pure": snapshot_pure(),
        "cgroup_direct": snapshot_cgroup_direct(),
        "run_command": snapshot_run_command(),
        "cli": snapshot_cli(tmp),
    }
