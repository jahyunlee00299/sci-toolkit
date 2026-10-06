---
name: regress-check
description: Freeze the critical numbers a model produced and fail when one moves, when a tolerance is loosened to get green, or when a freeze has no recorded reason. Use before a number leaves the session (manuscript, report, email), after a re-run, and after a converged fit. Triggers - "골든", "회귀 확인", "숫자가 바뀌었나", "regression check", "freeze results".
license: MIT license
metadata:
    skill-author: Lab Researcher
---

# regress-check

Gate ④ of the verification family. It does not run your model. It compares numbers
your model already wrote to a results file (`json` or `toml`) against a frozen copy and
tells you when they differ by more than you said they may.

## Install

```bash
pip install "git+https://github.com/jahyunlee00299/regress-check"
```

Not on PyPI. Standard library only, Python >= 3.11, command `regress-check`.

## Declare, freeze, check

`regress.toml` next to the results file:

```toml
[regress]
explain = ["fiducial check", "provenance-check check provenance.toml"]

[golden.mpsp]
actual = "out/results.json:economics.mpsp"   # <file>:<dotted.key>
rtol = 0.005
critical = "manuscript"
```

```bash
regress-check freeze --reason "initial freeze"     # writes regress.lock.json, commit it
regress-check check --explain                      # --explain runs the commands above on failure only
regress-check history mpsp
```

## The shortcut it refuses

A red check is fastest to green by raising `rtol` or re-recording the expected value.
Here both are violations:

- `freeze` without a non-empty `--reason` exits 2 and writes nothing. The lock keeps the
  old value, the new value, both tolerances and the reason.
- Widening a tolerance without a re-freeze is `tolerance-widened`. Never loosen `rtol` or
  `atol` to reach green; find out why the number moved, using the `--explain` output of
  the sibling gates.

## Exit codes

`0` every frozen number held · `1` a number moved, a tolerance widened, or an orphan lock
entry · `2` cannot check (registry missing, zero goldens, a golden never frozen, results
file or key missing, a non-number value). **Exit 2 is never a pass.** A run with one moved
number and one missing file exits 1.

## Limits

It cannot say whether a frozen number was *right*, only that it did not change and that
changing it left a reason behind. For whole-file snapshots use pytest-regressions or syrupy.

## Related skills

- `verification-gates` — which gate to run at which moment.
- `provenance-check` and `fiducial` — the cause when a number moves.
- `scientific-validation` — plausibility, identifiability, mass balance.
