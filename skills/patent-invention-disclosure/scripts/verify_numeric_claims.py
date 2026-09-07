#!/usr/bin/env python3
"""
Arithmetic re-derivation gate for patent invention-disclosure numeric claims.

Why this exists (do not remove without reading):
a batch placeholder-fill pass produced an invention disclosure claiming
"initial substrate 154.2 mM, titer 112 mM, yield 91.9%" where 112/154.2 = 72.6%,
not 91.9%. That number sat inside a dependent claim's numeric limitation
(">=91%"), which is patent-fatal if false. A first "looks OK, has a footnote"
pass missed it. Footnotes can be fabricated; only re-computing the arithmetic
catches this class of error.

This script re-derives yield / productivity / free-energy claims from the
OTHER numbers stated alongside them and flags any claim whose stated value
disagrees with the re-derived value beyond tolerance. It does not know
whether a number is "true" against raw data (that needs the source
manuscript/rawdata, i.e. adversarial-verifier) — it only catches internal
arithmetic self-contradiction, which is a strictly cheaper, deterministic,
always-worth-running first pass.

Usage:
    python verify_numeric_claims.py --self-test
    python verify_numeric_claims.py claims.json [--tol 0.02]
    python verify_numeric_claims.py --scan document.docx [--tol 0.02]

claims.json format: a list of claim objects, each one of:
    {"type": "yield", "label": "...", "initial": 154.2, "final": 112, "claimed_pct": 91.9}
    {"type": "productivity", "label": "...", "titer": 1.09, "time_h": 24, "claimed": 0.087, "unit": "g/L/h"}
    {"type": "triple_avg", "label": "...", "values": [10.5, 10.9, 10.2], "claimed_avg": 10.9}
    {"type": "delta_g", "label": "...", "keq": 3.7e4, "temp_k": 298.15, "claimed_kj_mol": -26.1}

Exit code: 0 = all claims consistent, 1 = at least one MISMATCH found.
"""
import argparse
import json
import math
import re
import sys

R_KJ = 8.314462618e-3  # kJ / (mol*K)


def check_yield(c, tol):
    initial = c["initial"]
    final = c["final"]
    claimed = c["claimed_pct"]
    if initial == 0:
        return _result(c, None, claimed, "initial is zero, cannot derive yield")
    derived = final / initial * 100
    return _result(c, derived, claimed, None, tol=tol, tol_is_pct_points=True)


def check_productivity(c, tol):
    titer = c["titer"]
    time_h = c["time_h"]
    claimed = c["claimed"]
    if time_h == 0:
        return _result(c, None, claimed, "time_h is zero, cannot derive productivity")
    derived = titer / time_h
    return _result(c, derived, claimed, None, tol=tol)


def check_triple_avg(c, tol):
    values = c["values"]
    claimed = c["claimed_avg"]
    derived = sum(values) / len(values)
    return _result(c, derived, claimed, None, tol=tol)


def check_delta_g(c, tol):
    keq = c["keq"]
    t_k = c.get("temp_k", 298.15)
    claimed = c["claimed_kj_mol"]
    if keq <= 0:
        return _result(c, None, claimed, "Keq must be > 0 for ln(Keq)")
    derived = -R_KJ * t_k * math.log(keq)
    return _result(c, derived, claimed, None, tol=tol)


CHECKERS = {
    "yield": check_yield,
    "productivity": check_productivity,
    "triple_avg": check_triple_avg,
    "delta_g": check_delta_g,
}


def _result(claim, derived, claimed, error, tol=None, tol_is_pct_points=False):
    if error:
        return {"label": claim.get("label", "?"), "type": claim["type"],
                "verdict": "UNRESOLVED", "reason": error,
                "claimed": claimed, "derived": None}
    if tol_is_pct_points:
        diff = abs(derived - claimed)
        ok = diff <= tol * 100
    else:
        denom = max(abs(claimed), 1e-9)
        diff = abs(derived - claimed) / denom
        ok = diff <= tol
    return {
        "label": claim.get("label", "?"),
        "type": claim["type"],
        "verdict": "CONSISTENT" if ok else "MISMATCH",
        "claimed": claimed,
        "derived": round(derived, 4),
        "diff": round(diff, 4),
    }


def verify_claims(claims, tol=0.02):
    results = []
    for c in claims:
        checker = CHECKERS.get(c.get("type"))
        if checker is None:
            results.append({"label": c.get("label", "?"), "type": c.get("type"),
                             "verdict": "UNRESOLVED",
                             "reason": f"unknown claim type {c.get('type')!r}"})
            continue
        results.append(checker(c, tol))
    return results


# ---------------------------------------------------------------------------
# Best-effort scan of Korean patent-register prose for yield-triplet patterns.
# This is a recall aid, not a substitute for structured claims.json input —
# it flags CANDIDATE triples for a human/agent to confirm before trusting.
# ---------------------------------------------------------------------------
YIELD_TRIPLE_RE = re.compile(
    r"(?:초기|initial)[^0-9]{0,20}?(?P<initial>[\d.]+)\s*mM.{0,80}?"
    r"(?:titer|티터)[^0-9]{0,10}?(?P<final>[\d.]+)\s*mM.{0,80}?"
    r"(?:수율|yield)[^0-9]{0,10}?(?P<pct>[\d.]+)\s*%",
    re.IGNORECASE | re.DOTALL,
)


