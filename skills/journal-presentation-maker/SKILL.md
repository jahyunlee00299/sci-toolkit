---
name: journal-presentation-maker
description: Automated academic presentation creation and review. Use when (1) creating journal club presentations, literature review slides, or research overview presentations, or (2) reviewing lab meeting/journal club PPTs for graph/table accuracy, scientific content validity, and speaker notes consistency. Searches academic databases (PubMed, Crossref, bioRxiv, arXiv), generates professional PowerPoint slides with Arial font and speaker notes. Also reviews existing PPTs via python-pptx analysis and OneDrive PowerPoint Online visual inspection.
---

# Journal Presentation Maker

## Execution Method
All tasks in this skill must be run as a subagent using the **Agent tool**.
Do not run directly; delegate the entire task to the Agent.

## Complementary Skills

| Skill | When to use together |
|------|----------------|
| **pubmed-database** | Direct PubMed query for paper search |
| **openalex-database** | Auto-collect paper metadata and citation counts |
| **biorxiv-database** | Preprint-specific search for bioRxiv/medRxiv |
| **literature-review** | Systematic literature review (PRISMA criteria) |
| **research-search** | Literature review and fact-checking |
| **markitdown** | Convert local PDF to Markdown for content extraction |
| **paper-2-web** | Convert paper PDF to web page (easier figure extraction) |
| **publication-figures** | Generate mechanism/workflow diagrams |
| **publication-figures** | When creating new graphs/figures |
| **markdown-mermaid-writing** | Structural diagrams (flow, timeline, ER) |
| **manuscript-pipeline** | Validate academic quality of slide text |
| **endnote-citation-injection** | Insert and format citations |
| **academic-term-rules** | Auto-validate biotech/biochemistry academic notation |
| **pptx** | Build/inspect the .pptx file itself |

### Recommended Workflow

```
openalex-database / pubmed-database / research-search    <- Gather papers
         |
         v
literature-review                      <- Systematic review
         |
         v
markitdown / paper-extract             <- Extract PDF content
         |
         v
journal-presentation-maker             <- Compose PPT
         |
         v
publication-figures                    <- Add new figures
         |
         v
manuscript-pipeline / endnote-citation-injection <- Clean text and citations
         |
         v
pptx-reviewer                          <- Final review
```

## Overview

Create professional academic presentations from research literature. Search multiple databases (peer-reviewed journals and preprints), intelligently filter papers by relevance and impact, extract key content, and generate structured slides with proper citation tracking.

## Workflow

### Step 1: Paper Search and Selection

Use web_search and web_fetch tools to search academic literature:

1. **Search strategy**:
   - Use web_search with targeted keywords for academic databases
   - Query multiple sources: PubMed, Google Scholar, bioRxiv/medRxiv, arXiv
   - Example: `web_search("multi-enzyme cascade biosynthesis PubMed")`

2. **Smart filtering** (apply automatically):
   - **Recent papers (2023-2025)**: Include regardless of citations
   - **Medium recent (2020-2022)**: Include if well-cited (50+ citations)
   - **Classic papers (pre-2020)**: Include only high-impact (200+ citations)
   - **Preprints**: Always include regardless of date/citations
   
3. **Retrieve paper details**:
   - Use web_fetch to access DOI links and get full metadata
   - Extract: title, authors, year, journal, abstract, figures
   - Target: 5-100 papers (user specifies range)

4. **Present to user**:
   ```
   1. [Title] (2024, Nature, cited: 245)
      Authors et al.
      DOI: 10.1038/xxxxx
   
   2. [Title] (2025, bioRxiv - PREPRINT)
      Authors et al.
      DOI: 10.1101/xxxxx
   
   3. [Title] (2018, Cell, cited: 523) ★ High-impact classic
      Authors et al.
      DOI: 10.1016/xxxxx
   ```

5. **User selects papers** to include in presentation

### Step 2: Content Extraction and Organization

1. **Fetch full paper content**:
   - Use web_fetch on DOI links
   - Extract: abstract, methods, results, discussion, tables
   - **CRITICAL**: Extract ALL figure captions completely

