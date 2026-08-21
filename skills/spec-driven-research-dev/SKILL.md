---
name: spec-driven-research-dev
description: |
  Four-phase spec-driven workflow for research code: specify → plan → tasks → implement.
  Use it when a coding request is big enough that jumping straight to an edit loses the
  thread — a new analysis pipeline, a new script that several people will run, a rewrite
  of a fitting/simulation module, or any change whose scope you cannot hold in your head.

  Each phase writes one artifact under `specs/<NNN-short-name>/`, and each phase reads the
  previous one instead of re-deriving intent from chat history. The point is that the
  intent survives: a spec written on Monday still says what the code was for on Friday,
  after the conversation is gone.

  Use this skill when:
  - The user describes a capability to build, not a line to change ("we need something
    that batches the HPLC exports and flags outliers")
  - A script is about to be rewritten and the current behavior is only in someone's head
  - Work will be split across sessions, machines, or people and must survive the handoff
  - The user says: "새 파이프라인 만들자", "이거 제대로 설계해서 만들자", "스펙부터",
    "설계부터 하자", "명세 먼저", "작업 쪼개줘", "구현 계획 세워줘",
    "spec first", "plan this out", "break this into tasks", "spec-driven"

  Do NOT use for: a one-line fix, a parameter change, a single-file edit, or a question
  (just do it — the ceremony costs more than the work). Do NOT use for running a fit or
  an optimization (kinetic-bo-pipeline / the relevant analysis skill), for validating a
  number a run produced (scientific-validation), or for writing a manuscript
  (manuscript-pipeline).
license: MIT license
metadata:
    skill-author: generic
    adapted-from: github/spec-kit (MIT) — see NOTICE.md
---

# Spec-Driven Development for Research Code

Research code fails in a particular way. It is written quickly against a question that is
clear at the time, it works, and six months later nobody — including its author — can say
what it was supposed to do, so nobody can say whether it still does it. The code survives;
the intent does not.

This skill front-loads four artifacts that outlive the conversation:

| Phase | Artifact | Answers |
|---|---|---|
| 1. Specify | `spec.md` | **What** must be true when this works, and how would we know? |
| 2. Plan | `plan.md` | **How** — stack, structure, data shape, and what we chose against |
| 3. Tasks | `tasks.md` | **In what order**, in dependency order, each naming a real file |
| 4. Implement | the code | Executed against `tasks.md`, verified against `spec.md` |

**The phases are separable on purpose.** Stopping after `spec.md` is a legitimate outcome —
a written spec that shows the work is not worth doing has already paid for itself.

## The rule that makes this worth doing

**Phase 1 forbids implementation detail.** No language, no library, no file layout, no
function name in `spec.md`. This is not style policing. Writing "the tool must flag runs
whose mass balance closes worse than 95%" instead of "add a `check_balance()` to
`qc.py`" is what exposes that nobody had agreed what "closes" means. Naming the function
first hides that question behind a decision that looks settled.

Success criteria carry the same rule: they must be measurable and stated without reference
to how they are met.

- Good — "every raw file in a run folder is accounted for: parsed, or listed with a reason"
- Good — "a 200-sample batch finishes without manual steps between files"
- Bad — "the pandas merge is efficient" (names the tool, measures nothing)
- Bad — "parsing is robust" (not verifiable — robust against what?)

## Where the artifacts go

```text
specs/<NNN-short-name>/
├── spec.md          # Phase 1 — what and why
├── plan.md          # Phase 2 — how
├── tasks.md         # Phase 3 — ordered work items
└── checklists/
    └── requirements.md   # Phase 1 self-check, written by phase 1
```

`<NNN>` is the next free 3-digit number in `specs/`; `<short-name>` is 2–4 words in
action-noun form (`hplc-batch-qc`, `refit-kla-model`). Create exactly one feature
directory per invocation.

If the repository has a `PROJECT_STRUCTURE.md`, `AGENTS.md`, or `CLAUDE.md`, read it before
Phase 2 — its conventions are constraints on the plan, not suggestions.

---

## Phase 1 — Specify

**Input**: the user's description. **Output**: `spec.md` + `checklists/requirements.md`.

1. Copy `templates/spec-template.md` to `spec.md` and fill it, preserving section order.
2. Extract actors, actions, data, and constraints from the description.
3. For anything unclear, **make an informed guess and record it under Assumptions.**
   Mark `[NEEDS CLARIFICATION: <specific question>]` only when the choice materially
   changes scope and no reasonable default exists. **Hard limit: 3 markers.** Prioritize
   scope > correctness/safety of the result > usability > technical detail.
4. Write scenarios as user stories in priority order (P1, P2, P3), each with an
   **Independent Test** — how that story alone can be verified as working. P1 is the MVP.
5. Write functional requirements. Every one must be testable: if you cannot state what
   observation would falsify it, rewrite it.
6. Self-check against `checklists/requirements.md`. Fix what fails and re-check, up to 3
   rounds; record anything still failing in the checklist notes rather than hiding it.
7. If `[NEEDS CLARIFICATION]` markers remain, ask them **together, once** — as a numbered
   list with suggested options — rather than interrogating one at a time.

### Research-specific things to pin in the spec

These are the ones that come back to bite when left implicit:

- **Inputs**: which instrument/export format, which columns, which units. Never guess a
  column meaning — say it is unknown and ask.
- **What counts as done for one sample** vs for a batch.
- **Failure policy**: does a bad sample stop the run or get flagged and skipped? Silent
  skipping is how a batch silently reports on 190 of 200 samples.
- **What must be reproducible**: which outputs must be byte-identical on a re-run, and
  which are allowed to vary (and why).

## Phase 2 — Plan

**Input**: `spec.md`. **Output**: `plan.md` (+ `research.md` when there are open unknowns).

1. Read `spec.md` in full. Do not plan from memory of the conversation.
2. Fill Technical Context: language/version, dependencies, data storage, test approach,
   scale. Mark unknowns `NEEDS CLARIFICATION` rather than picking silently.
3. **Resolve those unknowns before designing.** For each one, write into `research.md`:
   *Decision* / *Rationale* / *Alternatives considered and why rejected*. A decision with
   no rejected alternative usually means no choice was actually made.
4. Check the plan against this repository's own rules (`AGENTS.md` §1 SOLID, §2
   verification, §3 number SSOT). Where the plan violates one, either fix the plan or
   record the violation and its justification in Complexity Tracking — do not leave it
   unstated.
