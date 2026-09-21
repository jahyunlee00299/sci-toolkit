---
name: paramguard
description: Check whether a number that claims to be measured is allowed to be where it is. Three static rules — (1) a parameter declared to be fitted/measured must not appear as a hard-coded literal or be fetched with a silent default; (2) a config file name carrying a version token must not contradict the versions its own fields declare; (3) a declared parameter must have some test asserting something about it, so a parameter that is plumbed in but gated by nobody is caught before it is trusted. Use before trusting a fit, when a constant appears in a script, when config lineage looks off, or as a pre-commit gate. 한국어 트리거 — "이 상수 출처가 뭐지", "하드코딩된 파라미터 찾아", "파일명이랑 내용이 안 맞아", "버전 꼬인 것 같아", "silent fallback 검사", "아무도 검사 안 하는 파라미터".
---

# paramguard

Asks one question that dependency checkers, dataframe validators and regression
baselines all leave open: **is this number allowed to be here at all?**

## Install

> **Status (260921): not published yet.** `paramguard` is not on PyPI and the
> GitHub repo below is not public, so the commands in this section do not work
> for anyone but the author yet. Install from a local clone until it ships:
>
> ```bash
> pip install /path/to/paramguard
> ```

Once published:

```bash
pip install paramguard
```

Stdlib only, no dependencies, Python ≥3.10. This skill carries **no copy of the
source** — it calls the installed package. A second copy inside a skill folder
has no `pyproject`, so it cannot be imported without `sys.path` surgery, and the
two drift apart with nothing to detect it.

## The three rules

### rule ① — measured keys must not be hard-coded or silently defaulted

```bash
paramguard literals --keys eta,k_transfer,kcat_enzyme scripts/
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
paramguard names scripts/_refactor/configs/
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
paramguard coverage --spec .claude/params_spec.yaml -- tests/
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

## Exit codes — an empty check is an error, not a pass

```
0  clean
1  violations found
2  the check could not be performed
```

Exit `2` covers an empty `--keys`, zero matched files, and unparseable source.
**Do not treat 2 as success.** This package exists because a scanner whose path
globs had gone stale printed `OK — no violations across 0 file(s)` and exited 0
for long enough that nobody questioned it.

When scripting it, branch on all three:

```bash
paramguard names configs/; rc=$?
case $rc in
  0) echo "clean" ;;
  1) echo "violations — read them" ;;
  2) echo "COULD NOT CHECK — do not record this as clean" ;;
esac
```

## As a pre-commit gate

```yaml
- repo: https://github.com/jahyunlee00299/paramguard
  rev: v0.1.0
  hooks:
    - id: paramguard-names
    - id: paramguard-literals
      args: [--keys, "eta,k_transfer,enzyme_activity_scale"]
```

> That repo is **not public yet** (see Install above), so this block does not
> resolve for anyone else. Until it ships, wire it through a local hook script
> as this lab does, below.

Where this is in use, the rules are wired via `.git/hooks/pre-commit.local`,
which an existing strict-params hook chains to before its own scan. Only **staged** files are checked, so
pre-existing violations do not block unrelated work — a guard that fails on day
one for reasons the committer did not cause gets bypassed permanently.

Bypass: `PARAMGUARD_SKIP=1 git commit ...`

## What it found here

Running rule ① over 1,522 files with 49 declared keys surfaced
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
