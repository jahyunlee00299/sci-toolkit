"""Characterization of what `collect_snapshot` does around the values it returns.

host_probe_snapshots.py pins every VALUE `collect_snapshot` returns over ~20 fake
hosts. This module pins the rest of its contract, so the function can be cut into
stages without anyone noticing a change the value golden cannot see:

  * probe order        every file read and every command run, in order, with the
                       keyword arguments the probe passed, for each of those hosts
  * argument hygiene   the caller's `environ` mapping is left untouched
  * default arguments  psutil imported on demand (present and absent), `environ`
                       taken from os.environ, `observed_at` taken from the clock
  * fresh output       two calls never share a mutable object: emptying one result
                       cannot change the next
  * signature         parameter names, kinds, annotations and defaults

The golden file (tests/golden/collect_snapshot.json) was produced from the
`collect_snapshot` that was one 125-line function. Nothing here touches the real
machine's inventory.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import inspect
import json
import os
import re
import sys
from pathlib import Path

import pytest

import host_probe_snapshots as hps
from host_probe_snapshots import (
    GIB, NVIDIA_5COL, OBSERVED, FakeHost, FakePsutil, dr, make_read_text, make_run_command, ok,
)

GOLDEN = hps.GOLDEN
_ISO_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")


# --------------------------------------------------------------------------
# probe-order recorder
# --------------------------------------------------------------------------
class ProbeLog:
    """Ordered record of every file read and command run during one call."""

    def __init__(self):
        self.events: list[list] = []

    def wrap_read(self, read_text):
        def read(path):
            self.events.append(["read", Path(path).as_posix()])
            return read_text(path)
        return read

    def wrap_run(self, run_command):
        def run(argv, **kwargs):
            self.events.append(["run", list(argv), dict(sorted(kwargs.items()))])
            return run_command(argv, **kwargs)
        return run


def _compact(events: list) -> dict:
    """Short logs verbatim; long ones as count + head/tail + a hash of the whole ordered log."""
    digest = hashlib.sha256(json.dumps(events, sort_keys=True).encode()).hexdigest()
    if len(events) <= 40:
        return {"count": len(events), "events": events, "sha256": digest}
    return {"count": len(events), "head": events[:8], "tail": events[-4:], "sha256": digest}


def _install_tracer(monkeypatch, sink: list) -> None:
    """Make detect_resources.collect_snapshot log its probes into `sink`, one entry per call."""
    real = dr.collect_snapshot

    def traced(**kwargs):
        log = ProbeLog()
        environ = kwargs.get("environ")
        before = copy.deepcopy(dict(environ)) if environ is not None else None
        if "read_text" in kwargs:
            kwargs["read_text"] = log.wrap_read(kwargs["read_text"])
        if "run_command" in kwargs:
            kwargs["run_command"] = log.wrap_run(kwargs["run_command"])
        result = real(**kwargs)
        sink.append({"probes": _compact(log.events),
                     "environ_unchanged": before is None or before == dict(environ)})
        return result

    monkeypatch.setattr(dr, "collect_snapshot", traced)


def snapshot_probe_order() -> dict:
    """Probe log of every host scenario that host_probe_snapshots.py builds."""
    sink: list = []
    tracer = pytest.MonkeyPatch()
    host = pytest.MonkeyPatch()
    try:
        _install_tracer(tracer, sink)
        scenarios = hps.snapshot_scenarios(host)
        errors = hps.snapshot_environment_errors(host)
    finally:
        host.undo()
        tracer.undo()
    names = list(scenarios) + list(errors)
    assert len(sink) == len(names), "a scenario made more than one collect_snapshot call"
    return dict(zip(names, sink))


# --------------------------------------------------------------------------
# default-argument branches
# --------------------------------------------------------------------------
def _linux_host(monkeypatch) -> None:
    FakeHost(monkeypatch, system="Linux", machine="x86_64", cpu_count=8, affinity=4,
             process_cpu_count=4, disk=(100 * GIB, 40 * GIB, 60 * GIB), statvfs=(50 * 1024**2, 1024))


def _json(obj):
    return json.loads(json.dumps(obj, sort_keys=True, default=str))


# os.environ carries a Slurm job and a GPU restriction while the default-argument
# scenarios run, so a call that passes its own `environ` - even an empty one - must
# ignore it, whatever the machine running the test happens to export.
PROCESS_ENVIRON = {"SLURM_JOB_ID": "77", "SLURM_CPUS_PER_TASK": "2", "SLURM_MEM_PER_CPU": "1024",
                   "CUDA_VISIBLE_DEVICES": "0", "HOME": "/secret"}


def _clock_case(**kwargs) -> dict:
    """One call that takes observed_at from the clock: the stamp is checked, then masked."""
    first = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    snapshot = dr.collect_snapshot(psutil_module=None, read_text=make_read_text({}),
                                   run_command=make_run_command({}), skip_accelerators=True,
                                   environ={}, **kwargs)
    last = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    stamp = snapshot["observed_at"]
    parsed = dt.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    snapshot["observed_at"] = "<clock>"
    return {
        "iso_utc_seconds": bool(_ISO_UTC.fullmatch(stamp)),
        "within_call_window": first <= parsed <= last,
        "snapshot": _json(snapshot),
    }


def snapshot_defaults(monkeypatch) -> dict:
    out = {}
    _linux_host(monkeypatch)
    monkeypatch.setattr(os, "environ", dict(PROCESS_ENVIRON))
    quiet = dict(read_text=make_read_text({}), run_command=make_run_command({}),
                 skip_accelerators=True, observed_at=OBSERVED, environ={})

    # psutil_module omitted -> imported on demand
    monkeypatch.setitem(sys.modules, "psutil", FakePsutil(physical=4, affinity=[0, 1, 2, 3]))
    out["psutil_imported_on_demand"] = _json(dr.collect_snapshot(**quiet))
    monkeypatch.setitem(sys.modules, "psutil", None)  # makes `import psutil` raise ImportError
    out["psutil_missing_on_demand"] = _json(dr.collect_snapshot(**quiet))

    # environ omitted -> os.environ; environ={} is a real (empty) environment, not "omitted"
    out["environ_from_process_environment"] = _json(dr.collect_snapshot(
        psutil_module=None, read_text=make_read_text({}), observed_at=OBSERVED,
        run_command=make_run_command({dr.NVIDIA_QUERY: ok(NVIDIA_5COL)})))
    out["empty_environ_ignores_process_environment"] = _json(dr.collect_snapshot(
        psutil_module=None, read_text=make_read_text({}), observed_at=OBSERVED, environ={},
        run_command=make_run_command({dr.NVIDIA_QUERY: ok(NVIDIA_5COL)})))

    # observed_at omitted (or empty) -> the clock, UTC, whole seconds
    out["observed_at_from_clock"] = _clock_case()
    out["empty_observed_at_falls_back_to_clock"] = _clock_case(observed_at="")
    return out


# --------------------------------------------------------------------------
# fresh output on every call
# --------------------------------------------------------------------------
def _empty_in_place(obj) -> None:
    if isinstance(obj, dict):
        for value in list(obj.values()):
            _empty_in_place(value)
        obj.clear()
    elif isinstance(obj, list):
        for value in obj:
            _empty_in_place(value)
        obj.clear()


def snapshot_fresh_output(monkeypatch) -> dict:
    _linux_host(monkeypatch)

    def call():
        return dr.collect_snapshot(
            environ={"SLURM_JOB_ID": "5", "SLURM_CPUS_PER_TASK": "2", "CUDA_VISIBLE_DEVICES": "0"},
            psutil_module=FakePsutil(physical=4), observed_at=OBSERVED,
            read_text=make_read_text({}), run_command=make_run_command({dr.NVIDIA_QUERY: ok(NVIDIA_5COL)}))

    first = call()
    reference = _json(first)
    second = call()
    _empty_in_place(first)  # a result that shared a mutable object would damage the next call
    third = call()
    return {
        "two_calls_equal": _json(second) == reference,
        "emptied_result_does_not_leak_into_next_call": _json(third) == reference,
        "snapshot_sha256": hashlib.sha256(json.dumps(reference, sort_keys=True).encode()).hexdigest(),
        "top_level_keys": sorted(reference),
    }


# --------------------------------------------------------------------------
# signature
# --------------------------------------------------------------------------
def _default_repr(default) -> str:
    if default is inspect.Parameter.empty:
        return "<required>"
    if default is dr._AUTO:
        return "<AUTO sentinel>"
    if callable(default):
        return f"<callable {default.__module__}.{default.__qualname__}>"
    return repr(default)


def snapshot_signature() -> dict:
    sig = inspect.signature(dr.collect_snapshot)
    return {
        "parameters": [[p.name, str(p.kind), str(p.annotation), _default_repr(p.default)]
                       for p in sig.parameters.values()],
        "returns": str(sig.return_annotation),
        "module": dr.collect_snapshot.__module__,
    }


def build_all(monkeypatch) -> dict:
    return {
        "probe_order": snapshot_probe_order(),
        "defaults": snapshot_defaults(monkeypatch),
        "fresh_output": snapshot_fresh_output(monkeypatch),
        "signature": snapshot_signature(),
    }
