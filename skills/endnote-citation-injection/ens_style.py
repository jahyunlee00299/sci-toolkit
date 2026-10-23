"""
ens_style.py — read, inspect and edit EndNote output styles (.ens) without the GUI.

Format (reverse-engineered 261023; byte-exact round trip on all 503 styles shipped with
EndNote 2025, see tests/test_ens_style.py). PRONOM fmt/324 names the signature; the old
Zotero.ENConverter was the only prior parser and documented none of the layout.

    header   16 bytes: 00 08 00 FF 00 00 00 10 'RSFTSTYL'   big-endian (499 of 503 shipped)
                       00 08 FF 00 00 00 10 00 'RSFTSTYL'   little-endian, UTF-16LE (4 of 503)
    record   tag u16 | type u16 | length u32
      type 1 container   length = 8 + payload; payload is a sequence of records
      type 2 string      length = 8 + payload; payload is UTF-16BE text
      type 3 integer     length field IS the value; the record is 8 bytes, no payload
    padding  after a type 1/2 record, 0xFB bytes up to the next 4-byte boundary; a container's
             length excludes its LAST child's padding (that padding is the container's own)
    text     a rich-text value is a container holding 0020 (string) + 0021 (formatting runs)

Known tags (from the GUI panels they reproduce; anything else is kept verbatim):

    1001 About      1010 name  1013 ?  1014 category  1015 comments  1016 based on  1017 created by
    1002 Bibliography   (verified: editing 1023 changed the CWYW-rendered reference list)
         1021/1022  author list block: 1074 > 1078 range {1079 from, 107a to,
                    107b separator, 107c before-last}; 1075 abbreviated list {107d on,
                    107e "if N or more", 107f "list first N", 1081 et-al text}
         1023       templates: 10a0 per type {10a1 type code, 10a2 > 1090 element
                    {1091 field id (RefTypeTable numbering), 1092/0012 style bits
                    (1 bold, 2 italic — verified on rendered output), 1094 prefix, 1095 suffix}}
    1003-100a      other panels (citations, footnotes, ...): parsed and preserved, not yet named
    rich text      0020 text + 0021 runs; run 0022 {0023 start offset, 0026 style bits}

Editing goes through Node objects and `dump()`; the tree keeps unknown records and their
order, so an untouched file re-serialises to identical bytes.

    python ens_style.py dump  "Style.ens" [--depth N]
    python ens_style.py info  "Style.ens"
    python ens_style.py strings "Style.ens"                 # every text value with its path
    python ens_style.py templates "Style.ens" [--type "Journal Article"]
    python ens_style.py set-template "In.ens" "Out.ens" --type "Journal Article" --field 7 --bits 0
    python ens_style.py replace "In.ens" "Out.ens" --path 1002/1021/1075/1081 --text ", et al"

Output always goes to a NEW file (put it in Documents\\EndNote\\Styles under a new name); the
original stays as the backup. Exit: 0 ok | 2 bad input / refused edit
"""

import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

MAGIC = bytes.fromhex("000800ff00000010") + b"RSFTSTYL"            # big-endian (most styles)
MAGIC_LE = bytes.fromhex("0008ff0000001000") + b"RSFTSTYL"         # little-endian variant
ENDIAN = {MAGIC: (">HHI", "utf-16-be"), MAGIC_LE: ("<HHI", "utf-16-le")}
CONTAINER, STRING, INTEGER = 1, 2, 3
PAD = 0xFB


class FormatError(ValueError):
    pass


class Node:
    __slots__ = ("tag", "type", "value", "children")

    def __init__(self, tag, typ, value=None, children=None):
        self.tag, self.type, self.value = tag, typ, value
        self.children = children if children is not None else []

    # -- navigation
    def find(self, *tags):
        """First descendant reached by following child tags in order (ints)."""
        node = self
        for t in tags:
            node = next((c for c in node.children if c.tag == t), None)
            if node is None:
                return None
        return node

    def find_all(self, tag):
        out = [c for c in self.children if c.tag == tag]
        for c in self.children:
            out += c.find_all(tag)
        return out

    @property
    def text(self):
        """String value of a type-2 node, or of a rich-text container's 0020 child."""
        if self.type == STRING:
            return self.value
        s = self.find(0x0020)
        return s.value if s is not None and s.type == STRING else None


