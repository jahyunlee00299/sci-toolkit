"""Host and process CPU counts, and the effective CPU capacity across all limits."""

from __future__ import annotations

import math
import os
import re
from pathlib import Path
from typing import Any, Callable, Mapping

from .core import MAX_CPU_ID, _bounded_nonnegative, _provenance, _safe_text, _try_read, _warning

APPLE_SYSCTL_QUERY = (
    "sysctl",
    "-n",
    "hw.logicalcpu",
    "hw.physicalcpu",
    "hw.memsize",
    "machdep.cpu.brand_string",
)


def parse_cpu_list(value: str) -> int | None:
    """Count CPUs in a Linux range list without expanding it."""
    if not isinstance(value, str) or not value.strip() or len(value) > 4096:
        return None
    intervals: list[tuple[int, int]] = []
    for token in value.strip().split(","):
        token = token.strip()
        match = re.fullmatch(r"(\d+)(?:-(\d+))?", token)
        if not match:
            return None
        start = int(match.group(1))
        end = int(match.group(2) or start)
        if start > end or end > MAX_CPU_ID:
            return None
        intervals.append((start, end))
    intervals.sort()
    total = 0
    current_start, current_end = intervals[0]
    for start, end in intervals[1:]:
        if start <= current_end + 1:
            current_end = max(current_end, end)
        else:
            total += current_end - current_start + 1
            current_start, current_end = start, end
    total += current_end - current_start + 1
    return total if total <= MAX_CPU_ID + 1 else None


def _linux_physical_cores(
    read_text: Callable[[Path], str],
) -> int | None:
    payload = _try_read(read_text, Path("/proc/cpuinfo"))
    if not payload:
        return None
    pairs: set[tuple[str, str]] = set()
    for block in payload.split("\n\n"):
        fields: dict[str, str] = {}
        for line in block.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                fields[key.strip().lower()] = value.strip()
        if "physical id" in fields and "core id" in fields:
            pairs.add((fields["physical id"], fields["core id"]))
    count = len(pairs)
    return count if 0 < count <= MAX_CPU_ID + 1 else None


def _mac_sysctl_values(
    run_command: Callable[..., dict[str, Any]],
    warnings: list[dict[str, str]],
    provenance: list[dict[str, str]],
) -> dict[str, Any]:
    result = run_command(APPLE_SYSCTL_QUERY, timeout=2.0)
    if result["status"] != "ok":
        _warning(
            warnings,
            "APPLE_SYSCTL_UNAVAILABLE",
            "platform",
            "Apple sysctl inventory was unavailable; other sources were retained.",
            severity="info",
        )
        _provenance(provenance, "platform.apple_sysctl", "sysctl", result["status"])
        return {}
    lines = result["stdout"].splitlines()
    if len(lines) < 4:
        _warning(
            warnings,
            "APPLE_SYSCTL_PARSE_FAILED",
            "platform",
            "Apple sysctl returned an unexpected bounded response.",
        )
        _provenance(provenance, "platform.apple_sysctl", "sysctl", "parse_error")
        return {}
    _provenance(provenance, "platform.apple_sysctl", "sysctl", "ok")
    return {
        "logical": _bounded_nonnegative(lines[0]),
        "physical": _bounded_nonnegative(lines[1]),
        "memory": _bounded_nonnegative(lines[2]),
        "brand": _safe_text(lines[3]),
    }


