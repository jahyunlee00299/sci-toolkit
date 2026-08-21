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
import hashlib
import io
import json
import re
import shutil
import sys
from dataclasses import dataclass, field
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

# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

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

# Directories we never want to walk into during the sentinel scan (huge,
# irrelevant, or already-excluded-from-distribution paths).
SCAN_EXCLUDE_DIRS = {
    ".git",
    "__pycache__",
    ".cache",
    "node_modules",
    ".venv",
    "venv",
    ".mypy_cache",
    ".pytest_cache",
}

# Only scan text-ish files; skip large/binary formats to keep this fast.
SCAN_EXCLUDE_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg",
    ".pdf", ".zip", ".tar", ".gz", ".7z", ".whl",
    ".pyc", ".pyo", ".so", ".dll", ".exe", ".bin",
    ".sqlite", ".sqlite3", ".db",
}

MAX_SCAN_FILE_BYTES = 5 * 1024 * 1024  # 5 MB — skip anything bigger

# `doctor.py --quick` (the 10 environment checks, no check_toolkit_selftests)
# measured at ~1.5s locally. install.py imports this rather than hardcoding
# its own timeout, so the two stay in sync if quick mode grows a check.
QUICK_MODE_TIMEOUT_SEC = 60

# Filenames that are an automatic FAIL if found anywhere in the tree,
# regardless of content (a real secrets store should never ship).
SENTINEL_FORBIDDEN_FILENAMES = {
    "secrets.json",
    ".git-credentials",
}

# This scanner's own test fixtures carry intentionally fake credentials
# (see tests/test_doctor_sentinel.py) — scanning them would always "find" a leak.
# 탐지기의 **계약**을 정의하는 파일들. 여기 담긴 문자열은 유출이 아니라
# "이런 것을 잡아야 한다"는 명세이므로 SENTINEL 스캔에서 제외한다.
# 제외하지 않으면 유출을 막는 테스트가 스스로 유출로 잡혀, 결국 케이스를
# 지우는 쪽으로 압력이 생긴다 — 그 순간 탐지기가 무력해진다.
SENTINEL_SELF_TEST_FILES = {
    "test_doctor_sentinel.py",
    "test_research_marker_scan.py",
    "test_feedback_sanitize.py",
}

# ── research-marker scan ────────────────────────────────────────────────────
# A SECOND, separate axis from the secret scan above. Secrets are credentials;
# these are *unpublished research contents* — enzyme variants, rate laws,
# private repo names. v1.2.0 shipped with RoGDH / LpNoxV / a full cascade ODE
# still in it while claiming in writing that they had been removed, because the
# SENTINEL scan only ever looked for credentials and Korean personal names.
# This axis closes that hole. Contract + the actual leaked strings:
# tests/test_research_marker_scan.py — do not delete those cases.
#
# The hard part is separating a project-specific token from ordinary teaching
# content: `Vmax,XR` must be caught while `Vmax` must not, `RoGDH` while
# `*Ec*XylA` (a generic naming-rule example) must not. Every pattern below is
# therefore anchored to a *specific* enzyme/substrate/repo identifier, never to
# a bare biochemical symbol.
RESEARCH_MARKERS = [
    # Species-prefixed enzyme abbreviations actually used in the unpublished work.
    # Two-letter genus prefix + a specific enzyme family, optionally italic-marked.
    ("enzyme abbreviation",
     re.compile(r"\*?\b(?:Ro|Rs|Bs|Lp|Ao|Go|Ps|Sc)\*?(?:GDH|Gdh|NoxV?|SucP|FDH|Fdh|GRE3)\b")),
    # Engineered variant naming (scgre3, GRE3 variants)
    ("engineered variant", re.compile(r"\b(?:sc)?gre3\b", re.IGNORECASE)),
    # Rate-law symbols carrying a *project enzyme* subscript. The subscript set is
    # deliberately limited to the unpublished cascade's enzymes — a generic
    # cofactor subscript like `kdeg,NADH` (NADH degradation constant) appears in
    # any redox system and must NOT trip this, or the scanner blocks its own
    # sanitized replacement text.
    ("rate law with enzyme subscript",
     re.compile(r"\bv(?:XR|GDH|NOX|FDH)\b"
                r"|\b(?:Vmax|Km|KmA|KmB|KiA|KiB|kdeg)\s*,\s*(?:XR|GDH|NOX|FDH)\b"
                r"|\bvsub\(\s*['\"](?:XR|GDH|NOX|FDH)['\"]\s*\)")),
    # The specific empirical correlation from the unpublished SI. `kLa` on its own
    # is standard fermentation engineering and `Eq. S5` on its own is just an SI
    # cross-reference style — neither is secret. What identifies the project is
    # the *correlation itself* (kLa as a power law in stirrer speed).
    ("SI correlation",
     re.compile(r"\bkLa\s*=\s*(?:α|alpha)\s*[·*]\s*N|\bkLa\b[^\n]{0,40}\bN\s*\^\s*(?:β|beta)")),
    # Substrate/product of the unpublished cascade. NOTE: D-galactose and D-Gal
    # are NOT here — it is a commodity sugar used across the literature, and the
    # skills legitimately use it to teach abbreviation consistency. What is
    # unpublished is the *target rare sugar* and the specific conversions.
    ("unpublished substrate",
     re.compile(r"\btagatose\b|\b타가토스\b|\bL-ribose\b|\bgalactitol\b", re.IGNORECASE)),
    # Private repository / project names.
    ("private repo name",
     re.compile(r"\bUDH_Clustering\b|\bKinetic-modeling\b|\bPeakPicker\b"
                r"|\bbiosteam-tagatose\b|\bmanuscript-figures\b")),
    # Real figure-folder naming from the manuscript repo (F_figS2_<name>_<measure>).
    ("manuscript figure path", re.compile(r"\bF_fig[S]?\d+[a-z]?_\w+")),
]

