---
name: analysis-code-testing
description: Write pytest tests for analysis and processing code — the scripts that parse raw data, compute a rate or a yield, fit a curve, or produce a number that ends up in a figure or a manuscript. Covers fixtures, parameterization, float comparison with tolerances, golden-file regression against a frozen expected result, and the seeding/isolation rules that make a stochastic fit reproducible. Use when adding tests to an analysis script, when a computation changed and you need to know what else moved, or when a result cannot be reproduced. For design/SOLID review use code-quality; for whether a converged number is physically sensible use scientific-validation.
license: MIT
metadata:
  skill-author: sci-toolkit (adapted from wshobson/agents, MIT)
  upstream: https://github.com/wshobson/agents — plugins/python-development/skills/python-testing-patterns
---

# Analysis Code Testing

A test on analysis code answers a question no review can: **if I change this
script, does the number it produced last week still come out?** That is the
failure this skill targets — not crashes, but a silent change in a computed
value that nobody notices until it is in a figure.

Upstream general-purpose testing guidance is written for web services (retries,
HTTP mocks, token expiry). Those patterns are omitted here. What follows is the
subset that applies to code whose output is a number.

## When to use this skill

- Adding tests to a parser, a rate/yield calculation, a fitting routine, a
  normalization step, or any script feeding `publication-figures`
- A computation changed and you need to know what else moved (regression)
- A result cannot be reproduced from the same inputs
- Before a script becomes the canonical source for a reported number (§3 SSOT
  in `AGENTS.md`) — a canonical script with no test is a number with no anchor

Do **not** use this skill to decide whether a converged parameter is
*physically* plausible — that is `scientific-validation`. A test proves the
code still computes what it computed before; it says nothing about whether
that was ever right.

## The three test kinds, in the order worth writing them

### 1. Known-answer test — the anchor

Pick an input whose correct output you can derive by hand or from a textbook
case, and pin it. This is the only test that can tell you the code was ever
right; everything else only tells you it has not changed.

```python
def test_initial_rate_matches_hand_calculation():
    """Linear phase: 0.20 mM consumed over 4.0 min -> 0.050 mM/min."""
    t = [0.0, 1.0, 2.0, 3.0, 4.0]
    c = [1.00, 0.95, 0.90, 0.85, 0.80]
    assert initial_rate(t, c) == pytest.approx(0.050, rel=1e-9)
```

### 2. Property test — what must hold for every input

Cheaper than enumerating cases, and it catches whole classes of error:
conservation, monotonicity, bounds, unit scaling.

```python
@pytest.mark.parametrize("scale", [0.1, 1.0, 10.0, 1000.0])
def test_yield_is_scale_invariant(scale):
    """Yield is a ratio — multiplying every concentration must not change it."""
    base = compute_yield(substrate=10.0, product=7.5)
    assert compute_yield(substrate=10.0 * scale,
                         product=7.5 * scale) == pytest.approx(base)

def test_mass_balance_closes():
    out = run_model(substrate0=10.0)
    total = out["product"] + out["byproduct"] + out["residual_substrate"]
    assert total == pytest.approx(10.0, rel=1e-6)
```

### 3. Golden-file regression — the change detector

Freeze a known-good output, then assert against it. When it fails, the
question is not "is the test broken" but **"did I mean to change this number?"**

```python
def test_pipeline_output_matches_golden(tmp_path):
    result = run_pipeline("tests/data/run_a.csv")
    golden = json.loads(Path("tests/golden/run_a.json").read_text())
    for key, expected in golden.items():
        assert result[key] == pytest.approx(expected, rel=1e-6), (
            f"{key} changed: {golden[key]} -> {result[key]}. "
            "If intended, regenerate the golden file and say so in the commit."
        )
```

Regenerating a golden file to make a red test go green, without stating what
changed and why, defeats the entire mechanism. Treat the regeneration as the
thing under review, not the test.

## Floating point: never assert equality

`0.1 + 0.2 != 0.3`. Every numeric assertion needs a tolerance, and the
tolerance is a claim about the precision you are entitled to.

