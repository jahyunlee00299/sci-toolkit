# Writing Voice Guide — manuscript-pipeline reference

## SSOT hierarchy (read this first)

| File | Scope |
|---|---|
| **writing_voice.md** (this file) | Macro tone, sentence-level anti-patterns, prose rhythm |
| **writing_style.md** | Micro punctuation: dash, colon, citation placement |
| **academic-term-rules skill** | All notation: species italics, enzyme prefix, EC numbers, coenzyme, units |

These three files are non-overlapping. When they appear to conflict, the narrower scope wins (notation > micro-style > macro tone). The tone, no-colon-dash-splice, and arrow-notation rules are already encoded in `writing_style.md`; this file does not repeat them.

---

## A. AI anti-patterns — exclusion list

Each pattern is followed by a plain alternative. **Detection only** — never auto-correct without context. Use `scripts/ai_tells_lint.py` to flag occurrences.

### A1 — Inflated adjectives

These add no information. Replace with a measurement or mechanism.

| AI phrase | Plain alternative |
|---|---|
| plays a crucial / pivotal / vital role in | is required for; controls; drives |
| robust (as vague intensifier) | state what held up: "stable across pH 5–8" |
| intricate / complex (without elaboration) | describe the actual complexity |
| meticulous(ly) | omit; the method section shows it was careful |
| groundbreaking / unprecedented | state what was not done before, specifically |
| novel (as filler before a noun) | omit; novelty is established by context |
| comprehensive | state what was covered |

Quantitative grounding: "meticulously" is overrepresented +991 % and "underscore" +766 % in LLM-generated text vs. human writing (arXiv 2506.21817). "delve", "realm", and "underscore" co-occur in 98.8 % of flagged AI abstracts (medRxiv 2024.05.31.24308296).

### A2 — Meaning fillers (frame-setters that add no content)

Delete the entire frame; state the fact directly.

| Remove | Replace with |
|---|---|
| It is important to note that X | X |
| It should be noted that X | X |
| This result sheds light on X | This result shows / indicates / suggests X |
| This work paves the way for X | explicitly describe the next step |
| This sets the stage for X | same as above |
| This serves as a testament to X | state the evidence |
| Importantly, … (sentence opener) | omit the adverb; rearrange for stress position if needed |

### A3 — AI-signature verbs

These verbs rarely appear in published chemistry/bioengineering prose.

| AI verb | Plain substitute |
|---|---|
| delve (into) | examine, investigate, study, analyze |
| showcase | show, demonstrate |
| leverage | use, apply, exploit |
| foster | promote, increase, improve |
| garner | obtain, achieve, collect |
| underscore | confirm, support, show |
| facilitate (overused) | enable, allow — or rewrite to active voice |

### A4 — Stacked hyphenated modifiers (user priority item)

Stacking compound modifiers converts a process claim into a label and hides mechanism. Unfold to a relative clause.

| Stacked form | Unfolded alternative |
|---|---|
| a cofactor-balanced, waste-minimizing cascade | a cascade that recycles its cofactor and produces little waste |
| a sustainability-driven, atom-economical process | a process designed to reduce waste and use atoms efficiently |
| an enzyme-coupled, redox-neutral regeneration system | a regeneration system that couples two enzymes with net-zero redox change |
| an NADH-recycling, cell-free platform | a cell-free platform that recycles NADH |

Rule: a single hyphenated compound (e.g., "cell-free", "one-pot", "NAD+-dependent") is acceptable. Two or more stacked before the same noun → unfold at least the domain-specific one.

### A5 — Rule-of-three rhetoric

Three-item lists used for rhetorical effect ("efficient, scalable, and sustainable") obscure which property matters. Include only items that are independently supported by data.

BAD: "The system is efficient, scalable, and sustainable."
GOOD: "The system achieved 94 % yield at 100 mM substrate; scale-up to 1 L retained yield within 5 %."

### A6 — Negative parallelism

"Not only…but also" construction reads as rhetorical amplification rather than a scientific statement.

BAD: "This approach not only eliminates the need for protecting groups but also reduces solvent consumption."
GOOD: "This approach requires no protecting groups and reduces solvent consumption by 60 %."