2. **Figure extraction strategy** (4-tier approach):

   **Priority**: Tier 0 (local PDF xref) -> Tier 1 (PMC) -> Tier 2 (Chrome screenshot) -> Tier 3 (Placeholder)

   **CRITICAL: Extract figure images only. Do NOT render full pages (get_pixmap) and insert into PPT.**
   - Full page rendering includes body text, captions, headers/footers in addition to figures -- inappropriate
   - Must use `extract_image(xref)` to extract only embedded figure images
   - If xref image is incomplete (mixed vector+raster) -> fallback to Tier 2 (Chrome screenshot)

   **Tier 0: Local PDF xref extraction (first priority -- most effective for paid journals)**

   If user provides a local PDF file, extract only embedded images using PyMuPDF (fitz).

   ```python
   import fitz  # PyMuPDF (pip install pymupdf)
   import os

   doc = fitz.open("paper.pdf")

   # 1. Check image list per page
   for page_num in range(len(doc)):
       page = doc[page_num]
       images = page.get_images(full=True)
       for img in images:
           xref = img[0]
           info = doc.extract_image(xref)
           w, h = info["width"], info["height"]
           print(f"Page {page_num+1}: xref={xref}, {w}x{h}, {info['ext']}")
           # Skip small images (logos, icons, data points, etc.)
           if w < 500 or h < 300:
               continue

   # 2. Save Figure image (xref-based — Figure portion only)
   doc.extract_image(xref)["image"]  # returns bytes
   with open(f"fig{n}.{ext}", "wb") as f:
       f.write(info["image"])
   ```

   **Figure caption extraction (text-based):**
   ```python
   for page_num in range(len(doc)):
       page = doc[page_num]
       text = page.get_text("text")
       # Find caption position by "FIGURE N" or "Fig. N" pattern
       idx = text.find("FIGURE 1")
       if idx >= 0:
           caption = text[idx:idx+600]  # ~500 characters
   ```

   **Inserting into PPT with python-pptx:**
   ```python
   from pptx.util import Inches
   from PIL import Image

   # Check original image size (preserve aspect ratio)
   with Image.open(fig_path) as img:
       orig_w, orig_h = img.size

   # Scale to fit slide area while preserving aspect ratio
   max_w = Inches(12.5)
   max_h = Inches(3.5)
   scale = min(max_w / orig_w, max_h / orig_h)
   fig_w = orig_w * scale
   fig_h = orig_h * scale

   # Center horizontally on slide
   fig_left = (slide_width - fig_w) / 2
   fig_top  = slide_height - fig_h - Inches(0.5)  # margin from bottom

   slide.shapes.add_picture(fig_path, fig_left, fig_top, fig_w, fig_h)
   ```

   **Advantages:**
   - No internet access required
   - Works perfectly for paid journals (Wiley, Elsevier, ACS, etc.)
   - Extracts original high-resolution images (2000px+ resolution common)
   - Accurately extracts all figures embedded in PDF
   - Can also extract caption text

   **Notes:**
   - Skip small images (width < 500px or height < 300px) -- likely logos/icons
   - If multiple images on one page, filter by size
   - Need to manually map PDF pages to paper figure numbers
     (e.g., Page 2 = Figure 1, Page 3 = Figure 2, etc.)
   - Requires PyMuPDF: `pip install pymupdf`
   - Requires Pillow (for size calculation): `pip install pillow`

   **Tier 1: PMC Open Access (first attempt when no local PDF)**
   - DOI to PMCID conversion: `web_fetch("https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/?ids={DOI}&format=json")`
   - Access PMC paper page: `web_fetch("https://pmc.ncbi.nlm.nih.gov/articles/{PMCID}/")`
   - Extract figure image URL: PMC figures are usually in `/pmc/articles/PMC.../figure/fig1/` format
   - Extract caption text alongside
   - Open Access papers allow direct figure access

   **Tier 2: Chrome MCP browser capture (when Tier 1 fails)**
   - Navigate paper page using browser tools:
     ```
     1. tabs_context_mcp -> confirm tab ID
     2. navigate(url=paper_URL, tabId=tabID)
     3. find(query="Figure 1" or "Fig. 1", tabId=tabID) -> locate figure element
     4. scroll_to(ref=figure_ref, tabId=tabID) -> scroll to figure
     5. computer(action="screenshot", tabId=tabID) -> capture full screen
     6. computer(action="zoom", region=[x0,y0,x1,y1], tabId=tabID) -> capture figure area only
     ```
   - Use captured screenshot as image to insert into slide
   - Must include figure caption and source attribution

   **Tier 3: Placeholder + user guidance (when both Tier 1 and 2 fail)**
   - Create figure placeholder box in slide:
     ```html
     <div class="figure-placeholder">
       <p>[Insert Figure X here]</p>
       <p class="citation">Source: Author et al. (Year), Figure X</p>
       <p class="instruction">Download: DOI_URL -> click Figure X -> save image</p>
     </div>
     ```
   - Provide detailed figure download instructions in speaker notes