```python
assert value == pytest.approx(expected, rel=1e-6)   # 6 significant figures
assert value == pytest.approx(expected, abs=1e-9)   # near zero: use abs
assert arr == pytest.approx(expected_arr, rel=1e-6) # numpy arrays too
```

Rules of thumb:
- Analytical result, closed form → `rel=1e-9`
- Numerical integration / ODE solve → `rel=1e-6`, and pin the solver tolerance
- Fitted parameter from noisy data → `rel=1e-3` or looser; a tighter bound
  tests the optimizer's tie-breaking, not your model
- Comparing to zero → `abs=`, never `rel=` (relative tolerance to zero is
  meaningless and the assertion becomes unfalsifiable)

## Reproducibility: seed, and prove the seed works

Anything stochastic — bootstrap, cross-validation split, differential
evolution, MCMC init, Bayesian optimization — is untestable until seeded.
Pass the seed explicitly; do not rely on a global `np.random.seed()` that
another import can reset.

```python
def test_bootstrap_ci_is_reproducible():
    rng_a = np.random.default_rng(20260821)
    rng_b = np.random.default_rng(20260821)
    assert bootstrap_ci(data, rng=rng_a) == pytest.approx(bootstrap_ci(data, rng=rng_b))

def test_fit_converges_from_multiple_starts():
    """A fit that only converges from one start point is not converged."""
    results = [fit(data, seed=s) for s in (1, 2, 3, 4, 5)]
    kcat = [r["kcat"] for r in results]
    assert np.std(kcat) / np.mean(kcat) < 0.01, f"start-dependent: {kcat}"
```

That second test is the one that finds real problems. A fit reported from a
single starting point has not been shown to have found the optimum.

## Fixtures: small, in-repo, committed

Test data belongs in the repository next to the tests, not in a cloud-synced
folder or an absolute path on one machine.

```python
@pytest.fixture
def kinetic_run():
    """Six-point progress curve — trimmed real data, committed at tests/data/."""
    return pd.read_csv(Path(__file__).parent / "data" / "kinetic_min.csv")

@pytest.fixture
def tmp_output(tmp_path):
    """pytest's tmp_path — never write test output next to the source data."""
    return tmp_path / "out.csv"
```

Trim a real file down to the smallest case that still exercises the code
(a few rows, one replicate). A synthetic fixture that never saw the
instrument's actual output format will not catch a parser bug.

## Edge cases worth a test in this domain

| Case | Why it bites |
|---|---|
| Empty file / zero rows | Parsers return an empty frame and downstream silently reports 0 |
| Single data point | Slope, SD, and CI are undefined — must raise, not return `nan` |
| All-identical values | Zero variance → division by zero in normalization |
| NaN in the middle | `mean()` skips it; `np.trapz` propagates it — decide which you meant |
| Negative concentration | Below detection limit clipped to 0, or a baseline error |
| Duplicate timepoints | Averaged, or the last one wins? Both are defensible; pin one |
| Non-monotonic time | Sorted silently, or an error? |
| Unit mismatch (mM vs µM) | The classic 1000× error — test the conversion explicitly |

## Running

```bash
pytest                             # everything
pytest tests/test_kinetics.py -v   # one file, verbose
pytest -k "yield" -v               # by name
pytest -x                          # stop at first failure
pytest --lf                        # rerun only last failures
pytest -m "not slow"               # skip long fits (mark them @pytest.mark.slow)
pytest --cov=analysis --cov-report=term-missing
```

Coverage measures which lines ran, not whether the numbers were right. A
module at 100 % coverage with no known-answer test is untested in the sense
that matters here.

## Gate

Before treating an analysis script as canonical:

1. `pytest` exits 0 — quote the summary line, don't paraphrase it
2. At least one **known-answer** test exists for its central computation
3. Every numeric assertion carries an explicit tolerance
4. Any stochastic step takes an explicit seed
5. If a golden file changed in this diff, the commit message says what number
   moved and why

Never weaken a tolerance, delete an assertion, or regenerate a golden file to
turn a test green. If a check fails, the artifact is what needs fixing
(`AGENTS.md` §0, rule 2).
