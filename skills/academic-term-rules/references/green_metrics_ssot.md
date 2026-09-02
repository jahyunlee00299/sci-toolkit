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
