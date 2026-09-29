---
name: sequence-verification
description: >-
  Check whether a plasmid variant exists on disk, build the expected-sequence map to align
  sequencing reads against, and compute the mass of the protein a construct really expresses.
  Use when asked where a construct's sequence file is, whether a mutation is saved in any map,
  what to compare a sequencing result to, which primer reaches the mutated position, or how
  many kDa the tagged protein is. Reads residues from SnapGene .dna / GenBank files instead of
  trusting filenames, recovers codons from stored mutagenesis primers, edits only named codons
  of a lab-built map, checks Sanger read distance, and translates the anchored ORF for fusion
  vs native MW, pI, e280. Triggers - "시퀀스 파일 찾아", "서열 파일 어디 있지", "이 변이 들어간 파일 있나", "변이 확인용 맵",
  "시퀀싱 대조", "무슨 프라이머로 시퀀싱", "분자량 계산", "몇 kDa", "밴드 크기", "which file has the mutation",
  "reference map for sequencing", "protein molecular weight from plasmid". Not for designing
  primers (primer-design) or judging whether a measured number is plausible (scientific-
  validation).
license: Proprietary
---

# Sequence Verification

Answers one question end to end: **does the variant I think I have exist, and what do I compare
a sequencing read to?**

The trap this skill exists for: a filename, a folder name, and even an annotated mutagenesis
primer are all consistent with a map that holds pure wild-type sequence. SnapGene stores a
primer's *binding site*, which is template sequence, so a map can display `iPCR_E223A` in its
primer list and carry `E` at 223. In one real audit, 28 candidate files all belonged to a
variant construction project and all 28 were wild type — the variant map had never been saved.

## Requirements

```bash
pip install biopython
```

SnapGene `.dna` parsing is reused from the `primer-design` skill, which must be installed
alongside this one (the installer pulls it automatically).

## Workflow

Work in this order. Each step feeds the next.

### 1. Narrow the candidates before opening anything

These scripts read file contents. On synced cloud storage (OneDrive, Dropbox, Drive) that
forces placeholder files to materialise, so build a shortlist from a file listing or metadata
index first and pass only those paths on. Filename filters are for *narrowing*, never for
concluding — step 2 is what decides.

### 2. Does any file actually carry the variant?

```bash
python scripts/find_variant_maps.py --reference WT.dna --residues 223,271 \
    --expect 223=A --expect 271=A  <dirs-or-files...>
```

Translates every candidate in six frames, anchors it against the wild-type protein, and reads
the residues. Exit 1 means nothing carries it — which is an answer, not a failure.

### 3. If nothing carries it, recover what was intended

```bash
python scripts/primer_codons.py MAP.dna --reference WT.dna --filter iPCR
```

Aligns each stored primer to the template and reports the mismatches as residue changes, e.g.
`S271A:GCC (TCC->GCC)`. Forward and reverse primers are reported independently; when they agree,
that is a real cross-check. The output line is already formatted as `--mutate` arguments.

🔴 **Residue numbers come from `--reference`, never from the CDS annotation.** Annotated CDS
bounds are routinely a base or two off the true frame — a vector fusion trims the start codon and
the label keeps the old range. Trusting the label shifts every residue and reports the mutation at
a wrong position with a plausible-looking amino acid.

### 4. Build the expected map from something real

```bash
python scripts/build_reference_map.py --base MEASURED.dna --reference WT.dna \
    --mutate E223A:GCA --mutate S271A:GCC --out expected.gb
```

Starts from a map that was actually built in the lab and changes **only** the named codons. It
refuses to write when the base residue is not what the mutation assumes, when a codon does not
encode the stated amino acid, or when the tagged fusion changes length. Verification is printed
(nt changed, aa changed, fusion length) and the file is re-read before success is reported.

🔴 **Do not assemble the map by simulating a ligation.** An insert cut for one vector carries that
vector's reading frame. In a measured case, a pETDuet MCS1 insert (start codon trimmed for the
upstream tag) dropped into pET-28a's BamHI site shifted the frame and died at 39 aa, while the
lab's own BamHI/XhoI map expressed a 352 aa fusion. Starting from the measured map keeps the
junction that was proven to work and keeps the diff small enough to audit.

