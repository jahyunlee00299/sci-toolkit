"""
en_fields.py — read every EndNote citation of a .docx IN DOCUMENT ORDER.

What a CWYW citation looks like on disk (reverse-engineered 261023 from formatted manuscripts):

    <w:fldChar begin/>  instrText " ADDIN EN.CITE "                    <- outer field
        <w:fldChar begin><w:fldData>BASE64</w:fldData></w:fldChar>    <- nested field, only when
        instrText " ADDIN EN.CITE.DATA "  <w:fldChar end/>               the record XML is large
    <w:fldChar separate/>  rendered runs "(Song et al., 2018)"  <w:fldChar end/>

  * small payloads sit inline: instrText " ADDIN EN.CITE <EndNote><Cite>...</EndNote>"
  * large payloads sit in the nested EN.CITE.DATA field's fldData: plain base64 of the same
    UTF-8 XML (no compression)
  * the payload is <EndNote> with one <Cite> per record: <Author>, <Year>, <RecNum>,
    <DisplayText>, and a <record> whose <foreign-keys><key db-id=".."> names the library
    the record came from (the library's own id is misc(code=14) in sdb.eni)
  * unformatted citations are plain text "{Author, Year #RecNum; Author, Year #RecNum}"

A flat begin/end regex mis-pairs the nested field (SKILL.md, "CWYW can shift..."), so this
walks the XML with a field stack and records, per citation, whether it sits inside a tracked
deletion (<w:del>/<w:moveFrom>) or insertion.
"""

import base64
import re
import zipfile

from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_T = lambda n: "{%s}%s" % (W, n)  # noqa: E731
DEL_TAGS = {_T("del"), _T("moveFrom")}
INS_TAGS = {_T("ins"), _T("moveTo")}
TEXT_TAGS = {_T("t"), _T("delText")}
INSTR_TAGS = {_T("instrText"), _T("delInstrText")}
MARKER = re.compile(r"\{([^{}]*#\s*\d+[^{}]*)\}")
CITE = re.compile(r"<Cite\b.*?</Cite>", re.S)


def _tag(s, name):
    m = re.search(r"<%s\b[^>]*>(.*?)</%s>" % (name, name), s, re.S)
    return re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else ""


def parse_payload(xml_text):
    """EndNote XML -> list of {recnum, author, year, db_id, display}."""
    out = []
    for c in CITE.findall(xml_text or ""):
        rn = _tag(c, "RecNum") or _tag(c, "rec-number")
        db = re.search(r'db-id="([^"]+)"', c)
        out.append({"recnum": int(rn) if rn.isdigit() else None, "author": _tag(c, "Author"),
                    "year": _tag(c, "Year"), "db_id": db.group(1) if db else "",
                    "display": _tag(c, "DisplayText")})
    return out


def parse_marker(body):
    """'Song, 2018 #460; Kim, 2020 #12' -> [{recnum, author, year}]"""
    out = []
    for part in body.split(";"):
        m = re.match(r"\s*(.*?),\s*([^#,]*?)\s*#\s*(\d+)\s*$", part)
        if m:
            out.append({"recnum": int(m.group(3)), "author": m.group(1).strip(),
                        "year": m.group(2).strip(), "db_id": "", "display": ""})
    return out


class _Field:
    __slots__ = ("instr", "data", "result", "phase", "deleted", "inserted", "child_data", "para", "offset")

    def __init__(self, deleted, inserted, para):
        self.instr, self.data, self.result, self.phase = "", "", "", "instr"
        self.deleted, self.inserted, self.child_data, self.para = deleted, inserted, "", para


def _decode(b64):
    try:
        return base64.b64decode(re.sub(r"\s+", "", b64)).decode("utf-8", "replace")
    except Exception:
        return ""


def read_document_xml(path, part="word/document.xml"):
    with zipfile.ZipFile(path) as z:
        return z.read(part)


