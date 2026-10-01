---
name: fiducial
description: Check whether a number that claims to be measured is allowed to be where it is. Five static rules — (1) a declared fitted/measured parameter must not be a hard-coded literal or a silent default; (2) a config file name carrying a version token must not contradict the versions its own fields declare; (3) a declared parameter must have some test asserting something about it; (4) a document repeating a number from another document must not contradict it; (5) an index that registers artefacts must not point at files that are gone. Use before trusting a fit, when a constant appears in a script, when config lineage looks off, when a design note repeats numbers another document owns, or as a pre-commit gate. 한국어 트리거 — "이 상수 출처가 뭐지", "하드코딩된 파라미터 찾아", "파일명이랑 내용이 안 맞아", "버전 꼬인 것 같아", "silent fallback 검사", "아무도 검사 안 하는 파라미터", "문서끼리 값이 다르다", "PFD 수치가 SSOT랑 안 맞아", "어느 문서가 원본이야".
---

# fiducial

*Formerly `paramguard` (renamed 2026-09-30; the old repo is deleted).*

Asks one question that dependency checkers, dataframe validators and regression
baselines all leave open: **is this number allowed to be here at all?**

## Install

```bash
pip install fiducial-check
```

The PyPI distribution is `fiducial-check`; the command and import name are
`fiducial` (`python -m fiducial` also works from a checkout). Source:
<https://github.com/jahyunlee00299/fiducial>. Stdlib only, no dependencies,
Python >=3.10. This skill carries **no copy of the source** — it calls the
installed package. A second copy inside a skill folder has no `pyproject`, so it
cannot be imported without `sys.path` surgery, and the two drift apart with
nothing to detect it.

## The five rules

### rule ① — measured keys must not be hard-coded or silently defaulted

```bash
fiducial literals --keys eta,k_transfer,kcat_enzyme scripts/
```

Flags two shapes, for keys **you declare** as measured:

```python
eta = params.get("eta", 0.87)   # missing key -> a wrong fit, not a failure
model.k_transfer = 0.412        # measured where? by whom? against what?
```

`--keys` is required. A checker that guessed which numbers were physical would
be wrong constantly and switched off within a day. Pull the list from the
project's own declaration — in this lab that is `learnable_keys` in
`<repo>/.claude/params_spec.yaml`.

`--include-neutral` also reports defaults of `0.0`/`1.0`. They are excluded by
default because on the reference codebase they were 575 of 705 hits (82%) —
`setdefault("vmax_futile_nadph", 0.0)` is a term switched off, not a fabricated
measurement — and reporting them buried the 115 that mattered.

### rule ② — a file name must not contradict its own contents

```bash
fiducial names scripts/_refactor/configs/
```

```
opt_model_v15b_5d.yaml: name says v15b but contents say v16.
```

`--mode set` (default) also catches partial-overlap lies: a file named `v8_v3`
whose `fit_json` is `v8_v4`. `--mode strict` requires no shared version at all
and is quieter. Comments, prose fields (`description:`, `note:`) and
path-valued references (`extends:`, `ratio_source:`) are excluded — those
describe or point elsewhere, they do not declare what the file *is*.

### rule ③ — a declared parameter must be gated by some test

```bash
fiducial coverage --spec .claude/params_spec.yaml -- tests/
```

```
enzyme_activity_scale: declared as a fitted/measured parameter, but it does not
appear anywhere in the test tree. Nothing checks it, and nothing will notice
when it changes.
```

Rules ① and ② ask whether a number is *shaped* wrongly. This one catches the
parameter that is plumbed in correctly and tested by nobody — the suite stays
green because the assertion that would fail was never written. This is the
primary rule: preventing an ungated parameter, not auditing after the fact.

Four levels: `asserted` / `pinned` (frozen in a golden JSON the tests compare
at runtime — pass those files with `--data`) / `mentioned` / `absent`. Only
`absent` is wired to block; `--baseline` freezes pre-existing gaps so the gate
never fails on day one for something the committer did not cause.

**🔴 What it does not tell you.** A `mentioned-only` verdict means *"no gate
found by the patterns implemented here"*, not "no gate" — the classifier was
rewritten four times and each round found another mechanism that leaves no
parameter name in the source. The error runs the other way too: a key named
inside an `assert` is not evidence the assert can *fail* on it. In the corpus
this was built on, three parameters are set by a test asserting `rate == 0` at
a manufactured equilibrium where the numerator is structurally zero and those
three appear only in the denominator — the assertion holds whatever they are.
Deciding whether an assertion is actually sensitive to a parameter is mutation
testing's question, and it answers it by running the suite. This rule does not
attempt that and must not be read as having done so.

### rule ④ — a document must not contradict the SSOT document it declares

```bash
fiducial docs docs/
```

```
docs/process_draft.md:161: pH asserted as 5.0 but docs/PROCESS_CONDITIONS.md carries 10.0
    | 중화 단계 | pH 5.0 |
```

