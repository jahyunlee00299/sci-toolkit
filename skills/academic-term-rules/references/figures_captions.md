# Figure Caption Rules and Citation-Order Diagnosis

## 7. Figure Caption Rules

**Required components**:
1. **Number**: "Figure 1." — "Figure." without number forbidden
2. **Title**: Bold, sentence case, AND a declarative noun phrase that names what is shown
   [Auto-detectable, `caption_style.check_title_form`]. Forbidden in the title sentence: a
   question word at the start (Why / How / What / Where / When / Whether / Which), a trailing
   "?", a colon subtitle ("X: Y"), and rhetorical framing or a clause that makes a claim
   ("... interact rather than acting independently"). The title says WHAT the figure is; why
   the data look that way belongs in the body.
   - Before: `Fig. S3. Why the optimum sits outside the tested range: one-at-a-time
     sensitivity of the five process variables.`
   - After: `Fig. S3. One-at-a-time sensitivity of product yield to the five process variables.`
   A colon inside a ratio ("1:1") or a math span is not a subtitle. Colon-subtitle and
   question titles are HIGH in `publication-figures/scripts/figure_lint.py`.
3. **Panel description**: (a), (b) or (A), (B) — case consistency
4. **Experimental conditions**: Substrate concentration, temperature, pH, time, rpm
5. **Normalization basis**: When using "Relative amount", specify reference
6. **n and error**: "Data are mean ± SD (n = 3 independent experiments)"
7. **Abbreviations**: Full name on first mention in caption
8. **No mathtext in captions**: `\mathrm{...}`, `\it{...}`, `^+` etc. are matplotlib/LaTeX codes —
   forbidden in Word/journal captions. Use plain text with italic formatting (*Ec*Adh) and Unicode
   superscripts (NAD⁺, NADP⁺).
9. **Enzyme name integration**: "Maximum X mM." as a standalone sentence should be integrated as a
   clause instead: "…, reaching a maximum of X mM at Y h."
10. **No internal-facing content** [Auto-detectable]: a caption describes the figure to a reader who
    has never seen the project. It is not a place to defend a choice, log an open task, or point at
    an earlier draft. Delete, do not soften:
    - **Justifying a methodological choice the figure no longer shows.** A caption that explains why
      an earlier, different version of the analysis was used, once the figure has moved on, is
      explaining a decision the reader cannot see.
    - **Open issues and tracker links.** A caption never cites an internal ID (Notion, Asana, Jira)
      and never carries status emoji (🔴/⚠️/✅) — that belongs in the tracker, not under a published
      figure.
    - **Comparisons against earlier versions of our own work.** "not comparable point-for-point with
      an earlier, narrower-box front" compares against something the reader has never seen. State
      the basis the figure actually uses; drop the history.
    - **Shouted emphasis.** "a DIFFERENT comparison" in capitals is a note to a collaborator, not
      reader-facing text. If the distinction matters, say it in words the sentence already allows.

    What stays: anything a reader needs to read the plot correctly — a basis definition, a bound the
    optimizer hit, a condition that was clipped, an uncertainty that is plotted versus one that is
    not. The test is not "is it a caveat" but **"does the reader need it to read this figure"** — a
    limitation that changes how the data should be read stays; a record of what is not yet finished
    goes.

    The FLAG-ONLY regex list for this item (`CAPTION_INTERNAL_FLAGS`: tracker IDs, status emoji,
    open-task language, "reported as shipped", "not comparable point-for-point", shouted
    DIFFERENT/SAME/NOT/ONLY) lives in `skills/publication-figures/scripts/caption_style.py`
    so every checker shares ONE copy. Each hit is a candidate for deletion, not an automatic
    edit - read the sentence and apply the test above first.

    > These rules govern the caption's TEXT. Two adjacent failures they do not catch: whether the
    > picture above the caption is the right picture, and whether it still sits on the same page as
    > the caption. When a caption-editing job touches figures, also check pagination and file-to-slot
    > mapping (map files to slots by caption text, not by filename).

11. **No restatement of visible data, no causal interpretation** [Flag-only, manual judgment on the
    cut]: a caption tells the reader what the figure/table shows and how to read it — not what it
    means. Two failure modes, distinct from #10 above:
    - **Restating a value the plot/table already displays** as a standalone caption sentence (e.g.,
      "X yielded the highest titer (55.6 ± 3.0 mM)." when the bar/point is plotted). If the value is
      needed to disambiguate an otherwise-ambiguous panel (e.g., which of several close lines is
      which), keep it; if it is simply readable off the axis, delete it.
    - **Causal or comparative interpretation that belongs in the body** ("X rises because Y", "the
      difference is due to Z"). Test: does the reader need this sentence to read the panel correctly,
      or is it explaining why the data looks the way it does? The former stays; the latter moves to
      Results/Discussion, or is deleted if already stated there.
    - Filler disclaimers ("X was not performed and is not shown here") belong nowhere in a caption —
      either the item is absent from the figure (say nothing) or its absence matters to
      interpretation (state the scope directly, without the "was not performed" framing).

    **Detector (FLAG-ONLY, `caption_style.INTERPRETIVE_FLAGS`, MED)** - interpretive or
    rhetorical connectives that explain the data instead of describing it. Each hit is a
    candidate for a human decision (keep only if the reader needs it to read the panel), never
    an auto-edit:

    ```python
    INTERPRETIVE_FLAGS = [
        r'\bso that\b', r'\btherefore\b', r'\bhence\b', r'\bthus\b',
        r'\brather than being\b',                       # bare "rather than" is too broad
        r'\bnot (?:a )?preferences?\b', r'\bequally good\b', r'\bnow also\b',
        r'\b(?:was|were) not (?:performed|computed|run|done|measured)\b',
        r'\bdominates?\b', r'\bis the axis that\b', r'\bcost-free\b', r'\bacts? the same way\b',
    ]
    ```
    Example of a caption that trips several at once: "... so that parallel lines mean the
    variable acts the same way everywhere ... rather than being cost-free ... the reference
    values are equally good ... was not computed."

    🔴 **A caption sidecar is GENERATOR OUTPUT, not a source** (`<name>.caption.txt` in the
    figure-generation repo is written by the render script's caption function or f-string). A
    caption fix therefore goes into the render script's caption generator; then re-run the script
    and require `git diff -- <sidecar>` to show the intended text and nothing else. A
    manuscript-only or sidecar-only edit regresses on the next re-sync or re-render. Measured
    case: several caption fixes were applied to sidecars only; re-running the scripts later
    regenerated the deleted sentences because the generators still emitted the old text. Before
    promoting any integer version, diff the manuscript caption text against its sidecar for every
    figure the promotion touched, and lint the sidecar (`figure_lint.py <render script>` reads
    the committed sidecar).

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

