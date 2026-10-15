#!/usr/bin/env python3
"""
template_adapter.py -- build journal-ppt decks on a REAL third-party .pptx/.potx template.

deck_builder.Deck draws every slide itself on a blank 13.333 x 7.5 in canvas. A real template
(university, conference, slide-marketplace) instead carries its own masters, layouts and
placeholders at its own slide size. This module reads such a template and fills its placeholders
by meaning, with the same refusal-to-overflow discipline as Deck.

CLI
    python template_adapter.py inspect <template.pptx> [--json] [--out FILE]
    python template_adapter.py theme   <template.pptx> [--name NAME]    # THEMES-entry draft + contrast report

API
    inspect_template(path) -> dict                      slide size, theme colours/fonts, layouts, placeholders
    theme_from_template(path) -> dict                   journal-ppt Theme-shaped palette + contrast report
    TemplateDeck(path, keep_originals=False)
        .layouts / .roles()                             what the template offers
        .add(layout_or_role, title=, subtitle=, body=, picture=, notes=, ...) -> slide
        .save(path)

Rules enforced by TemplateDeck.add (TemplateError is a StyleError, raised before anything is written):
  * text that does not fit its placeholder at the template's own font size is an error, never a
    silent overflow (optional min_scale lets the size shrink in explicit steps);
  * a picture is never stretched: it is cropped to the placeholder (fit="cover", refused when more
    than max_crop of either side would be lost) or placed whole (fit="contain");
  * speaker notes are required: >= 100 chars and Korean (QC-10);
  * placeholders that received nothing are removed, so no "Click to add ..." prompt survives;
  * the template's own example slides are dropped (keep_originals=False) through the slide id
    list, relationships and section list, so the package stays valid.

License note: templates stay outside the repository; nothing from a template is copied here.
"""
from __future__ import annotations

import argparse
import colorsys
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lxml import etree  # noqa: E402
from pptx import Presentation  # noqa: E402
from pptx.enum.shapes import PP_PLACEHOLDER  # noqa: E402
from pptx.oxml.ns import qn  # noqa: E402
from pptx.util import Pt  # noqa: E402

try:                                     # same error class as Deck, when importable
    from deck_builder import StyleError
except Exception:                        # pragma: no cover - deck_builder unavailable
    class StyleError(ValueError):
        """Hard rejection of an off-spec request."""

from qc_layout import text_width_pt, contrast_ratio, luminance  # noqa: E402

EMU_IN = 914400.0
REF_W_IN, REF_H_IN = 13.333, 7.5
LINE_FACTOR = 1.2                  # Arial-like single-line pitch, same as qc_layout
FIT_TOL_IN = 0.02
MIN_NOTES_CHARS = 100
HANGUL_RE = re.compile(r"[가-힣㄰-㆏]")
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
P14_NS = "http://schemas.microsoft.com/office/powerpoint/2010/main"
SECTION_EXT_URI = "{521415D9-36F7-43E2-AB2F-B90AF26B5E84}"


class TemplateError(StyleError):
    """A request the template cannot satisfy honestly (no fit, no slot, bad picture, no notes)."""


# --------------------------------------------------------------------------- theme XML ---
def _master_theme_root(prs):
    master = prs.slide_masters[0]
    for rel in master.part.rels.values():
        if rel.reltype.endswith("/theme"):
            return etree.fromstring(rel.target_part.blob)
    return None


def theme_colors(prs) -> dict:
    """{dk1, lt1, dk2, lt2, accent1..6, hlink, folHlink} -> 'RRGGBB' from the first master's theme."""
    root = _master_theme_root(prs)
    out: dict = {}
    if root is None:
        return out
    cs = root.find(".//{%s}clrScheme" % A_NS)
    for el in (cs if cs is not None else []):
        ch = el[0]
        val = ch.get("val") if etree.QName(ch).localname == "srgbClr" else ch.get("lastClr")
        if val:
            out[etree.QName(el).localname] = val.upper()
    return out


def theme_fonts(prs) -> dict:
    """{'major': name, 'minor': name} (latin face; east-asian face when the latin one is empty)."""
    root = _master_theme_root(prs)
    out = {"major": "Arial", "minor": "Arial"}
    if root is None:
        return out
    fs = root.find(".//{%s}fontScheme" % A_NS)
    if fs is None:
        return out
    for key, tag in (("major", "majorFont"), ("minor", "minorFont")):
        f = fs.find("{%s}%s" % (A_NS, tag))
        if f is None:
            continue
        lat = f.find("{%s}latin" % A_NS)
        ea = f.find("{%s}ea" % A_NS)
        name = (lat.get("typeface") if lat is not None else "") or (ea.get("typeface") if ea is not None else "")
        if name:
            out[key] = name
    return out


def _clr_map(prs) -> dict:
    cm = prs.slide_masters[0]._element.find(qn("p:clrMap"))
    base = {"bg1": "lt1", "tx1": "dk1", "bg2": "lt2", "tx2": "dk2"}
    if cm is not None:
        for k in ("bg1", "tx1", "bg2", "tx2"):
            if cm.get(k):
                base[k] = cm.get(k)
    return base


def _hex_to_rgb(h: str):
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb) -> str:
    return "".join(f"{max(0, min(255, int(round(c)))):02X}" for c in rgb)


def _blend(a: str, b: str, t: float) -> str:
    """a moved fraction t toward b."""
    ra, rb = _hex_to_rgb(a), _hex_to_rgb(b)
    return _rgb_to_hex([x + (y - x) * t for x, y in zip(ra, rb)])


def _resolve_clr(holder, colors: dict, clrmap: dict) -> str | None:
    """Color of a solidFill-like element: srgbClr, sysClr, schemeClr (with clrMap, lumMod, lumOff)."""
    if holder is None or not len(holder):
        return None
    ch = holder[0]
    tag = etree.QName(ch).localname
    if tag == "srgbClr":
        base = ch.get("val", "").upper()
    elif tag == "sysClr":
        base = (ch.get("lastClr") or "").upper()
    elif tag == "schemeClr":
        name = ch.get("val")
        name = clrmap.get(name, name)
        base = colors.get(name, "")
    else:
        return None
    if len(base) != 6:
        return None
    mod = off = None
    for m in ch:
        t = etree.QName(m).localname
        if t == "lumMod":
            mod = int(m.get("val")) / 100000.0
        elif t == "lumOff":
            off = int(m.get("val")) / 100000.0
    if mod is not None or off is not None:
        r, g, b = [c / 255.0 for c in _hex_to_rgb(base)]
        h, l, s = colorsys.rgb_to_hls(r, g, b)
        l = max(0.0, min(1.0, l * (mod if mod is not None else 1.0) + (off or 0.0)))
        base = _rgb_to_hex([c * 255 for c in colorsys.hls_to_rgb(h, l, s)])
    return base


def master_background(prs) -> str:
    """Background color of the first master (solid fill or bgRef), else the mapped light color."""
    colors, cmap = theme_colors(prs), _clr_map(prs)
    bg = prs.slide_masters[0]._element.find(qn("p:cSld")).find(qn("p:bg"))
    if bg is not None:
        bgpr = bg.find(qn("p:bgPr"))
        if bgpr is not None:
            c = _resolve_clr(bgpr.find(qn("a:solidFill")), colors, cmap)
            if c:
                return c
        ref = bg.find(qn("p:bgRef"))
        if ref is not None:
            c = _resolve_clr(ref, colors, cmap)
            if c:
                return c
    return colors.get(cmap.get("bg1", "lt1"), "FFFFFF")


# --------------------------------------------------------------------------- placeholders ---
_KIND = {
    PP_PLACEHOLDER.TITLE: "title", PP_PLACEHOLDER.CENTER_TITLE: "title", PP_PLACEHOLDER.VERTICAL_TITLE: "title",
    PP_PLACEHOLDER.SUBTITLE: "subtitle",
    PP_PLACEHOLDER.BODY: "body", PP_PLACEHOLDER.OBJECT: "body", PP_PLACEHOLDER.VERTICAL_BODY: "body",
    PP_PLACEHOLDER.VERTICAL_OBJECT: "body",
    PP_PLACEHOLDER.PICTURE: "picture", PP_PLACEHOLDER.BITMAP: "picture",
    PP_PLACEHOLDER.CHART: "chart", PP_PLACEHOLDER.TABLE: "table", PP_PLACEHOLDER.MEDIA_CLIP: "media",
    PP_PLACEHOLDER.FOOTER: "footer", PP_PLACEHOLDER.DATE: "date", PP_PLACEHOLDER.SLIDE_NUMBER: "number",
    PP_PLACEHOLDER.HEADER: "footer",
}
CHROME_KINDS = ("footer", "date", "number")      # never filled, never cloned onto slides
TEXT_KINDS = ("title", "subtitle", "body")


def _ph_type(ph):
    try:
        return ph.placeholder_format.type
    except Exception:
        return None


def ph_kind(ph) -> str:
    return _KIND.get(_ph_type(ph), "other")


@dataclass
class TextStyle:
    size: float = 18.0
    bold: bool = False
    family: str = "arial"
    caps: bool = False
    line_mult: float = 1.0           # lnSpc percentage / 100
    space_before: float = 0.0        # pt
    margin_left: float = 0.0         # pt (text indent of this level incl. bullet hang)
    indent: float = 0.0              # pt (first-line indent, negative = hanging bullet)
    algn: str = "l"
    has_marl: bool = False           # marL defined somewhere in the chain (then it is written explicitly)
    has_indent: bool = False


def _chain(ph):
    """The placeholder element and its base placeholders (layout -> master)."""
    els, cur = [], ph
    for _ in range(3):
        if cur is None:
            break
        els.append(cur._element)
        cur = getattr(cur, "_base_placeholder", None)
    return els


def _lvl_nodes(sp_els, master, kind: str, level: int):
    tag = "a:lvl%dpPr" % (level + 1)
    for el in sp_els:
        tx = el.find(qn("p:txBody"))
        ls = tx.find(qn("a:lstStyle")) if tx is not None else None
        n = ls.find(qn(tag)) if ls is not None else None
        if n is not None:
            yield n
    ts = master._element.find(qn("p:txStyles"))
    if ts is not None:
        sty = {"title": "p:titleStyle", "subtitle": "p:bodyStyle", "body": "p:bodyStyle"}.get(kind, "p:otherStyle")
        node = ts.find(qn(sty))
        n = node.find(qn(tag)) if node is not None else None
        if n is not None:
            yield n