3. **Figure Caption PPT insertion best practices:**

   1. **Caption position**: Directly below figure (Inches(0.06) margin), caption box height Inches(0.75)
   2. **Caption font**: **9.5pt**, italic, MID_GRAY (`#888888`) color
   3. **Caption content**: Full original paper caption (no abbreviation) + source attribution
   4. **Source format**: Last line of caption `(Author et al., Journal Year)` -- this line is bold + DARK_GRAY
   5. **Line breaks**: Split caption text by `\n` and add as separate paragraphs per line
   6. **Alignment**: LEFT alignment (better readability than CENTER)

   **Example caption implementation:**
   ```python
   CAPTION_H = Inches(0.75)
   cap_top = fig_top + fig_h + Inches(0.06)
   cap_box = slide.shapes.add_textbox(
       Inches(0.3), cap_top,
       slide_width - Inches(0.6), CAPTION_H)
   tf = cap_box.text_frame
   tf.word_wrap = True
   lines = caption_text.split("\n")
   first = True
   for line in lines:
       p = tf.paragraphs[0] if first else tf.add_paragraph()
       first = False
       p.alignment = PP_ALIGN.LEFT
       run = p.add_run()
       run.text = line
       run.font.size = Pt(9.5)
       run.font.italic = True
       run.font.color.rgb = RGBColor(0x88, 0x88, 0x88)
       if "et al." in line:          # source line: bold + dark color
           run.font.bold = True
           run.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
       run.font.name = "Arial"
   ```

4. **Figure attribution (required)**:
   - Source attribution for all figures: "(Figure X from [ref_num])"
   - Include complete original caption
   - If not Open Access, note "Adapted from" or "Reprinted with permission"
   - Record copyright information in speaker notes

5. **Organize content by section**:
   - **Introduction**: Background, motivation, research gap with in-text citations [1,2]
   - **Methods**: Experimental design, techniques, materials
   - **Results**: Key findings with figures and original captions
   - **Discussion**: Interpretation, implications, limitations with citations
   - **Conclusion**: Main takeaways, future directions

6. **Reference numbering system**:
   - Assign reference numbers in order of first appearance: [1], [2], [3]...
   - Track first mention of each paper in content
   - Maintain consistent numbering throughout presentation

7. **Track sources meticulously**:
   ```json
   {
     "slide_content": "...",
     "ref_numbers": [1, 3, 5],
     "sources": [
       {
         "ref_num": 1,
         "paper_idx": 0,
         "author": "Kim et al.",
         "year": 2024,
         "doi": "10.1038/xxxxx",
         "figures": ["Figure 2B", "Figure 3A"],
         "figure_captions": {
           "Figure 2B": "Original caption text...",
           "Figure 3A": "Original caption text..."
         }
       }
     ]
   }
   ```

8. **Figure recommendation**:
   - Identify most impactful figures from each paper
   - Prioritize: key results, mechanisms, summary figures
   - Include complete original captions
   - Suggest 1-2 figures per major finding

### Step 2.5: Slide Language & Academic Notation Rules

#### Slide Language Rules (MANDATORY)

- **Slide body**: Must be written in **English**. No Korean text.
  - Title, bullet points, captions, labels, References all in English
- **Speaker Notes**: Must be written in **Korean**. Korean script format for presenter convenience.
- This rule applies to all Journal Club and research presentation PPTs.

#### Academic Notation Rules (Academic Notation Enforcement)

Before placing content on slides, always apply the following academic notation rules:

#### Italic Rules
- **Gene names**: Distinguish by species
  - Human genes: italic + all caps -> *BRCA1*, *TP53*
  - Mouse genes: italic + first letter capitalized -> *Brca1*, *Tp53*
  - Proteins: not italic -> BRCA1 (protein), Brca1 (mouse protein)
- **Species names**: always italic -> *Escherichia coli*, abbreviated as *E. coli*
- **Latin terms**: *in vitro*, *in vivo*, *in situ*, *de novo*, *et al.* -- use italics
- HTML implementation: use `<em>` or `<i>` tags

#### Chemical Formula Notation
- **Subscripts** (atom counts): H2O, CO2, CH3OH, C6H12O6
- **Superscripts** (ion charges): Na+, Ca2+, Fe3+, SO42-, PO43-
- HTML implementation: `<sub>`, `<sup>` tags
  - Example: `H<sub>2</sub>O`, `Fe<sup>3+</sup>`
- **Reaction equations**: substrate -> product (use ->, Unicode U+2192)
- **Enzyme notation**: Include EC number (e.g., EC 5.3.1.5, D-xylose isomerase)

#### Unit Notation
- Follow SI units, space between number and unit:
  - Concentration: 5 uM, 10 mM, 0.1 M
  - Molecular weight: 45 kDa, 2.5 MDa
  - Temperature: 37 degrees C (space before degrees symbol)
  - Volume: 100 uL, 5 mL
  - Time: 2 h, 30 min, 10 s
  - pH: pH 7.4 (pH not italic, space before number)
- Wrong: `5uM` -> Correct: `5 uM`

#### Statistics/Numeric Notation
- p-value: *p* < 0.05 (italic lowercase p)
- Sample size: *n* = 10 (italic lowercase n)
- Standard deviation: mean +/- SD
- Yield/conversion: 95% yield, 85% conversion
- Michaelis-Menten parameters: K<sub>m</sub>, V<sub>max</sub>, *k*<sub>cat</sub>

