"""Parsers for nvidia-smi CSV, amd-smi / rocm-smi JSON and system_profiler JSON output,
plus the accelerator visibility-environment summary."""

from __future__ import annotations

import csv
import io
import json
import math
import re
from typing import Any, Mapping

from .core import GIB, MAX_BYTES, MIB, _bounded_nonnegative, _safe_text

ACCELERATOR_ENV_KEYS = (
    "CUDA_VISIBLE_DEVICES",
    "HIP_VISIBLE_DEVICES",
    "NVIDIA_VISIBLE_DEVICES",
    "ROCR_VISIBLE_DEVICES",
)


def _mib_to_bytes(value: str) -> int | None:
    try:
        amount = float(value)
    except ValueError:
        return None
    if not math.isfinite(amount) or amount < 0:
        return None
    result = round(amount * MIB)
    return result if result <= MAX_BYTES else None


def parse_nvidia_csv(payload: str) -> list[dict[str, Any]]:
    devices: list[dict[str, Any]] = []
    try:
        rows = csv.reader(io.StringIO(payload))
        for row in rows:
            if len(row) not in {5, 6}:
                continue
            index = _bounded_nonnegative(row[0])
            if index is None or index > 4096:
                continue
            devices.append(
                {
                    "backend_candidate": "cuda",
                    "compute_capability": (
                        _safe_text(row[5], 16) if len(row) == 6 else None
                    ),
                    "device_class": "gpu",
                    "device_permission": "not_tested",
                    "driver_version": _safe_text(row[4], 64),
                    "local_index": index,
                    "management_query": "visible",
                    "memory": {
                        "dedicated_free_bytes": _mib_to_bytes(row[3].strip()),
                        "dedicated_total_bytes": _mib_to_bytes(row[2].strip()),
                        "model": "dedicated",
                    },
                    "name": _safe_text(row[1]) or "NVIDIA GPU",
                    "runtime_compatibility": "not_tested",
                    "vendor": "nvidia",
                }
            )
    except csv.Error:
        return []
    return sorted(devices, key=lambda item: item["local_index"])


def _recursive_scalar(
    value: Any,
    accepted_keys: set[str],
) -> tuple[str, Any] | None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = re.sub(r"[^a-z0-9]+", "_", str(key).lower()).strip("_")
            if normalized in accepted_keys and isinstance(child, (str, int, float)):
                return normalized, child
        for child in value.values():
            found = _recursive_scalar(child, accepted_keys)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _recursive_scalar(child, accepted_keys)
            if found is not None:
                return found
    return None


def _amd_entries(data: Any) -> list[tuple[int, dict[str, Any]]]:
    entries: list[tuple[int, dict[str, Any]]] = []
    if isinstance(data, list):
        for index, item in enumerate(data):
            if isinstance(item, dict) and (
                "gpu" in {str(key).lower() for key in item}
                or "asic" in {str(key).lower() for key in item}
            ):
                gpu_value = next(
                    (
                        value
                        for key, value in item.items()
                        if str(key).lower() == "gpu"
                    ),
                    index,
                )
                gpu_index = _bounded_nonnegative(gpu_value)
                entries.append((gpu_index if gpu_index is not None else index, item))
    elif isinstance(data, dict):
        for key, item in data.items():
            normalized = re.sub(
                r"[^a-z0-9]+", "_", str(key).lower()
            ).strip("_")
            if normalized in {"gpu_data", "gpu_devices", "gpus"}:
                entries.extend(_amd_entries(item))
        for key, item in data.items():
            match = re.fullmatch(r"(?:card|gpu)\s*(\d+)", str(key), re.IGNORECASE)
            if match and isinstance(item, dict):
                entries.append((int(match.group(1)), item))
        if not entries and "gpu" in {str(key).lower() for key in data}:
            gpu_value = next(
                value for key, value in data.items() if str(key).lower() == "gpu"
            )
            if not isinstance(gpu_value, (dict, list)):
                gpu_index = _bounded_nonnegative(gpu_value)
                entries.append((gpu_index or 0, data))
    deduplicated: dict[int, dict[str, Any]] = {}
    for index, entry in entries:
        deduplicated.setdefault(index, entry)
    return sorted(deduplicated.items())


