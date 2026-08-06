#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sci_validate.py — Scientific validity gate for fit / calibration / optimization results.

Companion to the `scientific-validation` skill. Runs the *mechanical* parts of the four-axis
check so Claude can focus its judgment on the parts a script can't decide (identifiability
covariance reasoning, conservation, SSOT provenance, independent reproduction).

It NEVER fits anything and NEVER touches raw data files — it only audits an already-produced
result, given as JSON or on the command line.

CHECKS (each -> PASS / CAUTION / FAIL with evidence)
  1. physical_range : each parameter inside its plausible window  (PHYSICAL_RANGES, extensible)
  2. bound_hit      : no parameter pinned on its search bound      (needs bounds)
  3. unit_sanity    : kcat-like values not off by ~10^3 (Vmax/kcat mix-up heuristic)
  4. residual_runs  : residuals look like noise (Wald-Wolfowitz runs test) (needs residuals)
  5. dof            : #free params not saturating #data points (overfitting heuristic)
  6. identifiability: CV / correlation flags                       (needs stderr or corr)

INPUT (JSON)  -- pass --json path/to/results.json  OR pipe JSON on stdin
{
  "params":     {"kcat_gdh": 12.3, "km_b_gdh": 0.009, "effectiveness_factor": 1.4, ...},
  "bounds":     {"kcat_gdh": [0.1, 500], "km_b_gdh": [0.01, 10], ...},      # optional
  "stderr":     {"kcat_gdh": 0.5, "km_b_gdh": 0.02, ...},                   # optional, for CV
  "corr":       [[1.0, 0.97], [0.97, 1.0]],                                 # optional, param-param corr matrix
  "corr_names": ["kcat_gdh", "km_b_gdh"],                                   # names for corr matrix rows
  "residuals":  [0.1, -0.2, 0.05, ...],                                     # optional, ordered along the curve
  "n_data":     42,                                                         # optional, #independent data points
  "ranges":     {"my_param": [lo, hi]},                                     # optional, extend/override PHYSICAL_RANGES
  "mass_balance": {                                                          # optional, conservation check
      "t0_total":   100.0,                                                  # conserved total at t=0 (e.g. total carbon, cofactor pool)
      "species":    {"product": 70.0, "byproduct": 8.0, "residual_substrate": 20.0}, # measured species at the target timepoint
      "tol_frac":   0.10,                                                   # allowed closure deviation (default 0.10 = ±10%)
      "label":      "total carbon (mM)"                                     # what is being conserved
  }
}

EXIT CODE: 0 = pass/caution only; 1 = a real scientific FAIL (gate should block);
          2 = bad invocation / unparseable input; 3 = a check crashed (tool/input error, NOT science).
