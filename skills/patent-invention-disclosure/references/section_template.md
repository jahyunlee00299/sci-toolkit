# 9-section invention-disclosure template

Distilled from the actual structure of four prior invention-disclosure drafts for
enzymatic-cascade inventions, most fully realized in a generator script archived alongside
the most complete of them. This is the target shape of the "Draft" stage's structured
intermediate — extract manuscript content into this shape *before* writing prose, don't
translate paragraph-by-paragraph.

| # | Section (KO) | Source in manuscript | Notes |
|---|---|---|---|
| — | 표지 (cover) | — | 발명의 명칭(국/영문), 발명자, 출원인, 작성일. Ask the user for 발명자/출원인/작성일 — never invent. |
| 1 | 발명의 명칭 | Manuscript title | 국문 + 영문 both required. The Korean title is usually NOT a literal translation of the paper title — it follows patent naming convention (method/composition framing, see `translation_register.md` §Title). |
| 2 | 기술분야 | Abstract / Intro first paragraph | One paragraph: field + what the invention specifically does. |
| 3 | 발명의 배경이 되는 기술 | Intro (prior-art framing) | Subsections 3.1 (importance/motivation), 3.2 (existing chemical/physical method limitations), 3.3 (existing biological/enzymatic method limitations). **This needs MORE than what the manuscript's Introduction cites** — a manuscript intro motivates the paper; a patent background must establish the *problem the invention solves* against prior art the attorney will search. Flag gaps rather than padding with manuscript prose. |
| 4 | 발명의 내용 | Results + Methods | 4-1 해결하고자 하는 과제 (from the paper's stated goals/hypothesis) — 4-2 과제의 해결 수단, broken into subsections mirroring the paper's Results structure (e.g. (1) composition/components table, (2) mechanism/pathway description, (3) model/optimization if any, (4) parameter tables, (5) optimal condition tables). This is the largest section — most manuscript Results content lands here. |
| 5 | 발명의 효과 | Results (headline numbers) / Discussion | Bullet list, each bullet = one advantage + the manuscript number that supports it. Every effect claimed here becomes a candidate for `verify_numeric_claims.py`. |
| 6 | 도면의 간단한 설명 | All figure captions | One line per figure: `[도 N] <what figure shows>`. Final numbering happens in the Restructure stage — draft with source-manuscript figure/scheme labels first (e.g. "Figure 1", "Scheme 2") and let restructure renumber. |
| 7 | 발명을 실시하기 위한 구체적인 내용 | Methods + Results (experiment-by-experiment) | [실시예 N] per manuscript experiment/condition set (cloning, initial run, optimization, validation...), [비교예] for any prior-art comparison table. This section carries almost all the manuscript's Methods detail — cloning primers, expression/purification conditions, experimental protocols verbatim where the manuscript already states them precisely. |
| 8 | 특허 청구범위 (요약) | — | **Summary only** — 1-2 sentences pointing to the separate `..._청구범위_초안.docx`. Do not draft claims here (see SKILL.md ground rule 2). |
| 9 | 발명자 서명 | — | Signature table: 발명자 1/2/…, 서명/날인, 제출일. Ask the user for the inventor list and contribution split — do not infer from manuscript author order (a manuscript's author list and a patent's inventor list can legally differ; in one prior case whether a particular contributor belonged on the inventor list had to be resolved with the attorney, not assumed from paper authorship).

## Content NOT in the manuscript that the patent still needs

The manuscript and the disclosure are not 1:1. Content the manuscript never states but the
disclosure needs to add:
- **Sequence listing** for any claimed protein/gene — see `sequence_listing.md`.
- **Broader background/prior-art framing** in §3 — manuscripts motivate; patents must
  establish patentability against a completed prior-art search.
- **Explicit numeric ranges for claims** — a manuscript reports the values it measured;
  claims (in the separate claims draft) need the attorney-agreed range/boundary framing
  (e.g. "D-Rib 20–70 mM" as a claimed range vs. the manuscript's "we tested 20, 30, 40, 50,
  60, 70 mM").
- **Comparative/prior-art performance table** (§7 비교예) — the manuscript may cite prior
  literature narratively; the disclosure needs it as a structured side-by-side table for
  novelty/inventive-step argument (the archived examples place this as a dedicated 비교 표).

## Content in the manuscript that does NOT belong in the disclosure

- Discussion-section hedging/limitations language — a patent disclosure states what the
  invention does, not where it might fall short (that framing actively undermines a patent
  application). Translate confidently; don't carry manuscript hedges over verbatim.
- Peer-review-oriented framing ("we believe", "further work is needed") — strip.
- Citation-heavy comparison prose — becomes the structured 비교예 table instead (see above).
