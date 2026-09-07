# Sequence listing (서열목록) — patent-only content the manuscript never has

Content the patent adds that the manuscript never had — specifically amino acid sequences.
Confirmed by checking all four prior invention-disclosure drafts (every revision of the most
complete one, plus the three others) — **none of them contain a completed sequence listing
yet**. Those drafts only have: (a) cloning primer DNA sequences in a table (5′→3′, ~20-40 nt
each — these are NOT the gene/protein sequence, just PCR primers), and (b) prose mentioning
specific amino-acid *substitutions* (e.g. "A198G/D221Q/C255A/H379K/S380V"), never the full
sequence. So this is a genuine gap in the prior worked examples, not something to copy from
them — the guidance below is general KIPO/PCT sequence-listing practice, **not
verified against a completed local example**. Confirm the exact format with the patent attorney
before treating a generated listing as filing-ready.

## Why the manuscript never has this

A scientific manuscript cites the sequence's public database record (GenBank / UniProt
accession, e.g. "the enzyme (UniProt P00000)") — readers who need the sequence look it up there. A
patent application cannot rely on an external database reference for something the claims may
recite structurally; KIPO (and PCT/WIPO ST.25 or the newer ST.26 XML standard) require the full
nucleotide and/or amino acid sequence to be submitted as part of the application when:
- A claim recites "the amino acid sequence of SEQ ID NO: X" (sequence-specific dependent claims —
  this is a recurring attorney-strategy option — e.g. specifying an engineered variant only
  in the dependent claims), or
- The specification otherwise discloses a sequence ≥ a residue-count threshold (practically:
  any claimed protein/enzyme sequence, and any engineered/mutant sequence central to the
  invention) in a way that needs unambiguous, database-independent disclosure.

## What to build

1. **Identify every protein/gene the invention claims or substantially relies on** — pull from
   the §4-2 "(1) 효소 구성" table (`section_template.md`). This includes every cascade enzyme and
   every cofactor-regeneration enzyme. Watch for engineered variants: a mutant's sequence differs
   from wild-type at each substitution site, so the *mutant* sequence, not just the wild-type
   accession, must be given.
2. **Source the full sequence**: fetch from the manuscript's stated accession (UniProt/GenBank
   ID) via `openalex-database`/`pubmed-database`-adjacent lookup tooling or direct database
   query — never fabricate or approximate a sequence. For a variant/mutant enzyme, apply the stated substitutions to the wild-type sequence programmatically and flag
   the result for the user to confirm against their actual construct sequence (a plasmid map or
   sequencing result, if available, is the real ground truth — the recomputed sequence is a
   best-effort fallback only).
3. **Format as a separate 서열목록 file** (do not embed in the main disclosure docx body — this
   follows the same separation pattern as claims/prior-art, `SKILL.md` ground rule 2). **Default
   to WIPO ST.26 XML** — it has been the mandatory format for new applications at KIPO/USPTO/EPO
   since the July 2022 transition, so it is the correct default rather than an open choice; only
   fall back to legacy ST.25 text format if the attorney explicitly says the filing is under an
   ST.25 transitional/legacy track. Generate the ST.26 XML with the sequence(s), their moltype
   (protein/DNA), organism, and SEQ ID NO mapping filled in from step 1–2 above; still have the
   attorney confirm before submission — the format choice itself doesn't need to block drafting.
4. **In the main disclosure body**, reference sequences only by "서열번호 N" (SEQ ID NO: N) —
   this is what makes §4/§7 tables/prose consistent with the separate listing file rather than
   duplicating full sequences inline in the main docx.

## Open question to raise with the user before building this for a specific invention

Sequence-specific claims narrow scope (easier to prove, easier for a competitor to design
around) vs. functional/homolog claims broaden scope (harder to prove, more valuable if granted).
This recurs as an unresolved strategy question in attorney discussions (mutant 청구 범위 /
homolog·variant 포함 여부). Don't default silently to sequence-specific — ask.