Verdict + per-check evidence printed as a table AND emitted as JSON (--emit-json).
"""
import sys
import json
import math
import argparse
import io

# Force UTF-8 stdout/stderr: on Windows PowerShell 5.1 (cp949) the console would otherwise choke on
# the ✅/⚠️/❌/— glyphs below. reconfigure() on 3.7+, TextIOWrapper fallback for older Pythons.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── Starter physical-range table. Extend per system via "ranges" in the input JSON. ──────────
# Format: name_token -> (lo, hi, unit, note). Matching is on whole name tokens (see _classify_range),
# so "kcat_gdh", "kcat_nox" both match key "kcat", but "kma_x" does NOT match "km". Longest key wins.
PHYSICAL_RANGES = {
    # generic kinetics
    "kcat":                 (0.1, 500.0, "1/s",  "dehydrogenase kcat_true ~1-50; <0.1 or >500 suggests Vmax(mM/s) unit error"),
    "km":                   (0.001, 50.0, "mM",  "Km typically 0.01-10 mM"),
    "vmax_futile":          (0.0, 0.05, "mM/s",  ">0.05 non-physical for a futile cycle"),
    # whole-cell / cascade (starter values; override per system via the "ranges" input)
    "effectiveness_factor": (0.1, 1.0, "-",      "effectiveness factor CANNOT exceed 1.0"),
    "alpha":                (0.5, 10.0, "-",     "alpha_pntab ~1-5; >10 non-physical"),
    "qo2_basal":            (0.01, 1.0, "mmol/gDCW/h", "basal qO2 ~0.05-0.30; >1.0 caution"),
    "kla":                  (0.0001, 50.0, "1/h", "kLa; pinned at 0.0001 or upper bound = bound-hit"),
    "yield":                (0.0, 1.0, "frac",   "fractional yield in [0,1]"),
}


def _name_tokens(name):
    """Split a parameter name into word tokens, lowercased, separating on _, -, spaces and digits
    (so 'kcat_gdh', 'km_b_gdh', 'qo2_basal' tokenize cleanly; 'kma_x'->['kma','x'] won't match 'km')."""
    out, cur = [], []
    for ch in name.lower():
        if ch.isalpha():
            cur.append(ch)
        else:
            if cur:
                out.append("".join(cur)); cur = []
    if cur:
        out.append("".join(cur))
    return out


def _classify_range(name, val, ranges):
    """Return (verdict, note) for one parameter against the range table.
    Match a registered key only if it is a WHOLE token of the name (or the name starts with key+token-
    boundary) — never a bare substring, so 'kma_*' does not inherit the 'km' range (the substring-collision
    false-FAIL bug). Longest matching key wins."""
    tokens = _name_tokens(name)
    matches = []
    for k in ranges:
        ktoks = _name_tokens(k)
        if not ktoks:
            continue
        # Match only if the key's token sequence appears as a CONTIGUOUS run of whole tokens in the
        # name. So key 'km' matches name token ['km',...] but NOT 'kma' (different token); multi-token
        # key 'effectiveness_factor' -> ['effectiveness','factor'] matches name ['effectiveness','factor'].
        n, m = len(tokens), len(ktoks)
        if m <= n and any(tokens[i:i + m] == ktoks for i in range(n - m + 1)):
            matches.append(k)
    if not matches:
        return ("CAUTION", f"no physical range registered for '{name}' — add to 'ranges' and judge manually")
    k = max(matches, key=len)
    entry = ranges[k]
    lo, hi, unit, note = entry
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return ("FAIL", f"value is None/NaN")
    if val < lo or val > hi:
        return ("FAIL", f"{val:g} {unit} OUTSIDE [{lo:g}, {hi:g}] — {note}")
    # Soft "near edge" band, measured on a LOG scale when the range spans orders of magnitude
    # (a linear 5%-of-span band over [0.1,500] would flag 12 as 'near edge', which is nonsense).
    edge = None
    if lo > 0 and hi > 0 and hi / lo > 20:  # wide / multi-decade range -> log proximity
        lr = math.log10(hi / lo)
        if math.log10(val / lo) < 0.05 * lr or math.log10(hi / val) < 0.05 * lr:
            edge = True
    else:  # narrow range -> linear 5% band
        span = hi - lo
        if span > 0 and (val - lo < 0.05 * span or hi - val < 0.05 * span):
            edge = True
    if edge:
        return ("CAUTION", f"{val:g} {unit} near edge of [{lo:g}, {hi:g}] — {note}")
    return ("PASS", f"{val:g} {unit} in [{lo:g}, {hi:g}]")


def check_physical_range(d, ranges):
    params = d.get("params", {})
    if not params:
        return ("CAUTION", "no 'params' supplied — physical-range check skipped", [])
    rows, worst = [], "PASS"
    order = {"PASS": 0, "CAUTION": 1, "FAIL": 2}
    for name, val in params.items():
        v, note = _classify_range(name, val, ranges)
        rows.append(f"  {name}: {v} — {note}")
        if order[v] > order[worst]:
            worst = v
    return (worst, f"{len(params)} parameters checked", rows)


def check_bound_hit(d):
    params, bounds = d.get("params", {}), d.get("bounds", {})
    if not bounds:
        return ("CAUTION", "no 'bounds' supplied — bound-hit check skipped (pass search bounds!)", [])
    rows, worst = [], "PASS"
    for name, b in bounds.items():
        if name not in params:
            continue
        val = params[name]
        # bounds must be an ordered 2-sequence of numbers; tolerate reversed by sorting, skip malformed.
        if not (isinstance(b, (list, tuple)) and len(b) == 2 and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in b)):
            rows.append(f"  {name}: bounds {b!r} malformed (need [lo, hi] numbers) — skipped")
            if worst == "PASS":
                worst = "CAUTION"
            continue
        lo, hi = sorted(b)
        if not isinstance(val, (int, float)) or isinstance(val, bool):
            continue
        for edge, label in ((lo, "lower"), (hi, "upper")):
            if edge == 0:
                hit = abs(val - edge) < 1e-9
            else:
                hit = abs(val - edge) / abs(edge) < 0.01
            if hit:
                rows.append(f"  {name}={val:g} pinned at {label} bound {edge:g} — optimum is OUTSIDE the box; value meaningless")
                worst = "FAIL"
    if not rows:
        return ("PASS", "no parameter pinned on a search bound", [])
    return (worst, "bound-hit detected", rows)


