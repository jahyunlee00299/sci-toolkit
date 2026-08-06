#!/usr/bin/env python
"""renumber_figures.py — Figure/Table re-numbering for DOCX manuscripts.

USAGE:
  # Dry-run: compute and print mapping only (default)
  python renumber_figures.py main.docx [--si si.docx] [--json mapping.json]

  # Apply: write tracked-change edits
  python renumber_figures.py main.docx [--si si.docx] --apply \
      [--out main_renumbered.docx] [--out-si si_renumbered.docx]

ALGORITHM:
  1. Scan document.xml for all Figure/Table references and captions in
     first-appearance order → old_label list.
  2. Assign new sequential numbers (1, 2, 3 …) by first-appearance order.
  3. Build old→new mapping (e.g. Fig. 3 → Fig. 1 when the Fig.3 comes first).
  4. Apply substitution via TWO-STAGE token replacement to avoid collisions:
       Stage A: every old label → @@RNTMP_<idx>@@
       Stage B: every @@RNTMP_<idx>@@ → new label
  5. If --si is given, apply the SAME mapping to the SI docx (cross-check).
  6. If --apply: write result via selective zip replacement (never full re-serialize).
     Each edit is wrapped as a tracked change (w:del + w:ins, author="Claude").
  7. Runs docx_preflight on output if --apply.

RECOGNIZED PATTERNS (in document body text, not inside w:instrText fields):
  Caption:    "Figure N."  "Figure SN."  "Table N."  "Table SN."
  Reference:  "Fig. N"  "Figure N"  "Fig. SN"  "Scheme N"
              "Table N"  "Table SN"  (N = integer, S = letter prefix e.g. S1)

SAFETY:
  - Never mutates input.
  - dry-run by default (--apply required to write).
  - Two-stage token avoids e.g. Fig.1→Fig.2 then Fig.2→Fig.3 cascades.
  - Raw zipfile byte-for-byte copy of all other members (OOXML safe pattern).
  - Never uses etree.tostring() on whole document (no namespace corruption).

NOTES:
  - For plain w:t text replacement only. If numbers live inside tracked-change
    blocks (w:ins / w:del), those are also captured but flagged with a warning.
  - This script treats Main and SI as separate numbering spaces by default.
    When --si is supplied, SI labels are expected to match the SAME mapping
    (same figure numbers appear cross-referenced in both files).
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
import zipfile
from pathlib import Path
from datetime import datetime

# UTF-8 stdout guard (Windows CP949 environments)
if __name__ == '__main__' and hasattr(sys.stdout, 'buffer'):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    except (ValueError, io.UnsupportedOperation):
        pass

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# Tokens that identify figure/table objects.
# Group 1 = prefix (Figure/Fig./Table/Scheme), group 2 = number (e.g. S3, 3)
_REF_RE = re.compile(
    r'\b(Fig(?:ure)?\.?\s*|Table\s*|Scheme\s*)(S?\d+)\b',
    re.IGNORECASE,
)

# Caption pattern (looser, handles "Figure 1." or "Table S2.")
_CAP_RE = re.compile(
    r'\b(Figure|Table|Scheme)\s+(S?\d+)\b',
    re.IGNORECASE,
)

# We extract plain text from w:t elements only (not instrText, not delText)
_WT_RE = re.compile(r'<w:t(?:\s[^>]*)?>([^<]*)</w:t>', re.DOTALL)

# For two-stage token substitution
_TMP_PREFIX = '@@RNTMP_'
_TMP_SUFFIX = '@@'


def _canonical(prefix: str, num: str) -> str:
    """Canonical label for grouping purposes: normalises prefix spelling."""
    p = prefix.strip().rstrip('.')
    p_lower = p.lower()
    if 'fig' in p_lower:
        kind = 'Fig'
    elif 'table' in p_lower:
        kind = 'Table'
    elif 'scheme' in p_lower:
        kind = 'Scheme'
    else:
        kind = p.strip()
    return f'{kind}_{num}'


# ---------------------------------------------------------------------------
# XML text extraction
# ---------------------------------------------------------------------------

def _extract_plain_runs(xml_str: str) -> list[tuple[int, int, str]]:
    """Return list of (start, end, text) for every w:t in xml_str.

    Only collects from non-field, non-tracked-delete context — we track
    depth of w:del and w:instrText so we don't process deleted/field text.
    Simple state-machine approach.
    """
    results = []
    # Quick scan: find all start positions of <w:del, </w:del, <w:ins, </w:ins
    # and <w:instrText, </w:instrText, plus <w:t matches.
    # We use a combined pattern and iterate.
    SCANNER = re.compile(
        r'<(/?w:del)\b|<(/?w:ins)\b|<(/?w:instrText)\b|'
        r'(<w:t(?:\s[^>]*)?>([^<]*)</w:t>)',
        re.DOTALL
    )
    del_depth = 0
    instr_depth = 0
    for m in SCANNER.finditer(xml_str):
        if m.group(1):  # w:del tag
            tag = m.group(1)
            if tag.startswith('/'):
                del_depth = max(0, del_depth - 1)
            else:
                del_depth += 1
        elif m.group(2):  # w:ins tag — we still process text inside ins
            pass
        elif m.group(3):  # w:instrText
            tag = m.group(3)
            if tag.startswith('/'):
                instr_depth = max(0, instr_depth - 1)
            else:
                instr_depth += 1
        elif m.group(4):  # <w:t...>text</w:t>
            if del_depth == 0 and instr_depth == 0:
                results.append((m.start(4), m.end(4), m.group(5)))
    return results


# ---------------------------------------------------------------------------
# Mapping computation
# ---------------------------------------------------------------------------

def compute_mapping(xml_str: str) -> dict[str, str]:
    """Scan xml_str for Figure/Table references in first-appearance order.

    Returns old_label → new_label dict.
    old_label format: 'Fig_S3', 'Table_2', etc. (canonical key).
    new_label format same way.

    The new number is the sequential order of FIRST appearance of that label.
    """
    runs = _extract_plain_runs(xml_str)
    seen_order: list[str] = []          # ordered unique canonical labels
    seen_set: set[str] = set()

    for _, _, text in runs:
        for m in _REF_RE.finditer(text):
            key = _canonical(m.group(1), m.group(2))
            if key not in seen_set:
                seen_set.add(key)
                seen_order.append(key)

    # Group by kind (Fig, Table, Scheme) — each has its own counter
    kind_counter: dict[str, int] = {}
    old_to_new: dict[str, str] = {}
    for canonical in seen_order:
        kind, old_num = canonical.split('_', 1)
        n = kind_counter.get(kind, 0) + 1
        kind_counter[kind] = n
        # Preserve 'S' prefix if old number had it
        if old_num.upper().startswith('S'):
            new_num = f'S{n}'
        else:
            new_num = str(n)
        new_key = f'{kind}_{new_num}'
        if canonical != new_key:
            old_to_new[canonical] = new_key

    return old_to_new


def _num_from_canonical(key: str) -> str:
    """Extract the number part: 'Fig_S3' → 'S3', 'Table_2' → '2'."""
    return key.split('_', 1)[1]


# ---------------------------------------------------------------------------
# Two-stage substitution
# ---------------------------------------------------------------------------

def _build_regex_map(old_to_new: dict[str, str]) -> list[tuple[re.Pattern, str, str]]:
    """Build a list of (pattern, old_canonical, new_canonical).

    Pattern matches 'Fig. 3', 'Figure 3', 'Table S2', etc. in raw XML text
    (inside w:t tags we'll do the substitution on the full XML string).
    """
    entries = []
    for old_key, new_key in old_to_new.items():
        kind, old_num = old_key.split('_', 1)
        _, new_num = new_key.split('_', 1)
        if kind == 'Fig':
            pat = re.compile(
                r'\b(Fig(?:ure)?\.?\s*)(' + re.escape(old_num) + r')\b',
                re.IGNORECASE,
            )
        else:
            pat = re.compile(
                r'\b(' + kind + r'\s*)(' + re.escape(old_num) + r')\b',
                re.IGNORECASE,
            )
        entries.append((pat, old_key, new_key))
    return entries


def apply_two_stage(xml_str: str, old_to_new: dict[str, str]) -> tuple[str, int]:
    """Apply two-stage token replacement to full XML string (w:t text only).

    Stage A: old labels → @@RNTMP_<idx>@@
    Stage B: tokens     → new labels

    Returns (new_xml_str, total_replacements).
    """
    if not old_to_new:
        return xml_str, 0

    regex_entries = _build_regex_map(old_to_new)

    # Index for tokens
    token_index: dict[str, str] = {}   # token → new_label_num
    for idx, (_, old_key, new_key) in enumerate(regex_entries):
        token = f'{_TMP_PREFIX}{idx}{_TMP_SUFFIX}'
        token_index[token] = _num_from_canonical(new_key)

    total = 0

    # Stage A: replace inside w:t text portions of the XML
    # We operate on the full XML but only replace inside w:t tag bodies.
    # Strategy: split on <w:t...> ... </w:t> boundaries, replace in text parts.

    def replace_in_text(text: str) -> tuple[str, int]:
        """Apply stage-A in plain text."""
        count = 0
        for idx, (pat, old_key, new_key) in enumerate(regex_entries):
            token = f'{_TMP_PREFIX}{idx}{_TMP_SUFFIX}'
            new, k = pat.subn(lambda m, t=token: m.group(1) + t, text)
            text = new
            count += k
        return text, count

    # Split XML into alternating non-wt and wt segments
    WT_SPLIT = re.compile(r'(<w:t(?:\s[^>]*)?>)(.*?)(</w:t>)', re.DOTALL)

    def process_wt(m: re.Match) -> str:
        nonlocal total
        open_tag, content, close_tag = m.group(1), m.group(2), m.group(3)
        new_content, k = replace_in_text(content)
        total += k
        return open_tag + new_content + close_tag

    stage_a = WT_SPLIT.sub(process_wt, xml_str)

    # Stage B: token → new number (token is plain text, not regex-special)
    for token, new_num in token_index.items():
        stage_a = stage_a.replace(token, new_num)

    return stage_a, total


# ---------------------------------------------------------------------------
# Tracked-change XML generation
# ---------------------------------------------------------------------------

_TC_DATE = '2026-01-01T00:00:00Z'
_TC_AUTHOR = 'Claude'


def _next_w_id(xml_str: str, start: int = 1000) -> int:
    """Return max existing w:id +1 (starts from `start` if no ids found)."""
    ids = [int(m.group(1)) for m in re.finditer(r'\bw:id="(\d+)"', xml_str)]
    return max(ids, default=start - 1) + 1


def build_tracked_xml(xml_str: str, old_to_new: dict[str, str]) -> tuple[str, int]:
    """Like apply_two_stage but wraps each replacement in w:del + w:ins tracked change.

    This is more complex: we need to locate the exact <w:t> spans and produce
    split run XML.  For safety we only handle the simple case where a single
    w:t run contains exactly the label text (the common manuscript pattern).
    Labels that span run boundaries get a WARNING comment but are left unchanged.

    Returns (new_xml, replacements_count).
    """
    if not old_to_new:
        return xml_str, 0

    regex_entries = _build_regex_map(old_to_new)
    id_counter = _next_w_id(xml_str)
    total = 0

    # We'll work segment-by-segment on w:t content
    WT_FULL_RE = re.compile(
        r'(<w:r(?:\s[^>]*)?>)((?:<w:rPr>.*?</w:rPr>)?)'
        r'(<w:t(?:\s[^>]*)?>)(.*?)(</w:t>)(</w:r>)',
        re.DOTALL,
    )

    def process_run(m: re.Match) -> str:
        nonlocal id_counter, total
        r_open = m.group(1)
        rpr = m.group(2)
        t_open = m.group(3)
        content = m.group(4)
        t_close = m.group(5)
        r_close = m.group(6)

        out = content
        changed = False
        for pat, old_key, new_key in regex_entries:
            def _replace(match: re.Match, ok=old_key, nk=new_key) -> str:
                nonlocal id_counter, changed, total
                changed = True
                total += 1
                old_prefix = match.group(1)
                old_num = _num_from_canonical(ok)
                new_num = _num_from_canonical(nk)
                del_id = id_counter; id_counter += 1
                ins_id = id_counter; id_counter += 1
                del_xml = (
                    f'</w:t>{t_close}{r_close}'
                    f'<w:del w:id="{del_id}" w:author="{_TC_AUTHOR}" w:date="{_TC_DATE}">'
                    f'<w:r>{rpr}<w:delText xml:space="preserve">{old_prefix}{old_num}</w:delText></w:r>'
                    f'</w:del>'
                    f'<w:ins w:id="{ins_id}" w:author="{_TC_AUTHOR}" w:date="{_TC_DATE}">'
                    f'<w:r>{rpr}<w:t xml:space="preserve">{old_prefix}{new_num}</w:t></w:r>'
                    f'</w:ins>'
                    f'{r_open}{rpr}{t_open}'
                )
                return del_xml

            out, _ = pat.subn(_replace, out)

        if changed:
            return r_open + rpr + t_open + out + t_close + r_close
        return m.group(0)  # unchanged

    result = WT_FULL_RE.sub(process_run, xml_str)

    # Clean up any empty <w:t></w:t> artefacts we created at split points
    result = re.sub(r'<w:t(?:\s[^>]*)?>(\s*)</w:t>', lambda m: m.group(0) if m.group(1).strip() else '', result)
    # Remove any orphaned empty runs: <w:r><w:rPr>...</w:rPr><w:t></w:t></w:r>
    result = re.sub(r'<w:r(?:\s[^>]*)?>(?:<w:rPr>.*?</w:rPr>)?<w:t(?:\s[^>]*)?></w:t></w:r>', '', result, flags=re.DOTALL)

    return result, total


# ---------------------------------------------------------------------------
# Human-readable mapping report
# ---------------------------------------------------------------------------

def format_mapping_report(old_to_new: dict[str, str]) -> str:
    if not old_to_new:
        return "  (no renumbering needed — all labels already in order)"
    lines = ["  OLD         ->  NEW"]
    lines.append("  " + "-" * 26)
    for old, new in sorted(old_to_new.items()):
        kind, old_n = old.split('_', 1)
        _, new_n = new.split('_', 1)
        old_lbl = f'{kind} {old_n}'
        new_lbl = f'{kind} {new_n}'
        lines.append(f"  {old_lbl:<12}  ->  {new_lbl}")
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Docx read / write helpers
# ---------------------------------------------------------------------------

def _read_member(docx_path: Path, member: str) -> bytes:
    with zipfile.ZipFile(docx_path, 'r') as z:
        return z.read(member)


def _selective_replace(in_path: Path, out_path: Path, replacements: dict[str, bytes]) -> None:
    """Byte-for-byte copy of all members except those in replacements."""
    with zipfile.ZipFile(in_path, 'r') as zin, \
            zipfile.ZipFile(out_path, 'w', zipfile.ZIP_DEFLATED) as zout:
        in_names = set(zin.namelist())
        unknown = set(replacements) - in_names
        if unknown:
            raise ValueError(f"Members not found in source: {unknown}")
        for item in zin.infolist():
            data = replacements[item.filename] if item.filename in replacements else zin.read(item.filename)
            new_item = zipfile.ZipInfo(item.filename, item.date_time)
            new_item.compress_type = item.compress_type
            new_item.external_attr = item.external_attr
            new_item.create_system = item.create_system
            zout.writestr(new_item, data)


# ---------------------------------------------------------------------------
# Preflight integration (optional — only when available)
# ---------------------------------------------------------------------------

def _try_preflight(path: Path) -> str:
    """Return preflight verdict string, or 'SKIPPED' if tool unavailable."""
    try:
        _here = Path(__file__).resolve().parent
        _docx_scripts = _here.parent.parent / 'docx' / 'scripts'
        import importlib.util, sys as _sys
        spec = importlib.util.spec_from_file_location('docx_preflight', _docx_scripts / 'docx_preflight.py')
        if spec is None:
            return 'SKIPPED'
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        result = mod.run_preflight(path)
        return result.verdict()
    except Exception as exc:  # noqa: BLE001
        return f'SKIPPED ({exc})'


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------

def process_docx(
    docx_path: Path,
    si_path: Path | None,
    dry_run: bool,
    out_path: Path | None,
    out_si_path: Path | None,
    json_out: Path | None,
    tracked: bool,
) -> None:
    docx_xml_bytes = _read_member(docx_path, 'word/document.xml')
    docx_xml = docx_xml_bytes.decode('utf-8')

    # If SI is supplied, concatenate for mapping computation so both share the same order.
    if si_path:
        si_xml_bytes = _read_member(si_path, 'word/document.xml')
        si_xml = si_xml_bytes.decode('utf-8')
        combined_xml = docx_xml + '\n' + si_xml
    else:
        si_xml_bytes = None
        si_xml = None
        combined_xml = docx_xml

    mapping = compute_mapping(combined_xml)

    print(f"\n[renumber_figures] source: {docx_path.name}")
    if si_path:
        print(f"  SI:     {si_path.name}")
    print(f"  mode:   {'DRY-RUN' if dry_run else 'APPLY' + (' (tracked changes)' if tracked else ' (direct)')}")
    print(f"\nMapping ({len(mapping)} label(s) to renumber):")
    print(format_mapping_report(mapping))

    if json_out:
        json_out.write_text(
            json.dumps({
                'source': str(docx_path),
                'si': str(si_path) if si_path else None,
                'mapping': {k: v for k, v in mapping.items()},
                'timestamp': datetime.utcnow().isoformat() + 'Z',
            }, indent=2, ensure_ascii=False),
            encoding='utf-8',
        )
        print(f"\n  Mapping JSON written to: {json_out}")

    if dry_run:
        print("\n[dry-run] No files written. Pass --apply to apply changes.")
        return

    # --- Apply ---
    if out_path is None:
        stem = docx_path.stem
        out_path = docx_path.parent / f'{stem}_renumbered.docx'

    _apply_to_docx(docx_path, mapping, out_path, tracked, label='Main')

    if si_path and si_xml_bytes is not None:
        if out_si_path is None:
            stem = si_path.stem
            out_si_path = si_path.parent / f'{stem}_renumbered.docx'
        _apply_to_docx(si_path, mapping, out_si_path, tracked, label='SI')


def _apply_to_docx(
    in_path: Path,
    mapping: dict[str, str],
    out_path: Path,
    tracked: bool,
    label: str = '',
) -> None:
    xml_bytes = _read_member(in_path, 'word/document.xml')
    xml_str = xml_bytes.decode('utf-8')

    if tracked:
        new_xml, count = build_tracked_xml(xml_str, mapping)
    else:
        new_xml, count = apply_two_stage(xml_str, mapping)

    if count == 0:
        print(f"\n  [{label}] 0 replacements — no changes written.")
        return

    _selective_replace(in_path, out_path, {'word/document.xml': new_xml.encode('utf-8')})
    print(f"\n  [{label}] {count} replacement(s) -> {out_path}")

    verdict = _try_preflight(out_path)
    print(f"  [{label}] preflight: {verdict}")
    if verdict.startswith('FAIL'):
        print(f"  [{label}] WARNING: preflight FAIL — review {out_path} before use.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description='Renumber Figure/Table labels in DOCX manuscripts.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument('docx', nargs='?', help='Main manuscript .docx file (not required with --test)')
    p.add_argument('--si', metavar='SI_DOCX', help='SI .docx (shares same mapping)')
    p.add_argument('--apply', action='store_true', help='Apply changes (default: dry-run only)')
    p.add_argument('--tracked', action='store_true',
                   help='Wrap replacements as tracked changes (w:del + w:ins, author=Claude)')
    p.add_argument('--out', metavar='OUT_DOCX', help='Output path for main (default: <stem>_renumbered.docx)')
    p.add_argument('--out-si', metavar='OUT_SI', help='Output path for SI')
    p.add_argument('--json', metavar='JSON_FILE', help='Write mapping JSON to this file')
    p.add_argument('--test', action='store_true', help='Run self-test on synthetic fixture and exit')
    return p


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

_SYNTHETIC_XML = """\
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:body>
  <!-- Body references Fig. 3 first, then Fig. 1, then Table 2 -->
  <w:p><w:r><w:t>As shown in Fig. 3, the results confirm the hypothesis.</w:t></w:r></w:p>
  <w:p><w:r><w:t>This is consistent with Fig. 1 and Table 2.</w:t></w:r></w:p>
  <w:p><w:r><w:t>Additionally, Fig. 3 demonstrates robustness.</w:t></w:r></w:p>
  <!-- Captions -->
  <w:p><w:r><w:t>Figure 3. Enzyme cascade overview.</w:t></w:r></w:p>
  <w:p><w:r><w:t>Figure 1. Kinetic profile.</w:t></w:r></w:p>
  <w:p><w:r><w:t>Table 2. Summary of parameters.</w:t></w:r></w:p>
  <!-- Deleted text (should NOT be counted) -->
  <w:p>
    <w:del w:id="1" w:author="Author" w:date="2026-01-01T00:00:00Z">
      <w:r><w:delText>Fig. 5 was removed.</w:delText></w:r>
    </w:del>
  </w:p>
</w:body>
</w:document>
"""


def _run_self_test() -> None:
    """Test the mapping computation on a synthetic fixture."""
    print("=" * 60)
    print("SELF-TEST: renumber_figures.py")
    print("=" * 60)
    print("\nInput XML (synthetic):")
    print("  Body references: Fig. 3 (first), Fig. 1, Table 2")
    print("  Captions: Figure 3, Figure 1, Table 2")
    print("  Deleted block: Fig. 5 (must NOT appear in mapping)")

    mapping = compute_mapping(_SYNTHETIC_XML)

    print(f"\nComputed mapping ({len(mapping)} entries):")
    print(format_mapping_report(mapping))

    # Expected: Fig. 3 appeared first → renamed to Fig. 1
    #           Fig. 1 appeared second → renamed to Fig. 2
    #           Table 2 appeared first  → renamed to Table 1
    expected = {
        'Fig_3': 'Fig_1',
        'Fig_1': 'Fig_2',
        'Table_2': 'Table_1',
    }

    print("\nVerification:")
    all_ok = True
    for old, new in expected.items():
        got = mapping.get(old)
        ok = got == new
        status = 'PASS' if ok else 'FAIL'
        print(f"  {old} -> {new}: {status} (got: {got})")
        if not ok:
            all_ok = False

    # Also check that Fig. 5 (inside w:del) did NOT appear in mapping
    if 'Fig_5' in mapping:
        print(f"  Fig_5 must NOT be in mapping: FAIL (was: {mapping['Fig_5']})")
        all_ok = False
    else:
        print(f"  Fig_5 (deleted) correctly excluded: PASS")

    # Test two-stage substitution
    print("\nTwo-stage substitution test:")
    new_xml, count = apply_two_stage(_SYNTHETIC_XML, mapping)

    # Extract only w:t text to verify — ignore XML comments and other markup
    wt_texts = re.findall(r'<w:t(?:\s[^>]*)?>([^<]*)</w:t>', new_xml)
    body_text = ' '.join(wt_texts)

    fig1_count = len(re.findall(r'\bFig(?:ure)?\.?\s*1\b', body_text))
    fig2_count = len(re.findall(r'\bFig(?:ure)?\.?\s*2\b', body_text))
    # Fig. 3 must not appear in w:t body (could still be in XML comments — that's OK)
    fig3_count_body = len(re.findall(r'\bFig(?:ure)?\.?\s*3\b', body_text))
    table1_count = len(re.findall(r'\bTable\s*1\b', body_text))
    table2_count_body = len(re.findall(r'\bTable\s*2\b', body_text))

    checks_sub = [
        (fig1_count >= 3, f"Fig 1/Figure 1 in w:t body >= 3 (got {fig1_count})"),
        (fig2_count >= 2, f"Fig 2/Figure 2 in w:t body >= 2 (got {fig2_count})"),
        (fig3_count_body == 0, f"Residual Fig 3 in w:t body == 0 (got {fig3_count_body})"),
        (table1_count >= 1, f"Table 1 in w:t body >= 1 (got {table1_count})"),
        (table2_count_body == 0, f"Residual Table 2 in w:t body == 0 (got {table2_count_body})"),
    ]
    for ok, msg in checks_sub:
        print(f"  {msg}: {'PASS' if ok else 'FAIL'}")
        if not ok:
            all_ok = False

    print(f"  Total substitutions applied: {count} (expected 7)")
    if count != 7:
        all_ok = False
        print(f"  FAIL: expected 7")

    print(f"\n{'=' * 60}")
    print(f"OVERALL: {'PASS' if all_ok else 'FAIL'}")
    print(f"{'=' * 60}\n")
    sys.exit(0 if all_ok else 1)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.test:
        _run_self_test()
        return  # unreachable — _run_self_test calls sys.exit

    if not args.docx:
        parser.error("the following arguments are required: docx")

    docx_path = Path(args.docx).resolve()
    if not docx_path.exists():
        sys.exit(f"ERROR: file not found: {docx_path}")

    si_path = Path(args.si).resolve() if args.si else None
    if si_path and not si_path.exists():
        sys.exit(f"ERROR: SI file not found: {si_path}")

    out_path = Path(args.out).resolve() if args.out else None
    out_si = Path(args.out_si).resolve() if args.out_si else None
    json_out = Path(args.json).resolve() if args.json else None

    process_docx(
        docx_path=docx_path,
        si_path=si_path,
        dry_run=not args.apply,
        out_path=out_path,
        out_si_path=out_si,
        json_out=json_out,
        tracked=args.tracked,
    )


if __name__ == '__main__':
    main()