### A7 — Hedge stacking (one hedge per claim)

Each factual claim may carry at most one epistemic hedge. Multiple hedges on one claim signal either low confidence or AI inflation.

BAD: "These results possibly suggest that the enzyme may play a role in…"
GOOD: "These results suggest that the enzyme contributes to…"

Reference: hedging frequency and function in scientific writing — PMC6311890.

### A8 — Sentence-opening transitions and boosters

Starting consecutive sentences with connective adverbs signals padding rather than logical flow. Replace with syntactic connection or rearrange the paragraph.

Words to move away from sentence-start position:
`Additionally` · `Moreover` · `Furthermore` · `Notably` · `Interestingly` · `Importantly` · `Significantly`

If the logical connection is additive, absorb into the prior sentence. If contrastive, use "However" once, then rely on content for contrast.

### A9 — Nominalization (smothered verb)

Convert noun-heavy constructions back to verbs. This shortens sentences and keeps the agent visible.

| Smothered | Verb form |
|---|---|
| performed an investigation of | investigated |
| conducted an analysis of | analyzed |
| made an observation that | observed |
| provides an indication of | indicates |
| resulted in an increase of | increased |
| demonstrated the ability to | could; was able to |

### A10 — Structural tells

These formatting choices signal AI-generated or pop-science prose and are inappropriate in journal manuscripts.

- Title-Case section headings (outside structured abstract fields): use Sentence case per journal style.
- **Bold** emphasis inside body paragraphs: use only for defined terms on first use, if journal permits.
- Bullet lists inside body prose: the manuscript body must be continuous paragraphs (SKILL.md Phase 2 rule).
- Em-dash overuse as a clause separator: see `writing_style.md`.

---

## B. Positive norms — chemistry and bioengineering

### B1 — ACS Style Quick Guide (pubs.acs.org/doi/full/10.1021/acsguide.40303)

- Active voice is preferred **when it results in a shorter sentence**. Passive voice is acceptable and conventional in Methods.
- Past tense for experimental actions ("was added", "was measured"). Present tense for established facts and conclusions ("the enzyme is known to…", "Fig. 2 shows…").
- Be consistent: choose one tense per context and do not switch within a paragraph without reason.

### B2 — Nature (author guidance, paraphrased; primary source behind author paywall)

- Write as concisely as possible. Each sentence should carry one idea.
- Minimize jargon and acronyms. Define every abbreviation on first use; thereafter use the short form consistently (do not introduce synonyms).
- Unpack concepts before using them. Do not assume the reader recognizes an enzyme name or pathway abbreviation.
- Short, simple sentence structures outperform complex nested constructions.

*Honesty flag*: Nature's detailed author style instructions are behind an author login. The above is a paraphrase of publicly available advice consistent with published Nature papers; it is not a verbatim quote.

### B3 — Angewandte Chemie abstract economy

Every word in the abstract must earn its place. The abstract is read before the paper is accepted for review; wordiness reduces acceptance probability. A practical target: zero filler sentences, no sentence that only restates the title.

### B4 — RSC Green Chemistry conventions (paraphrased from author guidelines)

- Do not duplicate data between figures and tables. If a trend is shown in a figure, the table should contain the numbers; the table should not also describe the trend in a caption.
- The Discussion section should answer the question posed in the Introduction. Structure: restate finding → compare with literature → mechanistic interpretation → acknowledge limitation → outlook. Do not add new data.

*Honesty flag*: RSC author guidelines are publicly available; this is a paraphrase, not a verbatim quote.

### B5 — Gopen and Swan, "The Science of Scientific Writing" (1990)

Full PDF: cseweb.ucsd.edu/~swanson/papers/science-of-writing.pdf

Two structural principles with strong predictive value:

**Topic position** (sentence start): place the information that connects backward to the prior sentence — old or shared information — at the start. This creates coherence.

**Stress position** (sentence end): place the information you want the reader to emphasize — the new, important, or surprising element — at the end of the sentence.

Application: when a sentence feels weak or confusing, check whether new information is buried mid-sentence and old information occupies the stress position.

