"""SENTINEL scan (secrets / private data) and the research-marker scan.

Two separate axes checked by the same tree walk: leaked credentials/personal
data (SENTINEL proper) and unpublished-research content (RESEARCH_MARKERS).
Both gate the same distribution tree, so they're checked together in
check_sentinel_scan().
"""

from __future__ import annotations

import re
from pathlib import Path

from doctor_lib.fswalk import SCAN_EXCLUDE_DIRS, _os_walk, _walk_files  # noqa: F401
from doctor_lib.result import CheckResult, STATUS_FAIL, STATUS_OK

# Only scan text-ish files; skip large/binary formats to keep this fast.
SCAN_EXCLUDE_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg",
    ".pdf", ".zip", ".tar", ".gz", ".7z", ".whl",
    ".pyc", ".pyo", ".so", ".dll", ".exe", ".bin",
    ".sqlite", ".sqlite3", ".db",
}

MAX_SCAN_FILE_BYTES = 5 * 1024 * 1024  # 5 MB — skip anything bigger

# Filenames that are an automatic FAIL if found anywhere in the tree,
# regardless of content (a real secrets store should never ship).
SENTINEL_FORBIDDEN_FILENAMES = {
    "secrets.json",
    ".git-credentials",
}

# This scanner's own test fixtures carry intentionally fake credentials
# (see tests/test_doctor_sentinel.py) — scanning them would always "find" a leak.
# These are the files that define the detector's **contract**. The strings
# they carry are not a leak — they're the specification of "this is what
# must be caught" — so they're excluded from the SENTINEL scan. Without
# this exclusion, the test that guards against leaks would flag itself as a
# leak, which creates pressure to just delete the case — and the moment
# that happens, the detector goes blind.
SENTINEL_SELF_TEST_FILES = {
    "test_doctor_sentinel.py",
    "test_research_marker_scan.py",
    "test_feedback_sanitize.py",
}

# Source files that carry the detection regexes/patterns themselves as string
# literals (doctor.py used to be the only one; the doctor_lib split moved the
# regex bodies here). Scanning any of these would always "find" what it is
# looking for, so — like the self-test fixtures above — they are excluded by
# name rather than weakening the patterns.
SENTINEL_DETECTOR_FILES = {
    "doctor.py",
    "sentinel.py",
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


def check_sentinel_scan(root: Path) -> CheckResult:
    """Distribution safety self-check: make sure no secrets / private
    identifiers leaked into the tree that is about to be shipped.
    """
    name = "SENTINEL scan (secrets / private data)"
    findings: list[str] = []

    for path in _walk_files(root):
        rel = path.relative_to(root)

        # 1) Forbidden filenames, regardless of content.
        if path.name.lower() in SENTINEL_FORBIDDEN_FILENAMES:
            findings.append(f"{rel}: forbidden filename '{path.name}' present in tree")
            continue

        # doctor.py and doctor_lib/sentinel.py carry the detection regexes
        # themselves as literals; never scan either.
        if path.name in SENTINEL_DETECTOR_FILES:
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
                findings.append(f"{rel}: possible personal name / honorific leaked")
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
