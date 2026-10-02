"""Host and swap memory, and the effective memory limit across cgroup and scheduler."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Callable, Mapping

from .core import MAX_BYTES, _bounded_nonnegative, _provenance, _try_read, _warning


def _parse_linux_meminfo(payload: str) -> dict[str, int | None]:
    values: dict[str, int] = {}
    for line in payload.splitlines():
        match = re.fullmatch(r"([A-Za-z_()]+):\s+(\d+)\s+kB", line.strip())
        if match:
            values[match.group(1)] = int(match.group(2)) * 1024
    return {
        "available": values.get("MemAvailable"),
        "swap_free": values.get("SwapFree"),
        "swap_total": values.get("SwapTotal"),
        "total": values.get("MemTotal"),
    }


def _psutil_memory(
    psutil_module: Any | None,
    provenance: list[dict[str, str]],
) -> tuple[int | None, int | None, int | None, int | None]:
    """(host total, host available, swap total, swap free) from psutil, None where unreadable."""
    host_total: int | None = None
    host_available: int | None = None
    swap_total: int | None = None
    swap_free: int | None = None
    if psutil_module is not None:
        try:
            memory = psutil_module.virtual_memory()
            host_total = _bounded_nonnegative(memory.total)
            host_available = _bounded_nonnegative(memory.available)
            _provenance(provenance, "memory.host", "psutil.virtual_memory", "ok")
        except (AttributeError, OSError, RuntimeError, ValueError):
            pass
        try:
            swap = psutil_module.swap_memory()
            swap_total = _bounded_nonnegative(swap.total)
            swap_free = _bounded_nonnegative(swap.free)
            _provenance(provenance, "memory.swap", "psutil.swap_memory", "ok")
        except (AttributeError, OSError, RuntimeError, ValueError):
            pass
    return host_total, host_available, swap_total, swap_free


def _platform_memory_fallbacks(
    *,
    system: str,
    mac_sysctl: Mapping[str, Any],
    read_text: Callable[[Path], str],
    provenance: list[dict[str, str]],
    host_total: int | None,
    host_available: int | None,
    swap_total: int | None,
    swap_free: int | None,
) -> tuple[int | None, int | None, int | None, int | None]:
    """Fill what psutil did not give: /proc/meminfo (Linux), sysctl (macOS), os.sysconf."""
    if system == "Linux" and (host_total is None or host_available is None):
        payload = _try_read(read_text, Path("/proc/meminfo"))
        if payload:
            parsed = _parse_linux_meminfo(payload)
            host_total = host_total or parsed["total"]
            host_available = (
                host_available
                if host_available is not None
                else parsed["available"]
            )
            swap_total = swap_total if swap_total is not None else parsed["swap_total"]
            swap_free = swap_free if swap_free is not None else parsed["swap_free"]
            _provenance(provenance, "memory.host", "proc_meminfo", "ok")
    if system == "Darwin" and host_total is None:
        candidate = mac_sysctl.get("memory")
        if isinstance(candidate, int) and candidate > 0:
            host_total = candidate
            _provenance(provenance, "memory.host.total", "sysctl", "ok")
    if host_total is None:
        try:
            pages = os.sysconf("SC_PHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
            candidate = pages * page_size
            if 0 < candidate <= MAX_BYTES:
                host_total = candidate
                _provenance(provenance, "memory.host.total", "os.sysconf", "ok")
        except (AttributeError, OSError, TypeError, ValueError):
            pass
    return host_total, host_available, swap_total, swap_free


def _effective_memory(
    host_total: int | None,
    host_available: int | None,
    cgroup: Mapping[str, Any],
    scheduler: Mapping[str, Any],
) -> dict[str, Any]:
    """Tightest hard limit and available memory over host, cgroup and scheduler."""
    limit_candidates: list[tuple[str, int]] = []
    available_candidates: list[tuple[str, int]] = []
    for source, value in (
        ("host_total", host_total),
        ("cgroup_memory_max", cgroup.get("memory_max_bytes")),
        (
            "scheduler_memory",
            scheduler.get("allocation", {}).get("memory_effective_bytes"),
        ),
    ):
        if isinstance(value, int) and value >= 0:
            limit_candidates.append((source, value))
    for source, value in (
        ("host_available", host_available),
        ("cgroup_memory_remaining", cgroup.get("memory_available_bytes")),
        (
            "scheduler_memory_upper_bound",
            scheduler.get("allocation", {}).get("memory_effective_bytes"),
        ),
    ):
        if isinstance(value, int) and value >= 0:
            available_candidates.append((source, value))

    effective_limit = (
        min(value for _, value in limit_candidates) if limit_candidates else None
    )
    effective_available = (
        min(value for _, value in available_candidates)
        if available_candidates
        else None
    )
    if (
        effective_limit is not None
        and effective_available is not None
        and effective_available > effective_limit
    ):
        effective_available = effective_limit
    limiting_sources = (
        sorted(
            source
            for source, value in limit_candidates
            if value == effective_limit
        )
        if effective_limit is not None
        else []
    )
    available_sources = (
        sorted(
            source
            for source, value in available_candidates
            if value == effective_available
        )
        if effective_available is not None
        else []
    )
    return {
        "available": effective_available,
        "available_sources": available_sources,
        "limit": effective_limit,
        "limit_sources": limiting_sources,
    }


def _detect_memory(
    *,
    system: str,
    machine: str,
    psutil_module: Any | None,
    mac_sysctl: Mapping[str, Any],
    cgroup: Mapping[str, Any],
    scheduler: Mapping[str, Any],
    read_text: Callable[[Path], str],
    warnings: list[dict[str, str]],
    provenance: list[dict[str, str]],
) -> dict[str, Any]:
    host_total, host_available, swap_total, swap_free = _psutil_memory(
        psutil_module, provenance
    )
    host_total, host_available, swap_total, swap_free = _platform_memory_fallbacks(
        system=system,
        mac_sysctl=mac_sysctl,
        read_text=read_text,
        provenance=provenance,
        host_total=host_total,
        host_available=host_available,
        swap_total=swap_total,
        swap_free=swap_free,
    )

    if host_total is None:
        _warning(
            warnings,
            "HOST_MEMORY_TOTAL_UNKNOWN",
            "memory",
            "Host memory total could not be determined.",
        )
    if host_available is None:
        _warning(
            warnings,
            "HOST_MEMORY_AVAILABLE_UNKNOWN",
            "memory",
            "Host available memory could not be determined without an allocation probe.",
            severity="info",
        )

    effective = _effective_memory(host_total, host_available, cgroup, scheduler)
    unified = system == "Darwin" and machine.lower() in {"arm64", "aarch64"}
    return {
        "cgroup_v2": {
            "available_bytes": cgroup.get("memory_available_bytes"),
            "current_bytes": cgroup.get("memory_current_bytes"),
            "high_bytes": cgroup.get("memory_high_bytes"),
            "max_bytes": cgroup.get("memory_max_bytes"),
        },
        "effective": {
            "available_bytes": effective["available"],
            "available_limiting_sources": effective["available_sources"],
            "hard_limit_bytes": effective["limit"],
            "hard_limit_sources": effective["limit_sources"],
            "pressure_threshold_bytes": cgroup.get("memory_high_bytes"),
        },
        "host": {
            "available_bytes": host_available,
            "total_bytes": host_total,
        },
        "model": "unified_cpu_gpu" if unified else "system_ram",
        "swap": {"free_bytes": swap_free, "total_bytes": swap_total},
    }
