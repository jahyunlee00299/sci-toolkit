"""
cwyw_update.py — run EndNote's "Update Citations and Bibliography" on a Word document
from Python.

WHY THIS WORKS (260726 finding, corrects an earlier "impossible" verdict)
------------------------------------------------------------------------
A previous attempt concluded CWYW could not be automated, because it created Word through
``win32.Dispatch("Word.Application")``. That instance starts in *automation mode* and loads
no COM add-ins, so ``EndNote.WordAddin.Connect`` is absent and ``Application.Run`` finds no
macro — the failure was the headless instance, not CWYW itself.

Opening the document normally (Start-Process / os.startfile) launches a full Word session
with the add-in connected and ``EndNote Cwyw.dotm`` attached. Attaching to THAT session with
``GetActiveObject`` makes the macro reachable:

    Application.Run("ENFormatBibliography")

Verified on Word 16.0 + EndNote 2025: 173 unformatted ``{Author, Year #RN}`` markers were
converted to fields and a 57-entry bibliography was generated, INVALID CITATION 0.

Note: ``VBProject`` enumeration stays blocked unless "Trust access to the VBA project object
model" is enabled — it is not needed, the macro name above is enough.

Usage
-----
    python cwyw_update.py "C:/path/to/manuscript.docx"        # open, update, save, close
    python cwyw_update.py "C:/path/to/manuscript.docx" --keep-open
    python cwyw_update.py --attached                          # use the already-open document

Guarded run (261023): before the macro, ``cwyw_guard.precheck`` refuses a document with a
tracked-deleted citation field, a foreign-library db-id or an orphan RecNum (``--force``
overrides), and a snapshot of the expected citation order is taken. After the save, the file
on disk is re-read and compared; a SHIFT, a RESURRECTED record, an unconverted marker or a
field naming the wrong author exits 4. ``--attached`` snapshots the document's saved file, so
save it before running.

Exit: 0 updated, saved and verified | 1 add-in or macro unavailable / precheck blocked
      | 2 bad input | 4 CWYW output failed verification (the file is saved: inspect, do not ship)
"""

import argparse
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cwyw_guard  # noqa: E402

try:
    import win32com.client as win32
except ImportError:
    print("[ERR] pywin32 is required (pip install pywin32)")
    sys.exit(1)

MACROS = ["ENFormatBibliography", "EndNote Cwyw.dotm!ENFormatBibliography",
          "ENRefreshCitations", "ENUpdateCitationsAndBibliography"]


def attach(timeout=60):
    """Attach to a running Word, waiting for it to finish starting up."""
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            return win32.GetActiveObject("Word.Application")
        except Exception as exc:
            last = exc
            time.sleep(2)
    raise RuntimeError("could not attach to Word: %s" % last)


