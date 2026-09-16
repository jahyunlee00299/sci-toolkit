"""Run a dry-run install against a disposable venv and collect failures.

Prefers `uv` when it's on PATH (100x+ faster venv creation, same-process
resolver). Falls back to the standard-library `venv` module + `pip` when
`uv` isn't installed, since most machines this tool will run on don't have
it. Both backends are fail-fast resolvers: a single dry-run call reports
only the first unsatisfiable requirement, so probe_all() drops each failing
package and retries until the resolve succeeds or stops making progress.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ProbeResult:
    ok: bool
    stdout: str
    stderr: str
    resolved_packages: list[str] = field(default_factory=list)
    failing_package: str | None = None


class _Backend(ABC):
    name: str

    @abstractmethod
    def create_venv(self, venv_path: Path, python_version: str) -> subprocess.CompletedProcess:
        ...

    @abstractmethod
    def dry_run_install(self, venv_path: Path, requirements: list[str]) -> subprocess.CompletedProcess:
        ...

    @abstractmethod
    def parse(self, proc: subprocess.CompletedProcess) -> ProbeResult:
        ...


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    # Windows' cp949 console encoding can't decode uv's box-drawing error
    # glyphs (×, ╰, ▶) — found via a live crash, not by inspection.
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


class _UvBackend(_Backend):
    name = "uv"

    _NO_VERSION_RE = re.compile(r"no version of ([A-Za-z0-9_.\-]+)")
    _UNSATISFIABLE_RE = re.compile(
        r"because you require ([A-Za-z0-9_.\-]+)[><=! ]", re.IGNORECASE,
    )
    _ABI_MISMATCH_RE = re.compile(r"([A-Za-z0-9_.\-]+) \(v[^)]+\) has no wheels")

    def create_venv(self, venv_path: Path, python_version: str) -> subprocess.CompletedProcess:
        return _run(["uv", "venv", str(venv_path), "--python", python_version])

    def dry_run_install(self, venv_path: Path, requirements: list[str]) -> subprocess.CompletedProcess:
        return _run(["uv", "pip", "install", "--dry-run", "--python", str(venv_path), *requirements])

    def parse(self, proc: subprocess.CompletedProcess) -> ProbeResult:
        ok = proc.returncode == 0
        resolved = []
        if ok:
            # uv writes the install plan ("+ pkg==ver") to stderr, not stdout.
            resolved = [
                line.strip(" +")
                for line in proc.stderr.splitlines()
                if line.strip().startswith("+")
            ]
        failing = None if ok else self._extract_failing_package(proc.stderr)
        return ProbeResult(ok=ok, stdout=proc.stdout, stderr=proc.stderr,
                            resolved_packages=resolved, failing_package=failing)

    def _extract_failing_package(self, stderr: str) -> str | None:
        for pattern in (self._ABI_MISMATCH_RE, self._NO_VERSION_RE, self._UNSATISFIABLE_RE):
            m = pattern.search(stderr)
            if m:
                return m.group(1)
        return None


class _PipBackend(_Backend):
    """Fallback for machines without uv — stdlib venv + pip, same interface."""
    name = "pip"

    _NO_MATCH_RE = re.compile(
        r"Could not find a version that satisfies the requirement ([A-Za-z0-9_.\-]+)",
    )
    _CONFLICT_RE = re.compile(
        r"Cannot install ([A-Za-z0-9_.\-]+)[><=! ].+ and \1", re.IGNORECASE,
    )
    _USER_REQUESTED_RE = re.compile(r"The user requested ([A-Za-z0-9_.\-]+)")

    def create_venv(self, venv_path: Path, python_version: str) -> subprocess.CompletedProcess:
        # python_version is advisory only here — the fallback uses whatever
        # interpreter is running this process; it cannot fetch other versions
        # the way `uv venv --python X.Y` can.
        return _run([sys.executable, "-m", "venv", str(venv_path)])

    def _venv_python(self, venv_path: Path) -> str:
        if sys.platform == "win32":
            return str(venv_path / "Scripts" / "python.exe")
        return str(venv_path / "bin" / "python")

    def dry_run_install(self, venv_path: Path, requirements: list[str]) -> subprocess.CompletedProcess:
        py = self._venv_python(venv_path)
        return _run([py, "-m", "pip", "install", "--dry-run", *requirements])

    def parse(self, proc: subprocess.CompletedProcess) -> ProbeResult:
        ok = proc.returncode == 0
        resolved = []
        if ok:
            # pip writes "Would install pkg1-ver pkg2-ver ..." to stdout.
            for line in proc.stdout.splitlines():
                if line.startswith("Would install "):
                    resolved = line[len("Would install "):].split()
        # `python -m pip` routes ERROR: lines to stderr; a standalone `pip`
        # executable was observed routing them to stdout instead — check both.
        failing = None if ok else (
            self._extract_failing_package(proc.stderr) or self._extract_failing_package(proc.stdout)
        )
        return ProbeResult(ok=ok, stdout=proc.stdout, stderr=proc.stderr,
                            resolved_packages=resolved, failing_package=failing)

    def _extract_failing_package(self, stdout: str) -> str | None:
        m = self._NO_MATCH_RE.search(stdout)
        if m:
            return m.group(1)
        # Conflict messages name every requested package; take the first one
        # since we only need *a* package to drop and retry.
        m = self._USER_REQUESTED_RE.search(stdout)
        if m:
            return m.group(1)
        return None


def _select_backend() -> _Backend:
    if shutil.which("uv"):
        return _UvBackend()
    return _PipBackend()


def probe_once(requirements: list[str], python_version: str = "3.11",
                backend: _Backend | None = None) -> ProbeResult:
    """Create a throwaway venv and dry-run install the given requirement specs."""
    backend = backend or _select_backend()
    with tempfile.TemporaryDirectory(prefix="compat_check_") as tmp:
        venv_path = Path(tmp) / "venv"
        create = backend.create_venv(venv_path, python_version)
        if create.returncode != 0:
            return ProbeResult(ok=False, stdout=create.stdout, stderr=create.stderr)

        if not requirements:
            return ProbeResult(ok=True, stdout="", stderr="")

        install = backend.dry_run_install(venv_path, requirements)
        return backend.parse(install)


def probe_all(requirements: list[str], python_version: str = "3.11", max_rounds: int = 20) -> dict:
    """Repeatedly probe, dropping each failing package, to surface every failure.

    Returns {"ok": bool, "backend": str, "failures": [{"package": str, "stderr": str}],
    "resolved": [str]}.
    """
    backend = _select_backend()
    remaining = list(requirements)
    failures: list[dict] = []
    seen_failing: set[str] = set()

    for _ in range(max_rounds):
        result = probe_once(remaining, python_version, backend=backend)
        if result.ok:
            return {"ok": not failures, "backend": backend.name,
                     "failures": failures, "resolved": result.resolved_packages}

        combined_output = "\n".join(s for s in (result.stderr, result.stdout) if s)
        pkg = result.failing_package
        if pkg is None or pkg in seen_failing:
            failures.append({"package": pkg or "<unknown>", "stderr": combined_output})
            break

        seen_failing.add(pkg)
        failures.append({"package": pkg, "stderr": combined_output})
        remaining = [r for r in remaining if not r.lower().startswith(pkg.lower())]

    final = probe_once(remaining, python_version, backend=backend)
    return {"ok": False, "backend": backend.name,
             "failures": failures, "resolved": final.resolved_packages}
