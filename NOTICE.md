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

## Adapted from upstream projects

Some skills here were **adapted**, not vendored: the mechanism was taken and
rewritten in this repository's own format and voice, targeted at research work.
Attribution is required by the upstream licenses and is recorded here.

| Skill in this repo | Adapted from | Upstream license |
|---|---|---|
| `skills/debugging-loop` | `skills/engineering/diagnosing-bugs` in [mattpocock/skills](https://github.com/mattpocock/skills) | MIT (Copyright (c) 2026 Matt Pocock) |
| `skills/test-quality` | `skills/engineering/tdd` (SKILL.md + tests.md) in [mattpocock/skills](https://github.com/mattpocock/skills) | MIT (Copyright (c) 2026 Matt Pocock) |
| `skills/code-quality` (Mode C, two-axis review only) | `skills/engineering/code-review` in [mattpocock/skills](https://github.com/mattpocock/skills) | MIT (Copyright (c) 2026 Matt Pocock) |
| `skills/spec-first-development`, `skills/test-first-development` | brainstorming / plan-writing / TDD methodology in [obra/superpowers](https://github.com/obra/superpowers) | MIT (Copyright (c) 2025 Jesse Vincent) |
| `skills/spec-driven-research-dev` | four-phase spec-driven workflow + artifact templates in [github/spec-kit](https://github.com/github/spec-kit) | MIT (Copyright GitHub, Inc.) |
| `skills/analysis-code-testing` | `plugins/python-development/skills/python-testing-patterns` in [wshobson/agents](https://github.com/wshobson/agents) | MIT (Copyright (c) 2024 Seth Hobson) |
| `skills/data-quality-checks` | `plugins/data-engineering/skills/data-quality-frameworks` in [wshobson/agents](https://github.com/wshobson/agents) | MIT (Copyright (c) 2024 Seth Hobson) |
| `skills/avoid-ai-writing/korean-tells.md` (Korean detect-only supplement; the skill itself is vendored upstream MIT) | `skills/humanize-korean/references/ai-tell-taxonomy.md` (Korean AI Tell Taxonomy v2.0) in [epoko77-ai/im-not-ai](https://github.com/epoko77-ai/im-not-ai) | MIT |

The upstream MIT license permits this use and requires the copyright notice be
retained; that is what this section does. No upstream file is redistributed
verbatim — what was taken is the discipline (build the feedback loop before the
hypothesis; rank falsifiable hypotheses; tag debug output; the tautological-
assertion and internal-coupling test failures), not the text.

`skills/spec-first-development/SKILL.md` and
`skills/test-first-development/SKILL.md` take the three-path classification, the
approval gate, the no-placeholder rule, and the red-green-refactor cycle with its
rationalization table from **[obra/superpowers](https://github.com/obra/superpowers)**,
© 2025 Jesse Vincent, **MIT License**. The text was rewritten for a research
codebase (data loaders, fitting routines, analysis pipelines) rather than
vendored, and the surrounding framework of that project (its hooks, commands,
subagent orchestration, and plugin wiring) is deliberately **not** included.
MIT permits this adaptation; this notice is the required attribution.

`skills/spec-driven-research-dev/` adapts the four-phase spec-driven workflow
(specify → plan → tasks → implement) and its artifact templates from:

- **github/spec-kit** — <https://github.com/github/spec-kit> — MIT License,
  Copyright GitHub, Inc.

The workflow structure, the phase-artifact separation, the `[ID] [P] [Story]`
task format, and the spec-quality checklist mechanism come from there. The
prompts and templates were rewritten for research code — the upstream
originals assume web/app projects, carry an extension-hook system and a CLI
(`specify`) that this package does not ship, and their templates ask about
frameworks and endpoints rather than instrument formats, units, failure
policy, and number provenance. No upstream file is vendored verbatim.

MIT permits this reuse; the attribution above is the condition.

Two skills are adaptations of units from
[`wshobson/agents`](https://github.com/wshobson/agents) (MIT, Copyright (c) 2024
Seth Hobson). Neither is a verbatim copy: the upstream text was rewritten for
laboratory analysis work, the tool-specific material was dropped, and the
upstream `model:`/agent-type routing fields do not carry over — skills in this
package are model-neutral.


MIT requires the copyright notice be retained; this section is that notice.
`tests/test_adopted_skills.py` pins this section, the `upstream:` front-matter
lines, and the model-neutrality of both skills.

## Skills with their own terms

| License | Skills |
|---|---|
| MIT | most of `skills/`, including several authored by K-Dense Inc. |
| Apache-2.0 | see the individual `SKILL.md` |
| BSD-3-Clause | see the individual `SKILL.md` |

If a skill's `SKILL.md` says `license: Unknown`, treat it as "do not
redistribute" until its origin is established.