def addin_ready(app):
    try:
        for a in app.COMAddIns:
            if "EndNote" in (a.Description or "") and a.Connect:
                return True
    except Exception:
        pass
    return False


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("docx", nargs="?", help="document to update (omit with --attached)")
    ap.add_argument("--attached", action="store_true", help="operate on the already-open ActiveDocument")
    ap.add_argument("--keep-open", action="store_true", help="leave Word open afterwards")
    ap.add_argument("--db", default=cwyw_guard.DEFAULT_DB, help="library for precheck / verify")
    ap.add_argument("--force", action="store_true", help="run even when precheck blocks")
    ap.add_argument("--no-guard", action="store_true", help="skip precheck and verify entirely")
    ap.add_argument("--keep-husks", action="store_true",
                    help="do not unlink payload-less EN.CITE fields before the macro")
    args = ap.parse_args()
    lib = cwyw_guard.Library(args.db) if (not args.no_guard and os.path.exists(args.db)) else None

    snap = None
    if not args.attached:
        if not args.docx or not os.path.exists(args.docx):
            print("[ERR] document not found: %r" % args.docx)
            return 2
        if not args.no_guard:
            snap = guard_before(args.docx, lib, args.force)
            if snap is False:
                return 1
        os.startfile(os.path.abspath(args.docx))   # full Word session -> add-ins load
        time.sleep(10)

    app = attach()
    doc = app.ActiveDocument
    print("document: %s" % doc.Name)
    path = doc.FullName
    if args.attached and not args.no_guard:
        snap = guard_before(path, lib, args.force)
        if snap is False:
            return 1

    if not addin_ready(app):
        print("[ERR] the EndNote CWYW add-in is not connected in this Word session.")
        print("      Open the document by double-clicking it (not via automation) and retry.")
        return 1

    if not args.keep_husks:
        n = unhusk(doc)
        if n:
            print("unhusk   : %d payload-less EN.CITE field(s) unlinked to their marker text" % n)

    before = doc.Fields.Count
    ran = None
    for name in MACROS:
        try:
            app.Run(name)
            ran = name
            break
        except Exception:
            continue
    if not ran:
        print("[ERR] no CWYW macro could be run (tried: %s)" % ", ".join(MACROS))
        return 1

    time.sleep(3)
    doc.Save()
    time.sleep(1)
    after = doc.Fields.Count
    print("macro    : %s" % ran)
    print("fields   : %d -> %d" % (before, after))
    print("saved    : %s" % doc.Saved)
    verdict = 0
    if snap:
        problems = cwyw_guard.verify(snap, path, lib)
        for p in problems[:20]:
            print("  FAIL " + p)
        print("verify   : %s" % ("%d problem(s) - do NOT ship this output" % len(problems) if problems else "ok"))
        verdict = 4 if problems else 0

    if not args.keep_open and not args.attached:
        doc.Close(SaveChanges=0)
        try:
            app.Quit()
        except Exception:
            pass
    if verdict:
        return verdict
    print("\nDONE. Also run docx/scripts/endnote_biblio_check.py before trusting the output.")
    return 0


HUSK_RESULT = re.compile(r"^\s*\{[^{}]*#\s*\d+[^{}]*\}\s*$")


def unhusk(doc):
    """Unlink EN.CITE fields that carry no record payload and still show marker text.

    Measured 261023 on a manuscript copy: CWYW turns each such field (the 260714 "fldData
    husk") into "!!! INVALID CITATION !!! {...}" with RecNum 0. The field holds nothing but
    its result text, so Unlink() — which replaces a field with its result — loses nothing and
    hands CWYW an ordinary {Author, Year #N} marker. Runs untracked: the field never
    reached the reader as anything but that text.
    """
    tracked = doc.TrackRevisions
    doc.TrackRevisions = False
    n = 0
    try:
        for i in range(doc.Fields.Count, 0, -1):     # backwards: Unlink renumbers
            f = doc.Fields(i)
            # the husk keeps its nested EN.CITE.DATA field (fldData "PA==", one "<" byte), so
            # the OUTER code reads " ADDIN EN.CITE  ADDIN EN.CITE.DATA "; the nested field
            # itself never matches (empty result) and goes with its parent.
            code = (f.Code.Text or "").strip()
            if code.startswith("ADDIN EN.CITE") and not code.startswith("ADDIN EN.CITE.DATA") \
                    and "<EndNote>" not in code and HUSK_RESULT.match(f.Result.Text or ""):
                f.Unlink()
                n += 1
    finally:
        doc.TrackRevisions = tracked
    return n


def guard_before(docx, lib, force):
    """precheck + snapshot. Returns the snapshot, or False when precheck blocks."""
    _, findings = cwyw_guard.precheck(docx, lib)
    for level, code, _, msg in findings:
        print("  %-5s %-13s %s" % (level, code, msg))
    if any(f[0] == "BLOCK" for f in findings) and not force:
        print("[ERR] precheck blocked this document (see SKILL.md); --force overrides.")
        return False
    snap = cwyw_guard.snapshot(docx)
    print("snapshot : %d citation group(s), %d deleted record(s)" % (len(snap["groups"]), len(snap["deleted_recnums"])))
    return snap


if __name__ == "__main__":
    sys.exit(main())
