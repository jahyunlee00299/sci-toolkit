"""Repo-integrity checks: checksums manifest, credentials-store divergence,
skill/agent reference resolution, and tool connectivity."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from doctor_lib.result import CheckResult, STATUS_FAIL, STATUS_OK, STATUS_WARN, _run_python


def check_sha256sums(root: Path) -> CheckResult:
    """Verify SHA256SUMS manifest if one exists at the project root.

    A manifest is expected to contain lines like:
        <hexdigest>  <relative/path>
    (the format produced by `sha256sum` / `shasum -a 256`).
    """
    name = "SHA256SUMS integrity"
    manifest = root / "SHA256SUMS"
    if not manifest.is_file():
        # WARN, not OK. This check exists to answer "did this copy arrive
        # intact"; with no manifest that question cannot be answered, and
        # reporting OK means a copy that lost its manifest in transit — the
        # exact failure the manifest guards against — scores full marks
        # (measured 260807: 10 OK / 0 FAIL on a tree with SHA256SUMS removed).
        # It stays WARN rather than FAIL because a single skill folder copied
        # out of the package legitimately has no manifest.
        return CheckResult(
            name, STATUS_WARN,
            "no SHA256SUMS manifest — integrity of this copy cannot be "
            "verified. If this is the full package, the manifest is missing; "
            "regenerate with `python scripts/make_checksums.py --apply`.",
        )

    mismatches: list[str] = []
    missing: list[str] = []
    checked = 0
    try:
        lines = manifest.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return CheckResult(name, STATUS_FAIL, f"could not read SHA256SUMS: {exc}")

    for lineno, line in enumerate(lines, start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Accept both "<hash>  <path>" and "<hash> *<path>" (binary mode marker)
        parts = line.split(None, 1)
        if len(parts) != 2:
            mismatches.append(f"line {lineno}: unparsable entry: {line!r}")
            continue
        expected_hex, rel_path = parts
        rel_path = rel_path.lstrip("*").strip()
        target = root / rel_path
        if not target.is_file():
            missing.append(rel_path)
            continue
        actual_hex = _sha256_of(target)
        checked += 1
        if actual_hex.lower() != expected_hex.lower():
            mismatches.append(f"{rel_path}: expected {expected_hex[:12]}…, got {actual_hex[:12]}…")

    details = []
    if missing:
        details.append(f"{len(missing)} file(s) listed in manifest are missing: "
                        + ", ".join(missing[:10]) + (" ..." if len(missing) > 10 else ""))
    if mismatches:
        details.extend(mismatches[:20])
        if len(mismatches) > 20:
            details.append(f"... and {len(mismatches) - 20} more mismatch(es)")

    if mismatches or missing:
        return CheckResult(
            name, STATUS_FAIL,
            f"{len(mismatches)} mismatch(es), {len(missing)} missing file(s) "
            f"out of {checked + len(missing)} manifest entries",
            details,
        )
    return CheckResult(name, STATUS_OK, f"{checked} file(s) verified against SHA256SUMS")


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def check_credentials_divergence(root: Path) -> CheckResult:
    """Warn when tokens registered in this package's credentials.json are
    invisible to a pre-existing ~/.claude/scripts/ automation setup.

    [260810] Filed by an actual installer (issue #3): register_token.py makes
    a token work for scripts/connectors/*, but a coexisting ~/.claude install
    has its own shared secrets store with different key names (notion.token
    vs NOTION_TOKEN) that scripts/connectors/ never touches and vice versa.
    Neither side is broken on its own — doctor.py passed 11/11 while roughly
    30 pre-existing scripts silently failed, because this divergence was
    never checked. This is a WARN, not a FAIL: not having a ~/.claude/
    install at all is the common case and entirely fine.

    [260822] The shared store moved from ~/.claude/secrets.json to
    ~/.secrets/secrets.json, so a tool-owned directory can no longer claim it.
    Both are probed, newest location first: an installer who has not migrated
    yet still gets a correct answer, and one who has is no longer told the
    store "does not exist" when it plainly does.
    """
    name = "Credentials store divergence"
    creds_path = root / "config" / "credentials.json"
    if not creds_path.is_file():
        return CheckResult(name, STATUS_OK, "no config/credentials.json yet — nothing to check")

    try:
        creds = json.loads(creds_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return CheckResult(name, STATUS_WARN, f"could not read config/credentials.json: {exc}")

    # service -> (credentials.json section, shared secrets-store key)
    # Only services with a plausible ~/.claude/ counterpart are checked —
    # mail/google have no single well-known secrets.json key to compare against.
    SERVICE_KEY_MAP = {
        "notion": "NOTION_TOKEN",
        "asana": "ASANA_PAT",
        "github": "GITHUB_PAT",
    }

    registered = []
    for service in SERVICE_KEY_MAP:
        section = creds.get(service) or {}
        token = section.get("token", "")
        # "ENV:VAR" placeholders and the literal example string are not real registrations.
        if token and not token.startswith("ENV:"):
            registered.append(service)
        elif token.startswith("ENV:"):
            import os
            if os.environ.get(token[4:]):
                registered.append(service)

    if not registered:
        return CheckResult(name, STATUS_OK, "no services registered in credentials.json yet")

    # Newest location first. ~/.claude/secrets.json is the pre-260816 path and
    # is kept only so an unmigrated installer still gets a correct answer.
    SECRETS_CANDIDATES = (
        Path("~/.secrets/secrets.json").expanduser(),
        Path("~/.claude/secrets.json").expanduser(),
    )
    secrets_path = next((c for c in SECRETS_CANDIDATES if c.is_file()), None)
    if secrets_path is None:
        looked = " or ".join(str(c) for c in SECRETS_CANDIDATES)
        return CheckResult(
            name, STATUS_WARN,
            f"credentials.json has {', '.join(registered)} registered, but no "
            f"shared secrets store was found ({looked}) — any pre-existing "
            f"~/.claude/scripts/ automation that expects that file cannot see "
            f"these tokens (they use different key names: notion.token vs "
            f"NOTION_TOKEN, asana.token vs ASANA_PAT, github.token vs GITHUB_PAT). "
            f"If you don't have a ~/.claude/ automation setup, this is expected "
            f"and safe to ignore.",
        )

    try:
        secrets = json.loads(secrets_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        secrets = {}

    missing_in_secrets = [
        s for s in registered if not secrets.get(SERVICE_KEY_MAP[s])
    ]
    if missing_in_secrets:
        pairs = ", ".join(f"{s}.token -> {SERVICE_KEY_MAP[s]}" for s in missing_in_secrets)
        return CheckResult(
            name, STATUS_WARN,
            f"{', '.join(missing_in_secrets)} registered in credentials.json "
            f"but missing from {secrets_path} ({pairs}) — scripts "
            f"outside scripts/connectors/ that read secrets.json directly "
            f"will not see these tokens.",
        )
    return CheckResult(name, STATUS_OK,
                        f"{', '.join(registered)} present in both credentials.json and secrets.json")


def _run_test_script(root: Path, rel: str, name: str,
                     ok_msg: str, fail_msg: str) -> CheckResult:
    """Delegate a check to a test script so the rule lives in exactly one place."""
    script = root / rel
    if not script.is_file():
        return CheckResult(name, STATUS_WARN, f"{rel} not present — skipped")
    try:
        rc, stdout, stderr = _run_python(root, [str(script)], timeout=180)
    except (OSError, subprocess.SubprocessError) as exc:
        return CheckResult(name, STATUS_WARN, f"could not run {rel}: {exc}")

    out = stdout + stderr
    # The script's own verdict is its last non-empty stdout line ("ALL PASS —
    # every reference exists", "Checked N reference(s) ..."). An earlier
    # version matched two Korean words here; after the 2026-08-28 English
    # translation nothing printed them and the summary silently fell back to
    # ok_msg for every run.
    summary = next((ln.strip() for ln in reversed(stdout.splitlines()) if ln.strip()), "")
    if rc == 0:
        return CheckResult(name, STATUS_OK, summary or ok_msg)
    details = [ln for ln in out.splitlines() if ln.startswith("  ") and ln.strip()][:20]
    return CheckResult(name, STATUS_FAIL, fail_msg, details)


def check_skill_references(root: Path) -> CheckResult:
    """Every file/skill a SKILL.md tells the user to use must actually exist.

    The most common way a distributed package fails is not a code bug but a
    dead pointer: the docs say "run `scripts/foo.py`" or "use the `bar` skill"
    and neither ships. Delegates to tests/test_skill_references.py so the rule
    lives in exactly one place.
    """
    return _run_test_script(
        root, "tests/test_skill_references.py", "Skill reference integrity",
        ok_msg="all skill references resolve",
        fail_msg="dead reference(s) found — docs point at files/skills that do not ship")


def check_agents_routing(root: Path) -> CheckResult:
    """AGENTS.md §0 is the agent's entry point — it must not point at nothing.

    An agent follows that table literally. A skill or script named there but
    absent from the package produces either a hard failure or, worse, an
    invented substitute.
    """
    return _run_test_script(
        root, "tests/test_agents_routing.py", "AGENTS.md routing table",
        ok_msg="routing table resolves",
        fail_msg="AGENTS.md §0 points at files/skills that do not ship")


def check_connectivity(root: Path) -> CheckResult:
    """Every shipped tool must be reachable (a doc, importer or hook leads to it)
    and should be exercised (a test or doctor names it).

    FAIL = an ORPHAN (nothing points at the file) or a dangling ``wired-by:``
    path in the connectivity ledger. WARN = reachable tools with no test; the
    ratchet that stops that number from growing lives in
    tests/test_connectivity.py, not here, so doctor reports and the test gates.
    """
    name = "Tool connectivity (orphans / untested)"
    script = root / "scripts" / "connectivity_check.py"
    if not script.is_file():
        return CheckResult(name, STATUS_WARN, "scripts/connectivity_check.py not present — skipped")
    try:
        _rc, stdout, stderr = _run_python(root, [str(script), "--root", str(root), "--json"], timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        return CheckResult(name, STATUS_WARN, f"could not run connectivity_check.py: {exc}")
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return CheckResult(name, STATUS_FAIL, "connectivity_check.py emitted no JSON",
                           [(stdout + stderr).strip()[-300:]])

    details = [f"ORPHAN (nothing leads here): {p}" for p in data["orphans"]]
    details += [f"ledger wired-by path missing: {p}" for p in data["dangling_ledger_paths"]]
    if details:
        return CheckResult(name, STATUS_FAIL,
                           f"{data['orphan_count']} orphan tool(s), "
                           f"{len(data['dangling_ledger_paths'])} dangling ledger path(s) "
                           f"— name it in a doc/SKILL.md or retire it", details)
    if data["untested_count"]:
        return CheckResult(name, STATUS_WARN,
                           f"{data['tool_count']} tools reachable; {data['untested_count']} have no test "
                           f"(ratchet in tests/test_connectivity.py) — "
                           f"`python scripts/connectivity_check.py` lists them")
    return CheckResult(name, STATUS_OK,
                       f"{data['tool_count']} tools reachable and tested; "
                       f"{data['ledger_wired_by_count']} ledger wired-by path(s) exist")
