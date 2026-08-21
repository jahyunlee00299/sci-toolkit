---
name: debugging-loop
description: >
  Discipline for a bug that did not yield to the first read of the code. Build a
  tight, red-capable feedback loop BEFORE forming any theory, minimise the repro,
  rank falsifiable hypotheses, instrument one variable at a time, and close with
  a regression test plus tagged-log cleanup. Use when a script crashes, returns
  a wrong number, silently produces nothing, or got slower — and the cause is not
  obvious from one look. 한국어 트리거 — 왜 안 되지, 버그 잡아줘, 디버깅, 재현
  안 돼, 값이 이상해, 결과가 틀려, 갑자기 느려졌어, 원인 찾아줘.
license: MIT
---

# Debugging Loop

The failure this skill prevents is **theorising before measuring**. An agent
reads the traceback, forms a plausible story, edits the file, re-runs, sees
different output, and reports the bug fixed — with no evidence the change caused
the improvement, and often with a second bug introduced under the first.

The discipline is a loop first, a theory second. If you have a command that goes
red on *this* bug and green when it is gone, the cause is a matter of time.
Without one, no amount of reading code will settle it.

## Phase 1 — Build the feedback loop (this is the skill)

Everything after this phase is mechanical. Spend disproportionate effort here.

Ways to construct a loop, in roughly the order to try them:

1. **A failing test** at whatever seam reaches the bug.
2. **A CLI invocation** on a fixture input, diffing stdout against a known-good
   result.
3. **A direct call** — a few lines that import the function and assert on its
   return for one recorded input.
4. **A replayed capture.** Save the real input that triggered it (the raw data
   row, the request payload, the parameter set) to disk and push it through the
   code path in isolation.
5. **A throwaway harness.** The smallest subset of the pipeline that still
   reaches the bug, driven by one function call.
6. **A randomised loop.** For "sometimes wrong", run many inputs and count the
   failure mode rather than hunting one instance.
7. **A bisection harness.** If it worked at a known earlier state (a commit, an
   older data file, a previous version), automate "set state X → check" so the
   search is mechanical.
8. **A differential loop.** Same input through two versions or two configs, then
   diff the outputs.

### Completion criterion

Phase 1 is done when you can name **one command** that you have **already run at
least once** (show the invocation and its output), and that is:

- **Red-capable** — it drives the real code path and asserts the *symptom the
  user described*, so it can go red now and green once fixed. "Runs without
  erroring" is not a signal.
- **Deterministic** — same verdict every run. Pin the seed, freeze the clock,
  fix the input file, isolate the working directory.
- **Fast** — seconds. A 30-second flaky loop is barely better than none.
- **Runnable unattended** — you can invoke it yourself, without a human clicking.

If you catch yourself reading code to build a theory before this command exists,
**stop**. Jumping to a hypothesis is the exact failure this skill prevents.

If you genuinely cannot build a loop, say so explicitly, list what you tried, and
ask for what would unblock it (access to the environment that reproduces it, a
saved copy of the failing input, permission to add temporary instrumentation).
Do not proceed to hypothesise without one.

### Non-deterministic bugs

The goal is not a clean repro but a **higher reproduction rate**. Loop the
trigger many times, add load, narrow the timing window. A bug that appears half
the time is debuggable; one in a hundred is not — raise the rate until it is.

## Phase 2 — Reproduce, then minimise

Run the loop and watch it go red. Confirm it produces **the failure the user
described**, not a different one that happens to live nearby. Wrong bug, wrong
fix.

Then shrink the repro to the smallest scenario that still goes red: cut inputs,
callers, configuration, and data **one at a time**, re-running after each cut.
Keep only what is load-bearing.

This is not tidiness. Every element you remove is one fewer suspect in Phase 3,
and what survives becomes the regression test in Phase 5.

Done when removing any remaining element makes the loop go green.

## Phase 3 — Hypothesise

Write **3–5 ranked hypotheses before testing any of them.** Generating one at a
time anchors you on the first plausible idea, which is how a whole afternoon
goes into the wrong subsystem.

Each hypothesis must be **falsifiable** — state the prediction it makes:

> If <X> is the cause, then <changing Y> makes the bug disappear.

A hypothesis with no prediction is a vibe. Sharpen it or discard it.

Show the ranked list to the user before testing. They often re-rank it instantly
from context you do not have ("that file was regenerated yesterday"). Do not
block on the answer if they are away.

## Phase 4 — Instrument

Every probe maps to a specific prediction from Phase 3. **Change one variable at
a time**, or the result tells you nothing about either.

Preference order: an interactive inspection (debugger, REPL, notebook cell) beats
targeted prints at the boundary that separates two hypotheses, which beats
logging everything and grepping — that last one is not instrumentation, it is
hoping.

**Tag every debug print** with a unique marker, e.g. `[DBG-a4f2]`. Cleanup then
becomes one grep. Untagged prints survive into the committed file; tagged ones
die on schedule.

**If it is a slowdown rather than a wrong answer**, prints are usually the wrong
tool. Establish a baseline measurement first (time the stages, profile, count the
calls), then bisect on the measurement. Measure first, fix second.

## Phase 5 — Fix, with a regression test

Write the regression test **before** the fix — but only if a **correct seam**
exists for it. A correct seam exercises the real bug pattern as it occurs at the
call site. A test at a seam too shallow to reach the pattern (a single-input test
for a bug that needs two rows to interact) gives false confidence, which is worse
than no test.

**If no correct seam exists, that is itself the finding.** Say so. The structure
of the code is preventing the bug from being pinned down.

Where a seam exists:

1. Turn the minimised repro into a failing test there.
2. Watch it fail.
3. Apply the fix.
4. Watch it pass.
5. Re-run the Phase 1 loop against the **original, un-minimised** scenario.

Step 5 is not optional. A fix that satisfies the minimised case and not the
original means the minimisation cut something load-bearing.

## Phase 6 — Cleanup before declaring done

- [ ] The original repro no longer reproduces (re-run the Phase 1 loop, quote it)
- [ ] The regression test passes — or the absence of a correct seam is written down
- [ ] All `[DBG-...]` instrumentation removed (grep the tag)
- [ ] Throwaway harnesses deleted or moved to a scratch location
- [ ] The hypothesis that turned out correct is stated in the commit message

## Numbers, data, and this loop

When the symptom is a **wrong number** rather than a crash, the loop's assertion
must come from an independent source of truth — a hand-worked example, a value
from the instrument, a published figure. An assertion that recomputes the
expected value the way the code computes it passes by construction and can never
go red — the tautological-assertion trap, and the dominant failure mode in
scientific test suites.

Once fixed, any number the bug touched is **provisional** until re-derived from
its canonical source — see AGENTS.md §3 and the `scientific-validation` skill.

## Redaction

This skill has you show commands and their output. Redact secrets before
displaying anything: write `<REDACTED>` in place of keys, tokens, and passwords,
and build loops against environment variables so the credential stays out of what
you print. If the redacted output is not enough to diagnose the bug, say so and
ask.

## Anti-patterns

- Editing code before a red-capable command exists.
- A loop that asserts "did not crash" instead of the user's actual symptom.
- Testing several hypotheses at once, then not knowing which change mattered.
- Declaring a fix because output changed, without re-running the original repro.
- Leaving untagged debug prints in the file.
- Minimising a repro and never re-checking the full original scenario.
