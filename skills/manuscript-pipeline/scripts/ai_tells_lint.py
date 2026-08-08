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
    # "novel" was here as r"novel\s+\w+" (any pre-noun use). Removed 260809:
    # measured on this lab's five manuscripts, 2 of 3 hits were false — "novel
    # food" is the EFSA regulatory term and "novel kinases" was neutral
    # annotation. Ownership moved to A14, which fires only when the claim sits
    # next to a self-reference, because that is what makes it self-praise.
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

# A12: first-person INTERPRETIVE framing. Deliberately narrow — it must never
# fire on first-person ACTION verbs ("we report", "we measured", "we assayed",
# "we constructed", "we chose"), which are conventional in the target journals.
# The verb list is therefore an allow-by-omission: only interpretive verbs here.
_A12_FRAMES = [
    r"\bwe\s+(?:read|believe|feel|think|would\s+argue|are\s+convinced)\b",
    r"\bin\s+our\s+(?:opinion|view)\b",
    r"\bit\s+is\s+our\s+view\b",
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

for _f in _A12_FRAMES:
    RULES.append(("A12", "first-person-interpretive-frame", re.compile(_f, re.IGNORECASE)))

# A14: novelty/success claims, but ONLY next to a self-reference. Measured
# 260809: a bare \bnovel\b would have been wrong more often than right —
# "novel food" is the EFSA regulatory term, and both "for the first time" hits
# described other groups' work. Proximity to our/we/this study is what makes
# the claim self-referential, and that is the thing worth flagging.
_SELF = r"(?:our|we|this\s+(?:study|work))"
_A14_SELF_CLAIM = re.compile(
    rf"\b{_SELF}\b(?![^.]{{0,40}}\bnovel\s+food\b)[^.]{{0,40}}?\b(?:novel|successful(?:ly)?)\b"
    rf"|\b(?:novel|successful(?:ly)?)\b[^.]{{0,40}}?\b{_SELF}\b",
    re.IGNORECASE,
)
_A14_REDUNDANT_SUCCESS = re.compile(
    r"\b(?:was|were)\s+successfully\s+"
    r"(?:applied|used|performed|developed|demonstrated|implemented|achieved|obtained)\b",
    re.IGNORECASE,
)
_A14_IN_THIS_STUDY = re.compile(r"\bin\s+this\s+(?:study|work),?\s+we\b", re.IGNORECASE)

RULES.append(("A14", "self-referential-novelty-claim", _A14_SELF_CLAIM))
RULES.append(("A14", "redundant-successfully", _A14_REDUNDANT_SUCCESS))
RULES.append(("A14", "in-this-study-we", _A14_IN_THIS_STUDY))

# ── Sentence-level predicates (not regex matches) ─────────────────────────────

# A13 threshold. Measured 260809 over 1,215 sentences of this lab's manuscripts:
# 162 (13.3%) exceed 40 words, longest 185. 45 is set above the 40-word mark so
# the flag lands on the genuinely unwieldy rather than on every long sentence.
A13_WORD_LIMIT = 45

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]*")
_STAT_WARRANT = re.compile(
    r"\bp\s*[<=≤]|\bANOVA\b|\bt-?test\b|\bTukey\b|\bWelch\b|\b95\s*%\s*CI\b|\bn\s*=",
    re.IGNORECASE,
)
# Rhetorical opener, makes no statistical claim.
_SIGNIF_WHITELIST = re.compile(r"\b(?:perhaps\s+)?most\s+significantly\b", re.IGNORECASE)


def _check_long_sentence(sentence: str):
    n = len(_WORD_RE.findall(sentence))
    return f"{n} words" if n > A13_WORD_LIMIT else None


def _check_significantly_without_warrant(sentence: str):
    if not re.search(r"\bsignificantly\b", sentence, re.IGNORECASE):
        return None
    if _SIGNIF_WHITELIST.search(sentence) or _STAT_WARRANT.search(sentence):
        return None
    return "significantly (no test named in this sentence)"


