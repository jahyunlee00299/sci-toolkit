# Table Formatting Standards (Biotech/Biochemistry Journals)

## 13. Table Formatting Standards (Biotech/Biochemistry Journals)

### Three-line table rule (booktab style)
- **Top rule** (thick): above column headers
- **Mid rule** (thin): below column headers
- **Bottom rule** (thick): below last data row
- **NO vertical lines** — never use column dividers
- **NO horizontal lines** between data rows (except for grouped sections: one thin line)

### Table title
- Placed **above** the table (unlike figure legends which go below)
- Format: **Table N.** Bold number + period, then sentence-case title (not bold)
- Example: **Table 1.** Bacterial strains and plasmids used in this study.
- No period at end of title is acceptable in some journals — pick one style and be consistent

### Table footnotes
- Placed **below** the table
- Marked with superscript lowercase letters (ª, ᵇ, ᶜ) or symbols (†, ‡) — not numbers (numbers conflict with data)
- First footnote: define all abbreviations used in the table that were not defined in the main text
- Subsequent footnotes: clarify specific cells, conditions, or sources

### Column header rules
- Sentence case (not ALL CAPS)
- Units in parentheses on same line: "Concentration (mM)" or separate subheader row
- Italic for gene/species-derived symbols (*K*m, *k*cat, *V*max)
- Align: text columns left, numeric columns right or decimal-aligned

### Data cell rules
- Numerical data: consistent decimal places within a column
- "–" (en dash) for not determined / not applicable (never blank, never "N/A" unless defined)
- Mean ± SD format in cells; n stated in footnote or column header

### In-text reference
- "Table 1" (capital T, no abbreviation) when referring to a specific table
- "(Table 1)" in parenthetical citation

### docx XML implementation
- Borders: top/bottom = `<w:top>/<w:bottom>` with `w:sz="12"` (thick); mid = `w:sz="6"` (thin)
- No left/right/insideV borders on any cell
- InsideH borders: only on header row bottom (= mid rule); none between data rows
- Cell padding: top/bottom 80 twips, left/right 120 twips

```python
# Three-line table border pattern for docx XML
# CRITICAL: use w:start/w:end (NOT w:left/w:right) in both tcBorders and tcMar
# CRITICAL: element order must be top → start → bottom → end (schema-enforced)

# Header row cells: thick top + thin bottom, no start/end
# <w:tcBorders>
#   <w:top w:val="single" w:sz="12" w:space="0" w:color="000000"/>
#   <w:start w:val="none" w:sz="0" w:space="0" w:color="auto"/>
#   <w:bottom w:val="single" w:sz="6" w:space="0" w:color="000000"/>
#   <w:end w:val="none" w:sz="0" w:space="0" w:color="auto"/>
# </w:tcBorders>

# Last data row: thick bottom only
# Data rows: all none

# tcMar padding (also uses start/end, same order):
# <w:tcMar>
#   <w:top w:w="80" w:type="dxa"/>
#   <w:start w:w="120" w:type="dxa"/>
#   <w:bottom w:w="80" w:type="dxa"/>
#   <w:end w:w="120" w:type="dxa"/>
# </w:tcMar>
```