#### Abbreviation Rules
- Spell out on first mention: "adenosine triphosphate (ATP)"
- Use abbreviation only afterward: "ATP"
- Manage abbreviation list per slide to avoid omissions

### Step 3: Presentation Generation

#### Output File Convention

- **Save path**: set via the `JC_DIR` environment variable (defaults to `~/presentations` if unset). Point it at wherever you keep presentations.
- **Filename format**: `YYMMDD_Journal Club Presentation.pptx` (e.g., `260308_Journal Club Presentation.pptx`)
  ```python
  import datetime, os
  from pathlib import Path
  JC_DIR = os.environ.get("JC_DIR", str(Path.home() / "presentations"))
  DATE_STR = datetime.date.today().strftime("%y%m%d")
  out_path = os.path.join(JC_DIR, f"{DATE_STR}_Journal Club Presentation.pptx")
  ```
- If presentation date differs from today, set `DATE_STR` directly (e.g., `DATE_STR = "260315"`)

#### Line Spacing Rules (MANDATORY)

**Must call `set_line_spacing()` on every paragraph. Without this, PowerPoint renders with default (1.0x) and text looks cramped.**

**CRITICAL: `disable_autofit()` must be applied**

PowerPoint ignores line spacing settings in textboxes where `spAutoFit` (auto-fit) is active.
`set_line_spacing()` alone is insufficient; `disable_autofit()` must also be called for 1.5x line spacing to actually apply.

```python
def disable_autofit(text_frame):
    """Disable spAutoFit so line spacing is respected by PowerPoint."""
    from pptx.oxml.ns import qn as _qn
    bodyPr = text_frame._txBody.find(_qn('a:bodyPr'))
    if bodyPr is not None:
        for child in bodyPr.findall(_qn('a:spAutoFit')):
            bodyPr.remove(child)
        for child in bodyPr.findall(_qn('a:normAutofit')):
            bodyPr.remove(child)
        etree.SubElement(bodyPr, _qn('a:noAutofit'))
```

**Application order** (common to all textboxes/bullet bodies):
1. `disable_autofit(tf)` -- disable auto-fit
2. `set_line_spacing(paragraph, 1.5)` -- set line spacing

Call `disable_autofit(tf)` in all helper functions that add text such as `add_bullet_body`, `add_textbox`, `add_multiline_textbox`.

| Text type | Line spacing | Applied function |
|------------|--------|----------|
| Body bullets (add_bullet_body) | **1.5x** | `line_spacing=1.5` (default) |
| General textbox (add_textbox) | **1.5x** | auto-applied when italic=False |
| Caption/italic/source text | **1.0x** | auto-applied when italic=True |
| References slide | **1.0-1.2x** | specify `line_spacing=1.0` or `1.2` |

**`set_line_spacing()` helper (must include)**:
```python
def set_line_spacing(paragraph, spacing):
    """Set paragraph line spacing using python-pptx API.
    spacing=1.5 for 1.5x, 1.0 for single."""
    paragraph.line_spacing = spacing
```

> **Do NOT use direct XML manipulation (`spcPct val=...`).** This may not be recognized by the PowerPoint UI.
> Always use `paragraph.line_spacing = spacing` (python-pptx built-in API).

`add_textbox` line spacing auto-apply pattern:
```python
def add_textbox(..., italic=False, line_spacing=None):
    ...
    if line_spacing is None:
        line_spacing = 1.0 if italic else 1.5
    set_line_spacing(p, line_spacing)
```

#### Generation Implementation Details

The low-level python-pptx details for this step — the font-size reference table
(13.33"×7.5" widescreen), the figure-dedicated slide layout template, and the
post-processing script pattern — are in **[references/pptx_generation.md](references/pptx_generation.md)**.

**Read `references/pptx_generation.md` before writing the slide-generation code.** The
MANDATORY rules above (line spacing via `set_line_spacing()`, `disable_autofit()`) still
apply — that reference shows the exact sizing and layout code that honors them.

### Step 4: Quality Checks

1. **Citation completeness**:
   - Every factual claim has reference number [1,2,3]
   - References numbered in order of first appearance
   - All figures attributed with original captions
   - References slide includes all cited papers in order

2. **Content quality**:
   - Maximum 30 slides total
   - Max 6-8 bullet points per slide
   - Max 40-50 words per slide (excluding title and captions)
   - Figures with complete original captions included
   - Section summary schematics present

3. **Technical validation**:
   - All fonts are Arial
   - All DOI links functional
   - Author names and years accurate
   - Reference numbers consistent throughout
   - Figure captions complete and attributed

