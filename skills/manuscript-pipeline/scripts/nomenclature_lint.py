"""nomenclature_lint.py — read-only nomenclature/style linter for manuscript DOCX.

Mechanically detects a SAFE SUBSET of the academic_qc_rules.md R1~R15 rules and
reports them with location (paragraph index + leading context). This tool NEVER
modifies the document — every finding is a recommendation/flag only.

What it checks (and the source rule):
  R2  (abbrev)   : full-name term that has a standard abbreviation in
                   domain_abbrev_registry.md is used in body text
                   (e.g. "ADP-glucose" -> recommend "ADP-Glc").
  R5  (units)    : superscript minus-one notation (e.g. "g L⁻¹", "min⁻¹").
                   Recommend slash form. Only the ⁻¹ superscript is flagged
                   (spacing checks are intentionally omitted — too many FPs).
  DASH (R-range) : numeric range using ASCII hyphen ("10-14", "20-50°C") that
                   should be an en-dash (–). Heuristics exclude citation/DOI/
                   negative-number/date-like patterns.
  STAB (weak)    : "thermal stability" appearing near an activity-loss percentage
                   in the same paragraph -> stability vs instability sanity flag
                   (WARN, low-confidence signal).
  R6  (species)  : common binomial species names located in the text. italic
                   detection at run level is NOT performed here; locations are
                   reported for MANUAL italic confirmation (see risk_notes).

Usage:
    python nomenclature_lint.py <document.docx>
    python nomenclature_lint.py <document.docx> --json

Standard library + defusedxml only (matches repo deps). word/document.xml is read
directly out of the OOXML zip, so this lint has no dependency on the docx skill,
which is not shipped with this package.
"""

# Windows 기본 콘솔은 cp949 라서 한글/기호 출력에서 죽는다. UTF-8로 맞춘다.
# reconfigure 를 쓴다: TextIOWrapper 로 감싸면 원본 스트림을 소유하게 되어,
# 이 모듈이 import 된 뒤 래퍼가 GC 될 때 호출자의 stdout 까지 닫는다(실측).
import sys as _sys
for _s in (_sys.stdout, _sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

import argparse
import json
import os
import re
import sys
import zipfile
import tempfile
from pathlib import Path

import defusedxml.ElementTree as ET

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


# --------------------------------------------------------------------------- #
# DOCX extraction
# --------------------------------------------------------------------------- #
def extract_document_xml(docx_path: Path, work_dir: Path) -> Path:
    """Extract word/document.xml from the docx, return the path to it.

    Read straight out of the OOXML zip rather than shelling out to the docx
    skill's unpack.py. That skill is Anthropic-owned and is not shipped with
    this package (see docs/12), so the subprocess route made this lint — a
    mandatory gate in the AGENTS.md §0 routing table — fail with
    FileNotFoundError for every user who installed sci-toolkit alone.
    reference_validator.py in this same folder already reads the part this way.

    Read-only: the archive is never re-serialized, so the docx cannot be
    corrupted by linting it.
    """
    out_dir = work_dir / "unpacked" / "word"
    out_dir.mkdir(parents=True, exist_ok=True)
    doc_xml = out_dir / "document.xml"
    try:
        with zipfile.ZipFile(docx_path) as z:
            doc_xml.write_bytes(z.read("word/document.xml"))
    except KeyError as exc:
        raise RuntimeError(
            f"{docx_path} has no word/document.xml — not a Word document?"
        ) from exc
    except zipfile.BadZipFile as exc:
        raise RuntimeError(f"{docx_path} is not a readable .docx (bad zip)") from exc
    return doc_xml


# --------------------------------------------------------------------------- #
# Paragraph iteration (body + table cells)
# --------------------------------------------------------------------------- #
def _para_text(p) -> str:
    return "".join(t.text or "" for t in p.iter(f"{{{W}}}t"))


def _is_in_table(p) -> bool:
    anc = p.getparent() if hasattr(p, "getparent") else None
    # defusedxml/ElementTree has no getparent(); we precompute via parent map.
    return anc is not None


def iter_paragraphs(root):
    """Yield (para_index, in_table, text) for every w:p in document order.

    ElementTree has no parent pointers, so build a child->parent map to detect
    whether a paragraph sits inside a table cell (<w:tc>).
    """
    body = root.find(f"{{{W}}}body")
    if body is None:
        return
    parent_map = {c: par for par in body.iter() for c in par}
    idx = 0
    for p in body.iter(f"{{{W}}}p"):
        in_table = False
        node = parent_map.get(p)
        while node is not None:
            if node.tag == f"{{{W}}}tc":
                in_table = True
                break
            node = parent_map.get(node)
        yield idx, in_table, _para_text(p)
        idx += 1


# --------------------------------------------------------------------------- #
# Registry parsing (R2)
# --------------------------------------------------------------------------- #
def _find_registry() -> Path:
    here = Path(__file__).resolve()
    reg = here.parent.parent / "references" / "domain_abbrev_registry.md"
    return reg


# Full-names that are too generic / risky to flag mechanically (high FP).
_REGISTRY_SKIP_FULLNAMES = {
    "phosphate", "phosphate (free)",
    "branched starch", "glycogen-like α-glucan",
    "branched starch / glycogen-like α-glucan",
}


def parse_registry(reg_path: Path):
    """Parse the markdown table into [(full_name, abbrev)] pairs.

    Only keeps rows where the full name is a concrete, low-ambiguity token
    (contains a hyphen or digit, or is multiword) to reduce false positives.
    Hard-coding is avoided — pairs are read dynamically from the registry file.
    """
    pairs = []
    if not reg_path.exists():
        return pairs
    for line in reg_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cols = [c.strip() for c in line.strip("|").split("|")]
        if len(cols) < 2:
            continue
        full, abbrev = cols[0], cols[1]
        # skip header / separator rows
        if full.lower() in ("term", "") or set(abbrev) <= {"-", ":", " "}:
            continue
        if "standard abbrev" in abbrev.lower():
            continue
        if full.lower() in _REGISTRY_SKIP_FULLNAMES:
            continue
        # abbrev must look like a real abbreviation token (no spaces, has letters)
        if " " in abbrev or not re.search(r"[A-Za-z]", abbrev):
            continue
        # require the full name to be specific: hyphen, digit, or 2+ words
        if not (re.search(r"[-\d]", full) or len(full.split()) >= 2):
            continue
        pairs.append((full, abbrev))
    return pairs


# --------------------------------------------------------------------------- #
# Rule checks
# --------------------------------------------------------------------------- #
SPECIES_NAMES = [
    "Escherichia coli",
    "E. coli",
    "Saccharomyces cerevisiae",
    "Lactobacillus acidophilus",
]

# Superscript minus-one: U+207B (⁻) followed by U+00B9 (¹), optionally spaced.
_SUPERSCRIPT_INV = re.compile(r"⁻\s*¹")

# Numeric range with ASCII hyphen, e.g. "10-14", "20-50", "6.7-17.2".
_RANGE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)(?![\w])")