def resolve_text_style(ph, master, theme_fonts_: dict, level: int = 0) -> TextStyle:
    """Font size / bold / face / caps / line and paragraph spacing a layout placeholder gives its text."""
    kind = ph_kind(ph)
    nodes = list(_lvl_nodes(_chain(ph), master, kind, level))
    st = TextStyle()
    got_size = False
    for n in nodes:
        d = n.find(qn("a:defRPr"))
        if d is not None:
            if not got_size and d.get("sz"):
                st.size, got_size = int(d.get("sz")) / 100.0, True
            if d.get("cap") == "all":
                st.caps = True
    for n in nodes:                                     # first node that defines each property wins
        d = n.find(qn("a:defRPr"))
        if d is not None and d.get("b") is not None:
            st.bold = d.get("b") in ("1", "true")
            break
    for n in nodes:
        d = n.find(qn("a:defRPr"))
        lat = d.find(qn("a:latin")) if d is not None else None
        if lat is not None and lat.get("typeface"):
            tf = lat.get("typeface")
            st.family = (theme_fonts_.get("major" if tf == "+mj-lt" else "minor", "Arial") if tf.startswith("+") else tf).lower()
            break
    else:
        st.family = theme_fonts_.get("major" if kind == "title" else "minor", "Arial").lower()
    for n in nodes:
        ln = n.find(qn("a:lnSpc"))
        pct = ln.find(qn("a:spcPct")) if ln is not None else None
        if pct is not None:
            st.line_mult = int(pct.get("val")) / 100000.0
            break
    for n in nodes:
        sb = n.find(qn("a:spcBef"))
        if sb is not None:
            pts, pct = sb.find(qn("a:spcPts")), sb.find(qn("a:spcPct"))
            if pts is not None:
                st.space_before = int(pts.get("val")) / 100.0
            elif pct is not None:
                st.space_before = int(pct.get("val")) / 100000.0 * st.size
            break
    for n in nodes:
        if n.get("marL") is not None:
            st.margin_left, st.has_marl = int(n.get("marL")) / 12700.0, True
            break
    for n in nodes:
        if n.get("indent") is not None:
            st.indent, st.has_indent = int(n.get("indent")) / 12700.0, True
            break
    for n in nodes:
        if n.get("algn"):
            st.algn = n.get("algn")
            break
    return st


def _body_attrs(ph) -> dict:
    """bodyPr insets (EMU, defaults 0.1/0.05 in) and anchor, searched master -> layout (layout overrides)."""
    vals = {"lIns": 91440, "tIns": 45720, "rIns": 91440, "bIns": 45720}
    anchor = "t"
    for el in reversed(_chain(ph)):
        tx = el.find(qn("p:txBody"))
        bp = tx.find(qn("a:bodyPr")) if tx is not None else None
        if bp is not None:
            for k in vals:
                if bp.get(k) is not None:
                    vals[k] = int(bp.get(k))
            if bp.get("anchor"):
                anchor = bp.get("anchor")
    return {**vals, "anchor": anchor}


def _body_insets_in(ph) -> tuple:
    """(left, top, right, bottom) text insets in inches, searched layout -> master, default 0.1/0.05."""
    v = _body_attrs(ph)
    return tuple(v[k] / EMU_IN for k in ("lIns", "tIns", "rIns", "bIns"))


# --- inherited text color vs background ---------------------------------------------------
# qc_layout only sees colors written on the slide's own runs. A template can color a level white
# (bg1) on a white slide, so the adapter resolves the inherited color itself.
def _layout_clr_map(lay, base: dict) -> dict:
    ov = lay._element.find(qn("p:clrMapOvr"))
    o = ov.find(qn("a:overrideClrMapping")) if ov is not None else None
    if o is None:
        return base
    out = dict(base)
    for k in ("bg1", "tx1", "bg2", "tx2"):
        if o.get(k):
            out[k] = o.get(k)
    return out


def resolve_text_color(ph, master, level: int, colors: dict, clrmap: dict):
    """Hex color the template gives text of `level` in this placeholder, or None when it cannot be resolved."""
    for n in _lvl_nodes(_chain(ph), master, ph_kind(ph), level):
        d = n.find(qn("a:defRPr"))
        sf = d.find(qn("a:solidFill")) if d is not None else None
        if sf is not None:
            return _resolve_clr(sf, colors, clrmap)
    return None


def background_under(lay, ph, colors: dict, base_map: dict):
    """Color behind a layout placeholder: its own fill, the topmost filled layout/master shape that
    contains its center, else the layout/master background. None = unknown (e.g. a picture behind)."""
    clrmap = _layout_clr_map(lay, base_map)
    for el in _chain(ph):
        sppr = el.find(qn("p:spPr"))
        sf = sppr.find(qn("a:solidFill")) if sppr is not None else None
        if sf is not None:
            return _resolve_clr(sf, colors, clrmap)
    cx, cy = ph.left + ph.width / 2, ph.top + ph.height / 2
    found, seen = None, False
    for src in (lay.slide_master.shapes, lay.shapes):
        for sh in src:
            if sh.left is None or sh.width is None:
                continue
            if sh.is_placeholder and (sh.placeholder_format.idx == ph.placeholder_format.idx or src is not lay.shapes):
                continue
            if not (sh.left <= cx <= sh.left + sh.width and sh.top <= cy <= sh.top + sh.height):
                continue
            tag = etree.QName(sh._element).localname
            if tag == "pic":
                found, seen = None, True
                continue
            sppr = sh._element.find(qn("p:spPr"))
            sf = sppr.find(qn("a:solidFill")) if sppr is not None else None
            if sf is None and sh.is_placeholder:             # another placeholder's inherited fill
                for el in _chain(sh):
                    sp2 = el.find(qn("p:spPr"))
                    sf = sp2.find(qn("a:solidFill")) if sp2 is not None else None
                    if sf is not None:
                        break
            if sf is not None:
                found, seen = _resolve_clr(sf, colors, clrmap), True
            elif sppr is not None and (sppr.find(qn("a:gradFill")) is not None or sppr.find(qn("a:blipFill")) is not None):
                found, seen = None, True
    if seen:
        return found
    for part in (lay, lay.slide_master):
        bg = part._element.find(qn("p:cSld")).find(qn("p:bg"))
        if bg is None:
            continue
        bgpr = bg.find(qn("p:bgPr"))
        if bgpr is not None:
            if bgpr.find(qn("a:solidFill")) is not None:
                return _resolve_clr(bgpr.find(qn("a:solidFill")), colors, clrmap)
            return None
        ref = bg.find(qn("p:bgRef"))
        if ref is not None:
            return _resolve_clr(ref, colors, clrmap)
    return _resolve_clr(etree.fromstring('<a:solidFill xmlns:a="%s"><a:schemeClr val="bg1"/></a:solidFill>' % A_NS), colors, clrmap)


# --- text fitting ---------------------------------------------------------------------------
_SAMPLE = "the enzymatic cascade raised yield and titer under pH 7.5 at 30 C with NADPH recycling "


def _width(text: str, st: TextStyle, size: float) -> float:
    if st.caps:
        text = text.upper()
    w = text_width_pt(text, st.family, st.bold, size)
    # faces we cannot measure fall back to Arial metrics: keep a safety margin
    known = st.family in ("arial", "calibri", "times new roman", "malgun gothic")
    return w * (1.0 if known else 1.07)


def wrapped_lines(text: str, avail_pt: float, st: TextStyle, size: float) -> int:
    lines, cur = 0, 0.0
    space = _width(" ", st, size)
    for word in text.split():
        w = _width(word, st, size)
        if cur > 0 and cur + space + w > avail_pt:
            lines += 1
            cur = 0.0
        while w > avail_pt:                       # over-long token: hard break
            lines += 1
            w -= avail_pt
        cur = (cur + space if cur > 0 else 0.0) + w
    return lines + (1 if cur > 0 or lines == 0 else 0)


def text_height_in(paras, style_of, inner_w_in: float, scale: float = 1.0) -> float:
    """Estimated height (in) of [(level, text), ...] given style_of(level) -> TextStyle."""
    total = 0.0
    for i, (lvl, text) in enumerate(paras):
        st = style_of(lvl)
        size = st.size * scale
        avail = inner_w_in * 72.0 - st.margin_left
        n = wrapped_lines(text, avail, st, size)
        total += n * size * LINE_FACTOR * st.line_mult
        if i > 0:
            total += st.space_before * scale
    return total / 72.0


INK_COLLIDE_IN = 0.06


def text_ink_in(slot, paras, scale: float = 1.0) -> tuple:
    """(left, top, right, bottom) in inches of the area the text will actually occupy in `slot`."""
    st0 = slot.style(0)
    l, t, r, b = _body_insets_in(slot._shape)
    inner_w = max(slot.width_in - l - r, 0.05)
    widest = 0.0
    for lvl, text in paras:
        st = slot.style(lvl)
        w = (_width(text, st, st.size * scale) + st.margin_left) / 72.0
        widest = max(widest, min(w, inner_w))
    h = text_height_in(paras, slot.style, slot.inner_width_in(), scale)
    x0 = slot.left_in + l
    x_l = x0 + (inner_w - widest) / 2 if st0.algn == "ctr" else (x0 + inner_w - widest if st0.algn == "r" else x0)
    avail = slot.height_in - t - b
    anchor = _body_attrs(slot._shape)["anchor"]
    y_t = slot.top_in + t + ((avail - h) / 2 if anchor == "ctr" else (avail - h if anchor == "b" else 0.0))
    return (x_l, y_t, x_l + widest, y_t + h)


@dataclass
class PlaceholderInfo:
    idx: int
    type: str
    kind: str
    name: str
    left_pct: float
    top_pct: float
    width_pct: float
    height_pct: float
    left_in: float
    top_in: float
    width_in: float
    height_in: float
    font_pt: float | None = None
    capacity_chars: int | None = None
    capacity_lines: int | None = None
    chars_per_line: int | None = None
    _shape: object = field(default=None, repr=False, compare=False)
    _master: object = field(default=None, repr=False, compare=False)
    _fonts: dict = field(default=None, repr=False, compare=False)

    def style(self, level: int = 0) -> TextStyle:
        return resolve_text_style(self._shape, self._master, self._fonts, level)

    def inner_width_in(self) -> float:
        l, _, r, _ = _body_insets_in(self._shape)
        return max(self.width_in - l - r, 0.05)

    def inner_height_in(self) -> float:
        _, t, _, b = _body_insets_in(self._shape)
        return max(self.height_in - t - b, 0.05)

    def public(self) -> dict:
        return {k: v for k, v in asdict(self).items() if not k.startswith("_")}


def _capacity(info: PlaceholderInfo):
    st = info.style(0)
    info.font_pt = st.size
    avg = _width(_SAMPLE, st, st.size) / len(_SAMPLE)
    cpl = max(int((info.inner_width_in() * 72.0 - st.margin_left) / max(avg, 0.1)), 1)
    pitch = st.size * LINE_FACTOR * st.line_mult / 72.0
    lines = max(int((info.inner_height_in() + FIT_TOL_IN) / pitch), 0)
    info.chars_per_line, info.capacity_lines, info.capacity_chars = cpl, lines, int(cpl * lines * 0.92)