def check_unit_sanity(d):
    """Heuristic: a kcat-named parameter that is suspiciously small (<0.1) is often an
    apparent-Vmax (mM/s) mislabeled as kcat (1/s). Flag for manual unit trace."""
    params = d.get("params", {})
    rows = []
    for name, val in params.items():
        if "kcat" in name.lower() and val is not None and 0 < val < 0.1:
            rows.append(f"  {name}={val:g}: <0.1 1/s is unusually small for a kcat — check if this is Vmax(mM/s) needing /[E]")
    if not rows:
        return ("PASS", "no obvious kcat unit mix-up signature", [])
    return ("CAUTION", "possible Vmax-vs-kcat unit error", rows)


def check_residual_runs(d):
    """Wald-Wolfowitz runs test on the sign of residuals (ordered along the curve).
    Too few runs => systematic structure => wrong model even at high R²."""
    res = d.get("residuals")
    if not res:
        return ("CAUTION", "no residuals supplied — residual-structure check skipped", [])
    # Keep only numeric residuals; drop exact zeros AFTER, then judge sufficiency on the nonzero count
    # (zeros must not pad the count past the min-n guard and hide sign-clustering).
    numeric = [r for r in res if isinstance(r, (int, float)) and not isinstance(r, bool)]
    if len(numeric) < len(res):
        return ("CAUTION", "some residuals non-numeric — fix input before judging residual structure", [])
    signs = [1 if r > 0 else 0 for r in numeric if r != 0]
    # All residuals essentially zero => a (near-)perfect fit, not a systematic bias. Don't false-FAIL it.
    if len(signs) == 0:
        return ("PASS", f"residuals essentially zero ({len(numeric)} pts) — (near-)perfect fit; nothing to test", [])
    if len(signs) < 8:
        return ("CAUTION", f"only {len(signs)} nonzero residuals — too few for a runs test; eyeball the residual plot", [])
    n1, n2 = sum(signs), len(signs) - sum(signs)
    if n1 == 0 or n2 == 0:
        return ("FAIL", f"all residuals same sign ({len(signs)} pts) — systematic bias, model is wrong", [])
    runs = 1 + sum(1 for i in range(1, len(signs)) if signs[i] != signs[i - 1])
    n = n1 + n2
    mu = 1 + 2 * n1 * n2 / n
    var = (2 * n1 * n2 * (2 * n1 * n2 - n)) / (n * n * (n - 1)) if n > 1 else 0
    if var <= 0:
        return ("CAUTION", "runs-test variance degenerate", [])
    z = (runs - mu) / math.sqrt(var)
    detail = [f"  runs={runs}, expected≈{mu:.1f}, z={z:.2f} (n+={n1}, n-={n2})"]
    # One-sided: only TOO FEW runs (z < 0) means sign-clustering = systematic structure / wrong model.
    # Too MANY runs (z > 0) is anti-correlation, not a goodness-of-fit failure, so don't flag it.
    if z < -1.96:
        return ("FAIL", f"residuals sign-clustered (z={z:.2f}<-1.96) — systematic structure; high R² is misleading", detail)
    if z < -1.0:
        return ("CAUTION", f"residuals lean toward clustering (z={z:.2f}) — eyeball the residual plot", detail)
    return ("PASS", "residuals consistent with random noise", detail)


def check_dof(d):
    params, n_data = d.get("params", {}), d.get("n_data")
    p = len(params)
    if not n_data:
        return ("CAUTION", f"{p} free params; no 'n_data' supplied — can't assess overfitting", [])
    if p == 0:
        return ("PASS", "no free parameters", [])
    ratio = n_data / p
    detail = [f"  {p} free params vs {n_data} data points (ratio {ratio:.1f} pts/param)"]
    if ratio < 2:
        return ("FAIL", f"only {ratio:.1f} data points per parameter — overfitting / unidentifiable", detail)
    if ratio < 5:
        return ("CAUTION", f"{ratio:.1f} pts/param is thin — check identifiability", detail)
    return ("PASS", f"{ratio:.1f} data points per parameter", detail)


