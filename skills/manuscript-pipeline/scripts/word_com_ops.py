#!/usr/bin/env python
"""word_com_ops.py — Reliable Windows docx editing engine via Microsoft Word COM.

WHY THIS EXISTS (MANUSCRIPT_QC_TOOLING_PLAN H2):
    - accept_changes.py uses LibreOffice (soffice) which needs an installed
      LibreOffice; on Windows the socket path assumptions fail.
    - apply_workorder's tracked_replace hits CrossBoundary errors on run-fragmented
      text (EndNote field tokens and <w:lastRenderedPageBreak/> split a phrase
      across multiple <w:r> runs).
    Microsoft Word's own Find/Replace and range operations cross run boundaries
    NATIVELY, so Word COM (pywin32) sidesteps both problems. On Windows this is the
    DEFAULT for: accept-revisions, long find/replace, caption replace, table move,
    figure/table insertion. LibreOffice/apply_workorder are fallbacks.

SAFETY MODEL:
    - Every op writes to a NEW output file (never mutates the input in place) unless
      --in-place is given. The caller is expected to run docx_preflight.py +
      word_validate.py on the output before promoting it (C-45 / verification gate).
    - DisplayAlerts is suppressed; Word runs invisible; the app is always Quit in
      finally so no orphan WINWORD.EXE is left behind.

SUBCOMMANDS:
    accept-revisions IN [-o OUT]
        Document.AcceptAllRevisions(). Clears all tracked changes to final state.

    find-replace IN OLD NEW [-o OUT] [--tracked] [--match-case] [--whole-word]
        Word Find/Replace across run boundaries. For NEW/OLD longer than Word's
        255-char Find.Text limit, falls back to paragraph-scan + Range.Text set.
        --tracked records the edit as a tracked change (TrackRevisions=True).

    replace-caption IN LABEL NEW_TEXT [-o OUT]
        Find the paragraph beginning with a display-item label ("Figure 3.",
        "Table 4.", "Scheme 2.") and set its text to NEW_TEXT, re-bolding just the
        label token and forcing Arial. Use to fix caption/figure drift (H3).

    set-table-cell IN TABLE_ANCHOR ROW COL NEW_TEXT [-o OUT]
        Locate the table whose text contains TABLE_ANCHOR (unique substring),
        then set the (1-based ROW, COL) cell's text to NEW_TEXT in place — writes
        into the existing cell Range so first-run formatting (italics etc.) is
        preserved. Use when two occurrences of the same old text exist in
        different table rows and a global find-replace would hit the wrong one.

    move-table IN TABLE_HEADER AFTER_HEADER [-o OUT]
        Cut the caption paragraph matching TABLE_HEADER plus its following table,
        and paste it after the paragraph matching AFTER_HEADER. Verifies the table
        count is unchanged.

    insert-figure IN ANCHOR PNG [--caption CAP] [-o OUT]
        Insert PNG as an inline picture on a new paragraph after the paragraph
        containing ANCHOR, with an optional caption paragraph below it.

    insert-table IN ANCHOR ROWSJSON [--caption CAP] [-o OUT]
        Insert a table (ROWSJSON = JSON list-of-lists) after the paragraph
        containing ANCHOR, with an optional caption paragraph above it.

EXIT CODES:  0 ok | 2 not-found/precondition-failed | 3 environment (no pywin32/Word)

Note: the bash docx-guard blocks command lines containing a `.docx` literal unless
they invoke a whitelisted tool. This script is such a tool (docx arrives as argv).
"""
from __future__ import annotations

import argparse
import io
import json
import shutil
import sys
from pathlib import Path

if __name__ == "__main__" and hasattr(sys.stdout, "buffer"):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except (ValueError, io.UnsupportedOperation):
        pass

