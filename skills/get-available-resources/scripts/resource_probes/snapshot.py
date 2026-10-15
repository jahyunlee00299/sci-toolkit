"""Container hints and `collect_snapshot`, the single assembly point of all probes."""

from __future__ import annotations

import datetime as dt
import os
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from _common import SCHEMA_VERSION, emit_json

from .accelerator_parsers import _visibility_summary
from .accelerators import _detect_accelerators
from .cgroup import _cgroup_not_detected, detect_cgroup_v2
from .commands import _load_psutil, _run_bounded_command
from .core import _AUTO, _provenance, _read_bounded_text, _safe_text
from .cpu import _detect_cpu_inventory, _detect_process_cpu_count, _effective_cpu, _mac_sysctl_values
from .disk import _detect_disk
from .memory import _detect_memory
from .scheduler import detect_scheduler


def _container_context(
    *,
    cgroup: Mapping[str, Any],
    exists: Callable[[Path], bool] = Path.exists,
) -> dict[str, Any]:
    evidence: list[str] = []
    for marker, label in (
        (Path("/.dockerenv"), "docker_marker"),
        (Path("/run/.containerenv"), "containerenv_marker"),
    ):
        try:
            if exists(marker):
                evidence.append(label)
        except OSError:
            pass
    if cgroup.get("detected") and any(
        cgroup.get(key) is not None
        for key in ("cpu_quota_cores", "cpuset_logical", "memory_max_bytes")
    ):
        evidence.append("cgroup_limit")
    return {
        "detected": bool(
            {"docker_marker", "containerenv_marker"}.intersection(evidence)
        ),
        "evidence": sorted(evidence),
        "runtime": (
            "docker_or_compatible"
            if "docker_marker" in evidence
            else "oci_compatible"
            if "containerenv_marker" in evidence
            else None
        ),
    }


def _observed_at() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _skipped_accelerators(environment: Mapping[str, str]) -> dict[str, Any]:
    """The accelerator section when --skip-accelerators is given."""
    return {
        "candidate_counts": {"cuda": 0, "metal": 0, "rocm": 0},
        "candidate_upper_bounds": {
            "cuda": None,
            "metal": None,
            "rocm": None,
        },
        "devices": [],
        "runtime_usable_devices": None,
        "visibility_environment": _visibility_summary(environment),
    }


def _completeness(warnings: list[dict[str, str]]) -> str:
    if any(item["severity"] == "warning" for item in warnings):
        return "partial"
    return "complete_with_informational_notes" if warnings else "complete"


@dataclass(frozen=True)
class _ProbeContext:
    """What every probe stage shares: the host identity, the injected I/O and the record lists."""

    system: str
    machine: str
    environment: Mapping[str, str]
    psutil_module: Any
    read_text: Callable[[Path], str]
    run_command: Callable[..., dict[str, Any]]
    warnings: list[dict[str, str]]
    provenance: list[dict[str, str]]


def _resolve_psutil(
    psutil_module: Any,
    warnings: list[dict[str, str]],
    provenance: list[dict[str, str]],
) -> Any:
    """The psutil module to probe with: imported on demand, or the injected one (None = absent)."""
    if psutil_module is _AUTO:
        return _load_psutil(warnings, provenance)
    if psutil_module is None:
        _provenance(provenance, "inventory.psutil", "injected", "unavailable")
    return psutil_module


def _detect_mac_sysctl(ctx: _ProbeContext) -> dict[str, Any]:
    """Apple sysctl values; every other system has none."""
    if ctx.system != "Darwin":
        return {}
    return _mac_sysctl_values(ctx.run_command, ctx.warnings, ctx.provenance)


