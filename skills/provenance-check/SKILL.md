---
name: provenance-check
description: Check that a derived constant (a fitted kcat, a calibration slope, a pasted parameter) really came from the dataset it claims, by source file, sha256, measurement date, instrument, valid range and the value the code actually uses. Use when a fit finished, new raw data landed, or a constant was pasted into a params file. Triggers - "이 상수 어디서 나왔어", "출처 확인", "provenance", "which dataset produced this constant".
license: MIT license
metadata:
    skill-author: Lab Researcher
---

# provenance-check

Gate ② of the verification family. It asks one question: **which dataset produced
this constant, and is the value in use still that value?** Every number in a model
can be plausible and still be unsourced; this tool refuses the claim when the source
file, hash, date, instrument or range does not hold.

## Install

```bash
pip install "git+https://github.com/jahyunlee00299/provenance-check"
```

Not on PyPI. Standard library only, Python >= 3.11, command `provenance-check`.
This skill carries no copy of the source; it calls the installed package.

## Declare, then check

`provenance.toml` (paths relative to the file):

```toml
[provenance]
expect = ["k_17", "kla_scale"]        # keys that MUST be declared

[constants.k_17]
value = 0.1077
source = "rawdata/run_0502.csv"       # required
sha256 = "<hex>"                      # provenance-check hash <file>
measured_at = "2026-05-02"            # required ISO date, not in the future
instrument = "HPLC-RID"               # required
valid_range = [0.05, 0.5]             # optional
value_ref = "params/model.json:kinetics.k_17"   # where the value is USED
```

```bash
provenance-check check provenance.toml            # --format json for tooling
provenance-check hash rawdata/run_0502.csv
provenance-check init --params params/model.json --source rawdata/run_0502.csv --out draft.toml
```

`init` drafts a declaration from a params file with `measured_at = "TODO"`. The
untouched draft **fails** `check` on purpose; a person fills in the date and the
instrument.

## Exit codes (shared by the whole family)

`0` clean · `1` violations · `2` cannot check (empty declaration, empty `expect`,
`value_ref` pointing at a key that is gone). **Exit 2 is never a pass.** Report it as
BLIND and say what could not be read.

## Rules worth knowing

- `undeclared`: a key in `expect` with no `[constants.<key>]` block is a violation.
  Put every fitted constant in `expect` so its absence fails.
- `value-drift`: the value at `value_ref` differs from the declared value, so the
  constant in use is not the constant that was sourced.
- `hash-mismatch` is certain; `hash-unpinned` needs a human decision. Identity is the
  hash, never the file mtime (synced folders make mtime meaningless).
- It does **not** check whether raw data is tracked in git; only that the file exists
  and matches its hash.

## Related skills

- `verification-gates` — which gate to run at which moment.
- `fiducial` — gate ③ reads the code (is a measured key hard-coded); this gate reads the data binding.
- `regress-check` — gate ④; run after this one when a number is about to leave the session.
- `scientific-validation` — plausibility and identifiability, which this tool does not judge.
