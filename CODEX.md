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

> **Note (measured 2026-08-16 and 2026-08-21, Codex CLI 0.147.0).** Earlier
> versions of this file said Codex had no hook mechanism at all. It does, and
> the guards in `hooks/` can be wired into it — but only through an adapter,
> because Codex ignores the exit-2 contract they are written against. See
> [§ Codex-native enforcement](#codex-native-enforcement-hooks-and-rules) below
> for the measured contract and the wiring procedure.

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

> To get these enforced rather than merely documented, wire the guards into
> Codex's own hook mechanism — see
> [§ Codex-native enforcement](#codex-native-enforcement-hooks-and-rules) for
> the measured contract and the three-step procedure.
>
> Until that is set up, or to check a single command by hand, run the chain
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
subsystems** and they behave differently: rules block on their own, hooks block
only through the adapter described below.

Everything below was measured against **Codex CLI 0.147.0**: the rules
subsystem on 2026-08-16, the hooks contract on 2026-08-21. The hook measurements
are recorded in [issue #5](https://github.com/jahyunlee00299/sci-toolkit/issues/5)
— cite that comment rather than re-deriving them.

> **Release-note review, 2026-08-22 (0.147.0 → 0.149.0).** The five measured
> facts below were re-checked against the 0.148.0 and 0.149.0 release notes.
> None of the five is contradicted — no note touches the exit-2 contract, the
> global-only load path, the payload shape, the trust gate, or
> `${CLAUDE_PLUGIN_ROOT}`. **The contract stands as written.** Four changes
> extend it, and one is a live hazard:
>
> - 🔴 **Hooks now run with the captured session environment** (0.149.0,
>   [#39314](https://github.com/openai/codex/pull/39314)). A guard that reads an
>   environment variable now sees the value captured at session start, not the
>   value at fire time. The guards in `hooks/` are unaffected: they read the
>   command from stdin, and the only variables they touch (`GUARD_FIELDS`,
>   `GUARD_HAVE_*`, `REASON_FILE`) are exported by the guard itself moments
>   before it reads them, within the same process. The hazard is for a *wrapper*
>   that exports a variable mid-session and expects a later hook to observe it —
>   that now silently reads the stale value.
> - **Hooks can run asynchronously and invoke MCP tools** (0.148.0,
>   [#37533](https://github.com/openai/codex/pull/37533),
>   [#38705](https://github.com/openai/codex/pull/38705); enabled in sessions by
>   0.149.0 [#39296](https://github.com/openai/codex/pull/39296)). An async hook
>   cannot block — its decision arrives after the command has run. **Keep every
>   guard in this package synchronous.**
> - **A `SessionEnd` hook event exists** (0.145.0,
>   [#33895](https://github.com/openai/codex/pull/33895)), matching the event
>   list below. Timed-out hook process trees are now terminated (0.148.0,
>   [#37527](https://github.com/openai/codex/pull/37527)) — a guard that hangs
>   is killed rather than wedging the session.
> - **`codex exec --full-auto` was removed** in 0.147.0
>   ([#36054](https://github.com/openai/codex/pull/36054)); use
>   `--sandbox workspace-write`. Nothing in this package passed that flag.
> - Sandbox restrictions now **fail closed** for denied or unreadable paths
>   (0.148.0), and Windows sandbox ACL update failures now propagate instead of
>   passing silently (0.149.0,
>   [#39279](https://github.com/openai/codex/pull/39279)). Both make a
>   misconfigured boundary louder, which is the direction you want.
>
> Re-measure rather than trusting this paragraph if you are on 0.150.x or
> later: the permission subsystem was under active rework across this window
> (0.149.0 began *rejecting* obsolete app-server permission-profile fields and
> lossy legacy permission projections, where earlier versions ignored them).

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

### Hooks — measured contract

Codex fires `PreToolUse` hooks, and this package's guards can read its payload
unchanged. But **Codex does not honour the exit-code contract they are written
against**, so wiring them in as-is gets you guards that run and never block.
The five facts that matter:

| # | Fact | Consequence for this package |
|---|---|---|
| (1) | Hook config loads from **global `~/.codex/hooks.json` only** | A project-local `hooks.json` or `.codex/hooks.json` is ignored — silently |
| (2) | stdin payload is **identical to Claude Code's** | The guards parse `tool_name` / `tool_input` as-is; no translation needed |
| (3) | **`exit 2` does not block** — the command runs anyway | Every guard here needs the adapter below |
| (4) | Without `--dangerously-bypass-hook-trust`, hooks are **silently skipped** | Headless runs need that flag or they get no enforcement and no warning |
| (5) | `${CLAUDE_PLUGIN_ROOT}` is **not injected** | `~/.codex/hooks.json` must use absolute paths |

**(1) Load path.** Only `~/.codex/hooks.json` is read. A project-local
`hooks.json`, a `.codex/hooks.json` in the project, and a `hooks = "<path>"`
key in `config.toml` were each measured and each failed — the `config.toml`
key is a struct (`HooksToml`), not a path, and the string form belongs to
plugin manifests. `codex features list` reports `plugin_hooks removed`, so the
global file is the only live path. The file format is the same schema as this
package's `hooks/hooks.json`:

```json
{"hooks": {"PreToolUse": [{"matcher": "Bash|Write|Edit",
  "hooks": [{"type": "command", "command": "/abs/path/to/hook.sh"}]}]}}
```

Event names present in the binary: `PreToolUse`, `PostToolUse`, `SessionStart`,
`SessionEnd`, `UserPromptSubmit`.

**(2) Payload.** Captured verbatim:

```json
{"session_id":"...","turn_id":"...","transcript_path":"...","cwd":"...",
 "hook_event_name":"PreToolUse","model":"...","permission_mode":"...",
 "tool_name":"Bash","tool_input":{"command":"echo hooktest"},"tool_use_id":"..."}
```

`tool_name` plus `tool_input.command` — exactly what the guards in `hooks/`
already read. This is deliberate on Codex's side: the binary carries the
comment *"Claude requires `reason` when `decision` is `block`; we enforce that
semantic rule."* A command run through PowerShell still arrives as
`tool_name: "Bash"`.

**(3) Blocking — this is the one that changes the wiring.** A hook that exits 2
with a reason on stderr is **ignored**; the command executes and reports
success. Codex blocks only when the hook writes

```json
{"decision":"block","reason":"..."}
```

to **stdout** and exits **0**, which surfaces as
`Command blocked by PreToolUse hook: <reason>`.

Every guard in `hooks/` speaks exit 2. Wired in raw, they would run, detect the
violation, print their reason — and let the command through. That is a guard
producing a green light on an unchecked command, which is worse than no guard
at all. Use the adapter.

**(4) Trust gate.** Without `--dangerously-bypass-hook-trust`, `codex exec`
skips hooks entirely: no firing, no warning, nothing in the log. The tradeoff
is real and it is not symmetric — *without* the flag you get no enforcement
**and no signal that enforcement is missing**, which is the failure mode this
whole section exists to prevent. *With* it you get a warning on every run, and
hooks that actually fire. For headless automation, pass the flag. (The TUI has
its own hooks-review UI with persisted `trusted_hash` state; not measured here.)

**(5) Path expansion.** The captured environment holds only `CODEX_MANAGED_*`
variables. `${CLAUDE_PLUGIN_ROOT}`, which this package's `hooks/hooks.json`
relies on, is never set — resolve it to an absolute path when you copy the file.

### Wiring the guards under Codex

**a) Install the hook config globally.** Copy or merge this package's
`hooks/hooks.json` into `~/.codex/hooks.json`, rewriting
`${CLAUDE_PLUGIN_ROOT}` to an absolute path (fact 5). If you already have a
`~/.codex/hooks.json`, merge into its `PreToolUse` array rather than replacing
the file.

**b) Wrap every guard in the exit-2 adapter.** `hooks/_codex_json_adapter.sh`
runs a guard and translates `exit 2` + stderr into the `{"decision":"block"}`
JSON Codex acts on (fact 3). Point it at `_run_hooks_chained.sh` to get the
whole guard chain in one hook:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash|Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "sh /abs/path/to/sci-toolkit/hooks/_codex_json_adapter.sh /abs/path/to/sci-toolkit/hooks/_run_hooks_chained.sh"
          }
        ]
      },
      {
        "matcher": "Read",
        "hooks": [
          {
            "type": "command",
            "command": "sh /abs/path/to/sci-toolkit/hooks/_codex_json_adapter.sh /abs/path/to/sci-toolkit/hooks/_run_hooks_chained.sh"
          }
        ]
      }
    ]
  }
}
```

The adapter's translation table:

| Guard exits | Adapter emits | Adapter exit |
|---|---|---|
| `2` | `{"decision":"block","reason":"<guard stderr>"}` | `0` |
| `0` | nothing (or the guard's own hook JSON, passed through) | `0` |
| anything else | nothing, plus a `WARN` on stderr | `0` |

The last row is permissive on purpose: a crashed or half-installed guard must
not brick every tool call. It warns loudly instead, so a dead guard cannot
quietly pass for a working one.

`tests/test_codex_hook_adapter.py` pins this translation — including that a
reason containing quotes, Windows backslashes, non-ASCII, or newlines still
produces *parseable* JSON. That last part is not cosmetic: malformed JSON means
Codex cannot read the decision, and the block degrades back into an allow.

**c) Pass `--dangerously-bypass-hook-trust` on headless runs** (fact 4), or the
hooks will not fire and nothing will tell you.

**d) Prove it once.** Wiring is not enforcement until you have watched it
block. Run a command you know is forbidden and confirm you get
`Command blocked by PreToolUse hook: ...`:

```bash
codex exec --dangerously-bypass-hook-trust 'run: git push --force origin main'
```

You can also exercise the adapter directly, without Codex:

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"<the command>"}}' \
  | sh hooks/_codex_json_adapter.sh hooks/_run_hooks_chained.sh
# prints {"decision":"block",...} when a guard refuses; silent when it allows
```

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
