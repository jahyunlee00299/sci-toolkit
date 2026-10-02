"""Bounded subprocess runner (fixed argv, no shell) and the optional psutil import."""

from __future__ import annotations

import importlib
import subprocess
import threading
from typing import Any, Sequence

from .core import MAX_PROBE_OUTPUT, _provenance, _warning


def _run_bounded_command(
    argv: Sequence[str],
    *,
    timeout: float = 4.0,
    maximum: int = MAX_PROBE_OUTPUT,
) -> dict[str, Any]:
    """Run a fixed argv with bounded stdout/stderr and no shell."""
    if not isinstance(argv, tuple) or not argv or not all(
        isinstance(item, str) and item for item in argv
    ):
        raise ValueError("internal command must be a fixed nonempty tuple")
    try:
        process = subprocess.Popen(
            list(argv),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
        )
    except FileNotFoundError:
        return {"status": "not_found", "stdout": "", "stderr": ""}
    except OSError:
        return {"status": "start_error", "stdout": "", "stderr": ""}

    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    truncated = threading.Event()

    def drain(name: str, stream: Any) -> None:
        try:
            while True:
                chunk = stream.read(4096)
                if not chunk:
                    break
                remaining = maximum - len(buffers[name])
                if remaining > 0:
                    buffers[name].extend(chunk[:remaining])
                if len(chunk) > remaining:
                    truncated.set()
                    try:
                        process.kill()
                    except OSError:
                        pass
        finally:
            try:
                stream.close()
            except OSError:
                pass

    threads = [
        threading.Thread(
            target=drain,
            args=("stdout", process.stdout),
            daemon=True,
        ),
        threading.Thread(
            target=drain,
            args=("stderr", process.stderr),
            daemon=True,
        ),
    ]
    for thread in threads:
        thread.start()

    timed_out = False
    try:
        return_code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            process.kill()
        except OSError:
            pass
        return_code = process.wait()
    for thread in threads:
        thread.join(timeout=1.0)

    status = "ok" if return_code == 0 else "error"
    if timed_out:
        status = "timeout"
    elif truncated.is_set():
        status = "truncated"
    return {
        "returncode": return_code,
        "status": status,
        "stderr": buffers["stderr"].decode("utf-8", errors="replace"),
        "stdout": buffers["stdout"].decode("utf-8", errors="replace"),
    }


def _load_psutil(
    warnings: list[dict[str, str]],
    provenance: list[dict[str, str]],
) -> Any | None:
    try:
        module = importlib.import_module("psutil")
    except (ImportError, OSError):
        _warning(
            warnings,
            "PSUTIL_UNAVAILABLE",
            "inventory",
            "Optional psutil is unavailable; standard-library fallbacks were used.",
            severity="info",
        )
        _provenance(provenance, "inventory.psutil", "optional_import", "unavailable")
        return None
    _provenance(provenance, "inventory.psutil", "optional_import", "ok")
    return module
