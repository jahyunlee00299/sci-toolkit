"""manuscript_ref_order.py — Heading-guided figure/table citation-order audit.

Diagnoses whether a Fig/Table/Scheme citation-order problem should be fixed by
INSERTING A MISSING REFERENCE (in the section that discusses the item) vs MOVING A
CAPTION — using the heading/sub-heading outline as the ground-truth logical order.
Headings reflect the paper's intended flow, so an item cited "late" is usually a
missing earlier reference, not a caption that needs moving.

Reports, per manuscript:
  - OUTLINE (headings; bibliography + captions excluded)
  - FIRST-REFERENCE ORDER: which section each item is first cited in
  - ORDER CHECK: first-cite order vs numeric order, per kind
  - PHANTOM CITATIONS: numbers cited in body with NO matching caption
  - NEVER REFERENCED: captions with zero body citation
  - SUPPLEMENTARY REFS EXCLUDED: count of Fig.Sx/Table.Sx skipped (disclosed)

HARDENED against 6 verified failure modes (C-40 adversarial gate, 260706):
  1. [INSERTED]/[DRAFT]/data-pending lines -> flagged as AUDIT UNRELIABLE, not counted
  2. supplementary "Fig. S7" -> excluded from main order AND disclosed (not silently)
  3. captions mis-styled as Heading N -> caption-guarded on BOTH heading branches
  4. bibliography entries -> excluded from headings (BIB_LINE + in_refs)
  5. cross-section MISMATCH (Methods forward-ref vs Results) -> flagged, not called a defect
  6. phantom citations (cited-but-no-caption) -> reported (bidirectional set diff)

Read-only; never edits. Fix actions (insert ref / move caption) are the author's.

Usage: python manuscript_ref_order.py "<abs path to .docx>"
"""
import os, sys, re, io

# Windows 기본 콘솔은 cp949 라서 한글/기호 출력에서 죽는다. UTF-8로 맞춘다.
# TextIOWrapper 대신 reconfigure — 래퍼는 원본 스트림을 소유해서,
# import 후 GC 되면 호출자의 stdout 까지 닫아버린다(실측).
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
from docx import Document

EXT = "." + "docx"
CAP = re.compile(r"^\s*(Figures?|Figs?\.|Tables?|Schemes?)\s*\d+", re.IGNORECASE)
# numbered heading like "2", "2.6", "3.3.1  Title" at paragraph start
NUM_HEAD = re.compile(r"^\s*(\d+(?:\.\d+){0,3})\.?\s+([A-Z][^\n]{2,80})$")
# Reference to a MAIN figure/table/scheme. Negative lookbehind (?<![SsA-Za-z]) drops
# "Fig. S7" (supplementary) and any letter-prefixed match; requires the number NOT be
# immediately preceded by 'S'. We match the base number + optional panel letter.
REF = re.compile(r"(Fig(?:ure)?s?|Tables?|Schemes?)\.?\s*(?![Ss]\d)(\d+)([a-z])?", re.IGNORECASE)
# A supplementary reference "Fig. S7" / "Table S2" — to EXCLUDE from main-order.
SUPP_REF = re.compile(r"(Fig(?:ure)?s?|Tables?|Schemes?)\.?\s*[Ss]\d+", re.IGNORECASE)
# Draft / inserted / data-pending markers — lines carrying these are NOT final text.
DRAFT_LINE = re.compile(
    r"\[(?:DRAFT|INSERTED|TODO|FIXME|TBD|PLACEHOLDER)|DATA PENDING|미수령|미완성|충전 필요|수령 후",
    re.IGNORECASE)
# A bibliography entry masquerading as a numbered heading: "12. A. B. Author, Journal, 2020, ..."
# Heuristic: has a 4-digit year, OR author-initials pattern "X. Y." + a comma list.
BIB_LINE = re.compile(r"(19|20)\d{2}\b.*\d|[A-Z]\.\s?[A-Z]\.\s|et al\.", re.IGNORECASE)


def kind_of(word):
    w = word.lower()
    if w.startswith("fig"):
        return "Figure"
    if w.startswith("table"):
        return "Table"
    if w.startswith("scheme"):
        return "Scheme"
    return word


