#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""numeric_consistency_check.py — manuscript-pipeline Phase 3 self-review helper.

Scans a manuscript .docx (and optional Table/figure CSV sidecars) and reports:
  1. Numeric conflicts: same labelled quantity (e.g. sEF, titer, yield) carrying
     different values across body text / tables / figure CSVs.  This is the
     "single source of truth" check (e.g. a metric reported in the body, a table,
     and a figure CSV that disagree — the canonical kind of incident this catches).
  2. Untraceable figures/tables: a "Figure N" / "Table N" cited in body text but with
     no corresponding caption, or a captioned float never cited in the body.

It is a *reviewer*, not an editor — it never modifies the manuscript.  Output is a
JSON report (machine-checkable) plus a human summary; exit code is non-zero when any
hard finding (conflict or untraceable float) is present, so it can gate a workflow.

Usage:
  python numeric_consistency_check.py MANUSCRIPT.docx [--csv DIR_OR_GLOB ...]
                                       [--json OUT.json] [--tol 0.02]

--tol is the relative tolerance below which two numbers for the same label are
treated as "the same" (default 2%, accommodating rounding such as 1.816 -> 1.8).
"""
from __future__ import annotations

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
import csv
import glob
import io
import json
import os
import re
import sys
import zipfile

# UTF-8 stdout guard (Korean Windows console)
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


# --- docx text extraction (no python-docx dependency: read the zip directly) ---

def docx_paragraphs(path):
    """Yield paragraph plain-text strings from a .docx in document order."""
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    # Each <w:p ...>...</w:p> is one paragraph. Concatenate <w:t> runs inside.
    for p_match in re.finditer(r"<w:p[ >].*?</w:p>", xml, re.DOTALL):
        block = p_match.group(0)
        texts = re.findall(r"<w:t[^>]*>(.*?)</w:t>", block, re.DOTALL)
        para = "".join(texts)
        # unescape the handful of XML entities Word emits
        para = (para.replace("&amp;", "&").replace("&lt;", "<")
                    .replace("&gt;", ">").replace("&quot;", '"').replace("&apos;", "'"))
        if para.strip():
            yield para


# --- numeric extraction ---

# A labelled quantity: a token (sEF, cEF, titer, yield, conversion, ee) optionally
# with "= : of" then a number with optional unit. We capture (label, value, unit, context).
NUM = r"[-+]?\d+(?:\.\d+)?"
# Known quantity keywords worth cross-checking (case-insensitive, word-ish boundaries).
QUANTITY_KEYS = [
    "sEF", "cEF", "E-factor", "Efactor",
    "titer", "titre",
    "yield", "conversion", "selectivity",
    "ee", "de",
    "MPSP",
    "productivity", "STY",
    "TON", "TOF",
]


def _find_quantities(text, source):
    """Return list of dicts {label, value, unit, source, context} found in text.

    De-duplicated per (label, value, unit) within a single text block so that a
    quantity is not double-counted when several keys (e.g. "E-factor" and "sEF")
    sit next to the same number.
    """
    out, seen = [], set()
    for key in QUANTITY_KEYS:
        # label, then up to a short run of separators/words/punctuation
        # (handles "sEF) of 1.8", "titer = 10.3 g/L", "yield of 42.6%",
        #  "sEF reached 2.0"), then a number and optional unit.
        pat = re.compile(
            r"(?P<label>" + re.escape(key) + r")"
            r"[\s):=]*"
            r"(?:was|is|of|at|reached|reaching|equal\s+to)?[\s):=]*"
            r"(?P<value>" + NUM + r")"
            r"\s*(?P<unit>%|g/L|g/g|U/mL|mM|M|\$/kg|kg|mol/mol)?",
            re.IGNORECASE,
        )
        for m in pat.finditer(text):
            value = float(m.group("value"))
            unit = (m.group("unit") or "").strip()
            dedup = (_norm_label(key), value, unit)
            if dedup in seen:
                continue
            seen.add(dedup)
            start = max(0, m.start() - 35)
            end = min(len(text), m.end() + 15)
            out.append({
                "label": key,
                "value": value,
                "unit": unit,
                "source": source,
                "context": text[start:end].replace("\n", " ").strip(),
            })
    return out


def _norm_label(label):
    return label.lower().replace("-", "").replace("_", "")


def detect_conflicts(quantities, rel_tol):
    """Group by (normalized label, unit); flag groups whose values disagree > rel_tol."""
    groups = {}
    for q in quantities:
        gkey = (_norm_label(q["label"]), q["unit"])
        groups.setdefault(gkey, []).append(q)

    conflicts = []
    for (label, unit), items in groups.items():
        vals = [it["value"] for it in items]
        vmin, vmax = min(vals), max(vals)
        if vmin == 0:
            differ = vmax != 0
        else:
            differ = (vmax - vmin) / abs(vmin) > rel_tol
        if differ and len({round(v, 6) for v in vals}) > 1:
            conflicts.append({
                "label": label,
                "unit": unit,
                "distinct_values": sorted({round(v, 6) for v in vals}),
                "occurrences": [
                    {"value": it["value"], "source": it["source"], "context": it["context"]}
                    for it in items
                ],
            })
    return conflicts


# --- figure / table traceability ---

CITE_RE = re.compile(r"\b(Figure|Fig\.?|Table|Scheme)\s*(\d+)", re.IGNORECASE)
CAPTION_RE = re.compile(r"^\s*(Figure|Fig\.?|Table|Scheme)\s*(\d+)\s*[.:—-]", re.IGNORECASE)


def _float_kind(word):
    w = word.lower().rstrip(".")
    if w in ("fig", "figure"):
        return "Figure"
    if w == "table":
        return "Table"
    if w == "scheme":
        return "Scheme"
    return word.capitalize()


def detect_float_issues(paragraphs):
    cited, captioned = set(), set()
    for para in paragraphs:
        cap = CAPTION_RE.match(para)
        if cap:
            captioned.add((_float_kind(cap.group(1)), int(cap.group(2))))
            continue  # a caption line is not also a citation of itself
        for m in CITE_RE.finditer(para):
            cited.add((_float_kind(m.group(1)), int(m.group(2))))

    cited_not_captioned = sorted(cited - captioned)
    captioned_not_cited = sorted(captioned - cited)
    return {
        "cited_without_caption": [{"kind": k, "number": n} for k, n in cited_not_captioned],
        "captioned_but_never_cited": [{"kind": k, "number": n} for k, n in captioned_not_cited],
    }


# --- CSV sidecar numbers (figure data) ---

def csv_quantities(csv_paths):
    out = []
    for path in csv_paths:
        try:
            with open(path, newline="", encoding="utf-8-sig") as fh:
                reader = csv.reader(fh)
                rows = list(reader)
        except Exception as e:
            out.append({"_error": f"{path}: {e}"})
            continue
        if not rows:
            continue
        header = [h.strip() for h in rows[0]]
        base = os.path.basename(path)
        for ci, col in enumerate(header):
            key = next((k for k in QUANTITY_KEYS if _norm_label(k) in _norm_label(col)), None)
            if not key:
                continue
            for r in rows[1:]:
                if ci < len(r):
                    try:
                        val = float(r[ci])
                    except (ValueError, IndexError):
                        continue
                    out.append({
                        "label": key, "value": val, "unit": "",
                        "source": f"csv:{base}", "context": f"{col}={val}",
                    })
    return out


def _expand_csv_args(args):
    paths = []
    for a in args or []:
        if os.path.isdir(a):
            paths.extend(glob.glob(os.path.join(a, "**", "*.csv"), recursive=True))
        else:
            paths.extend(glob.glob(a))
    return sorted(set(paths))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Manuscript numeric + citation consistency check.")
    ap.add_argument("docx", help="manuscript .docx path")
    ap.add_argument("--csv", action="append", default=[],
                    help="figure CSV file/dir/glob (repeatable)")
    ap.add_argument("--json", help="write JSON report to this path")
    ap.add_argument("--tol", type=float, default=0.02,
                    help="relative tolerance for value agreement (default 0.02 = 2%%)")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.docx):
        print(f"ERROR: not found: {args.docx}", file=sys.stderr)
        return 2

    paragraphs = list(docx_paragraphs(args.docx))

    quantities = []
    for para in paragraphs:
        quantities.extend(_find_quantities(para, "body"))
    csv_paths = _expand_csv_args(args.csv)
    csv_q = csv_quantities(csv_paths)
    csv_errors = [q["_error"] for q in csv_q if "_error" in q]
    quantities.extend([q for q in csv_q if "_error" not in q])

    conflicts = detect_conflicts(quantities, args.tol)
    floats = detect_float_issues(paragraphs)

    report = {
        "manuscript": os.path.abspath(args.docx),
        "paragraphs_scanned": len(paragraphs),
        "csv_files": csv_paths,
        "csv_errors": csv_errors,
        "quantities_found": len(quantities),
        "conflict_count": len(conflicts),
        "conflicts": conflicts,
        "float_issues": floats,
        "untraceable_count": (len(floats["cited_without_caption"])
                              + len(floats["captioned_but_never_cited"])),
    }

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)

    # human summary
    print(f"Manuscript: {report['manuscript']}")
    print(f"  paragraphs scanned : {report['paragraphs_scanned']}")
    print(f"  quantities found   : {report['quantities_found']} "
          f"(body + {len(csv_paths)} csv)")
    print(f"  numeric conflicts  : {report['conflict_count']}")
    for c in conflicts:
        print(f"    [CONFLICT] {c['label']} {c['unit']}: values {c['distinct_values']}")
        for occ in c["occurrences"]:
            print(f"        {occ['value']!r:>10}  ({occ['source']})  …{occ['context']}…")
    print(f"  untraceable floats : {report['untraceable_count']}")
    for f in floats["cited_without_caption"]:
        print(f"    [NO CAPTION] {f['kind']} {f['number']} cited but no caption found")
    for f in floats["captioned_but_never_cited"]:
        print(f"    [NEVER CITED] {f['kind']} {f['number']} captioned but never cited in body")
    if csv_errors:
        print("  csv read errors:")
        for e in csv_errors:
            print(f"    {e}")

    hard = report["conflict_count"] + report["untraceable_count"]
    print("RESULT:", "PASS" if hard == 0 else f"FAIL ({hard} finding(s))")
    return 0 if hard == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
