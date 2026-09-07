---
name: patent-invention-disclosure
description: Convert an English scientific manuscript (Word) into a Korean patent invention disclosure ("발명내용설명서") for a Korean patent attorney, following this lab's established 9-section structure. Use when the user says "발명내용설명서", "특허 발명설명서", "특허명세서 초안", "논문을 특허로 변환", "invention disclosure", or asks to turn a manuscript into patent-filing material. Covers section drafting, English-to-Korean patent-register translation, figure/citation repositioning, claims and prior-art kept as separate linked docx, sequence-listing content the patent needs but the manuscript doesn't have, and a mandatory numeric-claim arithmetic verification gate before anything is presented as final. Do NOT use for general docx editing (use docx skill) or manuscript writing/review (use `manuscript-pipeline`).
---

# Patent Invention Disclosure (특허 발명내용설명서 변환)

Converts a submitted/near-final manuscript docx into a Korean-language invention disclosure
docx for attorney review, plus two separate linked docx files (claims draft, prior-art draft).
The pattern encoded here was distilled from four hand-built invention disclosures for
enzymatic-cascade inventions; this skill generalizes that worked pattern. If your lab keeps
prior disclosure drafts, treat them as read-only reference — never edit them in place.

## Non-negotiable ground rules

1. **All docx creation/editing goes through the docx skill's mechanics — never `python-docx`
   `Document().save()`.** (The docx skill is Anthropic-owned and not shipped in this repo — see
   `docs/12`; this skill declares it as a dependency the same way `manuscript-pipeline` does.) `manuscript-pipeline` states this as SSOT and it applies here too:
   build new documents with docx-js (`npm install -g docx`) per the docx skill's "Creating New
   Documents" section, then validate with `docx_preflight.py` + `word_validate.py` before
   anything is shown to the user. `python-docx` may be used **read-only** (extracting text/tables
   from the source manuscript, or from an already-final patent docx to check it) — never to write.
2. **Claims draft and prior-art-search draft are SEPARATE docx files, never merged into the main
   invention-disclosure docx.** This matches every one of the prior cases
   (`<과제명>_청구범위_초안.docx`, `<과제명>_선행기술조사서_초안.docx` sit next to, not inside,
   `발명내용 설명서.docx`). The main disclosure's §8 "특허 청구범위" is a *summary paragraph*
   pointing at the separate claims file, not the claims themselves.
3. **Numeric claims MUST pass `scripts/verify_numeric_claims.py` before the draft is called
   final.** Non-negotiable — see `references/numeric_verification_gate.md`. A claim the script
   marks UNRESOLVED is not verified; it is not the same as CONSISTENT.
4. **Never edit the user's actual patent docx files in place.**
   Read them as reference/prior-art only unless the user explicitly asks to continue that specific
   draft — and if so, follow the docx skill's incremental_edit session, never in-place overwrite.

## Pipeline (5 stages)

```
1. Extract  → manuscript.docx (+ figures + tables) → structured intermediate (JSON)
2. Draft    → structured intermediate → 9-section Korean draft (docx-js) + register translation
3. Augment  → add patent-only content the manuscript never had (sequence listing, claim-support numbering)
4. Restructure → consolidate figures into one 【도면】 section, renumber, dedupe, integrate any scattered supplementary content into the numbered body
5. Verify   → numeric-claim arithmetic gate (mandatory) + academic-term-rules typography pass + docx integrity gate
```

Stage detail lives in `references/`:

