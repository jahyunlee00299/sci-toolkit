---
name: reference-surveyor
description: Tool for surveying implementation examples from public GitHub repositories and mapping them to your own use case. (1) Exploring public implementations of papers/methodologies, (2) Evaluating repositories (runnability, quality, similarity, license), (3) Analyzing key code patterns, (4) Verifying example execution, (5) Writing mapping documentation. Dedicated to P1.5.
---

# Reference Surveyor (Code Case Survey) — Dedicated to P1.5

Skill for exploring public repositories, analyzing code, and writing mapping documentation.

## Pipeline Position

```
P1 (Academic Review) → [P1.5 Reference Survey] → P2 (Implementation)
```

## Execution Method

- Repository exploration: Parallel WebSearch calls (simultaneous Papers With Code + GitHub search)
- Repository evaluation: Direct verification with Bash (`gh repo view`, etc.)
- Example execution: Bash → clone → venv → pip install → run

## Prerequisites

- P1 requirements document is complete
- Search keywords are prepared

---

## Step 1.5-1: Repository Exploration (Team Parallel)

### Search Source Priority

1. Direct paper link (Code Availability, supplementary)
2. Papers With Code
3. Direct GitHub search
4. Package documentation examples
5. Community (Stack Overflow, Reddit)

Search rules: minimum 2 searches, 1-6 words, no duplicate queries

---

## Step 1.5-2: Repository Evaluation & Selection

Evaluate each on 5 points: runnability, code quality, case similarity
License: MIT/Apache/BSD → PASS, none → FAIL
Python: 3.10+ → PASS

Select top 2-3.

---

## Step 1.5-3: Code Analysis

```
[Structure]     What is the project directory structure?
[Entry point]   What is the main execution flow?
[Core logic]    In which file and function is the algorithm I need?
[Data flow]     What are the data types and formats for input → transform → output?
[Configuration] How are parameters managed?
[Dependencies]  Which libraries are used?
```

---

## Step 1.5-4: Example Execution Verification

Fork → Clone → venv → pip install → run reference example → save results

```
results/reference/
├─ reference_output.json
├─ reference_run_log.txt
└─ reference_params.yaml
```

---

## Step 1.5-5: Mapping Documentation

File: `docs/reference_mapping.md`

Key content:
- Original repository info (URL, Fork, commit hash, license)
- Mapping table (reference location ↔ my use case location ↔ modification notes)
- Items requiring no modification / requiring modification
- Dependency differences
- Reference execution results

---

## Pre-check (Ask if uncertain)

Before starting work, if any of the following are unclear, **do not guess — ask the user**:
- Scope of methodology/algorithm to search
- Language/framework preference (Python only? R also OK?)
- License constraints (GPL allowed?)
- Fork requirement (read-only vs. actual modification planned)

## Completion Checklist (Report when done)

```
✅ N repositories explored, M selected
✅ Per-repo evaluation scores (runnability/quality/similarity)
✅ Example execution verification: pass/fail
✅ Mapping document docs/reference_mapping.md written
✅ Fork + upstream remote configured
✅ License verified
⬜ [List any missing items here]
```

## Exit Conditions

Deliverables: Forked repo + mapping document + reference execution results → P2

## Skill Integrations

- Input: P1 requirements document, S3 search results
- Output: → P2 (code-implementer), → P3 (code-validator), → P4 (triple comparison)
