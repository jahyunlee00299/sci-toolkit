---
name: academic-term-rules
description: "Biotech/biochemistry nomenclature standards — species italic, gene/protein naming, coenzyme notation, unit formatting, kinetics symbols, figure captions, dash rules, American spelling, E-factor/green-metric notation, single-source-of-truth, TYPO_PATTERNS. SSOT layer skill referenced by manuscript-pipeline QC agents, journal-presentation-maker, and pptx reviewer."
---

# Academic Term Rules — Biotech/Biochemistry Nomenclature Standards

> Layer skill: loaded by QC agents in manuscript-pipeline (Phase 3, P10) and journal-presentation-maker.
> Each rule is classified as [Auto-detectable] or [Manual review required].

## Execution Method

This is a **layer skill** — not invoked directly. It is read by QC agents during document review.
When an agent needs nomenclature rules, it reads this SKILL.md file.

---

## 1. Biological Nomenclature

- Genus·Species (*Genus species*): **Italic**, genus capitalized, species lowercase
  - First mention: *Escherichia coli*, thereafter: *E. coli*
- Strain code: No italics needed — BL21(DE3), K-12
- Species name alone forbidden: "cerinus" → "*Gluconobacter cerinus*"

| Incorrect | Correct |
|---|---|
| E.coli | *E. coli* |
| Bacillus subtilis (non-italic) | *Bacillus subtilis* |
| G. cerinus (first mention) | *Gluconobacter cerinus* |

---

## 2. Gene and Protein/Enzyme Nomenclature

**Gene name**: Italic, lowercase — *xylA*, *gldA*, *ptsG*

**Protein/Enzyme name**: No italics, capitalized or all caps — XylA, GDH, FDH

Species origin prefix (italic for genus abbreviation):

