#!/usr/bin/env python3
"""figure_lint.py — enforce figure_aesthetics_rules.md on a figure render script.

THE enforcement layer. The rules SSOT + helpers existed but were opt-in, so every
hand-authored render script re-derived layout/color logic with raw ax.legend(loc=...)
and literal hex — which is why "rules get ignored." This lint turns the rules doc from
advisory into a checked gate.

Scans a render script (text + light AST) and reports rule violations as JSON:
  raw_legend_calls       : ax.legend / plt.legend NOT via smart_legend  (R: legend)
  hardcoded_hex          : '#RRGGBB' literals outside an allowed SSOT line (R: color)
  hardcoded_fontsize     : numeric fontsize=  not theme.FS_*             (R: font)
  set_title_descriptive  : ax.set_title with >3-char non-panel text      (R2: no title)
  layout_manager         : constrained_layout / tight_layout present?    (R4)
  savefig_ok             : every savefig has dpi(=300) + bbox_inches='tight'
  external_legend        : bbox_to_anchor outside axes / loc contains 'center'

Exit code: 0 if no HIGH-severity findings, 1 otherwise. Use as a pre-"figure done" gate.

Usage:
    python figure_lint.py render_figN.py [render_figM.py ...]
    python figure_lint.py --json render_figN.py      # machine-readable
"""
from __future__ import annotations

