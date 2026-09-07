# Reference/citation repositioning

A manuscript has ONE reference list. A patent invention disclosure splits that same set of
citations across up to 4 different destinations — repositioning them correctly (not just
translating the list) is the other piece the user flagged as needing precision.

| Manuscript citation use | Patent destination | Format |
|---|---|---|
| Prior-art framing in Introduction ("X has been reported to achieve Y [12]") | §3 배경기술 body, as **narrative prose**, no bracket/superscript marker in the disclosure body | Cite by description ("기존 보고된 방법은..."), not by inline reference number — the disclosure's own `[참고문헌]` list at the end still carries the full citation |
| End-of-manuscript reference list (all citations) | `[참고문헌]` section (end of disclosure, before or paired with EndNote Bibliography) | Same bibliographic entries as the manuscript, renumbered to the disclosure's own citation order — do not assume manuscript numbering carries over (it won't once §3 selectively cites a subset) |
| A citation that is a **direct performance competitor** (same product, comparable yield/titer/condition) | §7 [비교예] structured table row, not prose | Pull the *numbers* into the comparison table (see `section_template.md` §7); the citation itself still also needs a `[참고문헌]` entry |
| A citation to a **patent** (not a paper) — e.g. a competitor's existing patent covering an overlapping method | Its own line, flagged distinctly — this is exactly the material a patent attorney's prior-art search focuses on (in a prior case a single competitor WO publication was flagged as the most relevant prior art and tracked separately from the paper reference list) | Keep patent citations (application number, assignee) visibly separate from journal citations — do not fold them into `[참고문헌]` as if they were papers |
| EndNote-managed citations (`{Author, Year #RecNum}` fields) in the source manuscript docx | EndNote Bibliography section, if the disclosure is built by copying manuscript passages that still carry live EndNote fields | Follow the docx skill's EndNote field-preservation rules (`{Author, Year #RecNum}` braces are structural, don't hand-edit) — if the disclosure is regenerated from a structured intermediate rather than copy-pasted, EndNote fields don't survive the round-trip and citations need re-resolving via `manuscript-pipeline`'s `references/endnote_integration.md` |

## What NOT to do

- Don't keep the manuscript's inline `[N]` bracket numbers in the disclosure body — they will
  desync the moment §3 selectively cites a subset of the manuscript's reference list. Cite by
  description in body prose; let a separate reference-numbering pass build `[참고문헌]`.
- Don't merge patent-citation and paper-citation into one undifferentiated list — an attorney
  reading this needs to immediately tell "this is a competing patent" from "this is a paper we
  cite for background," and they are searched/analyzed completely differently.
- Don't silently drop the "which figure/table in the ORIGINAL patent (if comparing to one) this
  number came from" provenance when building the §7 비교예 table — a real patent-citation audit found solubility
  data attributed to the wrong patent in a related project (US7101432B2 vs
  US20050188912A1 — same family, different document) purely because the attribution wasn't
  checked at the "which specific document/paragraph" level. When citing a competitor patent's
  data, record the exact paragraph/table/example number, not just "cited in Patent X".