def _detect_cpu_counts(
    ctx: _ProbeContext,
    mac_sysctl: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Host CPU inventory and this process's CPU count, probed before the limits that cap them."""
    host_cpu = _detect_cpu_inventory(
        system=ctx.system,
        psutil_module=ctx.psutil_module,
        mac_sysctl=mac_sysctl,
        read_text=ctx.read_text,
        warnings=ctx.warnings,
        provenance=ctx.provenance,
    )
    process_cpu = _detect_process_cpu_count(
        psutil_module=ctx.psutil_module,
        warnings=ctx.warnings,
        provenance=ctx.provenance,
    )
    return host_cpu, process_cpu


def _detect_cgroup(ctx: _ProbeContext) -> dict[str, Any]:
    """cgroup v2 limits; only Linux has them."""
    if ctx.system != "Linux":
        return _cgroup_not_detected("not_applicable")
    return detect_cgroup_v2(
        read_text=ctx.read_text,
        warnings=ctx.warnings,
        provenance=ctx.provenance,
    )


def _cpu_section(
    host_cpu: dict[str, Any],
    process_cpu: dict[str, Any],
    cgroup: Mapping[str, Any],
    scheduler: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "cgroup_v2": {
            "cpuset_logical": cgroup.get("cpuset_logical"),
            "quota_cores": cgroup.get("cpu_quota_cores"),
        },
        "effective": _effective_cpu(host_cpu, process_cpu, cgroup, scheduler),
        "host": host_cpu,
        "process": process_cpu,
    }


def _accelerator_section(
    ctx: _ProbeContext,
    scheduler: Mapping[str, Any],
    skip_accelerators: bool,
) -> dict[str, Any]:
    """Probe the accelerators, or report them as skipped when the caller asked not to."""
    if skip_accelerators:
        accelerators = _skipped_accelerators(ctx.environment)
        _provenance(ctx.provenance, "accelerators", "user_option", "skipped")
        return accelerators
    return _detect_accelerators(
        system=ctx.system,
        machine=ctx.machine,
        environ=ctx.environment,
        scheduler=scheduler,
        run_command=ctx.run_command,
        warnings=ctx.warnings,
        provenance=ctx.provenance,
    )


def _sort_records(
    warnings: list[dict[str, str]],
    provenance: list[dict[str, str]],
) -> None:
    """Put both record lists into their deterministic order, in place."""
    warnings.sort(
        key=lambda item: (
            item["component"],
            item["code"],
            item["message"],
        )
    )
    provenance.sort(
        key=lambda item: (item["component"], item["source"], item["status"])
    )


def _assemble_snapshot(
    ctx: _ProbeContext,
    observed_at: str | None,
    *,
    accelerators: dict[str, Any],
    cgroup: Mapping[str, Any],
    cpu: dict[str, Any],
    disk: dict[str, Any],
    memory: dict[str, Any],
    scheduler: dict[str, Any],
) -> dict[str, Any]:
    """The snapshot document; every section is a fresh object, the record lists are ctx's."""
    return {
        "accelerators": accelerators,
        "cgroup_v2": {
            "detected": cgroup.get("detected"),
            "scope": cgroup.get("scope"),
        },
        "completeness": _completeness(ctx.warnings),
        "container": _container_context(cgroup=cgroup),
        "cpu": cpu,
        "disk": disk,
        "memory": memory,
        "observed_at": observed_at or _observed_at(),
        "platform": {
            "machine": ctx.machine,
            "python_version": _safe_text(platform.python_version(), 64) or "unknown",
            "system": ctx.system,
        },
        "privacy": {
            "absolute_paths_included": False,
            "environment_values_included": False,
            "hostnames_included": False,
            "identifiers_redacted_by_default": True,
        },
        "provenance": ctx.provenance,
        "scheduler": scheduler,
        "schema_version": SCHEMA_VERSION,
        "snapshot_kind": "effective_resource_snapshot",
        "warnings": ctx.warnings,
    }


def collect_snapshot(
    *,
    skip_accelerators: bool = False,
    observed_at: str | None = None,
    environ: Mapping[str, str] | None = None,
    psutil_module: Any = _AUTO,
    read_text: Callable[[Path], str] = _read_bounded_text,
    run_command: Callable[..., dict[str, Any]] = _run_bounded_command,
) -> dict[str, Any]:
    """Collect one snapshot; individual probe failures remain warnings."""
    warnings: list[dict[str, str]] = []
    provenance: list[dict[str, str]] = []
    environment = os.environ if environ is None else environ
    system = _safe_text(platform.system(), 64) or "Unknown"
    machine = _safe_text(platform.machine(), 64) or "unknown"
    ctx = _ProbeContext(
        system=system,
        machine=machine,
        environment=environment,
        psutil_module=_resolve_psutil(psutil_module, warnings, provenance),
        read_text=read_text,
        run_command=run_command,
        warnings=warnings,
        provenance=provenance,
    )

    mac_sysctl = _detect_mac_sysctl(ctx)
    host_cpu, process_cpu = _detect_cpu_counts(ctx, mac_sysctl)
    cgroup = _detect_cgroup(ctx)
    scheduler = detect_scheduler(
        ctx.environment,
        warnings=warnings,
        provenance=provenance,
    )
    cpu = _cpu_section(host_cpu, process_cpu, cgroup, scheduler)
    memory = _detect_memory(
        system=ctx.system,
        machine=ctx.machine,
        psutil_module=ctx.psutil_module,
        mac_sysctl=mac_sysctl,
        cgroup=cgroup,
        scheduler=scheduler,
        read_text=read_text,
        warnings=warnings,
        provenance=provenance,
    )
    accelerators = _accelerator_section(ctx, scheduler, skip_accelerators)
    disk = _detect_disk(warnings, provenance)
    _sort_records(warnings, provenance)
    return _assemble_snapshot(
        ctx,
        observed_at,
        accelerators=accelerators,
        cgroup=cgroup,
        cpu=cpu,
        disk=disk,
        memory=memory,
        scheduler=scheduler,
    )


def detect_all_resources(output_path: str | None = None) -> dict[str, Any]:
    """Compatibility API: collect a snapshot and optionally write it safely."""
    snapshot = collect_snapshot()
    if output_path is not None:
        emit_json(snapshot, output_path)
    return snapshot