# Generic biochemistry that must never trip the scanner. Checked first: if the
# match is one of these in its entirety, it is ordinary teaching content.
# Over-blocking gets a scanner switched off, and a switched-off scanner is worth
# nothing — so this list is as important as the patterns above.
RESEARCH_MARKER_ALLOW = re.compile(
    r"^(?:NAD\+?|NADH|NADP\+?|NADPH|ATP|ADP|AMP|FAD|kcat|Km|Vmax|Ki|kLa_generic)$",
    re.IGNORECASE,
)


def scan_research_markers(text: str) -> list[str]:
    """Return labels of unpublished-research markers found in `text`.

    Empty list means clean. Used by the SENTINEL check and by the standalone
    sanitization sweep; kept as a plain function so tests can call it directly
    with a single line of text.
    """
    found: list[str] = []
    for label, rx in RESEARCH_MARKERS:
        for m in rx.finditer(text):
            if RESEARCH_MARKER_ALLOW.match(m.group(0).strip()):
                continue
            entry = f"{label}: {m.group(0).strip()}"
            if entry not in found:
                found.append(entry)
    return found

# Content patterns considered a leaked secret / private identifier.
# Each entry: (label, compiled regex)
TAILSCALE_IP_RE = re.compile(r"\b100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}\b")
API_KEY_RE = re.compile(
    r"""
    (?:api[_-]?key|apikey|secret[_-]?key|access[_-]?token)
    \s*[:=]\s*
    ["']?[A-Za-z0-9_\-\.]{16,}["']?
    | sk-[A-Za-z0-9]{20,}
    | ghp_[A-Za-z0-9]{30,}
    | gho_[A-Za-z0-9]{30,}
    | github_pat_[A-Za-z0-9_]{20,}
    | xox[baprs]-[A-Za-z0-9-]{10,}
    | AKIA[0-9A-Z]{16}
    | AIzaSy[A-Za-z0-9_\-]{20,}
    """,
    re.IGNORECASE | re.VERBOSE,
)
# The last four were missing until 2026-08-08, and the gap was between layers
# rather than inside one: hooks/secret_scan_guard.sh already carried all of
# them, so a live tool call pasting an AWS or Google key was blocked — but this
# scanner, whose whole job is the last look before distribution, walked past
# the same key sitting in a file. Measured: a bare AKIA…, AIzaSy…, and
# github_pat_… all read as clean here while the guard blocked each one.
# The vendor prefixes are specific enough that widening this costs no false
# positives (MUST_NOT_BLOCK in tests/test_doctor_sentinel.py pins that).

