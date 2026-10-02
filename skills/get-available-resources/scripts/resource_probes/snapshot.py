"""Container hints and `collect_snapshot`, the single assembly point of all probes."""

from __future__ import annotations

import datetime as dt
import os
import platform
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

    if psutil_module is _AUTO:
        psutil_module = _load_psutil(warnings, provenance)
    elif psutil_module is None:
        _provenance(provenance, "inventory.psutil", "injected", "unavailable")

    mac_sysctl: dict[str, Any] = {}
    if system == "Darwin":
        mac_sysctl = _mac_sysctl_values(run_command, warnings, provenance)
    host_cpu = _detect_cpu_inventory(
        system=system,
        psutil_module=psutil_module,
        mac_sysctl=mac_sysctl,
        read_text=read_text,
        warnings=warnings,
        provenance=provenance,
    )
    process_cpu = _detect_process_cpu_count(
        psutil_module=psutil_module,
        warnings=warnings,
        provenance=provenance,
    )
    cgroup = (
        detect_cgroup_v2(
            read_text=read_text,
            warnings=warnings,
            provenance=provenance,
        )
        if system == "Linux"
        else _cgroup_not_detected("not_applicable")
    )
    scheduler = detect_scheduler(
        environment,
        warnings=warnings,
        provenance=provenance,
    )
    cpu = {
        "cgroup_v2": {
            "cpuset_logical": cgroup.get("cpuset_logical"),
            "quota_cores": cgroup.get("cpu_quota_cores"),
        },
        "effective": _effective_cpu(host_cpu, process_cpu, cgroup, scheduler),
        "host": host_cpu,
        "process": process_cpu,
    }
    memory = _detect_memory(
        system=system,
        machine=machine,
        psutil_module=psutil_module,
        mac_sysctl=mac_sysctl,
        cgroup=cgroup,
        scheduler=scheduler,
        read_text=read_text,
        warnings=warnings,
        provenance=provenance,
    )
    if skip_accelerators:
        accelerators = _skipped_accelerators(environment)
        _provenance(provenance, "accelerators", "user_option", "skipped")
    else:
        accelerators = _detect_accelerators(
            system=system,
            machine=machine,
            environ=environment,
            scheduler=scheduler,
            run_command=run_command,
            warnings=warnings,
            provenance=provenance,
        )

    disk = _detect_disk(warnings, provenance)
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
    return {
        "accelerators": accelerators,
        "cgroup_v2": {
            "detected": cgroup.get("detected"),
            "scope": cgroup.get("scope"),
        },
        "completeness": _completeness(warnings),
        "container": _container_context(cgroup=cgroup),
        "cpu": cpu,
        "disk": disk,
        "memory": memory,
        "observed_at": observed_at or _observed_at(),
        "platform": {
            "machine": machine,
            "python_version": _safe_text(platform.python_version(), 64) or "unknown",
            "system": system,
        },
        "privacy": {
            "absolute_paths_included": False,
            "environment_values_included": False,
            "hostnames_included": False,
            "identifiers_redacted_by_default": True,
        },
        "provenance": provenance,
        "scheduler": scheduler,
        "schema_version": SCHEMA_VERSION,
        "snapshot_kind": "effective_resource_snapshot",
        "warnings": warnings,
    }


def detect_all_resources(output_path: str | None = None) -> dict[str, Any]:
    """Compatibility API: collect a snapshot and optionally write it safely."""
    snapshot = collect_snapshot()
    if output_path is not None:
        emit_json(snapshot, output_path)
    return snapshot
