# Numeric verification gate (mandatory, non-negotiable)

## Why this exists

A batch placeholder-fill pass on three of the four prior invention disclosures produced real
arithmetic errors that survived a first "looks OK, has a footnote" review pass:
- Case A: claimed 91.9% yield from stated initial 154.2 mM and titer 112 mM — the true
  value is 112/154.2 = 72.6%. This number sat inside a **dependent claim's numeric limitation**
  (≥91%) — if filed as claimed, the claim's factual support would be false, which is
  patent-fatal (or at minimum grounds for a rejection/invalidation once challenged).
- Case B: claimed product productivity 87 mg/L/h vs. the correct 1.09 g/L ÷ 24 h = 45.4
  mg/L/h (~2× inflated).
- Case C: unsupported precision novelty claims ("본 발명 이전 보고된 바 없다") asserted before a
  prior-art search was complete.

The recurring failure mode: a footnote/citation on a filled number can itself be fabricated or
copied from a different condition/version. **Checking "does this claim have a citation" is not
verification. Re-deriving the arithmetic is.**

## What the gate checks (and what it does NOT check)

`scripts/verify_numeric_claims.py` re-derives a claimed value from the *other* numbers stated
alongside it (yield from initial+final, productivity from titer+time, an averaged value from
its components, ΔG from Keq) and flags disagreement beyond tolerance (default 2%).

This is **internal arithmetic self-consistency only**. It cannot tell you whether 154.2 mM was
itself the right initial concentration to cite — that needs cross-checking against the source
manuscript/rawdata cell, which is `adversarial-verifier`'s job, not this script's. Passing this
gate is necessary, not sufficient.

## When to run it

- After the Draft stage produces any numeric claim (§4 tables, §5 effects bullets, §7 실시예
  results) — build `claims.json` by hand listing every claim-critical number (anything that
  could plausibly become a claim limitation, i.e. yield/titer/ee/productivity/TTN thresholds).
- `--scan <docx>` is a recall aid for catching yield-triplet patterns in free prose — it will
  miss anything not matching its regex (different phrasing, tables, non-yield claim types). Do
  not treat a clean `--scan` result as proof the document has no arithmetic errors; it only
  proves the regex found nothing to check.
- Any UNRESOLVED result (division by zero, missing field, unknown claim type) is **not** a pass
  — it means the script could not check that claim at all. Investigate by hand.

## Escalation path when a MISMATCH is found

1. Do not silently "fix" the number to make the arithmetic self-consistent (e.g. changing 91.9%
   to 72.6% without checking which of the three numbers — initial/final/percentage — was
   actually wrong in the source).
2. Trace back to the source manuscript/rawdata cell for each of the three numbers independently.
3. If more than a one-line re-check is needed (e.g. the discrepancy implicates which experiment
   version/condition the number came from), escalate to the `adversarial-verifier` agent rather
   than resolving it inline — per this project's C-40 gate philosophy, a number entering a
   patent/manuscript/report is exactly the class of critical work that always gets independent
   re-verification, not a quick self-check.
4. Record the resolution (which value was wrong, why, source cell) — this is the kind of
   provenance note that should survive into the disclosure's changelog, not just fix-and-move-on.
