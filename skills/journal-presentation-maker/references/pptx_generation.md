# python-pptx Generation Reference

Low-level implementation details for Step 3 (Presentation Generation) of journal-presentation-maker.
Read this when actually generating the .pptx (font sizing, figure-slide layout, post-processing).

## Font Size Reference Table (13.33" x 7.5" widescreen)

| Element | Font size | Style | Color |
|------|-----------|--------|------|
| Content slide header | **Pt(26)** | bold | WHITE (DARK_BLUE background) |
| Figure slide header | **Pt(26)** | bold | WHITE (DARK_BLUE background) |
| Section subtitle (in box) | **Pt(18)** | bold | ORANGE / MID_BLUE |
| Figure slide subtitle | **Pt(14)** | bold + italic | MID_BLUE |
| Body bullets (main slides) | **Pt(16)** | regular | DARK_GRAY |
| Key point bullets (figure slides) | **Pt(14)** | regular | DARK_GRAY |
| Table header | **Pt(12)** | bold | WHITE (DARK_BLUE background) |
| Table cell | **Pt(12)** | regular | DARK_GRAY |
| Figure caption | **Pt(9.5)** | italic | MID_GRAY (`#888888`) |
| Footer text | **Pt(9-10)** | regular | LIGHT_GRAY |
| Slide conditions/annotations | **Pt(12)** | regular | MID_BLUE |

> **Header bar height**: Inches(1.1), margin_left Inches(0.4), margin_top Inches(0.12)
> **Figure slide subtitle position**: top Inches(1.15), height Inches(0.5)
> **Key point start position**: top Inches(1.7), height Inches(1.3) (for 3 bullets)

## Figure-dedicated Slide Layout Template

Use the following layout when placing paper figures on dedicated slides:

```python
def make_figure_slide(prs, title, subtitle, key_points, fig_path, caption_text):
    """
    Figure-dedicated slide layout (13.33" x 7.5"):
      0.00" -- DARK_BLUE header bar (1.1") -- title Pt(26) WHITE bold
      1.15" -- subtitle (0.5") ------------ Pt(14) MID_BLUE bold italic
      1.70" -- key points (1.3") ---------- bullet 3 items Pt(14) DARK_GRAY
      3.10" -- figure image (variable) ---- center-aligned, maintain ratio
      fig_top+fig_h+0.06" -- caption (0.75") -- Pt(9.5) italic MID_GRAY
      7.12" -- footer (0.38") ------------- Pt(9) LIGHT_GRAY
    """
    DARK_BLUE = RGBColor(0x1A, 0x35, 0x5E)
    MID_BLUE  = RGBColor(0x2E, 0x5E, 0x9B)
    DARK_GRAY = RGBColor(0x33, 0x33, 0x33)
    MID_GRAY  = RGBColor(0x88, 0x88, 0x88)
    WHITE     = RGBColor(0xFF, 0xFF, 0xFF)
    W = prs.slide_width
    H = prs.slide_height

    sl = prs.slides.add_slide(prs.slide_layouts[6])  # blank
    sl.background.fill.solid(); sl.background.fill.fore_color.rgb = WHITE

    # 1. Header bar
    bar = sl.shapes.add_shape(1, Inches(0), Inches(0), W, Inches(1.1))
    bar.fill.solid(); bar.fill.fore_color.rgb = DARK_BLUE
    bar.line.fill.background()
    tf = bar.text_frame; tf.word_wrap = True
    tf.margin_left = Inches(0.4); tf.margin_top = Inches(0.12)
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.LEFT
    run = p.add_run(); run.text = title
    run.font.size = Pt(26); run.font.bold = True
    run.font.color.rgb = WHITE; run.font.name = "Arial"

    # 2. Subtitle
    txb = sl.shapes.add_textbox(Inches(0.4), Inches(1.15), W - Inches(0.8), Inches(0.5))
    txb.text_frame.word_wrap = True
    p2 = txb.text_frame.paragraphs[0]; p2.alignment = PP_ALIGN.LEFT
    run2 = p2.add_run(); run2.text = subtitle
    run2.font.size = Pt(14); run2.font.bold = True; run2.font.italic = True
    run2.font.color.rgb = MID_BLUE; run2.font.name = "Arial"

    # 3. Key points
    kp_box = sl.shapes.add_textbox(Inches(0.4), Inches(1.7), W - Inches(0.8), Inches(1.3))
    kp_box.text_frame.word_wrap = True
    first = True
    for kp in key_points:
        p3 = kp_box.text_frame.paragraphs[0] if first else kp_box.text_frame.add_paragraph()
        first = False
        p3.space_before = Pt(4)
        run3 = p3.add_run(); run3.text = "  *  " + kp
        run3.font.size = Pt(14); run3.font.color.rgb = DARK_GRAY; run3.font.name = "Arial"

    # 4. Figure insertion (maintain aspect ratio)
    from PIL import Image as PILImage
    with PILImage.open(fig_path) as img:
        orig_w, orig_h = img.size
    CAPTION_H = Inches(0.75); FOOTER_H = Inches(0.38)
    avail_h = H - FOOTER_H - CAPTION_H - Inches(3.1) - Inches(0.1)
    avail_w = W - Inches(0.6)
    scale = min(avail_w / orig_w, avail_h / orig_h)
    fig_w = orig_w * scale; fig_h = orig_h * scale
    fig_left = (W - fig_w) / 2
    fig_top  = Inches(3.1) + (avail_h - fig_h) / 2
    sl.shapes.add_picture(fig_path, fig_left, fig_top, fig_w, fig_h)

    # 5. Caption
    cap_box = sl.shapes.add_textbox(
        Inches(0.3), fig_top + fig_h + Inches(0.06),
        W - Inches(0.6), CAPTION_H)
    cap_box.text_frame.word_wrap = True
    first_cap = True
    for line in caption_text.split("\n"):
        p4 = cap_box.text_frame.paragraphs[0] if first_cap else cap_box.text_frame.add_paragraph()
        first_cap = False
        run4 = p4.add_run(); run4.text = line
        run4.font.size = Pt(9.5); run4.font.italic = True
        run4.font.color.rgb = MID_GRAY; run4.font.name = "Arial"
        if "et al." in line:
            run4.font.bold = True
            run4.font.color.rgb = DARK_GRAY

    return sl


def insert_slide_at(prs, new_slide, position):
    """Insert new_slide at position index in prs"""
    slides = prs.slides._sldIdLst
    new_elem = slides[-1]
    slides.remove(new_elem)
    slides.insert(position, new_elem)
```

