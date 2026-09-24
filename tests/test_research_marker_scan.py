#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Two-directional regression test for the research-marker scanner.

Background (measured, 2026-08-07):
  This distribution's docs claimed "unpublished research names have been
  sanitized," while v1.2.0 actually shipped still carrying species-prefixed
  enzyme names / the full cascade ODE / an engineered-variant name / private
  repo names. doctor.py's
  SENTINEL scan only ever looked at secrets.json, API keys, Tailscale IPs,
  and Korean personal names, so **this category was never in scope to begin
  with.** That's how the "sanitization complete" self-description diverged
  from what was actually on disk.

Two MUST_FLAG contracts run here:
  · synthetic — config/research_markers.example.json, always present, proves
    the loader and the scan mechanics on invented names;
  · real — the "must_flag" list in the local marker file
    (config/research_markers.local.json, gitignored since 260925 because this
    repo is public and the list names the unpublished work). Every string
    there was **actually found in the distribution**. Delete or weaken a case
    and the same leak passes right back through. Without the local file this
    half is reported as SKIP, never as pass.

MUST_NOT_FLAG runs the opposite direction — ordinary biochemistry notation
(NADH, NADPH, Km, kcat) and explanations of taxonomic species-prefix
convention are legitimate teaching content and must never trip the scanner.
Over-blocking gets the scanner switched off, and a switched-off scanner is
worth nothing.
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
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location("doctor", ROOT / "doctor.py")
_doctor = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
# doctor.py uses @dataclass. dataclasses looks up a class's __module__ from
# sys.modules, so without registering it before exec_module, this dies with
# AttributeError('NoneType' object has no attribute '__dict__').
sys.modules["doctor"] = _doctor
_spec.loader.exec_module(_doctor)

scan_research_markers = _doctor.scan_research_markers
_sentinel = sys.modules["doctor_lib.sentinel"]


def _load_contract(path: Path):
    """(markers, must_flag) from a marker file."""
    import json
    data = json.loads(path.read_text(encoding="utf-8"))
    return _sentinel.load_research_markers(path), [tuple(c) for c in data.get("must_flag", [])]


# ── Legitimate teaching content (must never trip the scanner) ─────────────
MUST_NOT_FLAG = [
    # Generic coenzyme notation rules (the substance of academic-term-rules)
    "**Coenzymes**: NAD+, NADH, NADP+, NADPH (superscript+ required)",
    "| nadph | NADPH |",
    "`NAD+-dependent`, `NADH-dependent` — hyphenated modifier",
    "NAD+/NADH ratio, NADP+:NAD+",
    # Generic kinetics symbols
    "kcat/Km is written in italics",
    "Vmax and Km are Michaelis-Menten parameters",
    "Report kcat, Km, and kcat/Km with units",
    # A coenzyme subscript appears in any redox system — it's not project-specific.
    # Measured 260807: blocking this made the sanitized replacement text itself
    # trip the scanner.
    "kdeg = sub(ri('k'), rp('deg,NADH'))",
    "kdeg,NADH / kcat -> sub(ri('k'), rp('deg,NADH'))",
    # Explanation of the taxonomic species-prefix convention (a generic rule
    # mapped onto a real Latin binomial)
    "only the species prefix is italic, the enzyme name itself is roman: `*Ec*XylA`",
    "variant notation: `*Ec*XylA(G171R/L172R)`",
    "XxDH (glucose dehydrogenase from *B. subtilis*)",
    # Anonymized examples (the correct post-sanitization form — if this trips,
    # sanitization itself becomes impossible)
    "('MW: Enzyme1 (E1)', 37000.0, 'g/mol', 'SI Fig. S1 (example)')",
    "| Glucose dehydrogenase | GDH | species prefix italic: *Xx*GDH |",
    "d[Substrate]/dt = -v1",
    "v1 = (Vmax,E1 * [S]) / (Km,E1 + [S])",
    # Appearing as an ordinary word
    "This rule applies to all git repos (repo-a, repo-b, etc.)",
    "Peak picking is handled by the bundled parser.",
    # The 3 below were judged false positives in the 260807 sweep. The
    # reasoning is recorded here so the next person doesn't have to
    # re-investigate "why isn't this blocked."
    #  - D-Gal / D-galactose: a commodity sugar common in the literature, and
    #    skills legitimately use it to teach the general rule "don't mix an
    #    abbreviation with its full name." Blocking it would make
    #    sanitization itself impossible.
    #  - kLa alone: a standard fermentation-engineering symbol. What
    #    identifies the project isn't the name kLa but the specific
    #    *correlation* that expresses it as a power law of stirrer speed.
    #  - Eq. S5 alone: SI cross-reference notation. It necessarily appears
    #    when explaining a notation convention.
    '"D-Gal": "#009E73",   # RESERVED for D-galactose only',
    "check_abbrev_consistency([\"D-Gal\", \"D-Glc\", \"Formate\"])",
    "A fit just produced parameters (kcat, Km, alpha, kLa, ...) or a curve",
    "callouts (Fig. S7, Table S3, SI Note S1, Eq. S6), and generic named parts",
    '"(SI Eq. S2-S8)" when a concrete anchor exists',
]

_fail = 0
_pass = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global _fail, _pass
    if cond:
        _pass += 1
    else:
        _fail += 1
        print(f"  FAIL  {name}" + (f"  — {detail}" if detail else ""))


def run_contract(title: str, markers, must_flag) -> None:
    print(f"\n[{title}] MUST FLAG {len(must_flag)} — all must be blocked")
    for text, label in must_flag:
        hits = scan_research_markers(text, markers)
        check(f"{title} block: {label}", bool(hits),
              f"let it through -> {text[:60]!r}")
    print(f"[{title}] MUST NOT FLAG {len(MUST_NOT_FLAG)} legitimate items — all must pass")
    for text in MUST_NOT_FLAG:
        hits = scan_research_markers(text, markers)
        check(f"{title} allow: {text[:45]}", not hits,
              f"false positive {hits} -> {text[:60]!r}")


def main() -> int:
    print("Research-marker scanner two-directional verification")
    print("=" * 60)

    markers, must_flag = _load_contract(_sentinel.RESEARCH_MARKERS_EXAMPLE)
    check("synthetic contract is non-empty", bool(markers) and bool(must_flag))
    run_contract("synthetic", markers, must_flag)

    local = _sentinel.research_markers_path()
    if local.is_file():
        markers, must_flag = _load_contract(local)
        check("real contract is non-empty", bool(markers) and bool(must_flag))
        # The module-level default must be the same file, or doctor/feedback
        # scan with something other than what was just verified.
        check("default markers loaded from the local file",
              len(_sentinel.RESEARCH_MARKERS) == len(markers)
              and not _sentinel.RESEARCH_MARKERS_ERROR,
              str(_sentinel.RESEARCH_MARKERS_ERROR))
        run_contract("real", markers, must_flag)
    else:
        print(f"\n[real] SKIP — no {local} (public clone). The real leak contract did NOT run.")

    print("=" * 60)
    print(f"passed {_pass} / failed {_fail}")
    if _fail:
        print("\nThe scanner does not satisfy the contract. Fix the scanner — do not delete the cases.")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
