"""Environment/packaging checks: Python version, claude CLI, required skill
folders, plugin manifest, hooks config, shell environment for hooks."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from doctor_lib.result import CheckResult, STATUS_FAIL, STATUS_OK, STATUS_WARN, _run_command, _run_python

MIN_PYTHON = (3, 10)

# Skills this distribution actually ships. Missing one of these = FAIL.
REQUIRED_SKILLS = [
    "research-search",
    "manuscript-pipeline",
    "publication-figures",
]

# Skills this package depends on but deliberately does NOT ship: they are
# Anthropic's own, and their LICENSE.txt forbids retaining copies outside
# Anthropic's services. Their absence is expected, so it is reported as a
# notice — not a failure. A hard FAIL here would make `doctor.py` red on a
# correctly-assembled package, and a checker that is always red gets ignored.
# See docs/12_문서스킬_직접_준비하기.md.
EXTERNAL_SKILLS = ["docx", "pdf", "pptx", "xlsx"]

# `doctor.py --quick` (the 10 environment checks, no check_toolkit_selftests)
# measured at ~1.5s locally. install.py imports this rather than hardcoding
# its own timeout, so the two stay in sync if quick mode grows a check.
QUICK_MODE_TIMEOUT_SEC = 60


def check_python_version() -> CheckResult:
    name = "Python version"
    current = sys.version_info[:2]
    version_str = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if current >= MIN_PYTHON:
        return CheckResult(name, STATUS_OK, f"Python {version_str} (>= {'.'.join(map(str, MIN_PYTHON))} required)")
    return CheckResult(
        name, STATUS_FAIL,
        f"Python {version_str} found, but >= {'.'.join(map(str, MIN_PYTHON))} is required",
    )


def check_claude_cli() -> CheckResult:
    name = "claude CLI"
    path = shutil.which("claude")
    if path:
        return CheckResult(name, STATUS_OK, f"found on PATH: {path}")
    return CheckResult(
        name, STATUS_WARN,
        "`claude` CLI not found on PATH (optional, but most workflows expect it)",
    )


def check_required_skills(root: Path) -> CheckResult:
    name = "Required skill folders"
    skills_dir = root / "skills"
    if not skills_dir.is_dir():
        return CheckResult(
            name, STATUS_FAIL,
            f"skills/ directory not found at {skills_dir}",
        )

    missing = []
    present = []
    for skill in REQUIRED_SKILLS:
        skill_dir = skills_dir / skill
        if skill_dir.is_dir():
            present.append(skill)
        else:
            missing.append(skill)

    if missing:
        return CheckResult(
            name, STATUS_FAIL,
            f"{len(missing)}/{len(REQUIRED_SKILLS)} required skill folder(s) missing",
            [f"missing: {s}" for s in missing],
        )

    # Report the externally-supplied skills separately. Present is fine, absent
    # is fine — what matters is that the user knows which state they are in,
    # because it changes what the document workflows can do.
    ext_here = [s for s in EXTERNAL_SKILLS if (skills_dir / s).is_dir()]
    ext_away = [s for s in EXTERNAL_SKILLS if s not in ext_here]
    details = []
    if ext_away:
        details.append("not shipped (Anthropic-owned, see docs/12): "
                       + ", ".join(ext_away))
    if ext_here:
        details.append("found locally: " + ", ".join(ext_here))
    return CheckResult(
        name, STATUS_OK,
        f"all {len(present)} required skill folder(s) present under {skills_dir}",
        details,
    )


def check_plugin_manifest(root: Path) -> CheckResult:
    """Verify .claude-plugin/plugin.json exists and parses as valid JSON.

    Advisory only (OK if present-and-valid, WARN if absent or malformed) —
    older distributions of this package predate the plugin manifest, so its
    absence should not fail the doctor outright.
    """
    name = "Plugin manifest (.claude-plugin/plugin.json)"
    manifest = root / ".claude-plugin" / "plugin.json"
    if not manifest.is_file():
        return CheckResult(
            name, STATUS_WARN,
            "not found — `/plugin install` style packaging will not work "
            "until .claude-plugin/plugin.json is added",
        )
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return CheckResult(name, STATUS_WARN, f"present but failed to parse as JSON: {exc}")

    missing_fields = [f for f in ("name", "version", "description") if not data.get(f)]
    if missing_fields:
        return CheckResult(
            name, STATUS_WARN,
            f"present and parses, but missing field(s): {', '.join(missing_fields)}",
        )
    return CheckResult(
        name, STATUS_OK,
        f"present and valid ({data.get('name')} v{data.get('version')})",
    )


def check_hooks_config(root: Path) -> CheckResult:
    """Verify hooks/hooks.json exists and parses as valid JSON.

    Advisory only (OK if present-and-valid, WARN if absent or malformed) —
    a distribution with no wired hooks still works, it just has no
    mechanical safety net.
    """
    name = "Hooks config (hooks/hooks.json)"
    hooks_json = root / "hooks" / "hooks.json"
    if not hooks_json.is_file():
        return CheckResult(
            name, STATUS_WARN,
            "not found — safety guard hooks (secret/delete/git/cloud-path) are not wired in",
        )
    try:
        data = json.loads(hooks_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return CheckResult(name, STATUS_WARN, f"present but failed to parse as JSON: {exc}")

    if not isinstance(data.get("hooks"), dict) or not data["hooks"]:
        return CheckResult(name, STATUS_WARN, "present and parses, but has no 'hooks' entries")
    n_events = len(data["hooks"])
    return CheckResult(name, STATUS_OK, f"present and valid ({n_events} hook event type(s) configured)")


def check_skill_requirements(root: Path) -> CheckResult:
    """Declared per-skill packages that do not import in this interpreter.

    WARN, never FAIL: a missing optional package limits one skill, it does not
    break the toolkit. The declaration itself (config/skill-requirements.toml)
    is kept honest by tests/test_skill_requirements.py, which fails when the
    scripts and the TOML disagree.
    """
    name = "Skill dependencies (declared packages importable)"
    script = root / "scripts" / "skill_requirements.py"
    toml_path = root / "config" / "skill-requirements.toml"
    if not script.is_file() or not toml_path.is_file():
        return CheckResult(name, STATUS_WARN, "scripts/skill_requirements.py or config/skill-requirements.toml absent — skipped")
    try:
        _rc, out, err = _run_python(root, [str(script), "--missing", "--json"], timeout=60)
        data = json.loads(out)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        return CheckResult(name, STATUS_WARN, f"could not run skill_requirements.py: {exc}")
    missing = data.get("missing") or {}
    if not missing:
        return CheckResult(name, STATUS_OK, "every package a skill's scripts import is available here")
    details = [f"{skill}: pip install {' '.join(pkgs)}" for skill, pkgs in sorted(missing.items())]
    return CheckResult(name, STATUS_WARN,
                       f"{len(missing)} skill(s) need packages not installed here — those skills' scripts "
                       f"will fail until installed (see docs/06)", details)


def check_gitleaks(root: Path) -> CheckResult:
    """Second secret-scan layer: gitleaks with .gitleaks.toml, when the binary is present.

    SENTINEL (doctor_lib/sentinel.py) is a hand-kept pattern set tuned to this
    repo's own incidents; gitleaks brings ~150 vendor rules maintained
    upstream. Absent binary = WARN (the regex layer still ran), findings =
    FAIL, clean = OK. CI runs the same config via .github/workflows/doctor.yml.
    """
    name = "Secret scan (gitleaks, second layer)"
    exe = shutil.which("gitleaks")
    config = root / ".gitleaks.toml"
    if not config.is_file():
        return CheckResult(name, STATUS_WARN, ".gitleaks.toml absent — only the SENTINEL regex layer ran")
    if not exe:
        return CheckResult(name, STATUS_WARN,
                           "gitleaks not on PATH — only the SENTINEL regex layer ran "
                           "(install: https://github.com/gitleaks/gitleaks#installing; CI runs it regardless)")
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        report = Path(td) / "gitleaks.json"
        try:
            # `--source .` (cwd is root) so reported paths are repo-relative;
            # an absolute source made every allowlist anchor miss on CI.
            rc, out, err = _run_command(
                root, [exe, "detect", "--source", ".", "--config", str(config), "--no-git",
                       "--redact", "--exit-code", "1", "--report-format", "json", "--report-path", str(report)],
                timeout=300)
        except (OSError, subprocess.SubprocessError) as exc:
            return CheckResult(name, STATUS_WARN, f"gitleaks could not run: {exc}")
        findings = []
        if report.is_file():
            try:
                findings = json.loads(report.read_text(encoding="utf-8") or "[]")
            except ValueError:
                findings = []
    if rc == 0 and not findings:
        return CheckResult(name, STATUS_OK, f"gitleaks found nothing ({Path(exe).name}, config .gitleaks.toml)")
    if rc == 1 or findings:
        details = [f"{f.get('File')}:{f.get('StartLine')} {f.get('RuleID')}" for f in findings[:12]] \
            or [(out + err).strip()[-300:]]
        return CheckResult(name, STATUS_FAIL, f"gitleaks reported {len(findings) or 'some'} finding(s)", details)
    return CheckResult(name, STATUS_WARN, f"gitleaks exited {rc}", [(out + err).strip()[-300:]])


def check_shell_env(root: Path) -> CheckResult:
    """hooks/hooks.json runs `sh ...` -- if no bash-capable shell is reachable
    (typically: Windows with neither Git Bash nor WSL configured), Claude Code
    falls back to cmd.exe for hook execution, which cannot run .sh files. Every
    hook then fails silently: no secret scan, no dangerous-git guard, no docx
    corruption check. FAIL here means those guards are not actually running,
    even though check_hooks_config() above reports the config as valid --
    a valid hooks.json with an unreachable shell still enforces nothing.
    """
    name = "Shell environment for hooks"
    script = root / "scripts" / "env_detect.py"
    if not script.is_file():
        return CheckResult(name, STATUS_WARN, "scripts/env_detect.py not found — skipped")
    try:
        _rc, out, _err = _run_python(root, [str(script), "--json"], timeout=30)
        r = json.loads(out)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        return CheckResult(name, STATUS_WARN, f"could not run env_detect.py: {exc}")

    if r.get("shell_ok"):
        return CheckResult(
            name, STATUS_OK,
            f"{r.get('shell_source')}: {r.get('shell_path')}",
        )
    return CheckResult(
        name, STATUS_FAIL,
        f"no usable shell found for hooks (os={r.get('os')}) -- hooks will not run",
        r.get("advice", []),
    )
