# CLAUDE.md — sci-toolkit project instructions

Claude Code automatically reads this file as project-level instructions.
This is the tool-neutral companion to `AGENTS.md` in the same folder — read
`AGENTS.md` for the fuller operating principles (code quality, verification,
number provenance, writing conventions, figure regression rules). This file
states the short version plus a few Claude-Code-specific pointers.

## Start here — route the request before doing anything

**Read `AGENTS.md` §0 (Routing) first.** It maps an incoming request to the
skill chain it must take and the gate that decides whether the work is done.
Do not pick a skill by guesswork: if the request matches a row in that table,
follow that row.

Gates marked 🔒 in §0 are enforced by a script. Run it and read its exit code —
do not judge by eye, and do not weaken a check to make it pass. If a required
file or skill does not exist in this package, say so rather than writing
instructions that point at it (`python tests/test_skill_references.py` and
`python tests/test_agents_routing.py` exist to catch exactly that).

## Safety baseline (do not override)

- Never write, print, or commit real secrets (API keys, tokens, passwords).
  Treat any `secrets.json` / `*.credentials.json` file as off-limits for
  Write/Edit. Use environment variables or a local, gitignored config file
  instead, and never hardcode a credential literal into a script.
- Never run destructive git operations (`git push --force`, `git reset
  --hard`, `git config --global`, force-deleting a branch) unless the user
  explicitly asks for exactly that operation in those words.
- Never run recursive/forced deletes (`rm -rf`, `sudo rm`, `find ... -delete`)
  without explicit user confirmation of the exact path.
- Respect cloud-sync folders (OneDrive, Dropbox, iCloud Drive, Google Drive):
  avoid recursive scans (`find`, `ls -R`, `**` globs, bulk `cat *`) over
  paths inside them — this can force every file to download from the cloud.
  Prefer reading one specific file at a time, or the provider's own API/skill
  if one is available.
- These four guards are also enforced mechanically by the hook scripts in
  `hooks/` (see `hooks/hooks.json`) when this package is loaded as a plugin —
  treat this section as documentation of what those hooks do, not a
  substitute for thinking before running a command.

## Working style

- Read a file before editing it; don't guess its contents or explore with
  shell commands when a direct read would answer the question.
- New code should stay small and single-purpose (see `AGENTS.md` §1 for the
  full SOLID guidance). Split a script if it mixes unrelated concerns.
- One-off / throwaway scripts belong in a scratch or `scripts/oneshot/`
  folder, not scattered at the project root.

## Verification gate

- Do not treat a number, fitted parameter, figure, or generated report as
  final just because a script "ran successfully." Independently re-derive
  or re-check it from the underlying data/code before reporting it (see
  `AGENTS.md` §2). This applies especially to anything a sub-agent or
  background process reports as done — re-check its actual output rather
  than trusting the self-report.

## Number single-source-of-truth (SSOT)

- Any number that ends up in a document, plot, or report should trace back
  to one canonical script/raw-data source — not a hand-typed copy from a
  previous message or chat transcript. See `AGENTS.md` §3.

## Where to look next

- `AGENTS.md` — full generic agent operating rules (tool-agnostic).
- `docs/` — beginner-friendly setup guides (installation, API/MCP basics,
  token/cost awareness, giving an AI agent rules).
- `README.md` / `QUICKSTART.md` — what this package contains and how to
  install only the skills you need.
- Each `skills/<name>/SKILL.md` — the authoritative usage guide and trigger
  phrases for that specific skill; prefer it over general knowledge for any
  field-specific convention.
