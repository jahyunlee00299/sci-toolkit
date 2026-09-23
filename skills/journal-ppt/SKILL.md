---
name: journal-ppt
description: |
  Unified, self-sufficient skill for producing academic journal-club and research-seminar
  PowerPoint decks. Two modes: journal (someone's published paper via DOI/title, including
  presenting your OWN manuscript in journal-club format) and research (your own lab data/
  manuscript as a seminar deck). Consolidates the pipeline, style spec, and typography rules
  that were previously split across journal-ppt-team.md and journal-presentation-maker into
  one skill with a runnable builder + QC gate. Triggers: journal club presentation, 저널클럽
  발표자료, lab meeting slides, research seminar deck, DOI-to-slides, 논문 발표 ppt, PPT 만들어줘
  (paper/논문 context), presentation for lab meeting, slide deck from manuscript.
---

# journal-ppt

Builds a polished academic PowerPoint deck from either a published paper (journal mode) or
your own research (research mode), and proves it is correct with a runnable QC gate rather
than eyeballing the output.

This skill supersedes `~/.claude/commands/journal-ppt-team.md` and
`~/.claude/skills/journal-presentation-maker/` by being wired as an actual skill (the old
command file had `triggers:` frontmatter but no `~/.claude/skills/` directory, so it was
never reachable by name and the two decks built under it both shipped with defects — see
"Why this skill exists" below). Those two are left in place; this skill is the one to use
going forward.

## Read these before building (mandatory, not optional)

1. **`references/style_spec.md`** — the closed-list type scale, line-spacing rules, spacing
   rules, color palette, geometry constants, and text-fit policy. This is the spine of the
   skill. Do not invent a font size, color, or spacing value outside it.
2. **`scripts/deck_builder.py`** — the role-based helper library. Read its `ROLES` dict and
   `Deck` class docstrings before writing any slide-building code by hand; almost everything
   you need is already a method here.
3. **`references/pipeline.md`** — the per-agent prompts if you are orchestrating a multi-agent
   build rather than writing the deck directly in one session.
4. **`~/.claude/skills/academic-term-rules/SKILL.md`** — nomenclature rules (species italics,
   gene/protein naming, units, sub/superscripts, dashes, American spelling) that apply to
   every string that lands on a slide.
5. **`scripts/logo_fetch.py`** — institution/company logo download+rasterize helper for
   `Deck.authors_slide()`. Resolve the source URL yourself (Wikimedia Commons "original file"
   link first, official site as fallback), then call `fetch_institution_logo()` — do not
   hand-roll a second download/SVG-to-PNG path.

Skipping this list is exactly how the 2026-08-23 decks shipped with 16-19 distinct font
sizes, `line_spacing=None` everywhere, and Korean body text — the rules already existed in
scattered form and were never read before building.

## Two modes

**journal mode** — presenting someone else's published paper. Input is a DOI or title.
Structure: Title → Background/Motivation (2 slides) → Methods → Results (one slide per
PRIMARY figure) → Discussion → Strengths/Limitations → Questions for Discussion →
References → Thank You.

**research mode** — presenting your own lab data/manuscript as a seminar. Input is a
manuscript path, data directory, or verbal description. Structure: Title → Background →
Research Strategy → Results (one slide per experiment/analysis) → Discussion & Significance
→ Conclusions & Future Work → Acknowledgments & References.

**A third case, treat as journal mode**: the user's OWN manuscript presented in
journal-club format (e.g. rehearsing for a defense, or a lab-internal "here's my paper"
talk). Use the journal-mode slide structure with the user as presenter, and keep the
Strengths/Limitations and Questions-for-Discussion sections **honest** — they double as
reviewer-question prep, so softening them defeats the purpose. Do not switch to research
mode just because the paper is the user's own; the deciding factor is the *format*
(journal-club-style critical read), not authorship.

If mode is ambiguous, ask: "Is this for a journal club (presenting someone else's paper,
or your own paper in journal-club format) or a research seminar (your own data/progress)?"

## Agent pipeline (if orchestrating multiple agents)