## Post-processing Script Pattern (Post-processing Workflow)

Separating content creation, figure insertion, and note writing makes maintenance easier.
The three scripts below are **illustrative names for scripts you write yourself** — this
skill does not bundle them:

```
Step 1 (e.g. your own "make_ppt" script)    -> Generate 11 content slides (base PPTX)
Step 2 (e.g. your own "fix_figures" script) -> Insert figure-dedicated slides (base -> v2, 15 slides)
Step 3 (e.g. your own "update_notes" script)-> Full slide note update (v2 in-place modification)
```

Each script can run independently, making it easy to rewrite only notes or replace only figures.

> **Windows encoding note**: When using Korean/special characters in console output, add at first line:
> ```python
> import sys; sys.stdout.reconfigure(encoding='utf-8')
> ```

### 1. Plan presentation structure (maximum 30 slides):
   - Title slide
   - Introduction (2-4 slides)
   - Methods overview (1-3 slides)  
   - Results (8-12 slides, figure-heavy with original captions)
   - Discussion (2-4 slides)
   - Conclusion (1 slide)
   - References (1-3 slides)

### 2. Create CSS styling (see [references/styling_guide.md](styling_guide.md)):
   ```css
   /* shared-styles.css */
   :root {
     --primary-dark: #1a365d;
     --primary-medium: #2c5282;
     --text-base: 20px;
     --text-xl: 32px;
     --font-family: 'Arial', sans-serif;  /* REQUIRED: Use Arial */
   }
   
   body, h1, h2, h3, h4, h5, h6, p, li {
     font-family: var(--font-family);
   }
   ```

### 3. Generate HTML for each slide:
   - Use Arial font for all text
   - Include in-slide citation: [1,2,3]
   - Place detailed citation in speaker notes
   
   **For Introduction/Discussion slides**:
   - Include claims with reference numbers: "Recent studies show... [1,2]"
   - Track which papers support each claim

   **For Results slides**:
   - Include figures with complete original captions
   - Add reference at end of caption: "(Figure 2 from [3])"

   **Academic notation application examples (applying Step 2.5 rules)**:
   ```html
   <!-- Chemical formula + species name -->
   <p>D-glucose converted to D-fructose by <em>E. coli</em>-derived xylose isomerase (EC 5.3.1.5)
   (K<sub>m</sub> = 15 mM, <em>k</em><sub>cat</sub> = 120 s<sup>-1</sup>)</p>

   <!-- Gene/protein distinction -->
   <p>Activity of XylA protein encoded by the <em>xylA</em> gene was measured</p>

   <!-- Statistics notation -->
   <p>Yield 85 +/- 3% (<em>n</em> = 3, <em>p</em> &lt; 0.01)</p>

   <!-- Units (space between number and unit) -->
   <p>Reaction conditions: 50 mM Tris-HCl (pH 7.5), 37 degrees C, 2 h</p>
   ```

