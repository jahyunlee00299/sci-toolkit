#!/usr/bin/env python3
"""qc_prose.py -- prose and structure gate for journal-club decks (folded into qc_deck.py as QC-20).

Why it exists (a 2026 TEA journal club): the deck passed every layout/number gate and was still
sent back by the presenter for things no earlier gate could see:
  * speaker notes carried drafting residue ("earlier draft said ...", "I will add this before the talk");
  * a notes sentence said "five questions" while the slide listed six;
  * slide takeaway lines were semicolon-contrast sentences and vague phrases the AI-writing catalog flags;
  * slide text ended in periods although the presenter wants none;
  * no Conclusions slide.
All findings are WARNING (heuristics, never a verdict). The regex layer is deliberately cheap; it does NOT
replace `Skill(avoid-ai-writing)` in detect mode (C-62), it makes sure the obvious cases cannot ship unseen.

Rules
  P1 notes-residue   speaker notes mention drafting history, TODOs, or "I will add/verify before the talk"
  P2 notes-count     notes say "N questions/items" but the numbered list on the slide has a different count
  P3 notes-dup       the same (or near-identical) sentence appears twice in one slide's notes
  P4 slide-aiism     slide text: em dash, Tier-1A AI vocabulary, "in order to", semicolon splice in a headline/takeaway
  P5 trailing-period slide text line ends with "." (only when the deck prefs say trailing_period=false;
                     references slide and abbreviation endings exempt)
  P6 no-conclusions  no slide titled Conclusion(s)/Summary/Take-home (journal and research decks)
  P7 appendix-shown  slide titled Appendix/Backup is not hidden while prefs appendix.hidden=true
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from pptx.util import Inches

PREFS_CATEGORY_PREFIX = "journal-ppt-prefs:"

# P1: Korean drafting-residue phrases (speaker notes are Korean by the skill's language rule)
NOTES_RESIDUE_RE = re.compile(
    r"(앞선|이전|초기)\s*(초안|버전)|초안에는|이번에\s*바로잡|바로잡았습니다|폐기했습니다|"
    r"보완하겠습니다|추가하겠습니다|확인한\s*뒤\s*발표|발표\s*(직전|전)에\s*(확인|보완|추가)|"
    r"SSOT|TODO|todo|나중에\s*(확인|추가)|업데이트\】|이해관계\s*선언은\s*제가")
# P2: "<count word> 가지 질문" style statements in the notes
KO_COUNT = {"한": 1, "두": 2, "세": 3, "네": 4, "다섯": 5, "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9, "열": 10}
NOTES_COUNT_RE = re.compile(r"(한|두|세|네|다섯|여섯|일곱|여덟|아홉|열)\s*(?:가지|개)\s*(?:의\s*)?(질문|문항|항목|논점|주제)")
NUMBERED_LINE_RE = re.compile(r"^\s*(\d{1,2})[\s.)]+\S")
# P4: Tier-1A vocabulary (avoid-ai-writing references/word-lists.md) + wordiness, slide text only
AIISM_RE = re.compile(
    r"\b(delv\w*|tapestry|realm|paradigm|embark\w*|beacon|testament to|robust\w*|comprehensive\w*|cutting-edge|"
    r"leverag\w*|pivotal|underscor\w*|meticulous\w*|seamless\w*|game-chang\w*|holistic\w*|actionable|impactful|"
    r"synerg\w*|interplay|ever-evolving|nuanced|multifaceted|myriad|plethora|utiliz\w*|in order to|"
    r"it is worth noting|worth noting)\b", re.I)
KEEP_END = ("et al.", "vs.", "Fig.", "Eng.", "approx.", "ca.", "..")
CONCLUSION_TITLE_RE = re.compile(r"conclusion|summary|take-?home", re.I)
TITLE_ZONE_IN = 1.6


@dataclass
class Finding:
    severity: str          # always "WARNING" for this module
    slide: int
    rule: str
    message: str


def _iter_frames(slide):
    for sh in slide.shapes:
        if sh.has_text_frame and sh.text_frame.text.strip():
            yield sh
        elif getattr(sh, "has_table", False) and sh.has_table:
            for row in sh.table.rows:
                for cell in row.cells:
                    if cell.text.strip():
                        yield cell


def slide_title(slide) -> str:
    """Title = the text frame sitting in the title zone with the largest font; '' if none."""
    best, best_pt = "", -1.0
    for sh in slide.shapes:
        if not (sh.has_text_frame and sh.text_frame.text.strip()):
            continue
        if sh.top is not None and sh.top / 914400 > TITLE_ZONE_IN:
            continue
        sizes = [r.font.size.pt for p in sh.text_frame.paragraphs for r in p.runs if r.font.size]
        pt = max(sizes) if sizes else 0
        if pt > best_pt:
            best, best_pt = sh.text_frame.text.strip().split("\n")[0], pt
    return best


def _is_hidden(slide) -> bool:
    return slide._element.get("show") == "0"


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?。])\s+|(?<=다\.)\s+|(?<=요\.)\s+|\s*【[^】]*】\s*", text)
    return [p.strip() for p in parts if p and len(p.strip()) >= 24]


def _norm(s: str) -> str:
    return re.sub(r"[\s.,;:()\[\]\"'`]+", "", s)


def check_prose(prs, prefs_name: str | None = None, prefs: dict | None = None) -> list[Finding]:
    """Run P1-P7 over a Presentation. `prefs` is the loaded preset dict (or None for generic checks)."""
    prefs = prefs or {}
    out: list[Finding] = []
    n_titles = []
    for i, slide in enumerate(prs.slides, start=1):
        title = slide_title(slide)
        n_titles.append(title)
        notes = slide.notes_slide.notes_text_frame.text if slide.has_notes_slide else ""
        texts = [sh.text_frame.text if hasattr(sh, "text_frame") else sh.text for sh in _iter_frames(slide)]
        is_refs = any(t.strip() == "References" for t in texts)

        # P1 notes residue
        for m in NOTES_RESIDUE_RE.finditer(notes):
            ctx = notes[max(0, m.start() - 12): m.end() + 18].replace("\n", " ")
            out.append(Finding("WARNING", i, "P1.notes-residue",
                               f"speaker notes carry drafting/to-do residue: ...{ctx}... (delete it, notes are for the talk)"))
        # P2 notes count vs numbered list on the slide
        numbered = 0
        for sh in _iter_frames(slide):
            tf = sh.text_frame if hasattr(sh, "text_frame") else None
            if tf is None:
                continue
            numbered += sum(1 for p in tf.paragraphs if NUMBERED_LINE_RE.match(p.text))
        if numbered >= 2:
            for m in NOTES_COUNT_RE.finditer(notes):
                said = KO_COUNT[m.group(1)]
                if said != numbered:
                    out.append(Finding("WARNING", i, "P2.notes-count",
                                       f"notes say {said} {m.group(2)} but the slide lists {numbered}"))
        # P3 duplicate sentences inside one notes block
        sents = _sentences(notes)
        for a in range(len(sents)):
            for b in range(a + 1, len(sents)):
                na, nb = _norm(sents[a]), _norm(sents[b])
                if na == nb or difflib.SequenceMatcher(None, na, nb).ratio() >= 0.9:
                    out.append(Finding("WARNING", i, "P3.notes-dup",
                                       f"near-identical sentences in the notes: {sents[a][:40]!r} / {sents[b][:40]!r}"))
        # P4 AI-isms in slide text (not the references slide, not quoted titles of cited papers)
        if not is_refs:
            for sh in _iter_frames(slide):
                tf = sh.text_frame if hasattr(sh, "text_frame") else None
                if tf is None:
                    continue
                for p in tf.paragraphs:
                    txt = p.text
                    sizes = [r.font.size.pt for r in p.runs if r.font.size]
                    big = bool(sizes) and min(sizes) >= 18
                    if "—" in txt or " -- " in txt:
                        out.append(Finding("WARNING", i, "P4.slide-aiism", f"em dash in slide text: {txt[:60]!r}"))
                    m = AIISM_RE.search(txt)
                    if m:
                        out.append(Finding("WARNING", i, "P4.slide-aiism", f"AI-frequency word {m.group(0)!r}: {txt[:60]!r}"))
                    if big and ";" in txt and all(len(part.split()) >= 3 for part in txt.split(";", 1)):
                        out.append(Finding("WARNING", i, "P4.slide-aiism",
                                           f"semicolon contrast in a headline/takeaway (write one direct claim): {txt[:70]!r}"))
        # P5 trailing period
        if (prefs.get("slide_text") or {}).get("trailing_period") is False and not is_refs:
            for sh in _iter_frames(slide):
                tf = sh.text_frame if hasattr(sh, "text_frame") else None
                if tf is None:
                    continue
                for p in tf.paragraphs:
                    t = p.text.rstrip()
                    if t.endswith(".") and not t.endswith(KEEP_END):
                        out.append(Finding("WARNING", i, "P5.trailing-period", f"slide text ends with a period: {t[-50:]!r}"))
        # P7 appendix visibility
        if (prefs.get("appendix") or {}).get("hidden") and re.match(r"(appendix|backup)\b", title, re.I) and not _is_hidden(slide):
            out.append(Finding("WARNING", i, "P7.appendix-shown", f"{title!r} is not hidden (prefs appendix.hidden=true)"))
    # P6 conclusions slide
    if len(n_titles) >= 6 and not any(CONCLUSION_TITLE_RE.search(t) for t in n_titles):
        out.append(Finding("WARNING", 0, "P6.no-conclusions",
                           "no Conclusions/Summary slide (journal club: add Deck.conclusions_slide() before the references)"))
    return out


def prefs_from_deck(prs) -> dict | None:
    """Load the prefs preset recorded in core_properties.category by Deck(prefs=...), else None."""
    cat = (prs.core_properties.category or "")
    if cat.startswith(PREFS_CATEGORY_PREFIX):
        try:
            from deck_builder import load_prefs
            return load_prefs(cat[len(PREFS_CATEGORY_PREFIX):])
        except Exception:
            return None
    return None


if __name__ == "__main__":
    import sys
    from pptx import Presentation
    deck = Presentation(sys.argv[1])
    found = check_prose(deck, prefs=prefs_from_deck(deck))
    for f in found:
        print(f"Slide {f.slide}: [{f.rule}] {f.message}")
    print(f"{len(found)} finding(s)")
    sys.exit(0)
