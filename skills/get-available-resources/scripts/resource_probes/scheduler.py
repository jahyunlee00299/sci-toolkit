"""Slurm allocation variables, read from an allowlist only."""

from __future__ import annotations

import re
from typing import Any, Mapping

from .core import GIB, MAX_BYTES, MIB, _provenance, _warning

SLURM_ENV_KEYS = (
    "SLURM_JOB_ID",
    "SLURM_JOBID",
    "SLURM_CPUS_ON_NODE",
    "SLURM_CPUS_PER_TASK",
    "SLURM_JOB_CPUS_PER_NODE",
    "SLURM_MEM_PER_CPU",
    "SLURM_MEM_PER_NODE",
    "SLURM_NTASKS",
    "SLURM_NTASKS_PER_NODE",
    "SLURM_TASKS_PER_NODE",
    "SLURM_GPUS",
    "SLURM_GPUS_ON_NODE",
    "SLURM_GPUS_PER_TASK",
    "SLURM_JOB_GPUS",
    "SLURM_STEP_GPUS",
)


def _parse_slurm_count(value: str | None) -> int | None:
    if value is None or not 0 < len(value) <= 128:
        return None
    stripped = value.strip()
    if stripped.isdigit():
        count = int(stripped)
        return count if 0 <= count <= 1_000_000 else None
    match = re.fullmatch(r"(?:[A-Za-z0-9_.+-]+:)+(\d+)", stripped)
    if match:
        count = int(match.group(1))
        return count if count <= 1_000_000 else None
    return None


def _parse_slurm_memory(value: str | None) -> int | None:
    if value is None or not 0 < len(value) <= 128:
        return None
    match = re.fullmatch(r"\s*(\d+)\s*([KkMmGgTt]?)\s*", value)
    if not match:
        return None
    amount = int(match.group(1))
    if amount == 0:
        return None
    suffix = match.group(2).upper()
    multiplier = {"K": 1024, "M": MIB, "G": GIB, "T": 1024**4, "": MIB}[suffix]
    result = amount * multiplier
    return result if result <= MAX_BYTES else None


def _parse_first_repeated_count(value: str | None) -> int | None:
    if value is None or len(value) > 4096:
        return None
    match = re.match(r"\s*(\d+)(?:\(x\d+\))?", value)
    if not match:
        return None
    count = int(match.group(1))
    return count if count <= 1_000_000 else None


def _no_scheduler() -> dict[str, Any]:
    return {
        "allocation": {
            "cpu_per_process": None,
            "cpus_on_node": None,
            "gpus_per_process": None,
            "gpus_on_node": None,
            "memory_effective_bytes": None,
            "memory_scope": None,
            "tasks": None,
        },
        "detected": False,
        "enforcement": "not_applicable",
        "fields_read": [],
        "kind": None,
    }


def _slurm_memory(
    present: Mapping[str, str],
    cpu_per_process: int | None,
    tasks_per_node: int | None,
    warning_records: list[dict[str, str]],
) -> tuple[int | None, str | None]:
    """(effective memory bytes, scope) from SLURM_MEM_PER_CPU / SLURM_MEM_PER_NODE."""
    memory_per_cpu = _parse_slurm_memory(present.get("SLURM_MEM_PER_CPU"))
    memory_per_node = _parse_slurm_memory(present.get("SLURM_MEM_PER_NODE"))
    if memory_per_cpu is not None and cpu_per_process is not None:
        return min(MAX_BYTES, memory_per_cpu * cpu_per_process), "per_task_from_per_cpu"
    if memory_per_node is not None:
        if tasks_per_node is None or tasks_per_node > 1:
            _warning(
                warning_records,
                "SLURM_MEMORY_SHARED",
                "scheduler",
                "Slurm per-node memory is shared; it is only an upper bound for this process.",
                severity="info",
            )
        return memory_per_node, "shared_per_node"
    return None, None


def detect_scheduler(
    environ: Mapping[str, str],
    *,
    warnings: list[dict[str, str]] | None = None,
    provenance: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Interpret only an allowlist of Slurm allocation variables."""
    warning_records = warnings if warnings is not None else []
    provenance_records = provenance if provenance is not None else []
    present = {
        key: environ[key]
        for key in SLURM_ENV_KEYS
        if key in environ and isinstance(environ[key], str)
    }
    if not present:
        _provenance(provenance_records, "scheduler", "named_slurm_environment", "absent")
        return _no_scheduler()

    cpus_per_task = _parse_slurm_count(present.get("SLURM_CPUS_PER_TASK"))
    cpus_on_node = _parse_slurm_count(present.get("SLURM_CPUS_ON_NODE"))
    tasks = _parse_slurm_count(present.get("SLURM_NTASKS"))
    tasks_per_node = _parse_slurm_count(present.get("SLURM_NTASKS_PER_NODE"))
    if tasks_per_node is None:
        tasks_per_node = _parse_first_repeated_count(
            present.get("SLURM_TASKS_PER_NODE")
        )
    first_job_cpus = _parse_first_repeated_count(
        present.get("SLURM_JOB_CPUS_PER_NODE")
    )
    cpu_per_process = cpus_per_task
    if cpu_per_process is None and cpus_on_node is not None and tasks_per_node == 1:
        cpu_per_process = cpus_on_node

    memory_effective, memory_scope = _slurm_memory(
        present, cpu_per_process, tasks_per_node, warning_records
    )

    gpus_per_task = _parse_slurm_count(present.get("SLURM_GPUS_PER_TASK"))
    gpus_on_node = _parse_slurm_count(present.get("SLURM_GPUS_ON_NODE"))
    requested_gpus = _parse_slurm_count(present.get("SLURM_GPUS"))

    _warning(
        warning_records,
        "SLURM_ENFORCEMENT_UNKNOWN",
        "scheduler",
        "Allocation variables do not prove task affinity or cgroup enforcement.",
        severity="info",
    )
    if cpus_per_task is None and cpus_on_node is not None and tasks_per_node != 1:
        _warning(
            warning_records,
            "SLURM_CPU_SCOPE_SHARED",
            "scheduler",
            "Node CPU allocation was not treated as a per-process limit.",
            severity="info",
        )
    _provenance(provenance_records, "scheduler", "named_slurm_environment", "ok")
    return {
        "allocation": {
            "cpu_per_process": cpu_per_process,
            "cpus_on_node": cpus_on_node,
            "first_job_cpus_per_node": first_job_cpus,
            "gpus_per_process": gpus_per_task,
            "gpus_on_node": gpus_on_node,
            "gpus_requested": requested_gpus,
            "memory_effective_bytes": memory_effective,
            "memory_scope": memory_scope,
            "tasks": tasks,
            "tasks_per_node": tasks_per_node,
        },
        "detected": True,
        "enforcement": "unknown",
        "fields_read": sorted(present),
        "kind": "slurm",
    }
