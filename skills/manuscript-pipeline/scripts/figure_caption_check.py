#!/usr/bin/env python
"""figure_caption_check.py — Figure/Table/Scheme caption <-> content QC for docx.

WHY THIS EXISTS (MANUSCRIPT_QC_TOOLING_PLAN H3):
    Captions silently drift from the figures they describe. Observed failures:
      - a Figure caption named the wrong markers ("orange diamonds") and omitted
        the value axis;
      - a Scheme caption promised "(A)/(B)" panels a single-panel image never had;
      - a kinetics table captioned "Table 4" was physically the 2nd table;
      - one table caption was not bold while all others were;
      - in-image spelling (organised/isomerisation) disagreed with the manuscript's
        American-English convention.

WHAT THIS DOES:
    1. Extract every display-item caption (Figure/Table/Scheme N.) with its number,
       body text, label-bold state, and font — reading the OOXML directly and
       resolving tracked changes via manuscript_text.py semantics is NOT needed
       here because captions are read from the RENDERED paragraph runs.
    2. Static, automatable checks (each a machine verdict):
       C1 numbering — per-kind numbers are contiguous 1..N, no gaps/dupes.
       C2 order     — first-citation order in body == physical caption order.
       C3 bold      — the "Figure N."/"Table N." label token is bold on EVERY caption
                       (flag the odd ones out).
       C4 spelling  — caption text uses one English variant consistently
                       (flag British -ise/-isation/-our tokens if the doc is American).
       C5 numbers   — every number token in a caption also appears in the body text.
       C3b bold     — inside a caption only the label is bold; the descriptive body
                       must be roman (catches a bold Caption paragraph style).
       C6 aspect    — each embedded image's display extent matches its native pixel
                       aspect ratio (flag >2% distortion from squashed/stretched cx:cy).
       C7 pagebreak — a Figure/Scheme caption followed by body prose has a page break
                       between them (so the next section does not cling to the caption).
    3. Extract embedded images to a folder and emit a HUMAN/AGENT visual checklist
       forcing a caption<->image comparison for claims a static check cannot see
       (panel letters, marker shapes/colors, axis labels, quantity of panels).

    This tool FLAGS; it does not edit. Fix captions with
    word_com_ops.py replace-caption.

USAGE:
    python figure_caption_check.py file.docx                 # report to stdout
    python figure_caption_check.py file.docx --extract-images DIR
    python figure_caption_check.py file.docx --json
    python figure_caption_check.py file.docx --variant british   # doc uses British

EXIT CODES:  0 no flags | 1 flags raised | 2 error
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
import zipfile
from pathlib import Path

if __name__ == "__main__" and hasattr(sys.stdout, "buffer"):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except (ValueError, io.UnsupportedOperation):
        pass

_KINDS = ("Figure", "Table", "Scheme")
# Accept "Figure N.", "Fig. N.", "Figs. N.", "Table N.", "Scheme N." — many journals
# (and this lab's manuscripts) caption with the "Fig." abbreviation, which the old
# "Figure"-only pattern silently skipped, defeating the entire QC.
_CAP_RE = re.compile(
    r"^\s*(Figures?|Figs?\.|Tables?|Schemes?)\s*(\d+)\s*\.?", re.IGNORECASE
)


def _canon_kind(raw: str) -> str:
    """Normalize a caption-prefix token to its canonical kind."""
    r = raw.lower().rstrip(".s")
    if r.startswith("fig"):
        return "Figure"
    if r.startswith("table"):
        return "Table"
    if r.startswith("scheme"):
        return "Scheme"
    return raw.capitalize()


# British spellings whose American form is the manuscript convention (and vice-versa).
# EXPLICIT word lists only — a catch-all \w+ise/ize pattern false-flags ordinary words
# (exercise, noise, otherwise, surprise, precise, size, prize ...) that have no
# transatlantic variant. Each entry here has a genuine -ise/-ize counterpart.
_BRITISH_WORDS = [
    "colour", "behaviour", "flavour", "favour", "labour", "honour", "vapour", "odour",
    "centre", "metre", "litre", "fibre", "theatre", "calibre",
    "analyse", "analysed", "analysing", "catalyse", "catalysed", "catalysing",
    "organise", "organised", "organising", "utilise", "utilised", "utilising",
    "optimise", "optimised", "optimising", "characterise", "characterised", "characterising",
    "recognise", "recognised", "minimise", "minimised", "maximise", "maximised",
    "standardise", "standardised", "sterilise", "sterilised", "hydrolyse", "hydrolysed",
    "isomerise", "isomerised", "isomerisation", "polymerise", "polymerised", "polymerisation",
    "oxidise", "oxidised", "oxidisation", "neutralise", "neutralised",
    "unfavourable", "favourable", "neighbour", "neighbouring", "colouration",
]
_AMERICAN_WORDS = [
    "color", "behavior", "flavor", "favor", "labor", "honor", "vapor", "odor",
    "center", "meter", "liter", "fiber", "theater", "caliber",
    "analyze", "analyzed", "analyzing", "catalyze", "catalyzed", "catalyzing",
    "organize", "organized", "organizing", "utilize", "utilized", "utilizing",
    "optimize", "optimized", "optimizing", "characterize", "characterized", "characterizing",
    "recognize", "recognized", "minimize", "minimized", "maximize", "maximized",
    "standardize", "standardized", "sterilize", "sterilized", "hydrolyze", "hydrolyzed",
    "isomerize", "isomerized", "isomerization", "polymerize", "polymerized", "polymerization",
    "oxidize", "oxidized", "oxidation", "neutralize", "neutralized",
    "unfavorable", "favorable", "neighbor", "neighboring", "coloration",
]
_BRITISH_TOKENS = re.compile(r"\b(" + "|".join(sorted(_BRITISH_WORDS, key=len, reverse=True)) + r")\b", re.IGNORECASE)
_AMERICAN_TOKENS = re.compile(r"\b(" + "|".join(sorted(_AMERICAN_WORDS, key=len, reverse=True)) + r")\b", re.IGNORECASE)

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _effective_bold(run, para):
    """EFFECTIVE bold of a run, resolving inheritance. run.bold may be:
      True/False -> explicit direct formatting (wins)
      None       -> inherited: fall back to the run's character style, then the
                    paragraph style. A caption whose label is bold via a bold
                    PARAGRAPH STYLE (not a direct <w:b/>) must still read as bold —
                    otherwise a legitimately-bold label is falsely flagged.
    """
    if run.bold is not None:
        return bool(run.bold)
    # run character style
    try:
        st = run.style
        while st is not None:
            b = st.font.bold
            if b is not None:
                return bool(b)
            st = st.base_style
    except Exception:
        pass
    # paragraph style chain
    try:
        st = para.style
        while st is not None:
            b = st.font.bold
            if b is not None:
                return bool(b)
            st = st.base_style
    except Exception:
        pass
    return False  # nothing asserts bold anywhere -> not bold


def _para_text_and_bold(p):
    """Return (text, label_is_bold) for a python-docx paragraph, where label_is_bold
    is whether the leading "Figure N." token is bold (direct OR inherited)."""
    text = p.text
    m = _CAP_RE.match(text)
    if not m:
        return text, None
    label_end = m.end()
    consumed = 0
    bold_states = []
    for run in p.runs:
        rlen = len(run.text)
        if consumed >= label_end:
            break
        if run.text.strip():
            bold_states.append(_effective_bold(run, p))
        consumed += rlen
    label_bold = all(bold_states) if bold_states else False
    return text, label_bold


def _first_font(p):
    for run in p.runs:
        if run.text.strip() and run.font and run.font.name:
            return run.font.name
    # fall back to style font
    try:
        return p.style.font.name
    except Exception:
        return None


def collect_captions(docx: Path):
    """Return list of caption dicts in physical (document) order."""
    import docx as _docx

    d = _docx.Document(str(docx))
    caps = []
    for i, p in enumerate(d.paragraphs):
        text, label_bold = _para_text_and_bold(p)
        m = _CAP_RE.match(text)
        if not m:
            continue
        kind = _canon_kind(m.group(1))
        # label = the manuscript's actual prefix+number as written ("Fig. 1." / "Figure 1.")
        label = text.strip()[: m.end()].strip()
        if not label.endswith("."):
            label += "."
        caps.append(
            {
                "phys_index": i,
                "kind": kind,
                "num": int(m.group(2)),
                "label": label,
                "text": text.strip(),
                "label_bold": label_bold,
                "font": _first_font(p),
            }
        )
    return caps


def body_text(docx: Path) -> str:
    """Prose body only — EXCLUDES caption paragraphs so C5 does not match a
    caption number against itself (a caption's own '777' must appear in the prose,
    not merely in the caption)."""
    import docx as _docx

    d = _docx.Document(str(docx))
    return "\n".join(p.text for p in d.paragraphs if not _CAP_RE.match(p.text))


def check_numbering(caps):
    flags = []
    by_kind = {}
    for c in caps:
        by_kind.setdefault(c["kind"], []).append(c["num"])
    for kind, nums in by_kind.items():
        seen = sorted(set(nums))
        dupes = sorted({n for n in nums if nums.count(n) > 1})
        if dupes:
            flags.append(f"C1 numbering: {kind} has duplicate number(s) {dupes}")
        expected = list(range(1, max(seen) + 1)) if seen else []
        missing = [n for n in expected if n not in seen]
        if missing:
            flags.append(f"C1 numbering: {kind} missing number(s) {missing} (have {seen})")
    return flags


def _citation_positions(body: str, kind: str) -> dict:
    """Map {figure/table/scheme number -> first body char position it is cited at},
    expanding range citations (Figs. 1-3 / Figures 2–4) and lists (Figs. 1 and 3).
    """
    prefix = {"Figure": r"Fig(?:ure)?s?\.?", "Table": r"Tables?", "Scheme": r"Schemes?"}[kind]
    # capture the run of numbers/ranges/separators right after the prefix
    pat = re.compile(prefix + r"\s*((?:\d+\s*[-–—]\s*\d+|\d+)(?:\s*(?:,|and|&|to)\s*(?:\d+\s*[-–—]\s*\d+|\d+))*)",
                     re.IGNORECASE)
    positions: dict[int, int] = {}
    for m in pat.finditer(body):
        span_text = m.group(1)
        start = m.start()
        # expand every number and every A-B range inside this citation
        for rng in re.finditer(r"(\d+)\s*[-–—]\s*(\d+)", span_text):
            a, b = int(rng.group(1)), int(rng.group(2))
            if a <= b and b - a < 500:
                for n in range(a, b + 1):
                    positions.setdefault(n, start)
        # standalone numbers (also catches the endpoints, harmless)
        for num in re.finditer(r"\d+", span_text):
            positions.setdefault(int(num.group(0)), start)
    return positions


def check_citation_order(caps, body: str):
    """First mention of each label in the body should follow the same order as the
    physical caption order, per kind."""
    flags = []
    by_kind = {}
    for c in caps:
        by_kind.setdefault(c["kind"], []).append(c)
    for kind, items in by_kind.items():
        # first-citation position in body for each number, including RANGE citations
        # ("Figs. 1-3", "Figures 2–4", "Tables 1 and 3") which the old per-number
        # regex could not see, causing false "never cited" flags.
        cite_pos = _citation_positions(body, kind)
        order = []
        for c in items:
            order.append((c["num"], cite_pos.get(c["num"], 10**12)))
        # physical order is items as-is; citation order = sorted by body position
        phys = [c["num"] for c in items]
        cited = [n for n, _ in sorted(order, key=lambda x: x[1])]
        uncited = [n for n, pos in order if pos == 10**12]
        if uncited:
            flags.append(f"C2 order: {kind} {uncited} never cited in body text")
        cited_known = [n for n in cited if n not in uncited]
        phys_known = [n for n in phys if n not in uncited]
        if cited_known != phys_known:
            flags.append(
                f"C2 order: {kind} citation order {cited_known} != physical order {phys_known}"
            )
    return flags


def check_bold(caps):
    flags = []
    states = [(c["label"], c["label_bold"]) for c in caps if c["label_bold"] is not None]
    bolded = [lbl for lbl, b in states if b]
    unbolded = [lbl for lbl, b in states if not b]
    if bolded and unbolded:
        flags.append(
            f"C3 bold: label bold is inconsistent — bold={bolded} but NOT bold={unbolded}"
        )
    return flags


def check_spelling(caps, variant: str):
    flags = []
    wrong = _BRITISH_TOKENS if variant == "american" else _AMERICAN_TOKENS
    other = "British" if variant == "american" else "American"
    for c in caps:
        hits = sorted(set(m.group(0) for m in wrong.finditer(c["text"])))
        if hits:
            flags.append(f"C4 spelling: {c['label']} caption has {other} spelling {hits}")
    return flags


def check_numbers(caps, body: str):
    """Flag caption numbers absent from the prose — but suppress numbers that recur
    across multiple captions (recurring experimental quantities like a 96-well plate
    or a shared temperature are legitimately caption-only) and tiny integers 0-9
    (panel counts / (n=3) / small labels are not body-referenced claims)."""
    flags = []
    body_nums = set(re.findall(r"\d+(?:\.\d+)?", body))
    # count how many DISTINCT captions each number appears in
    from collections import Counter
    cap_freq: Counter = Counter()
    per_cap_nums = []
    for c in caps:
        cap_body = _CAP_RE.sub("", c["text"], count=1)
        nums = re.findall(r"\d+(?:\.\d+)?", cap_body)
        per_cap_nums.append(nums)
        for n in set(nums):
            cap_freq[n] += 1
    for c, nums in zip(caps, per_cap_nums):
        missing = []
        for n in nums:
            if n in body_nums:
                continue
            if "." not in n and float(n) < 10:  # tiny integer: panel/replicate label
                continue
            if cap_freq[n] >= 2:  # recurs across captions = shared experimental quantity
                continue
            missing.append(n)
        if missing:
            flags.append(
                f"C5 numbers: {c['label']} caption number(s) {sorted(set(missing))} not found in body text"
            )
    return flags


def _read_png_size(data: bytes):
    if len(data) >= 24 and data[:8] == b"\x89PNG\r\n\x1a\n":
        import struct
        w = struct.unpack(">I", data[16:20])[0]
        h = struct.unpack(">I", data[20:24])[0]
        return w, h
    return None


def _read_jpg_size(data: bytes):
    import struct
    i = 2
    n = len(data)
    while i + 9 < n:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3):
            h = struct.unpack(">H", data[i + 5:i + 7])[0]
            w = struct.unpack(">H", data[i + 7:i + 9])[0]
            return w, h
        if i + 4 > n:
            break
        seglen = struct.unpack(">H", data[i + 2:i + 4])[0]
        i += 2 + seglen
    return None


def _pixel_size(name: str, data: bytes):
    low = name.lower()
    if low.endswith(".png"):
        return _read_png_size(data)
    if low.endswith((".jpg", ".jpeg")):
        return _read_jpg_size(data)
    return None


def check_image_aspect(docx: Path, tol_pct: float = 2.0):
    """C6 — every embedded raster whose display extent (wp:extent cx/cy) deviates
    from its native pixel aspect ratio by more than tol_pct is flagged as distorted.
    Reads the OOXML drawing blocks directly and matches each blip r:embed rId to its
    media file via document.xml.rels."""
    flags = []
    try:
        with zipfile.ZipFile(docx) as z:
            names = z.namelist()
            if "word/document.xml" not in names:
                return flags
            doc = z.read("word/document.xml").decode("utf-8", "replace")
            rels = ""
            if "word/_rels/document.xml.rels" in names:
                rels = z.read("word/_rels/document.xml.rels").decode("utf-8", "replace")
            rid2media = {}
            for m in re.finditer(r'Id="(rId\d+)"[^>]*Target="(media/[^"]+)"', rels):
                rid2media[m.group(1)] = m.group(2)
            px_cache = {}

            def px(media):
                if media not in px_cache:
                    try:
                        px_cache[media] = _pixel_size(media, z.read("word/" + media))
                    except Exception:
                        px_cache[media] = None
                return px_cache[media]

            for dm in re.finditer(r"<w:drawing>.*?</w:drawing>", doc, flags=re.S):
                block = dm.group(0)
                bm = re.search(r'<a:blip[^>]*r:embed="(rId\d+)"', block)
                em = re.search(r'<wp:extent cx="(\d+)" cy="(\d+)"', block)
                if not (bm and em):
                    continue
                media = rid2media.get(bm.group(1))
                if not media:
                    continue
                cx, cy = int(em.group(1)), int(em.group(2))
                p = px(media)
                if not p or cy == 0 or p[1] == 0:
                    continue
                disp_ar = cx / cy
                src_ar = p[0] / p[1]
                dev = abs(disp_ar - src_ar) / src_ar * 100.0
                if dev > tol_pct:
                    flags.append(
                        f"C6 aspect: {Path(media).name} native {p[0]}x{p[1]} "
                        f"(AR {src_ar:.3f}) vs display AR {disp_ar:.3f} = {dev:.0f}% distortion"
                    )
    except Exception:
        return flags
    return flags


def check_caption_body_bold(docx: Path):
    """C3b/C3c — within a caption, only the leading label ("Fig. N."/"Table N.")
    should be bold; the descriptive body must be roman. Flags a caption whose text
    AFTER the label carries bold (direct run bold OR inherited from a bold Caption
    paragraph style). Reads OOXML directly so paragraph-style inheritance is seen."""
    flags = []
    try:
        with zipfile.ZipFile(docx) as z:
            if "word/document.xml" not in z.namelist():
                return flags
            doc = z.read("word/document.xml").decode("utf-8", "replace")
            styles = ""
            if "word/styles.xml" in z.namelist():
                styles = z.read("word/styles.xml").decode("utf-8", "replace")
        # style ids whose definition asserts bold (rPr <w:b/> not val=0)
        bold_styles = set()
        for sm in re.finditer(r'<w:style [^>]*w:styleId="([^"]+)".*?</w:style>', styles, flags=re.S):
            blk = sm.group(0)
            if re.search(r"<w:b/>", blk) and not re.search(r'<w:b w:val="(?:0|false|none|off)"', blk):
                bold_styles.add(sm.group(1))

        def run_bold(run_xml, para_style_bold):
            m = re.search(r"<w:b(?:\s+w:val=\"([^\"]+)\")?\s*/?>", run_xml)
            if m:
                return m.group(1) not in ("0", "false", "none", "off")
            # no direct bold -> inherit from paragraph style
            return para_style_bold

        for p in re.split(r"(?=<w:p[ >])", doc):
            txt = "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", p, flags=re.S))
            txt = txt.replace("&amp;", "&")
            m = _CAP_RE.match(txt.strip())
            if not m:
                continue
            label = m.group(0)
            ps = re.search(r'<w:pStyle w:val="([^"]+)"', p)
            para_style_bold = bool(ps and ps.group(1) in bold_styles)
            # walk runs, accumulate character offset, check bold on runs past the label
            offset = 0
            body_bold_hit = False
            for rm in re.finditer(r"<w:r\b[^>]*>.*?</w:r>", p, flags=re.S):
                rtext = "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", rm.group(0), flags=re.S)).replace("&amp;", "&")
                if not rtext:
                    continue
                start = offset
                offset += len(rtext)
                # skip runs entirely within the label span
                if start < len(label):
                    continue
                if run_bold(rm.group(0), para_style_bold) and rtext.strip():
                    body_bold_hit = True
                    break
            if body_bold_hit:
                where = f' (Caption style "{ps.group(1)}" asserts bold)' if para_style_bold else ""
                flags.append(
                    f"C3b bold: {label} caption body is bold — only the label should be bold{where}"
                )
    except Exception:
        return flags
    return flags


def check_caption_pagebreak(docx: Path):
    """C7 — a Figure/Scheme caption immediately followed by body prose (not another
    caption, a heading, a table, or the section end) with no page break in between
    leaves the next paragraph clinging to the caption. Flags the missing break."""
    flags = []
    try:
        with zipfile.ZipFile(docx) as z:
            if "word/document.xml" not in z.namelist():
                return flags
            doc = z.read("word/document.xml").decode("utf-8", "replace")
    except Exception:
        return flags
    blocks = re.split(r"(?=<w:p[ >])|(?=<w:tbl>)", doc)

    def btext(b):
        return "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", b, flags=re.S)).replace("&amp;", "&")

    figcap = re.compile(r"^\s*(Fig(?:ure)?\.?\s*\d|Scheme\s*\d)", re.I)
    for i, b in enumerate(blocks):
        if not b.startswith("<w:p"):
            continue
        t = btext(b).strip()
        if not (t and figcap.match(t)):
            continue
        nxt = blocks[i + 1] if i + 1 < len(blocks) else ""
        nt = btext(nxt).strip()
        # next is a table/another caption/heading/section-end -> no break expected
        if nxt.startswith("<w:tbl>") or "<w:sectPr" in nxt:
            continue
        if figcap.match(nt) or re.match(r"^\s*(Table\s*\d)", nt, re.I):
            continue
        if re.search(r'<w:pStyle w:val="(?:Heading|[Hh]eading)', nxt):
            continue
        if not nt:  # empty spacer paragraph counts as separation
            continue
        has_break = ('<w:br w:type="page"' in b or '<w:br w:type="page"' in nxt
                     or "<w:pageBreakBefore" in nxt)
        if not has_break:
            label = figcap.match(t).group(0)
            flags.append(
                f"C7 pagebreak: {label} caption is followed by body text with no page break"
            )
    return flags


def extract_images(docx: Path, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    with zipfile.ZipFile(docx) as z:
        for n in z.namelist():
            if n.startswith("word/media/"):
                data = z.read(n)
                dst = out_dir / Path(n).name
                dst.write_bytes(data)
                saved.append(str(dst))
    return sorted(saved)


def visual_checklist(caps, images):
    lines = ["VISUAL CHECKLIST (a static check cannot verify these — view each image):"]
    for c in caps:
        if c["kind"] in ("Figure", "Scheme"):
            lines.append(f"  [ ] {c['label']}  ↔  its image:")
            # Ask the identity question BEFORE the detail questions. A figure
            # integration once put one figure's chart under another's caption; every
            # static check passed (bytes intact, aspect ratio exact) because they
            # answer "is this image well-formed", not "is this the right image".
            # Comparing panel letters on the wrong figure finds nothing.
            lines.append("        - IS THIS THE RIGHT FIGURE AT ALL? the image depicts what the")
            lines.append("          caption describes (not merely a well-formed image)")
            lines.append("        - panel letters (A)/(B)/... in caption match panels in image")
            lines.append("        - marker shapes/colors named in caption appear in image")
            lines.append("        - axis labels named in caption appear on the image axes")
            lines.append("        - in-image spelling matches manuscript English variant")
    lines.append(f"  extracted images ({len(images)}): {[Path(i).name for i in images]}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("docx", type=Path)
    ap.add_argument("--variant", choices=["american", "british"], default="american",
                    help="manuscript English convention (default american) for C4 spelling")
    ap.add_argument("--extract-images", type=Path, default=None,
                    help="save embedded images to this dir for visual comparison")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not args.docx.exists():
        sys.exit(f"ERROR: file not found: {args.docx}")

    try:
        caps = collect_captions(args.docx)
        body = body_text(args.docx)
    except Exception as e:
        sys.exit(f"ERROR: failed to read docx: {e}")

    flags = []
    flags += check_numbering(caps)
    flags += check_citation_order(caps, body)
    flags += check_bold(caps)
    flags += check_caption_body_bold(args.docx)
    flags += check_spelling(caps, args.variant)
    flags += check_numbers(caps, body)
    flags += check_image_aspect(args.docx)
    flags += check_caption_pagebreak(args.docx)

    images = []
    if args.extract_images:
        images = extract_images(args.docx, args.extract_images)

    if args.json:
        print(json.dumps({
            "captions": caps,
            "flags": flags,
            "images": images,
        }, indent=2, ensure_ascii=False))
    else:
        print(f"{'=' * 68}\nFIGURE/CAPTION QC: {args.docx.name}\n{'=' * 68}")
        print(f"display items: {len(caps)}  "
              f"({', '.join(sorted({c['kind'] for c in caps})) or 'none'})")
        for c in caps:
            bold = {True: "bold", False: "NOT-bold", None: "?"}[c["label_bold"]]
            print(f"  {c['label']:<11} label={bold:<8} font={c['font']}")
        print()
        if flags:
            print(f"[{len(flags)} FLAG(S)]")
            for f in flags:
                print(f"  ! {f}")
        else:
            print("[PASS] no static caption flags")
        if args.extract_images:
            print()
            print(visual_checklist(caps, images))

    sys.exit(1 if flags else 0)


if __name__ == "__main__":
    main()