@dataclass
class LayoutInfo:
    index: int
    name: str
    role: str
    role_reason: str
    placeholders: list
    warnings: list = field(default_factory=list)
    sample_content: bool = False        # layout itself carries a sample chart/table or a fixed page number
    _layout: object = field(default=None, repr=False, compare=False)

    def slots(self, *kinds):
        return [p for p in self.placeholders if p.kind in kinds]

    def public(self) -> dict:
        return {"index": self.index, "name": self.name, "role": self.role, "role_reason": self.role_reason,
                "warnings": self.warnings, "sample_content": self.sample_content,
                "placeholders": [p.public() for p in self.placeholders]}


# --- role guessing ----------------------------------------------------------------------------
_CLOSING_RE = re.compile(r"thank|closing|\bend\b|q\s*&\s*a|question|acknowledg|contact|goodbye|summary and|"
                         r"\u8c22\u8c22|\u611f\u8c22|\u81f4\u8c22|danke|tack|schluss", re.I)
_TITLE_RE = re.compile(r"title slide|cover|titelfolie|opening|front page|\u6807\u9898\u5e7b\u706f\u7247|^title$|^intro slide", re.I)
_SECTION_RE = re.compile(r"section|divider|chapter|trennfolie|\u8282\u6807\u9898|\bpart\b|agenda|outline|break|big (title|number)", re.I)
_BLANK_RE = re.compile(r"blank|\u7a7a\u767d|leer", re.I)


def guess_role(name: str, phs: list, sw_in: float, sh_in: float) -> tuple[str, str]:
    content = [p for p in phs if p.kind not in CHROME_KINDS]
    kinds = [p.kind for p in content]
    has_title = "title" in kinds
    bodies = [p for p in content if p.kind == "body"]
    pics = [p for p in content if p.kind == "picture"]
    subs = [p for p in content if p.kind == "subtitle"]
    data = [p for p in content if p.kind in ("chart", "table", "media")]
    titles = [p for p in content if p.kind == "title"]
    centre_y = (titles[0].top_pct + titles[0].height_pct / 2) / 100.0 if titles else 0.0
    is_center_title = bool(titles) and _ph_type(titles[0]._shape) == PP_PLACEHOLDER.CENTER_TITLE
    if not content:
        return "blank", "no content placeholders"
    if any(_ph_type(p._shape) in (PP_PLACEHOLDER.VERTICAL_TITLE, PP_PLACEHOLDER.VERTICAL_BODY,
                                  PP_PLACEHOLDER.VERTICAL_OBJECT) for p in content) or "vert" in name.lower():
        return "vertical", "vertical-text placeholder (not filled by role)"
    if _BLANK_RE.search(name) and not has_title:
        return "blank", "name says blank"
    if _CLOSING_RE.search(name):
        return "closing", f"name matches closing hint '{name}'"
    if _TITLE_RE.search(name) and not re.search(r"content|only|and", name, re.I):
        return "title", f"name matches title hint '{name}'"
    if _SECTION_RE.search(name) and not pics:
        return "section", f"name matches section hint '{name}'"
    if is_center_title and (subs or len(bodies) <= 1):
        return "title", "center-title placeholder"
    if pics:
        return ("picture_text", "picture + text placeholders") if (bodies or subs) else ("picture", "picture placeholder only")
    if data and not bodies:
        return "data", "chart/table/media placeholder"
    if has_title and not bodies and not subs:
        return ("section", f"title-only layout with title at {centre_y:.0%} height") if centre_y > 0.28 \
            else ("title_only", "title-only layout, title near the top")
    if has_title and centre_y > 0.30 and (subs or (len(bodies) == 1 and bodies[0].height_pct < 35)):
        return "section", f"title at {centre_y:.0%} height + small text slot"
    if len(bodies) >= 3:
        return "multi_content", f"{len(bodies)} body placeholders"
    if len(bodies) == 2:
        return "two_content", "2 body placeholders"
    if len(bodies) == 1 or subs:
        big = (bodies or subs)[0]
        return ("content", f"title + one body ({big.width_pct:.0f}% x {big.height_pct:.0f}%)") if big.height_pct >= 35 \
            else ("section", "title + one small text slot")
    return "other", "no rule matched"


def _to_slide_number_field(sh):
    """Replace the runs of a typed page-number shape by a slide-number field."""
    for r in list(sh.text_frame._txBody.iter(qn("a:r"))):
        fld = etree.Element(qn("a:fld"))
        fld.set("id", "{B6F15528-21DE-4FAA-801E-634DDDAF4B2B}")
        fld.set("type", "slidenum")
        rpr = r.find(qn("a:rPr"))
        if rpr is not None:
            fld.append(rpr)
        etree.SubElement(fld, qn("a:t")).text = "‹#›"
        r.getparent().replace(r, fld)


PAGE_NO_RE = re.compile(r"[#\d./ -]{1,6}")


def repair_static_page_numbers(prs) -> list:
    """Layouts of some templates draw a typed page number ('007') on every slide. Replace such a run by a
    slide-number field, so each slide shows its own number. Works on the in-memory copy only."""
    fixed = []
    for lay in prs.slide_layouts:
        for sh in lay.shapes:
            if sh.is_placeholder or not getattr(sh, "has_text_frame", False) or not sh.has_text_frame:
                continue
            txt = sh.text_frame.text.strip()
            if not txt or not PAGE_NO_RE.fullmatch(txt) or _is_field_only(sh):
                continue
            _to_slide_number_field(sh)
            fixed.append(f"{lay.name}:{sh.name}:{txt}")
    return fixed


def _layout_warnings(lay) -> tuple:
    """Non-placeholder content a layout draws on EVERY slide that uses it: sample charts/tables and
    fixed text. A sample chart or a fixed page number ('007') cannot be removed from the slide."""
    warns, sample = [], False
    for sh in lay.shapes:
        if sh.is_placeholder:
            continue
        el = sh._element
        if etree.QName(el).localname == "graphicFrame":
            if el.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/chart}chart"):
                warns.append(f"sample chart '{sh.name}' is drawn by the layout")
                sample = True
            elif getattr(sh, "has_table", False) and sh.has_table:
                warns.append(f"sample table '{sh.name}' is drawn by the layout")
                sample = True
        elif etree.QName(el).localname == "pic":
            area = (sh.width or 0) * (sh.height or 0) / float(lay.part.package.presentation_part.presentation.slide_width
                                                              * lay.part.package.presentation_part.presentation.slide_height)
            if area > 0.08:
                warns.append(f"picture '{sh.name}' ({area:.0%} of the slide) is drawn by the layout on every slide")
        elif getattr(sh, "has_text_frame", False) and sh.has_text_frame and sh.text_frame.text.strip():
            txt = sh.text_frame.text.strip()
            if _is_field_only(sh):
                continue
            if PAGE_NO_RE.fullmatch(txt):
                warns.append(f"fixed page-number-like text {txt!r} is drawn by the layout "
                             f"(TemplateDeck turns it into a slide-number field)")
            else:
                warns.append(f"fixed text {txt[:30]!r} is drawn by the layout")
    return warns, sample


def _layout_infos(prs) -> list[LayoutInfo]:
    sw, sh = prs.slide_width, prs.slide_height
    fonts = theme_fonts(prs)
    out = []
    for i, lay in enumerate(prs.slide_layouts):
        master = lay.slide_master
        phs = []
        for ph in lay.placeholders:
            try:
                l, t, w, h = ph.left, ph.top, ph.width, ph.height
            except Exception:
                continue
            if None in (l, t, w, h):
                continue
            ty = _ph_type(ph)
            info = PlaceholderInfo(
                idx=ph.placeholder_format.idx, type=str(ty).split(".")[-1].split(" ")[0] if ty is not None else "NONE",
                kind=_KIND.get(ty, "other"), name=ph.name,
                left_pct=round(l / sw * 100, 1), top_pct=round(t / sh * 100, 1),
                width_pct=round(w / sw * 100, 1), height_pct=round(h / sh * 100, 1),
                left_in=round(l / EMU_IN, 3), top_in=round(t / EMU_IN, 3),
                width_in=round(w / EMU_IN, 3), height_in=round(h / EMU_IN, 3),
                _shape=ph, _master=master, _fonts=fonts)
            if info.kind in TEXT_KINDS:
                _capacity(info)
            phs.append(info)
        role, why = guess_role(lay.name, phs, sw / EMU_IN, sh / EMU_IN)
        warns, sample = _layout_warnings(lay)
        out.append(LayoutInfo(i, lay.name, role, why, phs, warns, sample, lay))
    return out


def inspect_template(path) -> dict:
    prs = Presentation(str(path))
    sw, sh = prs.slide_width / EMU_IN, prs.slide_height / EMU_IN
    return {
        "file": Path(path).name,
        "slide_width_in": round(sw, 3), "slide_height_in": round(sh, 3),
        "scale_vs_reference": {"x": round(sw / REF_W_IN, 3), "y": round(sh / REF_H_IN, 3)},
        "n_example_slides": len(prs.slides),
        "theme_colors": theme_colors(prs), "theme_fonts": theme_fonts(prs),
        "background": master_background(prs),
        "layouts": [li.public() for li in _layout_infos(prs)],
        "examples": [{"slide": n, "layout": sl.slide_layout.name,
                      "text_shapes": [example_shape_info(x, i) for i, x in enumerate(example_text_shapes(sl))]}
                     for n, sl in enumerate(prs.slides, 1)],
    }


def format_inspection(d: dict) -> str:
    out = [f"{d['file']}: {d['slide_width_in']} x {d['slide_height_in']} in "
           f"(x{d['scale_vs_reference']['x']} w, x{d['scale_vs_reference']['y']} h vs 13.333 x 7.5), "
           f"{d['n_example_slides']} example slides, background #{d['background']}",
           "fonts: major={major} | minor={minor}".format(**d["theme_fonts"]),
           "colors: " + " ".join(f"{k}={v}" for k, v in d["theme_colors"].items())]
    for lay in d["layouts"]:
        out.append(f"[{lay['index']:>2}] {lay['name']!r:38s} role={lay['role']:13s} ({lay['role_reason']})")
        for w in lay.get("warnings", []):
            out.append(f"       ! {w}")
        for p in lay["placeholders"]:
            cap = (f" {p['font_pt']:g}pt ~{p['capacity_chars']} chars ({p['chars_per_line']}/line x "
                   f"{p['capacity_lines']} lines)") if p["capacity_chars"] is not None else ""
            out.append(f"       idx{p['idx']:<3} {p['kind']:8s} {p['type']:14s} "
                       f"x{p['left_pct']:>5.1f}% y{p['top_pct']:>5.1f}% w{p['width_pct']:>5.1f}% h{p['height_pct']:>5.1f}%{cap}")
    n_ph = sum(1 for lay in d["layouts"] if lay["role"] not in ("blank", "other", "vertical"))
    out.append(f"-- {n_ph}/{len(d['layouts'])} layouts carry content placeholders; "
               f"{len(d['examples'])} example slides (pattern path: add_from_example):")
    for ex in d["examples"]:
        shp = "; ".join(f"{t['index']}:{t['name']}[{t['font_pt']:g}pt ~{t['capacity_chars']}] {t['text'][:24]!r}"
                        for t in ex["text_shapes"][:7])
        out.append(f"  ex{ex['slide']:>2} {ex['layout']!r}: {len(ex['text_shapes'])} text shapes  {shp}")
    return "\n".join(out)


