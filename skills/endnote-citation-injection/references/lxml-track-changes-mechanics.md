# Phase 7 — lxml Track Changes application mechanics

Full worked algorithm, XML element format, and code patterns for applying
citation transformations as Word Track Changes via lxml. The governing
rules (never use ElementTree, ins-after-del ordering) are stated in
SKILL.md Phase 7 — this file is the mechanical detail behind them.

## Algorithm

For each transformation:
1. Find the paragraph (lxml `root.iter(f'{W}p')`) containing the substring (concat `<w:t>` text)
2. Within paragraph, identify involved `<w:r>` runs
3. Build replacement structure:
   ```
   prefix_run + <w:del>middle</w:del> + <w:ins>new_text</w:ins> + suffix_run
   ```
4. Place `<w:ins>` BETWEEN `<w:del>` and suffix run — this is what keeps period/comma after the citation, not before

## Period-before-citation fix

**Wrong** (places ins at end of involved range):
```
prefix → del → suffix → ins
```
Result after Accept All: `text. {Author}` ← period goes BEFORE citation. Bad.

**Correct** (place ins immediately after del):
```
prefix → del → ins → suffix
```
Result: `text {Author}.` ← period stays after, as required by academic style.

## Leading space removal (optional but recommended)

User often wants `text{Author}` not `text {Author}`. Extend deletion to include preceding space:
```python
if idx > 0 and full[idx-1] == ' ':
    idx -= 1   # absorb single leading space into the deletion
```

This makes `text (Author, Year). next` → `text{Author, Year #N}. next` (no space between "text" and brace).

## Multi-run handling

Word splits text into multiple `<w:r>` runs when formatting changes (italic species names, superscripts, etc.). The substring may span multiple runs. Algorithm:

1. Concatenate all `<w:t>` in paragraph → find substring index
2. Determine which runs overlap [idx, idx+len]
3. For each involved run: split into `prefix` (before match) / `middle` (matched) / `suffix` (after match)
4. Rebuild paragraph children: `[all prefixes] + [all dels (middle wrapped)] + [ins] + [all suffixes]`

## `<w:ins>` / `<w:del>` element format

```xml
<w:del w:id="100000" w:author="Citation Update" w:date="2026-05-07T20:30:00Z">
  <w:r><w:rPr/><w:delText>(Author, 2020)</w:delText></w:r>
</w:del>
<w:ins w:id="100001" w:author="Citation Update" w:date="2026-05-07T20:30:00Z">
  <w:r><w:rPr/><w:t>{Author, 2020 #N}</w:t></w:r>
</w:ins>
```

Note: deletion uses `<w:delText>`, insertion uses `<w:t>`. ID must be unique per change. Author and date appear in Word's review pane.

## Apply incrementally per find_text group

Same substring may appear multiple times in same paragraph (e.g., `(Liu et al., 2019)` appearing twice). Loop within paragraph:
```python
for find_text, ops in op_groups.items():
    found_count = 0
    for p in all_paragraphs:
        if found_count >= len(ops): break
        while found_count < len(ops):
            full = concat_text(p)
            if find_text not in full: break
            replace_track(p, find_text, ops[found_count]['replace'])
            found_count += 1
```
