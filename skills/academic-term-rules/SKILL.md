---
name: academic-term-rules
description: "Biotech/biochemistry nomenclature standards — species italic, gene/protein naming, coenzyme notation, unit formatting, kinetics symbols, figure captions, dash rules, American spelling, E-factor/green-metric notation, single-source-of-truth, TYPO_PATTERNS. SSOT layer skill referenced by manuscript-pipeline QC agents, journal-ppt, and pptx reviewer."
---

# Academic Term Rules — Biotech/Biochemistry Nomenclature Standards

> Layer skill: loaded by QC agents in manuscript-pipeline (Phase 3, P10) and journal-ppt.
> Each rule is classified as [Auto-detectable] or [Manual review required].
> Full per-rule tables live under `references/<topic>.md`, one file per category group below —
> read the linked file for the actual rule content; this index only carries the one-line summary,
> the hard "never" rules, and the pointers other skills cite by section number (`§N`).

## Execution Method

This is a **layer skill** — not invoked directly. It is read by QC agents during document review.
When an agent needs nomenclature rules, it reads this SKILL.md file, then follows the pointer to
the relevant `references/<topic>.md` file for the full rule table.

---

## Rule categories

| § | Category | Summary | Full rules |
|---|---|---|---|
| 1 | Biological Nomenclature | Species/genus italics, strain codes, first-mention rule | `references/nomenclature.md` |
| 2 | Gene and Protein/Enzyme Nomenclature | Gene italic-lowercase vs. protein roman-caps, species-prefix table, EC numbers | `references/nomenclature.md` |
| 3 | Coenzyme and Chemical Nomenclature | NAD⁺/NADH family, chemical formula sub/superscripts, first-mention abbreviations | `references/nomenclature.md` |
| 4 | Unit Notation [Auto-detectable] | µL/mL/µM, °C, rpm, number-unit spacing | `references/units_kinetics_stats.md` |
| 5 | Enzyme Kinetics Notation | *K*m, *k*cat, *V*max, *k*cat/*K*m, *n*H italics | `references/units_kinetics_stats.md` |
| 6 | Statistical Notation [Auto-detectable] | mean ± SD, `n = 3`, *p*-value, test-method naming | `references/units_kinetics_stats.md` |
| 7 | Figure Caption Rules | Required caption components (number/title/panels/conditions/n/abbrev.) | `references/figures_captions.md` |
| 7c | Citation-order diagnosis (`manuscript_ref_order.py`) | "cited out of order" ≠ "move the caption" — diagnose against heading outline first | `references/figures_captions.md` |
| 8 | Punctuation — Dash Distinction [Auto-detectable] | hyphen vs. en dash vs. em dash | `references/punctuation_citations.md` |
| 8a | Citation Number Placement (numeric-superscript journals) [Auto-detectable] | citation number goes after terminal punctuation | `references/punctuation_citations.md` |
| 9 | Plasmid and Molecular Biology Notation | Plasmid italics, restriction enzyme caps, primer/PCR/Tm | `references/nomenclature.md` |
| 10 | Reaction Condition Notation Standard | Substrate → Buffer → Temperature → Time → Shaking speed order | `references/units_kinetics_stats.md` |
| 10a | Internal Cross-Reference Prose [Auto-detectable, FLAG-ONLY] | never cite the manuscript's own section numbers in running prose | `references/punctuation_citations.md` |
| 11 | Superscript / Subscript Rules | which tokens must render as `<w:vertAlign>` super/subscript, docx XML pattern | `references/superscript_subscript.md` |
| 12 | TYPO_PATTERNS (Auto-detection regex) | mechanical 1:1 substitutions — units, NAD⁺/NADP⁺, common misspellings | `references/typo_patterns.md` |
| 12a | PUNCT_SPACE_FLAGS [Auto-detectable, FLAG-ONLY] | missing space after `. , ; :` — flag-only, needs whitelist + human check | `references/typo_patterns.md` |
| 12b | COFACTOR_SPACE_FLAGS [Auto-detectable, FLAG-ONLY] | missing space after cofactor charge symbol/token (`NAD⁺regeneration`) | `references/typo_patterns.md` |
| 13 | Table Formatting Standards | Three-line (booktabs) rule, title/footnote placement, docx XML borders | `references/tables.md` |
| 14 | Reference Quality Standards | Journal tier classification, citation-count thresholds, red flags | `references/reference_quality.md` |
| 15 | American Spelling [Auto-detectable] | British → American spelling table + `SPELLING_PATTERNS` regex | `references/spelling.md` |
| 16 | Green-Chemistry Metric Notation | *E*-factor italic rule, sEF/cEF, PMI/AE/RME | `references/green_metrics_ssot.md` |
| 17 | Single Source of Truth (numeric consistency) | one canonical rawdata file per labelled quantity; citation-cluster and arrow-symbol rules | `references/green_metrics_ssot.md` |

---

## Hard "never" rules (apply regardless of which reference file you consulted)

- **Never** leave a species name un-italicized on first mention, and never drop the genus on
  first mention (§1).
- **Never** italicize a protein/enzyme name — only the gene is italic (§2).
- **Never** write `NAD+`/`NADP+` with a plain ASCII `+` in final text — superscript `⁺` is
  required (§3); see `references/typo_patterns.md` for the flag-only exceptions where an
  ASCII `+` is the correct *detection* target, not the correct *output*.
- **Never** blind-replace a `FLAG-ONLY` pattern (§10a, §12a, §12b) — every match must be checked
  against its whitelist and confirmed by a human before any text changes. These are review aids,
  not `TYPO_PATTERNS`-style mechanical substitutions.
- **Never** cite the manuscript's own numbered sections in running prose ("Section 3.3") — rewrite
  to name the content, a Figure/Table/Scheme/Equation number, or a named part instead (§10a).
  Figure/Table/Scheme/Equation numbers and SI callouts are the allowed anchors.
- **Never** use a vertical or inside-horizontal rule in a table — three-line (booktabs) style only,
  and footnotes use superscript letters/symbols, never numbers that would collide with data (§13).
- **Never** rewrite a proper noun, journal name, or cited title into American spelling — preserve
  as published (§15).
- **Never** use a reaction-arrow symbol (`X → Y`) in body text — use `-to-`/natural language;
  Scheme/equation/table figures are exempt (§17).
- **Never** let body/table/figure values for the same labelled quantity drift apart — trace every
  occurrence back to one canonical rawdata file and fix the source, not each site individually (§17).

---

## TYPO_PATTERNS (Auto-detection regex) — pointer

The full `TYPO_PATTERNS`, `PUNCT_SPACE_FLAGS`/`PUNCT_SPACE_WHITELIST`, and
`COFACTOR_SPACE_FLAGS`/`COFACTOR_SPACE_WHITELIST` regex tables (§12/12a/12b) live in
`references/typo_patterns.md`. `skills/manuscript-pipeline/scripts/body_typo_lint.py` implements
these patterns in code — when editing either side, keep the two in sync (the docstring there
cross-references this file explicitly).