# --------------------------------------------------------------------------- palette ---
def _best_text(bg: str, cands, need: float) -> str:
    ok = [c for c in cands if contrast_ratio(c, bg) >= need]
    if ok:
        return max(ok, key=lambda c: contrast_ratio(c, bg)) if need >= 7 else ok[0]
    return "FFFFFF" if contrast_ratio("FFFFFF", bg) >= contrast_ratio("000000", bg) else "000000"


def _ensure_contrast(fg: str, bg: str, need: float) -> str:
    """Move fg toward black or white (whichever helps) until it reaches `need` against bg."""
    target = "000000" if luminance(bg) > 0.4 else "FFFFFF"
    for step in range(0, 21):
        c = _blend(fg, target, step / 20.0)
        if contrast_ratio(c, bg) >= need:
            return c
    return target


def _chroma(h: str) -> float:
    r = _hex_to_rgb(h)
    return max(r) - min(r)


def theme_from_template(pptx_path) -> dict:
    """Palette for a journal-ppt THEMES entry, derived from the template's theme XML by luminance/contrast.

    Returns {name, description, header_style, bg, header_bg, rule_color, palette{...}, template_fonts,
    contrast_report[...], all_pass}. All colors are 'RRGGBB'. The text colors are pushed to WCAG
    thresholds (4.5:1 body/caption/footer, 7:1 headings) against the background they will sit on.
    """
    prs = Presentation(str(pptx_path))
    col, cmap = theme_colors(prs), _clr_map(prs)
    bg = master_background(prs)
    dark_bg = luminance(bg) < 0.3
    white, black = "FFFFFF", "000000"
    dk1, dk2 = col.get(cmap.get("tx1", "dk1"), black), col.get(cmap.get("tx2", "dk2"), black)
    accents = [col[k] for k in ("accent1", "accent2", "accent3", "accent4", "accent5", "accent6") if k in col]

    body = _best_text(bg, [dk1, dk2, white, black], 7.0)
    # accent: the most saturated theme accent that already reads on the background; else darken/lighten one
    readable = [a for a in accents if contrast_ratio(a, bg) >= 4.5]
    accent = max(readable, key=_chroma) if readable else _ensure_contrast(max(accents, key=_chroma) if accents else dk2, bg, 4.5)
    title_main = next((c for c in (accents[0] if accents else body, dk2, body) if contrast_ratio(c, bg) >= 7.0), body)
    subtitle = accent if contrast_ratio(accent, bg) >= 4.5 else body
    # header bar: a theme color that is dark on a light slide; on a dark slide a lifted version of the background
    if dark_bg:
        header_bg = _blend(bg, white, 0.08)
    else:
        dark_cands = [c for c in [dk2] + accents if luminance(c) < 0.22]
        header_bg = (max(dark_cands, key=_chroma) if dark_cands else None)
    header_style = "bar" if header_bg else "rule"
    bar = header_bg or _ensure_contrast(accent, white, 7.0)
    title_bar_text = _best_text(bar, [white, black], 4.5)
    highlight = _blend(accent, bg, 0.88)
    if contrast_ratio(body, highlight) < 7.0:
        highlight = _blend(accent, bg, 0.94)
    zebra = _blend(accent, bg, 0.93)
    warning = _blend("C0392B", bg, 0.88)
    grey = body
    for t in (0.42, 0.36, 0.30, 0.24, 0.18, 0.12, 0.06, 0.0):      # lightest gray that still passes on bg AND highlight
        g = _blend(body, bg, t)
        if contrast_ratio(g, bg) >= 4.5 and contrast_ratio(g, highlight) >= 4.5:
            grey = g
            break
    palette = dict(title_bar_text=title_bar_text, title_main=title_main, subtitle=subtitle, body=body,
                   caption=grey, footer=grey, accent=accent, stat=accent, highlight_bg=highlight,
                   warning_bg=warning, table_hdr_bg=bar, table_hdr_text=_best_text(bar, [white, black], 4.5),
                   zebra=zebra)
    pairs = [("body on bg", palette["body"], bg, 4.5), ("title_main on bg", title_main, bg, 4.5),
             ("subtitle on bg", subtitle, bg, 4.5), ("accent/stat on bg", accent, bg, 3.0),
             ("caption on bg", grey, bg, 4.5), ("footer on bg", grey, bg, 4.5),
             ("caption on highlight_bg", grey, highlight, 4.5), ("body on highlight_bg", body, highlight, 4.5),
             ("body on zebra", body, zebra, 4.5), ("body on warning_bg", body, warning, 4.5),
             ("title_bar_text on header", title_bar_text, bar, 4.5),
             ("table_hdr_text on table_hdr_bg", palette["table_hdr_text"], bar, 4.5)]
    report = [{"pair": n, "fg": f, "bg": b, "ratio": round(contrast_ratio(f, b), 2), "required": need,
               "pass": contrast_ratio(f, b) >= need} for n, f, b, need in pairs]
    name = Path(pptx_path).stem
    return {"name": name, "description": f"Derived from template {Path(pptx_path).name} (theme XML palette).",
            "header_style": header_style, "bg": bg, "header_bg": header_bg,
            "rule_color": accent if header_style == "rule" else None, "palette": palette,
            "template_fonts": theme_fonts(prs), "contrast_report": report,
            "all_pass": all(r["pass"] for r in report)}


def theme_entry_source(d: dict, name: str | None = None) -> str:
    """Source text of a deck_builder `_theme(...)` call for the dict above (paste into THEMES)."""
    p = d["palette"]
    nm = re.sub(r"[^a-z0-9_]+", "_", (name or d["name"]).lower()).strip("_")
    hb = f'"{d["header_bg"]}"' if d["header_bg"] else "None"
    rc = f', rule_color="{d["rule_color"]}"' if d["rule_color"] else ""
    keys = ["title_bar_text", "title_main", "subtitle", "body", "caption", "footer", "accent", "stat",
            "highlight_bg", "warning_bg", "table_hdr_bg", "table_hdr_text", "zebra"]
    pal = ",\n           ".join(", ".join(f'{k}="{p[k]}"' for k in keys[i:i + 3]) for i in range(0, len(keys), 3))
    return (f'_theme("{nm}", "{d["description"]}",\n           "{d["header_style"]}", "{d["bg"]}", {hb}{rc},\n'
            f"           {pal}),")


# --------------------------------------------------------------------------- example slides ---
# Many real templates (lab group-meeting decks, defense decks) keep their design in the EXAMPLE
# SLIDES, as free shapes on one plain layout, not in layout placeholders. add_from_example() clones
# such a slide as a pattern and replaces the text of named shapes, keeping every run/paragraph
# property of the original.
_SHAPE_TAGS = ("sp", "pic", "grpSp", "cxnSp", "graphicFrame")


def _walk(shapes):
    """Every shape incl. those inside groups, in document order."""
    for sh in shapes:
        yield sh
        if sh.shape_type is not None and sh.shape_type == 6:          # MSO_SHAPE_TYPE.GROUP
            yield from _walk(sh.shapes)


def _is_field_only(sh) -> bool:
    ps = sh.text_frame._txBody.findall(qn("a:p"))
    texty = [p for p in ps if p.find(qn("a:fld")) is not None or p.find(qn("a:r")) is not None]
    return bool(texty) and all(p.find(qn("a:r")) is None for p in texty)


def example_text_shapes(slide) -> list:
    """Text-bearing, non-field shapes of a slide (the ones add_from_example can fill), reading order."""
    out = []
    for sh in _walk(slide.shapes):
        if getattr(sh, "has_text_frame", False) and sh.has_text_frame and sh.text_frame.text.strip():
            if not _is_field_only(sh):
                out.append(sh)
    return sorted(out, key=lambda x: (round((x.top or 0) / 457200), x.left or 0))


def _proto_rpr(p_el):
    r = p_el.find(qn("a:r"))
    if r is not None and r.find(qn("a:rPr")) is not None:
        return r.find(qn("a:rPr"))
    return p_el.find(qn("a:endParaRPr"))


def _shape_size_pt(sh) -> float:
    for p in sh.text_frame._txBody.findall(qn("a:p")):
        rp = _proto_rpr(p)
        if rp is not None and rp.get("sz"):
            return int(rp.get("sz")) / 100.0
    return 18.0


def _shape_family(sh) -> tuple:
    for p in sh.text_frame._txBody.findall(qn("a:p")):
        rp = _proto_rpr(p)
        if rp is not None:
            lat = rp.find(qn("a:latin"))
            face = lat.get("typeface") if lat is not None else None
            fam = face if face and not face.startswith("+") else "arial"
            return fam.lower(), rp.get("b") in ("1", "true")
    return "arial", False


def _frame_insets_in(sh) -> tuple:
    bp = sh.text_frame._txBody.find(qn("a:bodyPr"))

    def g(k, d):
        return (int(bp.get(k)) if bp is not None and bp.get(k) is not None else d) / EMU_IN
    return g("lIns", 91440), g("tIns", 45720), g("rIns", 91440), g("bIns", 45720)


def example_shape_info(sh, idx: int) -> dict:
    size = _shape_size_pt(sh)
    fam, bold = _shape_family(sh)
    st = TextStyle(size=size, bold=bold, family=fam)
    w, h = (sh.width or 0) / EMU_IN, (sh.height or 0) / EMU_IN
    l, t, r, b = _frame_insets_in(sh)
    avg = _width(_SAMPLE, st, size) / len(_SAMPLE)
    cpl = max(int((w - l - r) * 72.0 / max(avg, 0.1)), 1)
    lines = max(int((h - t - b + FIT_TOL_IN) * 72.0 / (size * LINE_FACTOR)), 0)
    return {"index": idx, "name": sh.name, "text": sh.text_frame.text.strip()[:60], "font_pt": size,
            "left_in": round((sh.left or 0) / EMU_IN, 2), "top_in": round((sh.top or 0) / EMU_IN, 2),
            "width_in": round(w, 2), "height_in": round(h, 2), "capacity_chars": int(cpl * lines * 0.92),
            "chars_per_line": cpl, "capacity_lines": lines}