| File | Covers |
|---|---|
| `references/section_template.md` | The 9-section structure, what goes in each section, and where each piece of manuscript content (abstract, intro, methods, tables, figures, results) maps to it |
| `references/translation_register.md` | English manuscript prose → Korean **patent-register** prose — standardized phrase-bank per section type, not free translation (this is what the user specifically flagged as needing to be precise) |
| `references/citation_repositioning.md` | Where each manuscript citation goes in a patent context: body 인용 vs `[참고문헌]` vs EndNote bibliography vs prior-art comparison table — these are 4 different destinations for what was one manuscript reference list |
| `references/sequence_listing.md` | Patent-only content the manuscript never has: full amino-acid/nucleotide sequence listing (서열목록, SEQ ID NO), why it's required, and how to source it from the manuscript's UniProt/GenBank accessions |
| `references/restructure_postprocessing.md` | The figure-consolidation / renumbering / dedup pass (generalizes an archived, proven restructuring script's logic) |
| `references/numeric_verification_gate.md` | How and when to run `scripts/verify_numeric_claims.py`, what UNRESOLVED means, escalation to `adversarial-verifier` |

## Scripts

- `scripts/verify_numeric_claims.py` — arithmetic re-derivation gate (yield, productivity, triple-value averages, ΔG). `--self-test` reproduces and catches three real arithmetic errors found in prior drafts (a yield stated as 91.9% that re-derived to 72.6%, a productivity stated as 87 mg/L/h that re-derived to 45) — run this once after cloning to confirm the gate still works. `--scan <docx>` best-effort regex scan for yield triples in Korean prose (recall aid only, not exhaustive — always also hand-write `claims.json` for the claim-critical numbers, i.e. anything appearing in a numeric claim limitation).

## Workflow

1. **Confirm the source manuscript path and which invention this is** (topic, enzyme/gene names, target claim numbers if known). Don't assume — the prior cases show this recurs across different projects.
2. **Extract** — pull abstract/intro/methods/results prose, all tables, all figure captions + image files from the manuscript docx. Use the `paper-extract` skill for this rather than reimplementing it — its own description explicitly names "patent preparation" as a use case (table/figure/text extraction from docx/PDF). Feed its output into the structured intermediate shape in `references/section_template.md` rather than translating prose ad hoc — the structure is what makes repeat runs consistent.
3. **Draft** the 9 sections via docx-js, applying `references/translation_register.md` phrase-bank at each section boundary. Flag anywhere the source manuscript doesn't have enough information for a section (e.g. §3 배경기술 prior-art framing needs material beyond what an Introduction cites) rather than inventing content.
4. **Augment** — add sequence listing per `references/sequence_listing.md` if the invention involves a specific protein/gene sequence being claimed. Ask the user whether specific-sequence claims are wanted (functional/homolog-breadth vs sequence-specific dependent claims — this is a real attorney-strategy choice, not something to decide unilaterally).
5. **Restructure** per `references/restructure_postprocessing.md` once all sections + figures are placed.
6. **Verify**: run `scripts/verify_numeric_claims.py` against every numeric claim (build `claims.json` by hand for claim-critical numbers; use `--scan` as a recall aid only). Any MISMATCH or UNRESOLVED blocks presenting the draft as final — report it and either fix the source number or escalate to `adversarial-verifier` for a full re-derivation against rawdata (footnotes/citations on a filled number can themselves be fabricated — re-derive the arithmetic, don't just check "has a citation").
7. Validate the produced docx (`docx_preflight.py` + `word_validate.py`) before handing it to the user, and run `academic-term-rules` typography checks (species italics, gene naming, unit formatting) since these disclosures reuse manuscript terminology.

## Related skills
`docx` (all docx read/write mechanics — SSOT) · `manuscript-pipeline` (source manuscript itself) · `paper-extract` (Extract stage — table/figure/text pull, already scoped for patent prep) · `academic-term-rules` (typography SSOT reused here) · `scientific-validation` (its own docs already name "patent claim figure" as a high-stakes-number example — same verification philosophy as this skill's numeric gate) · `adversarial-verifier` agent (numeric claims that fail the arithmetic gate, or need re-derivation against rawdata, or novelty/prior-art claims — never assert "not previously reported" without a completed search).

**Overlap check performed** against this distribution catalog: no existing skill or catalog
entry covers patent/발명/특허 content directly. `docx`/`pdf`/`pptx`/`xlsx` are Anthropic-owned skills
external to that repo (catalog marks them `external=true`, dependency declaration only — this
skill declaring `docx` as a dependency matches the existing `manuscript-pipeline` pattern
exactly, not a conflict). No functional duplication found: `manuscript-pipeline`'s
`numeric_consistency_check.py` checks a labelled quantity for cross-document disagreement (body
vs table vs figure CSV); `scripts/verify_numeric_claims.py` here re-derives a claimed value
arithmetically from its own stated components (yield from initial+final, etc.) — adjacent
purposes, not the same check, both worth running on a patent draft.

## Known gaps (not yet built — do not claim these work)
- Stages 2–4 (docx-js drafting, translation-register application, restructure pass) are specified in `references/` but not yet implemented as runnable scripts — the prior worked examples prove the *pattern* works (python-docx based, pre-dating the docx-skill SSOT rule), but a generalized docx-js version has not been built or tested. Only `scripts/verify_numeric_claims.py` is implemented, proven (self-test + adverse-case regression), and ready to use today.
- Sequence-listing generation (`references/sequence_listing.md`) is guidance/spec only, based on general KIPO/PCT sequence-listing practice — no prior example was found to verify the exact template against (all four prior invention-disclosure drafts were checked; none contained a completed sequence listing yet). Confirm format requirements with the patent attorney before treating it as filing-ready.