Rules ①–③ all watch code and config. This one watches the layer where the same
drift kept landing unwatched: the PFD, the design note, the spec summary that
quietly carries last month's pH. It exists because a project with four SSOT
gates already in CI still shipped that defect three times — every one of those
gates compares a document against a **canonical JSON**, so two documents that
disagree with each other are structurally invisible to all of them.

The comparison is **declared, not inferred**. A derived document names its
upstream in YAML front matter and lists what it is repeating rather than
originating:

```yaml
---
ssot:
  source: docs/PROCESS_CONDITIONS.md
  repeats:
    pH: 10
    반응 온도 as 운전 온도: 60        # the two documents use different words
---
```

Only declared quantities are compared. Scanning every document for every number
instead was tried on a 54-document research corpus and drowns — the same figure
legitimately appears as prior art (`CN101904484A uses pH 5.0`), as a retracted
value, and as a target distinct from an operating point. Citations, struck-out
text, past-tense sentences and change arrows are therefore read as history, not
as assertions; ranges (`pH 4~8`) are skipped, because a band is not an operating
point.

**🔴 What it does not tell you.** It checks that a copy matches its original,
never that the original is right, and it reads one hop only. Two shapes are
invisible: a column-oriented table (label in the header row, value several rows
below) and a quantity stated without naming it. Both are cases where the rule
stays *silent*, so "no findings" is not proof — which is why a quantity whose
label is missing from either side is reported as a **gap** rather than counted
clean, and `--strict-gaps` makes gaps block. A declaration that quietly checks
nothing is this rule's real failure mode.

### rule ⑤ — an index must not name artefacts that are gone

```bash
fiducial pointers models/params/param_registry.json
```

An index (`.json`, `.yaml`, `.yml`) that registers artefacts must not carry a
`file` pointer to a missing path, or a `parent_id` naming no other entry. The
report separates *relocatable* (exactly one candidate: the file moved),
*gone* (no candidate) and *ambiguous* (several candidates: no proposal is made,
because picking one would point the index at the wrong artefact).

### Optional: conflicts, project config, machine-readable output

- `fiducial literals --keys 'k_*,*titer*' --conflicts src/` also reports one
  declared key bound to two different values across code and tests. A finding
  there is always `needs_review`; it never carries a fix.
- A project can declare its rules once under `[tool.fiducial]` in
  `pyproject.toml` (or a standalone `.fiducial.toml`) and run `fiducial check`.
  `check` combines verdicts pessimistically: any rule that could not run makes
  the whole command exit `2`.
- Every rule takes `--format=json`; each finding carries a `confidence` and an
  optional `fix` (`applicability`, `apply`) so an agent knows whether it may
  repair the finding alone. Read the upstream README for the exact schema:
  <https://github.com/jahyunlee00299/fiducial#when-the-caller-is-an-agent>.

## Exit codes — an empty check is an error, not a pass

```
0  clean
1  violations found
2  the check could not be performed
```

Exit `2` covers an empty `--keys`, zero matched files, unparseable source, and
— for rule ④ — a corpus where no document declares an SSOT at all.
**Do not treat 2 as success.** This package exists because a scanner whose path
globs had gone stale printed `OK — no violations across 0 file(s)` and exited 0
for long enough that nobody questioned it.

When scripting it, branch on all three:

```bash
fiducial names configs/; rc=$?
case $rc in
  0) echo "clean" ;;
  1) echo "violations — read them" ;;
  2) echo "COULD NOT CHECK — do not record this as clean" ;;
esac
```

## As a pre-commit gate

```yaml
- repo: https://github.com/jahyunlee00299/fiducial
  rev: v0.1.0
  hooks:
    - id: fiducial-names
    - id: fiducial-literals
      args: [--keys, "eta,k_transfer,enzyme_activity_scale"]
```

The hooks use `language: python`, so pre-commit builds an isolated environment
from the upstream `pyproject` and does not depend on whichever interpreter is on
`PATH`. Pre-existing violations should not block unrelated work: a guard that
fails on day one for reasons the committer did not cause gets bypassed
permanently (for rule ③, freeze the gaps with `--baseline`).

## What it found here

Running rule ① (as `paramguard`, the tool's earlier name) over 1,522 files with 49 declared keys surfaced
`model.k_transfer = 0.412` hard-coded in two scripts while the canonical fit
carries `0.5074` — a 53% discrepancy on a fitted parameter, in code that had
been read many times.

Rule ② over 231 configs: 127 comparable, 2 violations under `strict` (1.6%),
3 under `set` (2.4%).

**Quote the denominator.** This is a real defect class, not a widespread one,
and those are one corpus's figures.

## Not this

- versioning data → DVC
- validating dataframes → pandera
- pinning regression baselines → pytest-regressions
- checking whether a package installs → `compat-check` (sibling skill)
