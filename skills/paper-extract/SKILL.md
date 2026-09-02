---
name: paper-extract
description: >-
  Extract tables (xlsx), figures (png), and full text (md) from research paper PDFs and Word
  documents (docx) for patent preparation, literature review, and manuscript writing. Use when
  the user asks to extract tables from a paper, extract figures from a PDF, pull images from a
  PDF or docx, or collect paper assets. 한국어 트리거 — 논문에서 테이블 추출, 논문 그래프 가져와,
  선행연구 테이블, PDF에서 이미지 추출, Word에서 테이블 추출, docx에서 그래프 가져와, 원고에서 피겨 추출.
---

# Paper Extract Skill

Extract tables, figures, and text from research paper PDFs and Word documents (docx).

## When to Use

- User wants to extract tables or figures from a research paper PDF or Word document
- Preparing patent applications and need prior-art data
- Literature review requiring data from published papers
- Importing graphs/charts from papers into manuscripts or presentations
- Extracting assets from Word manuscripts (e.g., your own manuscript .docx files)

## Script Location

`scripts/extract_paper_assets.py` (relative to skill root)

## Usage

### Basic (output next to PDF)
```bash
python3 scripts/extract_paper_assets.py "<pdf_path>"
```

### Custom output directory
```bash
python3 scripts/extract_paper_assets.py "<pdf_path>" --output-dir "<output_dir>"
```

## Output Structure

```
<pdf_stem>_extracted/
├── table_p{page}_{idx}.xlsx    # Individual tables (one per table)
├── all_tables.xlsx             # All tables combined (separate sheets)
├── fig_p{page}_{idx}.png      # Embedded images (>50x50px)
├── fig_p{page}_fullpage.png   # Full page renders (pages without embedded images)
├── full_text.md               # Complete text in Markdown (via markitdown)
└── extraction_report.json     # Metadata and extraction summary
```

## Extraction Methods

| Asset | Library | Details |
|-------|---------|---------|
| Tables | pdfplumber | Structured table extraction → Excel with openpyxl |
| Figures | PyMuPDF (fitz) | Embedded images → PNG; fallback: 300 DPI page render |
| Text | markitdown | Full PDF → Markdown with table structure preserved |

## Workflow

1. Run the extraction script on the target PDF
2. Check `extraction_report.json` for summary (table count, figure count, text length)
3. Read individual files as needed:
   - Tables: open xlsx files or read all_tables.xlsx
   - Figures: view PNG files with Read tool
   - Text: read full_text.md for searchable content
4. For scanned PDFs with poor extraction, consider OCR fallback (requires `tesseract-ocr` system package)

## Dependencies

Already installed: `pdfplumber`, `PyMuPDF (fitz)`, `markitdown`, `Pillow`, `openpyxl`, `pypdfium2`, `pdf2image`

Optional (requires sudo): `tesseract-ocr`, `poppler-utils`

## Limitations

- Scanned PDFs: table extraction quality depends on PDF text layer; pure image PDFs need OCR
- Complex multi-span tables may lose structure
- Figures embedded as vector graphics may not extract as individual images (full page render used instead)
- Very large PDFs (>100 pages) may take significant time
