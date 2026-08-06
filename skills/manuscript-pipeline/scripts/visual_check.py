#!/usr/bin/env python3
"""visual_check.py — Render ANY document/figure to per-page PNGs for direct visual inspection.

Documented in docx/SKILL.md:
    visual_check.py <file> <outdir>
        PDF export 후 페이지별 PNG 렌더 (Claude 직접 시각 확인용).

Why this exists
---------------
Structural validators (docx_preflight / word_validate) prove a file OPENS and is
well-formed, but they cannot see LAYOUT: figure placement, table overflow, caption
alignment, heading style, page breaks, orphaned lines, running headers, reference-list
formatting, or whether a figure actually looks right. For manuscript / figure / slide
work you must actually LOOK at the rendered pages. This tool turns a document OR a
figure into PNGs that Claude can Read and inspect.

Supported inputs (auto-detected by extension)
---------------------------------------------
- Word            .docx .doc            -> PDF -> PNG
- PowerPoint      .pptx .ppt            -> PDF -> PNG (one PNG per slide)
- Excel           .xlsx .xls .csv       -> PDF -> PNG
- PDF             .pdf                   -> PNG directly (skip export)
- Image / figure  .png .jpg .jpeg .tif .tiff .bmp .gif .webp  -> normalized PNG(s)
                    (multi-page TIFF -> one PNG per frame; others pass through/convert)
- SVG             .svg                   -> PNG (via cairosvg or soffice, if available)

Pipeline (most-faithful first, with fallbacks)
----------------------------------------------
1. <office doc> -> PDF
     a. Microsoft Office via COM (Word/PowerPoint/Excel) -- pixel-identical to the author's view.
     b. LibreOffice (scripts/office/soffice.py --convert-to pdf) -- headless fallback.
2. PDF -> per-page PNG
     a. PyMuPDF (fitz)      -- no external binary needed.
     b. pdftoppm (poppler)  -- fallback.
3. images pass through Pillow (format-normalize, flatten multi-frame TIFF).

Output
------
<outdir>/page-001.png, page-002.png, ...  plus a manifest.json with page count,
renderer/rasterizer used, and any pages selected. Prints the PNG paths so the caller
can Read them.

Usage
-----
    python visual_check.py MyPaper.docx out_dir
    python visual_check.py Figure3.png  out_dir            # figure — normalized copy
    python visual_check.py slides.pptx  out_dir            # one PNG per slide
    python visual_check.py report.pdf   out_dir --pages 1-3,7
    python visual_check.py MyPaper.docx out_dir --dpi 200  # sharper
    python visual_check.py MyPaper.docx out_dir --keep-pdf # keep intermediate PDF

Exit codes: 0 ok, 2 render failed, 3 bad args.
"""
from __future__ import annotations

