# Word COM Structural QC — Formatting Leakage, Font Script-Slot Gaps, Page-Break Duplication

## 18a. Word COM Structural QC — Paragraph-Move Formatting Leakage, Font Script-Slot Gaps, Page-Break Duplication [Auto-detectable]

Found while moving a figure caption between sections with Word COM (`win32com.client`). Three
distinct defect classes can surface from ONE root cause — cutting a `Range` block whose insertion
point turns out to be mid-sentence — and none of them are caught by any text-level QC pass (§1–17),
because the text content itself is untouched; only paragraph-level and character-level formatting
attributes are corrupted.

### 18a-i. Paragraph-mark formatting leakage after cut/paste

When a `Range` block (figure + caption + spacer paragraph) is cut from one location and pasted into
another, the **paragraph mark** at the cut boundary carries its own formatting (`Alignment`,
`PageBreakBefore`, spacing) independent of the run-level text formatting. If the paste point is
mid-sentence rather than a clean paragraph boundary, Word can split the sentence into two paragraphs
and misattribute the *donor* paragraph's mark-level formatting (e.g. a Center-aligned,
`PageBreakBefore=True` figure-placeholder paragraph) to the *wrong* half of the split.

**Symptom**: a body-prose paragraph is unexpectedly Center-aligned (or otherwise carries
figure/scheme-placeholder formatting) with no reason for it in the visible text.

**Detection** — scan every text-bearing (non-empty, non-InlineShape-only) paragraph in the document
body:
```python
# win32com.client — flag any real prose paragraph that isn't Justify/Left
for i, para in enumerate(doc.Paragraphs):
    text = para.Range.Text.strip()
    if not text or text in ('\r', '\x0c') or para.Range.InlineShapes.Count > 0:
        continue  # figure/scheme placeholder paragraphs are legitimately Center
    align = para.Range.ParagraphFormat.Alignment
    if align not in (wdAlignParagraphJustify, wdAlignParagraphLeft):
        flag(i, f"prose paragraph with Alignment={align}")
```
Cross-check: a body-prose paragraph carrying `PageBreakBefore=True` with no section-heading or
Table/Figure-caption justification nearby is the same signature.

**Fix**: reset `ParagraphFormat.Alignment` and `PageBreakBefore` to match the surrounding document's
standard body-paragraph formatting (read a known-clean neighbor paragraph as the template, don't
hardcode a value) — then verify the sentence reads as ONE unbroken paragraph across the (former)
split point; a cut/paste that split a sentence usually still needs the two halves rejoined into one
paragraph, not just the alignment fixed.

**Prevention**: before any `Range` cut/paste that moves a figure/caption/scheme block, confirm the
exact cut boundaries land on paragraph marks, not mid-sentence — print the 30 characters immediately
before the start and after the end of the cut range and confirm each is a clean sentence/paragraph
boundary, not inside running prose.

### 18a-ii. Font script-slot gaps (`NameFarEast`/`NameOther`/`NameBi`) surviving a "fixed" style

Word's `Font` object carries **separate slots per script**: `Name`/`NameAscii` (Latin text),
`NameFarEast` (CJK), `NameOther` (other complex scripts), `NameBi` (bidirectional/Arabic-Hebrew).
Setting only `Font.Name`/`Font.NameAscii` on a style (e.g. "fixing" Normal/Caption/Heading 1/
Heading 2/bibliography style from a CJK default font to Arial) leaves `NameFarEast` pointing at the
old CJK font. Word silently routes certain Unicode characters — subscript/superscript digits, smart
quotes, the Unicode hyphen (U+2010) — through the FarEast slot even inside otherwise-Latin text, so
a single stray character (e.g. the "₂" in "Ca(OH)₂") renders in the wrong font while the surrounding
text is correctly Arial. This makes the defect **look fixed** (style inspector shows
`Font.Name = "Arial"`) while individual characters still leak — a font-fix pass that only checks
`Font.Name`/`NameAscii` will falsely report success.

**Detection** — a character-level scan is required; a run/paragraph-level `Font.Name` check is not
sufficient:
```python
# win32com.client — walk character-by-character, not run-by-run
for i in range(1, doc.Characters.Count + 1):
    ch = doc.Characters(i)
    f = ch.Font
    for slot_name in ('Name', 'NameFarEast', 'NameOther', 'NameBi'):
        slot_font = getattr(f, slot_name)
        if slot_font and slot_font != 'Arial':
            flag(i, f"{slot_name}={slot_font}")
```
Also audit every style actually in use (`doc.Styles`) for all four slots, not just `Name`:
```python
for style in doc.Styles:
    for slot_name in ('NameAscii', 'NameFarEast', 'NameOther', 'NameBi'):
        val = getattr(style.Font, slot_name)
        if val and val != 'Arial':
            flag(style.NameLocal, f"{slot_name}={val}")
```

**Fix, in order**:
1. Set all four slots (`NameAscii`, `NameFarEast`, `NameOther`, `NameBi`) — not just `Name` — to the
   target font on every style actually applied in the document (check styles beyond Normal:
   Caption, Heading 1/2, bibliography style, Keywords, etc. each have independent font inheritance
   and any one can retain a stale CJK/Math font).
2. For characters already carrying **direct (run-level) formatting** that overrides the style —
   a style-level fix alone will not reach these — force all four slots plus `Font.Name` on the
   specific `Range` via direct assignment.
3. Re-run the character-level scan (step above) and require zero remaining non-target-font
   characters before considering the pass complete.

**Note on autocorrect-substituted math font**: a related but distinct cause is Word's autocorrect
silently swapping certain characters (Unicode hyphen U+2010, superscript ⁺) into `Cambria Math`
regardless of style settings — this is not a `NameFarEast` inheritance problem and needs the same
character-level force-fix, but does not need a style-level correction (there is no "Math" style to
fix; it is autocorrect-driven direct formatting).

### 18a-iii. Page-break duplication after paragraph-mark leakage

A direct consequence of 18a-i: when a `PageBreakBefore=True` mark-level attribute leaks onto a
paragraph immediately adjacent to another paragraph that *also* has `PageBreakBefore=True` (or an
inserted `\x0c` form-feed break character), the two breaks stack and produce one blank page.

**Detection**: walk consecutive paragraphs' `PageBreakBefore` alongside the document's printed page
numbers (`Range.Information(wdActiveEndPageNumber)`); a jump of more than 1 page between adjacent
paragraph indices with no intervening large table/figure is the signature. Do not detect by counting
`\x0c` occurrences alone — a leaked `PageBreakBefore` attribute produces the same symptom without an
explicit break character.

**Fix**: identify which of the two (or more) stacked page-break sources is legitimate (usually the
pre-existing one tied to a real section/figure boundary) and clear `PageBreakBefore` on the other —
do not delete the form-feed character if it is the intentional pre-existing break.