4. **Speaker Notes validation (MANDATORY)**:
   - EVERY slide must have speaker notes
   - Notes written in Korean for presenter convenience
   - Each note includes:
     - Detailed explanation of slide content
     - Background context and terminology
     - Source citations with DOI
     - Talking points for presentation
   - Title slide: introduction and overview
   - Content slides: explanations and sources
   - Discussion slides: Q&A preparation
   - Final slide: summary and closing remarks

5. **Academic notation validation**:
   - Verify italic applied to gene names/species names (`<em>` or `<i>` tags)
   - Verify subscript/superscript accuracy for chemical formulas (`<sub>`, `<sup>`)
   - Verify space between unit and number (5 uM, not 5uM)
   - Verify abbreviations spelled out on first mention
   - Verify EC number included in enzyme names
   - Verify kinetic parameter notation accuracy: K<sub>m</sub>, V<sub>max</sub>
   - Verify italic for statistical symbols like *p*-value, *n*
   - Verify completeness of figure source attribution (attribution exists for all external figures)

### Step 5: Presentation Review (PPT Review)

Review the generated PPT file to check academic notation, layout, and citation accuracy.
This step can also be run independently when a user requests review of an existing PPT.

#### 5-1. Open PPT (2 methods)

**Method A: python-pptx programmatic analysis (local file -- recommended)**

Directly analyze local PPT file with python-pptx. No browser required, optimal for text-based precision inspection.

```python
from pptx import Presentation
from pptx.util import Pt

prs = Presentation("presentation.pptx")
for i, slide in enumerate(prs.slides):
    for shape in slide.shapes:
        if shape.has_text_frame:
            for para in shape.text_frame.paragraphs:
                for run in para.runs:
                    text = run.text
                    font = run.font
                    # Verify academic notation:
                    # - Italic: font.italic
                    # - Subscript: font.subscript (chemical formulas H2O, etc.)
                    # - Superscript: font.superscript (ion charges, etc.)
                    # - Font: font.name (verify Arial)
                    # - Size: font.size
```

Inspection items:
- Verify `font.italic = True` applied to gene names/species names
- Verify `font.subscript`/`font.superscript` applied to chemical formulas
- Space between numbers and units (regex `r'\d[umMkK]'` matching)
- Verify font is Arial
- Text quantity per slide (whether exceeding 40-50 words)

**Method B: University OneDrive + PowerPoint Online (visual review)**

Open PPT file synced to OneDrive in PowerPoint Online for visual review.
The university OneDrive is already logged in the browser, no separate authentication needed.

```
1. tabs_context_mcp -> confirm tab ID (createIfEmpty=true if no tab)
2. navigate(url="https://<your-tenant>-my.sharepoint.com/personal/<ACCOUNT_ID>/Documents/", tabId=tabID)
3. Browse OneDrive folder -> click PPT file -> PowerPoint Online opens automatically
4. Navigate slides by clicking in slide panel
5. computer(action="screenshot", tabId=tabID) -> capture slide
6. computer(action="zoom", region=[x0,y0,x1,y1], tabId=tabID) -> zoom detail area
```

- OneDrive local path: `$env:USERPROFILE\OneDrive - <YourOrg>\` (if you sync via OneDrive)
- PPT files placed in this folder sync automatically to OneDrive web
- Clicking PPT opens PowerPoint Online automatically (no Google Slides upload needed)

**Method selection criteria**:
- Precise text/notation error analysis -> **Method A** (python-pptx)
- Visual layout/figure rendering check -> **Method B** (OneDrive + PowerPoint Online)
- Optimal: **A + B combined** -- detect notation errors with python-pptx, then visually confirm in PowerPoint Online

#### 5-2. Per-slide Review Checklist

Analyze each slide screenshot and check the following items:

**A. Layout and readability**:
- [ ] Text does not overflow slide area
- [ ] Font size is sufficiently large (header Pt(26), body bullets Pt(16), table Pt(12), caption Pt(9.5))
- [ ] Margins are appropriate (text not touching edges)
- [ ] No overlap between figures and text
- [ ] Overall visual balance and alignment

**B. Academic notation accuracy** (Step 2.5 criteria):
- [ ] Italics: gene names (*xylA*), species names (*E. coli*), Latin terms (*in vitro*)
- [ ] Chemical formulas: subscripts/superscripts (H2O not displayed as H2O without subscript)
- [ ] Units: space between number and unit (5 uM, not 5uM)
- [ ] Statistical symbols: *p*, *n* italic
- [ ] Enzyme kinetic parameters: K_m correctly rendered as K<sub>m</sub>

**C. Figure quality**:
- [ ] Figures are actually inserted (no placeholders remaining)
- [ ] Figure resolution is sufficient (not pixelated or blurry)
- [ ] Figure captions are fully displayed (no truncation)
- [ ] Source attribution: "(Figure X from [ref_num])" exists

**D. Citation consistency**:
- [ ] In-slide citation numbers [1,2,3] are displayed
- [ ] References slide numbers match in-text citations
- [ ] DOIs are included

**E. Overall flow**:
- [ ] Slide order is logical (Introduction -> Methods -> Results -> Discussion -> Conclusion)
- [ ] Section transitions are natural
- [ ] Total slide count is appropriate (15-30 slides)

#### 5-3. Review Result Report

Report results to user in the following format after review completion:

```markdown
## PPT Review Results

