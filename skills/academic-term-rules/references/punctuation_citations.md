# Punctuation, Citation Placement, and Cross-Reference Prose

## 8. Punctuation — Dash Distinction [Auto-detectable]

| Symbol | Use | Example |
|---|---|---|
| `-` hyphen | Compound words | cell-free, dose-dependent |
| `–` en dash | Range | pH 3–5, 25–45 °C, 2020–2025 |
| `—` em dash | Insertion, emphasis | The result—surprisingly—showed... |


---

## 8a. Citation Number Placement (numeric-superscript journals) [Auto-detectable]

For journals using **numeric superscript** citation styles — **RSC** (Green Chemistry, etc.), **ACS**, **Nature**, **Cell**, Vancouver — the citation number goes **AFTER** the terminal punctuation, not before.

| Incorrect | Correct |
|---|---|
| `building blocks³³.` (number before period) | `building blocks.³³` (number after period) |
| `feasible⁵¹,` (number before comma) | `feasible,⁵¹` (number after comma) |
| `production[16-18].` (unformatted, number before period) | `production.¹⁶⁻¹⁸` (formatted, number after period) |

- Rule: superscript citation follows **. , ; :** — the number sits *outside* the punctuation mark.
- Verified against 2026-vintage Green Chemistry articles (d4gc02141j, d5gc03388h): all sentence-final citations render as `word.ⁿ` (number after period).
- **EndNote note:** with the correct RSC/ACS output style applied, "Update Citations and Bibliography" places the number after the period **automatically** — do NOT hand-move the period. A stray `[33].` (bracketed, number before period) usually means the field is still *unformatted*; format it rather than editing the period by hand.
- **Author–year / footnote styles are different:** parenthetical author–year `(Smith, 2020).` keeps the period outside the paren, and a few footnote styles place the marker before the period. This rule is specifically for **numeric superscript** journals.


---

## 10a. Internal Cross-Reference Prose [Auto-detectable, FLAG-ONLY]

**Do NOT refer to the manuscript's own numbered sections in running prose** — no
"Section 3.3", "in Section 2.4", "described in Section 2.2", "(Section 3.5)", "see Section 3.4".
Self-referential section numbering is fragile (breaks on renumber), reads as internal
lab-note bookkeeping rather than published prose, and most journals discourage or forbid it.

Fix by rewriting to name the *content*, not the section number:
- "the four macroalgal feedstocks evaluated (Section 3.3)" → "the four macroalgal feedstocks
  evaluated above" / "...evaluated (Fig. 4)" (point to the figure/table, or use above/earlier)
- "the engineered FDH described in Section 2.2" → "the engineered FDH described above"
  / name it directly ("the NADP⁺-active *Ps*FdhV9")
- "rate equations described in Section 2.4" → "rate equations described in the Methods"
  / "(SI Eq. S2–S8)" when a concrete anchor exists
- "presented in Section 3.5" → "presented below" / "in the techno-economic analysis"

Allowed anchors (keep): **Figure / Table / Scheme / Equation numbers**, **SI / Supplementary**
callouts (Fig. S7, Table S3, SI Note S1, Eq. S6), and generic named parts (**Methods**,
**Introduction**, **Supplementary Information**) *without* a number.

Detection regex (FLAG-ONLY — every hit is a rewrite candidate, author confirms):
```
\(?\bSections?\s+\d+(\.\d+)*\b
```
Exclude matches inside cited-reference titles or journal names (preserve as published).