# Windows 기본 콘솔은 cp949 라서 한글/기호 출력에서 죽는다. UTF-8로 맞춘다.
# reconfigure 를 쓴다: TextIOWrapper 로 감싸면 원본 스트림을 소유하게 되어,
# 이 모듈이 import 된 뒤 래퍼가 GC 될 때 호출자의 stdout 까지 닫는다(실측).
import sys as _sys
for _s in (_sys.stdout, _sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
import argparse
import json
import os
import sys
import shutil
import subprocess
import tempfile

# Extension -> input class. Kept explicit so an unknown extension errors loudly
# rather than being mis-rendered.
OFFICE_WORD = {".docx", ".doc"}
OFFICE_PPT = {".pptx", ".ppt"}
OFFICE_XLS = {".xlsx", ".xls", ".csv"}
OFFICE_EXTS = OFFICE_WORD | OFFICE_PPT | OFFICE_XLS
PDF_EXTS = {".pdf"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp"}
SVG_EXTS = {".svg"}


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def parse_pages(spec: str, total: int) -> list[int]:
    """'1-3,7,10-' -> sorted unique 0-based page indices within [0,total)."""
    if not spec:
        return list(range(total))
    out: set[int] = set()
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            a, _, b = chunk.partition("-")
            a = int(a) if a.strip() else 1
            b = int(b) if b.strip() else total
        else:
            a = b = int(chunk)
        for p in range(a, b + 1):
            if 1 <= p <= total:
                out.add(p - 1)
    return sorted(out)


# ----------------------------------------------------------------------------- docx -> pdf
def docx_to_pdf_word(src: str, pdf_out: str) -> bool:
    """Render via Microsoft Word COM. Most faithful. Returns True on success."""
    try:
        import win32com.client  # type: ignore
        import pythoncom  # type: ignore
    except Exception as e:  # noqa: BLE001
        _log(f"[word] win32com unavailable: {e}")
        return False

    wd_format_pdf = 17  # wdFormatPDF
    pythoncom.CoInitialize()
    word = None
    doc = None
    try:
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0  # wdAlertsNone
        # Open read-only, do not add to recent files, no repair prompts.
        doc = word.Documents.Open(
            os.path.abspath(src), ReadOnly=True, AddToRecentFiles=False,
            ConfirmConversions=False,
        )
        doc.SaveAs(os.path.abspath(pdf_out), FileFormat=wd_format_pdf)
        _log("[word] exported PDF via Microsoft Word COM")
        return os.path.exists(pdf_out) and os.path.getsize(pdf_out) > 0
    except Exception as e:  # noqa: BLE001
        _log(f"[word] COM export failed: {e}")
        return False
    finally:
        try:
            if doc is not None:
                doc.Close(SaveChanges=0)
        except Exception:
            pass
        try:
            if word is not None:
                word.Quit()
        except Exception:
            pass
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass


def pptx_to_pdf_powerpoint(src: str, pdf_out: str) -> bool:
    """Render via Microsoft PowerPoint COM (one slide per page)."""
    try:
        import win32com.client  # type: ignore
        import pythoncom  # type: ignore
    except Exception as e:  # noqa: BLE001
        _log(f"[ppt] win32com unavailable: {e}")
        return False
    ppt_pdf = 32  # ppSaveAsPDF
    pythoncom.CoInitialize()
    app = None
    pres = None
    try:
        app = win32com.client.DispatchEx("PowerPoint.Application")
        # PowerPoint refuses Visible=False in some builds; WithWindow=False on Open instead.
        pres = app.Presentations.Open(
            os.path.abspath(src), ReadOnly=True, Untitled=False, WithWindow=False)
        pres.SaveAs(os.path.abspath(pdf_out), ppt_pdf)
        _log("[ppt] exported PDF via Microsoft PowerPoint COM")
        return os.path.exists(pdf_out) and os.path.getsize(pdf_out) > 0
    except Exception as e:  # noqa: BLE001
        _log(f"[ppt] COM export failed: {e}")
        return False
    finally:
        try:
            if pres is not None:
                pres.Close()
        except Exception:
            pass
        try:
            if app is not None:
                app.Quit()
        except Exception:
            pass
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass


def xlsx_to_pdf_excel(src: str, pdf_out: str) -> bool:
    """Render via Microsoft Excel COM."""
    try:
        import win32com.client  # type: ignore
        import pythoncom  # type: ignore
    except Exception as e:  # noqa: BLE001
        _log(f"[xls] win32com unavailable: {e}")
        return False
    xl_pdf = 0  # xlTypePDF
    pythoncom.CoInitialize()
    app = None
    wb = None
    try:
        app = win32com.client.DispatchEx("Excel.Application")
        app.Visible = False
        app.DisplayAlerts = False
        wb = app.Workbooks.Open(os.path.abspath(src), ReadOnly=True)
        wb.ExportAsFixedFormat(xl_pdf, os.path.abspath(pdf_out))
        _log("[xls] exported PDF via Microsoft Excel COM")
        return os.path.exists(pdf_out) and os.path.getsize(pdf_out) > 0
    except Exception as e:  # noqa: BLE001
        _log(f"[xls] COM export failed: {e}")
        return False
    finally:
        try:
            if wb is not None:
                wb.Close(SaveChanges=False)
        except Exception:
            pass
        try:
            if app is not None:
                app.Quit()
        except Exception:
            pass
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass


def docx_to_pdf_soffice(src: str, pdf_out: str) -> bool:
    """Render via LibreOffice headless (scripts/office/soffice.py). Fallback."""
    here = os.path.dirname(os.path.abspath(__file__))
    soffice_helper = os.path.join(here, "office", "soffice.py")
    outdir = os.path.dirname(os.path.abspath(pdf_out)) or "."
    py = sys.executable
    cmd = None
    if os.path.exists(soffice_helper):
        cmd = [py, soffice_helper, "--headless", "--convert-to", "pdf",
               "--outdir", outdir, os.path.abspath(src)]
    else:
        soffice = shutil.which("soffice") or shutil.which("libreoffice")
        if soffice:
            cmd = [soffice, "--headless", "--convert-to", "pdf",
                   "--outdir", outdir, os.path.abspath(src)]
    if not cmd:
        _log("[soffice] no LibreOffice/soffice helper found")
        return False
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=300)
    except Exception as e:  # noqa: BLE001
        _log(f"[soffice] conversion failed: {e}")
        return False
    produced = os.path.join(
        outdir, os.path.splitext(os.path.basename(src))[0] + ".pdf")
    if produced != os.path.abspath(pdf_out) and os.path.exists(produced):
        shutil.move(produced, pdf_out)
    ok = os.path.exists(pdf_out) and os.path.getsize(pdf_out) > 0
    if ok:
        _log("[soffice] exported PDF via LibreOffice")
    return ok


# ----------------------------------------------------------------------------- pdf -> png
def pdf_to_png_fitz(pdf: str, outdir: str, dpi: int, pages_spec: str) -> list[str] | None:
    try:
        import fitz  # type: ignore
    except Exception as e:  # noqa: BLE001
        _log(f"[fitz] PyMuPDF unavailable: {e}")
        return None
    try:
        doc = fitz.open(pdf)
        total = doc.page_count
        idxs = parse_pages(pages_spec, total)
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        paths: list[str] = []
        for i in idxs:
            page = doc.load_page(i)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            out = os.path.join(outdir, f"page-{i + 1:03d}.png")
            pix.save(out)
            paths.append(out)
        doc.close()
        _log(f"[fitz] rasterized {len(paths)}/{total} page(s) at {dpi} dpi")
        return paths
    except Exception as e:  # noqa: BLE001
        _log(f"[fitz] rasterize failed: {e}")
        return None


def pdf_to_png_pdftoppm(pdf: str, outdir: str, dpi: int, pages_spec: str) -> list[str] | None:
    exe = shutil.which("pdftoppm")
    if not exe:
        _log("[pdftoppm] not found")
        return None
    # pdftoppm can't take an arbitrary page list, so render all then filter.
    prefix = os.path.join(outdir, "_ppm")
    try:
        subprocess.run([exe, "-png", "-r", str(dpi), pdf, prefix],
                       check=True, capture_output=True, timeout=300)
    except Exception as e:  # noqa: BLE001
        _log(f"[pdftoppm] failed: {e}")
        return None
    produced = sorted(
        f for f in os.listdir(outdir) if f.startswith("_ppm") and f.endswith(".png"))
    total = len(produced)
    keep = set(parse_pages(pages_spec, total))
    paths: list[str] = []
    for n, fname in enumerate(produced):
        if n in keep:
            dst = os.path.join(outdir, f"page-{n + 1:03d}.png")
            shutil.move(os.path.join(outdir, fname), dst)
            paths.append(dst)
        else:
            os.remove(os.path.join(outdir, fname))
    _log(f"[pdftoppm] rasterized {len(paths)}/{total} page(s) at {dpi} dpi")
    return paths


# ----------------------------------------------------------------------------- image / svg
def image_to_png(src: str, outdir: str, pages_spec: str) -> list[str] | None:
    """Normalize a figure/image to PNG(s). Multi-frame TIFF -> one PNG per frame."""
    try:
        from PIL import Image, ImageSequence  # type: ignore
    except Exception as e:  # noqa: BLE001
        _log(f"[image] Pillow unavailable: {e}")
        # last resort: if it's already a .png, just copy it through
        if src.lower().endswith(".png"):
            dst = os.path.join(outdir, "page-001.png")
            shutil.copyfile(src, dst)
            _log("[image] Pillow missing; copied PNG as-is")
            return [dst]
        return None
    try:
        im = Image.open(src)
        frames = list(ImageSequence.Iterator(im))
        total = len(frames)
        idxs = parse_pages(pages_spec, total)
        paths: list[str] = []
        for i in idxs:
            frame = frames[i].convert("RGB") if frames[i].mode not in ("RGB", "RGBA") else frames[i]
            out = os.path.join(outdir, f"page-{i + 1:03d}.png")
            frame.save(out, "PNG")
            paths.append(out)
        _log(f"[image] normalized {len(paths)}/{total} frame(s) to PNG")
        return paths
    except Exception as e:  # noqa: BLE001
        _log(f"[image] convert failed: {e}")
        return None


def svg_to_png(src: str, outdir: str, dpi: int) -> list[str] | None:
    out = os.path.join(outdir, "page-001.png")
    # 1) cairosvg
    try:
        import cairosvg  # type: ignore
        cairosvg.svg2png(url=src, write_to=out, dpi=dpi)
        if os.path.exists(out) and os.path.getsize(out) > 0:
            _log("[svg] rendered via cairosvg")
            return [out]
    except Exception as e:  # noqa: BLE001
        _log(f"[svg] cairosvg unavailable/failed: {e}")
    # 2) fall back to soffice -> pdf -> png (handled by caller via office path)
    return None


# ----------------------------------------------------------------------------- main
def classify(src: str) -> str:
    ext = os.path.splitext(src)[1].lower()
    if ext in OFFICE_EXTS:
        return "office"
    if ext in PDF_EXTS:
        return "pdf"
    if ext in IMAGE_EXTS:
        return "image"
    if ext in SVG_EXTS:
        return "svg"
    return "unknown"


def office_to_pdf(src: str, pdf_path: str) -> str | None:
    """Route an office file to the right COM exporter, then soffice fallback."""
    ext = os.path.splitext(src)[1].lower()
    if ext in OFFICE_WORD and docx_to_pdf_word(src, pdf_path):
        return "word-com"
    if ext in OFFICE_PPT and pptx_to_pdf_powerpoint(src, pdf_path):
        return "powerpoint-com"
    if ext in OFFICE_XLS and ext != ".csv" and xlsx_to_pdf_excel(src, pdf_path):
        return "excel-com"
    # universal headless fallback (also handles .csv)
    if docx_to_pdf_soffice(src, pdf_path):
        return "libreoffice"
    return None


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Render any document/figure to per-page PNGs for visual inspection.")
    ap.add_argument("file", help="input: .docx/.doc/.pptx/.xlsx/.pdf/.png/.jpg/.tif/.svg …")
    ap.add_argument("outdir", help="output directory for PNGs")
    ap.add_argument("--pages", default="", help="subset e.g. '1-3,7' (default: all)")
    ap.add_argument("--dpi", type=int, default=150, help="raster DPI (default 150)")
    ap.add_argument("--keep-pdf", action="store_true", help="keep intermediate PDF")
    ap.add_argument("--pdf-only", action="store_true", help="stop after PDF export")
    args = ap.parse_args()

    src = args.file
    if not os.path.exists(src):
        _log(f"error: input not found: {src}")
        return 3
    kind = classify(src)
    if kind == "unknown":
        _log(f"error: unsupported extension: {os.path.splitext(src)[1]} "
             f"(supported: office/pdf/image/svg)")
        return 3
    os.makedirs(args.outdir, exist_ok=True)

    # --- image: normalize straight to PNG(s), no PDF stage ---
    if kind == "image":
        pages = image_to_png(src, args.outdir, args.pages)
        if pages is None:
            _log("FATAL: could not process image (need Pillow).")
            return 2
        _finish_manifest(src, pages, "pillow", "pillow", args.dpi, args.outdir)
        return 0

    # --- svg: try cairosvg; else treat as office (soffice) below ---
    if kind == "svg":
        pages = svg_to_png(src, args.outdir, args.dpi)
        if pages is not None:
            _finish_manifest(src, pages, "cairosvg", "cairosvg", args.dpi, args.outdir)
            return 0
        _log("[svg] falling back to LibreOffice conversion")

    # --- pdf: skip export, rasterize directly ---
    if kind == "pdf":
        pdf_path = os.path.abspath(src)
        renderer = "n/a (already pdf)"
        keep_pdf_forced = True  # never delete the user's own pdf
    else:
        # office (or svg-fallback) -> pdf
        pdf_path = os.path.join(
            args.outdir, os.path.splitext(os.path.basename(src))[0] + ".pdf")
        renderer = office_to_pdf(src, pdf_path)
        keep_pdf_forced = False
        if renderer is None:
            _log("FATAL: could not export PDF (Office COM and LibreOffice both failed).")
            return 2
        if args.pdf_only:
            print(pdf_path)
            return 0

    # --- pdf -> png ---
    rasterizer = None
    pages = pdf_to_png_fitz(pdf_path, args.outdir, args.dpi, args.pages)
    if pages is not None:
        rasterizer = "pymupdf"
    else:
        pages = pdf_to_png_pdftoppm(pdf_path, args.outdir, args.dpi, args.pages)
        if pages is not None:
            rasterizer = "pdftoppm"
    if pages is None:
        _log("FATAL: could not rasterize PDF (need PyMuPDF or pdftoppm).")
        return 2

    if not args.keep_pdf and not keep_pdf_forced:
        try:
            os.remove(pdf_path)
        except Exception:
            pass

    _finish_manifest(src, pages, renderer, rasterizer, args.dpi, args.outdir)
    return 0


def _finish_manifest(src, pages, renderer, rasterizer, dpi, outdir):
    manifest = {
        "source": os.path.abspath(src),
        "renderer": renderer,
        "rasterizer": rasterizer,
        "dpi": dpi,
        "page_count": len(pages),
        "pages": [os.path.abspath(p) for p in pages],
    }
    with open(os.path.join(outdir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"Rendered {len(pages)} page(s) [{renderer} -> {rasterizer}, {dpi} dpi]:")
    for p in pages:
        print(os.path.abspath(p))


if __name__ == "__main__":
    sys.exit(main())