If you genuinely must build a new construct, `primer-design`'s `snapgene_writer` already does
in-silico cloning and writes native `.dna` — use that rather than writing another assembler.

### 5. Choose the sequencing primer before ordering

```bash
python scripts/read_coverage.py --map expected.gb --variants \
    --primers "T7 promoter,T7 terminator"
```

Sanger quality decays: usable from ~30 bases, good to ~600, marginal to ~850, unreliable beyond.
A variant 900 bases out often reads as wild type and the result looks clean. This prints the
distance from each primer to each target and names the primer to use; exit 1 means no primer
reaches some target and the order as planned cannot answer the question.

### 6. What protein does the construct express, and how heavy is it?

```bash
python scripts/construct_mw.py MAP.dna --native-start MPSIKL --mutate E223A --mutate S271A
```

Reads the ORF downstream of the T7 promoter (`--anchor` to change it, `--start-pos` to give the
start codon), translates it, and prints the **fusion** (what runs on the gel), the **native**
protein, and the thrombin-cleaved product, each with MW, pI and e280. `--native-start` is the first
residues of the native protein; it splits the vector leader off and fixes the numbering `--mutate`
uses (Met1 of the native). Both the wild-type and the mutant figures are printed. Exit 1 means the
construct could not be resolved: no anchor feature, no stop codon, motif absent or ambiguous, or
the base residue is not what the substitution assumes.

🔴 **Quote the fusion for a gel, the native for a stoichiometry.** A native-only figure leaves out
the vector leader: for pET-28a it is 34 aa (~3.5 kDa), so a 35.9 kDa enzyme runs near 39 kDa. In
one measured case (2026-09-29) the lab's recorded molecular weights were native-only, and the band
expected on the gel was 3.5 kDa higher than the number in the task. The reading frame is anchored
at the promoter on purpose: the longest ORF in a pET-28a map is often `lacI` (360 aa), not the insert.

Masses are average masses computed from sequence. They are not measurements, the initiator Met is
kept, and processing or PTMs are not modelled -- say "computed" wherever the number is filed.

### 7. Record the result honestly

A map from step 4 is an **expected** sequence, not a record of a verified clone. Say so wherever
it is filed or shared, and store the confirmed sequence separately once reads come back.

## Scripts

| Script | Job |
| --- | --- |
| `find_variant_maps.py` | Read residues out of many files; which ones carry the variant |
| `primer_codons.py` | Recover intended codons from stored mutagenesis primers |
| `build_reference_map.py` | Measured map + named codons -> verified expected map |
| `read_coverage.py` | Primer-to-target distance; can this read answer the question |
| `construct_mw.py` | Expressed fusion vs native protein from a map: MW, pI, e280, tags, mutations |
| `_seqcommon.py` | Shared `.dna`/`.gb` loading, translation, frame anchoring |

SnapGene binary parsing is borrowed from `primer-design` (`snapgene_parser`), not reimplemented.
`parse_snapgene_primers()` was added there by this skill's work, because primer sequences are
invisible to every feature-table reader including biopython.

## Related skills

- **`primer-design`** — designs the mutagenesis/cloning primers this skill later reads back, owns
  the SnapGene binary format (`snapgene_parser`, `snapgene_writer`) and in-silico cloning. Go
  there to *create* a construct or primer; come here to *check* one. Required dependency.
  Its `expression_analyzer` also reports a MW, but from a protein sequence you hand it; `construct_mw.py`
  reads the construct from the map, so the vector leader and the mutation are included.
- **`experiment-hub`** — surrounding experiment planning; routes to `primer-design` when an
  experiment needs primers, and here when a result needs checking against an expected sequence.
- **`scientific-validation`** — the gate for whether a measured *number* is plausible. Different
  job: this skill checks sequence identity, that one checks scientific sense.
