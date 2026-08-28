#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Two-directional regression test for the research-marker scanner.

Background (measured, 2026-08-07):
  This distribution's docs claimed "unpublished research names have been
  sanitized," while v1.2.0 actually shipped still carrying RoGDH / RsGDH /
  LpNoxV / the full cascade ODE / scgre3 / private repo names. doctor.py's
  SENTINEL scan only ever looked at secrets.json, API keys, Tailscale IPs,
  and Korean personal names, so **this category was never in scope to begin
  with.** That's how the "sanitization complete" self-description diverged
  from what was actually on disk.

Every string in MUST_FLAG was **actually found in the distribution**.
Delete or weaken a case and the same leak passes right back through.

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

# ── Leaks actually found in the distribution (all must be blocked) ────────
MUST_FLAG = [
    # Enzyme species prefix + real abbreviation (domain_abbrev_registry.md:12,14, 4 files total)
    ("species prefix italic: *Ro*GDH, *Rs*GDH", "RoGDH"),
    ("| NADH oxidase | Nox | *Lp*NoxV (engineered variant) |", "LpNoxV"),
    ("**enzyme prefix**: only the species prefix (e.g. *Ro*GDH) is italic", "RoGDH"),
    ("R1 | enzyme name: only the 2-letter species prefix is italic (`*Ro*GDH`) |", "RoGDH"),
    ("**enzyme abbreviation**: full name at first mention (BsGDH, PsFDH, etc.)", "BsGDH/PsFDH"),
    # cascade ODE (docx/SKILL.md:1089-1143)
    ("# d[D-Gal]/dt = -vXR", "vXR"),
    ("# d[NAD+]/dt = -vGDH + vNOX", "vGDH/vNOX"),
    ("# vFDH = (Vmax,FDH * [HCOO-]) / (Km,FDH + [HCOO-])", "vFDH"),
    ("para = omath(ddt('D-Gal') + r(' = -') + vsub('XR'))", "vsub('XR')"),
    ("# kLa = α · N^β  (Eq. S5)", "kLa correlation"),
    ("Vmax,XR -> sub(ri('V'), rp('max,XR'))", "Vmax,XR"),
    ("Km,FDH / KiA,XR / KmB,GDH / KiQ", "KiA,XR"),
    ("kdeg,GDH must trip this — it carries a project enzyme subscript", "kdeg,GDH"),
    # unpublished variant/repo names
    ("reference example: `F_figS2_scgre3_activity/script.py`", "scgre3"),
    ("all git repos (claude-scientific-skills, UDH_Clustering, Kinetic-modeling)", "UDH_Clustering"),
    ("ported the algorithm from the PeakPicker repo (~/PeakPicker) to stdlib only", "PeakPicker"),
    # research subject terms
    ("tagatose production from D-galactose", "tagatose"),
    ("L-ribose isomerase screening", "L-ribose"),
]

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
    "BsGDH (glucose dehydrogenase from *B. subtilis*)" .replace("BsGDH", "XxDH"),
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


def main() -> int:
    print("Research-marker scanner two-directional verification")
    print("=" * 60)

    print(f"\n[MUST FLAG] {len(MUST_FLAG)} real leaks — all must be blocked")
    for text, label in MUST_FLAG:
        hits = scan_research_markers(text)
        check(f"block: {label}", bool(hits),
              f"let it through -> {text[:60]!r}")

    print(f"\n[MUST NOT FLAG] {len(MUST_NOT_FLAG)} legitimate items — all must pass")
    for text in MUST_NOT_FLAG:
        hits = scan_research_markers(text)
        check(f"allow: {text[:45]}", not hits,
              f"false positive {hits} -> {text[:60]!r}")

    print("=" * 60)
    print(f"passed {_pass} / failed {_fail}")
    if _fail:
        print("\nThe scanner does not satisfy the contract. Fix the scanner — do not delete the cases.")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