def _pad_len(n):
    return (-n) % 4


def parse(data):
    if data[:16] not in ENDIAN:
        raise FormatError("not an RSFTSTYL .ens file (header %s)" % data[:16].hex())
    root = Node(-1, CONTAINER)
    root.value = data[:16]                       # the header picks the byte order on dump
    root.children = _parse_seq(data, 16, len(data), *ENDIAN[data[:16]])
    return root


def _parse_seq(data, off, end, fmt, enc):
    out = []
    while off < end:
        if off + 8 > end:
            raise FormatError("truncated record at %d" % off)
        tag, typ, ln = struct.unpack(fmt, data[off:off + 8])
        if typ == INTEGER:
            out.append(Node(tag, typ, ln))
            off += 8
            continue
        if typ not in (CONTAINER, STRING) or ln < 8 or off + ln > end:
            raise FormatError("bad record at %d: tag=%04x type=%d len=%d" % (off, tag, typ, ln))
        body = data[off + 8:off + ln]
        if typ == CONTAINER:
            node = Node(tag, typ, children=_parse_seq(data, off + 8, off + ln, fmt, enc))
        else:
            if len(body) % 2:
                raise FormatError("odd-length UTF-16 string at %d" % off)
            node = Node(tag, typ, body.decode(enc))
        off += ln
        skipped = 0
        while off < end and data[off] == PAD and skipped < 3:
            off += 1
            skipped += 1
        out.append(node)
    return out


def dump(root):
    header = root.value if root.value in ENDIAN else MAGIC
    fmt, enc = ENDIAN[header]
    return header + b"".join(rec + pad for rec, pad in (_dump_node(c, fmt, enc) for c in root.children))


def _dump_node(n, fmt, enc):
    """-> (record, padding). Kept apart because a container's stored length stops at its last
    child's payload: the last child's padding becomes the container's own padding (this rule
    is what took the round trip from 395/503 to 503/503 byte-identical files)."""
    if n.type == INTEGER:
        return struct.pack(fmt, n.tag, n.type, n.value), b""
    if n.type == STRING:
        body = n.value.encode(enc)
    else:
        parts = [_dump_node(c, fmt, enc) for c in n.children]
        body = b"".join(rec + pad for rec, pad in parts[:-1]) + (parts[-1][0] if parts else b"")
    rec = struct.pack(fmt, n.tag, n.type, 8 + len(body)) + body
    # recomputed from the new length, so an edited string stays aligned
    return rec, bytes([PAD]) * _pad_len(len(rec))


def load(path):
    with open(path, "rb") as fh:
        return parse(fh.read())


def save(root, path):
    with open(path, "wb") as fh:
        fh.write(dump(root))


# ----------------------------------------------------------------------------- semantics
def info(root):
    top = root.find(0x1000)
    about = top.find(0x1001) if top else None
    out = {}
    if about is not None:
        for tag, key in ((0x1010, "name"), (0x1014, "category"), (0x1016, "based_on"),
                         (0x1017, "created_by"), (0x1015, "comments")):
            n = about.find(tag)
            if n is not None:
                out[key] = n.text
    lists = top.find(0x1002) if top else None
    if lists is not None:
        for tag, key in ((0x1021, "author_list_a"), (0x1022, "author_list_b")):
            blk = lists.find(tag)
            if blk is not None:
                out[key] = author_list(blk)
    return out


def author_list(blk):
    ranges = []
    for r in (blk.find(0x1074).children if blk.find(0x1074) is not None else []):
        ranges.append({"from": _int(r, 0x1079), "to": _int(r, 0x107A),
                       "separator": _txt(r, 0x107B), "before_last": _txt(r, 0x107C)})
    ab = blk.find(0x1075)
    abbrev = None
    if ab is not None:
        abbrev = {"on": _int(ab, 0x107D), "if_at_least": _int(ab, 0x107E),
                  "list_first": _int(ab, 0x107F), "et_al": _txt(ab, 0x1081)}
    return {"ranges": ranges, "abbreviated": abbrev}


