# Feature Specification: [FEATURE NAME]

**Feature directory**: `specs/[NNN-short-name]/`
**Created**: [DATE]
**Status**: Draft
**Input**: [the user's original description, quoted]

> Write **what** must be true and **why**. No language, library, file layout, or function
> name belongs in this file — those are Phase 2 decisions. Delete any optional section
> that does not apply rather than leaving it as "N/A".

## User Scenarios & Testing *(mandatory)*

### User Story 1 - [Brief title] (Priority: P1)

[What someone needs to accomplish, in their words, without naming the mechanism.]

**Why this priority**: [Why this is the first slice worth building — this story alone is the MVP.]

**Independent Test**: [How to verify this story works on its own, with the later stories absent.]

**Acceptance Scenarios**:

1. **Given** [starting state], **When** [action], **Then** [observable result]
2. **Given** [starting state], **When** [action], **Then** [observable result]

### User Story 2 - [Brief title] (Priority: P2)

[Description.]

**Why this priority**: [Rationale.]

**Independent Test**: [How to verify this story alone.]

**Acceptance Scenarios**:

1. **Given** …, **When** …, **Then** …

### Edge Cases

> The ones that actually recur in research code — answer them here or they get decided
> silently at 2 a.m. by whoever is implementing.

- What happens when an input file is malformed, truncated, or has an unexpected column?
- Does one bad sample halt the batch, or get flagged and skipped? Where is it reported?
- What happens on a re-run — overwrite, append, or refuse?
- What if the input is empty, or a single row, or far larger than expected?

## Requirements *(mandatory)*

### Functional Requirements

> Every requirement must be falsifiable: state what observation would show it unmet.

- **FR-001**: The system MUST [specific capability]
- **FR-002**: The system MUST [specific capability]
- **FR-003**: The system MUST [how it behaves when an input is unusable]

### Key Entities *(include if the feature handles structured data)*

- **[Entity]**: [what it represents, its fields, and — for anything physical — its **units**]

## Success Criteria *(mandatory)*

> Measurable and stated without reference to how they are achieved. If a criterion names a
> library or a function, rewrite it as the outcome that would be observed.

### Measurable Outcomes

- **SC-001**: [e.g. "every input file in a run folder is either parsed or listed with a reason"]
- **SC-002**: [e.g. "a 200-sample batch completes with no manual step between files"]
- **SC-003**: [e.g. "re-running on unchanged inputs reproduces the reported values exactly"]

## Reproducibility & Provenance *(mandatory for anything producing numbers or figures)*

- **Canonical source**: [which script and which raw data each reported number comes from]
- **Must be reproducible**: [which outputs must be identical on re-run]
- **Allowed to vary**: [which outputs may differ, and why — e.g. a seeded sampler]

## Assumptions

> Every informed guess made while writing this spec. This section is what makes a guess
> reviewable instead of invisible.

- [Assumption, and the default it was based on]

## Out of Scope

- [What this feature deliberately does not cover, so scope creep is visible when it starts]

## Open Questions

> Maximum 3. Only for choices that materially change scope with no reasonable default.

- [ ] [NEEDS CLARIFICATION: specific question]
