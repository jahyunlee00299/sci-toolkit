# CODEX.md — running this toolkit under Codex CLI

`AGENTS.md` is the operating manual and it is deliberately tool-agnostic: Codex
reads it as-is, and everything in it applies here. **This file only covers what
is different when the agent is Codex rather than Claude Code.**

Read `AGENTS.md` first. Read this second.

---

## The one difference that matters: nothing is enforced for you

Claude Code runs the scripts in `hooks/` as `PreToolUse` hooks. Before a command
executes, a guard inspects it and can refuse — exit code 2 blocks the call.

**Codex has no equivalent.** `hooks/hooks.json` is inert here. Codex controls
risk with `approval_policy` and `sandbox_mode` in `~/.codex/config.toml`, which
gate *whether you may act at all*, not *what a specific command contains*.

So the seven rules below stop being a safety net and become **rules you follow
because you read them.** They are listed with the exact patterns the guards
matched, because a rule stated vaguely is a rule that gets rationalized around.

### 1. Credentials — never read, write, or print

Do not open, edit, cat, or echo: `secrets.json`, `*.credentials.json`,
`~/.ssh/*` private keys, `.git-credentials`, `.env` (the `.env.example`
template is fine).

Never write a literal credential into a file or a command. Patterns that count
as credentials: `sk-…`, `ghp_…`, `xox[baprs]-…`, and any
`api_key=`/`token=`/`secret=` assignment whose value is not an obvious
placeholder. Use an environment variable or a gitignored local config.

### 2. Deletion — never recursive, never forced

Forbidden without the user asking for that exact path in those words:
`rm -rf`, `rm -fr`, `sudo rm`, `find … -delete`, `find … -exec rm`,
`git clean -fd`, `robocopy /MIR`.

To remove something, move it to an archive directory instead. A move is
reversible; a delete on Windows outside the Recycle Bin is not.

### 3. Git — no history rewriting, no forced anything

Forbidden: `git push --force` / `-f` / `+refspec`, `git reset --hard`,
`git config --global`, `git branch -D`, and bypassing hooks via `--no-verify`
or `-c core.hooksPath=`.

**In a fork** (a repository with an `upstream` remote): never `git push
upstream`, and never run `gh pr create` without `--repo <your-fork>` — its
default target is the parent repository. For unpublished research this is the
one git mistake a revert cannot undo.

Stage files by explicit path. `git add -A` and `git add .` sweep in whatever
happens to be sitting in the tree.

### 4. Cloud-synced folders — never walk them recursively

Inside OneDrive / Dropbox / iCloud Drive / Google Drive paths, do not run
`find`, `ls -R`, `**` globs, `du`, or bulk `cat *`. Each of these forces every
file in the tree to download from the cloud — on a research folder that is tens
of gigabytes and a stalled session.

Read one specific file, or use the provider's API. To locate something, resolve
the path with a wildcard first (`ls -d "$HOME"/OneDrive*/`) rather than
searching.

### 5–7. Windows shell traps

These three matter because the command *appears to succeed* while doing
something else:

- **`conda run` + multi-line `python -c`** — newlines break in git-bash. Write
  the script to a file and run the file.
- **Non-ASCII inside a multi-line `python -c`** — the console is cp949, so
  `{"한글":1}` arrives as `{"??":1}`. Pure-ASCII multi-line is fine.
- **PowerShell syntax in a bash shell** — `$env:USERPROFILE` expands to
  `:USERPROFILE`, and `Get-Item`/`Out-File`/`Copy-Item` are not found. Either
  use bash syntax, or wrap the whole thing:
  `powershell.exe -NoProfile -Command "…"`.

> If you want these enforced rather than merely documented, run the guards
> yourself before acting:
> ```bash
> echo '{"tool_name":"Bash","tool_input":{"command":"<the command>"}}' \
>   | sh hooks/_run_hooks_chained.sh   # exit 2 = refuse
> ```
> That is the same chain Claude Code runs. It is a shell script — nothing about
> it is Claude-specific.

---

## What is the same

- **`AGENTS.md` §0 routing table** — the request → skill → gate map. Follow it.
- **`skills/`** — plain Markdown instructions plus helper scripts. Nothing in
  them assumes Claude Code. Read the relevant `SKILL.md` and follow it; run the
  scripts with `python`.
- **Verification gates (🔒 in §0 and §8)** — these are scripts with exit codes.
  Run them and read the exit code. Do not weaken a check to make it pass.
- **`doctor.py`** — `python doctor.py` must print `PASS`.
- **`scripts/feedback_log.py`** — records friction. Works identically.

## What does not apply

| Item | Why |
|---|---|
| `hooks/hooks.json` | Codex has no `PreToolUse` hook mechanism |
| `.claude-plugin/plugin.json` | Claude Code plugin manifest |
| `install/install.py --dest ~/.claude/skills` | pass your own `--dest` (see below) |
| `CLAUDE.md` | Claude Code reads it automatically; Codex reads `AGENTS.md` |

---

## Setup

Codex reads `AGENTS.md` from the working directory upward, plus
`~/.codex/AGENTS.md` globally. Two ways to wire this toolkit in:

**Per-project** — work inside a directory that has this repo's `AGENTS.md` in
its path, or copy it to your project root.

**Globally** — point your `~/.codex/AGENTS.md` at it, or append the routing
table to what you already have there. Keep your own machine-specific rules in
your global file; keep this repo's file generic, so it stays mergeable.

Skills are just directories of Markdown. There is no registration step:

```bash
python install/install.py --list                 # what is available
python install/install.py --preset paper-writing --dest ./skills-here --apply
```

`--dest` defaults to `~/.claude/skills`, which is meaningless under Codex —
always pass your own path. The installer merges rather than replacing, so
running it twice does not delete anything you added.

Then tell Codex where they are, e.g. in your project `AGENTS.md`:

> Skills live in `./skills/`. Before a task that matches a row in the §0
> routing table, read that skill's `SKILL.md` and follow it.

## Document skills (docx / pdf / pptx / xlsx)

Not in this repository — they are Anthropic's and their license forbids
redistribution. See `docs/12_문서스킬_직접_준비하기.md`. Under Codex you will
not have them at all, so for Word/Excel work use the lab-authored tools that
did ship, in `skills/manuscript-pipeline/scripts/`:

```bash
python skills/manuscript-pipeline/scripts/manuscript_text.py FILE.docx --count-only
python skills/manuscript-pipeline/scripts/figure_caption_check.py FILE.docx
python skills/manuscript-pipeline/scripts/word_com_ops.py --help    # Windows + Word
```

These need `python-docx` (and `pywin32` for the Word COM tools). They do not
depend on the Anthropic skills.