_STABILITY = re.compile(r"thermal\s+stability", re.IGNORECASE)
_ACTIVITY_LOSS = re.compile(r"\d+(?:\.\d+)?\s*%")


def _ctx(text: str, span_start: int, width: int = 40) -> str:
    start = max(0, span_start - width // 2)
    snippet = text[start:start + width].replace("\n", " ").strip()
    return snippet


def check_abbrev(text: str, pairs):
    """R2: registry full-name used in text -> recommend abbreviation."""
    found = []
    for full, abbrev in pairs:
        # word-ish boundaries; '-' in token means we anchor on non-word chars.
        pat = re.compile(r"(?<![\w-])" + re.escape(full) + r"(?![\w-])",
                         re.IGNORECASE)
        for m in pat.finditer(text):
            found.append((full, abbrev, m.start(), _ctx(text, m.start())))
    return found


def check_units(text: str):
    """R5: superscript ⁻¹ usage."""
    return [(m.start(), _ctx(text, m.start())) for m in _SUPERSCRIPT_INV.finditer(text)]


def check_dash(text: str):
    """Numeric-range hyphen that should be en-dash, with FP-reducing heuristics."""
    out = []
    for m in _RANGE.finditer(text):
        a, b = m.group(1), m.group(2)
        s, e = m.start(), m.end()
        # exclude likely citation/DOI/identifier contexts
        before = text[max(0, s - 6):s]
        after = text[e:e + 4]
        # DOI / URL-ish
        if "doi" in before.lower() or "/" in before[-2:] or "/" in after[:2]:
            continue
        # citation-number range inside square brackets, e.g. "[3-5]" or "[3–5]"
        if "[" in before and "]" in after:
            continue
        # date-like full year range (1900-2099 both sides) is acceptable but
        # often legitimate ranges too; keep flagging — en-dash applies to years.
        # negative number context: a minus sign immediately before first number
        if before[-1:] in "-–−" and not before[-2:-1].isdigit():
            continue
        # ascending range sanity: only flag when b >= a (true ranges)
        try:
            if float(b) < float(a):
                continue
        except ValueError:
            pass
        out.append((s, f"{a}-{b}", _ctx(text, s)))
    return out


def check_stability(text: str):
    """Weak signal: thermal stability mentioned alongside an activity-loss %."""
    if _STABILITY.search(text) and _ACTIVITY_LOSS.search(text):
        m = _STABILITY.search(text)
        return [(m.start(), _ctx(text, m.start()))]
    return []


def check_species(text: str):
    """R6: locate common species names (italic NOT verified here)."""
    out = []
    for name in SPECIES_NAMES:
        # "E. coli" is a substring of nothing problematic; match literally.
        pat = re.compile(r"(?<![\w])" + re.escape(name) + r"(?![\w])")
        for m in pat.finditer(text):
            # avoid double-counting "E. coli" inside "Escherichia coli" runs
            out.append((name, m.start(), _ctx(text, m.start())))
    return out


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #
def lint(docx_path: Path):
    registry_pairs = parse_registry(_find_registry())

    findings = {
        "R2_abbrev": [],
        "R5_units": [],
        "DASH_range": [],
        "STAB_flag": [],
        "R6_species": [],
    }

    with tempfile.TemporaryDirectory() as td:
        doc_xml = extract_document_xml(docx_path, Path(td))
        tree = ET.parse(str(doc_xml))
        root = tree.getroot()

        for idx, in_table, text in iter_paragraphs(root):
            if not text.strip():
                continue
            scope = "table" if in_table else "body"

            for full, abbrev, pos, ctx in check_abbrev(text, registry_pairs):
                findings["R2_abbrev"].append({
                    "para": idx, "scope": scope, "term": full,
                    "recommend": abbrev, "context": ctx,
                })
            for pos, ctx in check_units(text):
                findings["R5_units"].append({
                    "para": idx, "scope": scope, "context": ctx,
                })
            for pos, rng, ctx in check_dash(text):
                findings["DASH_range"].append({
                    "para": idx, "scope": scope, "range": rng, "context": ctx,
                })
            for pos, ctx in check_stability(text):
                findings["STAB_flag"].append({
                    "para": idx, "scope": scope, "context": ctx,
                })
            for name, pos, ctx in check_species(text):
                findings["R6_species"].append({
                    "para": idx, "scope": scope, "species": name, "context": ctx,
                })

    return findings, registry_pairs


_RULE_HEADERS = {
    "R2_abbrev": ("R2 (abbreviation, academic_qc_rules.md)",
                  "Full name used where a standard abbrev exists -> recommend abbreviation."),
    "R5_units": ("R5 (units, academic_qc_rules.md)",
                 "Superscript ⁻¹ found -> use slash form (e.g. g/L, /min)."),
    "DASH_range": ("R-range / en-dash (writing_style.md, academic-term-rules §8)",
                   "Numeric range with ASCII hyphen -> recommend en-dash (–)."),
    "STAB_flag": ("STABILITY sanity (WARN, weak signal)",
                  "'thermal stability' near an activity-loss % -> check stability vs instability."),
    "R6_species": ("R6 (species italic, academic_qc_rules.md)",
                   "Species name located -> confirm italic MANUALLY (run-level italic not checked)."),
}


def render_text(findings, registry_pairs) -> str:
    lines = []
    lines.append("=" * 72)
    lines.append("NOMENCLATURE LINT (read-only — recommendations/flags only)")
    lines.append("=" * 72)
    total = sum(len(v) for v in findings.values())
    lines.append(f"Total findings: {total}")
    lines.append(f"Registry pairs loaded for R2: {len(registry_pairs)}")
    lines.append("")
    for key in ("R2_abbrev", "R5_units", "DASH_range", "STAB_flag", "R6_species"):
        items = findings[key]
        title, desc = _RULE_HEADERS[key]
        lines.append("-" * 72)
        lines.append(f"[{title}]  count={len(items)}")
        lines.append(f"  {desc}")
        if not items:
            lines.append("  (none)")
            lines.append("")
            continue
        for it in items:
            loc = f"para {it['para']:>4} [{it['scope']}]"
            if key == "R2_abbrev":
                detail = f"'{it['term']}' -> '{it['recommend']}'"
            elif key == "DASH_range":
                detail = f"'{it['range']}'"
            elif key == "R6_species":
                detail = f"'{it['species']}'"
            else:
                detail = ""
            ctx = it["context"]
            lines.append(f"  {loc}  {detail}")
            lines.append(f"        ...{ctx}...")
        lines.append("")
    lines.append("=" * 72)
    lines.append("NOTE: No automatic fixes applied. All items are advisory.")
    lines.append("R6 species: italic state NOT verified — confirm in Word manually.")
    lines.append("=" * 72)
    return "\n".join(lines)


def main():
    # Ensure UTF-8 stdout (Windows consoles default to cp949/cp1252 and choke
    # on en-dash / superscript characters in the report).
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    ap = argparse.ArgumentParser(
        description="Read-only nomenclature/style linter for manuscript DOCX "
                    "(detects a safe subset of academic_qc_rules.md R1~R15)."
    )
    ap.add_argument("docx", help="Path to the .docx file to lint")
    ap.add_argument("--json", action="store_true", help="Emit JSON instead of text report")
    args = ap.parse_args()

    docx_path = Path(args.docx)
    if not docx_path.exists():
        print(f"Error: {docx_path} does not exist", file=sys.stderr)
        sys.exit(1)

    findings, registry_pairs = lint(docx_path)

    if args.json:
        out = {
            "document": str(docx_path),
            "total": sum(len(v) for v in findings.values()),
            "registry_pairs": len(registry_pairs),
            "findings": findings,
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(render_text(findings, registry_pairs))


if __name__ == "__main__":
    main()