# Obvious non-secret placeholders. These are matched against the VALUE side of
# the assignment only, and each must be a whole hyphen/underscore-delimited word
# — NOT a bare substring. A substring test lets a real key slip through the
# moment it happens to contain the marker (`api_key="…-project1-secret-…"`),
# which is exactly the kind of hole this scanner exists to catch.
PLACEHOLDER_WORDS = frozenset({
    "your", "yours", "yourkey", "yourapikey",
    "api", "key", "keys", "apikey", "token", "secret", "here",
    "example", "examples", "placeholder", "changeme", "dummy", "fake",
    "test", "sample", "replace", "insert", "todo", "xxx", "xxxx",
    "openrouter", "parallel", "perplexity",
})
# Whole-match markers: if the matched text contains one of these it is
# unambiguously documentation/code, not a literal credential.
PLACEHOLDER_LITERALS = (
    "...", "<", "os.environ", "getenv", "your.email", "your-handle",
)

# A "value" that is just the NAME of an environment variable is not a secret:
#   api_key="PARALLEL_API_KEY"  /  api_key = OPENROUTER_API_KEY
# Must stay NARROW: a credential like AKIA5FJ39DKS02MXZQ7B is also all-caps, so
# require underscore-separated words AND at least one credential-ish word. A
# real key is a single opaque run of characters, not KEY-ish English words.
ENV_VAR_NAME_VALUE_RE = re.compile(
    r"""["']?
        (?=[A-Z0-9_]*_)                    # must contain an underscore
        [A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+      # SCREAMING_SNAKE_CASE
        ["']?\s*$""",
    re.VERBOSE,
)
ENV_VAR_NAME_WORDS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "AUTH")


def _looks_like_word(segment: str) -> bool:
    """True if this reads like an English identifier word, not an opaque token.

    Environment-variable names are made of words (`OPENROUTER`, `API`, `KEY`).
    Credentials contain high-entropy runs (`9F3AB21C77DE40B8`, `A83F2C9D`).
    The discriminator that survives both: a real word has no digits in it and
    is not a long hex-looking run.
    """
    if not segment:
        return False
    if any(ch.isdigit() for ch in segment):
        return False          # `TOKEN9F3AB` / `V1ABCD` — not a plain word
    if len(segment) > 20:
        return False          # implausibly long for a name segment
    return segment.isalpha()


def _split_value(matched_text: str) -> str:
    """Return the value side of `name = value` / `name: value`, else the whole match."""
    for sep in ("=", ":"):
        head, found, tail = matched_text.partition(sep)
        if found:
            return tail.strip().strip("\"'")
    return matched_text.strip().strip("\"'")


