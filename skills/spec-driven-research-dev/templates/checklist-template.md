# Specification Quality Checklist: [FEATURE NAME]

**Purpose**: validate that `spec.md` is complete enough to plan against
**Created**: [DATE]
**Feature**: [link to spec.md]

> This checks the **specification**, not the implementation. `[x]` here means the spec
> meets the criterion — it says nothing about whether any code exists.

## Content quality

- [ ] No implementation detail (language, library, file layout, function names)
- [ ] Focused on what must be true and why, not on mechanism
- [ ] Readable by someone who knows the science but not the codebase
- [ ] All mandatory sections filled

## Requirement completeness

- [ ] No `[NEEDS CLARIFICATION]` markers remain
- [ ] Every functional requirement is falsifiable — an observation could show it unmet
- [ ] Success criteria are measurable
- [ ] Success criteria name no library, framework, or function
- [ ] Acceptance scenarios are defined for each user story
- [ ] Edge cases identified: malformed input, failure policy, re-run behavior, empty input
- [ ] Scope is bounded — Out of Scope is filled, not empty by default
- [ ] Assumptions are written down rather than left implicit

## Research-specific

- [ ] Input format, columns, and **units** are stated, not guessed
- [ ] Failure policy is explicit — does a bad sample halt the batch or get flagged?
- [ ] Reported numbers have a named canonical source (script + raw data)
- [ ] What must be reproducible on re-run is stated, and what may vary is justified

## Feature readiness

- [ ] Each user story has an Independent Test
- [ ] P1 alone is a coherent MVP
- [ ] The spec would still be understandable after the conversation is gone

## Notes

- Items left unchecked block Phase 2. Record why here rather than ticking them to proceed.