def scan_docx_text(text, tol=0.02):
    claims = []
    for m in YIELD_TRIPLE_RE.finditer(text):
        claims.append({
            "type": "yield",
            "label": text[max(0, m.start() - 20):m.start()].strip()[-30:] or "scanned",
            "initial": float(m.group("initial")),
            "final": float(m.group("final")),
            "claimed_pct": float(m.group("pct")),
        })
    return claims


def extract_docx_text(path):
    # Deliberately minimal: python-docx read-only text extraction is fine for
    # SCANNING (this script never writes a docx). Per the docx skill's own
    # rules, python-docx must never be used to CREATE/SAVE a docx — that
    # restriction does not apply to read-only paragraph text extraction here.
    from docx import Document
    doc = Document(path)
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            parts.append(" ".join(cell.text for cell in row.cells))
    return "\n".join(parts)


SELF_TEST_CASES = [
    # Real regression case A: claimed 91.9%, true 72.6%.
    {"type": "yield", "label": "regression case A - substrate yield",
     "initial": 154.2, "final": 112, "claimed_pct": 91.9},
    # Companion case from the same batch: claimed 72.3% vs stated inputs.
    {"type": "yield", "label": "regression case A - companion product yield",
     "initial": 20.6 / 0.723, "final": 20.6, "claimed_pct": 91.9},
    # Real regression case B: claimed 87 mg/L/h, true 1.09 g/L / 24h = 45.4 mg/L/h.
    {"type": "productivity", "label": "regression case B - productivity",
     "titer": 1.09 * 1000, "time_h": 24, "claimed": 87, "unit": "mg/L/h"},
    # A genuinely consistent control case — must NOT be flagged.
    {"type": "yield", "label": "control (should be consistent)",
     "initial": 100, "final": 96.4, "claimed_pct": 96.4},
]


def self_test():
    results = verify_claims(SELF_TEST_CASES, tol=0.02)
    ok = True
    print("=== self-test ===")
    for r, c in zip(results, SELF_TEST_CASES):
        print(f"[{r['verdict']:>10}] {r['label']}: claimed={r['claimed']} derived={r.get('derived')}")
    # Assertions: the three incident cases MUST be caught as MISMATCH,
    # the control case MUST be CONSISTENT. This is the Refute evidence —
    # proof the gate actually catches the known error class, not just that
    # it runs without crashing.
    expect_mismatch = results[0:3]
    expect_consistent = results[3]
    for r in expect_mismatch:
        if r["verdict"] != "MISMATCH":
            print(f"FAIL: expected MISMATCH for {r['label']!r}, got {r['verdict']}")
            ok = False
    if expect_consistent["verdict"] != "CONSISTENT":
        print(f"FAIL: expected CONSISTENT for control case, got {expect_consistent['verdict']}")
        ok = False
    if ok:
        print("PASS: all 3 known incident errors caught as MISMATCH; control case not flagged.")
    else:
        print("SELF-TEST FAILED")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", nargs="?", help="claims.json, or a docx path with --scan")
    ap.add_argument("--tol", type=float, default=0.02, help="relative tolerance (0.02 = 2%%)")
    ap.add_argument("--scan", action="store_true", help="treat input as a .docx and best-effort scan for yield triples")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--json", dest="json_out", help="write results as JSON to this path")
    args = ap.parse_args()

    if args.self_test:
        sys.exit(0 if self_test() else 1)

    if not args.input:
        ap.error("input is required unless --self-test")

    if args.scan:
        text = extract_docx_text(args.input)
        claims = scan_docx_text(text, tol=args.tol)
        if not claims:
            print("No yield-triplet candidates matched the scan pattern. "
                  "This does NOT mean the document is clean — write claims.json "
                  "by hand for any numeric claim not caught by the regex.")
    else:
        with open(args.input, encoding="utf-8") as f:
            claims = json.load(f)

    results = verify_claims(claims, tol=args.tol)
    mismatches = [r for r in results if r["verdict"] == "MISMATCH"]
    unresolved = [r for r in results if r["verdict"] == "UNRESOLVED"]
    for r in results:
        marker = {"CONSISTENT": "OK", "MISMATCH": "MISMATCH", "UNRESOLVED": "UNRESOLVED"}[r["verdict"]]
        extra = f" ({r['reason']})" if r["verdict"] == "UNRESOLVED" and r.get("reason") else ""
        print(f"[{marker:>10}] {r['label']} ({r['type']}): claimed={r.get('claimed')} derived={r.get('derived')}{extra}")

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

    # UNRESOLVED is NOT the same as CONSISTENT — a claim this script could not
    # check (malformed type, division by zero, missing field) must never be
    # reported as "fine". Both MISMATCH and UNRESOLVED block a clean exit.
    if mismatches or unresolved:
        if mismatches:
            print(f"\n{len(mismatches)} MISMATCH found — do NOT present these claims as final. "
                  "Re-check against source manuscript/rawdata (adversarial-verifier) before fixing.")
        if unresolved:
            print(f"\n{len(unresolved)} UNRESOLVED (could not be arithmetically re-derived) — "
                  "these were NOT verified. Fix the claim data or check by hand; do not treat as passing.")
        sys.exit(1)
    print(f"\nAll {len(results)} claims arithmetically consistent "
          "(does not guarantee correctness vs raw data — that needs adversarial-verifier).")
    sys.exit(0)


if __name__ == "__main__":
    main()