---

## C. Executable rules (10 + cascade supplement)

These are actionable decisions, not style preferences.

| # | Rule | Rationale |
|---|---|---|
| C1 | Delete significance-frame sentences and intensifiers before submitting | A1, A2 |
| C2 | One epistemic hedge per factual claim | A7, PMC6311890 |
| C3 | Prefer verb over nominalization | A9 — shorter, clearer agent |
| C4 | Active voice when it shortens the sentence | B1 — not an absolute rule |
| C5 | Unfold stacked compound modifiers (≥2) into a relative clause | A4 |
| C6 | Old information first, new information last (stress position) | B5 Gopen-Swan |
| C7 | Use one keyword for one concept throughout the paper | B2 — no synonym swapping |
| C8 | No rule-of-three rhetoric; no "not only…but also" | A5, A6 |
| C9 | AI-signature verbs and adjectives (A1–A3 lists) are default-blocked | A1–A3 |
| C10 | Do not open sentences with additive/booster adverbs | A8 |

### C-bis — Cascade description conventions

*Note: no single published style guide codifies cascade prose standards; these conventions are derived from Green Chemistry and ACS catalysis paper practice.*

- **One-pot / cell-free / in vitro / whole-cell / artificial cascade**: use each term only according to its technical definition. Do not choose between them for rhetorical variety.
  - *one-pot*: all components combined without intermediate isolation.
  - *cell-free*: cell extract or purified enzymes, no intact cells.
  - *in vitro*: outside living cells (overlaps with cell-free but broader).
  - *whole-cell*: intact living or resting cells as catalyst.
  - *artificial cascade*: enzyme sequence not found together in nature.

- **Describe a cascade as a reaction sequence**: name each enzyme and its conversion before attributing system-level properties. System-level properties (cofactor recycling, waste reduction) go in a separate sentence.
  - BAD: "a cofactor-balanced, waste-minimizing cascade converts xylose to ribose."
  - GOOD: "Xylose isomerase converts xylose to xylulose, and xylulose kinase phosphorylates xylulose to xylulose 5-phosphate. The cascade recycles NAD+ internally and produces no stoichiometric waste reagent."

- **Cofactor recycling**: describe the regeneration enzyme and the driving reaction separately from the productive sequence. This is the exact position where AI hyphen-stacking (A4) tends to intrude.

- **Enzyme naming and notation** (species italics, prefix convention, EC numbers, coenzyme abbreviations) → **academic-term-rules skill (SSOT)**. This voice guide does not redefine notation.

---

## Sources

All sources listed below are human-verifiable. No statistics or claims have been invented.

| Source | Used for |
|---|---|
| Wikipedia, "Signs of AI writing" (https://en.wikipedia.org/wiki/Signs_of_AI_writing) | A1–A3 pattern list, general framing |
| arXiv 2506.21817 (Liang et al., 2025) | Quantitative word frequency data: "meticulously" +991 %, "underscore" +766 % |
| medRxiv 2024.05.31.24308296 (Hazan et al., 2024) | "delve/realm/underscore" 98.8 % co-occurrence in AI abstracts |
| PMC6311890 (Hyland, 1998, via PubMed Central) | Hedging norms in academic discourse |
| ACS Style Quick Guide, pubs.acs.org/doi/full/10.1021/acsguide.40303 | B1 tense and voice rules |
| Gopen & Swan (1990), cseweb.ucsd.edu/~swanson/papers/science-of-writing.pdf | B5 topic/stress position |
| labarba/sciwrite (GitHub) | General scientific writing heuristics (C rules) |
| Strunk & White via softaworks/obra | Omit needless words (C1) |

**Honesty flags:**
- Nature author style guide: the full guide is behind an author login. B2 is a paraphrase of publicly consistent advice, not a verbatim quote.
- RSC Green Chemistry author guidelines: B4 is a paraphrase.
- Schimel, *Writing Science* (2012): primary text not confirmed accessible; Gopen-Swan PDF used as the verifiable substitute for the stress-position principle.
- Cascade prose conventions (C-bis): no single style guide exists; these are practice-derived.
