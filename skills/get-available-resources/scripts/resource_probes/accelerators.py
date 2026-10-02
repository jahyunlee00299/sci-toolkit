"""Accelerator management probes (nvidia-smi, amd-smi / rocm-smi, system_profiler)
and the visibility-based upper bounds. Management visibility only: nothing here
proves permission or framework/runtime compatibility."""

from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

from .accelerator_parsers import (
    _visibility_summary,
    parse_amd_json,
    parse_apple_profiler_json,
    parse_nvidia_csv,
)
from .core import MAX_DEVICES, _provenance, _warning

NVIDIA_QUERY = (
    "nvidia-smi",
    "--query-gpu=index,name,memory.total,memory.free,driver_version,compute_cap",
    "--format=csv,noheader,nounits",
)
NVIDIA_QUERY_FALLBACK = (
    "nvidia-smi",
    "--query-gpu=index,name,memory.total,memory.free,driver_version",
    "--format=csv,noheader,nounits",
)
AMD_SMI_QUERY = ("amd-smi", "static", "--json")
ROCM_SMI_QUERY = (
    "rocm-smi",
    "--showproductname",
    "--showmeminfo",
    "vram",
    "--json",
)

APPLE_DISPLAY_QUERY = ("system_profiler", "SPDisplaysDataType", "-json")


def _accelerator_upper_bounds(
    devices: Sequence[Mapping[str, Any]],
    visibility: Mapping[str, Mapping[str, Any]],
    scheduler: Mapping[str, Any],
) -> dict[str, int | None]:
    result: dict[str, int | None] = {}
    scheduler_count = scheduler.get("allocation", {}).get("gpus_per_process")
    if scheduler_count is None:
        scheduler_count = scheduler.get("allocation", {}).get("gpus_on_node")
    environment_keys = {
        "cuda": ("CUDA_VISIBLE_DEVICES", "NVIDIA_VISIBLE_DEVICES"),
        "rocm": ("ROCR_VISIBLE_DEVICES", "HIP_VISIBLE_DEVICES", "CUDA_VISIBLE_DEVICES"),
        "metal": (),
    }
    for backend, keys in environment_keys.items():
        query_count = sum(
            1 for device in devices if device.get("backend_candidate") == backend
        )
        if query_count == 0:
            result[backend] = None
            continue
        limits = [query_count]
        if isinstance(scheduler_count, int):
            limits.append(scheduler_count)
        for key in keys:
            item = visibility.get(key, {})
            if item.get("state") == "none":
                limits.append(0)
            elif (
                item.get("state") == "restricted"
                and isinstance(item.get("entry_count"), int)
            ):
                limits.append(item["entry_count"])
        result[backend] = min(limits)
    return result


def _record_probe_failure(
    result: Mapping[str, Any],
    *,
    code: str,
    component: str,
    tool: str,
    warnings: list[dict[str, str]],
    provenance: list[dict[str, str]],
) -> None:
    status = str(result.get("status", "error"))
    _provenance(provenance, component, tool, status)
    if status != "not_found":
        _warning(
            warnings,
            code,
            component,
            f"{tool} read-only query did not complete successfully ({status}).",
            severity="info" if status in {"start_error", "error"} else "warning",
        )


def _probe_nvidia(
    run_command: Callable[..., dict[str, Any]],
    warnings: list[dict[str, str]],
    provenance: list[dict[str, str]],
) -> list[dict[str, Any]]:
    nvidia = run_command(NVIDIA_QUERY, timeout=4.0)
    nvidia_devices = parse_nvidia_csv(nvidia.get("stdout", "")) if nvidia["status"] == "ok" else []
    if nvidia["status"] == "error":
        fallback = run_command(NVIDIA_QUERY_FALLBACK, timeout=4.0)
        if fallback["status"] == "ok":
            nvidia = fallback
            nvidia_devices = parse_nvidia_csv(fallback.get("stdout", ""))
    if nvidia["status"] == "ok":
        _provenance(provenance, "accelerators.nvidia", "nvidia-smi", "ok")
        if nvidia.get("stdout", "").strip() and not nvidia_devices:
            _warning(
                warnings,
                "NVIDIA_OUTPUT_PARSE_FAILED",
                "accelerators",
                "nvidia-smi returned an unexpected bounded CSV response.",
            )
    else:
        _record_probe_failure(
            nvidia,
            code="NVIDIA_QUERY_FAILED",
            component="accelerators.nvidia",
            tool="nvidia-smi",
            warnings=warnings,
            provenance=provenance,
        )
    return nvidia_devices


