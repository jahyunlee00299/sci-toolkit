"""Bounded, read-only resource probes behind `scripts/detect_resources.py`.

One module per resource family; `snapshot.collect_snapshot` assembles them:

    core.py               limits, warning/provenance records, bounded text helpers
    commands.py           bounded subprocess runner and the optional psutil import
    cpu.py                host/process CPU counts and the effective CPU capacity
    cgroup.py             cgroup v2 limits (CPU quota, cpuset, memory)
    scheduler.py          Slurm allocation variables (allowlist only)
    memory.py             host/swap memory and the effective memory limit
    disk.py               working-filesystem capacity
    accelerator_parsers.py  nvidia-smi / amd-smi / system_profiler output parsers
    accelerators.py       accelerator probes and visibility upper bounds
    snapshot.py           container hints and `collect_snapshot`

The CLI entry point stays `scripts/detect_resources.py`, which re-exports every
name the single-file script had.
"""
