<!-- Moved verbatim from AGENTS.md on 2026-10-07 so that AGENTS.md stays under the 32 KiB that Codex reads (`project_doc_max_bytes`). AGENTS.md keeps a stub with the rules in force; this file is the full text. -->

## 5. Figure Anti-Regression Rule
Figures for publication or reports are easy to silently regress (wrong
theme, broken caption, stale numbers) when re-generated repeatedly. Apply
this discipline:

- **Locked theme**: maintain one canonical plotting theme/style module
  (fonts, colors, sizes) that all figure scripts import — don't
  hand-tune styling inline per figure, and don't let a "quick fix" drift
  the theme for one figure away from the rest.
- **Lint gate**: run a figure linter (font consistency, missing axis
  labels, non-standard colors, resolution/DPI checks, etc.) before
  treating a figure as final. Target: zero high-severity lint findings.
- **Captions from rawdata only**: any number appearing in a figure
  caption is pulled from the same raw-data source as the plot itself
  (see Section 3) — never typed by hand.
- **Version control the figure pipeline, not just the output image**:
  commit the script/data changes *before* rendering, so regressions are
  traceable to a specific commit. Treat rendered images as build
  artifacts (can be regenerated, don't need their own manual history);
  the SSOT is the script + raw data.
- Recommended order: edit script → commit → render → visually verify the
  output actually looks right (don't assume a clean run == correct
  figure).
- Avoid repeatedly overwriting one review/gallery file if it destroys the
  ability to compare against a previous version — snapshot when it
  matters.