def _is_placeholder(matched_text: str) -> bool:
    low = matched_text.lower()

    # A match that spans a newline is the regex having run past the end of the
    # assignment and swallowed following code (e.g. `API_KEY='):\n  api_key =
    # line.split('`). The literal value ended at the line break, so this is a
    # parsing artifact, not a credential.
    if "\n" in matched_text or "\r" in matched_text:
        return True

    if any(lit in low for lit in PLACEHOLDER_LITERALS):
        return True

    value = _split_value(matched_text)
    if not value:
        return True

    # Strip a known vendor prefix (`sk-or-v1-`, `sk-`, `ghp_`, `xoxb-`) before
    # judging the words: the prefix is boilerplate in both real keys and docs,
    # so what matters is whether anything OPAQUE follows it.
    body = re.sub(r"^(?:sk-or-v\d+-|sk-|ghp_|gho_|xox[baprs]-|ya29\.)", "",
                  value, flags=re.IGNORECASE)
    if not body:
        return True

    # Split the value into words on the separators placeholders actually use.
    words = [w for w in re.split(r"[-_./\s]+", body.lower()) if w]
    if not words:
        return True

    # Placeholder only if EVERY word is a known filler word. One opaque token
    # (a real key fragment) anywhere in the value disqualifies it, so
    # "your-api-key-here" is a placeholder but "my-project1-a83f2c9d" is not.
    #
    # A short digit run is filler ("key1", "v2"); a LONG one is a credential.
    # `secret_key = "123456789012345678901234567890"` is a real leak, and an
    # unconditional isdigit() exemption waved exactly that through.
    def _filler(w):
        return w in PLACEHOLDER_WORDS or (w.isdigit() and len(w) <= 4)

    if all(_filler(w) for w in words):
        return True

    # `api_key = SOME_ENV_NAME` — the value is a variable name, not a key.
    # Narrow: EVERY segment must look like an English-ish word, otherwise an
    # opaque token is riding along (`AUTH_TOKEN_9F3AB21C77DE40B8` is a leak,
    # not a variable name).
    if ENV_VAR_NAME_VALUE_RE.match(value) and any(
            w in value.upper() for w in ENV_VAR_NAME_WORDS):
        segments = [s for s in value.strip("\"'").split("_") if s]
        if all(_looks_like_word(s) for s in segments):
            return True

    return False

# Personal Korean given/full names to guard against (edit to match your own
# distribution's real risk list — kept generic/placeholder here on purpose).
PERSONAL_NAME_PATTERNS = [
    re.compile(r"[가-힣]{2,4}\s*(?:박사|교수|선생님)"),  # "○○○ 박사" style honorifics
]

# Words that end in an honorific but name a ROLE, not a person. Writing
# "지도교수에게 물어보세요" in a guide is not a leaked name, and flagging it
# trains people to ignore this check — which is worse than not having it.
PERSONAL_NAME_ALLOWLIST = frozenset({
    "지도교수", "담당교수", "책임교수", "주임교수", "겸임교수", "객원교수",
    "부교수", "정교수", "조교수", "석좌교수", "명예교수",
    "지도박사", "담당박사", "박사후연구원",
    "담당선생님", "학과선생님",
})


# --------------------------------------------------------------------------
# Result model
# --------------------------------------------------------------------------

STATUS_OK = "OK"
STATUS_WARN = "WARN"
STATUS_FAIL = "FAIL"

_STATUS_RANK = {STATUS_OK: 0, STATUS_WARN: 1, STATUS_FAIL: 2}


