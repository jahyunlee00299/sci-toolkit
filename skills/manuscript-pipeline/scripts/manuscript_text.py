#!/usr/bin/env python
"""manuscript_text.py — Tracked-change-aware text extraction for manuscript docx.

THE PROBLEM THIS SOLVES (incident_manuscript_trackedchange_phantom_gaps_260705):
    python-docx `paragraph.text` silently DROPS <w:ins> content and renders
    <w:del> as gaps. Any QC / analysis / Workflow built on that text can fabricate
    phantom "empty headings" and "truncated sentences" that are really just
    PENDING tracked changes. A 113-agent Workflow (~6.5M tokens) was once wasted
    this way. Before extracting/QC-ing/feeding a manuscript docx to anything,
    resolve tracked changes FIRST.

WHAT THIS DOES:
    1. Pre-flight: count <w:ins>/<w:del> revisions directly in word/document.xml
       (plus header/footer parts), with author + date range. This is the SIGNAL:
       if ins==del==0 the docx is clean and python-docx text is trustworthy.
    2. Extract clean text via pandoc --track-changes:
         accept  -> final intent (all insertions kept, deletions dropped)  [default]
         all     -> shows every insertion/deletion inline (see pending changes)
         reject  -> pre-edit state (insertions dropped, deletions kept)
       pandoc reads the real OOXML revision markup, so nothing is silently lost.
    3. Emit a summary + the extracted text.

USAGE:
    python manuscript_text.py file.docx                     # accept mode, text to stdout
    python manuscript_text.py file.docx --mode all          # see pending changes inline
    python manuscript_text.py file.docx --count-only        # just the revision summary
    python manuscript_text.py file.docx --json              # machine-readable
    python manuscript_text.py file.docx -o out.md           # write text to a file

EXIT CODES:
    0  success, docx is CLEAN (no tracked changes)
    10 success, but docx HAS tracked changes (caller must NOT trust python-docx text)
    2  extraction/environment error

Note: the bash docx-guard blocks command lines containing a `.docx` literal unless
they invoke a whitelisted tool. This script IS such a tool (it is called by path,
the docx arrives as an argv value), so wrap manuscript work through it.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

if __name__ == "__main__" and hasattr(sys.stdout, "buffer"):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except (ValueError, io.UnsupportedOperation):
        pass

# OOXML namespace prefix used for revision elements.
_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

# Parts of the package that can carry body text + revisions.
_TEXT_PARTS = re.compile(
    r"^word/(document\d*\.xml|header\d*\.xml|footer\d*\.xml|footnotes\.xml|endnotes\.xml)$"
)

# Paired <w:ins ...>...</w:ins> / <w:del ...>...</w:del> revision blocks. We count a
# block only if it wraps ACTUAL text content — an empty insertion/deletion (no <w:t>
# text, or a self-closing tag) is NOT counted by Word's Revisions collection, so
# excluding it aligns this count with Word's canonical figure.
_INS_BLOCK = re.compile(r"<w:ins\b([^>]*)>(.*?)</w:ins>", re.DOTALL)
_DEL_BLOCK = re.compile(r"<w:del\b([^>]*)>(.*?)</w:del>", re.DOTALL)
_WT_TEXT = re.compile(r"<w:(?:t|delText)\b[^>]*>([^<]*)</w:(?:t|delText)>")
_AUTHOR = re.compile(r'w:author="([^"]*)"')
_DATE = re.compile(r'w:date="([^"]*)"')


def _block_has_text(inner: str) -> bool:
    return any(t.strip() for t in _WT_TEXT.findall(inner))


def _iter_revision_tags(xml: str):
    """Yield (kind, author, date) for each w:ins / w:del block that wraps real text
    (empty/self-closing revisions are skipped to match Word's Revisions.Count)."""
    for kind, pat in (("ins", _INS_BLOCK), ("del", _DEL_BLOCK)):
        for m in pat.finditer(xml):
            attrs, inner = m.group(1), m.group(2)
            if not _block_has_text(inner):
                continue
            author = _AUTHOR.search(attrs)
            date = _DATE.search(attrs)
            yield (
                kind,
                author.group(1) if author else "(unknown)",
                date.group(1) if date else None,
            )


def count_revisions(docx: Path) -> dict:
    """Directly inspect the OOXML for tracked-change revisions.

    Returns {ins, del, authors:sorted[str], date_min, date_max, parts_scanned}.
    Reads the zip members as raw XML — does NOT use python-docx (which would hide
    exactly the content we are trying to detect).
    """
    ins = 0
    dele = 0
    authors: set[str] = set()
    dates: list[str] = []
    parts_scanned: list[str] = []

    with zipfile.ZipFile(docx) as z:
        for name in z.namelist():
            if not _TEXT_PARTS.match(name):
                continue
            parts_scanned.append(name)
            xml = z.read(name).decode("utf-8", errors="replace")
            for kind, author, date in _iter_revision_tags(xml):
                if kind == "ins":
                    ins += 1
                else:
                    dele += 1
                authors.add(author)
                if date:
                    dates.append(date)

    dates.sort()
    return {
        "ins": ins,
        "del": dele,
        "total": ins + dele,
        "authors": sorted(authors),
        "date_min": dates[0] if dates else None,
        "date_max": dates[-1] if dates else None,
        "parts_scanned": parts_scanned,
    }


def extract_text(docx: Path, mode: str) -> str:
    """Extract manuscript text with pandoc, resolving tracked changes per mode.

    mode: accept | reject | all  (maps to pandoc --track-changes=accept|reject|all)
    """
    pandoc = shutil.which("pandoc")
    if not pandoc:
        raise RuntimeError(
            "pandoc not found on PATH. Install pandoc (conda install -c conda-forge pandoc) "
            "to extract tracked-change-resolved text."
        )
    cmd = [
        pandoc,
        str(docx.resolve()),
        f"--track-changes={mode}",
        "-t",
        "markdown-raw_html-native_divs-native_spans",
        "--wrap=none",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"pandoc failed (rc={proc.returncode}):\n{proc.stderr.strip()}")
    return proc.stdout


def summarize(docx: Path, rev: dict) -> str:
    lines = [
        f"{'=' * 68}",
        f"TRACKED-CHANGE PRE-FLIGHT: {docx.name}",
        f"{'=' * 68}",
    ]
    if rev["total"] == 0:
        lines.append("  [CLEAN] No tracked changes. python-docx text is trustworthy.")
    else:
        lines.append(
            f"  [HAS TRACKED CHANGES]  insertions={rev['ins']}  deletions={rev['del']}"
            f"  (total {rev['total']})"
        )
        lines.append("  -> DO NOT trust python-docx paragraph.text on this file.")
        lines.append("  -> Use this script's extracted text (mode=accept for final intent).")
        if rev["authors"]:
            lines.append(f"  authors : {', '.join(rev['authors'])}")
        if rev["date_min"]:
            span = rev["date_min"]
            if rev["date_max"] and rev["date_max"] != rev["date_min"]:
                span += f"  ..  {rev['date_max']}"
            lines.append(f"  dates   : {span}")
    lines.append(f"  parts   : {', '.join(rev['parts_scanned']) or '(none)'}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("docx", type=Path)
    ap.add_argument(
        "--mode",
        choices=["accept", "reject", "all"],
        default="accept",
        help="tracked-change resolution: accept(final intent, default) | reject(pre-edit) | all(inline)",
    )
    ap.add_argument("--count-only", action="store_true", help="only print the revision summary")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("-o", "--output", type=Path, help="write extracted text to a file instead of stdout")
    args = ap.parse_args()

    if not args.docx.exists():
        sys.exit(f"ERROR: file not found: {args.docx}")
    if args.docx.suffix.lower() != ".docx":
        sys.exit(f"ERROR: not a .docx file: {args.docx}")

    try:
        rev = count_revisions(args.docx)
    except zipfile.BadZipFile:
        sys.exit(f"ERROR: not a valid docx (zip) file: {args.docx}")

    text = None
    if not args.count_only:
        try:
            text = extract_text(args.docx, args.mode)
        except RuntimeError as e:
            if args.json:
                print(json.dumps({"revisions": rev, "error": str(e)}, indent=2, ensure_ascii=False))
            else:
                print(summarize(args.docx, rev), file=sys.stderr)
                print(f"\n[EXTRACTION ERROR] {e}", file=sys.stderr)
            sys.exit(2)

    if args.json:
        out = {"revisions": rev, "mode": args.mode}
        if text is not None:
            out["text"] = text
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        # summary always to stderr so stdout can be piped as pure text
        print(summarize(args.docx, rev), file=sys.stderr)
        if text is not None:
            if args.output:
                args.output.write_text(text, encoding="utf-8")
                print(f"\n[written] {args.output}  ({len(text)} chars)", file=sys.stderr)
            else:
                print(text)

    # exit 10 signals "has tracked changes" so callers can gate on it
    sys.exit(10 if rev["total"] > 0 else 0)


if __name__ == "__main__":
    main()
