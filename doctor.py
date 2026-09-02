#!/usr/bin/env python3
"""doctor.py — post-install verification for sci-toolkit.

Flutter/brew-doctor style: DIAGNOSE, do not auto-fix.

Checks:
  1. SHA256SUMS integrity          (skip with OK-note if the manifest is absent)
  2. Python >= 3.10
  3. `claude` CLI reachable on PATH   (WARN, not FAIL, if missing)
  4. Required skill folders present under ./skills
  5. SENTINEL scan — secrets.json / api_key / Tailscale IPs / personal Korean
     names leaked into the distributed tree (distribution safety self-check)

Exit code: 0 if every check is OK or WARN, 1 if any check is FAIL.
Usage:
    python doctor.py            # human-readable table
    python doctor.py --json     # machine-readable JSON report
    python doctor.py --root PATH  # check a tree other than this script's parent
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
from pathlib import Path

# Windows consoles often default stdout/stderr to a legacy codepage (cp949,
# cp1252, ...) that cannot encode en/em-dashes or other punctuation used
# below. Force UTF-8 output so this script behaves the same on every
# platform instead of crashing with UnicodeEncodeError mid-report.
for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name)
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, io.UnsupportedOperation):
            pass

# Make the doctor_lib package importable when doctor.py is loaded by path
# (tests use importlib.util.spec_from_file_location on doctor.py and set
# sys.modules["doctor"] before exec, which does not add this file's own
# directory to sys.path the way a normal `python doctor.py` invocation does).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from doctor_lib.result import (  # noqa: E402
    CheckResult,
    STATUS_OK,
    STATUS_WARN,
    STATUS_FAIL,
    _run_python,
    _classify_selftest_failure,
    overall_status,
)
from doctor_lib.sentinel import (  # noqa: E402
    SCAN_EXCLUDE_DIRS,
    SCAN_EXCLUDE_SUFFIXES,
    MAX_SCAN_FILE_BYTES,
    SENTINEL_FORBIDDEN_FILENAMES,
    SENTINEL_SELF_TEST_FILES,
    RESEARCH_MARKERS,
    RESEARCH_MARKER_ALLOW,
    scan_research_markers,
    TAILSCALE_IP_RE,
    API_KEY_RE,
    PLACEHOLDER_WORDS,
    PLACEHOLDER_LITERALS,
    ENV_VAR_NAME_VALUE_RE,
    ENV_VAR_NAME_WORDS,
    _looks_like_word,
    _split_value,
    _is_placeholder,
    PERSONAL_NAME_PATTERNS,
    PERSONAL_NAME_ALLOWLIST,
    check_sentinel_scan,
)
from doctor_lib.fswalk import _walk_files, _os_walk  # noqa: E402
from doctor_lib.checks_env import (  # noqa: E402
    MIN_PYTHON,
    REQUIRED_SKILLS,
    EXTERNAL_SKILLS,
    QUICK_MODE_TIMEOUT_SEC,
    check_python_version,
    check_claude_cli,
    check_required_skills,
    check_plugin_manifest,
    check_hooks_config,
    check_shell_env,
)
from doctor_lib.checks_repo import (  # noqa: E402
    check_sha256sums,
    _sha256_of,
    check_credentials_divergence,
    _run_test_script,
    check_skill_references,
    check_agents_routing,
    check_connectivity,
)
from doctor_lib.dead_automation import (  # noqa: E402
    _resolve_artifact_paths,
    check_dead_automation,
)
from doctor_lib.selftests import OFFLINE_ENV, _selftest_command, is_pytest_style, run_selftests  # noqa: E402


# --------------------------------------------------------------------------
# Runner / reporting
# --------------------------------------------------------------------------

def run_all_checks(root: Path, quick: bool = False) -> list[CheckResult]:
    """quick=True skips check_toolkit_selftests — that check alone runs 17+
    regression scripts (minutes), which is the wrong cost for a check that
    should run right after every install (see install/install.py's
    post-install doctor call). The fast checks (shell/hooks/sentinel/routing)
    are what actually differ machine-to-machine; the self-test suite verifies
    the package's own code and does not change with the install environment.
    """
    checks = [
        check_sha256sums(root),
        check_python_version(),
        check_claude_cli(),
        check_required_skills(root),
        check_plugin_manifest(root),
        check_hooks_config(root),
        check_shell_env(root),
        check_sentinel_scan(root),
        check_skill_references(root),
        check_agents_routing(root),
        check_credentials_divergence(root),
        check_dead_automation(root),
        check_connectivity(root),
    ]
    if not quick:
        checks.append(check_toolkit_selftests(root))
    return checks


# Test scripts that verify this package's own gates. Each must exit 0.
# A gate whose own test never runs is a gate nobody can trust.
SELF_TEST_SCRIPTS = [
    ("tests/test_doctor_sentinel.py", "secret scan"),
    ("tests/test_body_typo_lint.py", "body typo lint"),
    ("tests/test_doi_verify.py", "DOI verification"),
    ("tests/test_assumption_check.py", "stats assumption check"),
    ("tests/test_install_nondestructive.py", "non-destructive install"),
    ("tests/test_install_doctor_onboarding.py", "post-install doctor auto-run (onboarding)"),
    ("tests/test_capability_diff.py", "capability-loss detector"),
    ("tests/test_hooks_guards.py", "hook guards (block/allow)"),
    ("tests/test_env_guards.py", "environment-mismatch guards"),
    ("tests/test_hook_wiring.py", "hook file <-> chain-runner wiring (orphaned/dangling guards)"),
    ("tests/test_codex_hook_adapter.py", "Codex hook adapter (exit-2 -> block-JSON translation)"),
    ("tests/test_feedback_log.py", "feedback channel"),
    ("tests/test_research_marker_scan.py", "research-marker scanner"),
    ("tests/test_feedback_sanitize.py", "feedback sanitize gate"),
    ("tests/test_si_institutional.py", "SI fetch + institutional links"),
    ("tests/test_checksums_manifest.py", "manifest portability (untracked/EOL)"),
    ("tests/test_doc_counts.py", "documented counts match reality"),
    ("tests/test_vector_integrity.py", "SnapGene vectors still parse"),
    ("tests/test_env_detect.py", "shell-env detection (Windows Git-Bash/WSL branches)"),
    ("skills/biorxiv-database/tests/test_preprint_search.py", "preprint route retrieval (F2/F3 disk-artifact)"),
    ("tests/test_credentials_divergence.py", "credentials.json / secrets.json divergence detector"),
    ("tests/test_skill_drift.py", "toolkit vs authoring-tree skill drift detector"),
    ("tests/test_connectors.py", "REST connectors (dry-run isolation, --write gate, token gating)"),
    ("tests/test_service_routing.py", "service/skill routing (connector-silent steering, dead skill refs)"),
    ("tests/test_adopted_discipline_skills.py", "adopted discipline skills keep their substance"),
    ("tests/test_development_discipline.py", "spec-first/test-first discipline wiring + core rules"),
    ("tests/test_spec_driven_workflow.py", "spec-driven workflow (4 phases, templates, attribution, wiring)"),
    ("tests/test_dead_automation.py", "dead-automation detector (artifact freshness)"),
    ("tests/test_adopted_skills.py", "adopted-skill contract (upstream attribution, model-neutral, no vendored deps)"),
    ("tests/test_connectivity.py", "tool connectivity (orphan/untested ratchet, ledger wired-by paths)"),
    ("tests/test_tool_cli_smoke.py", "standalone tool smoke (HPLC parser, primer structure, variant filter, CLIs)"),
    ("tests/test_doctor_selftest_verdicts.py", "doctor self-test verdicts (upstream outage = WARN, broken tool = FAIL)"),
    ("tests/test_sci_http.py", "shared HTTP retry policy (429/5xx retried, 4xx not, Retry-After, backoff)"),
    ("tests/test_skill_sizes.py", "SKILL.md size ratchet (24 KiB cap; grandfathered files may only shrink)"),
    # A directory entry is a pytest suite: run with pytest, not as a script.
    # The root pytest.ini disables import-collection (tests/ are scripts), so
    # the suite passes its own python_files pattern back in.
    ("skills/web-scraping/tests", "web-scraping pytest suite (EZproxy scope, PDF pipeline, target safety, GitHub failure surfacing)"),
]


def check_toolkit_selftests(root: Path) -> CheckResult:
    """Run the regression tests for this package's own verification tools.

    Reads the module-global SELF_TEST_SCRIPTS at call time (not at import
    time): tests monkeypatch `doctor.SELF_TEST_SCRIPTS` and then call
    `doctor.check_toolkit_selftests(root)` to exercise outage/broken/mixed
    verdicts without touching the real suite.
    """
    return run_selftests(root, SELF_TEST_SCRIPTS)


def print_human_table(results: list[CheckResult], root: Path) -> None:
    icon = {STATUS_OK: "[OK]  ", STATUS_WARN: "[WARN]", STATUS_FAIL: "[FAIL]"}
    name_width = max((len(r.name) for r in results), default=20)

    print(f"sci-toolkit doctor — checking {root}")
    print("-" * 70)
    for r in results:
        print(f"{icon[r.status]} {r.name.ljust(name_width)}  {r.message}")
        for d in r.details:
            print(f"         - {d}")
    print("-" * 70)

    status = overall_status(results)
    n_ok = sum(1 for r in results if r.status == STATUS_OK)
    n_warn = sum(1 for r in results if r.status == STATUS_WARN)
    n_fail = sum(1 for r in results if r.status == STATUS_FAIL)
    print(f"Summary: {n_ok} OK, {n_warn} WARN, {n_fail} FAIL")

    if status == STATUS_FAIL:
        print("Result: FAIL — fix the issues above (this tool diagnoses, it does not auto-fix).")
    elif status == STATUS_WARN:
        print("Result: PASS with warnings.")
    else:
        print("Result: PASS.")


def print_json_report(results: list[CheckResult], root: Path) -> None:
    status = overall_status(results)
    report = {
        "root": str(root),
        "status": status,
        "exit_code": 0 if status != STATUS_FAIL else 1,
        "checks": [r.to_dict() for r in results],
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="doctor.py",
        description="sci-toolkit post-install doctor: diagnose, don't auto-fix. "
                     "Beginner-friendly diagnostics for a fresh install.",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="emit a machine-readable JSON report instead of the human table",
    )
    parser.add_argument(
        "--root", type=Path, default=None,
        help="root directory to check (default: this script's own directory)",
    )
    parser.add_argument(
        "--quick", action="store_true",
        help="skip the toolkit self-test suite (minutes) -- environment-only "
             "checks (shell/hooks/sentinel/routing). Used by install.py's "
             "post-install check; run without --quick for the full gate.",
    )
    parser.add_argument(
        "--offline", action="store_true",
        help="keep every self-test off the network (sets SCI_TOOLKIT_OFFLINE=1 for "
             "the subprocesses): script probes print SKIP with the reason, "
             "pytest-style tests marked 'network' are deselected. Use on a "
             "machine with no internet or when an upstream API is down.",
    )
    args = parser.parse_args(argv)
    if args.offline:
        os.environ[OFFLINE_ENV] = "1"

    root = (args.root or Path(__file__).resolve().parent).resolve()

    results = run_all_checks(root, quick=args.quick)

    if args.json:
        print_json_report(results, root)
    else:
        print_human_table(results, root)

    return 0 if overall_status(results) != STATUS_FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