| Prefix | Organism |
|---|---|
| *Bs* | *Bacillus subtilis* |
| *Ec* | *Escherichia coli* |
| *Ps*/*Pf* | *Pseudomonas* sp. |
| *Gc* | *Gluconobacter cerinus* |
| *Ao* | *Aspergillus oryzae* |
| *Sc* | *Saccharomyces cerevisiae* |
| *Lp* | *Lactobacillus plantarum* |
| *Ag* | *Agrobacterium* sp. |

- Full name required at first mention: "*Xx*GDH (glucose dehydrogenase from *Xxxxx yyyyy*)"
- Enzyme common name: lowercase — glucose dehydrogenase / Abbreviation: uppercase — GDH
- EC number: EC 1.1.1.47 format
- Tagged proteins: tag NOT italic (MBP-, His-), prefix italic (*Ag*), name not italic (MDH)

---

## 3. Coenzyme and Chemical Nomenclature

**Coenzymes**: NAD⁺, NADH, NADP⁺, NADPH (superscript+ required) / ATP, ADP, AMP / FAD, FADH₂ / CoA

| Incorrect | Correct |
|---|---|
| NAD+, NADP+ | NAD⁺, NADP⁺ (superscript) |
| nadph | NADPH |
| AcP (informal) | acetyl phosphate (AcP) — full name at first mention |

**Chemical formula subscripts**: CO₂, H₂O, H₂O₂, O₂, Mg²⁺, Ca²⁺, Fe³⁺, NH₄⁺

**Substrate/Reagent abbreviations**: Full name + abbreviation in parentheses at first mention

---

## 4. Unit Notation [Auto-detectable]

| Incorrect | Correct |
|---|---|
| ul, uL | µL |
| ml | mL |
| uM, UM | µM |
| ℃ (Unicode symbol) | °C |
| 30°C (no space) | 30 °C |
| hr, hrs | h |
| min. | min |
| RPM | rpm |
| 50mM (no space) | 50 mM |

**Number-unit spacing rule**: Always include space — "50 mM", "30 °C", "6 h"

---

## 5. Enzyme Kinetics Notation

| Term | Correct notation | Note |
|---|---|---|
| Michaelis constant | *K*m or Km | KM, km, kM non-standard |
| turnover number | *k*cat or kcat | Kcat error |
| maximum velocity | *V*max or Vmax | vmax, VMAX error |
| catalytic efficiency | *k*cat/*K*m | kcat/Km |
| Hill coefficient | *n*H | nH |

---

## 6. Statistical Notation [Auto-detectable]

| Incorrect | Correct |
|---|---|
| mean ± standard deviation | mean ± SD |
| n=3 | n = 3 |
| n=3 (repeat type not specified) | n = 3 independent experiments |

- p-value: *p* < 0.05 (italic p recommended, space before/after operator)
- Test method explicit: "Student's t-test", "one-way ANOVA + Tukey's HSD"
- Error bar definition explicit: SD, SEM, 95% CI

---

## 7. Figure Caption Rules

**Required components**:
1. **Number**: "Figure 1." — "Figure." without number forbidden
2. **Title**: Bold, sentence case
3. **Panel description**: (a), (b) or (A), (B) — case consistency
4. **Experimental conditions**: Substrate concentration, temperature, pH, time, rpm
5. **Normalization basis**: When using "Relative amount", specify reference
6. **n and error**: "Data are mean ± SD (n = 3 independent experiments)"
7. **Abbreviations**: Full name on first mention in caption

---

### 7c. Citation-order diagnosis — heading-guided, "missing ref" ≠ "wrong order" [`manuscript_ref_order.py`]

A "figure/table cited out of numeric order" flag is NOT automatically a caption-move job. Before
touching anything, diagnose the CAUSE against the heading outline (headings encode the paper's
intended logical order). Run `manuscript_ref_order.py <docx>` and read its verdict:
- **AUDIT UNRELIABLE (draft lines)** — the manuscript still has `[INSERTED]`/`[DRAFT]`/data-pending
  caption text in the body. Fix the draft state FIRST; the order check is meaningless until then.
- **PHANTOM CITATION** (cited number with no caption) — leftover draft text or a numbering typo, not
  an ordering problem. Delete/renumber, don't move captions.
- **NEVER REFERENCED** — the item has zero body citation. The fix is to ADD a reference in the section
  that discusses its topic (author judgment on the exact sentence), NOT to move the caption.
- **MISMATCH with `[cross-section ...]` note** — the out-of-order first-cites live in different major
  sections (e.g. a Table forward-referenced in Methods §2.x vs first Results use in §3.x). This is a
  Methods forward-reference, usually legitimate — NOT a Results ordering defect. Verify before acting.
- **MISMATCH, same section, no note** — a genuine within-section ordering anomaly; reordering the
  narrative or the caption is plausible (still an author call — read the section).
- **SUPPLEMENTARY REFS EXCLUDED: N** — SI cross-refs (`Fig. S7`) are out of scope; an "OK" verdict does
  NOT certify SI citation integrity. Check those separately.
Rule of thumb (260706 audit of 6 manuscripts): most "order" flags are missing references or draft
artifacts, not captions in the wrong place. Insert the reference; move a caption only when the tool
shows a same-section, non-phantom, non-draft mismatch AND the section text confirms it.

---

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

## 9. Plasmid and Molecular Biology Notation

- **Plasmid name**: Italic recommended — *pET-28a*, *pUC19*, *pBAD/His*
- **Restriction enzyme name**: Capitalized first letter, lowercase rest — EcoRI, BamHI, NdeI
- **PCR**: primer (lowercase), PCR (uppercase), Tm — italic T, subscript m

---

## 10. Reaction Condition Notation Standard

**Standard order**: Substrate → Buffer → Temperature → Time → Shaking speed

Buffer name: lowercase (except proper nouns) — sodium phosphate buffer / Tris-HCl buffer

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

---

## 11. Superscript / Subscript Rules [Auto-detectable]

In .docx XML, check `<w:vertAlign w:val="superscript"/>` or `<w:vertAlign w:val="subscript"/>`.

### Must be superscript

| Text | Superscript part | Example |
|---|---|---|
| NAD⁺ | + | `NAD<sup>+</sup>` |
| NADP⁺ | + | `NADP<sup>+</sup>` |
| Mg²⁺, Ca²⁺, Fe³⁺, Zn²⁺ | charge number + sign | `Mg<sup>2+</sup>` |
| kcat | — (but see §5 for italic) | |

### Must be subscript

| Text | Subscript part | Example |
|---|---|---|
| CO₂ | 2 | `CO<sub>2</sub>` |
| H₂O | 2 | `H<sub>2</sub>O` |
| H₂O₂ | both 2s | `H<sub>2</sub>O<sub>2</sub>` |
| O₂ | 2 | `O<sub>2</sub>` |
| NH₄⁺ | 4 (sub) + (sup) | `NH<sub>4</sub><sup>+</sup>` |
| FADH₂ | 2 | `FADH<sub>2</sub>` |
| Km | m | `K<sub>m</sub>` (italic K) |
| Vmax | max | `V<sub>max</sub>` (italic V) |
| kcat | cat | `k<sub>cat</sub>` (italic k) |
| Tm (melting) | m | `T<sub>m</sub>` (italic T) |

### Common errors

| Error | Correct |
|---|---|
| NAD+ (plain) | NAD⁺ or NAD`<sup>+</sup>` |
| CO2 (plain) | CO₂ or CO`<sub>2</sub>` |
| H2O (plain) | H₂O |
| Km (plain, no sub) | K`<sub>m</sub>` |
| 10^5 or 10^-3 | 10⁵ or 10⁻³ (superscript exponent) |

### XML detection pattern

```xml
<!-- Correct superscript in docx XML -->
<w:r>
  <w:rPr><w:vertAlign w:val="superscript"/></w:rPr>
  <w:t>+</w:t>
</w:r>

<!-- Correct subscript -->
<w:r>
  <w:rPr><w:vertAlign w:val="subscript"/></w:rPr>
  <w:t>2</w:t>
</w:r>
```

---

## 12. TYPO_PATTERNS (Auto-detection regex)

```python
TYPO_PATTERNS = [
    (r'\bul\b', 'µL'), (r'\buL\b', 'µL'), (r'\buM\b', 'µM'),
    (r'\bml\b', 'mL'), (r'\bhr\b', 'h'), (r'\bhrs\b', 'h'), (r'\bRPM\b', 'rpm'),
    (r'℃', '°C'), (r'(\d)°C', r'\1 °C'), (r'(\d)mM', r'\1 mM'),
    (r'n=(\d)', r'n = \1'), (r'mean ± standard deviation', 'mean ± SD'),
    (r'pH (\d)-(\d)', r'pH \1–\2'), (r'(\d+)-(\d+) °C', r'\1–\2 °C'),
    # NADP 를 먼저 — 'NAD+' 를 먼저 치환하면 'NADP+' 의 앞부분이 깨진다.
    # 뒤쪽 \b 를 두지 말 것: '+' 는 non-word 문자라, 'NAD+ regeneration' 처럼
    # 뒤에 공백·구두점이 오는 실제 문장 대부분에서 경계가 성립하지 않아
    # 규칙이 사실상 죽는다(실측 확인, 2026-07-23). 'NAD+-dependent' 도
    # 정정 대상이 맞다 — 하이픈 수식어에서도 위첨자 표기가 정답이다(§3).
    (r'\bNADP\+', 'NADP⁺'), (r'\bNAD\+(?!P)', 'NAD⁺'),
    (r'supertanant', 'supernatant'), (r'seperati', 'separati'),
]

MANUAL_REVIEW = [
    "Gene name italics (Genus species)",
    "Gene name italics·lowercase (xylA, gldA, etc.)",
    "Protein/enzyme abbreviation full name at first mention",
    "Figure number present",
    "Caption experimental condition completeness",
    "Relative amount normalization basis explicit",
    "Error bar definition (SD/SEM/CI)",
    "n = 3 independent experiments notation",
    "Km determination [S] range appropriateness",
]
```

---

### 12a. PUNCT_SPACE_FLAGS — missing space after sentence punctuation [Auto-detectable, FLAG-ONLY]

**Why this was missed before**: §12 `TYPO_PATTERNS` above covers only *unit* spacing (µL, NAD⁺,
`(\d)°C`, etc.) — it has never had a pattern for a punctuation mark glued directly onto the next
word (e.g. `conversion.Here`, `charge.Supplementary`). No linter in `manuscript-pipeline/scripts/`
scans whole body-text sentence punctuation either (`nomenclature_lint.py` only looks at
captions/abbreviations/units). Net effect: this class of typo
had zero coverage anywhere in the toolchain until the an internal QC pass found it by hand. Added
per user root-cause request — see `body_typo_lint.py` for the enforcement side.

**These patterns are FLAG-ONLY — do NOT add them to `TYPO_PATTERNS` and do NOT blind-replace.**
Unlike the unit-spacing patterns above (which are safe 1:1 mechanical substitutions), inserting a
space after `.`/`,` is only safe once the whitelist below has been applied and a human has
confirmed the match is a real sentence boundary, not an abbreviation/URL/filename/decimal/initials.

```python
# Review-only — every match here MUST be checked against PUNCT_SPACE_WHITELIST before acting.
PUNCT_SPACE_FLAGS = [
    # period glued to next capitalized word: "conversion.Here" -> "conversion. Here"
    (r'\b([a-z]{2,})\.([A-Z][a-z]{2,})\b', 'missing space after period'),
    # comma glued to next word (either case): "charge,Supplementary" -> "charge, Supplementary"
    (r'\b([a-z]{2,}),([A-Za-z]{2,})\b', 'missing space after comma'),
    # semicolon / colon glued to next word
    (r'\b([a-z]{2,});([A-Za-z]{2,})\b', 'missing space after semicolon'),
    (r'\b([a-z]{2,}):([A-Za-z]{2,})\b', 'missing space after colon'),
]

# Exclusion list — a match overlapping any of these is a false positive, NOT a real
# missing-space typo. Apply before reporting, not after.
PUNCT_SPACE_WHITELIST = [
    # abbreviations with internal periods (2-4 letter fragments before/after the dot)
    r'\bn\.a\.', r'\be\.g\.', r'\bi\.e\.', r'\bs\.d\.', r'\bet al\.',
    r'\bvs\.', r'\bcf\.', r'\betc\.', r'\bca\.', r'\bviz\.',
    # multi-part initials / degree abbreviations
    r'\bU\.S\.A\.', r'\bPh\.D\.', r'\b[A-Z]\.[A-Z]\.',
    # domain names / URLs / DOIs
    r'\borcid\.org', r'\bdoi\.org', r'[a-z]+\.(com|org|net|edu)\b',
    # filenames (word.ext where ext is a known file extension)
    # 확장자를 추가할 때는 body_typo_lint.py 의 같은 목록도 함께 고칠 것
    # (한쪽만 고치면 문서와 구현이 어긋난다). Rmd/Rproj 는 대문자로 시작해
    # "마침표 뒤 대문자" 패턴에 걸리므로 특히 필요하다.
    r'\.(jpe?g|png|tiff?|docx?|xlsx?|pdf|csv|py|json|[Rr]md|[Rr]proj|ipynb|ya?ml|toml)\b',
    # decimal numbers (digit.digit, not letter.letter)
    r'\d\.\d',
]
```

Exclusion notes (apply the whitelist as an overlap check — if the flagged span intersects any
whitelist match, drop the finding):
- `n.a.`, `e.g.`, `i.e.`, `s.d.`, `et al.`, `vs.`, `cf.`, `etc.` — standard abbreviations; the
  letters before/after the dot are the abbreviation itself, not two glued words.
- `orcid.org`, `doi.org` and generic `word.tld` domain patterns — not sentence punctuation.
- `image1.jpeg`, `Fig1.png` and similar filenames — extension dot, not sentence-final.
- `3.14`, `0.05` — decimal point between digits; the regexes above only match `[a-z]` on both
  sides so digits are already excluded by construction, but the explicit whitelist entry guards
  compound cases (e.g. a filename containing digits).
- `U.S.A.`, `Ph.D.` — multi-part initials; each `X.` fragment is 1 letter, already below the
  `{2,}` threshold in `PUNCT_SPACE_FLAGS`, but listed explicitly since a wrong tweak to that
  threshold would otherwise silently start flagging these.
- Anything already covered by the §8 dash-range rules or §11 superscript rules is a different
  character class (`-`/`–` or `<w:vertAlign>`) and is out of scope here — do not double-flag.

### 12b. COFACTOR_SPACE_FLAGS — missing space after cofactor/superscript symbol [Auto-detectable, FLAG-ONLY]

**Why this was missed before**: §12a `PUNCT_SPACE_FLAGS` only covers sentence punctuation
(`. , ; :`) glued to the next word. It does not cover a cofactor symbol — a superscript charge
(`⁺`/`⁻`) or a fully-spelled reduced-cofactor token (`NADH`/`NADPH`) — glued directly onto the
following word with no space, e.g. `NAD⁺regeneration`, `NADP⁺formation`, `NADHoxidase`. This class
was found by hand in the same an internal QC pass that found §12a's gap (`NAD⁺regeneration`,
found in a re-check *after* `body_typo_lint.py` had already run and reported only the 2 §12a
punctuation hits — i.e. this is a distinct character class, not a §12a regex tweak). §12 unit-space
`TYPO_PATTERNS` do not cover this either — those match `NAD⁺` as a *complete* token needing a space
*before* it (e.g. `mMNAD⁺` -> `mM NAD⁺`), not a word glued *after* it.

**FLAG-ONLY — do NOT add to `TYPO_PATTERNS` and do NOT blind-replace.** Same rationale as §12a:
a human must confirm the match is a real word boundary, since `NAD⁺-dependent` (hyphenated
modifier) and `NAD⁺ regeneration` (already spaced) are both **correct** and must not be flagged.

**Important — the observed instance used ASCII `+`, not the unicode superscript `⁺`
(U+207A).** Word renders the run as superscript via `<w:vertAlign w:val="superscript"/>`
formatting, but the underlying `<w:t>` text is a plain `+` character. A pattern that only matches
`⁺`/`⁻` misses this — ASCII `+` MUST be in the character class or the real-world typo is not
caught. ASCII `-` is deliberately **excluded** from the class (unlike `+`) because it is
ambiguous with the correct hyphenated-modifier connector (`NAD+-dependent`); only the unicode
superscript minus (`⁻`, U+207B) is unambiguous since real prose never uses that codepoint for a
plain hyphen.

```python
# Review-only — every match here MUST be checked against COFACTOR_SPACE_WHITELIST before acting.
COFACTOR_SPACE_FLAGS = [
    # charge symbol (ASCII "+" superscript-formatted OR unicode ⁺/⁻) glued to next lowercase
    # word: "NAD+regeneration"/"NAD⁺regeneration" -> "NAD⁺ regeneration". Covers NAD/NADP with
    # +/⁺/⁻. ASCII "-" is NOT included (see note above — ambiguous with hyphen-modifier). The
    # charge symbol itself is not a word-char, so \b anchors naturally at that boundary.
    (r'\b(NAD\(?P?\)?[+⁺⁻]+)([a-z]{3,})\b', 'missing space after cofactor charge symbol'),
    # fully-spelled reduced-cofactor token glued to next lowercase word: "NADHoxidase" -> "NADH oxidase"
    # NADH/NADPH end in a word-char (H), so no \b exists between "H" and the next letter —
    # anchor on the literal token instead of relying on a boundary.
    (r'\bNAD(P?H)([a-z]{3,})\b', 'missing space after cofactor token'),
]

# Exclusion list — a match overlapping any of these is a false positive, NOT a real
# missing-space typo. Apply before reporting, not after.
COFACTOR_SPACE_WHITELIST = [
    # hyphenated modifier is correct as-is: "NAD⁺-dependent", "NAD+-dependent", "NADH-dependent"
    r'\bNAD\(?P?\)?H?[+⁺⁻]*-[a-z]',
]
```

Exclusion notes:
- `NAD⁺-dependent`, `NAD+-dependent`, `NADH-dependent`, `NAD⁺-selective` — hyphenated modifier;
  the hyphen is the correct connector, not a missing space. Because ASCII `-` is excluded from
  the `COFACTOR_SPACE_FLAGS` charge-symbol class by construction, the flag pattern itself never
  matches into the hyphen — the whitelist entry is a belt-and-suspenders guard in case a future
  tweak loosens the character class.
- `NAD⁺ regeneration`, `NAD+ regeneration`, `NADPH regeneration` — already correctly spaced; the
  regex requires the letter to be immediately adjacent (no space) to match, so these never match
  in the first place.
- `NAD+/NADH ratio`, `NADP+:NAD+` — `+` followed by `/` or `:` (not a lowercase letter) never
  matches the `[a-z]{3,}` half of the pattern.
- `NADH.`, `NADPH,` at a sentence/clause boundary followed by punctuation — not in scope here
  (that is §12a `PUNCT_SPACE_FLAGS` territory if the punctuation itself is glued to the *next*
  word); this rule only fires when a **lowercase letter** (`{3,}`) is glued directly onto the
  cofactor symbol/token.
- Do not confuse with §11 superscript-rendering rules (`<w:vertAlign>` correctness) or §12 unit-
  space `TYPO_PATTERNS` (space *before* the cofactor token, e.g. `mMNAD⁺`) — this is a third,
  distinct character class: missing space *after* the cofactor symbol/token.

---

## 13. Table Formatting Standards (Biotech/Biochemistry Journals)

### Three-line table rule (booktab style)
- **Top rule** (thick): above column headers
- **Mid rule** (thin): below column headers
- **Bottom rule** (thick): below last data row
- **NO vertical lines** — never use column dividers
- **NO horizontal lines** between data rows (except for grouped sections: one thin line)

### Table title
- Placed **above** the table (unlike figure legends which go below)
- Format: **Table N.** Bold number + period, then sentence-case title (not bold)
- Example: **Table 1.** Bacterial strains and plasmids used in this study.
- No period at end of title is acceptable in some journals — pick one style and be consistent

### Table footnotes
- Placed **below** the table
- Marked with superscript lowercase letters (ª, ᵇ, ᶜ) or symbols (†, ‡) — not numbers (numbers conflict with data)
- First footnote: define all abbreviations used in the table that were not defined in the main text
- Subsequent footnotes: clarify specific cells, conditions, or sources

### Column header rules
- Sentence case (not ALL CAPS)
- Units in parentheses on same line: "Concentration (mM)" or separate subheader row
- Italic for gene/species-derived symbols (*K*m, *k*cat, *V*max)
- Align: text columns left, numeric columns right or decimal-aligned

### Data cell rules
- Numerical data: consistent decimal places within a column
- "–" (en dash) for not determined / not applicable (never blank, never "N/A" unless defined)
- Mean ± SD format in cells; n stated in footnote or column header

### In-text reference
- "Table 1" (capital T, no abbreviation) when referring to a specific table
- "(Table 1)" in parenthetical citation

### docx XML implementation
- Borders: top/bottom = `<w:top>/<w:bottom>` with `w:sz="12"` (thick); mid = `w:sz="6"` (thin)
- No left/right/insideV borders on any cell
- InsideH borders: only on header row bottom (= mid rule); none between data rows
- Cell padding: top/bottom 80 twips, left/right 120 twips

```python
# Three-line table border pattern for docx XML
# CRITICAL: use w:start/w:end (NOT w:left/w:right) in both tcBorders and tcMar
# CRITICAL: element order must be top → start → bottom → end (schema-enforced)

# Header row cells: thick top + thin bottom, no start/end
# <w:tcBorders>
#   <w:top w:val="single" w:sz="12" w:space="0" w:color="000000"/>
#   <w:start w:val="none" w:sz="0" w:space="0" w:color="auto"/>
#   <w:bottom w:val="single" w:sz="6" w:space="0" w:color="000000"/>
#   <w:end w:val="none" w:sz="0" w:space="0" w:color="auto"/>
# </w:tcBorders>

# Last data row: thick bottom only
# Data rows: all none

# tcMar padding (also uses start/end, same order):
# <w:tcMar>
#   <w:top w:w="80" w:type="dxa"/>
#   <w:start w:w="120" w:type="dxa"/>
#   <w:bottom w:w="80" w:type="dxa"/>
#   <w:end w:w="120" w:type="dxa"/>
# </w:tcMar>
```

---

## 14. Reference Quality Standards

Used by manuscript-pipeline Phase 3.5 Deep Reference QC agents.

### Journal Tier Classification

| Tier | Criteria | Examples |
|---|---|---|
| 1 | IF > 30 or field-leading | Nature, Science, Cell, PNAS, Lancet, NEJM |
| 2 | IF 10-30 or top specialized | Angew. Chem., ACS Catal., Metab. Eng., Biotechnol. Bioeng. |
| 3 | IF 3-10 | Enzyme Microb. Technol., Process Biochem., Bioresour. Technol. |
| 4 | IF < 3 or unknown | Flag for review |

### Citation Count Thresholds (age-adjusted)

| Paper Age | Low | Noteworthy | Highly Cited | Landmark |
|---|---|---|---|---|
| 0-3 years | <5 | 20+ | 100+ | 500+ |
| 3-7 years | <20 | 100+ | 500+ | 1000+ |
| 7+ years | <50 | 500+ | 1000+ | 5000+ |

### Recency Scoring
- Review papers: >50% refs within last 5 years expected
- Research papers: >30% refs within last 5 years expected
- Flag: key claims citing only refs >10 years old without recent confirmation

### Red Flags
- Predatory journal (check against known lists)
- Retracted paper (CrossRef retraction status)
- Preprint cited as published (bioRxiv/medRxiv without DOI update)
- Self-citation ratio >30% of total refs
- >5 refs from same author group (citation ring concern)

---

## 15. American Spelling [Auto-detectable]

Use American spelling throughout (per user policy). Apply to body, tables, captions.

| British | American |
|---|---|
| titre | titer |
| optimise / optimisation | optimize / optimization |
| characterise / characterisation | characterize / characterization |
| analyse | analyze |
| catalyse / catalysed | catalyze / catalyzed |
| colour | color |
| fibre | fiber |
| litre | liter (but unit symbol stays **L**, mL) |
| labelled / labelling | labeled / labeling |
| modelling | modeling |
| neighbour | neighbor |
| centre | center |
| sulphur / sulphate | sulfur / sulfate |

```python
SPELLING_PATTERNS = [
    (r'\btitre\b', 'titer'), (r'\boptimis', 'optimiz'), (r'\bcharacteris', 'characteriz'),
    (r'\banalyse\b', 'analyze'), (r'\bcatalys', 'catalyz'), (r'\bcolour\b', 'color'),
    (r'\bfibre\b', 'fiber'), (r'\blabell', 'labell→label'), (r'\bmodelling\b', 'modeling'),
    (r'\bsulph', 'sulf'), (r'\bcentre\b', 'center'),
]
# CAUTION: do not rewrite proper nouns / journal names / cited titles (preserve as published).
```

---

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

- Body citation cluster ≤ 3; "Table N" 참조 paragraph는 cluster 금지.
- 본문 반응 화살표 `X → Y` 기호 금지 → `-to-` / 자연어 (Scheme·식·표는 허용).