| Agent | Role | Model tier |
|---|---|---|
| Content Analyzer | Parse paper/data into `content_analysis.json`, validate numbers | Sonnet |
| PPT Builder | Build the deck with `deck_builder.py` | Sonnet |
| Academic QC | Nomenclature + `qc_deck.py` gate + reference/structure checks | **Sonnet** |
| Visual QC & Auto-Fixer | Render/inspect layout, fix issues found | Sonnet |

Full prompts: `references/pipeline.md`.

**Model routing note, measured twice in the 2026-08-23 session:** a local hook
(`agent_model_check.sh`) blocks Haiku for anything touching academic nomenclature. The
Academic QC agent MUST run on **Sonnet, not Haiku** — the older `journal-ppt-team.md`
pipeline defaulted this agent to Haiku and it was blocked both times. Every `Agent()` spawn
in this pipeline must pass `model=` **explicitly**, or the hook blocks the call outright
(observed failure mode: silent block, not a graceful fallback).

For a single-session build (no multi-agent orchestration), just follow the phases in
`references/pipeline.md` sequentially yourself — the model-routing note does not apply
when you are not spawning agents.

## Language rule — stated once, unmissable

**Slide body = English. Speaker notes = Korean.** No exceptions, no "just this one caveat
box in Korean." This is an academic deliverable read by anyone, reused in manuscripts, and
a mixed-language deck reads as unfinished — the whole deck gets rebuilt if this is
violated, not patched slide-by-slide.

Run the QC scan before calling a deck done:
```
"$PY" scripts/qc_deck.py <pptx_path>
```
Any Hangul codepoint (`가-힣`, `㄰-㆏`) found outside `notes_slide` is CRITICAL and blocks
delivery (`qc_deck.py` exits 1). The inverse also matters: speaker notes with **no** Korean
are flagged WARNING — notes exist for the Korean-speaking presenter's benefit.

## Content-integrity rules (measured failures, 2026-08-23 session)

- **Separate STATED numbers from DERIVED ones.** A number the paper's text or abstract
  states directly goes in verbatim. A number you computed from other stated values (a
  ratio, a percent change, a sum) must be labeled as an estimate on the slide or in the
  notes — do not present a derived number with the same confidence as a stated one.
- **When the abstract and Results disagree, present both and flag the mismatch** rather
  than silently picking whichever number is more convenient for the slide. This surfaces
  a real inconsistency in the source paper that the audience should know about.
- **Verify every number against `content_analysis.json` before it reaches a slide.** The
  Content Analyzer's Step 5 (Content Validation) exists specifically so a slide-writing
  agent is not the first place a number gets checked — see `references/pipeline.md` for
  the validation fields (`validated_numbers`, `validation_warnings`).

## Asset-sourcing rule

**Before cropping figures out of a PDF, check whether author-original exports already
exist.** Look in: the OneDrive project folder for the paper/manuscript, a `figures/`
directory alongside it, or a MANIFEST naming the canonical version (a project that keeps
a `FIGURE_STYLE.md` plus canonical asset naming is the pattern to look for).
The 2026-08-23 session found 4x-resolution originals only after the user pointed at them —
a PDF crop had already been used, at a fraction of the available quality. Checking first is
one directory listing; redoing the figure-insertion pass after finding originals late is a
full rebuild of every figure slide.

## Working directory and intermediate artifacts

Create `~/.claude/cache/journal_ppt_<timestamp>/` (or `research_ppt_<timestamp>/`). Save:

- `content_analysis.json` — structured content from Content Analyzer (schema: see
  `references/pipeline.md` §Agent 2 Output). This is the number-verification checkpoint —
  a slide-writing step should read numbers FROM this file, not re-derive them from raw text.
- `qc_report.md` — output of `qc_deck.py`, saved alongside the deck, not just printed.
- `assets/` — figures, extracted or sourced per the asset-sourcing rule above.

## Building a deck

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".claude" / "skills" / "journal-ppt" / "scripts"))  # runtime symlink into the skills repo
from deck_builder import Deck

deck = Deck(footer_right="Author et al., Journal Year")
deck.title_slide(title="...", citation="Author et al. (Year)",
                  journal_line="Journal, Vol(Issue):Pages -- DOI",
                  presenter="...", date="2026-08-23")