def _amd_memory_bytes(entry: Mapping[str, Any]) -> int | None:
    for key, value in entry.items():
        normalized = re.sub(r"[^a-z0-9]+", "_", str(key).lower()).strip("_")
        if (
            "vram" in normalized
            and ("total" in normalized or "size" in normalized)
            and isinstance(value, (str, int, float))
        ):
            match = re.search(r"(\d+(?:\.\d+)?)", str(value))
            if not match:
                continue
            amount = float(match.group(1))
            unit_context = f"{normalized} {str(value).lower()}"
            if "gib" in unit_context or "gb" in unit_context:
                multiplier = GIB
            elif "mib" in unit_context or "mb" in unit_context:
                multiplier = MIB
            else:
                multiplier = 1
            result = round(amount * multiplier)
            if 0 <= result <= MAX_BYTES:
                return result
        if isinstance(value, dict):
            nested = _amd_memory_bytes(value)
            if nested is not None:
                return nested
    return None


def parse_amd_json(payload: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(payload)
        entries = _amd_entries(data)
    except (json.JSONDecodeError, RecursionError):
        return []
    devices: list[dict[str, Any]] = []
    name_keys = {
        "asic_market_name",
        "card_model",
        "card_series",
        "market_name",
        "product_name",
    }
    for index, entry in entries:
        try:
            found = _recursive_scalar(entry, name_keys)
            total_memory = _amd_memory_bytes(entry)
        except RecursionError:
            continue
        name = _safe_text(found[1]) if found else None
        devices.append(
            {
                "backend_candidate": "rocm",
                "compute_capability": None,
                "device_class": "gpu",
                "device_permission": "not_tested",
                "driver_version": None,
                "local_index": index,
                "management_query": "visible",
                "memory": {
                    "dedicated_free_bytes": None,
                    "dedicated_total_bytes": total_memory,
                    "model": "dedicated_or_hbm",
                },
                "name": name or "AMD GPU",
                "runtime_compatibility": "not_tested",
                "vendor": "amd",
            }
        )
    return sorted(devices, key=lambda item: item["local_index"])


def parse_apple_profiler_json(
    payload: str,
    *,
    machine: str,
) -> list[dict[str, Any]]:
    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, RecursionError):
        return []
    entries = data.get("SPDisplaysDataType") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return []
    unified = machine.lower() in {"arm64", "aarch64"}
    devices: list[dict[str, Any]] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        name = _safe_text(entry.get("sppci_model") or entry.get("_name"))
        core_value = (
            entry.get("sppci_cores")
            or entry.get("spdisplays_gpu_cores")
            or entry.get("_spdisplays_gpu_cores")
        )
        devices.append(
            {
                "backend_candidate": "metal",
                "compute_capability": None,
                "device_class": "integrated_gpu" if unified else "gpu",
                "device_permission": "not_tested",
                "driver_version": None,
                "gpu_cores": _bounded_nonnegative(core_value),
                "local_index": index,
                "management_query": "visible",
                "memory": {
                    "dedicated_free_bytes": None,
                    "dedicated_total_bytes": None,
                    "model": "unified" if unified else "unknown",
                },
                "name": name or "Apple display accelerator",
                "runtime_compatibility": "not_tested",
                "vendor": "apple",
            }
        )
    return devices


def _visibility_summary(environ: Mapping[str, str]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key in ACCELERATOR_ENV_KEYS:
        if key not in environ:
            summary[key] = {
                "entry_count": None,
                "set": False,
                "state": "unset",
                "value_redacted": True,
            }
            continue
        raw = environ[key] if isinstance(environ[key], str) else ""
        if len(raw) > 4096:
            summary[key] = {
                "entry_count": None,
                "set": True,
                "state": "invalid_or_oversized",
                "value_redacted": True,
            }
            continue
        stripped = raw.strip()
        lowered = stripped.lower()
        if lowered in {"", "-1", "none", "void"}:
            state, count = "none", 0
        elif lowered == "all":
            state, count = "all", None
        else:
            entries = {
                item.strip() for item in stripped.split(",") if item.strip()
            }
            state = "restricted" if entries else "none"
            count = min(len(entries), 4096)
        summary[key] = {
            "entry_count": count,
            "set": True,
            "state": state,
            "value_redacted": True,
        }
    return summary
