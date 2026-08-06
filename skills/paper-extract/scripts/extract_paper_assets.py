#!/usr/bin/env python3
"""논문 PDF / Word(.docx) 에서 표·그림·본문을 한 번에 추출한다.

산출물은 입력 파일 옆(또는 --output-dir)에 `<파일명>_extracted/` 폴더로 떨어진다:

    <stem>_extracted/
    ├── table_p{page}_{idx}.xlsx     개별 표
    ├── all_tables.xlsx              전체 표(시트 분리)
    ├── fig_p{page}_{idx}.png        본문에 박혀 있던 이미지
    ├── fig_p{page}_fullpage.png     이미지가 없는 페이지는 통째로 렌더
    ├── full_text.md                 본문 전체(마크다운)
    └── extraction_report.json       추출 요약(개수·경고·건너뛴 것)

사용:
    python scripts/extract_paper_assets.py "<paper.pdf>"
    python scripts/extract_paper_assets.py "<manuscript.docx>" --output-dir "<out>"
    python scripts/extract_paper_assets.py "<paper.pdf>" --no-fullpage --dpi 200

설계 원칙:
- **없는 것은 없다고 보고한다.** 라이브러리가 없거나 페이지가 비면 조용히 넘어가지 않고
  `extraction_report.json` 의 `warnings` / `skipped` 에 남긴다. 추출 0건인데 성공처럼
  보이는 것이 이 도구에서 가장 위험한 실패 모드다.
- 선택 의존성은 **하나라도 있으면 그만큼 동작**한다(표만, 그림만이라도).
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import traceback
from pathlib import Path

# Windows 기본 콘솔은 cp949 라서 한글/기호 출력에서 죽는다. UTF-8로 맞춘다.
# TextIOWrapper 대신 reconfigure — 래퍼는 원본 스트림을 소유해서,
# import 후 GC 되면 호출자의 stdout 까지 닫아버린다(실측).
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

MIN_IMAGE_PX = 50          # 이보다 작은 이미지는 아이콘/장식으로 보고 버린다
DEFAULT_DPI = 300


class Report:
    """추출 결과를 모으는 그릇. 실패도 성공만큼 성실히 기록한다."""

    def __init__(self, source: Path, outdir: Path):
        self.source = str(source)
        self.outdir = str(outdir)
        self.tables: list[str] = []
        self.figures: list[str] = []
        self.text_file: str | None = None
        self.text_chars = 0
        self.warnings: list[str] = []
        self.skipped: list[str] = []

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)
        print(f"  [경고] {msg}")

    def skip(self, msg: str) -> None:
        self.skipped.append(msg)
        print(f"  [건너뜀] {msg}")

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "output_dir": self.outdir,
            "table_count": len(self.tables),
            "figure_count": len(self.figures),
            "tables": self.tables,
            "figures": self.figures,
            "text_file": self.text_file,
            "text_chars": self.text_chars,
            "warnings": self.warnings,
            "skipped": self.skipped,
        }


# ----------------------------------------------------------------------
# PDF
# ----------------------------------------------------------------------

def extract_pdf_tables(pdf: Path, outdir: Path, rep: Report) -> None:
    try:
        import pdfplumber
    except ImportError:
        rep.skip("표 추출: pdfplumber 가 설치되어 있지 않다 (pip install pdfplumber)")
        return
    try:
        from openpyxl import Workbook
    except ImportError:
        rep.skip("표 추출: openpyxl 이 설치되어 있지 않다 (pip install openpyxl)")
        return

    combined = Workbook()
    combined.remove(combined.active)
    found = 0

    with pdfplumber.open(str(pdf)) as doc:
        for pno, page in enumerate(doc.pages, 1):
            try:
                tables = page.extract_tables()
            except Exception as exc:                      # noqa: BLE001
                rep.warn(f"p{pno} 표 추출 실패: {exc}")
                continue
            for idx, table in enumerate(tables, 1):
                rows = [r for r in table if r and any(c not in (None, "") for c in r)]
                if not rows:
                    continue
                found += 1
                name = f"table_p{pno}_{idx}.xlsx"
                wb = Workbook()
                ws = wb.active
                ws.title = f"p{pno}_{idx}"[:31]
                for row in rows:
                    ws.append(["" if c is None else str(c) for c in row])
                wb.save(outdir / name)
                rep.tables.append(name)

                sheet = combined.create_sheet(f"p{pno}_{idx}"[:31])
                for row in rows:
                    sheet.append(["" if c is None else str(c) for c in row])

    if found:
        combined.save(outdir / "all_tables.xlsx")
        print(f"  표 {found}개 추출")
    else:
        rep.warn("표를 하나도 찾지 못했다 — 스캔 PDF이거나 표가 이미지일 수 있다")


def extract_pdf_figures(pdf: Path, outdir: Path, rep: Report,
                        dpi: int, fullpage: bool) -> None:
    try:
        import fitz  # PyMuPDF
    except ImportError:
        rep.skip("그림 추출: PyMuPDF(fitz) 가 설치되어 있지 않다 (pip install pymupdf)")
        return

    doc = fitz.open(str(pdf))
    embedded_total = 0
    try:
        for pno in range(len(doc)):
            page = doc[pno]
            page_hits = 0
            for idx, info in enumerate(page.get_images(full=True), 1):
                xref = info[0]
                try:
                    pix = fitz.Pixmap(doc, xref)
                except Exception as exc:                  # noqa: BLE001
                    rep.warn(f"p{pno+1} 이미지 {idx} 읽기 실패: {exc}")
                    continue
                if pix.width < MIN_IMAGE_PX or pix.height < MIN_IMAGE_PX:
                    pix = None
                    continue
                if pix.n - pix.alpha >= 4:                # CMYK -> RGB
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                name = f"fig_p{pno+1}_{idx}.png"
                pix.save(str(outdir / name))
                rep.figures.append(name)
                page_hits += 1
                embedded_total += 1
                pix = None

            # 그림이 벡터로만 그려진 페이지는 통째로 렌더해야 건질 수 있다.
            if fullpage and page_hits == 0 and page.get_drawings():
                name = f"fig_p{pno+1}_fullpage.png"
                page.get_pixmap(dpi=dpi).save(str(outdir / name))
                rep.figures.append(name)
    finally:
        doc.close()

    if rep.figures:
        print(f"  그림 {len(rep.figures)}개 추출 (본문 삽입 {embedded_total}개)")
    else:
        rep.warn("그림을 하나도 찾지 못했다")


def extract_pdf_text(pdf: Path, outdir: Path, rep: Report) -> None:
    text = None
    try:
        from markitdown import MarkItDown
        text = MarkItDown().convert(str(pdf)).text_content
    except ImportError:
        rep.warn("markitdown 이 없어 pdfplumber 로 본문을 뽑는다 (표 구조는 단순해진다)")
    except Exception as exc:                              # noqa: BLE001
        rep.warn(f"markitdown 변환 실패({exc}) — pdfplumber 로 대체한다")

    if text is None:
        try:
            import pdfplumber
            with pdfplumber.open(str(pdf)) as doc:
                text = "\n\n".join((p.extract_text() or "") for p in doc.pages)
        except ImportError:
            rep.skip("본문 추출: markitdown / pdfplumber 둘 다 없다")
            return

    _write_text(text, outdir, rep)


# ----------------------------------------------------------------------
# DOCX
# ----------------------------------------------------------------------

def extract_docx(src: Path, outdir: Path, rep: Report) -> None:
    try:
        import docx  # python-docx
    except ImportError:
        rep.skip("docx 처리: python-docx 가 설치되어 있지 않다 (pip install python-docx)")
        return

    document = docx.Document(str(src))

    # --- 표 ---
    try:
        from openpyxl import Workbook
    except ImportError:
        rep.skip("표 추출: openpyxl 이 없다")
    else:
        combined = Workbook()
        combined.remove(combined.active)
        for idx, table in enumerate(document.tables, 1):
            rows = [[c.text for c in r.cells] for r in table.rows]
            rows = [r for r in rows if any(v.strip() for v in r)]
            if not rows:
                continue
            name = f"table_p0_{idx}.xlsx"
            wb = Workbook()
            ws = wb.active
            ws.title = f"table{idx}"[:31]
            for row in rows:
                ws.append(row)
            wb.save(outdir / name)
            rep.tables.append(name)
            sheet = combined.create_sheet(f"table{idx}"[:31])
            for row in rows:
                sheet.append(row)
        if rep.tables:
            combined.save(outdir / "all_tables.xlsx")
            print(f"  표 {len(rep.tables)}개 추출")
        else:
            rep.warn("docx 에서 표를 찾지 못했다")

    # --- 그림 (워드 패키지에 박힌 이미지 파트를 그대로 꺼낸다) ---
    count = 0
    for rel in document.part.rels.values():
        if "image" not in rel.reltype:
            continue
        try:
            blob = rel.target_part.blob
            ext = Path(rel.target_part.partname).suffix or ".png"
        except Exception as exc:                          # noqa: BLE001
            rep.warn(f"이미지 파트 읽기 실패: {exc}")
            continue
        count += 1
        name = f"fig_p0_{count}{ext}"
        (outdir / name).write_bytes(blob)
        rep.figures.append(name)
    if count:
        print(f"  그림 {count}개 추출")
    else:
        rep.warn("docx 에서 그림을 찾지 못했다")

    # --- 본문 ---
    text = None
    try:
        from markitdown import MarkItDown
        text = MarkItDown().convert(str(src)).text_content
    except Exception:                                     # noqa: BLE001
        text = "\n\n".join(p.text for p in document.paragraphs if p.text.strip())
        rep.warn("markitdown 없이 python-docx 로 본문을 뽑았다 — "
                 "변경내용 추적(tracked changes)이 있으면 삽입/삭제분이 누락될 수 있다")
    _write_text(text, outdir, rep)


# ----------------------------------------------------------------------

def _write_text(text: str | None, outdir: Path, rep: Report) -> None:
    if not text or not text.strip():
        rep.warn("본문이 비어 있다 — 스캔본이면 OCR 이 필요하다")
        return
    (outdir / "full_text.md").write_text(text, encoding="utf-8")
    rep.text_file = "full_text.md"
    rep.text_chars = len(text)
    print(f"  본문 {len(text):,}자 추출")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="논문 PDF/docx 에서 표·그림·본문을 추출한다")
    ap.add_argument("source", help="입력 파일 (.pdf 또는 .docx)")
    ap.add_argument("--output-dir", help="출력 폴더 (기본: 입력 파일 옆)")
    ap.add_argument("--dpi", type=int, default=DEFAULT_DPI,
                    help=f"전체 페이지 렌더 해상도 (기본 {DEFAULT_DPI})")
    ap.add_argument("--no-fullpage", action="store_true",
                    help="이미지 없는 페이지의 통째 렌더를 건너뛴다")
    args = ap.parse_args()

    src = Path(args.source).expanduser().resolve()
    if not src.is_file():
        print(f"오류: 파일이 없다 — {src}", file=sys.stderr)
        return 2

    suffix = src.suffix.lower()
    if suffix not in (".pdf", ".docx"):
        print(f"오류: 지원하지 않는 형식 '{suffix}' (.pdf 또는 .docx 만 가능)",
              file=sys.stderr)
        return 2

    outdir = (Path(args.output_dir).expanduser().resolve() if args.output_dir
              else src.parent / f"{src.stem}_extracted")
    outdir.mkdir(parents=True, exist_ok=True)

    print(f"입력: {src}")
    print(f"출력: {outdir}")

    rep = Report(src, outdir)
    try:
        if suffix == ".pdf":
            extract_pdf_tables(src, outdir, rep)
            extract_pdf_figures(src, outdir, rep, args.dpi, not args.no_fullpage)
            extract_pdf_text(src, outdir, rep)
        else:
            extract_docx(src, outdir, rep)
    except Exception:                                     # noqa: BLE001
        rep.warn("예기치 못한 오류:\n" + traceback.format_exc())

    (outdir / "extraction_report.json").write_text(
        json.dumps(rep.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    total = len(rep.tables) + len(rep.figures) + (1 if rep.text_file else 0)
    print(f"\n요약: 표 {len(rep.tables)} / 그림 {len(rep.figures)} / "
          f"본문 {'있음' if rep.text_file else '없음'}")
    if rep.skipped:
        print(f"건너뛴 단계 {len(rep.skipped)}개 — extraction_report.json 의 'skipped' 확인")
    if total == 0:
        print("아무것도 추출하지 못했다. extraction_report.json 의 warnings/skipped 를 먼저 읽어라.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
