"""Working-filesystem capacity (no write probe)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from .core import _bounded_nonnegative, _provenance, _warning


def _detect_disk(
    warnings: list[dict[str, str]],
    provenance: list[dict[str, str]],
) -> dict[str, Any]:
    try:
        usage = shutil.disk_usage(Path.cwd())
        total = _bounded_nonnegative(usage.total)
        free = _bounded_nonnegative(usage.free)
        if total is None or free is None or free > total:
            raise ValueError("invalid bounded disk values")
        _provenance(provenance, "disk", "shutil.disk_usage", "ok")
    except (OSError, ValueError):
        _warning(
            warnings,
            "DISK_CAPACITY_UNKNOWN",
            "disk",
            "Working filesystem capacity could not be read.",
        )
        _provenance(provenance, "disk", "shutil.disk_usage", "unavailable")
        return {
            "capacity_bytes": None,
            "free_bytes": None,
            "scope": "working_filesystem_path_redacted",
            "user_available_bytes": None,
            "writable": None,
            "writability_check": "not_performed",
        }

    user_available = free
    if hasattr(os, "statvfs"):
        try:
            statvfs = os.statvfs(Path.cwd())
            candidate = _bounded_nonnegative(
                statvfs.f_bavail * statvfs.f_frsize
            )
            if candidate is not None:
                user_available = candidate
                _provenance(
                    provenance, "disk.user_available", "os.statvfs", "ok"
                )
        except (OSError, TypeError, ValueError):
            pass
    writable = os.access(Path.cwd(), os.W_OK)
    if not writable:
        _warning(
            warnings,
            "WORKING_DIRECTORY_NOT_WRITABLE",
            "disk",
            "The working directory failed the non-writing access check.",
        )
    return {
        "capacity_bytes": total,
        "free_bytes": free,
        "scope": "working_filesystem_path_redacted",
        "user_available_bytes": max(0, min(free, user_available)),
        "writable": bool(writable),
        "writability_check": "os_access_only_no_write_probe",
    }
