# Proof / Galley Stage Number Audit

The publisher has typeset the accepted manuscript and asks the corresponding author
to approve it, usually within 48 hours. **Approval is final — no further change is
possible.** This file is the audit that runs in that window.

## Why this is a separate stage

`manuscript_qc_checklist.md` is the pre-submission docx QC: it compares the
manuscript against its SSOT (rawdata, fit scripts, figure repo). At proof stage you
have **no SSOT access** — you have a PDF the publisher generated, and the only
evidence available is the printed values themselves. So the question changes from
"does the manuscript match its source?" to **"do the printed values reproduce each
other?"**

That inversion is the whole point. The errors that survive to proof are precisely
the ones humans cannot see by reading: a table footnote is read as a footnote, never
multiplied against an abstract three pages away.

Measured on a real proof: the publisher's own 11 production queries missed a footnote
whose arithmetic contradicted the yield printed in the same table. Steps 1–7 below
caught it; reading did not.

## Trigger

Any of: "proof", "galley", "page proof", "proof corrections", "Proof Central",
"교정지", "proof 확인", a publisher mail saying a proof is ready, or a 24–48 h
correction deadline on an accepted paper.

---

## Step 0 — Get the typeset PDF, not the DOM

Proof portals (RSC Proof Central, Elsevier, Wiley) are token-authenticated JS apps.
Scraping the editor DOM is unreliable and may be blocked outright.

1. Locate the download link's `href` (a `find`-style element query returns it
   directly — do not hand-walk the DOM).
2. `curl` it to a local file.
3. Parse with `pypdf`.

⚠️ **Never use the PDF text extraction to judge typography.** Extraction destroys
italics, small caps and ligatures, and glues units to numbers (`5m MH2SO4` for
`5 mM H2SO4`). Reporting those as manuscript errors wastes the author's deadline.
Use the extraction for **numbers, spelling and reference strings only**; anything
about rendering needs a visual check of the PDF itself.

🔴 **Do not click Submit, Approve, or Complete.** The corresponding author owns that
action. Read, download, and report.

---

## Step 1 — Re-derive every printed number from printed operands

Collect every derived quantity — N-fold, ratio, percentage, difference, titer,
TTN, yield × concentration — and recompute each **with a script, never mentally**.

The pass criterion is `academic-term-rules` §6a: the value must reproduce from the
operands **printed in this document**. Reproducing only from full-precision SSOT is
a failure at this stage, because a referee checks against the printed table.

```python
# one row per claim: label, computed, printed, does it round to the printed value
def chk(label, computed, printed, ok):
    print(f'[{"OK  " if ok else "MISMATCH"}] {label}: computed {computed} / printed "{printed}"')
```

Cross-multiply across sections deliberately: a table footnote against the abstract,
a caption against the results text. That pairing is where the surviving errors live.

Worked example (260822): footnote read `68.79 mM × 150.13/1000 = 10.33 g L⁻¹`. The
footnote's own arithmetic was correct. But the same table and the abstract printed
96.4% yield at 70 mM, and 70 × 0.964 = 67.48, not 68.79 — the footnote implied
98.3%. Neither number is wrong in isolation; they are wrong **together**.

## Step 2 — Back-solve the stoichiometric convention

For atom economy, E-factor, or any mass-based metric, recompute from the equation as
printed and see which convention reproduces the printed value.

Worked example: AE 64.1% reproduces as 150.13/(150.13 + 68.007 + 15.999) = 64.12%
using the **sodium salt** of the cosubstrate. Its free acid (46.03) would give 70.8%.
The paper names the salt throughout, so the value is self-consistent — PASS.

Note what is *not* a finding: that equation does not mass-balance as printed (Na has
no home on the right side, 234.14 vs 212.15). The AE value is conventional and the
equation survived review; raising it at proof stage invites a rewrite under deadline
for no gain. Report it as an observation, not a correction.

## Step 3 — Cross-check rate constants against the prose

Where the text makes a quantitative claim about a constant printed in a table,
evaluate it.

