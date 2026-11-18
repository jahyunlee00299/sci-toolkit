---
name: skill-developer
description: "Guide for creating new skills and wiring their auto-activation. The SKILL.md description is the trigger, a router hook is optional, and a trigger counts only after one measured firing. Used when creating, adding or configuring skills. Keep descriptions short - the skill listing has a character budget and Hangul counts double."
---

# Skill Developer — Skill Creation Guide

This skill covers the MECHANICS of a skill file: frontmatter, `references/`, and trigger wiring. It does
not decide WHETHER a new skill should exist or how it connects to its neighbors. Check first that no
existing skill already covers the job (search the skills folder and read the closest candidate's
`description`); a duplicate skill splits the triggers and the maintenance.

## Core Structure

```
~/.claude/
├── commands/              ← Personal custom skills (slash commands)
│   └── {name}.md          ← YAML frontmatter + Markdown body
├── skills/
│   └── {name}/
│       ├── SKILL.md       ← YAML frontmatter + Markdown body (the entry point)
│       ├── references/    ← depth, loaded only when the body points to it
│       └── scripts/       ← runnable tools the body names with a relative path
└── hooks/                 ← optional: UserPromptSubmit router if you run one
```

## Agent-Suitability Check When Modifying Skills

Before finalizing a new or modified SKILL.md, judge whether its tasks need sub-agent delegation. Do this
inline (one read plus a judgment call); a one-file suitability check is direct work, not a spawn.

**Needs an agent** (add an "Execution Method: must run as Agent" note near the top of SKILL.md):
- Parallel queries across several sources (literature databases, repositories, ...)
- Large, long-running outputs (paper sections, comprehensive reviews)
- Context-contamination risk (big intermediate results that should not pollute the main thread)
- Tasks that need autonomous exploration and judgment
- Tasks touching many files

**Does not need an agent** (leave as direct execution; this is the default):
- Interactive tasks that need user confirmation mid-process
- Simple single-call lookups
- Short, immediate tasks
- Tasks that need the user's judgment during design

Do not batch-scan the whole skills folder and stamp every SKILL.md with an agent-required note: direct
execution is the default and delegation is the exception.

---

## Create a New Skill (5 Steps)

### 1. Create the File
`~/.claude/skills/{skill-name}/SKILL.md` (or `~/.claude/commands/{skill-name}.md` for a personal slash command)

```markdown
---
name: my-skill
description: When to use this skill, with the trigger phrases users actually type (<=1024 chars)
---

# Skill Title

## Purpose
What this skill does

## Execution Procedure
Step 1. ...
Step 2. ...
```

**Rules:**
- ✅ ≤500 lines (if exceeding, split to a `references/` file)
- ✅ Trigger keywords explicit in the description
- ✅ Clear execution procedure included
- ✅ Keep the description short: the skill listing has a character budget, and Hangul counts double

### 2. Wire the Trigger

> **The `description` in the frontmatter is the trigger.** The harness lists every skill's name and
> description, and the model picks from that list. Put the phrases a user would type (in every language
> you work in) into the description.
>
> If you also run your own UserPromptSubmit router hook, add the rule to that hook's rule list, and
> **measure one actual firing** afterwards (step 3). A rule with no wiring is not a feature.
>
> A config file is not a feature until something reads it. A trigger-registry JSON that no hook ever
> loads looks exactly like a working registry and does nothing; edits to it change nothing. Before
> trusting any registry file, find the code that reads it.

### 3. Verify the Trigger Actually Fires

With a router hook, feed it a prompt that should trigger the skill and read what it prints:

```bash
printf '%s' '{"prompt":"<a prompt that should trigger it>"}' | bash ~/.claude/hooks/<your_router>.sh
```

Without a router, open a fresh session, type that prompt, and check that the skill is the one chosen. Also
type one prompt that should NOT trigger it. Editing a hook itself: edit the master copy, syntax-check it
(`bash -n`), fire-test it, then re-test the deployed copy.

### 4. Refine Triggers
- Keywords: focus on phrases users actually use
- If many false positives, make the phrases more specific
- When two skills fire on one prompt, narrow the description of the one that is further from the job

### 5. Verify the 500-Line Limit
```bash
wc -l ~/.claude/skills/my-skill/SKILL.md
```

---

## Check Skill Names Before Writing Them Down

A prose table of skill names goes stale after every reorganisation: skills get merged, renamed and retired,
and the table keeps naming them. Before trusting or writing any skill name in a document, list the real
folders (`ls ~/.claude/skills/`) and use only names that exist.

---

## Hook System Structure (optional router)

```
User input
    ↓
UserPromptSubmit hook (parallel execution)
    └── your router hook → matches the prompt against its rule list
            ↓ (stdout)
        Claude receives it as context
            ↓
        Related skill suggestion shown
```

## Official Agent Skills Spec

- Spec: https://agentskills.io/specification
- SKILL.md format: YAML frontmatter + Markdown

## Write Skills to Be Extended

Keep SKILL.md lean and put depth in `references/<topic>.md`, so that a later lesson can be added as a short
addition without growing the entry point. A skill about irreversible external actions (sending mail,
payments, administration) should never be edited unattended.