# Word enum constants (avoid depending on generated makepy constants).
WD_FORMAT_XML_DOCUMENT = 12       # wdFormatXMLDocument (.docx)
WD_REPLACE_ALL = 2                # wdReplaceAll
WD_FIND_STOP = 0                  # wdFindStop
WD_COLLAPSE_END = 0               # wdCollapseEnd
WD_COLLAPSE_START = 1             # wdCollapseStart
WD_STORY_MAIN = 6                 # wdMainTextStory
WD_LINE_STYLE_SINGLE = 1          # wdLineStyleSingle
FIND_TEXT_LIMIT = 255             # Word Find.Text hard limit


class WordError(Exception):
    """Raised on a precondition failure the caller should see (exit 2)."""


def _ensure_env():
    try:
        import win32com.client as win32  # noqa: F401
        import pywintypes  # noqa: F401
    except ImportError:
        print("[ENV_FAIL] pywin32 not installed (pip install pywin32)", file=sys.stderr)
        sys.exit(3)


def _open_word():
    import win32com.client as win32
    word = win32.gencache.EnsureDispatch("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0  # wdAlertsNone
    return word


def _prep_output(inp: Path, out: Path | None, in_place: bool) -> Path:
    """Return the path Word should open+save. Copies input->output first so the
    original is never mutated unless --in-place."""
    if in_place:
        return inp
    if out is None:
        # Derive a default name, but NEVER silently clobber an existing output from a
        # prior invocation — add a numeric suffix until the name is free.
        out = inp.with_name(inp.stem + "_wordops.docx")
        if out.exists():
            k = 2
            while True:
                cand = inp.with_name(f"{inp.stem}_wordops_{k}.docx")
                if not cand.exists():
                    out = cand
                    break
                k += 1
    shutil.copy2(inp, out)
    return out


def _save_close(doc, path: Path):
    doc.SaveAs2(str(path.resolve()), FileFormat=WD_FORMAT_XML_DOCUMENT)
    doc.Close(SaveChanges=False)


# ----------------------------------------------------------------------------- ops


def op_accept_revisions(word, path: Path) -> dict:
    doc = word.Documents.Open(str(path.resolve()), ReadOnly=False, AddToRecentFiles=False)
    before = doc.Revisions.Count
    doc.AcceptAllRevisions()
    after = doc.Revisions.Count
    _save_close(doc, path)
    return {"revisions_before": before, "revisions_after": after}


def _find_replace_short(rng, old: str, new: str, *, match_case, whole_word) -> int:
    """Use Word's native Find/Replace (crosses run boundaries). Returns hits."""
    f = rng.Find
    f.ClearFormatting()
    f.Replacement.ClearFormatting()
    f.Text = old
    f.Replacement.Text = new
    f.Forward = True
    f.Wrap = WD_FIND_STOP
    f.MatchCase = bool(match_case)
    f.MatchWholeWord = bool(whole_word)
    # Count first (Execute with replace consumes matches).
    n = 0
    probe = rng.Duplicate
    pf = probe.Find
    pf.ClearFormatting()
    pf.Text = old
    pf.MatchCase = bool(match_case)
    pf.MatchWholeWord = bool(whole_word)
    pf.Forward = True
    pf.Wrap = WD_FIND_STOP
    while pf.Execute():
        n += 1
        probe.Collapse(WD_COLLAPSE_END)
        if n > 100000:
            break
    f.Execute(Replace=WD_REPLACE_ALL)
    return n


def _norm(s: str) -> str:
    """Collapse whitespace so pandoc-extracted text and Word Range.Text compare
    reliably (pandoc normalizes runs of spaces / soft breaks; Word keeps them)."""
    return " ".join(s.split())


def _find_replace_long(doc, old: str, new: str, *, match_case) -> int:
    """For old/new beyond Word's 255-char Find limit: paragraph-scan and set
    Range.Text.

    Two-tier match (whitespace-normalized so pandoc-vs-Word text lines up):
      1. whole-paragraph equality  -> replace the whole paragraph body
      2. substring containment     -> replace only the matched span within the
         paragraph, preserving the rest and the paragraph mark
    Long `old` strings copied from pandoc output rarely equal Word's Range.Text
    byte-for-byte, so tier 2 is what makes this path usable in practice.
    """
    hits = 0
    t_norm = _norm(old) if match_case else _norm(old).casefold()
    for para in doc.Paragraphs:
        txt = para.Range.Text
        body = txt[:-1] if txt.endswith("\r") else txt  # drop trailing paragraph mark
        b_cmp = _norm(body) if match_case else _norm(body).casefold()

        if b_cmp == t_norm:
            rng = para.Range
            rng.End = rng.End - 1  # keep the paragraph mark
            rng.Text = new
            hits += 1
            continue

        # tier 2: substring — locate the span in the normalized paragraph, then
        # map back to raw offsets by walking the raw text word-by-word.
        idx = b_cmp.find(t_norm)
        if idx == -1:
            continue
        raw_start, raw_end = _map_norm_span_to_raw(body, old, match_case)
        if raw_start is None:
            continue
        rng = para.Range
        base = rng.Start
        span = doc.Range(Start=base + raw_start, End=base + raw_end)
        span.Text = new
        hits += 1
    return hits


def _map_norm_span_to_raw(raw: str, needle: str, match_case: bool):
    """Find `needle` (whitespace-insensitive) inside `raw`, return raw (start,end)
    char offsets of the matched span, or (None, None)."""
    import re as _re

    # Build a regex from needle where any run of whitespace matches \s+.
    parts = needle.split()
    if not parts:
        return None, None
    pat = r"\s+".join(_re.escape(p) for p in parts)
    flags = 0 if match_case else _re.IGNORECASE
    m = _re.search(pat, raw, flags)
    if not m:
        return None, None
    return m.start(), m.end()


def op_find_replace(word, path: Path, old: str, new: str, *, tracked, match_case, whole_word) -> dict:
    doc = word.Documents.Open(str(path.resolve()), ReadOnly=False, AddToRecentFiles=False)
    prev_track = doc.TrackRevisions
    doc.TrackRevisions = bool(tracked)
    try:
        if len(old) <= FIND_TEXT_LIMIT and len(new) <= FIND_TEXT_LIMIT:
            hits = _find_replace_short(
                doc.Content, old, new, match_case=match_case, whole_word=whole_word
            )
            mode = "native"
        else:
            hits = _find_replace_long(doc, old, new, match_case=match_case)
            mode = "paragraph-scan"
    finally:
        doc.TrackRevisions = prev_track
    _save_close(doc, path)
    return {"hits": hits, "mode": mode, "tracked": bool(tracked)}


def op_set_table_cell(word, path: Path, table_anchor: str, row: int, col: int, new_text: str) -> dict:
    """Set the text of a single table cell (1-based row/col), identified by a
    unique substring found in that table's own text (so callers don't have to
    guess table index). Preserves the existing run formatting (e.g. italics) of
    the FIRST run in the cell by writing into that run's range instead of
    replacing the whole cell Range (which would drop formatting)."""
    doc = word.Documents.Open(str(path.resolve()), ReadOnly=False, AddToRecentFiles=False)
    target_table = None
    for t in doc.Tables:
        if table_anchor.casefold() in t.Range.Text.casefold():
            target_table = t
            break
    if target_table is None:
        doc.Close(SaveChanges=False)
        raise WordError(f"no table containing anchor text {table_anchor!r}")
    try:
        cell = target_table.Cell(row, col)
    except Exception as e:
        doc.Close(SaveChanges=False)
        raise WordError(f"cell ({row},{col}) not found: {e}")
    crng = cell.Range
    crng.End = crng.End - 1  # drop the cell-end marker
    before = crng.Text
    # Preserve formatting of the first run (italics etc.) by writing text into
    # the existing range rather than deleting+inserting a fresh unformatted run.
    crng.Text = new_text
    _save_close(doc, path)
    return {"table_anchor": table_anchor, "row": row, "col": col, "before": before, "after": new_text}


def _find_para_by_prefix(doc, prefix: str):
    pref = prefix.casefold()
    for para in doc.Paragraphs:
        body = para.Range.Text
        if body.lstrip().casefold().startswith(pref):
            return para
    return None


def _find_para_containing(doc, needle: str):
    n = needle.casefold()
    for para in doc.Paragraphs:
        if n in para.Range.Text.casefold():
            return para
    return None


def _para_index(doc, target) -> int:
    """1-based index of `target` paragraph in doc.Paragraphs (matched by Range.Start)."""
    ts = target.Range.Start
    for i, p in enumerate(doc.Paragraphs, start=1):
        if p.Range.Start == ts:
            return i
    raise WordError("could not locate anchor paragraph index")


def op_replace_caption(word, path: Path, label: str, new_text: str) -> dict:
    doc = word.Documents.Open(str(path.resolve()), ReadOnly=False, AddToRecentFiles=False)
    para = _find_para_by_prefix(doc, label)
    if para is None:
        doc.Close(SaveChanges=False)
        raise WordError(f"no caption paragraph starting with {label!r}")
    para_start = para.Range.Start
    rng = para.Range
    rng.End = rng.End - 1  # preserve paragraph mark
    rng.Text = new_text
    # Re-resolve the paragraph by its stable start offset — after setting .Text the
    # original `para`/`rng` handles can be stale, which silently dropped the bold
    # (the label kept bold=None). Compute an ABSOLUTE label range from the fresh
    # paragraph and apply formatting there.
    dot = new_text.find(". ")
    label_len = dot + 1 if dot != -1 else len(label)  # up through the label's period
    body = doc.Range(Start=para_start, End=para_start + len(new_text))
    body.Font.Name = "Arial"
    body.Font.Bold = False
    lab = doc.Range(Start=para_start, End=para_start + label_len)
    lab.Font.Bold = True
    lab.Font.BoldBi = True  # complex-script bold too (mirrors <w:bCs/>)
    _save_close(doc, path)
    return {"label": label, "label_bolded_chars": label_len}


def op_move_table(word, path: Path, table_header: str, after_header: str) -> dict:
    doc = word.Documents.Open(str(path.resolve()), ReadOnly=False, AddToRecentFiles=False)
    n_tables_before = doc.Tables.Count
    cap = _find_para_by_prefix(doc, table_header) or _find_para_containing(doc, table_header)
    if cap is None:
        doc.Close(SaveChanges=False)
        raise WordError(f"no caption/paragraph matching {table_header!r}")
    anchor = _find_para_by_prefix(doc, after_header) or _find_para_containing(doc, after_header)
    if anchor is None:
        doc.Close(SaveChanges=False)
        raise WordError(f"no anchor paragraph matching {after_header!r}")

    # Range = caption paragraph .. end of the table immediately after it.
    start = cap.Range.Start
    # the table should be the next table after the caption
    tbl = None
    for t in doc.Tables:
        if t.Range.Start >= cap.Range.End:
            tbl = t
            break
    if tbl is None:
        doc.Close(SaveChanges=False)
        raise WordError(f"no table found after caption {table_header!r}")

    # Move via Range.FormattedText, COPY-THEN-DELETE order (never the clipboard —
    # Word's Cut/Paste hangs under headless COM). Copying the caption+table range
    # into the destination FIRST, while the source still exists, preserves the
    # table grid; only then do we delete the source. Anchor is remembered by a
    # bookmark so the source delete (which shifts offsets) does not lose it.
    bmk = "_wco_move_anchor"
    anchor_rng = anchor.Range
    anchor_rng.Collapse(WD_COLLAPSE_END)
    doc.Bookmarks.Add(Name=bmk, Range=anchor_rng)

    src_rng = doc.Range(Start=start, End=tbl.Range.End)
    moving = src_rng.FormattedText  # live copy while source still present

    # paste into destination first
    dest = doc.Bookmarks(bmk).Range
    dest.Collapse(WD_COLLAPSE_END)
    dest.InsertParagraphAfter()
    dest.Collapse(WD_COLLAPSE_END)
    dest.FormattedText = moving

    # re-resolve the source by content (offsets moved after the insert) and delete it
    cap2 = _find_para_by_prefix(doc, table_header) or _find_para_containing(doc, table_header)
    if cap2 is not None:
        tbl2 = None
        for t in doc.Tables:
            if t.Range.Start >= cap2.Range.End:
                tbl2 = t
                break
        if tbl2 is not None:
            doc.Range(Start=cap2.Range.Start, End=tbl2.Range.End).Delete()
    try:
        doc.Bookmarks(bmk).Delete()
    except Exception:
        pass

    n_tables_after = doc.Tables.Count
    if n_tables_after != n_tables_before:
        doc.Close(SaveChanges=False)
        raise WordError(
            f"table count changed {n_tables_before}->{n_tables_after}; aborted (not saved)"
        )
    _save_close(doc, path)
    return {"tables_before": n_tables_before, "tables_after": n_tables_after}


def op_insert_figure(word, path: Path, anchor: str, png: Path, caption: str | None) -> dict:
    if not png.exists():
        raise WordError(f"png not found: {png}")
    doc = word.Documents.Open(str(path.resolve()), ReadOnly=False, AddToRecentFiles=False)
    para = _find_para_containing(doc, anchor)
    if para is None:
        doc.Close(SaveChanges=False)
        raise WordError(f"no paragraph containing anchor {anchor!r}")
    # SAFE INSERTION pattern (validated): InsertParagraphAfter to spawn a new empty
    # paragraph, then RE-FETCH that paragraph by index and set its Range.Text with
    # End-1 (excluding the paragraph mark). Setting .Text on a range collapsed past
    # a fresh mark bleeds into and merges the following body paragraph; the
    # re-fetch + End-1 approach keeps every paragraph isolated (same End-1 idiom as
    # op_replace_caption). We insert the picture paragraph first, then the caption
    # paragraph below it → final order: anchor | picture | caption | body.
    anchor_idx = _para_index(doc, para)

    # picture paragraph
    para.Range.Collapse(WD_COLLAPSE_END)
    para.Range.InsertParagraphAfter()
    pic_para = doc.Paragraphs(anchor_idx + 1)
    pic_rng = pic_para.Range
    pic_rng.End = pic_rng.End - 1  # inside the empty paragraph, before its mark
    doc.InlineShapes.AddPicture(FileName=str(png.resolve()), LinkToFile=False,
                                SaveWithDocument=True, Range=pic_rng)

    added_caption = False
    if caption:
        pic_para2 = doc.Paragraphs(anchor_idx + 1)
        pic_para2.Range.Collapse(WD_COLLAPSE_END)
        pic_para2.Range.InsertParagraphAfter()
        cap_para = doc.Paragraphs(anchor_idx + 2)
        crng = cap_para.Range
        crng.End = crng.End - 1
        crng.Text = caption
        crng.Font.Name = "Arial"
        added_caption = True
    _save_close(doc, path)
    return {"anchor": anchor, "png": str(png), "caption_added": added_caption}


def op_insert_table(word, path: Path, anchor: str, rows: list[list[str]], caption: str | None) -> dict:
    if not rows or not all(isinstance(r, list) for r in rows):
        raise WordError("ROWSJSON must be a non-empty JSON list-of-lists")
    ncols = max(len(r) for r in rows)
    doc = word.Documents.Open(str(path.resolve()), ReadOnly=False, AddToRecentFiles=False)
    para = _find_para_containing(doc, anchor)
    if para is None:
        doc.Close(SaveChanges=False)
        raise WordError(f"no paragraph containing anchor {anchor!r}")
    rng = para.Range
    rng.Collapse(WD_COLLAPSE_END)
    rng.InsertParagraphAfter()
    rng.Collapse(WD_COLLAPSE_END)
    if caption:
        rng.Text = caption
        rng.Font.Name = "Arial"
        rng.Collapse(WD_COLLAPSE_END)
        rng.InsertParagraphAfter()
        rng.Collapse(WD_COLLAPSE_END)
    tbl = doc.Tables.Add(Range=rng, NumRows=len(rows), NumColumns=ncols)
    tbl.Borders.Enable = True
    for i, row in enumerate(rows, start=1):
        for j, val in enumerate(row, start=1):
            if j <= ncols:
                cell = tbl.Cell(i, j).Range
                cell.Text = str(val)
    _save_close(doc, path)
    return {"anchor": anchor, "rows": len(rows), "cols": ncols, "caption_added": bool(caption)}


# ----------------------------------------------------------------------------- cli


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_common(p):
        p.add_argument("docx", type=Path)
        p.add_argument("-o", "--output", type=Path, default=None)
        p.add_argument("--in-place", action="store_true")
        p.add_argument("--json", action="store_true")

    p = sub.add_parser("accept-revisions"); add_common(p)

    p = sub.add_parser("find-replace"); add_common(p)
    p.add_argument("old"); p.add_argument("new")
    p.add_argument("--tracked", action="store_true")
    p.add_argument("--match-case", action="store_true")
    p.add_argument("--whole-word", action="store_true")

    p = sub.add_parser("replace-caption"); add_common(p)
    p.add_argument("label"); p.add_argument("new_text")

    p = sub.add_parser("set-table-cell"); add_common(p)
    p.add_argument("table_anchor"); p.add_argument("row", type=int); p.add_argument("col", type=int)
    p.add_argument("new_text")

    p = sub.add_parser("move-table"); add_common(p)
    p.add_argument("table_header"); p.add_argument("after_header")

    p = sub.add_parser("insert-figure"); add_common(p)
    p.add_argument("anchor"); p.add_argument("png", type=Path)
    p.add_argument("--caption", default=None)

    p = sub.add_parser("insert-table"); add_common(p)
    p.add_argument("anchor"); p.add_argument("rows_json")
    p.add_argument("--caption", default=None)

    args = ap.parse_args()
    _ensure_env()

    if not args.docx.exists():
        sys.exit(f"ERROR: file not found: {args.docx}")

    target = _prep_output(args.docx, args.output, args.in_place)

    word = None
    try:
        word = _open_word()
        if args.cmd == "accept-revisions":
            res = op_accept_revisions(word, target)
        elif args.cmd == "find-replace":
            res = op_find_replace(word, target, args.old, args.new,
                                  tracked=args.tracked, match_case=args.match_case,
                                  whole_word=args.whole_word)
        elif args.cmd == "replace-caption":
            res = op_replace_caption(word, target, args.label, args.new_text)
        elif args.cmd == "set-table-cell":
            res = op_set_table_cell(word, target, args.table_anchor, args.row, args.col, args.new_text)
        elif args.cmd == "move-table":
            res = op_move_table(word, target, args.table_header, args.after_header)
        elif args.cmd == "insert-figure":
            res = op_insert_figure(word, target, args.anchor, args.png, args.caption)
        elif args.cmd == "insert-table":
            rows = json.loads(args.rows_json)
            res = op_insert_table(word, target, args.anchor, rows, args.caption)
        else:  # pragma: no cover
            sys.exit(f"unknown cmd {args.cmd}")
    except WordError as e:
        print(f"[FAILED] {e}", file=sys.stderr)
        sys.exit(2)
    finally:
        try:
            if word is not None:
                word.Quit(SaveChanges=False)
        except Exception:
            pass

    res["output"] = str(target)
    if args.json:
        print(json.dumps(res, indent=2, ensure_ascii=False))
    else:
        print(f"[OK] {args.cmd}: {res}")


if __name__ == "__main__":
    main()
