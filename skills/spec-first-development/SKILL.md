---
name: spec-first-development
description: >
  Turn a vague research-software request into an approved design, then a written
  spec, then a bite-sized implementation plan — before any code is written. Three
  paths sized to the request (spike / bounded / architectural), a hard approval
  gate that never scales down, a placeholder ban, and a self-review pass over both
  spec and plan. Use before building or changing a fitting script, a data pipeline,
  an analysis tool, or any feature where "just start coding" would lock in an
  assumption nobody checked. 한국어 트리거 — 설계부터, 스펙 먼저, 기획 좀,
  구현 계획 세워, 어떻게 만들지 정하자, 만들기 전에 정리, 요구사항 정리.
license: MIT
---

# spec-first-development

The expensive failure in research code is almost never a syntax error. It is
finishing a 400-line pipeline and discovering it answers a different question
than the one asked — the units were per-well and the model wanted per-litre, the
"blank" column was already subtracted, the fit was supposed to be global across
runs and was written per-run. None of that is caught by testing harder. It is
caught by agreeing on what is being built *before* building it.

This skill is the front half of the development loop: **intent → design →
spec → plan.** The back half (write the failing test first) is
`test-first-development`, which this skill hands off to.

Adapted from the brainstorming and plan-writing methodology of
[obra/superpowers](https://github.com/obra/superpowers) (MIT). See `NOTICE.md`.

---

## The hard gate

> **Write no implementation code until you have told the requester what you
> intend to build and they have said yes.**

The *artifact* scales with the task — sometimes two sentences in chat, sometimes
a committed spec document. The *approval* never scales. A one-function utility
and a new subsystem both stop and wait.

This is the rule that gets rationalized away first, so it is stated first.

---

## Step 1 — Classify the request, out loud

Say which path you are taking before you ask your first question, so the
requester can override you:

> "This looks bounded — the fitting script already exists and you want one more
> output column — so I'll sketch the design here rather than write a spec file."

| Path | What it is | Output |
|---|---|---|
| **Spike** | A feasibility question — "can we even fit this?", "does the instrument export include the timestamps?", "quick and dirty is fine". The deliverable is an *answer*, not code you keep. | 2–3 sentence probe plan → a recommendation. Anything built is labelled throwaway. |
| **Bounded** | A well-scoped change to code that **already exists in this repo**: one more CLI flag, one extra plot panel, a unit fix in an existing loader. | A few clarifying questions → a short design in chat → approval → implement. No spec file, no plan document. |
| **Architectural** | New scripts/subsystems, a new analysis pipeline, anything that changes an interface other scripts depend on (a data schema, a shared loader's return type, a results file format). | Questions → 2–3 approaches → sectioned design → written spec → implementation plan. |

**Bounded measures the repo, not your familiarity.** "I have written many
kinetics fitters" does not make a new one bounded — bounded means the flow you
are changing is here to read. A new project has no existing flow: it is
architectural.

**The ratchet is one-way.** When hidden complexity shows up mid-task — the raw
files turn out to be three different instrument formats, the "one extra column"
needs a schema change — stop, say so, and step *up* a path. Nothing ever steps
down mid-task. When torn between two paths, take the heavier one.

---

## Step 2 — Understand before proposing

- **Read the current state first**: the existing script, the raw data file's
  actual header, recent commits, any `PROJECT_STRUCTURE.md`. Do not reconstruct
  the codebase from memory or from what a similar project did.
- **Check scope before refining details.** If the request is really several
  independent subsystems ("a tool that ingests HPLC exports, fits kinetics, runs
  the optimizer, and writes the figures"), say so immediately and help decompose
  it. Do not spend your questions polishing one corner of a project that needs
  splitting first. Each sub-project gets its own spec → plan → implementation
  cycle.
- **Ask one question per message.** Multiple-choice where possible. Aim at
  purpose, constraints, and success criteria — not at trivia you could look up.

Questions worth asking in a research context, when the answer is not already
written down:

- What exactly is the input — one file, a folder, one row per replicate or per
  timepoint? Show me a real one.
- Which columns are already corrected (blank-subtracted, dilution-corrected,
  baseline-shifted) and which are raw?
- What are the units, and what units does the downstream consumer expect?
- What makes the output *right*? Is there a known-answer case, a published
  value, or an analytic limit we can check against?
- Does this need to reproduce an earlier result exactly, or supersede it?
- Who else reads the output file — a figure script, a manuscript table, another
  person?

---

## Step 3 — Approaches and design (architectural path)

- Propose **2–3 approaches** with trade-offs. Lead with your recommendation and
  say why.
- **YAGNI ruthlessly.** Strip every feature nobody asked for out of every
  approach. A configurable backend nobody will use is a liability you will
  maintain.
- Present the design **in sections scaled to their complexity** — a few
  sentences where it is obvious, up to a few hundred words where it is not.
  Ask after each section whether it looks right so far.
- Cover: architecture, components, data flow, error handling, testing.

**Design for isolation.** Split the work into units that each have one job,
communicate through a defined interface, and can be tested on their own. For
each unit you should be able to say what it does, how it is used, and what it
depends on. In a research context this usually means keeping **loading**,
**computing**, **plotting**, and **CLI parsing** apart — the single most common
reason a fitting script cannot be tested is that reading the file and doing the
maths live in the same function.

**In an existing codebase**, follow the patterns already there. Fix problems
that genuinely obstruct the work (a loader that has grown to do six things);
do not propose unrelated refactoring.

---

## Step 4 — Write the spec (architectural path only)

Save the validated design to `docs/specs/YYYY-MM-DD-<topic>-design.md` and
commit it. (A stated project preference for another location wins.)

Then **self-review it with fresh eyes** — inline, no second agent:

1. **Placeholder scan** — any "TBD", "TODO", unfinished section, or vague
   requirement? Fix it now.
2. **Internal consistency** — do any two sections contradict each other? Does
   the stated architecture match the feature descriptions?
3. **Scope check** — is this focused enough for one implementation plan, or does
   it still need decomposing?
4. **Ambiguity check** — could any requirement be read two ways? Pick one and
   write it explicitly.
5. **Number provenance** — every constant, threshold, and reference value in
   the spec names where it comes from (a raw file, a canonical script, a cited
   paper). A number whose only origin is this conversation is not yet a
   requirement (see `AGENTS.md` §3).

Fix issues inline and move on — no re-review loop.

**Then stop and hand the spec over:**

> "Spec written and committed to `<path>`. Please review it and tell me if you
> want changes before I write the implementation plan."

Wait. If changes are requested, make them and re-run the self-review.

---

## Step 5 — Write the implementation plan (architectural path only)

Save to `docs/plans/YYYY-MM-DD-<feature-name>.md`.

Write it for a competent programmer who knows **nothing** about this project or
its problem domain, and who does not know good test design. In this lab that is
often literally true — the reader may be a new member, or you in four months.
Document which files to touch, the actual code, how to test it, what to read
first.

**Map the file structure before writing tasks.** Which files get created,
which get modified, what each is responsible for. This is where decomposition
gets locked in. Files that change together live together; split by
responsibility, not by technical layer.

**Right-size the tasks.** A task is the smallest unit that carries its own test
cycle and is worth a reviewer's gate. Fold setup, config, and docs into the task
whose deliverable needs them. Split only where a reviewer could sensibly reject
one task and approve its neighbour. Each task ends in something independently
testable.

**Steps inside a task are one action each, 2–5 minutes:**

1. Write the failing test
2. Run it, watch it fail
3. Write the minimal code to pass
4. Run it, watch it pass
5. Commit

### Plan header

```markdown
# <Feature> Implementation Plan

**Goal:** [one sentence — what this builds]

**Architecture:** [2–3 sentences on the approach]

**Stack:** [key libraries and versions]

**Spec:** [path to the design doc this implements — the plan argues from the
spec, so they travel together]

## Global constraints

[Project-wide requirements copied verbatim from the spec — version floors,
dependency limits, units, naming rules, file-format requirements. One line
each. Every task inherits this section.]
```

### Task structure

````markdown
### Task N: <component>

**Files:**
- Create: `src/kinetics/loader.py`
- Modify: `src/kinetics/cli.py:40-58`
- Test: `tests/test_loader.py`

**Interfaces:**
- Consumes: [exact signatures this task uses from earlier tasks]
- Produces: [exact function names, parameter and return types later tasks
  rely on — the implementer sees only their own task, so this block is how
  they learn the neighbouring names]

- [ ] **Step 1: Write the failing test**

```python
def test_loader_reports_time_in_seconds():
    df = load_progress_curve("tests/data/run_minutes.csv")
    assert df["time_s"].iloc[-1] == 600.0
```

- [ ] **Step 2: Run it and watch it fail**

Run: `pytest tests/test_loader.py::test_loader_reports_time_in_seconds -v`
Expected: FAIL — `load_progress_curve` is not defined

- [ ] **Step 3: Minimal implementation**

```python
def load_progress_curve(path):
    df = pd.read_csv(path)
    df["time_s"] = df["time_min"] * 60.0
    return df
```

- [ ] **Step 4: Run it and watch it pass**

Run: `pytest tests/test_loader.py::test_loader_reports_time_in_seconds -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/kinetics/loader.py tests/test_loader.py
git commit -m "feat(kinetics): load progress curves with time normalised to seconds"
```
````

### No placeholders — these are plan failures

Never write any of these into a plan:

- "TBD", "TODO", "implement later", "fill in details"
- "add appropriate error handling" / "add validation" / "handle edge cases"
- "write tests for the above" without the actual test code
- "similar to Task 3" — repeat the code; tasks get read out of order
- a step that says *what* without showing *how* (code steps need code blocks)
- a reference to a function, type, or column that no task defines

### Plan self-review

After the plan is complete, check it against the spec yourself:

1. **Spec coverage** — walk each spec requirement. Can you point at the task
   that implements it? Add tasks for any gap.
2. **Placeholder scan** — search for every red flag above. Fix them.
3. **Name consistency** — do the function names, signatures, and column names
   used in later tasks match what earlier tasks defined? `time_s` in Task 2 and
   `t_sec` in Task 5 is a bug you can fix for free right now.

Fix inline, then move on.

---

## Red flags

| Thought | Reality |
|---|---|
| "This is too simple to need a design" | Simple means a *short* design, not no design. Two sentences, then approval. |
| "I'll call it bounded and skip the spec" | Reaching for a label in order to skip work *is* the doubt. Take the heavier path. |
| "The design is obvious — I'll start while they read it" | The gate is the approval, not the design's length. Present, then stop. |
| "I know this kind of analysis, so it's bounded" | Bounded measures the repo, not your experience. No existing flow → architectural. |
| "The spike works, so I'll keep the script" | A spike's output is an answer. Keeping the code is a new request — classify it. |
| "It grew, but I'm nearly done — no need to re-classify" | Hidden complexity upgrades the path mid-task. Stop and say so. |
| "They approved the spike, so the real version is approved too" | Every task gets its own classification and its own approval. |
| "I'll write the plan and start Task 1 in the same message" | The spec review gate and the plan are two separate stops. |

---

## Handoff

- **Spike** ends at a reported recommendation. Nothing is kept unless a new
  request says so.
- **Bounded** goes, after approval, straight to implementation — under
  `test-first-development`. No plan document.
- **Architectural** goes to the plan, then to implementation under
  `test-first-development`, one task at a time.

In all three cases the code that follows is written test-first. Route any
number the work produces through `AGENTS.md` §2 (verify, don't self-report) and
§3 (single source of truth) before it lands anywhere a person reads.