def check_identifiability(d):
    params, stderr = d.get("params", {}), d.get("stderr", {})
    corr, corr_names = d.get("corr"), d.get("corr_names", [])
    rows, worst = [], "PASS"
    order = {"PASS": 0, "CAUTION": 1, "FAIL": 2}
    # CV from stderr
    for name, se in (stderr or {}).items():
        if name not in params:
            continue
        val = params[name]
        if not isinstance(se, (int, float)) or isinstance(se, bool) or not isinstance(val, (int, float)) or isinstance(val, bool):
            continue
        # A param pinned at exactly 0 with nonzero stderr is maximally unidentifiable — don't silently skip.
        if val == 0:
            if se != 0:
                rows.append(f"  {name}: value=0 with stderr={se:g} — unconstrained (CV undefined); fix or reparametrize")
                if order["CAUTION"] > order[worst]:
                    worst = "CAUTION"
            continue
        cv = abs(se / val) * 100
        if cv > 100:
            rows.append(f"  {name}: CV={cv:.0f}% (stderr > value) — NOT identifiable; fix to a literature value")
            worst = "FAIL"
        elif cv > 50:
            rows.append(f"  {name}: CV={cv:.0f}% — poorly constrained")
            if order["CAUTION"] > order[worst]:
                worst = "CAUTION"
    # pairwise correlation
    if corr and corr_names:
        n = len(corr_names)
        for i in range(n):
            for j in range(i + 1, n):
                try:
                    c = corr[i][j]
                except (IndexError, TypeError):
                    continue
                if abs(c) > 0.95:
                    rows.append(f"  {corr_names[i]}~{corr_names[j]}: |corr|={abs(c):.2f} — compensation/trade-off; not independently identifiable")
                    if order["CAUTION"] > order[worst]:
                        worst = "CAUTION"
    if not stderr and not corr:
        return ("CAUTION", "no stderr/corr supplied — identifiability not assessed (pass covariance!)", [])
    if not rows:
        return ("PASS", "no identifiability red flags", [])
    return (worst, "identifiability concerns", rows)


def check_mass_balance(d):
    """Conservation: do the measured species sum to the conserved t0 total within tolerance?
    A model / dataset where mass (carbon, cofactor pool) doesn't close is wrong or mis-extracted,
    independent of fit quality. This is the 'measured total = product + byproducts + residual substrate
    vs t0' conservation check, generalized. A closure FAR below 1.0 also signals a measurement gap that must be
    normalized away before use (don't silently fit to a leaking basis)."""
    mb = d.get("mass_balance")
    if not mb:
        return ("CAUTION", "no 'mass_balance' supplied — conservation not checked (pass t0_total + species!)", [])
    t0 = mb.get("t0_total")
    species = mb.get("species", {})
    tol = mb.get("tol_frac", 0.10)
    label = mb.get("label", "conserved total")
    # t0 must be a positive number (a conserved total can't be <=0).
    if not isinstance(t0, (int, float)) or isinstance(t0, bool) or t0 <= 0 or not species:
        return ("CAUTION", "mass_balance needs t0_total (positive number) + non-empty species — skipped", [])
    # Validate species values: each must be a non-negative number (a concentration < 0 is impossible,
    # and a negative species could otherwise cancel an over-shoot into a false PASS).
    nums, bad, neg = {}, [], []
    for k, v in species.items():
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            bad.append(k)
        elif v < 0:
            neg.append(k)
        else:
            nums[k] = v
    if neg:
        return ("FAIL", f"species {neg} are NEGATIVE — impossible concentration; check extraction/sign", [f"  negative species: {neg}"])
    if bad:
        return ("CAUTION", f"species {bad} are non-numeric (None/str) — fix the extraction before trusting balance", [f"  non-numeric species: {bad}"])
    total = sum(nums.values())
    closure = total / t0
    breakdown = " + ".join(f"{k}={v:g}" for k, v in nums.items())
    detail = [f"  {label}: Σspecies={total:g} ({breakdown}) vs t0={t0:g} → closure={closure*100:.1f}%"]
    dev = round(closure - 1.0, 9)  # round kills float noise (110/100-1.0 == 0.10000000000000009)
    # OVERSHOOT is treated asymmetrically: mass exceeding the conserved total is physically impossible,
    # so it is NEVER excused as in-tolerance and NEVER sent to the undershoot/normalize remedy. Any
    # closure meaningfully above 100% is at least a CAUTION; beyond +tol it is a hard FAIL.
    if dev > tol:
        return ("FAIL", f"closure {closure*100:.1f}% exceeds +{tol*100:.0f}% — species sum > t0; impossible, check units/columns", detail)
    if dev > 0:
        return ("CAUTION", f"closure {closure*100:.1f}% > 100% — slight overshoot; mass can't exceed t0, check measurement/units", detail)
    # UNDERSHOOT side: within tol is fine; a gap means normalize; half-missing means mis-extraction.
    if dev >= -tol:
        return ("PASS", f"mass closes to {closure*100:.1f}% (within ±{tol*100:.0f}%)", detail)
    if closure < 0.5:
        return ("FAIL", f"closure only {closure*100:.1f}% — half the mass is unaccounted; suspect wrong column/species or unit", detail)
    return ("CAUTION", f"closure {closure*100:.1f}% (<100%−{tol*100:.0f}%) — measurement gap; normalize basis before use (don't fit to leaking total)", detail)