Worked example: "at 50 h, 95.1% of enzyme activity remained" against the table's
`kd = 0.001 h⁻¹` → exp(−0.001 × 50) = 95.12%. Exact agreement. This is strong
evidence the numbers came from a real calculation rather than being transcribed, and
it is worth doing precisely because it can only pass or fail cleanly.

A near-miss is not automatically an error: in the same paper a second enzyme was said
to fall "to <1%", where thermal decay alone gives 4.98% — but the model also carried a
turnover-dependent inactivation term. Check whether the text names a second mechanism
before flagging.

## Step 4 — Decompose the sampling design

If a global sensitivity analysis, bootstrap or Monte Carlo run reports a sample
count, factor it.

Worked example: Sobol `n = 18 432` = 1024 × 18 = N × (2D + 2) for D = 8 parameters,
with N a power of two — a clean Saltelli design. A count that does not decompose is
worth a question.

## Step 5 — Spelling consistency by regex, not by eye

Collect the whole `-ize/-ise`, `-ization/-isation`, `-yse/-yze`, `-our/-or`
families across the document and compare counts. Journals accept either convention
but require internal consistency.

```python
ize = set(re.findall(r'\b[A-Za-z]{3,}iz(?:e|es|ed|ing|ation|ations)\b', flat))
ise = set(re.findall(r'\b[A-Za-z]{3,}is(?:e|es|ed|ing|ation|ations)\b', flat))
# strip natively-'-ise' words (promise, precise, comprise, otherwise, ...) before judging
```

🔴 **Exclude the publisher's own boilerplate.** A proof PDF carries the production
queries and instructions in its front matter, and those are written in the
publisher's house style. Counting them produces false findings — in the 260822 case
`organisation` and `summarises` came from pages 2–3 (RSC instructions), while the
manuscript's only British forms were `immobilisation` and `favourably` on page 6.

Two occurrences of the same word in different spellings is the strongest signal:
`immobilisation` and `immobilization` appeared once each in that paper.

## Step 6 — Verify flagged references against the source APIs

For every reference the publisher queries, check the **whole entry**, not only the
field asked about. The query tells you where someone already noticed something; it
does not bound the error.

- CrossRef: `https://api.crossref.org/works?query.bibliographic=<authors journal year>`
- OpenAlex: `https://api.openalex.org/works?filter=...` — use this for author-position
  questions ("is the 95th author's surname right?"), since `authorships` is an
  ordered array you can index directly.

Worked example: the publisher asked only for a missing page number on ref 43. The
lookup returned article number `e202400777` **and** showed the printed year was
wrong — volume 17 is 2025, not 2024. Answering only the question asked would have
shipped the wrong year.

Watch for compound surnames and diacritics, the two things typesetting most often
drops: `Ali Rachedi`, `Pons Siepermann`, `Aït Barka` (printed as `Ait Barka`).

## Step 7 — Physical plausibility and units

Mass balances that should close, metric scaling that should be monotonic, quantities
that must not be conflated (an enzyme's total turnover number vs a cofactor's recycle
number differ by orders of magnitude and that is expected), and unit formatting.

Report what a referee could reasonably ask even when it is not actionable now. In the
same paper a 5.7 mM drop in product was attributed to a back-reaction while the
intermediate rose only 3.8 mM — 1.9 mM unaccounted, with no error bars printed. That
needs new data, so it cannot be fixed at proof; the author should still know it exists.

---

## Reporting

Split findings into three groups, because they need different decisions:

1. **Must fix** — internal contradictions and factually wrong metadata. Give the
   exact replacement string to type into the proof system.
2. **Should fix** — consistency issues (spelling, diacritics) that do not touch a
   claim.
3. **Observation** — things a referee might ask that cannot be resolved without new
   data or a rewrite. State them, recommend leaving them.

For anything where two corrections are self-consistent, present both and say which
evidence favours which — do not silently pick one. In the footnote case, keeping
96.4% means changing the titer, keeping 10.3 g/L means changing the yield; the Fig. 5
measurement settles it, but the author confirms.

Keep every re-derivation script. When the author asks "are you sure?", rerunning
beats re-arguing.
