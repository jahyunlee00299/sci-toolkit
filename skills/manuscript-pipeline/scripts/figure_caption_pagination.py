#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Does every figure still share a page with its caption?

Page count cannot answer this. Measured case: a figure grew from 5.70 to 7.22 in
when its render was replaced, pushing its own 10-line caption to the next page —
while the document stayed 63 pages before and after. A page-count diff reported
"no overflow introduced" and the split shipped unnoticed until the figure/caption
pairs were measured directly.

So compare each figure's page number against its caption's, and always against
the UNEDITED original — a document usually has pre-existing splits, and telling
"mine" from "already there" is the whole point of passing --before.

Read-only: opens Word with ReadOnly=True and never saves. Some manuscripts ban
Word COM saves outright (equation corruption); this script is safe under that
rule because it only reads.

Not the same check as figure_caption_check.py's C7. C7 reads the OOXML for an
explicit page break between a caption and the body prose after it. This measures
where Word actually lays the figure and its caption — a split caused by a figure
growing taller leaves no trace in the XML at all, so only a repaginated render
can see it. Run both.

Usage:
    python figure_caption_pagination.py <docx> [--before <original.docx>] [--json]

Exit codes:
    0  no new splits (or none at all when --before is omitted)
    1  new splits introduced relative to --before
    2  could not measure (Word unavailable, file missing)
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

WD_ACTIVE_END_PAGE = 3
WD_STAT_PAGES = 2
CAPTION_PREFIXES = ("Fig.", "Figure", "Scheme", "Table", "Chart")


def measure(path: Path, app) -> dict:
    """Page number of every inline shape and of the caption that follows it."""
    doc = app.Documents.Open(str(path), ReadOnly=True, AddToRecentFiles=False)
    try:
        doc.Repaginate()
        pairs, splits = [], []
        for i in range(1, doc.InlineShapes.Count + 1):
            shape = doc.InlineShapes(i)
            fig_pg = shape.Range.Information(WD_ACTIVE_END_PAGE)
            # the caption is the next paragraph, but blank paragraphs intervene
            par, hops = shape.Range.Paragraphs(1).Next(), 0
            while par is not None and hops < 4:
                text = par.Range.Text.strip()
                if text.startswith(CAPTION_PREFIXES):
                    cap_pg = par.Range.Information(WD_ACTIVE_END_PAGE)
                    rec = {"shape": i, "fig_page": fig_pg, "caption_page": cap_pg,
                           "caption": text[:60]}
                    pairs.append(rec)
                    if cap_pg != fig_pg:
                        splits.append(rec)
                    break
                par, hops = par.Next(), hops + 1
        return {"file": path.name, "pages": doc.ComputeStatistics(WD_STAT_PAGES),
                "shapes": doc.InlineShapes.Count, "pairs": pairs, "splits": splits}
    finally:
        doc.Close(False)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("docx", type=Path)
    ap.add_argument("--before", type=Path,
                    help="the unedited original, to separate new splits from pre-existing ones")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    for p in filter(None, [args.docx, args.before]):
        if not p.exists():
            print(f"ERROR: not found: {p}", file=sys.stderr)
            return 2
    try:
        import win32com.client as win32
    except ImportError:
        print("ERROR: pywin32 required (Word COM). pip install pywin32", file=sys.stderr)
        return 2

    app = win32.gencache.EnsureDispatch("Word.Application")
    app.Visible = False
    try:
        after = measure(args.docx, app)
        before = measure(args.before, app) if args.before else None
    finally:
        app.Quit()

    prior = {s["shape"] for s in before["splits"]} if before else set()
    new = [s for s in after["splits"] if s["shape"] not in prior]

    if args.json:
        print(json.dumps({"after": after, "before": before, "new_splits": new},
                         ensure_ascii=False, indent=2))
    else:
        if before:
            print(f"BEFORE {before['file']}: {before['pages']} pages, "
                  f"{len(before['splits'])} split(s)")
        print(f"AFTER  {after['file']}: {after['pages']} pages, "
              f"{len(after['splits'])} split(s)")
        if before and before["pages"] == after["pages"] and new:
            print("  note: page count is unchanged and would have hidden this.")
        for s in new:
            print(f"  NEW SPLIT shape {s['shape']}: figure p{s['fig_page']} / "
                  f"caption p{s['caption_page']}  {s['caption']}")
        if not new:
            print("  no new figure/caption splits.")

    if new:
        print("\nFix by shrinking the figure's WIDTH (keep the aspect ratio and update\n"
              "both <wp:extent> and the sibling <a:xfrm><a:ext>). Bisect the scale and\n"
              "re-run this check. Never buy height by dropping lettering below 7 pt.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