def fit_example_text(sh, texts: list, scale: float = 1.0, wide_in: float | None = None) -> str | None:
    """None if `texts` fit the shape at its own font size x scale, else a message saying how far it is off."""
    size = _shape_size_pt(sh) * scale
    fam, bold = _shape_family(sh)
    st = TextStyle(size=size, bold=bold, family=fam)
    l, t, r, b = _frame_insets_in(sh)
    w = (sh.width or 0) / EMU_IN - l - r
    ps = sh.text_frame._txBody.findall(qn("a:p"))
    ppr = ps[0].find(qn("a:pPr")) if ps else None
    ln = ppr.find(qn("a:lnSpc")) if ppr is not None else None
    pct = ln.find(qn("a:spcPct")) if ln is not None else None
    st.line_mult = int(pct.get("val")) / 100000.0 if pct is not None else 1.0
    bp = sh.text_frame._txBody.find(qn("a:bodyPr"))
    have = (sh.height or 0) / EMU_IN - t - b
    orig = [p.text for p in sh.text_frame.paragraphs if p.text.strip()] or [""]
    if bp is not None and bp.get("wrap") == "none":
        # no wrapping: every paragraph is one line and must not be wider than the box the sample text
        # filled (the decoration behind it was drawn to that width)
        widest = max(_width(x, st, size) for x in texts) / 72.0
        limit = wide_in if wide_in is not None else max(w, max(_width(x, st, _shape_size_pt(sh)) for x in orig) / 72.0)
        if widest > limit + FIT_TOL_IN:
            return f"needs {widest:.2f} in width at {size:g} pt, shape offers {limit:.2f} in"
        need = len(texts) * size * LINE_FACTOR * st.line_mult / 72.0
    else:
        need = text_height_in([(0, x) for x in texts], lambda _l: st, max(w, 0.05))
    # the space the template's own sample text occupied counts as available (stored shape heights go stale);
    # an auto-growing shape (spAutoFit) is otherwise held to its drawn size: growth would run into its neighbors
    st0 = TextStyle(size=_shape_size_pt(sh), bold=bold, family=fam, line_mult=st.line_mult)
    if bp is not None and bp.get("wrap") == "none":
        have = max(have, len(orig) * st0.size * LINE_FACTOR * st.line_mult / 72.0)
    else:
        have = max(have, text_height_in([(0, x) for x in orig], lambda _l: st0, max(w, 0.05)))
    if need > have + FIT_TOL_IN:
        return f"needs {need:.2f} in of {size:g} pt text, shape offers {have:.2f} in"
    return None


def fit_example_scale(sh, texts: list, min_scale: float, min_pt: float, wide_in: float | None = None):
    """(scale, None) for the largest font scale in [min_scale, 1] (5 % steps, never below min_pt) at which
    the text fits, else (None, message for the unscaled text)."""
    base = _shape_size_pt(sh)
    n = int(round((1.0 - min_scale) / 0.05))
    for k in range(n + 1):
        sc = round(1.0 - 0.05 * k, 2)
        if k and base * sc < min_pt:
            break
        if fit_example_text(sh, texts, sc, wide_in) is None:
            return sc, None
    return None, fit_example_text(sh, texts, 1.0, wide_in)


def example_ink_in(sh) -> tuple:
    """(left, top, right, bottom) in inches the current text of a free text shape occupies."""
    size = _shape_size_pt(sh)
    fam, bold = _shape_family(sh)
    st = TextStyle(size=size, bold=bold, family=fam)
    l, t, r, b = _frame_insets_in(sh)
    inner_w = max((sh.width or 0) / EMU_IN - l - r, 0.05)
    paras = [(0, p.text) for p in sh.text_frame.paragraphs if p.text.strip()] or [(0, "")]
    bp = sh.text_frame._txBody.find(qn("a:bodyPr"))
    nowrap = bp is not None and bp.get("wrap") == "none"
    widest = max(_width(x, st, size) for _, x in paras) / 72.0
    w = widest if nowrap else min(widest, inner_w)
    h = (len(paras) * size * LINE_FACTOR / 72.0) if nowrap else text_height_in(paras, lambda _l: st, inner_w)
    ps = sh.text_frame._txBody.findall(qn("a:p"))
    ppr = ps[0].find(qn("a:pPr")) if ps else None
    algn = (ppr.get("algn") if ppr is not None else None) or "l"
    left, width = (sh.left or 0) / EMU_IN, (sh.width or 0) / EMU_IN
    x0 = left + l
    x_l = left + (width - w) / 2 if algn == "ctr" else (left + width - r - w if algn == "r" else x0)
    anchor = (bp.get("anchor") if bp is not None else None) or "t"
    avail = (sh.height or 0) / EMU_IN - t - b
    top = (sh.top or 0) / EMU_IN + t
    y_t = top + ((avail - h) / 2 if anchor == "ctr" else (avail - h if anchor == "b" else 0.0))
    return (x_l, y_t, x_l + w, y_t + h)


def _rebuild_paragraphs(sh, texts: list, scale: float = 1.0):
    import copy
    tx = sh.text_frame._txBody
    old = tx.findall(qn("a:p"))
    protos = [p for p in old if p.find(qn("a:r")) is not None] or old
    for p in old:
        tx.remove(p)
    for j, text in enumerate(texts):
        proto = protos[min(j, len(protos) - 1)]
        p = etree.SubElement(tx, qn("a:p"))
        ppr = proto.find(qn("a:pPr"))
        if ppr is not None:
            p.append(copy.deepcopy(ppr))
        r = etree.SubElement(p, qn("a:r"))
        rp = _proto_rpr(proto)
        if rp is not None:
            node = copy.deepcopy(rp)
            node.tag = qn("a:rPr")
            if scale != 1.0:
                base = int(node.get("sz")) / 100.0 if node.get("sz") else 18.0
                node.set("sz", str(int(round(base * scale * 100))))
            r.append(node)
        elif scale != 1.0:
            etree.SubElement(r, qn("a:rPr")).set("sz", str(int(round(1800 * scale))))
        etree.SubElement(r, qn("a:t")).text = text


def _clone_into(new_slide, src_slide):
    """Deep-copy the shapes of src_slide into new_slide, re-pointing relationships (images, links)."""
    import copy
    rns = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    tree = new_slide.shapes._spTree
    for el in list(tree):
        if etree.QName(el).localname in _SHAPE_TAGS:
            tree.remove(el)
    bg = src_slide._element.find(qn("p:cSld")).find(qn("p:bg"))
    if bg is not None:
        csld = new_slide._element.find(qn("p:cSld"))
        old = csld.find(qn("p:bg"))
        if old is not None:
            csld.remove(old)
        csld.insert(0, copy.deepcopy(bg))
    remap = {}
    for el in src_slide.shapes._spTree:
        if etree.QName(el).localname not in _SHAPE_TAGS:
            continue
        if el.tag == qn("p:graphicFrame") and (
                el.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/chart}chart") or
                el.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/diagram}relIds")):
            raise TemplateError("example slide contains a chart/diagram graphic frame: cannot be cloned safely")
        new_el = copy.deepcopy(el)
        for h in list(new_el.iter(qn("a:hlinkClick"), qn("a:hlinkHover"))):
            h.getparent().remove(h)                    # internal jumps would point at removed slides
        for node in new_el.iter():
            for att in list(node.attrib):
                if att.startswith(rns):
                    rid = node.get(att)
                    if rid not in remap:
                        rel = src_slide.part.rels[rid]
                        remap[rid] = (new_slide.part.relate_to(rel.target_ref, rel.reltype, is_external=True)
                                      if rel.is_external else new_slide.part.relate_to(rel.target_part, rel.reltype))
                    node.set(att, remap[rid])
        tree.append(new_el)


# --------------------------------------------------------------------------- deck ---
def _crop_loss(img_w: int, img_h: int, box_w: float, box_h: float) -> float:
    """Fraction of the image lost when it is cropped to fill the box (aspect preserved)."""
    ia, ba = img_w / img_h, box_w / box_h
    return 1.0 - min(ia, ba) / max(ia, ba)


def _image_size(path) -> tuple[int, int]:
    from PIL import Image
    with Image.open(str(path)) as im:
        return im.size


def _norm_paras(body) -> list[tuple[int, str]]:
    out = []
    for item in body:
        lvl, text = (item if isinstance(item, tuple) else (0, item))
        if not isinstance(text, str) or not isinstance(lvl, int) or lvl < 0 or lvl > 4:
            raise TemplateError(f"body item {item!r}: use 'text' or (level 0-4, 'text')")
        for part in text.split("\n"):
            if part.strip():
                out.append((lvl, part.strip()))
    return out


def _is_group(body) -> bool:
    return bool(body) and all(isinstance(b, (list, tuple)) and (not isinstance(b, tuple) or not (len(b) == 2 and isinstance(b[0], int)))
                              for b in body)