# Windows' default console is cp949, which dies on Korean/symbol output.
# Force UTF-8. Use reconfigure(): wrapping the stream in a TextIOWrapper
# instead takes ownership of the underlying stream, so once this module is
# imported, the caller's stdout gets closed when that wrapper is later
# garbage-collected (measured).
import sys as _sys
for _s in (_sys.stdout, _sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
import sys
import re
import json
from pathlib import Path

HEX_RE = re.compile(r"#[0-9A-Fa-f]{6}\b")
# Whether the line is a color-SSOT definition (allowed): literals inside a
# SERIES_COLORS/OKABE_ITO/palette dict are permitted.
SSOT_COLOR_HINT = re.compile(r"OKABE_ITO|SERIES_COLORS|_COLORS\s*=|PALETTE|NEUTRAL")
# fontsize=<number> (a literal, not theme.FS_*)
FONTSIZE_LIT_RE = re.compile(r"fontsize\s*=\s*([0-9]+(?:\.[0-9]+)?)")
# raw legend() calls
RAW_LEGEND_RE = re.compile(r"\b(?:ax\w*|axes\[[^\]]*\]|plt)\.legend\s*\(")
EXTERNAL_LEGEND_RE = re.compile(r"bbox_to_anchor|loc\s*=\s*['\"][^'\"]*center")
SETTITLE_RE = re.compile(r"\.set_title\s*\(\s*([fr]?['\"])(.*?)\1")
SAVEFIG_RE = re.compile(r"\.savefig\s*\(")
SUPTITLE_RE = re.compile(r"\.suptitle\s*\(")
# In-axes text annotation calls. ax.text(...) — matches the `.text(` call
# itself so it still catches cases where transAxes is on the same or next
# line (set_xlabel/ylabel/title are not .text and are irrelevant). Combined
# with the condition-word check below to decide a violation.
AXTEXT_RE = re.compile(r"\b\w*ax\w*\.text\s*\(|\baxes\[[^\]]*\]\.text\s*\(")
# R3 forbidden: condition/scenario/description keywords (caption material).
# A bare enzyme name alone is exempt.
# Data-value labels (a reference-line 'X% yield', the yield/time text at the
# center of a donut chart, etc.) are excluded on purpose — this only catches
# "unnecessary description/condition" text. yield/titer/selectivity are
# excluded because those values are common (only scenario words are caught).
COND_WORDS = re.compile(
    r"\b(flask|fermentor|bioreactor|deterministic|marginal\w*|variants?|"
    r"medium|induction|IPTG|substrate|hydrolysate|env\.|scenario|condition)\b", re.I)
# Unit notation for measurement conditions (things like '8 g DCW/L' floating
# in a data region). reference-line % is excluded (it ends as a standalone
# value like yield).
COND_UNIT = re.compile(r"\b\d+\s*(?:°C|rpm|g\s*DCW|DCW\s*/?\s*L)\b|pH\s*\d")


def _strip_comment(line: str) -> str:
    """Strip anything after a comment (#) — a # inside a string is ignored
    by this simple approximation. Used for literal detection."""
    # position of the first # outside quotes
    in_s = None
    for i, ch in enumerate(line):
        if ch in ("'", '"'):
            if in_s is None:
                in_s = ch
            elif in_s == ch:
                in_s = None
        elif ch == "#" and in_s is None:
            return line[:i]
    return line


def lint_script(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    findings = {
        "raw_legend_calls": [], "hardcoded_hex": [], "hardcoded_fontsize": [],
        "set_title_descriptive": [], "external_legend": [],
        "suptitle": [], "condition_label": [],
    }
    is_theme_module = path.name in ("theme.py", "aesthetic_helpers.py")
    # A schematic/construct diagram (SBOL glyph artwork) is not a data plot,
    # so it is exempt from style rules (hardcoded hex/fontsize, layout
    # manager). Glyph-specific colors (backbone/promoter/RBS/zebra) and the
    # precise placement used for imshow compositing are unrelated to
    # theme.FS_*/constrained_layout. Semantic rules (suptitle, external/center
    # legend, R3 condition-label) still apply, though.
    nm = path.name.lower()
    is_schematic = any(k in nm for k in ("construct", "schematic", "scheme", "diagram"))

    for i, raw in enumerate(lines, 1):
        line = _strip_comment(raw)
        if not line.strip():
            continue
        # raw legend (routing through smart_legend is fine). A schematic
        # diagram (axes-off artwork) is exempt — its legend doubles as the
        # glyph caption, a bottom horizontal layout is conventional there,
        # and the corner rule doesn't apply.
        if not is_schematic and RAW_LEGEND_RE.search(line) and "smart_legend" not in line:
            findings["raw_legend_calls"].append({"line": i, "text": line.strip()[:90]})
        # external / center legend (exempt for schematics — axes-off means
        # there's no corner concept)
        if not is_schematic and EXTERNAL_LEGEND_RE.search(line) and ".legend(" in line:
            findings["external_legend"].append({"line": i, "text": line.strip()[:90]})
        # hardcoded hex (exempt: theme module, color-SSOT definition lines,
        # schematic diagrams)
        if not is_theme_module and not is_schematic and HEX_RE.search(line) and not SSOT_COLOR_HINT.search(line):
            for m in HEX_RE.findall(line):
                findings["hardcoded_hex"].append({"line": i, "hex": m, "text": line.strip()[:90]})
        # hardcoded fontsize (a number, not theme.FS_*; exempt for schematics)
        if not is_schematic:
            for m in FONTSIZE_LIT_RE.finditer(line):
                findings["hardcoded_fontsize"].append({"line": i, "value": m.group(1), "text": line.strip()[:90]})
        # descriptive set_title (exempt: panel letters like '(a)'/'a', 3 chars or fewer)
        mt = SETTITLE_RE.search(line)
        if mt:
            title_txt = mt.group(2)
            stripped = re.sub(r"[()\s]", "", title_txt)
            if len(stripped) > 3 and "loc" not in line.split(".set_title")[0][-30:]:
                # a loc='left' panel-letter usage is still a violation if the text is long
                if len(stripped) > 3:
                    findings["set_title_descriptive"].append({"line": i, "title": title_txt[:40]})
        # suptitle forbidden (R3: no figure title)
        if SUPTITLE_RE.search(line):
            findings["suptitle"].append({"line": i, "text": line.strip()[:80]})
        # in-axes condition/description label (R3: caption material). Two paths:
        #  (1) a direct ax.text(...transAxes...) call carrying a condition word/unit
        #  (2) a panel_tag/tag/label-style helper call carrying a condition string
        #      (when the call site and ax.text are separated)
        # A bare enzyme/sample name alone (used to identify which panel this
        # is) is exempt — only caught when a condition word/unit is also present.
        is_axtext = AXTEXT_RE.search(line)
        is_tag_call = re.search(r"\b(panel_tag|panel_subtitle|cond_label|annotate_cond)\s*\(", line)
        if (is_axtext or is_tag_call) and (COND_WORDS.search(line) or COND_UNIT.search(line)):
            strs = re.findall(r"['\"]([^'\"]{2,60})['\"]", line)
            label = " ".join(s for s in strs if "transAxes" not in s and s != "%" and "$" not in s)
            findings["condition_label"].append({"line": i, "label": (label or line.strip())[:60]})

    # layout manager / savefig global checks (a schematic diagram uses
    # precise subplots_adjust placement -> exempt)
    layout_manager = is_schematic or bool(re.search(
        r"constrained_layout\s*=\s*True|\.tight_layout\s*\(|fig\.set_layout_engine|subplots_adjust", text))
    savefig_calls = [i for i, ln in enumerate(lines, 1) if SAVEFIG_RE.search(_strip_comment(ln))]
    savefig_issues = []
    for ln_no in savefig_calls:
        # a savefig call can span multiple lines, so check ±2 lines combined
        ctx = " ".join(lines[max(0, ln_no - 1):ln_no + 2])
        has_dpi = "dpi=300" in ctx.replace(" ", "") or "dpi=300" in ctx
        has_bbox = "bbox_inches" in ctx and "tight" in ctx
        if not (has_dpi and has_bbox):
            savefig_issues.append({"line": ln_no, "has_dpi300": has_dpi, "has_bbox_tight": has_bbox})

    # tally severity
    high = (len(findings["raw_legend_calls"]) + len(findings["external_legend"])
            + len(findings["hardcoded_hex"]) + len(findings["set_title_descriptive"])
            + len(findings["suptitle"]) + len(findings["condition_label"])
            + (0 if layout_manager else 1) + len(savefig_issues))
    med = len(findings["hardcoded_fontsize"])

    return {
        "file": str(path.name),
        "findings": findings,
        "layout_manager_present": layout_manager,
        "savefig_issues": savefig_issues,
        "counts": {
            "raw_legend_calls": len(findings["raw_legend_calls"]),
            "hardcoded_hex": len(findings["hardcoded_hex"]),
            "hardcoded_fontsize": len(findings["hardcoded_fontsize"]),
            "set_title_descriptive": len(findings["set_title_descriptive"]),
            "external_legend": len(findings["external_legend"]),
            "suptitle": len(findings["suptitle"]),
            "condition_label": len(findings["condition_label"]),
            "savefig_issues": len(savefig_issues),
        },
        "high_severity": high,
        "med_severity": med,
        "pass": high == 0,
    }


def _print_human(r: dict):
    mark = "PASS" if r["pass"] else "FAIL"
    print(f"\n=== {r['file']}  [{mark}]  high={r['high_severity']} med={r['med_severity']} ===")
    c = r["counts"]
    if c["raw_legend_calls"]:
        print(f"  [HIGH] raw ax.legend(loc=...) x{c['raw_legend_calls']} — use smart_legend()")
        for f in r["findings"]["raw_legend_calls"]:
            print(f"         L{f['line']}: {f['text']}")
    if c["external_legend"]:
        print(f"  [HIGH] external/center legend x{c['external_legend']} — corners only, inside axes")
        for f in r["findings"]["external_legend"]:
            print(f"         L{f['line']}: {f['text']}")
    if c["hardcoded_hex"]:
        print(f"  [HIGH] hardcoded hex x{c['hardcoded_hex']} — route via series_color()/SERIES_COLORS")
        for f in r["findings"]["hardcoded_hex"][:12]:
            print(f"         L{f['line']}: {f['hex']}  ({f['text']})")
    if c["set_title_descriptive"]:
        print(f"  [HIGH] descriptive set_title x{c['set_title_descriptive']} — R2: no graph title")
        for f in r["findings"]["set_title_descriptive"]:
            print(f"         L{f['line']}: {f['title']}")
    if c["suptitle"]:
        print(f"  [HIGH] suptitle x{c['suptitle']} — R3: no figure title")
        for f in r["findings"]["suptitle"]:
            print(f"         L{f['line']}: {f['text']}")
    if c["condition_label"]:
        print(f"  [HIGH] on-figure condition/description label x{c['condition_label']} — R3: move to caption")
        for f in r["findings"]["condition_label"]:
            print(f"         L{f['line']}: \"{f['label']}\"  (strip condition; keep bare entity name only)")
    if not r["layout_manager_present"]:
        print("  [HIGH] no layout manager — add constrained_layout=True or tight_layout()")
    if r["savefig_issues"]:
        print(f"  [HIGH] savefig missing dpi=300/bbox_inches='tight' x{len(r['savefig_issues'])}")
        for f in r["savefig_issues"]:
            print(f"         L{f['line']}: dpi300={f['has_dpi300']} bbox_tight={f['has_bbox_tight']}")
    if c["hardcoded_fontsize"]:
        print(f"  [MED]  hardcoded fontsize x{c['hardcoded_fontsize']} — use theme.FS_*")
        for f in r["findings"]["hardcoded_fontsize"][:8]:
            print(f"         L{f['line']}: fontsize={f['value']}")
    if r["pass"] and not r["med_severity"]:
        print("  clean.")


def main(argv):
    as_json = "--json" in argv
    files = [a for a in argv if not a.startswith("--")]
    if not files:
        print("usage: figure_lint.py [--json] render_figN.py ...", file=sys.stderr)
        return 2
    results = [lint_script(Path(f)) for f in files]
    if as_json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        for r in results:
            _print_human(r)
        total_high = sum(r["high_severity"] for r in results)
        n_fail = sum(1 for r in results if not r["pass"])
        print(f"\n{'='*50}\nTOTAL: {len(results)} files, {n_fail} FAIL, {total_high} high-severity findings")
    return 0 if all(r["pass"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