@dataclass
class CheckResult:
    name: str
    status: str
    message: str
    details: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "details": self.details,
        }


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------

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
    has its own ~/.claude/secrets.json with different key names (notion.token
    vs NOTION_TOKEN) that scripts/connectors/ never touches and vice versa.
    Neither side is broken on its own — doctor.py passed 11/11 while roughly
    30 pre-existing scripts silently failed, because this divergence was
    never checked. This is a WARN, not a FAIL: not having a ~/.claude/
    install at all is the common case and entirely fine.
    """
    name = "Credentials store divergence"
    creds_path = root / "config" / "credentials.json"
    if not creds_path.is_file():
        return CheckResult(name, STATUS_OK, "no config/credentials.json yet — nothing to check")

    try:
        creds = json.loads(creds_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return CheckResult(name, STATUS_WARN, f"could not read config/credentials.json: {exc}")

    # service -> (credentials.json section, ~/.claude/secrets.json key)
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

    secrets_path = Path("~/.claude/secrets.json").expanduser()
    if not secrets_path.is_file():
        return CheckResult(
            name, STATUS_WARN,
            f"credentials.json has {', '.join(registered)} registered, but "
            f"~/.claude/secrets.json does not exist — any pre-existing "
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
            f"but missing from ~/.claude/secrets.json ({pairs}) — scripts "
            f"outside scripts/connectors/ that read secrets.json directly "
            f"will not see these tokens.",
        )
    return CheckResult(name, STATUS_OK,
                        f"{', '.join(registered)} present in both credentials.json and secrets.json")


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
    import subprocess
    script = root / "scripts" / "env_detect.py"
    if not script.is_file():
        return CheckResult(name, STATUS_WARN, "scripts/env_detect.py not found — skipped")
    try:
        proc = subprocess.run(
            [sys.executable, str(script), "--json"], cwd=str(root),
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=30)
        r = json.loads(proc.stdout)
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


def check_sentinel_scan(root: Path) -> CheckResult:
    """Distribution safety self-check: make sure no secrets / private
    identifiers leaked into the tree that is about to be shipped.
    """
    name = "SENTINEL scan (secrets / private data)"
    findings: list[str] = []

    # doctor.py itself contains the detection regexes as literals; never scan it.
    self_name = Path(__file__).name

    for path in _walk_files(root):
        rel = path.relative_to(root)

        # 1) Forbidden filenames, regardless of content.
        if path.name.lower() in SENTINEL_FORBIDDEN_FILENAMES:
            findings.append(f"{rel}: forbidden filename '{path.name}' present in tree")
            continue

        if path.name == self_name:
            continue
        # This scanner's own regression fixtures deliberately contain fake
        # credentials so the must-block half of the test can assert on them.
        if path.name in SENTINEL_SELF_TEST_FILES:
            continue
        if path.suffix.lower() in SCAN_EXCLUDE_SUFFIXES:
            continue
        try:
            if path.stat().st_size > MAX_SCAN_FILE_BYTES:
                continue
        except OSError:
            continue

        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        # Scan EVERY match, not just the first: a file whose first hit is a
        # documented placeholder can still carry a real key further down.
        if any(not _is_placeholder(m.group(0)) for m in API_KEY_RE.finditer(text)):
            findings.append(f"{rel}: possible API key / secret token pattern")
        if TAILSCALE_IP_RE.search(text):
            findings.append(f"{rel}: possible Tailscale IP (100.64.0.0/10) literal")
        hardcoded_re = re.compile(r"api_key\s*=\s*['\"][^'\"]{8,}['\"]", re.IGNORECASE)
        if any(not _is_placeholder(m.group(0)) for m in hardcoded_re.finditer(text)):
            findings.append(f"{rel}: possible hardcoded api_key= literal")
        for pat in PERSONAL_NAME_PATTERNS:
            if any(m.group(0).replace(" ", "") not in PERSONAL_NAME_ALLOWLIST
                   for m in pat.finditer(text)):
                findings.append(f"{rel}: possible personal name / honorific leaked (개인이름)")
                break
        # Unpublished research content is a separate axis from credentials, but
        # it ships out of the same tree, so it is gated here too. v1.2.0 went out
        # claiming these had been removed while they were still in four files.
        markers = scan_research_markers(text)
        if markers:
            shown = ", ".join(markers[:3]) + (f" (+{len(markers) - 3})" if len(markers) > 3 else "")
            findings.append(f"{rel}: unpublished research marker — {shown}")

    if findings:
        return CheckResult(
            name, STATUS_FAIL,
            f"{len(findings)} potential leak(s) found — review before distributing",
            findings[:30] + ([f"... and {len(findings) - 30} more"] if len(findings) > 30 else []),
        )
    return CheckResult(name, STATUS_OK, "no secrets / Tailscale IPs / personal names detected")


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


def _run_test_script(root: Path, rel: str, name: str,
                     ok_msg: str, fail_msg: str) -> CheckResult:
    """Delegate a check to a test script so the rule lives in exactly one place."""
    script = root / rel
    if not script.is_file():
        return CheckResult(name, STATUS_WARN, f"{rel} not present — skipped")
    import subprocess
    try:
        proc = subprocess.run(
            [sys.executable, str(script)], cwd=str(root),
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=180)
    except (OSError, subprocess.SubprocessError) as exc:
        return CheckResult(name, STATUS_WARN, f"could not run {rel}: {exc}")

    out = (proc.stdout or "") + (proc.stderr or "")
    summary = next((ln for ln in out.splitlines()
                    if ("확인" in ln or "대조 대상" in ln) and ln.strip()), "")
    if proc.returncode == 0:
        return CheckResult(name, STATUS_OK, summary.strip() or ok_msg)
    details = [ln for ln in out.splitlines() if ln.startswith("  ") and ln.strip()][:20]
    return CheckResult(name, STATUS_FAIL, fail_msg, details)


def _walk_files(root: Path):
    for dirpath, dirnames, filenames in _os_walk(root):
        dirnames[:] = [d for d in dirnames if d not in SCAN_EXCLUDE_DIRS and not d.startswith(".git")]
        for fn in filenames:
            yield Path(dirpath) / fn


def _os_walk(root: Path):
    import os
    yield from os.walk(root)


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
    ("tests/test_connectors.py", "REST connectors (dry-run isolation, --write gate, token gating)"),
    ("tests/test_service_routing.py", "service/skill routing (connector-silent steering, dead skill refs)"),
    ("tests/test_adopted_discipline_skills.py", "adopted discipline skills keep their substance"),
]


def check_toolkit_selftests(root: Path) -> CheckResult:
    """Run the regression tests for this package's own verification tools.

    These are the checks that guard manuscripts, numbers and secrets. If one of
    them silently stops working, every artifact it was supposed to gate ships
    unverified — so their tests run as part of doctor rather than on request.
    """
    name = "Toolkit self-tests"
    import subprocess
    present = [(rel, label) for rel, label in SELF_TEST_SCRIPTS
               if (root / rel).is_file()]
    if not present:
        return CheckResult(name, STATUS_WARN, "no self-test scripts present — skipped")

    failed, errored = [], []
    # `failed` mixes one header line per script with its detail lines, so its
    # length counts lines, not scripts — reporting it as "N of 16" produced
    # nonsense like "19 of 16". Count the scripts separately.
    n_failed_scripts = 0
    for rel, label in present:
        try:
            proc = subprocess.run(
                [sys.executable, str(root / rel)], cwd=str(root),
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=300)
        except (OSError, subprocess.SubprocessError) as exc:
            errored.append(f"{rel}: could not run ({exc})")
            continue
        if proc.returncode != 0:
            out = (proc.stdout or "") + (proc.stderr or "")
            # Keep the failing lines AND what follows them. Reporting only the
            # first "FAIL" line throws away the expected/actual values printed
            # underneath it, which is exactly what you need to tell a real
            # regression from an environment difference. A CI log that says only
            # "FAIL <case name>" cannot be diagnosed without re-running locally —
            # and if it reproduces locally you did not need the CI log anyway.
            lines = out.splitlines()
            detail = []
            for i, ln in enumerate(lines):
                if "FAIL" in ln or "Error" in ln or "Traceback" in ln or "attempt " in ln:
                    detail.append(ln.strip()[:160])
                    # the two lines after a failure usually carry 기대/실제
                    for nxt in lines[i + 1:i + 3]:
                        s = nxt.strip()
                        if s and not s.startswith("PASS"):
                            detail.append(f"    {s[:160]}")
                if len(detail) >= 12:
                    detail.append("    …")
                    break
            failed.append(f"{rel} ({label}) exited {proc.returncode}")
            failed.extend(f"    {d}" for d in detail)
            n_failed_scripts += 1

    if failed:
        return CheckResult(name, STATUS_FAIL,
                           f"{n_failed_scripts} of {len(present)} self-test(s) failing — "
                           f"a verification tool is broken",
                           failed + errored)
    if errored:
        return CheckResult(name, STATUS_WARN,
                           f"{len(errored)} self-test(s) could not run", errored)
    return CheckResult(name, STATUS_OK,
                       f"{len(present)} self-test(s) passing "
                       f"({', '.join(label for _, label in present)})")


def overall_status(results: list[CheckResult]) -> str:
    worst = max((r.status for r in results), key=lambda s: _STATUS_RANK[s], default=STATUS_OK)
    return worst


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
                     "Beginner-friendly (초심자) diagnostics for a fresh install.",
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
    args = parser.parse_args(argv)

    root = (args.root or Path(__file__).resolve().parent).resolve()

    results = run_all_checks(root, quick=args.quick)

    if args.json:
        print_json_report(results, root)
    else:
        print_human_table(results, root)

    return 0 if overall_status(results) != STATUS_FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