SENTENCE_CHECKS = [
    ("A13", "overlong-sentence", _check_long_sentence),
    ("A14", "significantly-without-warrant", _check_significantly_without_warrant),
]

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
        "These seven carry no logical relation. Do NOT extend this to connectives "
        "that DO carry one (However, Therefore, Because, Although, Whereas, "
        "In contrast) — stripping those is what leaves prose with no connective "
        "tissue. If pruning makes a relation implicit, restate it by subordinating "
        "the clause, not by deleting the link."
    ),
    "A12": (
        "State the inference instead of narrating it. "
        "'We read these results as X' → 'X' or 'These results are consistent with X'. "
        "First-person ACTION verbs stay: we report/measured/assayed/constructed/chose."
    ),
    "A13": (
        "FLAG-ONLY. Split where a literature claim, its citations, and this work's "
        "interpretation are fused into one sentence. A long sentence can be earned — "
        "a parallel enumeration standing in for a table should stay whole."
    ),
    "A14": (
        "Drop the self-praise and state the specific difference. "
        "'a novel approach that represents a significant contribution' → what it does "
        "that prior work did not. 'was successfully applied' → 'was applied'. "
        "'significantly' needs a test in the same sentence, or say 'lower'/'higher'."
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

_NO_SUGGESTION = "(no suggestion registered for this category)"


def _finding(category, label, match, para_idx, sent_idx, sentence) -> dict:
    """One finding record.

    SUGGESTIONS is looked up with .get on purpose. Both registries are extended
    by appending a tuple, and before 260809 appending one whose category had no
    SUGGESTIONS entry raised KeyError and killed the whole run — the registry
    was open for extension in form only. A missing suggestion is now a missing
    string, not a crash.
    """
    return {
        "category": category,
        "pattern": label,
        "match": match,
        "para_index": para_idx,
        "sentence_index": sent_idx,
        "sentence": sentence[:120] + ("…" if len(sentence) > 120 else ""),
        "suggestion": SUGGESTIONS.get(category, _NO_SUGGESTION),
    }


def lint(paragraphs: list[str]) -> list[dict]:
    findings = []
    for para_idx, para in enumerate(paragraphs):
        # Split into sentences for sentence-level indexing
        sentences = re.split(r"(?<=[.!?])\s+", para)
        for sent_idx, sentence in enumerate(sentences):
            for category, label, pattern in RULES:
                for m in pattern.finditer(sentence):
                    findings.append(_finding(category, label, m.group(0).strip(),
                                             para_idx, sent_idx, sentence))
            # Checks that are not pattern matches. A sentence's word count and
            # "does this sentence also name a statistical test" are predicates,
            # not regexes, so they get their own hook rather than a contorted
            # lookahead. The loops stay separate because a pattern can match
            # several times in one sentence and a predicate answers once.
            for category, label, check in SENTENCE_CHECKS:
                hit = check(sentence)
                if hit:
                    findings.append(_finding(category, label, hit,
                                             para_idx, sent_idx, sentence))
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
    # A12 — first-person interpretive framing
    ("We read these results as evidence of a shared binding mode.", {"A12"}),
    ("we read these results as a filter on the search space.", {"A12"}),
    ("We believe the mechanism is oxidative.", {"A12"}),
    ("We feel this is the dominant route.", {"A12"}),
    ("We think this suggests a shared binding mode.", {"A12"}),
    ("We would argue that the effect is real.", {"A12"}),
    ("We are convinced the pathway is complete.", {"A12"}),
    ("In our opinion the assay is adequate.", {"A12"}),
    ("In our view the data are sufficient.", {"A12"}),
    ("It is our view that the model holds.", {"A12"}),
    # ── Negative cases: these must produce NO finding at all ──────────────────
    ("The enzyme was incubated at 37 °C for 2 h.", set()),
    # A12 must spare first-person ACTION verbs — these are conventional.
    ("Here we report the first round of the campaign.", set()),
    ("We measured activity against both substrates.", set()),
    ("We constructed 21 single substitutions.", set()),
    ("We assayed each variant in five replicates.", set()),
    ("We chose 30 °C because the enzyme is unstable above it.", set()),
    ("The priors operated as a filter on the search space.", set()),
    # A8 must not fire on connectives that carry a logical relation. Stripping
    # these is what leaves prose with no connective tissue (user report 260809).
    ("However, the titer did not increase.", set()),
    ("Therefore, the cofactor was regenerated in situ.", set()),
    ("In contrast, the wild type retained full activity.", set()),
    # Adversarial near-misses for the A12 word boundaries.
    ("Weather effects were not modeled.", set()),
    ("The crew were readied for the run.", set()),
    # A13 — overlong sentence (predicate, not a pattern)
    (
        "Recent studies have demonstrated that rationally designed enzymatic "
        "cascades operating under mild aqueous conditions achieve lower E-factors "
        "and process mass intensity values compared with conventional multistep "
        "chemical synthesis routes that rely on protecting groups, organic "
        "solvents, and stoichiometric oxidants, and this comparison has been "
        "extended to several carbohydrate substrates in recent years by multiple "
        "independent groups working on related systems.",
        {"A13"},
    ),
    # A14 — self-referential novelty / success / unwarranted significance
    ("Our findings provide a novel approach to biomass valorization.", {"A14"}),
    ("The cascade was successfully applied to actual hydrolysates.", {"A14"}),
    ("In this study, we developed a biocatalytic platform.", {"A14"}),
    ("The titer was significantly higher in the engineered strain.", {"A14"}),
    # ── A13/A14 negatives: the false positives the 260809 measurement found ───
    # "novel food" is the EFSA regulatory term, not a self-praise claim.
    ("Our product was approved under the novel food regulation.", set()),
    # Both corpus hits of "for the first time" described OTHER groups' work.
    ("Chung and colleagues reported this activity for the first time in 1989.", set()),
    # "novel" with no self-reference nearby is neutral description.
    ("Two novel kinases were annotated in the genome.", set()),
    # "significantly" IS licensed when the sentence names the test.
    ("The titer was significantly higher (Welch t-test, p < 0.01).", set()),
    ("Yields differed significantly between groups (ANOVA, p = 0.003).", set()),
    # Rhetorical opener makes no statistical claim.
    ("Perhaps most significantly, the cofactor never had to be added.", set()),
    # A 44-word sentence must NOT trip the 45-word limit (boundary).
    (
        "The enzyme was incubated with the substrate in phosphate buffer at pH "
        "seven and thirty degrees for two hours before the reaction was stopped "
        "by heating, and the supernatant was then analyzed by chromatography "
        "against authentic standards prepared fresh on the same day of use.",
        set(),
    ),
]