def _int(n, tag):
    c = n.find(tag)
    return c.value if c is not None and c.type == INTEGER else None


def _txt(n, tag):
    c = n.find(tag)
    return c.text if c is not None else None


STYLE_BITS = {1: "bold", 2: "italic"}   # verified 261023 against a CWYW-rendered bibliography


def bibliography_templates(root):
    """Yield (type code, [element]) for every bibliography template (section 1002/1023).

    An element is {field, prefix, suffix, bits}: field id (RefTypeTable numbering), the text
    before/after it, and its character-style bits (1 bold, 2 italic). Section 1002 was
    confirmed as the bibliography by editing a template and reading the CWYW output."""
    bib = root.find(0x1000, 0x1002, 0x1023)
    for t in (bib.children if bib is not None else []):
        if t.tag != 0x10A0 or t.find(0x10A1) is None:
            continue
        elems = []
        for e in (t.find(0x10A2).children if t.find(0x10A2) is not None else []):
            if e.tag != 0x1090:
                continue
            elems.append({"field": _int(e, 0x1091), "prefix": _txt(e, 0x1094) or "",
                          "suffix": _txt(e, 0x1095) or "", "bits": _int(e.find(0x1092), 0x0012)
                          if e.find(0x1092) is not None else 0})
        yield t.find(0x10A1).value, elems


def render_template(elems, field_names):
    """Template as the GUI would show it: *italic*, **bold**, field labels by name."""
    out = []
    for e in elems:
        if e["field"] == 0:          # closing element of every template; meaning unverified
            out.append("%s<end>%s" % (e["prefix"], e["suffix"]))
            continue
        name = field_names.get(e["field"], "field#%s" % e["field"])
        bits = e["bits"] or 0
        if bits & 2:
            name = "*%s*" % name
        if bits & 1:
            name = "**%s**" % name
        out.append("%s%s%s" % (e["prefix"], name, e["suffix"]))
    return "".join(out).replace("\xa0", "·")


def set_text(node, text):
    """Set a string or rich-text node. Refuses a length change when formatting runs start
    inside the text (0021 > 0022 > 0023 is a character offset; shifting the text would move
    italic/bold onto the wrong characters)."""
    target = node if node.type == STRING else node.find(0x0020)
    if target is None:
        raise FormatError("node %04x holds no text" % node.tag)
    runs = node.find(0x0021) if node.type == CONTAINER else None
    inner = [_int(r, 0x0023) for r in (runs.children if runs is not None else [])]
    if len(text) != len(target.value) and any((o or 0) > 0 for o in inner):
        raise FormatError("text %r carries formatting runs at offsets %s; a length change would "
                          "misplace them — edit in the EndNote GUI or keep the length" % (target.value, inner))
    target.value = text


def strings(root):
    """Yield (path, text) for every string, path as '1000/1002/...'."""
    def walk(node, path):
        for c in node.children:
            p = path + ["%04x" % c.tag]
            if c.type == STRING:
                yield "/".join(p), c.value
            elif c.type == CONTAINER:
                yield from walk(c, p)
    yield from walk(root, [])


def node_at(root, path):
    """'1002/1021/1075/1081' (hex tags, first match at each level; the leading 1000 optional)."""
    tags = [int(t, 16) for t in path.strip("/").split("/")]
    if tags[0] != 0x1000:
        tags = [0x1000] + tags
    return root.find(*tags)


# ----------------------------------------------------------------------------- CLI
def _print_tree(node, depth, max_depth):
    for c in node.children:
        pad = "  " * depth
        if c.type == CONTAINER:
            rt = c.text if c.find(0x0021) is not None else None
            print("%s%04x {%s" % (pad, c.tag, (" %r" % rt) if rt is not None else ""))
            if max_depth is None or depth + 1 < max_depth:
                _print_tree(c, depth + 1, max_depth)
        elif c.type == STRING:
            print("%s%04x %r" % (pad, c.tag, c.value[:80]))
        else:
            print("%s%04x = %d" % (pad, c.tag, c.value))