def citations(xml_bytes):
    """Return citations in document order.

    Each item: kind ('field'|'marker'), cites (parse_payload list), rendered (result text of
    a field; the marker text itself for markers), deleted, inserted, para (paragraph index).
    """
    out = []
    stack = []
    del_depth = ins_depth = 0
    para = -1
    run_text = []              # text of the current paragraph outside any field (for markers)
    para_fields = []           # (offset in run_text, citation) for fields of this paragraph
    pending_data = None        # fldData seen inside a begin fldChar

    def offset():
        return sum(len(t) for t, _, _ in run_text)

    def flush_markers():
        txt = "".join(t for t, _, _ in run_text)
        items = list(para_fields)
        for m in MARKER.finditer(txt):
            # deletion state of the marker = state at its first character
            pos, acc, state = m.start(), 0, (False, False)
            for t, d, i in run_text:
                if acc + len(t) > pos:
                    state = (d, i)
                    break
                acc += len(t)
            items.append((m.start(), {"kind": "marker", "cites": parse_marker(m.group(1)),
                                      "rendered": m.group(0), "deleted": state[0],
                                      "inserted": state[1], "para": para}))
        # a field sits at the offset where it began, i.e. between the surrounding text
        items.sort(key=lambda it: it[0])
        out.extend(c for _, c in items)
        run_text.clear()
        para_fields.clear()

    for ev, el in etree.iterparse(_bytes_io(xml_bytes), events=("start", "end")):
        tag = el.tag
        if ev == "start":
            if tag in DEL_TAGS:
                del_depth += 1
            elif tag in INS_TAGS:
                ins_depth += 1
            elif tag == _T("p"):
                para += 1
            continue
        # ---- end events: text is complete here
        if tag in DEL_TAGS:
            del_depth -= 1
        elif tag in INS_TAGS:
            ins_depth -= 1
        elif tag == _T("p"):
            flush_markers()
        elif tag == _T("fldData"):
            pending_data = el.text or ""
        elif tag == _T("fldChar"):
            kind = el.get(_T("fldCharType"))
            if kind == "begin":
                f = _Field(del_depth > 0, ins_depth > 0, para)
                f.offset = offset()
                if pending_data:
                    f.data = pending_data
                stack.append(f)
            elif kind == "separate" and stack:
                stack[-1].phase = "result"
            elif kind == "end" and stack:
                f = stack.pop()
                instr = f.instr.strip()
                if instr.startswith("ADDIN EN.CITE.DATA"):
                    if stack:
                        stack[-1].child_data += f.data
                elif instr.startswith("ADDIN EN.CITE"):
                    inline = instr[len("ADDIN EN.CITE"):].strip()
                    payload = inline or _decode(f.data) or _decode(f.child_data)
                    cites = parse_payload(payload)
                    husk = not cites
                    if husk:
                        # payload-less field whose result is still the marker text (the
                        # 260714 "fldData husk" after an accept): the marker is the citation
                        m = MARKER.search(f.result)
                        cites = parse_marker(m.group(1)) if m else []
                    item = {"kind": "field", "cites": cites, "husk": husk,
                            "rendered": f.result.strip(), "deleted": f.deleted,
                            "inserted": f.inserted, "para": f.para}
                    if f.para == para:
                        para_fields.append((f.offset, item))
                    else:                       # a field spanning paragraphs: keep stream order
                        out.append(item)
            pending_data = None
        elif tag in INSTR_TAGS:
            if stack and stack[-1].phase == "instr":
                stack[-1].instr += el.text or ""
        elif tag in TEXT_TAGS:
            t = el.text or ""
            in_result = [f for f in stack if f.phase == "result"]
            for f in in_result:
                f.result += t
            if not stack:
                run_text.append((t, del_depth > 0, ins_depth > 0))
        if ev == "end" and tag not in (_T("body"), _T("document")) and not stack:
            el.clear()
    return out


def _bytes_io(b):
    import io
    return io.BytesIO(b)


def docx_citations(path):
    return citations(read_document_xml(path))
