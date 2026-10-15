---
name: journal-ppt
description: "Build academic journal-club or research-seminar PowerPoint decks (a paper via DOI or title, or your own data and manuscript) with a runnable builder and QC gate. Triggers: 저널클럽 발표자료, 논문 발표 ppt, PPT 만들어줘 for a paper, lab meeting slides, DOI-to-slides."
---

# journal-ppt

Builds a polished academic PowerPoint deck from either a published paper (journal mode) or
your own research (research mode), and proves it is correct with a runnable QC gate rather
than eyeballing the output.

This skill supersedes the `journal-ppt-team` command and the `journal-presentation-maker`
skill (the two decks built under them both shipped with defects — see "Why this skill
exists" below). Both are retired: journal-presentation-maker sits in `inactive/`, and the
command was moved out of `commands/` on 2026-10-02 because, while it stayed there, the skill
listing showed the command with its description and this skill as a bare name. The one part
of the command this skill still reuses, the Agent 1 paper-download procedure, now lives in
`references/paper_download.md`.

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
5. **Logos for `Deck.authors_slide()`** — it takes finished PNG paths, so fetch them
   before the build: resolve the source URL yourself (Wikimedia Commons "original file"
   link first, official site as fallback), rasterize SVG to PNG at the size you need, and
   pass the paths in. Keep one download/convert path rather than repeating it per slide.

Skipping this list is exactly how the 2026-08-23 decks shipped with 16-19 distinct font
sizes, `line_spacing=None` everywhere, and Korean body text — the rules already existed in
scattered form and were never read before building.

## Two modes

**journal mode** — presenting someone else's published paper. Input is a DOI or title.
Structure (journal-club preset, 261004): Title (with the top-left "JOURNAL CLUB | date" kicker) → Authors →
Background/Motivation (2 slides) → **Reactions slide (mandatory, S3)** → Methods → Results (one slide per
PRIMARY figure) → Discussion → **Conclusions (summary)** → References → **Thank You** → hidden
**Appendix** slides (Strengths/Limitations, Questions for Discussion). Strengths/Limitations and
Questions are NOT in the main run: they sit after Thank You as hidden slides titled "Appendix: ..."
(qc_layout L6 only lets slides whose title starts with Appendix/Backup follow the references slide;
"Additional info" fails the gate).

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
exist.** Look in: the project folder for the paper/manuscript, a `figures/`
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

# S3: reaction structures from the paper's own figures, zero bullets, right after Background
s_r = deck.reactions_slide("Reaction scheme", ["assets/fig1.png"], "Scheme 1. ... (Scheme 1 from [1])")
deck.notes(s_r, "...")

s2 = deck.figure_slide(title="Key Result", subtitle="What this figure shows",
                        key_points=["<=3 bullets", "each one line"],
                        fig_path="assets/fig1.png",
                        caption_text="Figure 1. Caption text. (Figure 1 from [ref])")
deck.notes(s2, "...")

# S4: comparison with prior work = the source figure, never a bullet list of numbers
s_p = deck.prior_work_slide("Comparison with prior work", "assets/fig1.png", "Figure 5. ...", note="optional one-liner")
deck.notes(s_p, "...")

deck.table_slide("Kinetic Parameters", headers=[...], rows=[...])
deck.references_slide(["Author et al. (Year) Journal, Vol, Pages. DOI.", ...])

deck.save(str(Path.home() / "presentations" / "journal_club_YYYY-MM-DD_Topic.pptx"))
```

`Deck` methods reject an off-scale font size, line-spacing multiplier, or `space_after`
value by raising `StyleError` rather than silently accepting it — the closed list in
`references/style_spec.md` is enforced at the API boundary, not just checked afterward.

## Journal-club preset: `Deck(prefs="journal_club")`

Five rounds of presenter corrections on a 2026 TEA journal-club deck are stored as one preset,
`references/prefs/journal_club.json`, so the next journal-club deck starts from them instead of
rediscovering them. `Deck(prefs="journal_club")` applies the buildable ones and records the preset name in
`core_properties.category`, which makes `qc_deck.py` enforce the checkable ones (QC-20).

| Preference | Where it lives |
|---|---|
| Figure captions: 12 pt, not italic, not bold, centered, two lines (title line, then conditions); NO source line for figures from the presented paper, a short "Source: ..." only for externally added or self-derived figures | `Deck.caption()` with prefs |
| Slide text ends without a period (references slide and abbreviations such as "et al." keep theirs); speaker notes keep normal punctuation | `Deck.save()` strips; QC-20 P5 flags |
| Text beside a figure is 16 pt (use role `body`, not `sidebar_bullet` 14 pt) or goes to the notes; no left/right text columns, figure centered and filling down to the 7.0 in floor | style rule (layout is the author's job) |
| Title slide: small top-left "JOURNAL CLUB \| date" kicker + hairline; closing slide has none | `Deck.title_slide(kicker=)` |
| Closing slide: one huge "Thank you" (54 pt, declared by layout `thank_you`) and one line; no paper / DOI / presenter block | `Deck.closing_slide()` |
| Conclusions slide before the references: takeaway line + 2-3 columns (what the paper shows / what stays uncertain / open question) | `Deck.conclusions_slide()` |
| Strengths/Limitations and Questions as hidden "Appendix: ..." slides at the very end | `Deck.appendix_slide()`, `Deck.hide()` |

To change a preference, edit the JSON (and `tests/test_journal_club.py`), not the individual deck.

**Reactions slide covers the whole reaction sequence.** Read the paper's process flow diagram first and draw
every transformation from feed to product, not only the key step (261004: the first scheme showed only the
Ca(OH)2 isomerization; the paper's first step, acid hydrolysis of lactose, was added after the presenter
asked). Structures: black on white, rendered at 3x and downsampled, atom labels at a fixed readable size,
reversible steps as two close half-headed arrows; check stereochemistry against CIP labels before drawing.

## QC gate before delivery

```
"$PY" scripts/qc_deck.py <pptx_path> [--source content_analysis.json [--ledger ledger.json]]
```

`qc_deck.py` is the single entry point and folds in two modules (integrated 2026-10-04):
`scripts/qc_layout.py` (L1 text overflow, L2 shape overlap, L3 WCAG contrast, L4 hidden/blank/
placeholder, L5 stretched picture, L6 references-last order; text over text is CRITICAL; always on, `--no-layout` to skip) and `scripts/qc_numbers.py` (slide numbers vs
`content_analysis.json`: DRIFT / SOURCE-CONFLICT = CRITICAL; UNSOURCED / DERIVED-UNLABELED =
WARNING; only on when `--source` is given, otherwise the report says "NOT RUN", and exit-2 BLIND
is a warning, never a pass). The ledger JSON is the input for an independent verifier pass (numbers entering a deliverable).
Regression: `"$PY" tests/mutation_suite.py` plants 18 defects and prints how many the gate catches.

**QC-20 prose gate** (`scripts/qc_prose.py`, always on, `--no-prose` to skip; all WARNING): speaker notes that
carry drafting residue or to-dos (P1: "earlier draft said", "I will add this before the talk", SSOT, TODO),
notes that say "N questions" while the slide lists a different count (P2), the same sentence twice in one
notes block (P3), slide text with an em dash, Tier-1A AI vocabulary or a semicolon contrast in a
headline/takeaway (P4), trailing periods when the deck prefs forbid them (P5), no Conclusions/Summary slide
(P6), an Appendix slide that is not hidden (P7). It is the cheap regex layer, not the C-62 pass: run
`Skill(avoid-ai-writing)` in detect mode on the English slide text and the Korean notes (with
`korean-tells.md`) before delivery, and delete the notes lines P1 reports. Notes are for the talk: no drafting
history, no promises to check something later, no "removed from the slide" bookkeeping.

**QC-19 language gate** (optional language-gate module that sits beside this skill, always
on when importable, `--no-language` to skip): every text frame, table cell and grouped shape plus the speaker
notes. Foreign script (Han, Kana, Cyrillic, ...) anywhere = CRITICAL; British spelling, known
misspellings, accents and Latin-script foreign prose in the slide body = WARNING; Korean
spelling/spacing/particles in the notes = WARNING; dictionary-unknown English words are one
aggregated review line. If the skill cannot be imported the report says "language-gate NOT RUN"
(a warning, never a pass). Fix certain errors in the source text before rebuilding.

Exits non-zero on any CRITICAL finding (verified live: `echo $?` after a failing run
returns 1, not just "printed FAIL"). Checks (style_spec.md §9): word_wrap set,
`disable_autofit()` applied, line_spacing/space_after in the closed lists, font is Arial,
font size in the closed type scale (9pt floor), no Hangul outside notes, geometry (nothing
below the Y=7.0in floor except the sanctioned footer band — identified by shape shape
[height <=0.4in, bottom near the true 7.5in slide edge], not a fixed top-coordinate, since
measured real decks place footer text anywhere from 7.05in to 7.1in; side margins, with an
exemption for full-bleed header bars that intentionally span the whole slide width), every
slide has notes >=100 chars containing Korean, every picture >=3in in one dimension, font
colors within the active theme's palette (warning-level; for navy_lab the base 8 from style_spec.md
§5 plus 3 sanctioned derived colors documented in that section's "Sanctioned derived
colors" subsection — header-bar subtitle text and the Strengths/Limitations heading pair).

**Value-dispersion check (independent of every named rule above).** For font size,
line_spacing, space_after, font name, and autoshape fill color, `qc_deck.py` counts the
number of DISTINCT values actually used across the whole deck and flags WARNING if that
count exceeds the expected ceiling (the theme's size list, 3 spacings, 5 space_after values, 1 font, the
theme's palette size) — **even when every individual value is inside its allowed set**. This exists
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

## Themes (style_spec.md §10)

`Deck(theme=...)`: `navy_lab` (default), `assertion_evidence` (sentence headline + one figure, no bullets),
`journal_print` (white, thin red rule, long caption), `dark_seminar` (dark room, amber emphasis, figures on a
light plate), `mono_one` (grayscale + Okabe-Ito blue, adds the 54 pt `stat_big` / `Deck.stat_slide()`), plus 22 more (editorial / movement / brand / marketing / korean families; `python scripts/deck_builder.py --list-themes`, style_spec.md §10.3). One deck,
one theme; the name is stored in `core_properties.keywords` and `qc_deck.py` autodetects it (`--theme NAME`
overrides, fallback `navy_lab`). The type scale, line-spacing and space_after lists are shared by every theme.

**Spacing and size (261004 user decision):** body, sidebar bullets and presenter lines use **line spacing 2.0**
(1.5 is retired; memory standard S2); `body` stays **16 pt**; `sidebar_bullet` stays **14 pt** because it sits
beside a figure. A figure slide holds at most 3 one-line key points (budget derived in style_spec.md §6.1).
Text roles must meet WCAG contrast (4.5:1, or 3:1 for >= 18 pt bold): caption/footer are #666666, the orange accent
is for large bold text and graphics only.

## Lab standards S3 / S4 / S7

- **S3** `Deck.reactions_slide()` is mandatory right after Background in journal mode (QC warns if absent) and
  must show every reaction step of the paper's process, feed to product (see the journal-club preset section).
- **S4** `Deck.prior_work_slide()`: prior-work comparison is the embedded figure, never a list of numbers.
- **S7** `scripts/extract_figures.py paper.pdf --out assets/`: crops each figure by its image block
  (PyMuPDF `type == 1`), caption-free, 300 DPI, named after the nearest "Fig./Scheme N" caption.

Tests: `"$PY" -m pytest tests/test_themes.py -q` (every theme builds, QC 0 CRITICAL, closed lists unchanged,
contrast for every role/background pair, vertical budget, S7).

## Slide count / structure targets

Journal mode: 13-23 slides, typical 15-18. Research mode: similar range. Always include
Title, Background, Results, Discussion, Conclusions, References, Thank You (QC-20 P6 warns when the
Conclusions/Summary slide is missing). Figure-First
Layout rules (figure gets 55-70% of a results slide, text fits into what remains, never the
reverse) are in `references/style_spec.md` §6-7 and `references/pipeline.md`.

## Using a real template

When the lab hands you a downloaded template (any slide size), do not rebuild it with `Deck`: read it with
`scripts/template_adapter.py inspect <pptx>` (layout roles, placeholders, capacities; `gallery` renders every layout),
then `TemplateDeck(...).add(role_or_layout, title=, body=, picture=, notes=)`; templates whose design lives on the example
slides use `add_from_example()`. Text that does not fit, pictures that would be stretched or would collide with text, text
drawn in the background color, and missing Korean notes (>= 100 chars) are errors, never silent. Check the result with
`qc_deck.py <pptx> --external-template` (slide size read from the file; own-theme checks off, overflow / overlap /
contrast / notes / language gate on). `theme_from_template()` drafts a `THEMES` palette from the template's colors.
Private study use only, never copy template files into a repo. Full guide: `references/template_adapter.md`.

## Motion (Morph transitions)

`Deck.name_shape(shape, "Enzyme1")` + `Deck.morph(slide)` build a PowerPoint **Morph** sequence: one slide per
step, the same named objects moved/resized between steps, `morph()` on every slide after the first. Use it for
pathway walk-throughs and result build-ups. Charts and tables do not morph; iterative scenes (BO convergence)
are better as an mp4 from Manim inserted into the slide. Examples: artifact "PPT 모션 예시".

## Related skills (wiring, 2026-10-04)

A deck-building request routes here through the toolkit's skill router, which can also surface this list.
`manuscript-pipeline` (own manuscript presented as a deck: SSOT number sync, academic-qc, docx cross-check) ·
`academic-term-rules` (nomenclature) · `paper-extract` (figures/tables from the paper PDF) ·
`novelty-check` ("first report" sentences) · `literature-review` (background slides) ·
`avoid-ai-writing` (C-62 on slide text and Korean notes, detect) · `avoid-ai-visuals` (rendered PNG audit) ·
`publication-figures` (inserted figures) · `verification-gates` then an independent verifier pass for the
`--ledger` of numbers (check a number before it enters a deliverable) · `pptx` (commenting on someone else's deck: academic-review.md) ·
language-gate (QC-19: Korean/English only, English and Korean spelling), when installed.

## What this skill does not cover

- Paper download / PDF extraction (DOI resolution, PyMuPDF figure extraction) — that logic
  is the old command's Agent 1, kept verbatim in `references/paper_download.md`; reuse it,
  it was not part of this session's measured failures.
- Full nomenclature rule text — defer to `academic-term-rules` rather than duplicating it
  here; this skill only restates the subset that governs slide *layout/typography*.