def _template_node(root, type_code, field_id):
    bib = root.find(0x1000, 0x1002, 0x1023)
    for t in (bib.children if bib is not None else []):
        if t.tag == 0x10A0 and t.find(0x10A1) is not None and t.find(0x10A1).value == type_code:
            for e in t.find(0x10A2).children:
                if e.tag == 0x1090 and _int(e, 0x1091) == field_id:
                    return e
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("dump"); p.add_argument("ens"); p.add_argument("--depth", type=int)
    p = sub.add_parser("info"); p.add_argument("ens")
    p = sub.add_parser("strings"); p.add_argument("ens")
    p = sub.add_parser("templates", help="bibliography templates in GUI notation")
    p.add_argument("ens"); p.add_argument("--type", help="only this reference type (name)")
    p = sub.add_parser("replace", help="set the first node at a hex tag path")
    p.add_argument("ens"); p.add_argument("out")
    p.add_argument("--path", required=True); p.add_argument("--text"); p.add_argument("--int", type=int)
    p = sub.add_parser("set-template", help="edit one field of one bibliography template")
    p.add_argument("ens"); p.add_argument("out")
    p.add_argument("--type", required=True, help="reference type name, e.g. 'Journal Article'")
    p.add_argument("--field", required=True, type=int, help="field id (see `templates`)")
    p.add_argument("--prefix"); p.add_argument("--suffix")
    p.add_argument("--bits", type=int, help="character style bits: 0 plain, 1 bold, 2 italic, 3 both")
    args = ap.parse_args(argv)

    try:
        root = load(args.ens)
    except (OSError, FormatError) as exc:
        print("[ERR] %s" % exc)
        return 2
    if args.cmd == "dump":
        _print_tree(root, 0, args.depth)
        return 0
    if args.cmd == "info":
        import json
        print(json.dumps(info(root), indent=1, ensure_ascii=False))
        return 0
    if args.cmd == "strings":
        for path, t in strings(root):
            print("%s	%r" % (path, t))
        return 0
    import en_reftypes
    types = en_reftypes.load()
    if args.cmd == "templates":
        names = en_reftypes.fields()
        only = en_reftypes.code_for(args.type, types) if args.type else None
        for code, elems in bibliography_templates(root):
            if only is None or code == only:
                print("%-24s %s" % (types.get(code, code), render_template(elems, names.get(code, {}))))
        return 0

    if os.path.abspath(args.out) == os.path.abspath(args.ens):
        print("[ERR] write to a new file; the original style stays as the backup")
        return 2
    try:
        if args.cmd == "replace":
            node = node_at(root, args.path)
            if node is None:
                raise FormatError("no node at %s" % args.path)
            if args.int is not None:
                if node.type != INTEGER:
                    raise FormatError("%s is not an integer node" % args.path)
                node.value = args.int
            elif args.text is not None:
                set_text(node, args.text)
            else:
                raise FormatError("give --text or --int")
        else:
            code = en_reftypes.code_for(args.type, types)
            e = _template_node(root, code, args.field)
            if e is None:
                raise FormatError("the %s template has no field %d" % (args.type, args.field))
            if args.prefix is not None:
                set_text(e.find(0x1094), args.prefix)
            if args.suffix is not None:
                set_text(e.find(0x1095), args.suffix)
            if args.bits is not None:
                e.find(0x1092, 0x0012).value = args.bits
    except (FormatError, KeyError) as exc:
        print("[ERR] %s" % (exc.args[0] if exc.args else exc))
        return 2
    save(root, args.out)
    load(args.out)                                    # the written file must parse back
    print("written %s" % args.out)
    if args.cmd == "set-template":
        for c, elems in bibliography_templates(load(args.out)):
            if c == code:
                print("  now: %s" % render_template(elems, en_reftypes.fields().get(code, {})))
    return 0


if __name__ == "__main__":
    sys.exit(main())
