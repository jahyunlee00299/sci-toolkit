"""
ai_tells_lint.py — AI-tells linter for chemistry/bioengineering manuscripts.

Detects AI-characteristic writing patterns in .docx, .md, or .txt files.
DETECTION ONLY — never auto-corrects. Exit code is always 0 (advisory, non-blocking).

Usage
-----
    python ai_tells_lint.py MANUSCRIPT.docx
    python ai_tells_lint.py MANUSCRIPT.docx --json
    python ai_tells_lint.py paper.md --json > report.json
    python ai_tells_lint.py --self-test

Categories detected
-------------------
A1  Inflated adjectives (crucial, pivotal, robust, intricate, meticulous,
    groundbreaking, novel-as-filler, comprehensive)
A2  Meaning-filler frames (it is important to note, sheds light on, paves the
    way for, sets the stage for, serves as a testament to)
A3  AI-signature verbs (delve, showcase, leverage, foster, garner, underscore,
    facilitate-overused)
A4  Stacked hyphenated compound modifiers (heuristic: WORD-ing/ed WORD-ing/ed
    or two hyphenated tokens before the same noun)
A8  Sentence-opening transition/booster adverbs (Additionally, Moreover,
    Furthermore, Notably, Interestingly, Importantly, Significantly)

Scope: body paragraphs AND table cells AND captions (all paragraph text in docx).
"""

import sys
import io
import re
import json
import argparse
import zipfile
import textwrap
from pathlib import Path
from xml.etree import ElementTree as ET

# ── UTF-8 stdout guard (required for Windows Korean locale) ──────────────────
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── Pattern definitions ───────────────────────────────────────────────────────

# A1: inflated adjectives — match as whole words, case-insensitive
_A1_WORDS = [
    "crucial", "pivotal", "vital", "robust", "intricate", "meticulous",
    "meticulously", "groundbreaking", "unprecedented", "comprehensive",
    # "novel" only as pre-noun filler — catch "novel X" constructions
    r"novel\s+\w+",
]

_A2_PHRASES = [
    r"it\s+is\s+important\s+to\s+note",
    r"it\s+should\s+be\s+noted",
    r"sheds?\s+light\s+on",
    r"paves?\s+the\s+way\s+for",
    r"sets?\s+the\s+stage\s+for",
    r"serves?\s+as\s+a\s+testament\s+to",
    r"(?:^|\.\s+|\!\s+|\?\s+)Importantly,",   # sentence-start Importantly
]

_A3_VERBS = [
    r"\bdelve[sd]?\b",
    r"\bdelving\b",
    r"\bshowcase[sd]?\b",
    r"\bshowcasing\b",
    r"\bleverag(?:e[sd]?|ing)\b",
    r"\bfoster(?:s|ed|ing)?\b",
    r"\bgarner(?:s|ed|ing)?\b",
    r"\bunderscor(?:e[sd]?|ing)\b",
]

# A4 heuristic: two or more hyphenated tokens (word-word) adjacent before a noun
# Pattern: (word-word)(,?\s+)(word-word)\s+\w+
# Also catch: word-(ing|ed) word-(ing|ed) before noun
_A4_STACKED = re.compile(
    r"\b(?:[A-Za-z]+-[A-Za-z]+)(?:[,\s]+(?:[A-Za-z]+-[A-Za-z]+))+\s+[A-Za-z]+",
    re.IGNORECASE,
)

# A8: sentence-opening boosters — only at true sentence start or after period
_A8_OPENERS = [
    "Additionally", "Moreover", "Furthermore", "Notably",
    "Interestingly", "Importantly", "Significantly",
]

# Compile all as (category, label, pattern) tuples
RULES: list[tuple[str, str, re.Pattern]] = []

for _w in _A1_WORDS:
    _pat = re.compile(rf"\b{_w}\b", re.IGNORECASE)
    RULES.append(("A1", _w.split(r"\\s")[0], _pat))

for _p in _A2_PHRASES:
    RULES.append(("A2", _p[:40], re.compile(_p, re.IGNORECASE)))

for _v in _A3_VERBS:
    RULES.append(("A3", _v, re.compile(_v, re.IGNORECASE)))

# A4 appended separately (special handling)
RULES.append(("A4", "stacked-hyphenated-modifiers", _A4_STACKED))

_A8_PAT = re.compile(
    r"(?:(?:^|(?<=[.!?])\s{1,3}))(" + "|".join(_A8_OPENERS) + r")[,\s]",
    re.IGNORECASE | re.MULTILINE,
)
RULES.append(("A8", "sentence-opening-booster", _A8_PAT))

# Suggestions map by category
SUGGESTIONS = {
    "A1": (
        "Replace with a measurement or mechanism. "
        "E.g. 'crucial' → 'required for'; 'robust' → state what held: 'stable across pH 5–8'."
    ),
    "A2": (
        "Delete the frame; state the fact directly. "
        "E.g. 'It is important to note that X' → 'X'."
    ),
    "A3": (
        "Use a plain verb. "
        "delve→examine/study; showcase→show; leverage→use; "
        "foster→promote; garner→obtain; underscore→confirm/support."
    ),
    "A4": (
        "Unfold to a relative clause. "
        "E.g. 'cofactor-balanced, waste-minimizing cascade' → "
        "'cascade that recycles its cofactor and produces little waste'."
    ),
    "A8": (
        "Remove the sentence-opening booster or absorb into the previous sentence. "
        "Logical flow should come from content order, not connective adverbs."
    ),
}

