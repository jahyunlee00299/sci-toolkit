# Paper download (journal mode, Agent 1)

> Moved here verbatim on 2026-10-02 from the retired `commands/journal-ppt-team.md`
> (config repo copy, the PDF-first / Unpaywall-first revision) so the logic this skill
> reuses no longer depends on the retired command. Off-campus (EZproxy) access is
> quota-tracked: log each off-campus download so the quota stays visible.

## Agent 1: Paper Downloader [Sonnet] — journal mode only

### Mission
Download the full paper and all supplementary materials. Save all assets.

### IMPORTANT: PDF-First Policy
- ALWAYS download the actual PDF file using curl and use PyMuPDF (fitz) for text/image extraction
- NEVER use WebFetch to read paper content — it converts HTML and loses figures/formatting
- WebFetch is ONLY acceptable for getting metadata from CrossRef/OpenAlex APIs (JSON endpoints)

### Step 1: Resolve DOI / Find Paper

If DOI given:
- Resolve via `https://doi.org/<DOI>` using web_fetch
- Get full metadata via CrossRef: `https://api.crossref.org/works/<DOI>`

If title given:
- Search via OpenAlex: `https://api.openalex.org/works?search=<title>&per_page=3`
- Confirm DOI with user if ambiguous

### Step 2: Attempt Full-Text Download

Download the PDF directly using curl/bash, NOT WebFetch.

**Tier 1: Unpaywall (check OA first)**
```bash
curl -s "https://api.unpaywall.org/v2/<DOI>?email=user@example.com"
```
Extract `best_oa_location.url_for_pdf`, then:
```bash
curl -L -o {work_dir}/assets/paper.pdf "<pdf_url>"
file {work_dir}/assets/paper.pdf  # Verify it's a PDF
```

**Tier 2: Publisher direct PDF**
- Wiley: `https://onlinelibrary.wiley.com/doi/pdfdirect/<DOI>?download=true`
- ACS: `https://pubs.acs.org/doi/pdf/<DOI>`
- Elsevier/Nature/Springer: check Unpaywall first

**Tier 3: PMC PDF**
```bash
curl -s "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/?ids=<DOI>&format=json"
curl -L -o paper.pdf "https://pmc.ncbi.nlm.nih.gov/articles/<PMCID>/pdf/"
```

**Tier 4: Korea University EZproxy (authenticated)**
```
proxy_url = f"https://oca.korea.ac.kr/link.n2s?url=https://doi.org/<DOI>"
```
Only if above tiers fail.

### Step 3: Extract Figures, Tables, Schemes, Graphical Abstract

If PDF downloaded locally:

**Primary: Extract embedded raster images from PDF**
```python
import fitz  # PyMuPDF

doc = fitz.open(pdf_path)
figures = []
for page_num in range(len(doc)):
    page = doc[page_num]
    images = page.get_images(full=True)
    for img_idx, img in enumerate(images):
        xref = img[0]
        info = doc.extract_image(xref)
        w, h = info["width"], info["height"]
        if w < 300 or h < 200:
            continue  # skip icons/logos
        fig_path = f"{work_dir}/assets/fig_p{page_num+1}_x{xref}.{info['ext']}"
        with open(fig_path, "wb") as f:
            f.write(info["image"])
        figures.append({"path": fig_path, "page": page_num+1, "size": (w, h), "xref": xref})
```

**Fallback for vector-only schemes (common in chemistry papers):**
If extract_image returns no usable figures (< 3 images > 500px), render pages at 300 DPI:
```python
for page_num in range(len(doc)):
    page = doc[page_num]
    mat = fitz.Matrix(300/72, 300/72)  # 300 DPI
    pix = page.get_pixmap(matrix=mat)
    pix.save(f"{work_dir}/assets/page_{page_num+1}_hires.png")
```
Then crop specific scheme regions using PIL. 300 DPI gives ~4x sharper images than 72 DPI.
IMPORTANT: When verifying cropped images, resize to <2000px before reading to avoid context size issues.

### Figure Quality Priority
1. **Best**: Extract embedded raster images from PDF (fitz extract_image) — original resolution
2. **Good**: Render pages at 300 DPI (fitz get_pixmap with matrix) → crop schemes
3. **Fallback**: Render at 72 DPI → crop (low quality, avoid)

NEVER use WebFetch to get page screenshots — they are HTML renders, not PDF content.
When cropping from rendered pages:
- Chemistry schemes are typically surrounded by text — crop ONLY the structural formula area
- Verify each crop by checking dimensions (scheme images should be > 500px wide)
- Do NOT read cropped images > 2000px with the Read tool (context size limit)

**Figure identification heuristic:**
- Images > 500px wide AND > 300px tall → likely a scheme/figure
- Images < 300px in both dimensions → likely logos, icons, journal watermarks → SKIP
- For vector schemes (common in chemistry papers): use page rendering + crop approach

Also extract figure captions (text matching "Fig.", "Figure", "Scheme", "Table"):
```python
for page_num in range(len(doc)):
    text = doc[page_num].get_text("text")
    # Extract caption blocks starting with Fig./Figure/Scheme/Table
    import re
    captions = re.findall(r'(Fig(?:ure)?\.?\s*\d+[^.]*\.)', text)
```

### Step 3b: Extract Full Text from PDF

Use PyMuPDF for text extraction (NOT WebFetch):
```python
full_text = ""
for page in doc:
    full_text += page.get_text("text") + "\n\n"
with open(f"{work_dir}/assets/paper_fulltext.txt", "w", encoding="utf-8") as f:
    f.write(full_text)
```

### Step 4: Download Supplementary Information

Check publisher page for SI links. Download:
- SI PDF(s)
- Dataset files (CSV, Excel)
- Video abstracts (note URL only, do not download binary)

Extract figures from SI PDF using same approach as main paper.

### Step 5: Output

Save to `{work_dir}/assets/`:
```
assets/
  paper_metadata.json   — title, authors, journal, year, doi, abstract
  paper_fulltext.txt    — full text (if available)
  fig_*.png/jpg         — extracted figures (main paper)
  si_fig_*.png/jpg      — SI figures
  tables/               — extracted table data if parseable
  captions.json         — figure label → caption text mapping
```

Return path: `{work_dir}/assets/`

---