def self_test() -> bool:
    """Regression gate.

    A positive case must yield its category. A NEGATIVE case (expected set is
    empty) must yield NO finding at all — before 260809 the check was
    `expected.issubset(found)`, and an empty set is a subset of everything, so
    every clean case passed unconditionally and the suite could not detect
    over-firing. That is the failure mode a linter actually has.
    """
    all_pass = True
    print("Running self-test...")

    # Extending either registry must not crash the linter. Appending a rule is
    # the documented way to add one, and before 260809 appending one whose
    # category had no SUGGESTIONS entry raised KeyError mid-run.
    RULES.append(("__PROBE__", "extension-probe", re.compile(r"\bzzprobezz\b")))
    try:
        lint(["A zzprobezz appears here."])
        print("  [PASS] registry stays usable when a rule has no SUGGESTIONS entry")
    except Exception as exc:                                  # noqa: BLE001
        all_pass = False
        print(f"  [FAIL] extending RULES raised {type(exc).__name__}: {exc}")
    finally:
        RULES.pop()

    for text, expected_cats in _SELF_TEST_CASES:
        found_cats = {f["category"] for f in lint([text])}
        if expected_cats:
            ok = expected_cats.issubset(found_cats)
        else:
            ok = not found_cats           # negative case: nothing may fire
        status = "PASS" if ok else "FAIL"
        if not ok:
            all_pass = False
        print(f"  [{status}] {text[:60]!r}")
        if not ok:
            print(f"    Expected categories: {expected_cats or 'NONE (clean)'}")
            print(f"    Got categories:      {found_cats or 'none'}")
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