### Overall Summary
- Total slides: X
- Passed review: Y items / Z total items
- Requires revision: N items

### Issues per Slide

**Slide 3 (Methods)**:
- [FAIL] "H2O" -> "H2O" (subscript missing)
- [FAIL] "E. coli" -> "*E. coli*" (italic missing)
- [WARN] Figure 1 resolution low -- recommend re-inserting original

**Slide 7 (Results)**:
- [FAIL] "5uM" -> "5 uM" (unit space missing)
- [FAIL] No figure source attribution -> add "(Figure 2A from [3])"

**Slide 12 (Discussion)**:
- [OK] All items passed

### Revision Priority
1. [HIGH] Academic notation errors (X items) -- directly affects presentation credibility
2. [MEDIUM] Figure quality/attribution (X items) -- copyright and readability
3. [LOW] Layout fine-tuning (X items) -- optional improvements
```

#### 5-4. Automated Correction Suggestions

Provide correction approaches for issues found during review:

- **Academic notation errors**: Present corrected text specifically (before -> after)
- **Figure issues**: Guide on alternative image source or re-capture method
- **Layout problems**: Provide CSS/HTML correction code (reflected in PPT regeneration)
- **Citation inconsistency**: Specify missing citation numbers and locations

Upon user approval, can regenerate PPT or partially revise to reflect issues.

### Step 6: Lab Meeting Presentation Review

Comprehensively review lab meeting PPT. Check accuracy of graphs/tables, scientific validity of slide content,
and appropriateness of speaker notes; report suggestions and errors.
Can be run independently from Journal Club PPT review (Step 5).

#### 6-1. Load PPT File

Use same method as Step 5-1:
- **Method A (python-pptx)**: Local file programmatic analysis -- precision inspection of text/numbers/notes
- **Method B (University OneDrive)**: PowerPoint Online visual review -- graph/layout check
- **Optimal**: A + B combined

Suggested lab-meeting PPT folder layout (point `$JC_DIR` / your own base at it):
```
<your presentations base>/
+-- research presentation/    <- Research presentation PPTs
+-- Journal Club/             <- Journal Club PPTs (Step 5 target)
+-- 20XX team meeting.pptx    <- Annual team meeting PPT
```

#### 6-2. Graph and Figure Review

**A. Graph quality check** (PowerPoint Online visual verification):
```
For each graph/chart:
1. computer(action="screenshot", tabId=tabID) -> capture slide
2. computer(action="zoom", region=[x0,y0,x1,y1], tabId=tabID) -> zoom graph area
3. Check checklist items below
```

- [ ] **Axis labels**: X-axis and Y-axis labels exist with units annotated
  - Correct: "Conversion (%)", "Time (h)", "Concentration (mM)"
  - Incorrect: missing axis labels, missing units
- [ ] **Axis range**: Appropriate range for data (no unnecessary whitespace, no clipped data)
- [ ] **Legend**: When multiple datasets exist, legend is present and distinguishable
- [ ] **Data points**: Error bars present, error bar type specified (SD, SEM, 95% CI)
- [ ] **Graph type suitability**: Graph type matches data characteristics
  - Time course -> line chart, comparison -> bar chart, distribution -> box plot, correlation -> scatter plot
- [ ] **Font size**: Text within graph is readable during presentation (>= 14pt recommended)
- [ ] **Color distinction**: Distinguishable even in black-and-white printing (color-blind accessible)
- [ ] **Figure number/caption**: Source is clear when citing paper figures

**B. Table review**:
- [ ] **Headers**: Column/row headers are clear with units annotated
- [ ] **Alignment**: Numbers right-aligned, text left-aligned
- [ ] **Significant figures**: Consistent decimal places used (e.g., all to 2 decimal places)
- [ ] **Statistical notation**: p-value, n count etc. noted in table or footnotes
- [ ] **Emphasis**: Key results highlighted in bold or color
- [ ] **Readability**: Not difficult to read due to too many rows/columns (<= 8 columns recommended)

**C. Graph value cross-check** (python-pptx):
```python
# Extract numerical values from slide text
import re
for slide in prs.slides:
    for shape in slide.shapes:
        if shape.has_text_frame:
            text = shape.text_frame.text
            # Extract key numbers like yield, conversion rate
            numbers = re.findall(r'(\d+\.?\d*)\s*(%|mM|uM|kDa|C|h|min)', text)
            # Compare with values in speaker notes
