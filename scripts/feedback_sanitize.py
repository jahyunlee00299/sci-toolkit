#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Feedback-sanitization gate — stops a saved record before it goes outward.

Why this is needed
-------------------
`feedback_log.py`'s `to_issue()` puts `what` / `expected` / `actual` / `note`
into the issue body **verbatim**. A student pasting an entire error message
is a normal way to report a problem, and that's exactly the moment a file
path, an undisclosed figure, an enzyme name, or an API key rides along with
it.

The docs (`docs/11_불편한점_남기기.md`) spelled out "what not to leave in a
report," but that was **guidance for a human, not code.** This workspace has
already made the same mistake three times — a guide/table/comment said
"removed" while the actual content shipped anyway (260807), a note said
"don't echo the value" while it got echoed anyway (260628), a note said
"don't keep sources/" while it got pushed anyway (260706). So this module is
an executed check, not a sentence.

Design principles
------------------
**Block only, never auto-fix.** Automatic masking would also erase
information needed to reproduce the issue, and the reporter wouldn't even
know what got erased. A human fixes it directly or approves it explicitly.

**Over-blocking kills the scanner.** What needs filtering is "what data did
this fail on," not "what failed." A version number, a file count, elapsed
time, a relative path, ordinary biochemistry notation (kcat, Km, NADH) must
always pass. Measured 260807: blocking `kdeg,NADH` had the precedent of
catching the very sanitized text that had just been written to report it.