def main():
    ap = argparse.ArgumentParser(description="Scientific validity gate for fit/optimization results.")
    ap.add_argument("--json", help="path to results JSON (else reads stdin)")
    ap.add_argument("--emit-json", action="store_true", help="also print machine-readable JSON verdict")
    args = ap.parse_args()

    raw = open(args.json, encoding="utf-8").read() if args.json else sys.stdin.read()
    try:
        d = json.loads(raw)
    except Exception as e:
        print(f"❌ could not parse input JSON: {e}", file=sys.stderr)
        sys.exit(2)
    # Top-level must be a JSON object; a list/scalar would crash every .get() downstream.
    if not isinstance(d, dict):
        print(f"❌ input must be a JSON object (got {type(d).__name__})", file=sys.stderr)
        sys.exit(2)
    # 'params' must be a dict if present (a list/scalar would crash several checks). Fail loud but clean.
    if "params" in d and not isinstance(d["params"], dict):
        print(f"❌ 'params' must be an object/dict (got {type(d['params']).__name__})", file=sys.stderr)
        sys.exit(2)

    ranges = dict(PHYSICAL_RANGES)
    extra = d.get("ranges")
    if isinstance(extra, dict):
        ranges.update(extra)

    # Run each check in isolation: a bug or malformed sub-input in one check must NOT abort the others
    # and must NOT masquerade as a scientific FAIL. A check that raises becomes an ERROR row (exit 3),
    # distinct from a real FAIL (exit 1) so a pipeline can tell "tool broke" from "science is wrong".
    check_fns = [
        ("Axis1 physical_range", lambda: check_physical_range(d, ranges)),
        ("Axis1 bound_hit",      lambda: check_bound_hit(d)),
        ("Axis1 identifiability", lambda: check_identifiability(d)),
        ("Axis2 residual_runs",  lambda: check_residual_runs(d)),
        ("Axis2 dof",            lambda: check_dof(d)),
        ("Axis3 unit_sanity",    lambda: check_unit_sanity(d)),
        ("Axis3 mass_balance",   lambda: check_mass_balance(d)),
    ]
    checks = []
    any_error = False
    for label, fn in check_fns:
        try:
            checks.append((label, fn()))
        except Exception as e:
            any_error = True
            checks.append((label, ("ERROR", f"check crashed: {type(e).__name__}: {e}", [])))

    icon = {"PASS": "✅", "CAUTION": "⚠️ ", "FAIL": "❌", "ERROR": "🛑"}
    print("=" * 70)
    print("SCIENTIFIC VALIDATION  (mechanical checks — judge Axis3/4 manually too)")
    print("=" * 70)
    any_fail = any_caution = False
    out = {}
    for label, (verdict, summary, rows) in checks:
        print(f"{icon.get(verdict, '?')} {label}: {verdict} — {summary}")
        for r in rows:
            print(r)
        out[label] = {"verdict": verdict, "summary": summary, "detail": rows}
        if verdict == "FAIL":
            any_fail = True
        if verdict == "CAUTION":
            any_caution = True

    print("-" * 70)
    if any_fail:
        overall = "❌ REJECT — at least one axis FAILED. Do NOT report/merge this number; fix the flagged axis."
    elif any_caution:
        overall = "⚠️  CAUTION — usable only with the caveats above resolved/stated."
    else:
        overall = "✅ MECHANICAL CHECKS PASS — now finish Axis3 (conservation/SSOT) + Axis4 (independent reproduction) manually."
    print(overall)
    print("REMINDER: high R²/optimizer-SUCCESS is NOT validity. A delegated/remote number stays PROVISIONAL until an independent 1-line reproduction agrees.")

    if any_error:
        print("🛑 one or more checks ERRORed (tool/input problem, NOT a science verdict) — see rows above.")

    if args.emit_json:
        print("\n--- JSON ---")
        print(json.dumps({"checks": out, "any_fail": any_fail, "any_caution": any_caution, "any_error": any_error}, ensure_ascii=False))

    # Exit-code contract: 1 = a real scientific FAIL (gate should block); 3 = tool/input error
    # (distinct so CI doesn't mistake a crash for a science failure); 0 = pass/caution only.
    if any_fail:
        sys.exit(1)
    if any_error:
        sys.exit(3)
    sys.exit(0)


if __name__ == "__main__":
    main()
