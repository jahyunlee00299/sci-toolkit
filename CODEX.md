# CODEX.md — running this toolkit under Codex CLI

`AGENTS.md` is the operating manual and it is deliberately tool-agnostic: Codex
reads it as-is, and everything in it applies here. **This file only covers what
is different when the agent is Codex rather than Claude Code.**

Read `AGENTS.md` first. Read this second.

---

## The difference that matters: assume nothing is enforced until you wire it

Claude Code runs the scripts in `hooks/` as `PreToolUse` hooks. Before a command
executes, a guard inspects it and can refuse — exit code 2 blocks the call.

**Under Codex this package's guards do not run unless you wire them yourself.**
Dropping the repo in a directory gets you the *rules*, not the *enforcement*.
Until that wiring is done and verified, the seven rules below are **rules you
follow because you read them** — listed with the exact patterns the guards
match, because a rule stated vaguely is a rule that gets rationalized around.

Codex additionally has `approval_policy` and `sandbox_mode` in
`~/.codex/config.toml`, which gate *whether you may act at all*, not *what a
specific command contains* — necessary, but not a substitute for the
content-level checks below.

> **Note (verified 2026-08-16, Codex CLI 0.147.0).** Earlier versions of this
> file said Codex had no hook mechanism at all. That is no longer true, and the
> correction matters enough to state precisely — see
> [§ Codex-native enforcement](#codex-native-enforcement-hooks-and-rules) below
> for what is confirmed, what is still unverified, and why you should not yet
> rely on it.

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

<a id="codex-native-enforcement-hooks-and-rules"></a>

## Codex-native enforcement: hooks and rules

Codex has two enforcement mechanisms of its own. They are **separate
subsystems**, they behave differently, and only one of them is proven to block.

Everything below was measured against **Codex CLI 0.147.0 on 2026-08-16**.
Where a claim could not be verified, it says so — do not upgrade a
"not verified" line into a "works" line without re-measuring.

### Rules — argv-prefix allow/forbid (confirmed to block)

Codex reads `$CODEX_HOME/rules/*.rules` (default `~/.codex/rules/`). Entries
look like:

```python
prefix_rule(pattern=["rm", "-rf"], decision="forbidden")
prefix_rule(pattern=["git", "push", "--force"], decision="forbidden")
```

- Matching is on the **argv prefix**, not command content. There is no regex or
  substring form — `prefix_rule` was the only rule type found.
- `decision="forbidden"` genuinely blocks.
- **This is the reliable way to enforce rules 2 and 3** (deletion, git) under
  Codex today. It cannot express the content-level checks — the credential
  patterns in rule 1, or the cloud-path and Windows-shell traps in rules 4–7 —
  because those depend on what is *inside* the command, not on its first tokens.

### Hooks — same schema as this package, contract unverified

`codex features list` reports `hooks  stable  true`, and the CLI exposes
`--dangerously-bypass-hook-trust`, so hooks are real and trust-gated.

Codex hook files use **the same JSON schema as this package's
`hooks/hooks.json`** — verified by structural comparison against the
`hooks.json` files shipped by Codex's own plugins:

```json
{"hooks": {"PreToolUse": [{"matcher": "Bash|Write|Edit",
  "hooks": [{"type": "command", "command": "./path/to/guard.sh"}]}]}}
```

Event names present in the binary: `PreToolUse`, `PostToolUse`, `SessionStart`,
`SessionEnd`, `UserPromptSubmit`.

**What is NOT verified, and why it matters:**

| Unverified | Consequence |
|---|---|
| The exit-code contract (is exit 2 a block?) | A guard could run, "fail", and the command proceeds anyway |
| The stdin payload format | The guards parse `tool_name` / `tool_input` from stdin JSON; if Codex passes something else they see an empty command and pass everything |
| Where a non-plugin hook file must live to be loaded | Wiring may silently no-op |

A guard that runs but cannot read the command is worse than no guard: it
produces a green light on an unchecked command. **So do not assume the wiring
works because you created the file.** Prove it first — make a guard that should
block actually block, on a command you know is forbidden — and only then rely
on it. Until you have done that, keep using the manual `_run_hooks_chained.sh`
call above.

If you do verify the contract, please record it via
`python scripts/feedback_log.py add "..."` so this section can be finished.

---

## Sub-agents and teams

Codex has native multi-agent support (`multi_agent  stable  true`). The primary
agent is `/root` and can spawn others through a collaboration tool namespace,
separate from the shell/exec namespace:

```
spawn_agent · followup_task · send_message · wait_agent · interrupt_agent · list_agents
```

- Concurrency and nesting are capped by `[agents]` in `~/.codex/config.toml`
  (`max_threads`, `max_depth`, `job_max_runtime_seconds`).
- Agent roles are `.toml` files in `$CODEX_HOME/agents/`. Only `description` is
  required; `name`, `developer_instructions`, and `nickname_candidates` are in
  active use.
- **Spawning is policy-gated.** In the install measured here, Codex was
  explicitly instructed not to spawn sub-agents *unless the user, an
  `AGENTS.md`, or a skill asks for delegation.* So a skill that needs a team has
  to say so — it will not happen implicitly.

`AGENTS.md` §6 (model routing) and §2 (distrust self-report) apply unchanged,
and §6 is the part worth re-reading before spawning anything: do not spawn an
agent for what one or two direct reads would answer, and prefer a single
verifier holding the whole artifact over parallel verifiers each holding a
fragment.

> Two skills in this package ask for delegation: `journal-presentation-maker`
> and `endnote-citation-injection`. Both are written against roles rather than a
> vendor API, so under Codex they map onto `spawn_agent` directly. Neither needs
> a team below its stated threshold — `endnote-citation-injection` says to run
> ≤5 refs inline, and §6 says the same thing generally.

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
| `hooks/hooks.json` **as loaded automatically** | Claude Code loads it via `.claude-plugin`. Codex uses the same schema but will not pick this file up on its own — wire it, then prove it blocks (see above) |
| `${CLAUDE_PLUGIN_ROOT}` in the hook commands | Claude Code sets that variable. Under Codex the paths must resolve some other way |
| `.claude-plugin/plugin.json` | Claude Code plugin manifest |
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

Skills are just directories of Markdown, in the same `SKILL.md` + YAML
frontmatter format both agents read. Codex **does** have a skill registry:
`$CODEX_HOME/skills` (default `~/.codex/skills`) is the user-scope location,
and Codex injects the discovered list at session start.

```bash
python install/install.py --list                 # what is available
python install/install.py --preset paper-writing --apply
```

With only `~/.codex` present, `--dest` defaults to `~/.codex/skills`. Pass your
own `--dest` to put them somewhere else (a project-local folder that your
`AGENTS.md` points at works too). The installer merges rather than replacing,
so running it twice does not delete anything you added.

> Codex's skill metadata carries a `repo` scope alongside `user`, so
> repository-local skills appear to be supported — but the directory
> convention for it could not be confirmed locally (checked 0.147.0). If you
> want per-repo skills, verify the path against current Codex docs rather than
> guessing.

Then tell Codex where they are, e.g. in your project `AGENTS.md`:

> Skills live in `./skills/`. Before a task that matches a row in the §0
> routing table, read that skill's `SKILL.md` and follow it.

## Document skills (docx / pdf / pptx / xlsx) — you have OpenAI's, not Anthropic's

This repository ships none of them: they are Anthropic's and their license
forbids redistribution (`docs/12_문서스킬_직접_준비하기.md`). That does **not**
leave you without office tooling under Codex — it means you use a different
implementation, and the routing table rows that name `docx`/`pptx`/`xlsx`/`pdf`
resolve to OpenAI's bundled equivalents instead.

Verified 2026-08-16 on Codex CLI 0.147.0. Five plugins ship under
`$CODEX_HOME/plugins/cache/openai-primary-runtime/`, all registered
`enabled = true` in `~/.codex/config.toml` — active by default, not opt-in:

| Codex plugin | Covers | Notes |
|---|---|---|
| `presentations` | `.pptx`, Google Slides | Bundled 26-layout template library; template-following mode inherits a supplied deck's masters |
| `documents` | `.docx`, Google Docs | Built on `python-docx` plus an OOXML patch layer for tracked changes and comments |
| `spreadsheets` | `.xlsx`/`.xls`/`.csv`/`.tsv`, Google Sheets | Also drives a live Excel instance |
| `pdf` | Read / create / render / extract | `reportlab`, `pdfplumber`/`pypdf`, Poppler |
| template&#8209;creator | Turns an existing artifact into a reusable personal skill | |

Two constraints worth knowing before you plan the work, both stated in the
plugins' own `SKILL.md` files:

- **`presentations` forbids the python&#8209;pptx library** and works only through
  its own sandboxed JS API. Do not try to script a deck around it.
- **`presentations` forbids programmatically drawn images** (matplotlib output,
  vector shapes built in code) for slide visuals.

That second one collides with how this toolkit makes scientific slides, so
route around it — see below.

### Making a scientific deck under Codex

`journal-presentation-maker` assumes the Claude-side `pptx` skill, whose figure
pipeline (pull a figure out of a paper PDF, crop it, place it) has no
counterpart here. Under Codex, split the work:

1. **Make the figures first, outside the deck.** `publication-figures` produces
   PNGs and `scripts/figure_lint.py` gates them — unchanged under Codex, both
   are plain Python.
2. **Then hand `presentations` finished image files.** Placing an existing PNG
   is not "programmatically drawing" one, so this stays inside its rules.
3. Keep the content gates as they are: numbers still trace to their source
   (§3), notation still goes through `academic-term-rules`.

Do not ask `presentations` to plot your data. It will either refuse or produce
something you would not put in a talk.

### Lab-authored Word tools still work

Independent of either vendor's skills, these shipped with this package and run
on plain `python-docx` (plus `pywin32` for the COM tools):

```bash
python skills/manuscript-pipeline/scripts/manuscript_text.py FILE.docx --count-only
python skills/manuscript-pipeline/scripts/figure_caption_check.py FILE.docx
python skills/manuscript-pipeline/scripts/word_com_ops.py --help    # Windows + Word
```

The 🔒 gate in §0 for extracting `.docx` text (`--count-only` first, exit 10 =
tracked changes) applies whichever office skill you used to make the file.