```
- Verify numbers in slide body match numbers in speaker notes
- Verify numbers mentioned in graph captions are not inconsistent with body text descriptions

#### 6-3. Scientific Validity Check of Content

**A. Logical flow**:
- [ ] Research objective/hypothesis clearly presented
- [ ] Experimental design appropriate for validating hypothesis
- [ ] Result interpretation is data-based (no over-interpretation)
- [ ] Control experiments included
- [ ] Conclusion logically derived from results

**B. Experimental conditions specified**:
- [ ] Reaction conditions (temperature, pH, time, concentration) noted
- [ ] Strain/cell line used specified
- [ ] Analytical method (HPLC, GC-MS, SDS-PAGE, etc.) specified
- [ ] Number of replicates (*n*) specified

**C. Comparison with existing literature**:
- [ ] Own results compared with existing research
- [ ] Discussion of differences/similarities present
- [ ] Literature citations appropriate

**D. Common scientific error check**:
- [ ] Not interpreting correlation as causation
- [ ] Statistical significance (*p* < 0.05) distinguished from biological significance
- [ ] Not generalizing single experiment results
- [ ] Negative results handled appropriately

#### 6-4. Speaker Notes Review

**A. Note existence check** (python-pptx):
```python
for i, slide in enumerate(prs.slides):
    notes_slide = slide.notes_slide if slide.has_notes_slide else None
    if notes_slide:
        notes_text = notes_slide.notes_text_frame.text
        # Analyze note content
    else:
        print(f"[WARN] Slide {i+1}: No speaker notes")
```

**B. Note quality checklist**:
- [ ] **Notes exist for all slides**: Detect empty note slides
- [ ] **Note-slide consistency**: Note content is related to corresponding slide content
  - Cross-check that slide title/keywords also appear in notes
  - Notes do not incorrectly reference other slide content
- [ ] **Number consistency**: Numbers mentioned in notes match slide graphs/text
  ```python
  # Compare slide body numbers vs note numbers
  slide_numbers = extract_numbers(slide_text)
  notes_numbers = extract_numbers(notes_text)
  mismatches = find_mismatches(slide_numbers, notes_numbers)
  ```
- [ ] **Sufficient length**: Each note at least 100 characters (too short causes difficulties during presentation)
- [ ] **Presentation tone**: Appropriate for spoken delivery (not paper text pasted directly)
- [ ] **Anticipated questions**: Discussion/Results slide notes have anticipated questions and answers prepared

**C. Note content accuracy verification**:
- Claims in notes are not inconsistent with slide data
- Literature information in notes (author, year) matches References
- Mechanism/method described in notes matches actual experiment

#### 6-5. Lab Meeting Review Result Report

```markdown
## Lab Meeting PPT Review Results

### Overall Summary
- Total slides: X
- Graphs/Figures: Y (N issues)
- Tables: Z (N issues)
- Speaker notes: present X / missing Y
- Total requiring revision: N items

### 1. Graph/Table Issues

**Slide 5 (Results - Conversion Graph)**:
- [FAIL] Y-axis label missing -> add "Conversion (%)"
- [FAIL] No error bars -> recommend adding SD or SEM error bars
- [WARN] X-axis range 0-100 but data concentrated in 0-50 range -> consider adjusting range

**Slide 8 (Results - Kinetics Table)**:
- [FAIL] K_m value decimal inconsistency: "15.2 mM" vs "15.23 mM" (within same table)
- [WARN] Need to unify significant figures

### 2. Scientific Content Issues

**Slide 10 (Discussion)**:
- [WARN] "Conversion rate was greatly improved" -> only qualitative expression without specific numbers
- [FAIL] Control result not presented -> insufficient basis for comparison
- [SUGGEST] Add quantitative comparison like "2.3-fold improvement over WT (85% vs 37%)"

**Slide 12 (Conclusion)**:
- [WARN] Conclusion includes generalization beyond data range shown in Results
- [SUGGEST] Add range-limiting expressions like "under these conditions"

### 3. Speaker Notes Issues

**Slide 3 (Methods)**:
- [FAIL] No speaker notes -> need to add note explaining experimental conditions

**Slide 7 (Results)**:
- [FAIL] Note value "90% conversion" inconsistent with slide graph "85%"
- [WARN] Notes appear to be paper text pasted directly -> recommend rewriting in spoken form

**Slide 11 (Discussion)**:
- [OK] 3 anticipated questions and answers prepared -- acceptable
- [SUGGEST] Also recommend adding question about "why this enzyme was chosen"

### 4. Overall Suggestions

#### [HIGH] Must fix (required before presentation)
1. Graph axis labels missing (slides 5, 9)
2. Slide-note number inconsistency (slide 7)
3. Control data not presented (slide 10)

