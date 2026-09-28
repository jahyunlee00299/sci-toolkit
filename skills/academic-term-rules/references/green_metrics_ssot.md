# Green-Chemistry Metric Notation and Single Source of Truth

## 16. Green-Chemistry Metric Notation

**E-factor**: italicize **only the *E*** — the symbol *E* is a variable; the rest is roman.

| Incorrect | Correct |
|---|---|
| E-factor (all roman) | *E*-factor |
| *E-factor* (all italic) | *E*-factor |
| sEF / cEF (italic) | sEF, cEF (roman — these are labels, not single-variable symbols) |
| PMI, AE, RME | roman (process mass intensity, atom economy, reaction mass efficiency) |

- Simple / complete E-factor: **sEF** (water-excluded) and **cEF** (water-included). Define both at first use.
- Catalyst-inclusive vs reagent-only basis must be stated explicitly in the table footnote.
- docx XML: italic only the `E` run — `<w:r><w:rPr><w:i/><w:iCs/></w:rPr><w:t>E</w:t></w:r><w:r><w:rPr><w:i w:val="0"/></w:rPr><w:t>-factor</w:t></w:r>`


---

## 17. Single Source of Truth (numeric consistency)

Body / table / figure values for the same labelled quantity (sEF, cEF, titer, yield, the cost metric, *ee*, …) must trace back to **one canonical rawdata file**. Never reconcile a conflict by editing one site silently. (See manuscript-pipeline Consistency Gate.)

- Body citation cluster ≤ 3; a paragraph that references "Table N" may not use a cluster.
- No reaction-arrow symbol `X → Y` in body text → use `-to-` / natural language instead (Scheme/equation/table figures are exempt).

---

## 6a. Derived numbers must reproduce from the PRINTED operands [Auto-detectable, FLAG-ONLY]

Any ratio, fold-change, percentage, or difference stated in the text must be reproducible by a
reader using only the values **printed in the same document** (Table, Figure, or text). The reader
cannot see the full-precision source, so a derived number that only reproduces from the SSOT
(above) is, to them, simply wrong.

This does not replace the SSOT rule above — the two are different layers:

| Layer | Source of truth | Purpose |
|---|---|---|
| Verification / internal reporting | SSOT full precision (fit output, script output) | is the number correct at all |
| Number printed in the manuscript | operands as displayed in the same document | can the reader reproduce it |

**When the two paths disagree after rounding, one of the two must be changed — never leave them
disagreeing.** Pick by which precision is free to move:

- **(a) Raise the table's displayed precision** by one significant figure so both paths round to the
  same value. Use when the extra digit is physically meaningful and the journal/table style allows
  it.
- **(b) Restate the derived value as computed from the displayed operands.** Use when the display
  precision is fixed by measurement precision or journal style
  (e.g. `1.74 / 0.32 = 5.4375 → 5.4`; a full-precision `5.4686 → 5.5` must not be printed while the
  table still shows `0.32`).

**Forbidden**: printing the full-precision derived value while leaving the operands at fewer digits.

**Scope**: manuscript body, abstract, captions, **and response-to-reviewer / cover letters** — a
reviewer checks a rebuttal number against the printed table, not against the raw fit.

**Self-check after writing any derived number** (do it at write time, not in QC):

```python
# FLAG-ONLY patterns — every hit needs a manual recompute from the printed operands
DERIVED_NUMBER_FLAGS = [
    r'\d+(?:,\d{3})*(?:\.\d+)?[-\s]fold',        # 5.4-fold, 1,009-fold
    r'(?:increased|decreased|improved|reduced)\s+(?:by\s+)?\d+(?:\.\d+)?\s*(?:%|-fold|times)',
    r'\bratio\s+of\s+\d+(?:\.\d+)?',
    r'\d+(?:\.\d+)?\s*(?:%|times)\s+(?:higher|lower|greater|faster|more|less)',
]
# For each hit: recompute from the operands AS PRINTED, round to the derived value's
# displayed precision, and require equality. Log the operand source (table/cell) with the result.
```

### Round with ROUND_HALF_UP — never Python's bare `round()`

Python's `round()` is **banker's rounding**: it breaks an exact tie toward the even digit, so
`round(2.25, 1)` is `2.2`, not `2.3`. Manuscripts round half **up**.

```python
from decimal import Decimal, ROUND_HALF_UP

def round_half_up(x, places):
    q = Decimal(1).scaleb(-places)                 # places=1 -> Decimal("0.1")
    return Decimal(repr(x)).quantize(q, rounding=ROUND_HALF_UP)
```

Two separate traps, and the second is the one that actually causes false-positive findings:

- **Trap 1 — banker's rounding on a true tie.** `round(2.5) == 2`, `round(0.125, 2) == 0.12`,
  `round(1.005, 2) == 1.0`. All three disagree with what a manuscript prints. Always use
  `round_half_up`.
- **Trap 2 — retyping the quotient instead of computing it.** A check that evaluates
  `round(2.25, 1)` gets `2.2` and flags a manuscript's `2.3-fold` as wrong. But if the real operands
  are `38.7 / 17.2 == 2.2500000000000004`, that is **not** a tie, and even bare `round()` on the
  actual division returns `2.3`. The false positive comes from **typing the rounded intermediate
  `2.25` into the check** rather than dividing the printed operands — the manuscript was correct.

```python
round_half_up(38.7 / 17.2, 1)   # -> Decimal('2.3')   correct: compute from the operands
round(2.25, 1)                  # -> 2.2               wrong: retyped intermediate + banker's
```

So the rule is **both**: divide the operands *as printed* in the same expression, and round with
`ROUND_HALF_UP`. Never let a hand-copied intermediate enter the check. Use `Decimal(repr(x))`, not
`Decimal(x)`: the latter takes the exact binary expansion and can tip a genuine tie the wrong way.

**Before reporting any derived-number mismatch, recompute it this way.** If the two paths agree
once computed correctly, there is no finding. Report the operand source alongside every derived
number (file/table + cell + formula + intermediate value) so a wrong-layer input is visible on sight.
