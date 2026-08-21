# NOTICE — licensing of the bundled skills

The repository-level `LICENSE` (MIT) covers the packaging — installer, doctor,
tests, connectors, hooks, evals, docs — and the skills authored for this
toolkit. Individual skills under `skills/` declare their own `license:` in the
front matter of their `SKILL.md`, and **that declaration governs**.

Check the front matter before redistributing anything from here. A
repository-level license claim that contradicts a bundled skill's own terms is
a licensing defect, not a formality.

## Not in this repository

`docx`, `pdf`, `pptx` and `xlsx` are Anthropic's skills. Their `LICENSE.txt`
states, in part:

> - Extract these materials from the Services or **retain copies of these
>   materials outside the Services**
> - **Distribute**, sublicense, or transfer these materials to any third party

Both are prohibited. So these four are **deliberately absent** — not forgotten.
The package still knows about them: `config/catalog.json` marks them
`external`, `install/install.py` skips them and explains why, `doctor.py`
reports their status without failing, and `AGENTS.md` §0 footnotes the rows
that route to them. See `docs/12_문서스킬_직접_준비하기.md`.

Seven manuscript tools that used to live inside the `docx` skill folder were
written by this lab, not by Anthropic. They have been moved to
`skills/manuscript-pipeline/scripts/` and remain under MIT:

    manuscript_text.py        word_com_ops.py       figure_caption_check.py
    manuscript_ref_order.py   word_live_edit.py     endnote_biblio_check.py
    visual_check.py

None of them import anything from the Anthropic skill.

## Upstream sources adapted here

`skills/spec-first-development/SKILL.md` and
`skills/test-first-development/SKILL.md` are adapted from the brainstorming,
plan-writing, and test-driven-development methodology of
**[obra/superpowers](https://github.com/obra/superpowers)**, © 2025 Jesse
Vincent, **MIT License**. The methodology — the three-path classification, the
approval gate, the no-placeholder rule, the red-green-refactor cycle and its
rationalization table — comes from there. The text was rewritten for a research
codebase (data loaders, fitting routines, analysis pipelines) rather than
vendored, and the surrounding framework of that project (its hooks, commands,
subagent orchestration, and plugin wiring) is deliberately **not** included.
MIT permits this adaptation; this notice is the required attribution.

## Skills with their own terms

| License | Skills |
|---|---|
| MIT | most of `skills/`, including several authored by K-Dense Inc. |
| Apache-2.0 | see the individual `SKILL.md` |
| BSD-3-Clause | see the individual `SKILL.md` |

If a skill's `SKILL.md` says `license: Unknown`, treat it as "do not
redistribute" until its origin is established.
