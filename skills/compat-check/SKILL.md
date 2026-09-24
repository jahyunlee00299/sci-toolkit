---
name: compat-check
description: Check whether a GitHub repo or PyPI package would install cleanly in the current environment, before installing it. Runs a real dry-run install (uv preferred, pip fallback) in a disposable venv and reports the resolver's own pass/fail, not a static metadata guess. Use before adding a new dependency, before `conda-env-manager` installs a missing import, or when a package might conflict with what's already in the environment. 한국어 트리거 — "이거 설치해도 되나", "설치 전에 충돌 확인", "호환성 체크", "의존성 충돌 미리 확인".
license: MIT license
metadata:
    skill-author: Lab Researcher
---

# compat-check

## Overview

Answers one question before you run `pip install` / `conda install` for real:
**will this actually resolve in this environment, or will it fail partway
through?** It does this by running a genuine dry-run install in a throwaway
virtual environment and reporting the resolver's own error, rather than
parsing package metadata and guessing.

Two things this catches that eyeballing `requirements.txt` does not:

- Both `uv` and `pip` are fail-fast resolvers — a single dry-run call reports
  only the *first* unsatisfiable requirement. If two unrelated packages in
  the same source are both broken, one hides behind the other. `compat-check`
  drops each failure and retries until every one surfaces.
- It works from the **real target** (a GitHub repo's `pyproject.toml`/
  `requirements.txt`/`setup.cfg`, or a PyPI package's `info.requires_dist`),
  not from a hand-copied list that may already be stale.

## When to Use

- Before adding a new dependency to a project, especially one with a history
  of conflicting with NumPy/SciPy-stack pinned versions
- Before installing something from a GitHub URL you haven't vetted
- As a pre-check inside `conda-env-manager`'s workflow (see below) — run it
  on the missing packages `scan_imports.py` reports, **before** installing
  them for real
- When two packages might have conflicting version constraints and you want
  the conflict surfaced before it happens mid-install

## Usage

The code is not in this folder — it ships as the `compat-check` package on
PyPI, so the skill has to be installed once into the environment you want it
to probe:

```bash
python -m pip install compat-check
```

Then either entry point works:

```bash
compat-check <github-url-or-pypi-package-name> [--python 3.11] [--no-cache] [--tree]
python -m compat_check.cli <github-url-or-pypi-package-name>   # same thing
```

```
$ compat-check https://github.com/pallets/flask
compat-check: https://github.com/pallets/flask
backend: uv
requirements checked: blinker>=1.9.0, click>=8.1.3, itsdangerous>=2.2.0, jinja2>=3.1.2, markupsafe>=2.1.1, werkzeug>=3.1.0

OK — 6 package(s) would install cleanly:
  + blinker==1.9.0
  + click==8.5.0
  ...
```

```
$ compat-check some-package-with-a-real-conflict
PROBLEMS FOUND — 1 package(s) cannot be resolved:

  [numpy]
      x No solution found when resolving dependencies:
      -> Because you require numpy>=2.0 and numpy<1.20, we can conclude that your
          requirements are unsatisfiable.
```

Exit codes: `0` clean, `1` conflicts found, `2` source could not be resolved
at all (bad URL, nonexistent package).

`--tree` shows the full dependency tree (requires `uv`; no pip-backend
equivalent — `uv tree` has no substitute in plain pip):

```
$ compat-check https://github.com/pallets/flask --tree
...
https://github.com/pallets/flask
├── blinker v1.9.0
├── click v8.5.0
├── jinja2 v3.1.6
│   └── markupsafe v3.0.3
└── werkzeug v3.1.8
    └── markupsafe v3.0.3
```

Results are cached locally (`~/.cache/compat_check/`, 7-day TTL) since a
dry-run against the same environment and requirements won't change
minute-to-minute. Use `--no-cache` to force a fresh probe.

## How it works

1. Fetch the requirement list — from `pyproject.toml`, `requirements.txt`,
   or `setup.cfg` on the GitHub repo, or from PyPI's JSON API for a bare
   package name.
2. Create a disposable virtual environment (`uv venv` if `uv` is on PATH,
   otherwise the standard-library `venv` module — no hard dependency on
   `uv` being installed).
3. Run `pip install --dry-run` (or `uv pip install --dry-run`) against it —
   this resolves and would-download, but never actually installs anything
   or runs arbitrary setup code from the target package.
4. Report the result, retrying with failing packages dropped one at a time
   so every conflict in a multi-package source gets surfaced, not just the
   first one the resolver hits.

## What it deliberately does not check

- BLAS/LAPACK backend compatibility — this is a post-install diagnostic
  (`numpy.show_config()`), not something knowable before installing
- GPU/CUDA driver compatibility beyond what the resolver itself reports
- `setup.py`-only packages with no `pyproject.toml`/`requirements.txt`/
  `setup.cfg` (would require unsafe code execution to parse reliably)

## Connection to `conda-env-manager`

`conda-env-manager` diagnoses an *existing* environment (conda/pip
duplicates, known version conflicts like numba↔numpy) and then installs
missing packages directly. It has no step that checks a new package
*before* installing it for real. Slot `compat-check` in as a pre-check
between its Step 2 and Step 4:

```
conda-env-manager Step 2: scan_imports.py finds missing packages
    ↓
compat-check: python -m compat_check.cli <missing-package> --no-cache
    → OK: proceed to conda-env-manager Step 4 (install)
    → PROBLEMS FOUND: read the resolver's own conflict message before
      choosing a version, instead of discovering it mid-`conda install`
    ↓
conda-env-manager Step 4: install/fix (conda-forge first, pip --no-deps fallback)
```

This only matters for a package that is not already conda-forge-packaged —
`conda-env-manager`'s conda-forge-first rule already avoids most pip-level
resolver conflicts. Reach for `compat-check` specifically when a package
has to go through pip (no conda-forge build, or a GitHub source).

## Requirements

- Python 3.10+
- the `compat-check` package installed from PyPI (`python -m pip install
  compat-check`) — this folder holds only the documentation; installing the
  skill files alone leaves the import failing
- `uv` (preferred backend) or nothing extra — falls back to the standard
  library `venv` + `pip` automatically if `uv` is not on PATH
- Network access (to fetch requirement lists and probe real package
  resolution against PyPI)

## Tests

This folder ships documentation only (see "Usage" above) — there is no local
copy of the test suite to run here. The tests live with the code, in the
`compat-check` package's own repository (15 files / 148 tests as of 0.6.0,
pytest-collected). Run `python -m pip install compat-check[test]` (or clone
the package repo) and `pytest` there to exercise them; several hit the real
network (GitHub raw content, PyPI JSON API, actual `uv`/pip resolution) since
the entire point of this tool is that dry-run results are ground truth, not a
static prediction. A local copy of these tests was tried once and removed
(SSOT-20, 2026-09-24) — it drifted from upstream with no sync mechanism, the
same failure mode the source copy hit under SSOT-11; testing the installed
package's own suite is the SSOT.
