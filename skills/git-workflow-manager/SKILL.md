---
name: git-workflow-manager
description: Comprehensive Git workflow management for clean repositories. ALWAYS enforces git pull before modifications in any git repository, automatically cleans up test/temp files keeping only final versions, detects duplicate files and suggests consolidation. Includes branch rules for research coding pipeline, commit tags ([P1]-[P5]), and upstream tracking procedures.
---

# Git Workflow Manager

Enforces best practices: git pull before modifications, automatic test file cleanup, duplicate file detection, pipeline branch strategy.

## Core Principle

**ALWAYS check and update git repository BEFORE making any modifications.**

## Critical Workflow

### 1. Before ANY Modifications (MANDATORY)

```bash
git status
git pull origin dev  # or main
```

### 2. During Development

Clean up test/temp files: test_*, temp_*, *_backup.*, *_old.*, scratch_*, debug_*

### 3. After Completing Work

Detect and clean up duplicate files.

---

## Parallel Sessions & SSOT Loss Prevention (260721)

**Parallel delegation is the main path to losing the canonical copy. Worktrees prevent
edit collisions but make SSOT loss WORSE (more copies). Order matters: guard first, worktree second.**

Measured incident (260721): 3 tmux sessions on one working tree →
202 lines of one session's work drifted onto another session's branch (uncommitted, carried
along by `checkout`). Audit then found **15 accumulated worktrees** (2 in `/tmp` = lost on
reboot) and **18 local-only branches**. One `/tmp` worktree held 7 uncommitted files including
a `delegation_worktree_template.sh` — a prior attempt to fix this very problem, itself about to vanish.

### Rules

1. **Never attach 2+ sessions to the same working tree.** Use a dedicated worktree per session.
2. **Diagnose before delegating.** RED → do not start.
3. **Never create worktrees in `/tmp`** (lost on reboot). Use `~/worktrees/`.
4. **Push branches the moment work ends.** A local-only branch is scheduled data loss.
5. **Snapshot before switching branches** if any other session is alive.
6. Assign **disjoint file sets** per parallel session; state them in the work order.

### Tooling

```bash
ssot_guard.sh check <repo>      # 7-axis diagnosis (RED → stop)
ssot_guard.sh snapshot <repo>   # preserve uncommitted work
ssot_guard.sh doctor <repo>     # check + auto-snapshot on RED
delegate_safe.sh <session> <repo> <workorder>   # guard → snapshot → worktree → auto-push
delegate_safe.sh --status | --cleanup
```

`ssot_guard.sh` axes: detached HEAD / uncommitted changes / trunk contamination /
concurrent sessions / worktree accumulation / unpushed branches / trunk sync.

Snapshots keep `tracked.patch` + untracked originals + **`branch.bundle`** (full history —
recover with `git clone <bundle>`), plus `CONTEXT.txt` with recovery steps.

### Merging accumulated branches

Back up trunk as a bundle first, then merge **independent files first, shared files last**.
Verify **after merging, before pushing** — per-branch passes do not guarantee the integrated
state. Check `git merge-base --is-ancestor` for stacked branches to avoid double merges.

---

## Pipeline Branch Strategy

```
main              # validated code only (merge after P4 ✅ pass)
├── dev           # code under development (P2-P3 work)
├── exp/{name}    # per-experiment branches (P1 requirement units)
└── fix/{issue}   # fix branch when P4 ❌ → P2 regression
```

Rules:
- P2 work is done on `exp/{experiment-name}` branch
- On P4 ✅ pass: merge exp/ → dev → main in order
- On P4 ❌: create `fix/{issue-N}` branch → fix → merge into exp/
- No direct commits to main

---

## Pipeline Commit Tags

```
Format: [Phase] type: description

Phase tags:
  [P1]   — write/modify requirements document
  [P1.5] — write mapping document, Fork repo
  [P2]   — code implementation, refactoring, test writing
  [P3]   — error fixes
  [P4]   — record validation results
  [P5]   — cycle log, improvement notes

type:
  feat / fix / refactor / test / docs / chore
```

Examples:
```
[P1.5] docs: write reference_mapping.md
[P2] feat: implement ribose conversion model
[P3] fix: fix pH calculation error (fix 1/3)
[P4] docs: record triple comparison results ✅
[P5] log: cycle 1 complete, add improvement notes
```

---

## Fork Repo Upstream Management

```bash
# Initial setup (after Fork in P1.5)
git remote add upstream https://github.com/{original}/{repo}.git

# Check every cycle in P5
git fetch upstream
git log HEAD..upstream/main --oneline

# Merge relevant updates (in next cycle P2)
git checkout exp/{name}
git merge upstream/main
```

---

## Pipeline Integration Workflow

```bash
# 1. Cycle start — check git status
git status && git pull

# 2. P1.5 — Fork & create branch
git checkout -b exp/{experiment-name}

# 3. P2 — implementation (commit per modified item)
git commit -m "[P2] feat: {change description}"

# 4. P3 — when fixing errors
git commit -m "[P3] fix: {error description}"

# 5. P4 ❌ regression
git checkout -b fix/{issue-N}
# ... fix ...
git commit -m "[P2] fix: P4 regression — {description}"
git checkout exp/{experiment-name}
git merge fix/{issue-N}

# 6. P4 ✅ pass
git checkout dev && git merge exp/{experiment-name}
git checkout main && git merge dev

# 7. P5 — log commit
git commit -m "[P5] log: cycle N complete"

# 8. Cleanup
git push origin main
```

---

## Safety Features

- Never forces destructive operations
- Warns before stashing
- Dry-run by default for cleanup
- Duplication detector is read-only

---

## Pre-Confirmation Before Commit/Push/PR (MANDATORY)

**Always get user confirmation before commit, push, or PR creation.** Do not perform automatically.

### Actions requiring confirmation
1. **Commit** — show commit message and file list, then ask "Shall I commit?"
2. **Push** — show target remote/branch, then ask "Shall I push?"
3. **PR creation** — show PR title, body, base/head branch, then ask "Shall I create the PR?"

### Rules
- Even if user **explicitly requests** "commit", "push", "create PR", etc., show a summary and get final confirmation just before executing
- Even if commit+push requested together, confirm each step separately (confirm commit → confirm push)
- `--force`, `--force-with-lease` pushes **must** include a danger warning before confirmation
- This rule applies to all git repos (any repo you work in — analysis code, manuscripts, shared toolkits)
