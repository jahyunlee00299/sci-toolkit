# TYPO_PATTERNS, PUNCT_SPACE_FLAGS, COFACTOR_SPACE_FLAGS (Auto-detection regex)

> Implemented by `skills/manuscript-pipeline/scripts/body_typo_lint.py`.

## 12. TYPO_PATTERNS (Auto-detection regex)

```python
TYPO_PATTERNS = [
    (r'\bul\b', 'µL'), (r'\buL\b', 'µL'), (r'\buM\b', 'µM'),
    (r'\bml\b', 'mL'), (r'\bhr\b', 'h'), (r'\bhrs\b', 'h'), (r'\bRPM\b', 'rpm'),
    (r'℃', '°C'), (r'(\d)°C', r'\1 °C'), (r'(\d)mM', r'\1 mM'),
    (r'n=(\d)', r'n = \1'), (r'mean ± standard deviation', 'mean ± SD'),
    (r'pH (\d)-(\d)', r'pH \1–\2'), (r'(\d+)-(\d+) °C', r'\1–\2 °C'),
    # NADP first — substituting 'NAD+' first would corrupt the front of 'NADP+'.
    # Don't add a trailing \b: '+' is a non-word character, so in most real
    # sentences where it's followed by whitespace or punctuation (e.g.
    # 'NAD+ regeneration'), the boundary never fires and the rule is
    # effectively dead (confirmed by measurement, 2026-07-23). 'NAD+-dependent'
    # is also a correction target — the superscript form is still correct
    # even in a hyphenated modifier (§3).
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
    # When adding an extension here, also update the matching list in
    # body_typo_lint.py (fixing only one side lets the doc and the
    # implementation drift apart). Rmd/Rproj especially need this since they
    # start with a capital letter and trip the "capital after a period" pattern.
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


---

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