class TemplateDeck:
    """A deck built on a real template. See module docstring."""

    def __init__(self, template_path, keep_originals=False):
        self.template_path = Path(template_path)
        self.prs = Presentation(str(self.template_path))
        self.repairs: list = repair_static_page_numbers(self.prs)
        self._colors = theme_colors(self.prs)
        self._clrmap = _clr_map(self.prs)
        self.layouts: list[LayoutInfo] = _layout_infos(self.prs)
        self.slide_w_in = self.prs.slide_width / EMU_IN
        self.slide_h_in = self.prs.slide_height / EMU_IN
        self.min_picture_in = 3.0 * min(self.slide_w_in / REF_W_IN, self.slide_h_in / REF_H_IN)
        self.default_grow = max(1.0, min(self.slide_w_in / REF_W_IN, self.slide_h_in / REF_H_IN, 1.5))
        self.min_pt = 12.0 * min(self.slide_w_in / REF_W_IN, self.slide_h_in / REF_H_IN)
        self.log: list[dict] = []
        self.links_removed = 0
        self.n_originals = len(self.prs.slides)
        if keep_originals is True:
            self._drop_originals: list[int] = []
        elif keep_originals is False or keep_originals is None:
            self._drop_originals = list(range(self.n_originals))
        else:                                   # iterable of 1-based slide numbers to keep
            keep = {int(i) - 1 for i in keep_originals}
            self._drop_originals = [i for i in range(self.n_originals) if i not in keep]
        # Originals are removed at save(), not here: add_from_example() clones them as patterns, and
        # they always precede the new slides, so index n-1 stays valid until then.
        self.n_originals_kept = self.n_originals - len(self._drop_originals)

    # -- structure ---------------------------------------------------------------------------
    def roles(self) -> dict:
        out: dict = {}
        for li in self.layouts:
            out.setdefault(li.role, []).append(li.name)
        return out

    def find_layouts(self, key: str, allow_sample_graphics: bool = False) -> list[LayoutInfo]:
        """Layouts matching a name, an index, or a role. By role, layouts that draw sample charts / fixed
        page numbers are left out; by name they need allow_sample_graphics=True."""
        k = key.strip().lower()
        by_name = [li for li in self.layouts if li.name.lower() == k]
        if k.isdigit() and not by_name and int(k) < len(self.layouts):
            by_name = [self.layouts[int(k)]]
        if by_name:
            li = by_name[0]
            if li.sample_content and not allow_sample_graphics:
                raise TemplateError(f"layout {li.name!r} draws template sample content on every slide "
                                    f"({'; '.join(li.warnings)}); choose another layout or pass allow_sample_graphics=True")
            return [li]
        return [li for li in self.layouts if li.role == k and not li.sample_content]

    def _delete_slides(self, indices):
        if not indices:
            return
        pres = self.prs.part._element
        lst = pres.find(qn("p:sldIdLst"))
        ids = list(lst)
        dropped_ids = set()
        for i in sorted(indices, reverse=True):
            sid = ids[i]
            dropped_ids.add(sid.get("id"))
            self.prs.part.drop_rel(sid.get(qn("r:id")))
            lst.remove(sid)
        # custom shows reference slides by rId: remove them rather than leave dangling references
        cs = pres.find(qn("p:custShowLst"))
        if cs is not None:
            pres.remove(cs)
        for sec in pres.iter("{%s}sectionLst" % P14_NS):
            for sid in list(sec.iter("{%s}sldId" % P14_NS)):
                if sid.get("id") in dropped_ids:
                    sid.getparent().remove(sid)
            for s in list(sec):
                if len(s.find("{%s}sldIdLst" % P14_NS)) == 0:
                    sec.remove(s)
            if len(sec) == 0:                   # last section gone: drop the whole extension
                ext = sec.getparent()
                ext.getparent().remove(ext)
                el = pres.find(qn("p:extLst"))
                if el is not None and len(el) == 0:
                    pres.remove(el)

    def _register_in_section(self, slide):
        pres = self.prs.part._element
        secs = list(pres.iter("{%s}sectionLst" % P14_NS))
        if not secs:
            return
        sid = pres.find(qn("p:sldIdLst"))[-1].get("id")
        last = secs[0][-1].find("{%s}sldIdLst" % P14_NS)
        etree.SubElement(last, "{%s}sldId" % P14_NS).set("id", sid)

    # -- selection ---------------------------------------------------------------------------
    def _select(self, key, *, subtitle, body_groups, picture, fill, allow_sample_graphics=False):
        cands = self.find_layouts(key, allow_sample_graphics)
        if not cands:
            raise TemplateError(f"no layout or role {key!r}; roles: {self.roles()}")
        reasons = []
        for li in cands:
            why = self._requirements(li, subtitle, body_groups, picture, fill)
            if why is None:
                return li
            reasons.append(f"{li.name!r}: {why}")
        raise TemplateError(f"no layout for {key!r} can take this content -> " + "; ".join(reasons))

    @staticmethod
    def _text_slots(li: LayoutInfo):
        """Body slots in reading order (rows of 8 % height, then left to right)."""
        return sorted(li.slots("body"), key=lambda p: (round(p.top_pct / 8), p.left_pct))

    @classmethod
    def _slots_for_groups(cls, li: LayoutInfo, n: int, taken=()):
        """The n largest free body slots, returned in reading order (a tiny corner label never wins)."""
        free = [p for p in cls._text_slots(li) if p.idx not in taken]
        big = sorted(free, key=lambda p: -p.width_in * p.height_in)[:n]
        return sorted(big, key=lambda p: (round(p.top_pct / 8), p.left_pct))

    def _requirements(self, li, subtitle, body_groups, picture, fill):
        bodies = [p for p in self._text_slots(li) if p.idx not in fill]       # slots addressed by fill= are taken
        if subtitle and not li.slots("subtitle") and not bodies:
            return "no subtitle/body slot for the subtitle"
        n_text = len(body_groups)
        free_bodies = len(bodies) - (1 if subtitle and not li.slots("subtitle") else 0)
        if n_text > free_bodies:
            return f"{n_text} text group(s) but {max(free_bodies, 0)} body slot(s)"
        if picture:
            n_pic = len(picture) if isinstance(picture, (list, tuple)) else 1
            n_fig = len(self._figure_slots(li, n_pic))
            if n_fig == 0 and free_bodies - n_text < 1:
                return "no picture placeholder (and no spare body slot to hold the figure)"
            if n_fig and n_pic > n_fig:
                return f"{n_pic} pictures but {n_fig} figure slot(s)"
        return None

    # -- add ---------------------------------------------------------------------------------
    def add(self, layout, *, title=None, subtitle=None, body=None, picture=None, notes=None,
            fill=None, alt=None, fit="auto", max_crop=0.02, min_scale=0.6, grow=None, picture_small_ok=False,
            allow_sample_graphics=False, bullets="auto"):
        """Add a slide. `layout` is a layout name, its index, or a role (see .roles()).

        body: list of strings / (level, string); or a list of such lists (one per body slot, reading order).
        picture: image path (or a list of paths) for the layout's figure slot(s), in reading order. fit="auto"|"cover"|"contain".
        bullets: "auto" removes the bullet of a lone short line (tagline, label); True/False force it.
        fill: {placeholder idx: text or [bullets]} for slots the roles do not cover (e.g. a section number).
        grow: largest font scale for non-title text (None = automatic: the slide-size ratio vs 13.333 x 7.5 in,
        capped at 1.5, never below 1); the biggest scale in [min_scale, grow] that fits is used.
        min_scale: the font may shrink from the template size in 5 % steps down to this fraction (never
        below min_pt, 12 pt on a 13.333 in slide, scaled with the slide); 1.0 = never shrink.
        """
        fill = dict(fill or {})
        if body is None:
            groups = []
        elif _is_group(body):
            groups = [_norm_paras(g) for g in body]
        else:
            groups = [_norm_paras(body)]
        groups = [g for g in groups if g]
        self._check_notes(notes)
        if fit not in ("auto", "cover", "contain"):
            raise TemplateError(f"fit={fit!r}: use auto|cover|contain")
        for pth in (picture if isinstance(picture, (list, tuple)) else [picture]):
            if pth is not None and not Path(pth).exists():
                raise TemplateError(f"picture not found: {pth}")
        li = self._select(layout, subtitle=subtitle, body_groups=groups, picture=picture, fill=fill,
                          allow_sample_graphics=allow_sample_graphics)

        plan = self._plan(li, title, subtitle, groups, picture, fill, min_scale,
                          self.default_grow if grow is None else grow)    # raises before any write
        slide = self.prs.slides.add_slide(li._layout)
        try:
            self._execute(slide, li, plan, picture, alt, fit, max_crop, picture_small_ok, bullets)
        except Exception:
            self._discard_last()
            raise
        self._register_in_section(slide)
        slide.notes_slide.notes_text_frame.text = notes
        self.log.append({"slide": len(self.prs.slides) - self.n_originals, "layout": li.name,
                         "scales": {i: v[2] for i, v in plan.items() if v[2] != 1.0}})
        return slide

    @staticmethod
    def _check_notes(notes):
        if not notes or not notes.strip():
            raise TemplateError("speaker notes are required (Korean, >= 100 chars): notes=...")
        if len(notes) < MIN_NOTES_CHARS:
            raise TemplateError(f"speaker notes {len(notes)} chars < {MIN_NOTES_CHARS}")
        if not HANGUL_RE.search(notes):
            raise TemplateError("speaker notes contain no Korean (QC-10 requires Korean notes)")

    def _discard_last(self):
        lst = self.prs.part._element.find(qn("p:sldIdLst"))
        sid = lst[-1]
        self.prs.part.drop_rel(sid.get(qn("r:id")))
        lst.remove(sid)

    def _plan(self, li, title, subtitle, groups, picture, fill, min_scale, grow=1.0):
        """Assign text to placeholder idx and prove each assignment fits. Returns {idx: (paras, scale)}."""
        plan: dict = {}
        by_idx = {p.idx: p for p in li.placeholders}
        title_slot = (li.slots("title") or [None])[0]
        if title:
            if title_slot is None:
                raise TemplateError(f"layout {li.name!r} has no title placeholder")
            plan[title_slot.idx] = ([(0, title)], title_slot)
        elif title_slot is not None and title_slot.idx not in fill:
            pass                                      # unfilled title is removed below
        sub_slot = (li.slots("subtitle") or [None])[0]
        taken = set(fill)
        group_slots = self._slots_for_groups(li, len(groups), taken)
        taken |= {p.idx for p in group_slots}
        if subtitle:
            if sub_slot is not None:
                plan[sub_slot.idx] = ([(0, subtitle)], sub_slot)
            else:
                spare = self._slots_for_groups(li, 1, taken)
                if not spare:
                    raise TemplateError(f"layout {li.name!r} has no slot for the subtitle")
                plan[spare[0].idx] = ([(0, subtitle)], spare[0])
                taken.add(spare[0].idx)
        for g, slot in zip(groups, group_slots):
            plan[slot.idx] = (g, slot)
        for idx, text in fill.items():
            if idx not in by_idx:
                raise TemplateError(f"fill idx {idx} not in layout {li.name!r}: {sorted(by_idx)}")
            plan[idx] = (_norm_paras(text if isinstance(text, list) else [text]), by_idx[idx])
        # fit proof
        scales = {}
        for idx, (paras, slot) in plan.items():
            slot = slot or by_idx[idx]
            plan[idx] = (paras, slot)
            scales[idx] = self._fit_scale(li, slot, paras, min_scale, grow)
        for idx, (paras, slot) in plan.items():
            self._check_visible(li, slot, sorted({lvl for lvl, _ in paras}))
        return {idx: (paras, slot, scales[idx]) for idx, (paras, slot) in plan.items()}

    def _check_visible(self, li, slot, levels):
        """Refuse text the template would draw in (nearly) the background color."""
        for lvl in levels:
            fg = resolve_text_color(slot._shape, slot._master, lvl, self._colors, self._clrmap)
            bg = background_under(li._layout, slot._shape, self._colors, self._clrmap)
            if fg is None or bg is None:
                continue
            ratio = contrast_ratio(fg, bg)
            if ratio < 3.0:
                raise TemplateError(
                    f"layout {li.name!r} placeholder idx {slot.idx}: text level {lvl + 1} is drawn in #{fg} on "
                    f"#{bg} ({ratio:.2f}:1), i.e. invisible; use level 1 only or another layout")
            if ratio < 4.5:
                self.log.append({"warning": f"{li.name!r} idx {slot.idx} level {lvl + 1}: #{fg} on #{bg} = {ratio:.2f}:1"})

    def _fit_scale(self, li, slot, paras, min_scale, grow=1.0):
        """Largest font scale in [min_scale, grow] (5 % steps) at which the text fits; titles never grow."""
        top = grow if slot.kind != "title" else 1.0
        n_steps = int(round((top - min_scale) / 0.05))
        floor_pt = self.min_pt
        smallest = min(slot.style(l).size for l, _ in paras)
        for k in range(n_steps + 1):
            scale = round(top - 0.05 * k, 2)
            if scale < 1.0 and smallest * scale < floor_pt and scale < top:
                break
            h = text_height_in(paras, slot.style, slot.inner_width_in(), scale)
            if h <= slot.inner_height_in() + FIT_TOL_IN:
                return scale
        h0 = text_height_in(paras, slot.style, slot.inner_width_in(), 1.0)
        raise TemplateError(
            f"text does not fit layout {li.name!r} placeholder idx {slot.idx} ({slot.kind}): needs "
            f"{h0:.2f} in, slot offers {slot.inner_height_in():.2f} in at {slot.font_pt:g} pt "
            f"(capacity ~{slot.capacity_chars} chars / {slot.capacity_lines} lines of ~{slot.chars_per_line}); "
            f"shorten the text, split the slide, pick a roomier layout, or allow min_scale<1")

    def _execute(self, slide, li, plan, picture, alt, fit, max_crop, picture_small_ok, bullets="auto"):
        by_idx = {ph.placeholder_format.idx: ph for ph in slide.placeholders}
        used = set()
        for idx, (paras, info, scale) in plan.items():
            ph = by_idx[idx]
            plain = bullets is False or (bullets == "auto" and len(paras) == 1 and len(paras[0][1]) < 80
                                         and info.kind in ("body", "subtitle"))
            self._write_text(ph, paras, info, scale, plain)
            used.add(idx)
        if picture:
            self._place_picture(slide, li, by_idx, used, picture, alt, fit, max_crop, picture_small_ok, plan)
        for idx, ph in by_idx.items():                 # nothing left empty: no "Click to add" prompts
            if idx not in used:
                ph._element.getparent().remove(ph._element)

    @staticmethod
    def _write_text(ph, paras, info, scale, plain=False):
        """Write the text with every inherited property that matters for fitting made explicit
        (size, line spacing, space before, indents, alignment, insets, anchor), so a checker that
        reads only the slide XML (qc_layout) sees exactly what PowerPoint will draw."""
        tf = ph.text_frame
        bp = tf._txBody.find(qn("a:bodyPr"))
        for k, v in _body_attrs(info._shape).items():
            bp.set(k, str(v))
        for i, (lvl, text) in enumerate(paras):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            if lvl:
                p.level = lvl
            st = info.style(lvl)
            ppr = p._p.get_or_add_pPr()
            if st.has_marl:
                ppr.set("marL", str(int(round(st.margin_left * 12700))))
            if st.has_indent:
                ppr.set("indent", str(int(round(st.indent * 12700))))
            if st.algn != "l":
                ppr.set("algn", st.algn)
            if st.line_mult != 1.0:
                p.line_spacing = st.line_mult
            if st.space_before and i > 0:
                p.space_before = Pt(round(st.space_before * scale, 1))
            if plain:                                   # a lone label or tagline is not a bullet list
                ppr.set("marL", "0")
                ppr.set("indent", "0")
                for old in ppr.findall(qn("a:buNone")):
                    ppr.remove(old)
                etree.SubElement(ppr, qn("a:buNone"))
                for tag in ("a:tabLst", "a:defRPr", "a:extLst"):       # keep schema order: buNone precedes these
                    for node in ppr.findall(qn(tag)):
                        ppr.remove(node)
                        ppr.append(node)
            run = p.add_run()
            run.text = text
            run.font.size = Pt(round(st.size * scale, 1))

    def _figure_slots(self, li, n_needed: int) -> list:
        """Picture slots of the layout that can carry a figure (>= 5 % of the slide; the small logo
        slots of institutional layouts are skipped), in reading order; else spare body slots."""
        sw, sh = self.slide_w_in, self.slide_h_in
        big = [p for p in li.slots("picture") if p.width_in * p.height_in >= 0.05 * sw * sh]
        big.sort(key=lambda p: (round(p.top_pct / 8), p.left_pct))
        return big

    def _place_picture(self, slide, li, by_idx, used, picture, alt, fit, max_crop, small_ok, plan=None):
        """Place one picture or a list of them; each goes to the next figure slot in reading order."""
        pics = list(picture) if isinstance(picture, (list, tuple)) else [picture]
        slots = self._figure_slots(li, len(pics))
        if not slots:
            spare = [p for p in self._text_slots(li) if p.idx not in used]
            slots = spare[-1:]
        if len(pics) > len(slots):
            raise TemplateError(f"{len(pics)} pictures but layout {li.name!r} has {len(slots)} figure slot(s)")
        alts = list(alt) if isinstance(alt, (list, tuple)) else [alt] * len(pics)
        placed = []
        for path, slot, one_alt in zip(pics, slots, alts):
            placed.append(self._place_one(slide, li, by_idx, used, path, one_alt, fit, max_crop, small_ok, slot))
        for idx, (paras, info, scale) in (plan or {}).items():
            ink = text_ink_in(info, paras, scale)
            for pl, pt_, pr, pb in placed:
                ox, oy = min(ink[2], pr) - max(ink[0], pl), min(ink[3], pb) - max(ink[1], pt_)
                if ox > INK_COLLIDE_IN and oy > INK_COLLIDE_IN:
                    raise TemplateError(f"text of placeholder idx {idx} ({paras[0][1][:24]!r}...) would run into a "
                                        f"picture by {ox:.2f} x {oy:.2f} in in layout {li.name!r}: shorten the "
                                        f"text, use a shorter label, or pick another layout")

    def _place_one(self, slide, li, by_idx, used, picture, alt, fit, max_crop, small_ok, slot):
        ph = by_idx[slot.idx]
        used.add(slot.idx)
        box_l, box_t, box_w, box_h = ph.left, ph.top, ph.width, ph.height
        iw, ih = _image_size(picture)
        loss = _crop_loss(iw, ih, box_w, box_h)
        mode = fit
        if mode == "auto":
            mode = "cover" if loss <= max_crop else "contain"
        if mode == "cover" and loss > max_crop:
            raise TemplateError(f"fit='cover' would crop {loss:.0%} of the picture (limit {max_crop:.0%}); "
                                f"use fit='contain' or a layout with a matching aspect "
                                f"(slot {box_w / box_h:.2f}:1, picture {iw / ih:.2f}:1)")
        ph._element.getparent().remove(ph._element)
        if mode == "cover":
            pic = slide.shapes.add_picture(str(picture), box_l, box_t, box_w, box_h)
            ia, ba = iw / ih, box_w / box_h
            if ia > ba:                                 # too wide: crop left/right
                pic.crop_left = pic.crop_right = (1 - ba / ia) / 2
            else:
                pic.crop_top = pic.crop_bottom = (1 - ia / ba) / 2
        else:
            scale = min(box_w / iw, box_h / ih)
            w, h = int(iw * scale), int(ih * scale)
            pic = slide.shapes.add_picture(str(picture), box_l + (box_w - w) // 2, box_t + (box_h - h) // 2, w, h)
        if not small_ok and max(pic.width, pic.height) / EMU_IN < self.min_picture_in - 0.01:
            raise TemplateError(f"picture slot too small for a legible figure: "
                                f"{max(pic.width, pic.height) / EMU_IN:.2f} in < {self.min_picture_in:.2f} in")
        pic.name = f"figure:{Path(picture).stem}"
        if alt:
            pic._element.nvPicPr.cNvPr.set("descr", alt)
        return (pic.left / EMU_IN, pic.top / EMU_IN, (pic.left + pic.width) / EMU_IN, (pic.top + pic.height) / EMU_IN)

    # -- example slides as patterns ------------------------------------------------------------
    def example_slides(self) -> list:
        """The template's own example slides: layout, fillable text shapes, pictures."""
        out = []
        for n, sl in enumerate(list(self.prs.slides)[:self.n_originals], 1):
            shapes = example_text_shapes(sl)
            out.append({"slide": n, "layout": sl.slide_layout.name,
                        "pictures": sum(1 for x in _walk(sl.shapes) if x.shape_type == 13),
                        "text_shapes": [example_shape_info(x, i) for i, x in enumerate(shapes)]})
        return out

    def _page_number_shapes(self, slide, example: int, shapes) -> list:
        """Indices of typed page numbers (digits only, small, in the bottom band of the slide)."""
        out = []
        for i, sh in enumerate(shapes):
            t = sh.text_frame.text.strip()
            if re.fullmatch(r"\d{1,3}", t) and sh.width < 914400 and                     (sh.top + sh.height / 2) / self.prs.slide_height > 0.88:
                out.append(i)
        return out

    def _loose_width(self, sh) -> float:
        """Widest a no-wrap line may be: up to 0.3 in from the slide edges around its anchor point."""
        ps = sh.text_frame._txBody.findall(qn("a:p"))
        ppr = ps[0].find(qn("a:pPr")) if ps else None
        algn = (ppr.get("algn") if ppr is not None else None) or "l"
        left, right = sh.left / EMU_IN, (sh.left + sh.width) / EMU_IN
        m = 0.3 * self.slide_w_in / REF_W_IN
        if algn == "ctr":
            c = (left + right) / 2
            return 2 * min(c - m, self.slide_w_in - m - c)
        return (self.slide_w_in - m - left) if algn == "l" else (right - m)

    def numeral_shapes(self, example: int) -> list:
        """Indices of digit-only decoration shapes ('01', '02' ...) of an example: pass them as keep=."""
        shapes = example_text_shapes(self.prs.slides[example - 1])
        return [i for i, sh in enumerate(shapes) if re.fullmatch(r"\d{1,3}", sh.text_frame.text.strip())]

    def add_from_example(self, example: int, texts: dict, *, pictures=None, notes=None,
                         unassigned="error", keep=(), fit="auto", max_crop=0.02, min_scale=0.5, loose=()):
        """Clone example slide `example` (1-based) and replace the text of its shapes.

        texts: {shape name | index into example_slides()[n-1]['text_shapes'] : str | list[str] | None}.
            A list becomes several paragraphs that reuse the original paragraph/run formatting;
            None removes the shape. Text that does not fit at the shape's own font size raises.
        loose: shapes (names or indices) whose no-wrap line may grow beyond the drawn box up to the slide
            margins (captions and labels with nothing drawn behind them); other no-wrap shapes keep their width.
        pictures: {picture shape name: image path | None}, replaced in the same rectangle (never stretched);
            None removes the picture (a logo or sample photo of the template).
        unassigned: what happens to text shapes you did not mention: "error" (default; no leftover
            sample text) or "drop" (remove them). Names or indices in `keep` are left untouched either way.
        """
        self._check_notes(notes)
        if not 1 <= example <= self.n_originals:
            raise TemplateError(f"example {example}: the template has {self.n_originals} example slides")
        if unassigned not in ("error", "drop"):
            raise TemplateError("unassigned must be 'error' or 'drop'")
        src = self.prs.slides[example - 1]
        src_shapes = example_text_shapes(src)
        names = [x.name for x in src_shapes]
        assign: dict = {}                              # index into src_shapes -> list[str] | None
        for k, v in texts.items():
            if isinstance(k, int):
                if not 0 <= k < len(src_shapes):
                    raise TemplateError(f"text shape index {k}: example {example} has {len(src_shapes)}")
                idx = k
            else:
                hits = [i for i, n in enumerate(names) if n == k]
                if not hits:
                    raise TemplateError(f"no text shape {k!r} in example {example}: {names}")
                if len(hits) > 1:
                    raise TemplateError(f"shape name {k!r} is ambiguous in example {example} "
                                        f"(indices {hits}); address it by index")
                idx = hits[0]
            assign[idx] = None if v is None else ([v] if isinstance(v, str) else [str(x) for x in v])
        keep_idx = {i for i, n in enumerate(names) if n in set(keep)} | {k for k in keep if isinstance(k, int)}
        pn_idx = set(self._page_number_shapes(src, example, src_shapes))
        keep_idx |= pn_idx                              # typed page numbers become slide-number fields below
        leftovers = [f"{i}:{names[i]}" for i in range(len(names)) if i not in assign and i not in keep_idx]
        if leftovers and unassigned == "error":
            raise TemplateError(f"example {example}: text shapes {leftovers} would keep the template's sample text; "
                                f"assign them (None removes), list them in keep=, or pass unassigned='drop'")
        loose_idx = {i for i, n in enumerate(names) if n in set(loose)} | {k for k in loose if isinstance(k, int)}
        scales: dict = {}
        for i, vals in assign.items():                 # fit proof before anything is written
            if vals:
                sc, msg = fit_example_scale(src_shapes[i], vals, min_scale, self.min_pt,
                                            self._loose_width(src_shapes[i]) if i in loose_idx else None)
                if sc is None:
                    raise TemplateError(f"example {example} shape {i}:{names[i]!r}: text does not fit, {msg} "
                                        f"(capacity ~{example_shape_info(src_shapes[i], 0)['capacity_chars']} chars; "
                                        f"min_scale={min_scale})")
                scales[i] = sc
        new = self.prs.slides.add_slide(src.slide_layout)
        try:
            _clone_into(new, src)
            cl = example_text_shapes(new)              # same geometry, same order as src_shapes
            if [x.name for x in cl] != names:
                raise TemplateError("internal: cloned slide shape order differs from the example")
            for i, vals in assign.items():
                if vals is None:
                    cl[i]._element.getparent().remove(cl[i]._element)
                else:
                    _rebuild_paragraphs(cl[i], vals, scales.get(i, 1.0))
            for i in pn_idx:
                if i not in assign:
                    _to_slide_number_field(cl[i])
            if unassigned == "drop":
                for i, sh in enumerate(cl):
                    if i not in assign and i not in keep_idx:
                        sh._element.getparent().remove(sh._element)
            placed = [r for r in (self._replace_picture(new, name, path, fit, max_crop)
                                  for name, path in (pictures or {}).items()) if r]
            self._check_picture_text_collision(new, placed, example)
            for ph in list(new.placeholders):         # empty inherited placeholders show "Click to add"
                if ph.has_text_frame and not ph.text_frame.text.strip() and ph_kind(ph) not in CHROME_KINDS:
                    ph._element.getparent().remove(ph._element)
        except Exception:
            self._discard_last()
            raise
        self._register_in_section(new)
        new.notes_slide.notes_text_frame.text = notes
        self.log.append({"slide": len(self.prs.slides) - self.n_originals, "example": example,
                         "scales": {i: v for i, v in scales.items() if v != 1.0}})
        return new

    def _replace_picture(self, slide, name, path, fit, max_crop):
        old = next((x for x in _walk(slide.shapes) if x.name == name and x.shape_type == 13), None)
        if old is None:
            raise TemplateError(f"no picture shape {name!r} in the cloned example")
        if path is None:                                  # drop the template's picture (logo, sample photo)
            rid = old._element.xpath(".//a:blip/@r:embed")
            old._element.getparent().remove(old._element)
            if rid and not slide._element.xpath(f'.//*[@r:embed="{rid[0]}"]'):
                slide.part.drop_rel(rid[0])
            return
        if not Path(path).exists():
            raise TemplateError(f"picture not found: {path}")
        l, t, w, h = old.left, old.top, old.width, old.height
        iw, ih = _image_size(path)
        loss = _crop_loss(iw, ih, w, h)
        mode = fit if fit != "auto" else ("cover" if loss <= max_crop else "contain")
        if mode == "cover" and loss > max_crop:
            raise TemplateError(f"fit='cover' would crop {loss:.0%} of the picture (limit {max_crop:.0%})")
        el = old._element
        rid = el.xpath(".//a:blip/@r:embed")
        parent = el.getparent()
        pos = list(parent).index(el)
        if mode == "cover":
            pic = slide.shapes.add_picture(str(path), l, t, w, h)
            ia, ba = iw / ih, w / h
            if ia > ba:
                pic.crop_left = pic.crop_right = (1 - ba / ia) / 2
            else:
                pic.crop_top = pic.crop_bottom = (1 - ia / ba) / 2
        else:
            sc = min(w / iw, h / ih)
            nw, nh = int(iw * sc), int(ih * sc)
            pic = slide.shapes.add_picture(str(path), l + (w - nw) // 2, t + (h - nh) // 2, nw, nh)
        pic.name = f"figure:{Path(path).stem}"
        pic._element.getparent().remove(pic._element)
        parent.insert(pos, pic._element)
        parent.remove(el)
        if rid and not slide._element.xpath(f'.//*[@r:embed="{rid[0]}"]'):
            slide.part.drop_rel(rid[0])
        return (pic.left / EMU_IN, pic.top / EMU_IN, (pic.left + pic.width) / EMU_IN, (pic.top + pic.height) / EMU_IN)

    def _check_picture_text_collision(self, slide, rects, example):
        """A replacement picture must not cover the text the slide now carries."""
        for sh in example_text_shapes(slide):
            ink = example_ink_in(sh)
            for pl, pt_, pr, pb in rects:
                ox, oy = min(ink[2], pr) - max(ink[0], pl), min(ink[3], pb) - max(ink[1], pt_)
                if ox > INK_COLLIDE_IN and oy > INK_COLLIDE_IN:
                    raise TemplateError(f"example {example}: the new picture would cover the text of shape "
                                        f"{sh.name!r} ({sh.text_frame.text.strip()[:30]!r}) by {ox:.2f} x {oy:.2f} in; "
                                        f"drop that picture (None), remove the text, or use another example")

    # -- output ------------------------------------------------------------------------------
    def _strip_dangling_slide_links(self) -> int:
        """Remove hyperlinks (menu buttons on masters/layouts, jumps on slides) that point at slides which are
        no longer in the deck, and drop their relationships: otherwise the deleted example slides stay alive in
        the package through those links. Returns the number of links removed."""
        kept = {id(sl.part) for sl in self.prs.slides}
        parts = [m.part for m in self.prs.slide_masters]
        parts += [lay.part for lay in self.prs.slide_layouts]
        parts += [sl.part for sl in self.prs.slides]
        removed = 0
        for part in parts:
            for rid, rel in list(part.rels.items()):
                if rel.is_external or not rel.reltype.endswith("/slide") or id(rel.target_part) in kept:
                    continue
                for h in part._element.xpath(f'.//a:hlinkClick[@r:id="{rid}"] | .//a:hlinkHover[@r:id="{rid}"]'):
                    h.getparent().remove(h)
                    removed += 1
                part.drop_rel(rid)
        return removed

    def save(self, path):
        if self._drop_originals:
            self._delete_slides(self._drop_originals)
            self._drop_originals = []
        self.links_removed = self._strip_dangling_slide_links()
        self.prs.core_properties.keywords = f"journal-ppt-template:{self.template_path.stem}"
        self.prs.save(str(path))
        return Path(path)


def layout_gallery(pptx_path, out_path):
    """Write a throw-away deck with one slide per layout, every placeholder labeled 'L<n> idx<i> <kind>',
    to look at the layouts before choosing (render it with PowerPoint). Not a deliverable: no notes."""
    td = TemplateDeck(pptx_path)
    for li in td.layouts:
        sl = td.prs.slides.add_slide(li._layout)
        for ph in sl.placeholders:
            idx = ph.placeholder_format.idx
            if ph.has_text_frame and ph_kind(ph) in TEXT_KINDS:
                ph.text_frame.text = f"L{li.index} idx{idx} {ph_kind(ph)}"
    td._drop_originals = list(range(td.n_originals))
    return td.save(out_path)


# --------------------------------------------------------------------------- CLI ---
def main(argv=None):
    ap = argparse.ArgumentParser(description="Inspect a real .pptx template and derive a journal-ppt palette")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("inspect", help="slide size, theme, layouts, placeholders, capacity, guessed roles")
    a.add_argument("pptx")
    a.add_argument("--json", action="store_true")
    a.add_argument("--out", default=None, help="write the JSON here")
    b = sub.add_parser("theme", help="THEMES-entry draft from the template palette, with contrast report")
    b.add_argument("pptx")
    b.add_argument("--name", default=None)
    b.add_argument("--json", action="store_true")
    c = sub.add_parser("gallery", help="one labeled slide per layout (to render and look at)")
    c.add_argument("pptx")
    c.add_argument("out")
    ns = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if not Path(ns.pptx).exists():
        print(f"ERROR: file not found: {ns.pptx}", file=sys.stderr)
        return 2
    if ns.cmd == "gallery":
        print(layout_gallery(ns.pptx, ns.out))
        return 0
    if ns.cmd == "inspect":
        d = inspect_template(ns.pptx)
        if ns.out:
            Path(ns.out).write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps(d, ensure_ascii=False, indent=1) if ns.json else format_inspection(d))
        return 0
    d = theme_from_template(ns.pptx)
    if ns.json:
        print(json.dumps(d, ensure_ascii=False, indent=1))
    else:
        print(theme_entry_source(d, ns.name))
        print(f"\ncontrast report (all_pass={d['all_pass']}):")
        for r in d["contrast_report"]:
            print(f"  {'ok ' if r['pass'] else 'LOW'} {r['pair']:34s} #{r['fg']} on #{r['bg']} = {r['ratio']}:1 (need {r['required']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