### 4. Create schematic diagrams for each section:
   ```html
   <!-- Use SVG or simple HTML/CSS diagrams -->
   <div class="schematic">
     <!-- Summarize key concepts from multiple papers -->
     <!-- Show workflow, mechanism, or relationships -->
     <!-- Add caption explaining the synthesis -->
   </div>
   <p class="caption">
     Schematic summary of [topic] integrating findings from [1,2,5].
   </p>
   ```

### 5. MANDATORY: Add comprehensive speaker notes to EVERY slide:

   Speaker notes are REQUIRED for all slides. Each slide must include:

   **For Title Slide**:
   ```
   [Greeting and introduction]
   - Paper title, authors, journal information
   - Importance of paper and reason for selection
   - Overview of presentation order
   ```

   **For Content Slides**:
   ```
   [Slide topic]
   - Detailed explanation of key points
   - Background knowledge and context
   - Points to emphasize during presentation

   [Sources]
   - [1] Kim et al. (2024), DOI: 10.1038/xxxxx
     -> Figure 2B (caption: "...")
   - [3] Lee et al. (2023), DOI: 10.1016/xxxxx
     -> Figure 1A (caption: "...")
   ```

   **For Discussion/Conclusion Slides**:
   ```
   [Discussion points]
   - Answer guide for each question
   - Anticipated questions and responses
   - Personal opinion/critique (strengths, weaknesses, limitations)
   ```

   **Speaker Notes Content Guidelines**:
   - Written in Korean (for presenter convenience)
   - **400-800 characters** per slide (too short causes difficulty during presentation)
   - Add header in `[Slide title -- section description]` format on first line
   - Write like a script of what to say during presentation
   - Include technical term explanations
   - Prepare anticipated audience questions and answers

   **Recommended note structure (figure slides):**
   ```
   [Figure N -- figure title]

   (a) Panel description:
     - Key point 1
     - Key point 2

   (b) Panel description:
     - Result values (e.g., 79+/-5% yield, 95% ee)
     - Comparison points

   Question point: 'Anticipated question?' -> Answer guide
   ```

   **Recommended note structure (content slides):**
   ```
   [Slide N -- section name]

   [Key content]
     - First point: detailed explanation
     - Second point: background knowledge

   [Experiment/method conditions]
     - Condition 1, Condition 2

   Note: Points to emphasize or content audiences may miss
   ```

   **"update_notes" pattern** (name your own script this if you follow this pattern) -- batch-update notes via separate script:
   ```python
   import sys; sys.stdout.reconfigure(encoding='utf-8')
   from pptx import Presentation

   NOTES = {
       1: "[Title slide -- presentation opening]\n\n...",
       2: "[Figure 1 -- research background]\n\n(a) ...\n(b) ...",
       # ...slide number (1-based): note text
   }

   prs = Presentation("presentation.pptx")
   for slide_idx, note_text in NOTES.items():
       notes_tf = prs.slides[slide_idx - 1].notes_slide.notes_text_frame
       notes_tf.clear()
       notes_tf.text = note_text
   prs.save("presentation.pptx")
   ```

### 6. Convert HTML to PowerPoint using html2pptx:
   ```javascript
   const pptxgen = require("pptxgenjs");
   const { html2pptx } = require("@ant/html2pptx");
   
   const pptx = new pptxgen();
   pptx.layout = "LAYOUT_16x9";
   
   // Process each HTML slide (max 30 slides)
   await html2pptx(pptx, "slide_01.html");
   await html2pptx(pptx, "slide_02.html");
   
   // Add notes to slides with reference details
   pptx.slides[0].addNotes("Speaker notes with [ref] sources...");
   
   await pptx.writeFile("presentation.pptx");
   ```

### 7. Create References slide:
   - List papers in order of first citation: [1], [2], [3]...
   - Use APA or Nature format
   - Include DOI links