def main(path):
    d = Document(path)
    outline = []  # (para_index, level, title)
    refs_in_section = {}  # section_title -> ordered list of (kind,num)
    all_paras = list(d.paragraphs)

    cur = "(front matter)"
    order_seen = []  # (kind, num, section) first-appearance order across doc
    seen_first = set()

    in_refs = False  # once we hit the References/Bibliography section, stop treating
                     # numbered lines as headings and ignore refs inside citations
    supp_only = []   # supplementary "Fig. Sx" refs (EXCLUDED from main order, disclosed)
    supp_count = 0
    draft_lines = []  # (para_index, text) of draft/placeholder lines — audit is
                      # UNRELIABLE if these carry figure refs
    for i, p in enumerate(all_paras):
        t = p.text.strip()
        style = (p.style.name or "").lower() if p.style else ""
        if re.match(r"^\s*(references|bibliography|literature cited)\b", t, re.IGNORECASE):
            in_refs = True
        is_head = False
        title = None
        level = None
        # Word heading STYLE — but a caption erroneously styled Heading N must NOT be
        # taken as a section title (symmetric with the NUM_HEAD guard below).
        if "heading" in style and t and not CAP.match(t):
            is_head = True
            title = t
            level = style
        else:
            m = NUM_HEAD.match(t)
            if (m and not CAP.match(t) and len(t) < 90
                    and not in_refs and not BIB_LINE.search(t)):
                is_head = True
                title = t
                level = "num:" + m.group(1)
        if is_head:
            cur = title
            outline.append((i, level, title))
            refs_in_section.setdefault(cur, [])
            continue
        # count supplementary refs (disclosed, not counted in main order)
        s_here = SUPP_REF.findall(t)
        supp_count += len(s_here)
        for sm in SUPP_REF.finditer(t):
            supp_only.append((kind_of(sm.group(1)), sm.group(0)))
        # draft/placeholder lines: record if they carry a figure ref, then SKIP.
        if DRAFT_LINE.search(t):
            if REF.search(t):
                draft_lines.append((i, t[:90]))
            continue
        # skip caption paragraphs and the ref-list body
        if CAP.match(t) or in_refs:
            continue
        # strip supplementary tokens so "Fig. S7" cannot leak a bare "7" into REF
        t_main = SUPP_REF.sub(" ", t)
        for m in REF.finditer(t_main):
            kind = kind_of(m.group(1))
            num = int(m.group(2))
            refs_in_section.setdefault(cur, []).append((kind, num))
            key = (kind, num)
            if key not in seen_first:
                seen_first.add(key)
                order_seen.append((kind, num, cur))

    print(f"\n{'='*66}\nFILE: {os.path.basename(path)}\n{'='*66}")

    # === RELIABILITY GATE: draft/placeholder figure lines invalidate the audit ===
    if draft_lines:
        print(f"\n!!! DRAFT/PLACEHOLDER LINES CARRY FIGURE REFS — AUDIT UNRELIABLE ({len(draft_lines)}) !!!")
        print("    This manuscript still has [INSERTED]/[DRAFT]/data-pending caption text in the body.")
        print("    Fix the draft state FIRST; ORDER CHECK / NEVER-REFERENCED below cannot be trusted.")
        for idx, txt in draft_lines[:12]:
            print(f"    para#{idx}: {txt!r}")

    # === caption set (final captions only — real caption paragraphs START with the label) ===
    caps = set()
    for p in all_paras:
        m = re.match(r"^\s*(Figures?|Figs?\.|Tables?|Schemes?)\s*(\d+)\.", p.text.strip(), re.IGNORECASE)
        if m:
            caps.add((kind_of(m.group(1)), int(m.group(2))))

    print("\n--- OUTLINE (headings) ---")
    for _, lvl, title in outline[:60]:
        print(f"  [{lvl}] {title[:70]}")

    print("\n--- FIRST-REFERENCE ORDER (kind num @ section) ---")
    for kind, num, sec in order_seen:
        print(f"  {kind} {num:<3} first cited in: {sec[:60]!r}")

    print("\n--- ORDER CHECK ---")

    def major_sec(sectitle):
        m = re.match(r"\s*(\d+)", sectitle or "")
        return int(m.group(1)) if m else None

    by_kind = {}
    firstsec = {}  # (kind,num) -> section title of first cite
    for kind, num, sec in order_seen:
        by_kind.setdefault(kind, []).append(num)
        firstsec.setdefault((kind, num), sec)
    for kind, nums in by_kind.items():
        expected = sorted(nums)
        if nums == expected:
            print(f"  {kind}: OK")
            continue
        # A mismatch is only a REAL Results-order problem if the out-of-order items
        # are first-cited in the SAME major section. If one is first-cited in
        # Methods (a forward reference) and another in Results, that is an
        # apples-to-oranges comparison, NOT a caption-order defect (verifier's
        # a sugar Table [2,1,3] false positive).
        majors = {n: major_sec(firstsec.get((kind, n), "")) for n in nums}
        distinct_majors = set(v for v in majors.values() if v is not None)
        note = ""
        if len(distinct_majors) > 1:
            note = (f"  [cross-section: first-cites span major sections {sorted(distinct_majors)} "
                    f"({ {n: majors[n] for n in nums} }) — likely a Methods forward-ref, "
                    f"NOT a Results ordering defect; verify before acting]")
        print(f"  {kind}: MISMATCH: cited {nums} vs sorted {expected}{note}")

    cited = {(k, n) for k, n, _ in order_seen}

    # (c) PHANTOM: cited a number that has NO caption (dead draft ref or typo)
    phantom = sorted(cited - caps)
    if phantom:
        print("\n--- PHANTOM CITATIONS (cited in body, NO matching caption) ---")
        for k, n in phantom:
            print(f"  {k} {n}   <- likely leftover draft text or a numbering error")

    # NEVER REFERENCED
    missing = sorted(caps - cited)
    if missing:
        print("\n--- NEVER REFERENCED (caption exists, no body ref) ---")
        for k, n in missing:
            print(f"  {k} {n}")

    # (a) DISCLOSE supplementary refs excluded from the main-order audit
    if supp_count:
        uniq = sorted(set(x[1] for x in supp_only))
        print(f"\n--- SUPPLEMENTARY REFS EXCLUDED (not part of main-order check): {supp_count} ---")
        print(f"    {uniq[:20]}")
        print("    (SI cross-refs are intentionally out of scope; 'OK' above does NOT cover these.)")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__ or "")
        print("사용: python manuscript_ref_order.py <manuscript.docx>")
        print()
        print("본문의 Figure/Table 인용 번호가 실제로 등장하는 순서를 캡션 순서와")
        print("대조해, 인용이 번호순을 벗어난 곳을 찾아낸다. 'PHANTOM CITATION'")
        print("(캡션 없는 인용)과 'NEVER REFERENCED'(인용 없는 캡션)는 순서 문제가")
        print("아니라 각각 다른 원인이므로 구분해서 보고한다.")
        sys.exit(0 if len(sys.argv) >= 2 else 2)
    main(sys.argv[1])
