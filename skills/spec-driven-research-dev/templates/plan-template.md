# Implementation Plan: [FEATURE]

**Feature directory**: `specs/[NNN-short-name]/` | **Date**: [DATE] | **Spec**: [link to spec.md]

> Filled in during Phase 2, reading `spec.md` — not from memory of the conversation.

## Summary

[The primary requirement from the spec, plus the technical approach chosen to meet it, in a
few sentences.]

## Technical Context

**Language/Version**: [e.g. Python 3.11 — or NEEDS CLARIFICATION]

**Primary Dependencies**: [e.g. pandas, scipy, matplotlib — or NEEDS CLARIFICATION]

**Data storage / format**: [e.g. CSV exports on a share, xlsx workbook, SQLite — or N/A]

**Testing**: [e.g. pytest — or NEEDS CLARIFICATION]

**Target environment**: [e.g. lab Windows machine, conda env `<name>`, shared HPC]

**Scale/Scope**: [e.g. ~200 files per run, ~10 MB each, run weekly]

**Reproducibility constraints**: [seeds, pinned versions, anything that must be deterministic]

## Unknowns → research

> One row per `NEEDS CLARIFICATION` above. Resolve each before designing. A decision with
> no rejected alternative usually means no choice was made.

| Unknown | Decision | Rationale | Alternatives rejected (and why) |
|---|---|---|---|
| [what was unclear] | [what was chosen] | [why] | [what else was considered] |

## Project rules check

*GATE: must pass before design. Re-check after the design below is written.*

> Check the plan against this repository's own operating rules (`AGENTS.md`). Record the
> verdict — an unstated violation is the one that survives review.

| Rule | Verdict | Note |
|---|---|---|
| §1 SOLID — one job per module; split when concerns mix | [PASS / violated] | |
| §2 Verification — how each output gets independently re-checked | [PASS / violated] | |
| §3 Number SSOT — one canonical script owns each reported number | [PASS / violated / N/A] | |
| Fitted / optimized results routed through `scientific-validation` | [PASS / N/A] | |
| Secrets stay out of code and out of the repo | [PASS / violated] | |

## Data model

> Entities, their fields, and — for anything physical — units. Omit if the feature handles
> no structured data.

- **[Entity]**: [fields, types, units, relationships, validation rules from the spec]

## Interface contract

> What this exposes to whoever runs it. CLI arguments for a script, the signature and
> return type for a module, the file contract for a pipeline stage. Skip only for
> genuinely internal one-off code.

```text
[e.g. python scripts/<name>.py <input-dir> --out <path> [--strict]
      exit 0 = all inputs processed · exit 1 = at least one input unusable]
```

## Number provenance

> Which script owns each reported number, and from which raw source. Decide this here:
> two scripts producing the same quantity is how they end up disagreeing.

| Reported quantity | Owning script | Raw source |
|---|---|---|
| [e.g. per-sample yield] | [path to the one script that computes it] | [raw export column, with units] |

## File layout

> Real paths. Delete the placeholders.

```text
scripts/
└── [name].py
tests/
└── test_[name].py
```

**Structure decision**: [why this layout, and where it follows the repository's existing
convention rather than inventing a new one]

## Validation approach

[How the finished feature gets checked against the spec's Success Criteria — the specific
command or observation per criterion, not "run the tests".]

## Complexity tracking

> Fill **only** if the rules check above has a violation that must stand.

| Violation | Why it is necessary | Simpler alternative rejected because |
|---|---|---|
| [what rule is broken] | [the need driving it] | [why the simpler path does not work] |
