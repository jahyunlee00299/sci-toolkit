#!/usr/bin/env python3
"""
body_typo_lint.py — body-text typo/spacing linter (.md / .txt).

This is the enforcement side of the patterns defined in
`skills/academic-term-rules/SKILL.md` §12/12a/12b. The patterns/whitelists
are carried over from that document verbatim; this script does not invent
new rules on its own — to change a rule, fix SKILL.md first and report that
alongside the change.

Two grades:
  AUTO-FIXABLE (§12 TYPO_PATTERNS)
      Safe 1:1 mechanical substitutions (µL, mL, h, rpm, space before °C,
      NAD⁺, etc.). `--fix --output <new_file>` produces the actual replaced
      text. The original is never overwritten.
  REVIEW-ONLY (§12a PUNCT_SPACE_FLAGS + §12b COFACTOR_SPACE_FLAGS)
      Missing space after punctuation/cofactor symbols. Requires human
      review — this script never auto-replaces these. A false-positive
      candidate filtered by the whitelist is not silently hidden; the
      summary shows how many were filtered.

Does not handle .docx input — it only points the user at
`skills/docx/scripts/manuscript_text.py --mode accept` to extract the text
first (that script already handles tracked changes correctly).

Usage:
    python body_typo_lint.py <file.md|file.txt>
    python body_typo_lint.py <file.md> --fix --output <new_file.md>
    python body_typo_lint.py <file.md> --strict     # REVIEW-ONLY also exits 1
    python body_typo_lint.py <file.md> --json
    python body_typo_lint.py --self-test
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Windows' default console is cp949, which dies on Korean/symbol output.
# Force UTF-8. Use reconfigure() instead of TextIOWrapper — the wrapper
# takes ownership of the underlying stream, so once it's GC'd after
# import, it closes the caller's stdout too (measured).
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# Pattern definitions — carried over verbatim from SKILL.md §12/§12a/§12b.
# Do not invent new rules here. If a change is needed, fix SKILL.md first
# and report it.
# --------------------------------------------------------------------------- #

# §12 TYPO_PATTERNS — AUTO-FIXABLE (safe 1:1 mechanical substitution)
TYPO_PATTERNS: list[tuple[str, str]] = [
    (r"\bul\b", "µL"), (r"\buL\b", "µL"), (r"\buM\b", "µM"),
    (r"\bml\b", "mL"), (r"\bhr\b", "h"), (r"\bhrs\b", "h"), (r"\bRPM\b", "rpm"),
    (r"℃", "°C"), (r"(\d)°C", r"\1 °C"), (r"(\d)mM", r"\1 mM"),
    (r"n=(\d)", r"n = \1"), (r"mean ± standard deviation", "mean ± SD"),
    (r"pH (\d)-(\d)", r"pH \1–\2"), (r"(\d+)-(\d+) °C", r"\1–\2 °C"),
    # NADP first — replacing "NAD+" first would corrupt the front of "NADP+".
    # No trailing \b: since "+" is a non-word character, the boundary does
    # not hold in a real sentence like "NAD+ regeneration" where a space or
    # punctuation follows, which kills the rule (that's exactly what
    # happened with SKILL.md §12's original \bNAD\+\b — both sides were
    # fixed after this was measured).
    (r"\bNADP\+", "NADP⁺"), (r"\bNAD\+(?!P)", "NAD⁺"),
    (r"supertanant", "supernatant"), (r"seperati", "separati"),
]

# §12a PUNCT_SPACE_FLAGS — REVIEW-ONLY (missing space after punctuation)
PUNCT_SPACE_FLAGS: list[tuple[str, str]] = [
    (r"\b([a-z]{2,})\.([A-Z][a-z]{2,})\b", "missing space after period"),
    (r"\b([a-z]{2,}),([A-Za-z]{2,})\b", "missing space after comma"),
    (r"\b([a-z]{2,});([A-Za-z]{2,})\b", "missing space after semicolon"),
    (r"\b([a-z]{2,}):([A-Za-z]{2,})\b", "missing space after colon"),
]

# §12a PUNCT_SPACE_WHITELIST — excluded from a REVIEW-ONLY verdict if it overlaps
PUNCT_SPACE_WHITELIST: list[str] = [
    r"\bn\.a\.", r"\be\.g\.", r"\bi\.e\.", r"\bs\.d\.", r"\bet al\.",
    r"\bvs\.", r"\bcf\.", r"\betc\.", r"\bca\.", r"\bviz\.",
    r"\bU\.S\.A\.", r"\bPh\.D\.", r"\b[A-Z]\.[A-Z]\.",
    r"\borcid\.org", r"\bdoi\.org", r"[a-z]+\.(com|org|net|edu)\b",
    # Keep this synced with the same list in academic-term-rules
    # SKILL.md §12a — updating only one side puts the doc and the
    # implementation out of sync.
    r"\.(jpe?g|png|tiff?|docx?|xlsx?|pdf|csv|py|json|[Rr]md|[Rr]proj|ipynb|ya?ml|toml)\b",
    r"\d\.\d",
]

# §12b COFACTOR_SPACE_FLAGS — REVIEW-ONLY (missing space after a cofactor symbol/token)
COFACTOR_SPACE_FLAGS: list[tuple[str, str]] = [
    (r"\b(NAD\(?P?\)?[+⁺⁻]+)([a-z]{3,})\b", "missing space after cofactor charge symbol"),
    (r"\bNAD(P?H)([a-z]{3,})\b", "missing space after cofactor token"),
]

# §12b COFACTOR_SPACE_WHITELIST
COFACTOR_SPACE_WHITELIST: list[str] = [
    r"\bNAD\(?P?\)?H?[+⁺⁻]*-[a-z]",
]

REVIEW_FLAGS = PUNCT_SPACE_FLAGS + COFACTOR_SPACE_FLAGS
REVIEW_WHITELIST = PUNCT_SPACE_WHITELIST + COFACTOR_SPACE_WHITELIST

_TYPO_COMPILED = [(re.compile(p), repl) for p, repl in TYPO_PATTERNS]
_REVIEW_COMPILED = [(re.compile(p), label) for p, label in REVIEW_FLAGS]
_WHITELIST_COMPILED = [re.compile(p) for p in REVIEW_WHITELIST]


# --------------------------------------------------------------------------- #
# Excluding code fences / inline code / URLs — a false positive here means nobody uses this tool
# --------------------------------------------------------------------------- #

_FENCE_RE = re.compile(r"^```")
_URL_RE = re.compile(r"https?://\S+")


def _mask_excluded_spans(line: str) -> tuple[str, list[tuple[int, int]]]:
    """Return the string with inline-code (`...`) and URL spans masked as
    spaces, plus the original list of (start, end) spans. Masking
    preserves offsets, so column numbers stay valid."""
    spans: list[tuple[int, int]] = []
    masked = list(line)

    for m in re.finditer(r"`[^`]*`", line):
        spans.append(m.span())
    for m in _URL_RE.finditer(line):
        spans.append(m.span())

    for start, end in spans:
        for i in range(start, end):
            masked[i] = " "
    return "".join(masked), spans


def _iter_scan_lines(text: str):
    """Skip entire code-fence (``` ... ```) blocks, and for every remaining
    line yield (1-based line number, the line masked for scanning)."""
    in_fence = False
    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        if _FENCE_RE.match(raw_line.strip()):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        masked, _ = _mask_excluded_spans(raw_line)
        yield lineno, raw_line, masked


# --------------------------------------------------------------------------- #
# The Finding data structure
# --------------------------------------------------------------------------- #

@dataclass
class Finding:
    grade: str          # "AUTO-FIXABLE" | "REVIEW-ONLY"
    line: int
    col: int             # 1-based
    current: str
    suggestion: str
    rule: str


@dataclass
class LintResult:
    findings: list[Finding] = field(default_factory=list)
    whitelisted_count: int = 0  # count of REVIEW-ONLY candidates filtered out by the whitelist


def _is_whitelisted(line: str, start: int, end: int) -> bool:
    """True if the flagged span overlaps a whitelist match (overlap-check)."""
    for pat in _WHITELIST_COMPILED:
        for wm in pat.finditer(line):
            if wm.start() < end and start < wm.end():
                return True
    return False


def lint_text(text: str) -> LintResult:
    result = LintResult()

    for lineno, raw_line, masked in _iter_scan_lines(text):
        # AUTO-FIXABLE: §12 TYPO_PATTERNS
        for pattern, repl in _TYPO_COMPILED:
            for m in pattern.finditer(masked):
                # Re-applying the pattern to m.group(0) can break the match,
                # because a boundary anchor like \b gets re-evaluated against
                # the "cut-out short string" (measured: for \bNAD\+\b, looking
                # only at the 4 characters "NAD+", the trailing \b no longer
                # holds at the end of that string, so the re-match fails and
                # nothing gets substituted). Instead this substitutes groups
                # and backreferences safely via expand() against the original
                # match span (no regex re-evaluation — it just fills the
                # already-found match object's groups into the repl
                # template, so there's no boundary problem).
                suggestion = m.expand(repl)
                result.findings.append(
                    Finding(
                        grade="AUTO-FIXABLE",
                        line=lineno,
                        col=m.start() + 1,
                        current=m.group(0),
                        suggestion=suggestion,
                        rule=f"TYPO_PATTERNS:{pattern.pattern}",
                    )
                )

        # REVIEW-ONLY: §12a + §12b
        for pattern, label in _REVIEW_COMPILED:
            for m in pattern.finditer(masked):
                if _is_whitelisted(masked, m.start(), m.end()):
                    result.whitelisted_count += 1
                    continue
                # Suggestion: insert a space at the offset where the last
                # capture group starts within the matched string (by offset,
                # not by reassembling the group text as a string). This works
                # safely regardless of how the group count/order differs
                # between patterns (§12a's whole 2-group match is
                # "symbol+next word"; §12b's token pattern has group(1)
                # capture only the suffix after NAD).
                last_group_idx = len(m.groups())
                split_at = m.start(last_group_idx) - m.start()
                whole = m.group(0)
                suggestion = whole[:split_at] + " " + whole[split_at:]
                result.findings.append(
                    Finding(
                        grade="REVIEW-ONLY",
                        line=lineno,
                        col=m.start() + 1,
                        current=m.group(0),
                        suggestion=suggestion,
                        rule=label,
                    )
                )

    return result


def apply_auto_fix(text: str) -> str:
    """Return new text with only AUTO-FIXABLE (§12 TYPO_PATTERNS) applied.
    Never touches inside code-fence blocks. Never touches REVIEW-ONLY."""
    lines = text.splitlines(keepends=True)
    in_fence = False
    out_lines = []

    for raw_line in lines:
        stripped = raw_line.strip("\n").strip("\r")
        if _FENCE_RE.match(stripped.strip()):
            in_fence = not in_fence
            out_lines.append(raw_line)
            continue
        if in_fence:
            out_lines.append(raw_line)
            continue

        # Leave inline-code/URL spans as-is and only substitute outside them.
        # Find match positions in the masked text (excluded spans replaced
        # with spaces), then splice in the original string fragments only at
        # those positions. Uses m.expand(repl) the same way lint_text() does,
        # to avoid the boundary-breaking problem from \b re-evaluation (the
        # literal-sub re-apply bug, confirmed via self-test).
        content = raw_line[: len(raw_line.rstrip("\n").rstrip("\r"))]
        eol = raw_line[len(content):]

        # Offsets shift after every pattern substitution, so reconstruct the
        # original string left-to-right in one pass per pattern (patterns
        # are applied sequentially, one after another).
        new_content = content
        for pattern, repl in _TYPO_COMPILED:
            masked, spans = _mask_excluded_spans(new_content)

            def _in_excluded(pos: int) -> bool:
                return any(s <= pos < e for s, e in spans)

            pieces = []
            last_end = 0
            for m in pattern.finditer(masked):
                if _in_excluded(m.start()):
                    continue
                pieces.append(new_content[last_end : m.start()])
                pieces.append(m.expand(repl))
                last_end = m.end()
            pieces.append(new_content[last_end:])
            new_content = "".join(pieces)

        out_lines.append(new_content + eol)

    return "".join(out_lines)


# --------------------------------------------------------------------------- #
# Report output
# --------------------------------------------------------------------------- #

def _format_findings(findings: list[Finding], source_name: str, whitelisted: int) -> str:
    lines = [f"body_typo_lint report — {source_name}"]
    auto = [f for f in findings if f.grade == "AUTO-FIXABLE"]
    review = [f for f in findings if f.grade == "REVIEW-ONLY"]

    for f in sorted(findings, key=lambda x: (x.line, x.col)):
        lines.append(
            f"{source_name}:{f.line}:{f.col}  [{f.grade}] "
            f"{f.current!r} → {f.suggestion!r}  ({f.rule})"
        )

    lines.append("")
    lines.append(
        f"Summary: AUTO-FIXABLE {len(auto)} / REVIEW-ONLY {len(review)} "
        f"(REVIEW-ONLY candidates filtered by whitelist: {whitelisted} — shown, not hidden)"
    )
    if not findings:
        lines.append("No issues.")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Self-test — bidirectional MUST FLAG / MUST NOT FLAG (per SKILL.md rules)
# --------------------------------------------------------------------------- #

def self_test() -> bool:
    must_flag = [
        # \bul\b matches "ul" only as a standalone token (same as SKILL.md's
        # original pattern). "50ul" directly attached to a digit doesn't
        # satisfy \b, so it isn't a target — confirmed:
        # re.findall(r'\bul\b', '50ul') == [].
        ("Volume was 50 ul total.", "AUTO-FIXABLE", "§12: ul -> µL (standalone token)"),
        ("Incubated at 37°C for 2 h.", "AUTO-FIXABLE", "§12: (digit)°C -> digit space °C"),
        ("Reported as n=3 replicates.", "AUTO-FIXABLE", "§12: n=(digit) -> n = digit"),
        # The NAD+ cases below are exactly the shape that SKILL.md §12's
        # original `\bNAD\+\b` **completely missed**. "+" is a non-word
        # character, so \b doesn't hold when a space or punctuation follows
        # it (measured). The trailing \b was removed to fix both SKILL.md
        # and the implementation, so if these cases get missed again, this
        # catches that regression.
        ("Cofactor NAD+ was regenerated.", "AUTO-FIXABLE", "§12: NAD+ -> NAD⁺ (followed by a space)"),
        ("Measured the NAD+/NADH ratio.", "AUTO-FIXABLE", "§12: NAD+ -> NAD⁺ (followed by a slash)"),
        ("An NAD+-dependent enzyme was used.", "AUTO-FIXABLE", "§12: superscript is correct even in a hyphenated modifier (§3)"),
        ("Added NADP+ to the buffer.", "AUTO-FIXABLE", "§12: NADP+ -> NADP⁺ (substituted before NAD)"),
        ("The supertanant was collected.", "AUTO-FIXABLE", "§12: typo supertanant"),
        ("After conversion.Here we show yield.", "REVIEW-ONLY", "§12a: missing space after period"),
        ("NAD⁺regeneration was observed.", "REVIEW-ONLY", "§12b: missing space after cofactor symbol"),
        ("NADHoxidase activity increased.", "REVIEW-ONLY", "§12b: missing space after cofactor token"),
    ]
    must_not_flag = [
        ("```python\ndf.head()\n```", "inside a code fence is not a scan target"),
        ("See https://a.com/x.Here for details.", "inside a URL is not a §12a target"),
        ("As shown previously, e.g. in the prior study.", "§12a whitelist: e.g."),
        ("This agrees with et al. reports.", "§12a whitelist: et al."),
        ("The constant was 3.14 in this run.", "§12a whitelist: decimal point (digit.digit)"),
        ("Data collected by J.H. Kim in 2024.", "§12a whitelist: initials X.X."),
        ("Raw file was data.Rmd for this run.", "§12a whitelist: filename extension"),
        ("The complex is NAD⁺-dependent for activity.", "§12b whitelist: hyphenated modifier"),
        ("Buffer contained NADPH regeneration mix.", "§12b: already has a space — no match to begin with"),
    ]

    all_pass = True
    print("=== MUST FLAG ===")
    for text, expected_grade, why in must_flag:
        result = lint_text(text)
        got_grades = {f.grade for f in result.findings}
        ok = expected_grade in got_grades
        status = "PASS" if ok else "FAIL"
        if not ok:
            all_pass = False
        print(f"  [{status}] {text[:55]!r}  (expected: {expected_grade} — {why})")
        if not ok:
            print(f"        actual findings: {[(f.grade, f.current) for f in result.findings]}")

    print("\n=== MUST NOT FLAG ===")
    for text, why in must_not_flag:
        result = lint_text(text)
        ok = len(result.findings) == 0
        status = "PASS" if ok else "FAIL"
        if not ok:
            all_pass = False
        print(f"  [{status}] {text[:55]!r}  ({why})")
        if not ok:
            print(f"        false positive: {[(f.grade, f.current, f.rule) for f in result.findings]}")

    print()
    print("self-test result:", "ALL PASS" if all_pass else "SOME FAILURES")
    return all_pass


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Body-text typo/spacing linter (.md/.txt). "
            "SKILL.md §12/§12a/§12b enforcement side. "
            "For .docx, extract the text first with "
            "skills/docx/scripts/manuscript_text.py --mode accept and pass that "
            "in (this script does not handle .docx directly)."
        )
    )
    parser.add_argument("file", nargs="?", help="path to a .md or .txt file")
    parser.add_argument("--fix", action="store_true", help="actually replace AUTO-FIXABLE items")
    parser.add_argument("--output", help="path to the new file to write --fix results to (never overwrites the original)")
    parser.add_argument("--strict", action="store_true", help="treat REVIEW-ONLY as exit 1 too")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--self-test", action="store_true", help="run the built-in regression test")
    args = parser.parse_args(argv)

    if args.self_test:
        ok = self_test()
        return 0 if ok else 1

    if not args.file:
        parser.print_help()
        return 0

    path = Path(args.file)
    if not path.exists():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        return 2

    if path.suffix.lower() == ".docx":
        print(
            "ERROR: this script does not handle .docx directly.\n"
            "  First extract the text by running:\n"
            "    python skills/docx/scripts/manuscript_text.py "
            f"{path} --mode accept\n"
            "  (this is the SSOT script for extracting a final version that\n"
            "  correctly reflects tracked changes.)",
            file=sys.stderr,
        )
        return 2

    text = path.read_text(encoding="utf-8", errors="replace")

    if args.fix:
        if not args.output:
            print("ERROR: --fix must be used together with --output <new_file> (never overwrites the original).",
                  file=sys.stderr)
            return 2
        out_path = Path(args.output)
        if out_path.resolve() == path.resolve():
            print("ERROR: --output must be a different path from the original (never overwrites the original).",
                  file=sys.stderr)
            return 2
        fixed_text = apply_auto_fix(text)
        out_path.write_text(fixed_text, encoding="utf-8", newline="\n")
        # Report the remaining state against the new file after --fix.
        remaining = lint_text(fixed_text)
        remaining_auto = [f for f in remaining.findings if f.grade == "AUTO-FIXABLE"]
        print(f"WROTE {out_path} (original {path} left unchanged)")
        print(f"AUTO-FIXABLE applied: {len([f for f in lint_text(text).findings if f.grade == 'AUTO-FIXABLE'])}")
        if remaining_auto:
            print(f"Warning: {len(remaining_auto)} AUTO-FIXABLE item(s) still remain after --fix (check for overlapping/recursive patterns)")
        if remaining.findings:
            print()
            print(_format_findings(remaining.findings, str(out_path), remaining.whitelisted_count))
        return 0

    result = lint_text(text)
    auto = [f for f in result.findings if f.grade == "AUTO-FIXABLE"]
    review = [f for f in result.findings if f.grade == "REVIEW-ONLY"]

    if args.json:
        payload = {
            "file": str(path),
            "findings": [
                {
                    "grade": f.grade,
                    "line": f.line,
                    "col": f.col,
                    "current": f.current,
                    "suggestion": f.suggestion,
                    "rule": f.rule,
                }
                for f in result.findings
            ],
            "summary": {
                "auto_fixable": len(auto),
                "review_only": len(review),
                "whitelisted_filtered": result.whitelisted_count,
            },
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(_format_findings(result.findings, str(path), result.whitelisted_count))

    if auto:
        return 1
    if review and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
