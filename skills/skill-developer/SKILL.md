---
name: skill-developer
description: Guide for creating new skills, modifying skill-rules.json, understanding hook system. Used when creating/adding/configuring skill triggers.
---

# Skill Developer — Skill Creation Guide

## Core Structure

```
~/.claude/
├── commands/              ← Personal custom skills (slash commands)
│   └── {name}.md          ← YAML frontmatter + Markdown body
├── skills/
│   ├── skill-rules.json   ← Auto-activation trigger configuration
│   └── {name}/SKILL.md    ← Public K-Dense skills (170)
└── hooks/
    ├── skill-activation-prompt.py   ← Analyze prompt → suggest skills
    └── skill-activation-prompt.sh   ← Wrapper
```

## Team Workflow When Modifying Skills

When skill creation/modification request comes in, check agent-suitability criteria:

```
[Checker agent]                    [Modifier agent]
Review skill draft             →   Reflect feedback, modify file
- Evaluate agent suitability        - Create commands/*.md
- Detect anti-patterns              - Add skill-rules.json triggers
- Output recommendations            - Run JSON validation
```

> Agent suitability: prefer a sub-agent when the task is multi-file or long-running.

---

## Create New Command Skill (5 Steps)

### 1. Create File
`~/.claude/commands/{skill-name}.md`

```markdown
---
name: my-skill
description: When to use this skill, include trigger keywords (≤1024 chars)
---

# Skill Title

## Purpose
What this skill does

## Execution Procedure
Step 1. ...
Step 2. ...
```

**Rules:**
- ✅ ≤500 lines (if exceeding, split to references/ file)
- ✅ Trigger keywords explicit in description
- ✅ Clear execution procedure included

### 2. Add Trigger to skill-rules.json

Add to `~/.claude/skills/skill-rules.json` `skills` section:

```json
"my-skill": {
  "type": "domain",
  "enforcement": "suggest",
  "priority": "high",
  "description": "One-line description",
  "promptTriggers": {
    "keywords": ["keyword1", "keyword2", "keyword3"],
    "intentPatterns": [
      "(verb|동사).*(noun|명사)",
      "(keyword).*(action|동작)"
    ]
  }
}
```

**Choose priority:**
| Level | When to Use |
|------|-----------|
| `critical` | Always needed core skill |
| `high` | Clear related work |
| `medium` | Possibly related |
| `low` | Reference |

### 3. Test Hook Behavior

```bash
echo '{"session_id":"test","prompt":"help with paper writing","cwd":"/tmp","permission_mode":"default"}' | \
  python ~/.claude/hooks/skill-activation-prompt.py
```

### 4. Refine Triggers
- Keywords: focus on phrases users actually use
- intentPatterns: regex, use `(A|B).*(C|D)` patterns
- If many false positives, make keywords more specific

### 5. Verify 500-Line Limit
```bash
wc -l ~/.claude/commands/my-skill.md
```

---

## Current Command Skills

| Skill | Example Trigger Keywords |
|------|--------------------|
| `manuscript-writer` | paper writing, manuscript, paper writing |
| `research-discussion` | discussion, result interpretation, interpret result |
| `pptx-reviewer` | ppt, slide, powerpoint, typo |
| `experiment-hub` | experiment plan, protocol design |
| `research-search` | find papers, literature search, pubmed |
| `code-validator` | code review, pytest, debugging |
| `improvement-analyzer` | improvements, retrospective, bottleneck |
| `git-workflow-manager` | git, commit, PR, branch |
| `conda-env-manager` | conda, virtual environment, package install |
| `academic-term-rules` | academic notation, italic, gene notation |
| `solid-principles` | SOLID, refactoring, class design |
| `lab-equipment-check` | equipment reservation, HPLC, lab equipment |
| `reference-surveyor` | GitHub investigation, implementation case |
| `code-implementer` | implementation, implement, fork |
| `update-skills` | skill update, install skills |
| `weekly-briefing` | weekly briefing, weekly summary |
| `skill-developer` | create skill, skill-rules |

---

## Hook System Structure

```
User input
    ↓
UserPromptSubmit hook (parallel execution)
    ├── prompt_hook.sh    → Usage report + in_progress detection
    └── skill-activation-prompt.sh → Python skill-rules.json matching
            ↓ (stdout)
        Claude receives as context
            ↓
        Related skill suggestion message shown
```

## Official Agent Skills Spec

- Spec: https://agentskills.io/specification
- K-Dense public skills: `~/.claude/skills/` (170)
- SKILL.md format: YAML frontmatter + Markdown

---

**Reference**: `skill-rules.json` JSON syntax validation
```bash
python -c "import json; json.load(open('$HOME/.claude/skills/skill-rules.json'))"
```
