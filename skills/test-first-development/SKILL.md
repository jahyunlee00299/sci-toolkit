---
name: test-first-development
description: >
  Write the failing test before the implementation, watch it fail for the right
  reason, then write the minimal code that passes. Covers the red-green-refactor
  cycle, what a "test" means for numerical research code (known-answer cases,
  analytic limits, conservation checks, golden files), and the rationalizations
  that end with untested analysis code in a manuscript. Use when implementing or
  fixing any feature, script, or bug — especially a fitting routine, a data
  loader, or a unit conversion. 한국어 트리거 — 테스트 먼저, TDD, 테스트 코드
  짜줘, 실패하는 테스트, 회귀 테스트, 검증 코드, 버그 재현 테스트.
license: MIT
---

# test-first-development

**Write the test first. Watch it fail. Write the minimal code that passes.**

The core principle in one line: *if you never watched the test fail, you do not
know that it tests anything.* A test written after the code passes on the first
run — and a test that has never failed has never proved it can catch a bug.

This is the back half of the development loop. The front half — deciding what to
build and getting that agreed — is `spec-first-development`.

Adapted from the test-driven-development methodology of
[obra/superpowers](https://github.com/obra/superpowers) (MIT). See `NOTICE.md`.

---

## The iron law

```
NO IMPLEMENTATION CODE WITHOUT A FAILING TEST FIRST
```

Wrote the code before the test? Delete it and start over. Not "keep it as
reference", not "adapt it while writing the test", not "just look at it once".
Delete means delete — code you can see is code you will reproduce, and that is
testing after with extra steps.

**Exceptions, and you ask a person before taking one:** throwaway spikes
(labelled throwaway, thrown away), generated code, pure configuration files.

Thinking "skip it just this once"? That thought is the rationalization, not the
exception.

---

## Red → Green → Refactor

### RED — write one failing test

One behaviour. A name that says what should happen. Real code, not mocks.

<Good>

```python
def test_michaelis_menten_rate_at_saturating_substrate_approaches_vmax():
    rate = mm_rate(s=1000.0, vmax=2.0, km=0.5)
    assert rate == pytest.approx(2.0, rel=1e-3)
```

Clear name, tests real behaviour, one thing, and the expected value comes from
the analytic limit rather than from running the code and copying the output.
</Good>

<Bad>

```python
def test_rate():
    mock_model = Mock()
    mock_model.predict.return_value = 2.0
    assert fit(mock_model).vmax == 2.0
```

Vague name, and it asserts on the mock's behaviour rather than on the code's.
This test passes if `fit` is `return SimpleNamespace(vmax=2.0)`.
</Bad>

### Verify RED — watch it fail. Mandatory.

```bash
pytest tests/test_kinetics.py::test_michaelis_menten_rate_at_saturating_substrate_approaches_vmax -v
```

Confirm three things:

- it **fails**, rather than erroring out
- the failure message is the one you expected
- it fails because the feature is missing — not because of a typo, a bad import,
  or a missing fixture file

**Test passed immediately?** Then it is testing behaviour that already exists.
The test is wrong; fix the test.

**Test errored?** Fix the error and rerun until it fails cleanly.

### GREEN — the minimal code that passes

```python
def mm_rate(s, vmax, km):
    return vmax * s / (km + s)
```

Just enough. Do not add the substrate-inhibition term, the optional
`n_hill` parameter, or the caching layer because you can see they might be
wanted later. YAGNI. Do not refactor neighbouring code while you are here.

### Verify GREEN — watch it pass. Mandatory.

Confirm: this test passes, the other tests still pass, and the output is clean —
no new warnings, no `RuntimeWarning: overflow`, no stray prints.

**This test fails?** Fix the code, not the test. **Another test broke?** Fix it
now, not later.

### REFACTOR — only once green

Remove duplication, improve names, extract helpers. Keep the tests green. Add no
behaviour. Then write the next failing test.

---

## What counts as a test for research code

"Write a test for a curve fit" stalls people, because the honest answer to
"what should the fitted `kcat` be?" is often "that is the thing we are trying to
find out". You are not testing the biology. You are testing that the code does
what you meant. Pick whichever of these applies:

| Kind | What it pins | Example |
|---|---|---|
| **Known-answer** | The routine recovers parameters you planted | Generate data from `vmax=2.0, km=0.5` with a fixed seed, fit it, assert the fit returns those within tolerance |
| **Analytic limit** | Behaviour at a boundary you can derive by hand | `s → 0` gives a rate linear in `s`; `s → ∞` gives `vmax` |
| **Conservation** | A quantity that must not change | Total mass/carbon in equals total out; concentrations stay non-negative |
| **Invariance** | Something that must not matter | Feeding time in minutes vs seconds gives the same fitted rate constant; row order does not change the result |
| **Regression / golden** | Today's output on a fixed input | A committed 20-row input file and its expected output — this is what catches "the refactor changed the numbers" |
| **Contract** | Shape and units of what you return | The loader returns a `time_s` column, sorted, with no NaNs |
| **Failure** | It refuses bad input instead of returning nonsense | An empty file raises, not returns `NaN`; a negative concentration raises |

Two rules specific to numerical work:

- **Use `pytest.approx` with an explicit tolerance you can justify** — not `==`
  on floats, and not a tolerance loosened until the test passed. If you widened
  a tolerance, say so and say why.
- **Fix every seed.** A test that fails one run in twenty gets deleted by
  whoever is on deadline, and takes the real bug with it.

Keep the fixture files small and committed. A test that needs a 300 MB
instrument export is a test nobody will run.

---

## Testability is a design signal

If the fit function reads the CSV, does the maths, and draws the plot, you
cannot test the maths without a file and a display. That is not a testing
problem — it is the design telling you the boundaries are wrong. Split loading,
computing, and plotting (`spec-first-development` §Step 3). "Hard to test"
almost always means "hard to reuse".

| Problem | What it means |
|---|---|
| Do not know how to test it | Write the API you wish existed, then the assertion. Ask a person. |
| The test is too complicated | The design is too complicated. Simplify the interface. |
| Must mock everything | The code is too coupled. Inject the dependency. |
| The setup is enormous | Extract helpers. Still huge? Simplify the design. |

---

## Rationalizations

| Excuse | Reality |
|---|---|
| "Too simple to test" | Simple code breaks — a unit conversion is four characters and half the bugs. The test takes 30 seconds. |
| "I'll test after" | Tests written after pass immediately, which proves nothing. They test what you remembered, not what you would have discovered. You never watched it fail, so you never proved it can catch the bug. |
| "Tests-after achieve the same thing — spirit, not ritual" | Tests-after answer "what does this do?"; tests-first answer "what should this do?" The first is biased by the code already in front of you. |
| "I already checked it by hand" | Manual checking has no record of what was covered and no way to rerun it after the next change. "It looked right when I tried it" is not coverage. |
| "It's just an analysis script, not software" | It produces the numbers in the manuscript. That is the code that most needs to be right. |
| "The result looks physically reasonable" | Plausible is not correct. Plausible-and-wrong is the failure mode that survives review and reaches print. |
| "I already spent hours on it — deleting is wasteful" | Sunk cost. The time is gone either way. The real choice is rewrite with confidence vs. keep code you cannot trust. |
| "Keep it as reference, I'll write tests first" | You will adapt it. That is testing after. Delete means delete. |
| "I need to explore first" | Fine — explore, then throw the exploration away and start with TDD. |
| "TDD will slow me down" | The alternative is debugging a wrong number after it is in a figure. That is the slow path. |
| "The existing code has no tests either" | You are improving it. Add tests for what you touch. |

---

## Red flags — stop and start over

Code before test · test written after implementation · test passed on its first
run · you cannot explain why it failed · "I'll add tests later" · "just this
once" · "I already checked it manually" · "it's about spirit not ritual" ·
"keep it as reference" · "deleting hours of work is wasteful" · "TDD is dogma,
I'm being pragmatic" · "this case is different because…"

Every one of these means the same thing: delete the code, start with the test.

---

## Bug fixes

Never fix a bug without a test. Reproduce it as a failing test **first** — that
test is what proves the fix works and what stops it coming back.

```python
def test_blank_subtraction_is_not_applied_twice():
    # 2026-08-21: pipeline subtracted the blank in both the loader and the
    # fitter, so every reported rate was low by one blank.
    df = load_plate("tests/data/plate_with_blank.csv")
    rate = fit_initial_rate(df)
    assert rate == pytest.approx(0.42, rel=1e-3)
```

---

## Before you call it done

- [ ] Every new function has a test
- [ ] You watched each test fail before implementing
- [ ] Each failed for the expected reason (feature missing, not a typo)
- [ ] You wrote the minimal code to pass each one
- [ ] All tests pass, and the output is clean
- [ ] Tests exercise real code; mocks only where unavoidable
- [ ] Edge cases and error paths are covered
- [ ] Every tolerance and seed is explicit
- [ ] No test was weakened to make it pass — or if one was, you said so and
      justified it

Cannot tick all of them? You did not do TDD. Start over.

A passing suite is still not proof that a *number* is right — that is a separate
gate. Any value heading for a figure, report, or manuscript goes through
`AGENTS.md` §2 (independently re-derive, never trust the self-report) and §3
(single source of truth), and for physical plausibility through
`scientific-validation`.