**Reuse validated patterns.** Enzyme abbreviations, rate equations,
undisclosed substrates, and private repo names are already an asset that
`doctor.py`'s `scan_research_markers()` has calibrated through a
bidirectional test (`tests/test_research_marker_scan.py`). Don't rewrite them
here — two copies drift apart.
"""
from __future__ import annotations

import sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Fields that land in the issue body. env is excluded because it's
# auto-collected (OS/Python version) — there's no human-written content
# there, and if a version string trips numeric detection, every record gets
# blocked.
SCANNED_FIELDS = ("what", "expected", "actual", "note")


# ── Reuse doctor.py's validated research-marker scanner ──────────────────
def _load_research_scanner():
    """Import doctor.py's scan_research_markers.

    Returns None if unavailable, and the caller continues with just the
    other axes. It's riskier for the whole gate to die because one scanner
    is missing.
    """
    doctor_path = ROOT / "doctor.py"
    if not doctor_path.exists():
        return None
    try:
        spec = importlib.util.spec_from_file_location("doctor", doctor_path)
        mod = importlib.util.module_from_spec(spec)
        # doctor.py uses @dataclass. dataclasses looks up __module__ from
        # sys.modules, so it must be registered before exec.
        sys.modules.setdefault("doctor", mod)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod.scan_research_markers
    except Exception:
        return None


_scan_research = _load_research_scanner()


# ── Axis 1: credentials ───────────────────────────────────────────────────
# Measured 260628 — OPENROUTER_API_KEY (`sk-or-...`) leaked via stdout, left
# behind 15 times across 2 JSONL log files. Patterns with a distinctive
# prefix have essentially no false positives.
CREDENTIAL_PATTERNS = [
    ("API key/token",
     re.compile(r"\b(?:sk-[A-Za-z0-9\-]{16,}"
                r"|ghp_[A-Za-z0-9]{20,}|gho_[A-Za-z0-9]{20,}"
                r"|github_pat_[A-Za-z0-9_]{20,}"
                r"|xox[baprs]-[A-Za-z0-9\-]{10,}"
                r"|AKIA[0-9A-Z]{16}"
                r"|AIzaSy[A-Za-z0-9_\-]{20,})")),
    ("credential assignment statement",
     re.compile(r"(?:api[_-]?key|apikey|secret[_-]?key|access[_-]?token"
                r"|auth[_-]?token|client[_-]?secret|password|passwd)"
                r"\s*[:=]\s*[\"']?[A-Za-z0-9_\-.]{12,}[\"']?",
                re.IGNORECASE)),
    ("Tailscale IP",
     re.compile(r"\b100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}\b")),
]

# Let obvious placeholders through on the assignment-statement axis. If docs
# and examples get flagged, nobody can leave the most common report of all —
# "this isn't working for me."
#
# 🔴 This MUST apply only to the **value side**. Checking the whole
# assignment statement lets the `_key` in the key name `api_key` itself match
# `_KEY\b`, misjudging a real key as a placeholder even when the value is
# genuine — a hole measured on 260807 by this very test. doctor.py keeping a
# separate `_split_value()` exists for the same reason.
_CREDENTIAL_PLACEHOLDER = re.compile(
    r"your|example|placeholder|changeme|dummy|fake|sample|여기|입력|발급"
    r"|xxx+|\.\.\.|<|os\.environ|getenv"
    r"|^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+$",   # the value is literally an ENV variable name
    re.IGNORECASE,
)


def _assignment_value(matched: str) -> str:
    """Extract just the value portion from an assignment-statement match (`api_key = "abc"` -> `abc`)."""
    _, sep, value = matched.partition("=")
    if not sep:
        _, sep, value = matched.partition(":")
    return value.strip().strip("\"'") if sep else matched


# ── Axis 2: undisclosed research figures ──────────────────────────────────
# Measured 260706 — an undisclosed MPSP ($137.42/$84.09) and yield (88.3%)
# were left in a skill file and pushed. The judgment isn't "is this a
# number" but **a number carrying a research unit.** A version number
# (3.11), a count (3 items), a duration (10 min), memory (8GB) must always
# pass.
RESEARCH_UNIT_RE = re.compile(
    r"""(?<![A-Za-z0-9])
    \d+(?:\.\d+)?\s*
    (?:
        g/L|mg/mL|g/l|mg/ml|µg/mL|ug/mL          # concentration (mass)
      | mM|μM|uM|nM|M\b                          # concentration (molar)
      | U/mg|U/mL|U/ml|IU/mg                     # specific activity
      | mol%|wt%|w/w%|v/v%                       # composition
      | h⁻¹|s⁻¹|min⁻¹|/h\b|/s\b                  # rate constant
      | kcal/mol|kJ/mol                          # energy
      | °C(?=\s*(?:에서|조건|반응|배양))          # temperature only when it's a stated condition
    )
    """,
    re.VERBOSE,
)

# A dollar amount, a percentage, or a bare number is common on its own. It's
# treated as an undisclosed research value only when a research-context word
# accompanies it — that combination is the exact shape that actually leaked
# on 260706.
#
# 🔴 The judgment is **the word that follows the number, not the number's
# shape**. Measured 260807, comparing three approaches (24 cases):
#   . decimals only        -> 1 false positive, but **4/7 leaks got through**
#     (`수율이 92 였습니다` = "the yield was 92")
#   . every integer too    -> 0 leaks got through, but **13/13 false
#     positives = the report feature is effectively dead**
#   . integers + excluding quantity-words -> 0 leaks, 0 false positives  <- adopted
# "92 였습니다" (was 92) is a value; "3번째 줄" (3rd line), "2개" (2 items),
# "5분" (5 minutes) are quantities. The distinction isn't digit count or a
# decimal point — it's the particle/unit-word that follows.
MONEY_PCT_RE = re.compile(
    r"(?:\$\s*\d+(?:\.\d+)?"      # currency
    r"|\d+(?:\.\d+)?\s*%)"        # percentage
)

# A bare number (integers included) to check when a context word is present.
BARE_NUMBER_RE = re.compile(r"(?<![\d.])\d+(?:\.\d+)?(?![\d.])")

# If one of these words follows the number, it's a quantity/ordinal/duration,
# not a research measurement. This list is the false-positive defense line
# itself — add to it whenever a new false positive is reported.
#
# 🔴 After a unit word, a **boundary is required, but a particle must be
# allowed.** Both lessons were learned by measurement (260807):
#   . with no boundary -> `달` (month) matches the front of `달러` (dollar),
#     so `MPSP 120 달러` passes through whole (a miss).
#   . with the boundary as `(?![가-힣])` -> a normal form carrying a particle
#     like `2개로`, `3행에서`, `7개가` isn't exempted, producing 10 false
#     positives.
# So the rule treats "the Korean that follows is a particle, or isn't
# Korean at all" as a pass. Same root cause as the particle problem hit in
# real-name detection.
_COUNTERS = (
    r"번째|번|개|줄|쪽|장|건|회|명|차|단계|칸|열|행|셀|탭|시트|파일|항목|"
    r"분|초|시간|시|일|주|달|개월|년치|년|"
    r"에러|오류|코드|포트|버전"
)
COUNTER_WORD_RE = re.compile(
    rf"^\s*(?:{_COUNTERS})"
    # In addition to particles, also allow a sentence-final predicate ending
    # (`3번째입니다`). Allowing only particles leaves `번째입니다` failing
    # the boundary and becoming a false positive again — measured, 1 case.
    r"(?:입니다|이다|이고|이며|째)?"
    r"(?:이|가|은|는|을|를|로|으로|에|에서|의|만|도|과|와|랑)?"
    r"(?![가-힣])"
    r"|^\s*(?:MB|GB|KB|TB|bytes?|byte|px|dpi)\b")

# If one of these words precedes the number, it's not a value.
#   . version/keyboard shortcut: "Python 3.11", "Ctrl+7"
#   . identifier: "issue #42", "PR #7" — a number after `#` is a number, not a measurement
PRE_TECHNICAL_RE = re.compile(
    r"(?:Python|Ctrl|Alt|Shift|v|version|버전)\s*\+?\s*$|#\s*$", re.IGNORECASE)

# 0 is essentially never reported as a measurement, and is used far more
# often as a boundary-value statement like "starts from 0" or "0 items."
# Catching it would only add false positives.
_NOT_A_VALUE = frozenset({"0"})
RESEARCH_CONTEXT_RE = re.compile(
    r"MPSP|수율|전환율|역가|titer|yield|conversion|selectivity|선택도"
    r"|E-factor|순도|purity|생산성|productivity|비용|단가",
    re.IGNORECASE,
)


# ── Axis 3: personally identifying information ───────────────────────────
# Measured 260706 — two mentees' real names, left in skill code comments and
# SKILL.md, were pushed to a remote (the names themselves are not
# transcribed here — that would make this file the same leak). A Korean name
# mixes with ordinary nouns, so detection is **limited to a name followed by
# a title.** Widening it would catch phrases like "students" (학생 여러분)
# and block reports.
PERSON_PATTERNS = [
    ("email address", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    ("phone number", re.compile(r"\b01[0-9][-\s]?\d{3,4}[-\s]?\d{4}\b")),
    # 🔴 A particle attached after a title is the normal Korean form
    # ("○○○ 학생이 준" = "given by student ○○○"). A negative lookahead
    # would fail the whole match on the particle — measured 260807:
    # `○○○ 선생님 데이터` (followed by a space) got caught, but
    # `○○○ 학생이` (followed by a particle) passed through. Instead,
    # explicitly allow the particles that can follow a title.
    ("real name + title",
     re.compile(r"[가-힣]{2,4}\s*(?:교수|박사|선생님|학생|연구원|조교|님)"
                r"(?:님)?(?:이|가|은|는|을|를|과|와|의|께|에게|한테)?(?![가-힣])")),
]

# Role words that end in a title but don't refer to a specific person. Same
# intent as doctor.py's PERSONAL_NAME_ALLOWLIST — widened here for the
# feedback context.
_PARTICLE_RE = re.compile(r"(?:이|가|은|는|을|를|과|와|의|께|에게|한테)$")


def _strip_particle(text: str) -> str:
    """Strip whitespace, particles, and the honorific `님` to get a form comparable against a role word.

    `담당교수님께` -> `담당교수`. A role word carrying `님` is normal
    honorific speech, not a person's name. Without stripping it, a common
    sentence like "제출할 담당교수님께" ("to the professor in charge, to be
    submitted") gets falsely flagged as a real name (measured 260807).
    """
    stripped = _PARTICLE_RE.sub("", text.replace(" ", ""))
    # If only `님` remains (i.e. the title itself), don't strip it.
    if stripped.endswith("님") and len(stripped) > 1:
        stripped = stripped[:-1]
    return stripped


PERSON_ALLOWLIST = frozenset({
    "지도교수", "담당교수", "책임교수", "주임교수", "겸임교수", "객원교수",
    "부교수", "정교수", "조교수", "석좌교수", "명예교수", "교수",
    "지도박사", "담당박사", "박사", "선생님", "담당선생님", "학과선생님",
    "학생", "연구원", "조교", "님", "대학원생", "학부생", "참여연구원",
})


# ── Axis 4: absolute paths + username ─────────────────────────────────────
# A path itself is useful for reproduction, but an absolute path exposes a
# username and research folder name. A relative path (scripts/foo.py) and a
# bare filename (data.xlsx) are let through.
PATH_PATTERNS = [
    ("Windows absolute path", re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s\"']+", re.IGNORECASE)),
    ("POSIX home path", re.compile(r"/(?:home|Users)/[^/\s\"']+")),
    ("OneDrive path", re.compile(r"OneDrive[^\s\"']*[\\/][^\s\"']+")),
]


def _iter_hits(text: str) -> list[str]:
    """List of risky items found in a single string. Empty list = clean."""
    found: list[str] = []

    def add(label: str, matched: str) -> None:
        entry = f"{label}: {matched.strip()}"
        if entry not in found:
            found.append(entry)

    # Axis 1 — credentials
    for label, rx in CREDENTIAL_PATTERNS:
        for m in rx.finditer(text):
            hit = m.group(0)
            if label == "credential assignment statement" and _CREDENTIAL_PLACEHOLDER.search(
                    _assignment_value(hit)):
                continue
            add(label, hit)

    # Axis 2 — figures carrying a research unit
    for m in RESEARCH_UNIT_RE.finditer(text):
        add("research figure", m.group(0))
    # A dollar amount, percentage, or bare number is checked only alongside a research-context word.
    if RESEARCH_CONTEXT_RE.search(text):
        for m in MONEY_PCT_RE.finditer(text):
            add("research figure", m.group(0))
        for m in BARE_NUMBER_RE.finditer(text):
            tail, head = text[m.end():], text[:m.start()]
            if m.group(0) in _NOT_A_VALUE:
                continue
            # A quantity/ordinal/duration/version/identifier is not a value.
            if COUNTER_WORD_RE.match(tail) or PRE_TECHNICAL_RE.search(head):
                continue
            # A `$`/`%`-carrying match was already caught above — avoid a duplicate report.
            if tail.lstrip().startswith("%") or head.rstrip().endswith("$"):
                continue
            add("research figure", m.group(0))

    # Axis 3 — personally identifying information
    for label, rx in PERSON_PATTERNS:
        for m in rx.finditer(text):
            hit = m.group(0)
            # The match allowed a particle, so the particle must be stripped
            # before comparing against the role-word list. Without stripping
            # it, `지도교수에게` isn't in the list and becomes a false positive.
            if label == "real name + title" and _strip_particle(hit) in PERSON_ALLOWLIST:
                continue
            add(label, hit)

    # Axis 4 — absolute paths
    for label, rx in PATH_PATTERNS:
        for m in rx.finditer(text):
            add(label, m.group(0))

    # Axis 5 — undisclosed research markers (reusing doctor.py)
    if _scan_research is not None:
        for hit in _scan_research(text):
            if hit not in found:
                found.append(hit)

    return found


def scan_text(text: str | None) -> list[str]:
    """Check a single string. An empty list means it passed."""
    if not text:
        return []
    return _iter_hits(text)


def scan_entry(entry: dict) -> list[str]:
    """Check one record — looks at every field that lands in the issue body.

    Checking only `what` leaves the other three fields completely
    unguarded. `actual` is the field a student is most likely to paste the
    raw error text into.
    """
    found: list[str] = []
    for field in SCANNED_FIELDS:
        for hit in scan_text(entry.get(field)):
            tagged = f"[{field}] {hit}"
            if tagged not in found:
                found.append(tagged)
    return found


def format_report(hits: list[str], *, prefix: str = "  ") -> str:
    """Format the blocking reasons for human reading."""
    return "\n".join(f"{prefix}· {h}" for h in hits)


if __name__ == "__main__":
    # Check text taken from stdin or from arguments. Running the script
    # directly should let you check "does this sentence get flagged?"
    text = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else sys.stdin.read()
    hits = scan_text(text)
    if hits:
        print("Suspicious item(s):")
        print(format_report(hits))
        sys.exit(2)
    print("Clean.")
    sys.exit(0)
