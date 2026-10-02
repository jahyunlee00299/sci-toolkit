"""cgroup v2 limits: CPU quota, cpuset and memory, read without exposing paths."""

from __future__ import annotations

import math
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from .core import (
    MAX_CGROUP_LEVELS,
    _bounded_nonnegative,
    _provenance,
    _read_bounded_text,
    _try_read,
    _warning,
)
from .cpu import parse_cpu_list


def _parse_cpu_max(value: str) -> float | None:
    fields = value.strip().split()
    if len(fields) != 2 or fields[0] == "max":
        return None
    quota = _bounded_nonnegative(fields[0])
    period = _bounded_nonnegative(fields[1])
    if quota is None or period in (None, 0) or quota == 0:
        return None
    capacity = quota / period
    if not math.isfinite(capacity) or capacity <= 0:
        return None
    return round(capacity, 6)


def _cgroup_relative_path(payload: str) -> tuple[str, ...] | None:
    for line in payload.splitlines():
        fields = line.split(":", 2)
        if len(fields) == 3 and fields[0] == "0" and fields[1] == "":
            raw = PurePosixPath(fields[2])
            parts = tuple(part for part in raw.parts if part not in {"/", ""})
            if any(part in {".", ".."} for part in parts):
                return None
            return parts
    return None


def _cgroup_not_detected(scope: str = "unknown") -> dict[str, Any]:
    """The cgroup result when there is nothing to read (or it is not applicable)."""
    return {
        "detected": False,
        "cpu_quota_cores": None,
        "cpuset_logical": None,
        "memory_available_bytes": None,
        "memory_current_bytes": None,
        "memory_high_bytes": None,
        "memory_max_bytes": None,
        "scope": scope,
    }


def _cgroup_chain(
    root: Path,
    current: Path,
    warning_records: list[dict[str, str]],
) -> list[Path]:
    """`current` and its ancestors up to `root` (bounded depth)."""
    chain: list[Path] = []
    cursor = current
    for _ in range(MAX_CGROUP_LEVELS):
        chain.append(cursor)
        if cursor == root:
            break
        parent = cursor.parent
        if parent == cursor or (parent != root and root not in parent.parents):
            break
        cursor = parent
    else:
        _warning(
            warning_records,
            "CGROUP_DEPTH_BOUNDED",
            "cgroup",
            "cgroup ancestor traversal reached its safety bound.",
        )
    return chain


def _limit_or_none(text: str | None) -> int | None:
    """A cgroup limit file: missing or the literal `max` means unlimited."""
    if text is None or text.strip() == "max":
        return None
    return _bounded_nonnegative(text)


def _chain_limits(
    read_text: Callable[[Path], str],
    chain: list[Path],
) -> dict[str, Any]:
    """The tightest CPU quota / memory limits over the cgroup chain."""
    quota_candidates: list[float] = []
    memory_max_candidates: list[int] = []
    memory_high_candidates: list[int] = []
    memory_available_candidates: list[int] = []
    current_memory: int | None = None

    for index, directory in enumerate(chain):
        cpu_max_text = _try_read(read_text, directory / "cpu.max")
        if cpu_max_text is not None:
            quota = _parse_cpu_max(cpu_max_text)
            if quota is not None:
                quota_candidates.append(quota)

        memory_current = _bounded_nonnegative(
            _try_read(read_text, directory / "memory.current")
        )
        if index == 0:
            current_memory = memory_current
        memory_max = _limit_or_none(_try_read(read_text, directory / "memory.max"))
        memory_high = _limit_or_none(_try_read(read_text, directory / "memory.high"))
        if memory_max is not None:
            memory_max_candidates.append(memory_max)
            if memory_current is not None:
                memory_available_candidates.append(max(0, memory_max - memory_current))
        if memory_high is not None:
            memory_high_candidates.append(memory_high)

    return {
        "cpu_quota_cores": min(quota_candidates) if quota_candidates else None,
        "memory_available_bytes": (
            min(memory_available_candidates) if memory_available_candidates else None
        ),
        "memory_current_bytes": current_memory,
        "memory_high_bytes": (
            min(memory_high_candidates) if memory_high_candidates else None
        ),
        "memory_max_bytes": (
            min(memory_max_candidates) if memory_max_candidates else None
        ),
    }


def detect_cgroup_v2(
    *,
    read_text: Callable[[Path], str] = _read_bounded_text,
    root: Path = Path("/sys/fs/cgroup"),
    proc_self_cgroup: Path = Path("/proc/self/cgroup"),
    warnings: list[dict[str, str]] | None = None,
    provenance: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Read current and ancestor cgroup v2 limits without exposing paths."""
    warning_records = warnings if warnings is not None else []
    provenance_records = provenance if provenance is not None else []
    if _try_read(read_text, root / "cgroup.controllers") is None:
        _provenance(
            provenance_records, "cgroup_v2", "cgroup.controllers", "unavailable"
        )
        return _cgroup_not_detected()

    membership = _try_read(read_text, proc_self_cgroup)
    parts = _cgroup_relative_path(membership or "")
    if parts is None:
        _warning(
            warning_records,
            "CGROUP_MEMBERSHIP_UNKNOWN",
            "cgroup",
            "cgroup v2 was detected but current membership could not be parsed.",
        )
        parts = ()
    current = root.joinpath(*parts)
    chain = _cgroup_chain(root, current, warning_records)
    limits = _chain_limits(read_text, chain)

    cpuset_text = _try_read(read_text, current / "cpuset.cpus.effective")
    cpuset_count = parse_cpu_list(cpuset_text) if cpuset_text else None
    if cpuset_text and cpuset_count is None:
        _warning(
            warning_records,
            "CGROUP_CPUSET_PARSE_FAILED",
            "cgroup",
            "cpuset.cpus.effective had an unexpected bounded value.",
        )

    _provenance(provenance_records, "cgroup_v2", "procfs_and_cgroupfs", "ok")
    return {
        "detected": True,
        "cpu_quota_cores": limits["cpu_quota_cores"],
        "cpuset_logical": cpuset_count,
        "memory_available_bytes": limits["memory_available_bytes"],
        "memory_current_bytes": limits["memory_current_bytes"],
        "memory_high_bytes": limits["memory_high_bytes"],
        "memory_max_bytes": limits["memory_max_bytes"],
        "scope": "non_root" if parts else "root",
    }