# ── Text extraction ───────────────────────────────────────────────────────────

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _iter_w_texts(xml_bytes: bytes) -> list[str]:
    """Extract all paragraph text strings from word/document.xml bytes."""
    root = ET.fromstring(xml_bytes)
    paragraphs = []
    # Collect all <w:p> elements regardless of depth (body + table cells + text boxes)
    for wp in root.iter(f"{{{_W}}}p"):
        runs = []
        for child in wp.iter(f"{{{_W}}}t"):
            if child.text:
                runs.append(child.text)
        text = "".join(runs).strip()
        if text:
            paragraphs.append(text)
    return paragraphs


def extract_paragraphs(path: Path) -> list[str]:
    """Return list of paragraph strings from .docx, .md, or .txt."""
    suffix = path.suffix.lower()
    if suffix == ".docx":
        with zipfile.ZipFile(path, "r") as zf:
            xml_bytes = zf.read("word/document.xml")
        return _iter_w_texts(xml_bytes)
    else:
        # .md / .txt — split on blank lines or newlines
        raw = path.read_text(encoding="utf-8", errors="replace")
        paras = [p.strip() for p in re.split(r"\n{2,}", raw)]
        return [p for p in paras if p]


# ── Lint engine ───────────────────────────────────────────────────────────────

def lint(paragraphs: list[str]) -> list[dict]:
    findings = []
    for para_idx, para in enumerate(paragraphs):
        # Split into sentences for sentence-level indexing
        sentences = re.split(r"(?<=[.!?])\s+", para)
        for sent_idx, sentence in enumerate(sentences):
            for category, label, pattern in RULES:
                for m in pattern.finditer(sentence):
                    findings.append(
                        {
                            "category": category,
                            "pattern": label,
                            "match": m.group(0).strip(),
                            "para_index": para_idx,
                            "sentence_index": sent_idx,
                            "sentence": sentence[:120] + ("…" if len(sentence) > 120 else ""),
                            "suggestion": SUGGESTIONS[category],
                        }
                    )
    return findings


# ── Reporting ─────────────────────────────────────────────────────────────────

def _text_report(findings: list[dict], source_name: str) -> str:
    lines = [
        f"ai_tells_lint report — {source_name}",
        f"Total findings: {len(findings)}",
        "",
    ]
    by_cat: dict[str, list[dict]] = {}
    for f in findings:
        by_cat.setdefault(f["category"], []).append(f)

    for cat in sorted(by_cat):
        lines.append(f"── {cat} ({len(by_cat[cat])} occurrences) ──")
        for f in by_cat[cat]:
            lines.append(
                f"  Para {f['para_index']:>3}, Sent {f['sentence_index']:>2} | "
                f"match: {f['match']!r:30s} | {f['sentence']}"
            )
            lines.append(f"    Suggestion: {textwrap.shorten(f['suggestion'], 80)}")
        lines.append("")

    if not findings:
        lines.append("No AI-tell patterns detected.")
    return "\n".join(lines)


# ── Self-test ─────────────────────────────────────────────────────────────────

_SELF_TEST_CASES = [
    # (text, expected_categories)
    ("This plays a crucial role in the reaction mechanism.", {"A1"}),
    ("It is important to note that the yield exceeded 90%.", {"A2"}),
    ("The study delves into the kinetics of the enzyme.", {"A3"}),
    (
        "This is a cofactor-balanced, waste-minimizing, sustainability-driven cascade.",
        {"A4"},
    ),
    ("Moreover, the titer increased by 40%.", {"A8"}),
    ("The enzyme was incubated at 37 °C for 2 h.", set()),  # clean — no match
]


def self_test() -> bool:
    all_pass = True
    print("Running self-test...")
    for text, expected_cats in _SELF_TEST_CASES:
        found_cats = {f["category"] for f in lint([text])}
        matched = expected_cats.issubset(found_cats)
        status = "PASS" if matched else "FAIL"
        if not matched:
            all_pass = False
        print(f"  [{status}] {text[:60]!r}")
        if not matched:
            print(f"    Expected categories: {expected_cats}")
            print(f"    Got categories:      {found_cats}")
    print()
    print("Self-test result:", "ALL PASS" if all_pass else "SOME FAILURES")
    return all_pass


# ── CLI ───────────────────────────────────────────────────────────────────────

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="AI-tells linter for chemistry/bioengineering manuscripts. "
        "Detects AI-characteristic patterns. Advisory only — exit code always 0."
    )
    parser.add_argument("file", nargs="?", help="Path to .docx, .md, or .txt file")
    parser.add_argument(
        "--json", action="store_true", help="Output findings as JSON array"
    )
    parser.add_argument(
        "--self-test", action="store_true", help="Run built-in regression tests and exit"
    )
    args = parser.parse_args(argv)

    if args.self_test:
        self_test()
        sys.exit(0)

    if not args.file:
        parser.print_help()
        sys.exit(0)

    path = Path(args.file)
    if not path.exists():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        sys.exit(0)

    paragraphs = extract_paragraphs(path)
    findings = lint(paragraphs)

    if args.json:
        print(json.dumps(findings, ensure_ascii=False, indent=2))
    else:
        print(_text_report(findings, path.name))

    # Exit 0 always — this is advisory, not a gate
    sys.exit(0)


if __name__ == "__main__":
    main()
