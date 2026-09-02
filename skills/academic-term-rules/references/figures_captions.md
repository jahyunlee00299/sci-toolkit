# Figure Caption Rules and Citation-Order Diagnosis

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

