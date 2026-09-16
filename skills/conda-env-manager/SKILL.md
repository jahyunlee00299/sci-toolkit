---
name: conda-env-manager
description: Conda environment management for scientific Python projects. Diagnose environments (list, verify existence, detect conda/pip conflicts), scan project imports via AST, identify missing packages, resolve version conflicts (numba-numpy etc.), create/repair environments with conda-forge priority, and configure VS Code interpreter settings. Use when setting up new projects, migrating from PyCharm, troubleshooting import errors, or auditing environment health.
license: MIT license
metadata:
    skill-author: Lab Researcher
---

# Conda Environment Manager

## Overview

Skill for automating creation, diagnosis, and recovery of conda environments per project.
Used for PyCharm → VS Code migration, environment rebuilding, and dependency conflict resolution.

## When to Use

- When `ImportError` / `ModuleNotFoundError` occurs in a project
- When setting up a new project environment
- When migrating from PyCharm to VS Code
- When package conflicts occur from conda/pip mixing
- When verifying whether an environment is deleted/damaged

## Workflow

```
Step 1: Environment diagnosis (check_env.py --list)
    → All conda environments + disk existence + Python version
    ↓
Step 2: Project scan (scan_imports.py <dir> [env])
    → Extract imports via AST → classify installed/missing packages
    ↓
Step 3: Conflict check (check_env.py --check <env>)
    → Detect conda/pip duplicates + check known version conflicts
    ↓
Step 3.5: Pre-install probe for anything pip-only (see `compat-check` below)
    → For a missing package with no conda-forge build (or a GitHub source),
      dry-run it before installing for real
    ↓
Step 4: Install/fix
    → Install missing packages (conda-forge priority → pip fallback)
    → Fix version conflicts
    ↓
Step 5: VS Code connection (optional)
    → Set interpreter path in .vscode/settings.json
```

## Related skill: `compat-check`

This skill diagnoses environments **after the fact** — conda/pip duplicates,
known version conflicts, a package that already failed to import. It has no
step that checks a candidate package *before* actually installing it.

For a package Step 2 flags as missing that has no conda-forge build (so it
has to go through pip) or comes from a GitHub URL, run
`skills/compat-check` first: it does a real dry-run install in a disposable
venv and surfaces the resolver's own conflict message, instead of you
discovering the conflict mid-`pip install`. See
`skills/compat-check/SKILL.md` for usage.

## Scripts

### `scripts/scan_imports.py`

Extract third-party imports from `.py` files in project directory via AST.

```bash
# Basic scan
conda run -n base python scripts/scan_imports.py /path/to/project

# Check missing packages by comparing with conda environment
conda run -n base python scripts/scan_imports.py /path/to/project env_name
```

**Features:**
- Automatic stdlib vs third-party distinction
- Identify optional imports inside try/except
- Map import names → package names (PIL→Pillow, sklearn→scikit-learn, etc.)
- Flag conda-forge-only packages (rdkit, openmm, etc.)

### `scripts/check_env.py`

Diagnose conda environment status.

```bash
# Full environment list + existence check
conda run -n base python scripts/check_env.py --list

# Diagnose specific environment (duplicate/conflict check)
conda run -n base python scripts/check_env.py --check biosteam
```

**Features:**
- Verify registered environments vs actual disk existence
- Detect conda/pip duplicate packages
- Automatically check known version conflicts (numba↔numpy, etc.)

### `references/known_conflicts.yml`

DB of known version conflict patterns. Referenced by check_env.py.

## Installation Rules

Follow the priority below when installing packages:

### 1. conda-forge first

```bash
# Good: install pre-built binaries from conda-forge
conda install -n env_name -c conda-forge rdkit numpoly

# Bad: attempt to build C extension packages via pip (may fail on Windows)
pip install rdkit  # ❌ build failure
```

### 2. pip with --no-deps only for minimum needed

Conflicts occur when conda and pip packages share the same dependencies.
Install with pip using `--no-deps` for only the needed packages.

```bash
# Install base with conda
conda install -n env_name -c conda-forge numpoly

# Install only top-level package with pip (conda manages dependencies)
conda run -n env_name pip install biorefineries --no-deps
```

### 3. Prevent conda/pip duplication

```bash
# Check: if same package exists in both conda and pip
conda run -n env_name pip show numpoly  # check pip version
conda list -n env_name numpoly          # check conda version

# Fix: remove pip version → keep only conda version
conda run -n env_name pip uninstall numpoly -y
conda install -n env_name -c conda-forge numpoly --force-reinstall
```

## Known Issues

### C extension build failure on Windows

**Symptom:** `Microsoft Visual C++ 14.0 or greater is required`
**Cause:** Build Tools not installed
**Fix:** Use pre-built binary from conda-forge

### numba ↔ numpy version mismatch

**Symptom:** `Numba needs NumPy 2.3 or less`
**Cause:** pip installs latest numpy (2.4+), numba only supports up to 2.3
**Fix:** `pip install "numpy<=2.3"`

### conda/pip ghost packages

**Symptom:** Previous pip version is imported even after conda install
**Cause:** pip's dist-info shadows conda installation
**Fix:** `pip uninstall <pkg>` → `conda install --force-reinstall`

### conda activate not working in Claude Code

**Symptom:** `conda activate` command does not work
**Cause:** Claude Code bash does not load `~/.bashrc`
**Fix:** Use `conda run -n env_name <command>`

## VS Code Integration

Configure per-project interpreter in `.vscode/settings.json`:

```json
{
    "python.defaultInterpreterPath": "<CONDA_BASE>\\envs\\biosteam\\python.exe"
}
```

Or click VS Code bottom status bar → `Python: Select Interpreter` → select environment.
