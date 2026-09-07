# English manuscript → Korean patent-register translation

Narrative translation and reference repositioning both need to be highly standardized and
precise. Free-hand paragraph translation is NOT acceptable here — a patent disclosure has a
distinct register from scientific prose, and inconsistent phrasing across drafts (the prior
cases show long v2→v8 iteration cycles fixing exactly this) is expensive to catch late. Use the
fixed phrase-bank below at section boundaries; extend it as new patterns recur, don't improvise
per-sentence.

## Register shift, not just language shift

| Manuscript register (EN) | Patent register (KO) | Why |
|---|---|---|
| Hedged claims: "appears to", "may suggest", "we believe" | Confident assertion: "~이다", "~을 확인하였다" | A patent states what the invention achieves; hedging weakens enablement/support arguments. |
| Passive, results-first: "Yield was found to be 96.4%" | Active, invention-first: "본 발명은 ... 96.4%의 수율을 달성하였다" | Patent prose centers the invention as actor. |
| Comparative/citation-dense: "(Author, Year)" inline | Structured reference: either 배경기술 prose (no inline citation) or 비교예 table row | See `citation_repositioning.md`. |
| Discussion hedges: "further optimization may improve..." | Omit, or reframe as a dependent-claim-supporting embodiment | Limitations undermine; reframe as claimed scope instead. |
| First person plural: "we constructed", "we measured" | Impersonal/invention-centered: "본 발명에서는 ~하였다", "~를 구축하였다" | Standard KO patent voice. |

## Standardized phrase-bank (extend this table, don't ad-lib)

| EN manuscript phrase (pattern) | KO patent phrase (standard) |
|---|---|
| "X was achieved" / "we achieved X" | "X를 달성하였다" |
| "X exhibited/showed Y" | "X는 Y를 나타내었다" / "X는 Y를 나타내는 것으로 확인되었다" |
| "compared to prior work / previous studies" | "종래 기술 대비" |
| "to the best of our knowledge, X has not been reported" | **Do not translate directly** — this is a novelty claim; route through prior-art search verification first (see below), never assert unilaterally. |
| "X is a promising approach for Y" | "X는 Y에 유용하게 활용될 수 있다" |
| "under optimized conditions" | "최적화된 조건 하에서" |
| "Fig. N shows..." | "[도 N]은 ~을 나타낸다" (label renumbered per `restructure_postprocessing.md`) |
| "significantly higher/lower (p<0.05)" | Keep the numeric comparison; drop the statistical-significance framing unless the claim itself depends on it — patents argue magnitude, not p-values. |
| enzyme/gene names, species names | Keep italics per `academic-term-rules` skill — do not re-derive typography rules here, that skill is SSOT. |

## Novelty/priority-language rule (hard rule, not a style choice)

Never translate or write "본 발명 이전 보고된 바 없다" / "for the first time" / "unprecedented"
unless a completed prior-art search backs the specific claim. A real prior case failed exactly
this way: a filled Korean patent draft asserted novelty without a completed search.
If the manuscript itself makes a "first/only" claim, that claim is a manuscript peer-review
framing, not verified prior-art — treat it as UNVERIFIED and route to `adversarial-verifier` or
the attorney's prior-art report before writing it into the disclosure at all — there is a real
case where exactly this kind of overstated novelty had to be walked back after the fact.

## Section-specific register notes

- **§2 기술분야, §3 배경기술**: most translation-register-sensitive — this is patent-attorney-read
  prose, not scientist-read prose. Confident, generic-to-specific framing.
- **§4/§7 (내용/실시예)**: closest to literal translation of Methods/Results — precision matters
  more than register here (these are the sections an examiner checks numbers against), don't
  over-polish at the cost of a number drifting from its source value.
- **§5 발명의 효과**: most compressed/confident register — bullet-per-advantage, headline numbers only.
