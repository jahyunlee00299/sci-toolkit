"""Limits, warning/provenance records and bounded text helpers shared by every probe."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from _common import MAX_BYTES

MAX_PROBE_OUTPUT = 65_536
MAX_KERNEL_TEXT = 524_288
MAX_CGROUP_LEVELS = 64
MAX_CPU_ID = 1_048_575
MAX_DEVICES = 256
MIB = 1024**2
GIB = 1024**3
_AUTO = object()


def _warning(
    warnings: list[dict[str, str]],
    code: str,
    component: str,
    message: str,
    *,
    severity: str = "warning",
) -> None:
    warnings.append(
        {
            "code": code,
            "component": component,
            "message": message,
            "severity": severity,
        }
    )


def _provenance(
    records: list[dict[str, str]],
    component: str,
    source: str,
    status: str,
) -> None:
    records.append(
        {"component": component, "source": source, "status": status}
    )


def _safe_text(value: Any, maximum: int = 128) -> str | None:
    if not isinstance(value, (str, int, float)):
        return None
    rendered = " ".join(str(value).split())
    rendered = "".join(character for character in rendered if character.isprintable())
    return rendered[:maximum] or None


def _read_bounded_text(path: Path, maximum: int = MAX_KERNEL_TEXT) -> str:
    with path.open("rb") as stream:
        payload = stream.read(maximum + 1)
    if len(payload) > maximum:
        raise ValueError("bounded text input exceeded")
    return payload.decode("utf-8", errors="replace")


def _try_read(
    read_text: Callable[[Path], str],
    path: Path,
) -> str | None:
    try:
        return read_text(path)
    except (OSError, ValueError, UnicodeError):
        return None


def _bounded_nonnegative(value: str | int | None) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        parsed = int(str(value).strip(), 10)
    except (TypeError, ValueError):
        return None
    return parsed if 0 <= parsed <= MAX_BYTES else None