#### [MEDIUM] Recommended (quality improvement)
4. Add error bars (slides 5, 6, 9)
5. Strengthen quantitative comparison expressions (slides 10, 12)
6. Add notes for slides without notes (slides 3, 4)

#### [LOW] Optional improvements (if time permits)
7. Unify significant figures in table (slide 8)
8. Optimize graph axis range (slide 5)
9. Add anticipated questions (slide 11)

### 5. Presentation Readiness Assessment
- Slide completeness: 3/5
- Data reliability: 4/5
- Speaker notes preparation: 2/5
- Anticipated question preparation: 3/5
- **Overall**: Presentable after addressing revision items
```

#### 6-6. Automated Correction Support

Suggest corrections based on review findings:

- **Graph issues**: Guide on adding axis labels, legends (using PowerPoint Online edit mode)
- **Number inconsistency**: Present accurate numbers unified on both sides (slide + notes)
- **Speaker notes supplement**: Auto-generate note draft for slides without notes
  ```python
  # Add/modify notes with python-pptx
  from pptx import Presentation
  prs = Presentation("labmeeting.pptx")
  slide = prs.slides[2]  # slide without notes
  notes_slide = slide.notes_slide
  notes_slide.notes_text_frame.text = "Generated speaker notes..."
  prs.save("labmeeting_reviewed.pptx")
  ```
- **Scientific expression improvement**: Present specific correction (before -> after)
- **Anticipated question generation**: Auto-generate 3-5 questions professors/colleagues might ask based on research content

## Example Usage

**User**: "Make a presentation about an N-step enzyme cascade for a target product"

**Claude**:
1. Searches PubMed, bioRxiv for "multi-enzyme cascade biosynthesis target product"
2. Finds 45 papers, filters to 15 most relevant
3. Presents list to user with citations and impact metrics
4. User selects 8 papers
5. Extracts content from all 8 papers including:
   - All figure captions
   - Key claims with context
   - Methods and results details
6. Assigns reference numbers in order of first mention: [1]-[8]
7. Generates 25-slide presentation with:
   - Title slide
   - Background (3 slides) - with claims cited as [1,2]
   - Enzyme systems (5 slides) - figures with original captions
   - Schematic summary (1 slide) - integrating findings from [1,3,5]
   - Cascade optimization (4 slides) - figures and data
   - Kinetic analysis (3 slides) - figures with captions from [6,7]
   - Applications (3 slides) - with citations [2,4,8]
   - Conclusion (1 slide)
   - References (2 slides) - papers listed [1]-[8] in order
8. All text in Arial font
9. EVERY slide has comprehensive Korean speaker notes:

   **Example - Title Slide Notes**:
   ```
   [Greeting and introduction]
   Hello. Today I will present the paper "Multi-Enzyme Cascades for Biosynthesis of a Target Product".

   [Importance of paper]
   - Presents a new paradigm for multi-step enzymatic production
   - High potential for industrial application

   [Presentation order]
   Background -> Methods -> Results -> Discussion -> Conclusion
   ```

   **Example - Content Slide Notes**:
   ```
   [Enzyme cascade mechanism]
   This slide explains the mechanism of the N-step enzymatic reaction.

   - First enzyme (Enzyme A): converts substrate S1 to intermediate I1
   - Second enzyme (Enzyme B): converts I1 to intermediate I2
   - Third enzyme (Enzyme C): converts I2 to the target product P

   [Sources]
   - [1] Kim et al. (2024), DOI: 10.1038/xxxxx
     -> Figure 2B (caption: "Enzymatic cascade for production of target product P...")
   - [3] Park et al. (2023), DOI: 10.1016/xxxxx
     -> Figure 1A (caption: "Reaction scheme showing...")

   [Presentation points]
   - Emphasize substrate specificity of each enzyme
   - Explain the significance of overall yield 85%
   ```

## Resources

### references/

- **[api_reference.md](references/api_reference.md)**: Database APIs, search strategies, citation metrics, data formats for PubMed/Crossref/preprint servers
- **[styling_guide.md](references/styling_guide.md)**: Academic presentation design patterns, color schemes, typography, layout templates, citation display formats
- **[pptx_generation.md](references/pptx_generation.md)**: Low-level python-pptx implementation for Step 3 — font-size table, figure-slide layout template, post-processing script pattern

**When to read**: 
- Read `api_reference.md` when implementing paper search
- Read `styling_guide.md` before creating slide HTML
- Read `pptx_generation.md` before writing slide-generation code (Step 3)

### scripts/

- **search_papers.py**: Template for paper search implementation (placeholder for actual API integration)
- **generate_presentation.py**: Template for presentation generation workflow (demonstrates content organization and note tracking)

**Note**: Scripts are templates showing structure. Actual implementation uses web_search and web_fetch tools combined with pptx skill workflow.