5. Define the data shape (entities, fields, units, relationships) and the interface the
   thing exposes — CLI arguments for a script, the function signature for a module. Skip
   this only for genuinely internal one-off code.
6. Write the concrete file layout. Real paths, not a placeholder tree.

### The gate that belongs to this repository

Any output of this plan that is a **number, a fitted parameter, or a figure** must trace
to one canonical script and its raw data (`AGENTS.md` §3), and any fitted or optimized
result must pass `scientific-validation` before it is reported. Decide *in the plan* which
script owns each number. Deciding it later is how two scripts end up producing the same
quantity and disagreeing.

## Phase 3 — Tasks

**Input**: `spec.md` + `plan.md`. **Output**: `tasks.md`.

Organize by user story, so each story can be finished and tested on its own.

```text
- [ ] T001 [P] [US1] Description that names an exact file path
```

- **T###** — sequential in execution order.
- **[P]** — only if it touches different files from every other task not yet done and
  depends on nothing incomplete. Two tasks writing the same file are never both `[P]`.
- **[US#]** — required for user-story tasks; omitted for Setup, Foundational, and Polish.
- The description must name a real path. "Add validation" is not a task; "Add a unit check
  to `<the parser script>`, named by its real path" is.

Phase order: **Setup** → **Foundational** (blocking prerequisites — anything every story
needs) → **one phase per user story in priority order** → **Polish**. Mark a checkpoint at
the end of each story phase stating what should now work end to end.

Tests are optional and included **only** if the spec or the user asked for them. When they
are included, the test task for a behavior comes before the task implementing it.

## Phase 4 — Implement

**Input**: `tasks.md`. **Output**: working code.

1. Re-read `tasks.md`, `plan.md`, and `spec.md` before starting.
2. If `checklists/` has unchecked items, report the counts and **ask before proceeding.**
   Do not tick someone else's checklist to clear the path.
3. Work phase by phase, in order. Sequential tasks in sequence; `[P]` tasks may go
   together. Mark each finished task `[X]` in `tasks.md` as you go — that file is the
   progress record, and an unmarked file after a crash is indistinguishable from no work.
4. **Halt on a failed non-parallel task** and report it. Continue past a failed `[P]` task
   only for the others, and report which failed. Do not paper over a failure to reach the
   end of the list.
5. Never weaken a check to make it pass. If a check is wrong, say so explicitly and
   justify the change (`AGENTS.md` §0, rule 2).

### Done means verified, not executed

A script exiting 0 is not evidence the output is correct (`AGENTS.md` §2). Before
reporting the feature done:

- Re-derive at least one non-trivial output independently of the code that produced it.
- Walk the **Success Criteria** in `spec.md` one at a time and state, per criterion, the
  observation that satisfies it. A criterion you cannot demonstrate is not met — say so.
- Run whatever gate `AGENTS.md` §0 assigns to the artifact class you produced.

## Anti-patterns

- **Writing all four artifacts in one pass without reading back.** The value is in each
  phase reading the last one; skip that and you have written four documents restating one
  paragraph.
- **Implementation detail in `spec.md`.** See the rule above — it hides the disagreement
  the spec exists to surface.
- **Tasks without file paths.** They cannot be executed or checked off honestly.
- **Ceremony on a small change.** A one-line fix does not need a spec directory. Say you
  are skipping the workflow and why, then fix it.
- **Treating the spec as frozen.** When implementation proves the spec wrong, update the
  spec and say what changed — do not let the code and the spec silently disagree.

## Templates

`templates/spec-template.md`, `templates/plan-template.md`, `templates/tasks-template.md`,
`templates/checklist-template.md` — copy, don't rewrite from memory.

Adapted from [github/spec-kit](https://github.com/github/spec-kit) (MIT). See `NOTICE.md`.