s = deck.content_slide("Background & Motivation")
deck.bullets(s, ["Point 1.", "Point 2.", "Point 3."], role="body")
deck.notes(s, "Korean speaker notes, >=100 chars, include 예상 질문 where relevant.")

s2 = deck.figure_slide(title="Key Result", subtitle="What this figure shows",
                        key_points=["<=3 bullets", "each one line"],
                        fig_path="assets/fig1.png",
                        caption_text="Figure 1. Caption text. (Figure 1 from [ref])")
deck.notes(s2, "...")

deck.table_slide("Kinetic Parameters", headers=[...], rows=[...])
deck.references_slide(["Author et al. (Year) Journal, Vol, Pages. DOI.", ...])

deck.save(str(Path.home() / "presentations" / "journal_club_YYYY-MM-DD_Topic.pptx"))
```

`Deck` methods reject an off-scale font size, line-spacing multiplier, or `space_after`
value by raising `StyleError` rather than silently accepting it — the closed list in
`references/style_spec.md` is enforced at the API boundary, not just checked afterward.

## QC gate before delivery

```
"$PY" scripts/qc_deck.py <pptx_path>
```

Exits non-zero on any CRITICAL finding (verified live: `echo $?` after a failing run
returns 1, not just "printed FAIL"). Checks (style_spec.md §9): word_wrap set,
`disable_autofit()` applied, line_spacing/space_after in the closed lists, font is Arial,
font size in the closed type scale (9pt floor), no Hangul outside notes, geometry (nothing
below the Y=7.0in floor except the sanctioned footer band — identified by shape shape
[height <=0.4in, bottom near the true 7.5in slide edge], not a fixed top-coordinate, since
measured real decks place footer text anywhere from 7.05in to 7.1in; side margins, with an
exemption for full-bleed header bars that intentionally span the whole slide width), every
slide has notes >=100 chars containing Korean, every picture >=3in in one dimension, font
colors within the resolved 11-color palette (warning-level; the base 8 from style_spec.md
§5 plus 3 sanctioned derived colors documented in that section's "Sanctioned derived
colors" subsection — header-bar subtitle text and the Strengths/Limitations heading pair).

**Value-dispersion check (independent of every named rule above).** For font size,
line_spacing, space_after, font name, and autoshape fill color, `qc_deck.py` counts the
number of DISTINCT values actually used across the whole deck and flags WARNING if that
count exceeds the expected ceiling (9 sizes, 3 spacings, 5 space_after values, 1 font, 11
colors) — **even when every individual value is inside its allowed set**. This exists
because the two defects that shipped in the pre-skill decks (Korean body text; 16-19
distinct font sizes with `line_spacing=None` everywhere) both trace back to the same root
cause: the spec was silent on a property, so the builder improvised something, and no named
rule caught the improvisation because nothing had named that property yet. A closed-list
assertion can only test "is this value legal" — it cannot test "why does this vary at all,"
which is the question that actually catches undocumented drift. **Do not delete this check
as redundant with the closed-list assertions** — it is structurally different (it fires on
combinations of otherwise-legal values, not on any single illegal one) and is the only
defense against a rule nobody has written yet.

Run it on every deck before calling the build done. A deck that fails QC is not finished —
send it back through the fix loop (Visual QC & Auto-Fixer, or a direct edit) and re-run.

## Slide count / structure targets

Journal mode: 13-23 slides, typical 15-18. Research mode: similar range. Always include
Title, Background, Results, Discussion, Conclusion/Questions, References. Figure-First
Layout rules (figure gets 55-70% of a results slide, text fits into what remains, never the
reverse) are in `references/style_spec.md` §6-7 and `references/pipeline.md`.

## What this skill does not cover

- Paper download / PDF extraction (DOI resolution, PyMuPDF figure extraction) — that logic
  is unchanged from `journal-ppt-team.md`'s Agent 1; reuse it, it was not part of this
  session's measured failures.
- Full nomenclature rule text — defer to `academic-term-rules` rather than duplicating it
  here; this skill only restates the subset that governs slide *layout/typography*.
