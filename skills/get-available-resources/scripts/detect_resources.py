#!/usr/bin/env python3
"""Collect a conservative, privacy-preserving resource snapshot.

The script performs only bounded, read-only probes. It never stress-tests the
machine, allocates a large buffer, changes affinity, or changes accelerator
state. JSON is written to stdout unless a private local filename is explicitly
requested.

The probes live in the `resource_probes` package next to this file (see its
docstring for the module map); this file is the CLI entry point and re-exports
every name the single-file script used to define.
"""

from __future__ import annotations

import argparse
from typing import Sequence

from _common import (  # noqa: F401  (MAX_BYTES, SCHEMA_VERSION re-exported)
    MAX_BYTES,
    SCHEMA_VERSION,
    ResourceToolError,
    cli_error,
    emit_json,
)
from resource_probes.accelerator_parsers import (  # noqa: F401
    ACCELERATOR_ENV_KEYS,
    _amd_entries,
    _amd_memory_bytes,
    _mib_to_bytes,
    _recursive_scalar,
    _visibility_summary,
    parse_amd_json,
    parse_apple_profiler_json,
    parse_nvidia_csv,
)
from resource_probes.accelerators import (  # noqa: F401
    AMD_SMI_QUERY,
    APPLE_DISPLAY_QUERY,
    NVIDIA_QUERY,
    NVIDIA_QUERY_FALLBACK,
    ROCM_SMI_QUERY,
    _accelerator_upper_bounds,
    _detect_accelerators,
    _record_probe_failure,
)
from resource_probes.cgroup import (  # noqa: F401
    _cgroup_relative_path,
    _parse_cpu_max,
    detect_cgroup_v2,
)
from resource_probes.commands import _load_psutil, _run_bounded_command  # noqa: F401
from resource_probes.core import (  # noqa: F401
    GIB,
    MAX_CGROUP_LEVELS,
    MAX_CPU_ID,
    MAX_DEVICES,
    MAX_KERNEL_TEXT,
    MAX_PROBE_OUTPUT,
    MIB,
    _AUTO,
    _bounded_nonnegative,
    _provenance,
    _read_bounded_text,
    _safe_text,
    _try_read,
    _warning,
)
from resource_probes.cpu import (  # noqa: F401
    APPLE_SYSCTL_QUERY,
    _detect_cpu_inventory,
    _detect_process_cpu_count,
    _effective_cpu,
    _linux_physical_cores,
    _mac_sysctl_values,
    parse_cpu_list,
)
from resource_probes.disk import _detect_disk  # noqa: F401
from resource_probes.memory import _detect_memory, _parse_linux_meminfo  # noqa: F401
from resource_probes.scheduler import (  # noqa: F401
    SLURM_ENV_KEYS,
    _parse_first_repeated_count,
    _parse_slurm_count,
    _parse_slurm_memory,
    detect_scheduler,
)
from resource_probes.snapshot import (  # noqa: F401
    _container_context,
    _observed_at,
    collect_snapshot,
    detect_all_resources,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Report host inventory and effective process limits as deterministic JSON"
        )
    )
    parser.add_argument(
        "--output",
        metavar="FILE.json",
        help=(
            "write a private JSON file in the current directory; default: stdout"
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace an existing explicit output file",
    )
    parser.add_argument(
        "--skip-accelerators",
        action="store_true",
        help="skip bounded accelerator management queries",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.force and not args.output:
        parser.error("--force requires --output")
    try:
        snapshot = collect_snapshot(skip_accelerators=args.skip_accelerators)
        emit_json(snapshot, args.output, force=args.force)
    except ResourceToolError as exc:
        return cli_error(parser, exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
