#!/usr/bin/env python3
"""caption_style.py -- ONE shared rule set for caption title FORM and interpretive language.

WHY THIS EXISTS:
    A supplementary caption titled "Fig. S3. Why the optimum sits outside the tested
    range: one-at-a-time sensitivity of the five process variables." followed by
    sentences such as "... so that parallel lines mean the variable acts the same way
    everywhere ... rather than being cost-free ... the reference values are equally
    good" passed a full caption QC. Nothing checked the title FORM, nothing detected
    interpretive wording (academic-term-rules section 7 items 2 and 11), and the
    caption checker did not recognise S-prefixed labels. This module is the detector.

USED BY:
    scripts/figure_lint.py  -- lints the `<stem>.caption.txt` sidecar a render script
                               writes (HIGH question/colon title, MED interpretive).
    any caption checker     -- import by path (importlib), no install needed.

SEVERITY:
    HIGH  title form: starts with a question word / ends with "?" / "X: Y" colon title
    MED   interpretive or rhetorical wording (item 11), clause-style title, and the
          item-10 internal-facing flags. FLAG-ONLY: a hit is a candidate for a human
          decision, never an automatic edit.

CLI:
    python caption_style.py file.caption.txt [more ...]
    python caption_style.py --text "Fig. S3. Why ...: ..."
    python caption_style.py --self-test
Exit: 0 no HIGH | 1 HIGH found | 2 usage/error.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Labels: Fig./Figure/Figs./Table/Scheme + optional S + number + optional letter
# ---------------------------------------------------------------------------
LABEL_RE = re.compile(
    r"^\s*(Figures?|Figs?\.?|Tables?|Schemes?)\s*(S?)(\d+)([A-Za-z](?![A-Za-z]))?\s*(?:\(([a-z])\))?\s*\.?",
    re.IGNORECASE,
)
# Unnumbered sidecar labels ("Fig X.", "Fig. SX.", "Graphical abstract.")
LOOSE_LABEL_RE = re.compile(
    r"^\s*(?:(?:Figures?|Figs?\.?|Tables?|Schemes?)\s*S?[A-Za-z]{0,2}\s*\.|"
    r"Graphical abstract\s*\.|Supplementary\s+[A-Za-z]+\s*\.)",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Title form (academic-term-rules section 7 item 2)
# ---------------------------------------------------------------------------
QUESTION_WORDS = ("Why", "How", "What", "Where", "When", "Whether", "Which", "Who")
_QUESTION_START_RE = re.compile(r"^\W*(?:%s)\b" % "|".join(QUESTION_WORDS))
# colon that introduces a subtitle: ": " followed by text; skips ratios "1:1" and math spans
_COLON_SUBTITLE_RE = re.compile(r"(?<![\d$}]):\s+\S")
# Clause-style title cues (a title is a noun phrase, not a sentence). MED only.
TITLE_CLAUSE_FLAGS = [
    r"\brather than\b",
    r"\b(?:sits?|acts?|interacts?|lies|rises?|falls?|matters?|dominates?)\b",
]
# sentence end that is not an abbreviation dot
_SENT_END_RE = re.compile(
    r"(?<!\bvs)(?<!\bFig)(?<!\bal)(?<!\bca)(?<!\bapprox)(?<!\bno)(?<![A-Z])(?<!\d)\.(?=\s+[A-Z(\[]|\s*$|\s*\n)"
)


def split_caption(text: str):
    """Return (label, title, rest). label is '' when no label is recognised.
    title = first sentence of the caption after the label (ends at the first non-
    abbreviation period, a newline, or a panel marker "(a)")."""
    t = text.strip()
    m = LABEL_RE.match(t) or LOOSE_LABEL_RE.match(t)
    label = t[: m.end()].strip() if m else ""
    body = t[m.end():].lstrip() if m else t
    end = len(body)
    nl = body.find("\n")
    if nl != -1:
        end = nl
    pm = re.search(r"\s\(a[,)\s]", body)
    if pm and pm.start() < end:
        end = pm.start()
    se = _SENT_END_RE.search(body[:end])
    if se:
        end = se.end()
    return label, body[:end].strip(), body[end:].strip()


def check_title_form(text: str):
    """Title-form findings: list of (severity, code, message)."""
    label, title, _ = split_caption(text)
    out = []
    if not title:
        return out
    if _QUESTION_START_RE.match(title):
        out.append(("HIGH", "TITLE_QUESTION",
                    f"title opens with a question word ({title.split()[0]}); use a declarative noun phrase"))
    if title.rstrip(". ").endswith("?"):
        out.append(("HIGH", "TITLE_QUESTION", "title is a question; use a declarative noun phrase"))
    if _COLON_SUBTITLE_RE.search(title):
        out.append(("HIGH", "TITLE_COLON",
                    "colon 'X: Y' title; state what is shown as one noun phrase"))
    for pat in TITLE_CLAUSE_FLAGS:
        m = re.search(pat, title, re.IGNORECASE)
        if m:
            out.append(("MED", "TITLE_CLAUSE",
                        f"title reads as a clause/claim ({m.group(0)!r}); name what is shown"))
    return out


# ---------------------------------------------------------------------------
# Item 11: interpretive / rhetorical caption language (FLAG-ONLY)
# Bare "rather than" and "because" are deliberately absent: too many false positives.
# ---------------------------------------------------------------------------
INTERPRETIVE_FLAGS = [
    r"\bso that\b",
    r"\btherefore\b",
    r"\bhence\b",
    r"\bthus\b",
    r"\brather than being\b",
    r"\bnot (?:a )?preferences?\b",
    r"\bequally good\b",
    r"\bnow also\b",
    r"\bwas not (?:performed|computed|run|done|measured)\b",
    r"\bwere not (?:performed|computed|run|done|measured)\b",
    r"\bdominates?\b",
    r"\bis the axis that\b",
    r"\bcost-free\b",
    r"\bacts? the same way\b",
]

# ---------------------------------------------------------------------------
# Item 10: internal-facing content (FLAG-ONLY)
# ---------------------------------------------------------------------------
CAPTION_INTERNAL_FLAGS = [
    r"(?:Notion|Asana|Jira)\s+[0-9a-f]{6,}",       # tracker IDs
    "[\U0001F534⚠✅]",                    # status emoji
    r"\bstill open\b|\bnot yet correct\b",         # open-task language
    r"\breported as shipped\b",                    # defending our own choice
    r"\brather than re-optimi[sz]ed\b",
    r"\bnot comparable point-for-point\b",         # versus an earlier draft
    r"\b(?:DIFFERENT|SAME|NOT|ONLY)\b(?![-\w])",   # shouted emphasis
]

_INTERP_RES = [re.compile(p, re.IGNORECASE) for p in INTERPRETIVE_FLAGS]
_INTERNAL_RES = [re.compile(p) for p in CAPTION_INTERNAL_FLAGS]


def scan_interpretive(text: str):
    """Item 11 hits as (pattern, matched_text)."""
    return [(rx.pattern, m.group(0)) for rx in _INTERP_RES for m in rx.finditer(text)]


def scan_internal(text: str):
    """Item 10 hits as (pattern, matched_text)."""
    return [(rx.pattern, m.group(0)) for rx in _INTERNAL_RES for m in rx.finditer(text)]


def analyze(text: str, include_internal: bool = False):
    """All style findings for one caption: list of dicts {sev, code, msg}."""
    out = [{"sev": s, "code": c, "msg": m} for s, c, m in check_title_form(text)]
    for _pat, hit in scan_interpretive(text):
        out.append({"sev": "MED", "code": "INTERPRETIVE", "msg": f"interpretive wording {hit!r}"})
    if include_internal:
        for _pat, hit in scan_internal(text):
            out.append({"sev": "MED", "code": "INTERNAL", "msg": f"internal-facing content {hit!r}"})
    return out


# ---------------------------------------------------------------------------
# self-test (generic examples)
# ---------------------------------------------------------------------------
EXAMPLE_BAD = (
    "Fig. S3. Why the optimum sits outside the tested range: one-at-a-time sensitivity of the "
    "five process variables. Each panel sweeps one variable so that parallel lines mean the "
    "variable acts the same way everywhere. Reaction time now also improves yield, so the "
    "optimum sits at its upper cap rather than being cost-free. The last two variables are not "
    "preferences and the reference values are equally good. No total-order sensitivity was computed."
)
EXAMPLE_GOOD = (
    "Fig. S3. One-at-a-time sensitivity of product yield to the five process variables. "
    "(a) Range of yield obtained when each variable is swept across its search bound."
)


def _self_test() -> int:
    fails = []

    def check(name, cond):
        print(("ok   " if cond else "FAIL ") + name)
        if not cond:
            fails.append(name)

    m = LABEL_RE.match("Fig. S14. Foo")
    check("label Fig. S14 -> S + 14", bool(m) and m.group(2).upper() == "S" and m.group(3) == "14")
    check("label Table S3", bool(LABEL_RE.match("Table S3. Foo")))
    m = LABEL_RE.match("Figure 2. Foo")
    check("label Figure 2 has no S", bool(m) and m.group(2) == "")
    bad = analyze(EXAMPLE_BAD)
    check("bad: question title HIGH", any(f["sev"] == "HIGH" and f["code"] == "TITLE_QUESTION" for f in bad))
    check("bad: colon title HIGH", any(f["sev"] == "HIGH" and f["code"] == "TITLE_COLON" for f in bad))
    check("bad: >=3 interpretive hits", sum(f["code"] == "INTERPRETIVE" for f in bad) >= 3)
    check("good: clean", not analyze(EXAMPLE_GOOD))
    check("ratio 1:1 is not a colon title", not check_title_form("Fig. 2. Yield at a 1:1 substrate ratio."))
    check("'vs.' does not end the title",
          split_caption("Fig. 5. Titer vs. yield of the front. More text.")[1] == "Titer vs. yield of the front.")
    check("bare 'rather than' is not an item-11 flag", not scan_interpretive("A was tested rather than B."))
    print("SELF-TEST", "PASS" if not fails else f"FAIL ({len(fails)})")
    return 0 if not fails else 1


def main(argv) -> int:
    for _s in (sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            try:
                _s.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass
    if not argv:
        print(__doc__)
        return 2
    if argv[0] == "--self-test":
        return _self_test()
    if argv[0] == "--text":
        texts = {"<text>": " ".join(argv[1:])}
    else:
        texts = {a: Path(a).read_text(encoding="utf-8", errors="replace") for a in argv}
    rc = 0
    for name, txt in texts.items():
        fs = analyze(txt, include_internal=True)
        if not fs:
            print(f"[clean] {name}")
            continue
        print(f"=== {name}")
        for f in fs:
            print(f"  [{f['sev']}] {f['code']}: {f['msg']}")
            if f["sev"] == "HIGH":
                rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
