---
name: verification-gates
description: Router for the mechanical verification gates that run before a number is trusted - compat-check (environment), provenance-check (data source), fiducial (parameters in code), regress-check (results), canon-gate (recorded lab constants) - with one shared 0/1/2 exit contract. Use to decide which gate holds at the current moment and how to report it. Triggers - "검증 게이트", "검증 돌려", "4축", "출처 확인", "골든", "회귀 확인", "fiducial 돌려", "which gate", "verify this number".
license: MIT license
metadata:
    skill-author: Lab Researcher
---

# verification-gates

A routing layer. The tools carry the logic; this skill says which one holds when. The
gates are **not a pipeline**: each fires at a different moment, and none replaces the
judgement checks in `scientific-validation`.

## Shared contract

`0` clean · `1` violations · `2` cannot check (empty declaration, zero files, unreadable
source). **Exit 2 is never "fine".** A gate that checked nothing has not passed: report
it as BLIND, never fold 1 and 2 into one word, and never write "all gates pass" unless
every gate you ran returned 0.

## Which gate now?

| axis | question | tool (skill) | holds when |
|---|---|---|---|
| ① environment | will it install and run here | `compat-check` | once, before adopting a dependency or foreign repo |
| ② data | which dataset produced this constant | `provenance-check` | new raw data landed, or a constant was refit or pasted |
| ③ parameters | is this number allowed to be hard-coded here | `fiducial` | before every commit that carries numbers |
| ④ results | does it come out the same way twice | `regress-check` | before a number leaves the session (manuscript, report, email) |
| ⑥ lab constants | does this config contradict a recorded researcher decision | `experiment-hub/canon_gate.py FILE` | a pipetting config or Params sheet is about to be used at the bench |

Decision by moment:

1. Bringing in code you do not own → ① first. If ① exits 1 or 2, a clean ③ on that clone
   means little (③ reads the source, it does not run it). Say which exit each gave.
2. A fit finished, or a constant was pasted into params → ② (`provenance-check check provenance.toml`).
3. About to commit code that carries numbers → ③ (`fiducial check`; run it from the
   repo being checked, never from a directory that contains a `fiducial/` folder).
4. A critical number is about to leave the session (manuscript number, converged fit or
   optimizer parameters, a correctness-critical commit, a number from a remote machine)
   → ④ (`regress-check check --explain`). A moved number is explained by the ③ and ②
   output, not argued.
5. Whatever the gates cannot decide (physical plausibility, identifiability, mass
   balance, claim versus source) → `scientific-validation`. For a multi-axis or
   high-stakes claim, hand the gate output to ONE independent verifier agent instead of
   re-deriving it; a self-review is not a verification.

## Anti-shortcut rules (encoded in the tools; do not route around them)

- Freezing a golden needs a reason (`regress-check freeze --reason ...`); the history is the audit trail.
- A widened tolerance is a violation until re-frozen with a reason. Never loosen `rtol` or `atol` to reach green.
- A constant with no dataset binding is undeclared, not "probably fine". List it in `[provenance].expect` so its absence fails.
- Identity is a hash, never a file mtime.
- A number from a remote or delegated run stays provisional until ④ passes locally.

## Reporting format

One line per axis actually run: `axis | tool | exit | N violations / M blind | worst finding`.
Axes not run are listed as `not run` with the reason.

## Setup for a new project (minimal)

```
provenance.toml     # constants + source + sha256 + measured_at + instrument (+ valid_range, value_ref)
regress.toml        # goldens: actual = "<file>:<dotted.key>", rtol/atol, critical tag
regress.lock.json   # written by `regress-check freeze --reason ...`, committed
.fiducial.toml      # enable only rules that have targets, or the run is blind
```

## Related skills

- `compat-check`, `provenance-check`, `fiducial`, `regress-check` — the gates themselves.
- `experiment-hub` — owns `canon_gate.py` and the pipetting-workbook checks.
- `scientific-validation` — the judgement axes the gates leave open.
- `code-quality` — its verification gate points here for numbers.