def _probe_amd(
    run_command: Callable[..., dict[str, Any]],
    warnings: list[dict[str, str]],
    provenance: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """amd-smi first; rocm-smi when amd-smi is absent, failed or listed nothing."""
    amd = run_command(AMD_SMI_QUERY, timeout=4.0)
    amd_devices = parse_amd_json(amd.get("stdout", "")) if amd["status"] == "ok" else []
    amd_tool = "amd-smi"
    if not amd_devices and amd["status"] in {"not_found", "error", "start_error"}:
        amd = run_command(ROCM_SMI_QUERY, timeout=4.0)
        amd_tool = "rocm-smi"
        amd_devices = parse_amd_json(amd.get("stdout", "")) if amd["status"] == "ok" else []
    if amd["status"] == "ok":
        _provenance(provenance, "accelerators.amd", amd_tool, "ok")
        if amd.get("stdout", "").strip() and not amd_devices:
            _warning(
                warnings,
                "AMD_OUTPUT_PARSE_FAILED",
                "accelerators",
                f"{amd_tool} returned an unexpected bounded JSON response.",
            )
    else:
        _record_probe_failure(
            amd,
            code="AMD_QUERY_FAILED",
            component="accelerators.amd",
            tool=amd_tool,
            warnings=warnings,
            provenance=provenance,
        )
    return amd_devices


def _apple_silicon_inferred_device() -> dict[str, Any]:
    """Placeholder device when system_profiler lists nothing on Apple silicon."""
    return {
        "backend_candidate": "metal",
        "compute_capability": None,
        "device_class": "integrated_gpu",
        "device_permission": "not_tested",
        "driver_version": None,
        "gpu_cores": None,
        "local_index": 0,
        "management_query": "inferred_from_apple_silicon_platform",
        "memory": {
            "dedicated_free_bytes": None,
            "dedicated_total_bytes": None,
            "model": "unified",
        },
        "name": "Apple silicon integrated GPU",
        "runtime_compatibility": "not_tested",
        "vendor": "apple",
    }


def _probe_apple(
    run_command: Callable[..., dict[str, Any]],
    machine: str,
    warnings: list[dict[str, str]],
    provenance: list[dict[str, str]],
) -> list[dict[str, Any]]:
    apple = run_command(APPLE_DISPLAY_QUERY, timeout=5.0)
    apple_devices = (
        parse_apple_profiler_json(apple.get("stdout", ""), machine=machine)
        if apple["status"] == "ok"
        else []
    )
    if apple["status"] == "ok":
        _provenance(
            provenance, "accelerators.apple", "system_profiler", "ok"
        )
    else:
        _record_probe_failure(
            apple,
            code="APPLE_ACCELERATOR_QUERY_FAILED",
            component="accelerators.apple",
            tool="system_profiler",
            warnings=warnings,
            provenance=provenance,
        )
    if not apple_devices and machine.lower() in {"arm64", "aarch64"}:
        apple_devices = [_apple_silicon_inferred_device()]
    return apple_devices


def _detect_accelerators(
    *,
    system: str,
    machine: str,
    environ: Mapping[str, str],
    scheduler: Mapping[str, Any],
    run_command: Callable[..., dict[str, Any]],
    warnings: list[dict[str, str]],
    provenance: list[dict[str, str]],
) -> dict[str, Any]:
    devices: list[dict[str, Any]] = []
    devices.extend(_probe_nvidia(run_command, warnings, provenance))
    devices.extend(_probe_amd(run_command, warnings, provenance))
    if system == "Darwin":
        devices.extend(_probe_apple(run_command, machine, warnings, provenance))

    devices.sort(
        key=lambda item: (
            str(item.get("backend_candidate")),
            int(item.get("local_index", 0)),
            str(item.get("name")),
        )
    )
    if len(devices) > MAX_DEVICES:
        devices = devices[:MAX_DEVICES]
        _warning(
            warnings,
            "ACCELERATOR_DEVICE_LIST_BOUNDED",
            "accelerators",
            f"Accelerator output was limited to {MAX_DEVICES} devices.",
        )
    visibility = _visibility_summary(environ)
    if devices:
        _warning(
            warnings,
            "ACCELERATOR_RUNTIME_NOT_TESTED",
            "accelerators",
            "Management visibility does not prove permission or framework/runtime compatibility.",
            severity="info",
        )
    counts = {
        backend: sum(
            1 for device in devices if device.get("backend_candidate") == backend
        )
        for backend in ("cuda", "metal", "rocm")
    }
    return {
        "candidate_counts": counts,
        "candidate_upper_bounds": _accelerator_upper_bounds(
            devices, visibility, scheduler
        ),
        "devices": devices,
        "runtime_usable_devices": None,
        "visibility_environment": visibility,
    }
