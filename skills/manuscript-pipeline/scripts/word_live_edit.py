#!/usr/bin/env python
"""
Live Word edit — attach to the ALREADY-OPEN document and edit it in place,
so the change appears immediately in the window the user is watching.

Usage:
  python live_edit.py <mode> [args...]

Modes:
  probe                         -> list open docs + attach status
  find     "TEXT"               -> report page/found for TEXT (read-only)
  replace  "OLD" "NEW"          -> find-replace once, save (screen updates live)
  replace-tracked "OLD" "NEW"   -> same but recorded as a tracked change (author=Claude)
  italic   "TERM"               -> re-apply italic to every occurrence of TERM
  save                          -> save the open doc

Notes:
  - Attaches via GetActiveObject; NEVER opens a new hidden instance, so no file-lock clash.
  - MatchCase=True, Wrap=wdFindStop. Screen scrolls to the edit so the user sees it.
  - EndNote {Author, Year #NNN} placeholders here are plain text; moved/edited as text.
  - Match name substring of the target doc via env DOC_MATCH (required).
"""

# Windows' default console is cp949 and dies on non-ASCII/symbol output. Force UTF-8.
# Use reconfigure: wrapping in a TextIOWrapper takes ownership of the underlying
# stream, so once this module is imported, GC'ing the wrapper closes the
# caller's stdout too (measured).
import sys as _sys
for _s in (_sys.stdout, _sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
import win32com.client as win32

DOC_MATCH = os.environ.get("DOC_MATCH", "")  # required: substring of the open doc name
WD_REPLACE_ALL = 2
WD_FIND_STOP = 0
WD_PAGE = 3  # wdActiveEndPageNumber

def get_word():
    return win32.GetActiveObject("Word.Application")

def get_doc(word):
    # An empty DOC_MATCH substring-matches every open document, which would attach
    # to an arbitrary one and edit the wrong manuscript. Require it explicitly.
    if not DOC_MATCH:
        raise SystemExit(
            "[ERR] DOC_MATCH is required — set it to a substring of the target "
            'document name (e.g. DOC_MATCH="Main_v12"). Refusing to guess.'
        )
    matches = [
        word.Documents.Item(i)
        for i in range(1, word.Documents.Count + 1)
        if DOC_MATCH in word.Documents.Item(i).Name
    ]
    if not matches:
        raise SystemExit(f"[ERR] no open doc matching {DOC_MATCH!r}. Open it in Word first.")
    if len(matches) > 1:
        names = ", ".join(d.Name for d in matches)
        raise SystemExit(f"[ERR] {DOC_MATCH!r} matches {len(matches)} open docs ({names}). Narrow it.")
    return matches[0]

def do_find(doc, text):
    f = doc.Content.Find
    f.ClearFormatting(); f.Text = text; f.Forward = True; f.Wrap = WD_FIND_STOP; f.MatchCase = True
    if f.Execute():
        rng = f.Parent
        rng.Select()  # scroll into view
        print(f"[FOUND] page {rng.Information(WD_PAGE)}: {text!r}")
        return True
    print(f"[MISS] {text!r}")
    return False

def do_replace(doc, old, new, tracked=False):
    prev = doc.TrackRevisions
    if tracked:
        doc.TrackRevisions = True
    try:
        f = doc.Content.Find
        f.ClearFormatting(); f.Replacement.ClearFormatting()
        f.Text = old; f.Replacement.Text = new
        f.Forward = True; f.Wrap = WD_FIND_STOP; f.MatchCase = True
        hit = f.Execute(Replace=WD_REPLACE_ALL)
        print(f"[{'OK' if hit else 'MISS'}] replace ({'tracked' if tracked else 'direct'})")
        if hit:
            # scroll to the edited spot
            g = doc.Content.Find
            g.ClearFormatting(); g.Text = new[:120]; g.Forward=True; g.Wrap=WD_FIND_STOP; g.MatchCase=True
            if g.Execute():
                g.Parent.Select()
        doc.Save()
        print("[SAVED]")
        return hit
    finally:
        doc.TrackRevisions = prev

def do_italic(doc, term):
    rng = doc.Content
    f = rng.Find
    f.ClearFormatting(); f.Text = term; f.Forward=True; f.Wrap=WD_FIND_STOP; f.MatchCase=True
    n = 0
    while f.Execute():
        rng.Italic = True
        rng.Collapse(0)
        f = rng.Find
        f.ClearFormatting(); f.Text = term; f.Forward=True; f.Wrap=WD_FIND_STOP; f.MatchCase=True
        n += 1
        if n > 100: break
    doc.Save()
    print(f"[OK] italic x{n} on {term!r}; saved")

def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    mode = sys.argv[1]
    word = get_word()
    if mode == "probe":
        print("attached; open docs:", word.Documents.Count, "| Visible:", word.Visible)
        for i in range(1, word.Documents.Count+1):
            d = word.Documents.Item(i)
            print(f"  [{i}] {d.Name}  saved={d.Saved}")
        return
    doc = get_doc(word)
    if mode == "find":
        do_find(doc, sys.argv[2])
    elif mode == "replace":
        do_replace(doc, sys.argv[2], sys.argv[3], tracked=False)
    elif mode == "replace-tracked":
        do_replace(doc, sys.argv[2], sys.argv[3], tracked=True)
    elif mode == "italic":
        do_italic(doc, sys.argv[2])
    elif mode == "save":
        doc.Save(); print("[SAVED]")
    else:
        print("unknown mode:", mode); print(__doc__)

if __name__ == "__main__":
    main()