def _detect_cpu_inventory(
    *,
    system: str,
    psutil_module: Any | None,
    mac_sysctl: Mapping[str, Any],
    read_text: Callable[[Path], str],
    warnings: list[dict[str, str]],
    provenance: list[dict[str, str]],
) -> dict[str, int | None]:
    host_logical = os.cpu_count()
    if (
        not isinstance(host_logical, int)
        or isinstance(host_logical, bool)
        or not 1 <= host_logical <= MAX_CPU_ID + 1
    ):
        host_logical = None
        _warning(
            warnings,
            "HOST_LOGICAL_CPU_UNKNOWN",
            "cpu",
            "Host logical CPU count could not be determined.",
        )
        _provenance(provenance, "cpu.host.logical", "os.cpu_count", "unavailable")
    else:
        _provenance(provenance, "cpu.host.logical", "os.cpu_count", "ok")

    host_physical: int | None = None
    if psutil_module is not None:
        try:
            candidate = psutil_module.cpu_count(logical=False)
            if (
                isinstance(candidate, int)
                and not isinstance(candidate, bool)
                and 0 < candidate <= MAX_CPU_ID + 1
            ):
                host_physical = candidate
                _provenance(
                    provenance, "cpu.host.physical", "psutil.cpu_count", "ok"
                )
        except (AttributeError, OSError, RuntimeError, ValueError):
            pass
    if host_physical is None and system == "Darwin":
        candidate = mac_sysctl.get("physical")
        if isinstance(candidate, int) and 0 < candidate <= MAX_CPU_ID + 1:
            host_physical = candidate
            _provenance(provenance, "cpu.host.physical", "sysctl", "ok")
    if host_physical is None and system == "Linux":
        host_physical = _linux_physical_cores(read_text)
        if host_physical is not None:
            _provenance(provenance, "cpu.host.physical", "proc_cpuinfo", "ok")
    if host_physical is None:
        _warning(
            warnings,
            "HOST_PHYSICAL_CPU_UNKNOWN",
            "cpu",
            "Physical core count is unknown and was not inferred from logical CPUs.",
            severity="info",
        )
        _provenance(provenance, "cpu.host.physical", "platform_fallbacks", "unavailable")
    return {"logical": host_logical, "physical": host_physical}


def _detect_process_cpu_count(
    *,
    psutil_module: Any | None,
    warnings: list[dict[str, str]],
    provenance: list[dict[str, str]],
) -> dict[str, int | None]:
    affinity_count: int | None = None
    affinity_source: str | None = None
    get_affinity = getattr(os, "sched_getaffinity", None)
    if callable(get_affinity):
        try:
            affinity = get_affinity(0)
            if affinity and len(affinity) <= MAX_CPU_ID + 1:
                affinity_count = len(affinity)
                affinity_source = "os.sched_getaffinity"
        except (OSError, TypeError, ValueError):
            pass
    if affinity_count is None and psutil_module is not None:
        try:
            affinity = psutil_module.Process().cpu_affinity()
            if affinity and len(affinity) <= MAX_CPU_ID + 1:
                affinity_count = len(affinity)
                affinity_source = "psutil.Process.cpu_affinity"
        except (AttributeError, OSError, RuntimeError, ValueError):
            pass
    if affinity_count is not None:
        _provenance(provenance, "cpu.process.affinity_logical", affinity_source or "", "ok")
    else:
        _provenance(
            provenance, "cpu.process.affinity_logical", "affinity_apis", "unavailable"
        )

    process_count: int | None = None
    process_cpu_count = getattr(os, "process_cpu_count", None)
    if callable(process_cpu_count):
        try:
            candidate = process_cpu_count()
            if (
                isinstance(candidate, int)
                and not isinstance(candidate, bool)
                and 0 < candidate <= MAX_CPU_ID + 1
            ):
                process_count = candidate
                _provenance(
                    provenance,
                    "cpu.process.python_available_logical",
                    "os.process_cpu_count",
                    "ok",
                )
        except (OSError, ValueError):
            pass
    if affinity_count is None and process_count is None:
        _warning(
            warnings,
            "PROCESS_CPU_SCOPE_UNKNOWN",
            "cpu",
            "No process-aware CPU count API was available.",
            severity="info",
        )
    return {
        "affinity_logical": affinity_count,
        "python_available_logical": process_count,
    }


def _effective_cpu(
    host: Mapping[str, int | None],
    process: Mapping[str, int | None],
    cgroup: Mapping[str, Any],
    scheduler: Mapping[str, Any],
) -> dict[str, Any]:
    candidates: list[tuple[str, float]] = []
    for source, value in (
        ("host_logical", host.get("logical")),
        ("process_affinity", process.get("affinity_logical")),
        ("python_process_count", process.get("python_available_logical")),
        ("cgroup_cpuset", cgroup.get("cpuset_logical")),
        ("cgroup_quota", cgroup.get("cpu_quota_cores")),
        (
            "scheduler_per_process",
            scheduler.get("allocation", {}).get("cpu_per_process"),
        ),
    ):
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
            candidates.append((source, float(value)))
    if not candidates:
        return {
            "capacity_cores": None,
            "limiting_sources": [],
            "worker_ceiling": 1,
        }
    capacity = min(value for _, value in candidates)
    limiting = sorted(
        source for source, value in candidates if abs(value - capacity) < 1e-9
    )
    return {
        "capacity_cores": round(capacity, 6),
        "limiting_sources": limiting,
        "worker_ceiling": max(1, min(1024, math.floor(capacity))),
    }
