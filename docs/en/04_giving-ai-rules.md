> English translation of [04_AI에게_규칙주기.md](../04_AI에게_규칙주기.md). The Korean original is canonical; if they differ, the Korean version wins.

# 04. Giving the AI Rules: What Are CLAUDE.md and AGENTS.md?

This document is a guide for beginners who wonder,
"Why do I need to create something like a rules file for an AI agent?"
You only need to understand the concept; you don't have to write a rules file yourself right now.

---

## 1. Why do you need a rules file?

In document 00, we compared an AI agent to "a new researcher seated in front of my computer."
What would happen if a new researcher started work on the first day with no explanation at all?

- They wouldn't know how our lab organizes files, so they'd save things in the wrong places,
- They might accidentally overwrite an important original file,
- And you'd have to explain "please do it this way" from scratch every single time.

A rules file (CLAUDE.md / AGENTS.md) is like writing down "this is how our lab works" in advance
and leaving it on this new researcher's desk. The AI automatically reads this file before starting work
and tries to follow the rules written in it.

> Analogy: it plays the same role as a company's "new employee manual" or a lab's "SOP (standard operating procedure)."
> Even if a person doesn't explain it out loud every time, once it's written down,
> it gets followed every time.

---

## 2. What's the difference between CLAUDE.md and AGENTS.md?

- CLAUDE.md: the file name that Claude Code automatically reads from a project folder.
  If you use Claude Code, save it under this name.
- AGENTS.md: a name recognized in common not only by Claude Code but also by other AI agent tools such as Codex.
  Use it when writing "shared rules" that aren't tied to a specific tool.

You can keep both files in the same project. For example, `CLAUDE.md` can say only briefly,
"See AGENTS.md for details," while the actual content is gathered in `AGENTS.md`. Since keeping the two
separately maintained for each tool is a hassle, it's convenient to gather the content
in one place and have the other file point to it.

Place them at the top of the project folder (the repository you're working in), that is,
the root directory. The AI automatically finds and reads them when it starts work in that folder.

---

## 3. Thinking of the rules in three levels

If you list rules haphazardly, both the AI and people get confused. Dividing them into the following three levels
makes it easy to organize.

### (1) Always follow (basic principles)

These are things that must be followed automatically every time unless there are special circumstances. Examples:
"Write new code in small, function-sized pieces," "Re-check important calculation results
against the original data." The AI follows these without asking a person each time.

### (2) Ask first (hard to undo, or ambiguous)

These are things where the AI must first get a person's confirmation: "Is it okay to proceed this way?"
They usually have one of the following two characteristics.

- Hard to undo: deleting a file permanently, overwriting without a backup, etc.
- Ambiguous default: there are several options and it's hard for the AI to judge on its own
  which is right.

### (3) Never do (prohibitions)

These are things that must not be done under any instruction, even if you hear
"It's fine, just do it." Examples: writing a password or API key directly into code
and uploading it to a repository, or running a deletion command that can't be forcibly undone
without confirmation. At this level the rules are absolute.

> If you write rules down divided into these three levels, the AI can tell for itself:
> "This is something I can just do," "This I should ask about first," "This I must not do at all."

---

## 4. A very small example (general content only)

Below is a very small, general example that could apply to any project.
It contains no specific lab or personal information.
It is a sample to show the concept. You can copy it and use it as is, or adapt it to our situation.

```markdown
# CLAUDE.md example

## Always follow
- Before changing code, read the file in question first (don't guess).
- Write new code in small pieces so that each does only one job.
- Report result numbers (calculated values, statistics, etc.) only after re-checking them against the original data.

## Ask first
- When an existing file must be overwritten entirely (with no backup).
- When it's ambiguous which of several approaches is right.
- Before taking an action that goes outside (sending email, publishing publicly, etc.).

## Never do
- Uploading sensitive information such as passwords or API keys directly into code or a repository.
- Forcibly deleting files without the user's explicit request, or
  running commands that can't be undone (the `force delete` family).
- Accidentally overwriting an important original file without confirmation.
```

These three short sections are already useful. Don't try to write it perfectly from the start;
as you work, every time you think, "Ah, I should have said this in advance," just add one more line.

---

## 5. This toolkit already has rules files

The sci-toolkit you're using right now already has files like these.

- `AGENTS.md` (the toolkit's top-level folder): it lays out the general rules that apply
  in common no matter which AI agent tool you use. It contains the order in which a request
  should be handled (the routing table), code quality principles, result verification
  principles, safety standards (the list of things never to do), and so on.
- `CLAUDE.md` (in the same location): a short file for Claude Code that
  points to `AGENTS.md` and adds only a few Claude Code-specific items.

You don't need to edit these files yourself right now. But when you become curious about "Why does the AI
behave this way?", you can open these two files to see
the reason (which rules it is following). In particular,
the "0. Routing" table at the very front of `AGENTS.md` shows at a glance which request goes through which procedure,
so skimming it when you're curious can help.

If you need a rules file when starting a new project, you can also copy `AGENTS.md` as is
and adapt it to our situation. That's why the very top of that file says
"written so it can be used generally, without personal information or institution names."

---

## 6. Summary

| Question | Answer |
|---|---|
| What is a rules file? | A document, automatically read by the AI agent before work, that says "this is how we work" |
| CLAUDE.md vs AGENTS.md | The former is a Claude Code-specific name, the latter a tool-common name. You can keep both and write the content in just one |
| Three-level rules | (1) Always follow (2) Ask first (hard to undo or ambiguous) (3) Never do |
| What are this toolkit's rules files? | `AGENTS.md` (shared rules) + `CLAUDE.md` (a short guide for Claude Code) in the top-level folder |
| What should I do right now? | You don't have to do anything. Open the two files when you're curious |

The next document (05) explains how this toolkit connects with external services (mail, Notion, Asana, etc.).
