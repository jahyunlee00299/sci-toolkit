# Tasks: [FEATURE NAME]

**Input**: `spec.md` (user stories + priorities) and `plan.md` (stack, layout, contracts)

**Tests**: optional — include test tasks only if the spec or the user asked for them.

**Organization**: grouped by user story, so each story can be finished and verified alone.

## Format

```text
- [ ] T### [P?] [US#?] Description naming an exact file path
```

- **[P]** — parallel-safe: touches different files from every other unfinished task and
  depends on nothing incomplete. Two tasks writing the same file are never both `[P]`.
- **[US#]** — required for user-story tasks; omitted for Setup, Foundational, and Polish.
- Every description names a real path. "Add validation" is not a task.

> Replace every sample task below. They are shape examples, not work.

---

## Phase 1: Setup

**Purpose**: what has to exist before any real work starts.

- [ ] T001 Create the directory layout from `plan.md`
- [ ] T002 [P] Pin dependencies in [env file] and record the environment name

---

## Phase 2: Foundational

**Purpose**: blocking prerequisites — everything every user story needs. Nothing in Phase 3+
can start until this phase is done.

- [ ] T003 Implement [shared loader/config] in `[path]`

**Checkpoint**: foundation ready — user stories can begin.

---

## Phase 3: User Story 1 - [Title] (Priority: P1) 🎯 MVP

**Goal**: [what this story delivers on its own]

**Independent Test**: [how to verify this story with all later stories absent]

- [ ] T004 [P] [US1] [task] in `[exact path]`
- [ ] T005 [US1] [task] in `[exact path]`

**Checkpoint**: User Story 1 works end to end and is independently testable.

---

## Phase 4: User Story 2 - [Title] (Priority: P2)

**Goal**: [what this story delivers]

**Independent Test**: [how to verify this story alone]

- [ ] T006 [P] [US2] [task] in `[exact path]`

**Checkpoint**: User Stories 1 and 2 both work independently.

---

## Phase N: Polish

**Purpose**: cross-cutting work that needed the stories to exist first.

- [ ] T0NN [P] Document usage in `[path]`
- [ ] T0NN Verify each Success Criterion in `spec.md` and record the observation per criterion

---

## Dependencies

- Phase 1 → Phase 2 → user story phases (priority order) → Polish
- [Any dependency between stories — most should have none]

## Parallel opportunities

- [Which `[P]` tasks can genuinely run together, and why they do not share a file]

## Implementation strategy

**MVP**: User Story 1 only. Finish it, verify it independently, and stop there if that
answers the need — the later stories are increments, not obligations.
