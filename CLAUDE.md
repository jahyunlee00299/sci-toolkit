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

## Repository language — English, with named exceptions

**Everything written in this repository is in English**: code, comments,
docstrings, CLI output, error/log messages, test names and fixture prose,
Markdown docs, `SKILL.md` bodies, and commit messages. This package is
distributed to users and parsed by agents that do not share one native
language, so a single register keeps it readable and reviewable everywhere.

This rule governs the *repository's own text*. It does not change how you
talk to the user: reply in whatever language the user writes in (see
`AGENTS.md` §Language).

### Korean is kept — only where it is data, not prose

Five categories carry meaning that English cannot: translating them either
changes behavior or defeats the text's purpose. Leave them in Korean and do
not "clean them up":

1. **Router trigger phrases.** `한국어 트리거 — …` lines, and Korean phrases in
   a `SKILL.md` frontmatter `description:` or `triggers:` list. These are how
   a Korean-language request matches the skill. Translate them and the skill
   stops firing.
2. **Korean-language detection logic.** Korean literals used as patterns —
   particles, counters, honorifics, josa — e.g. the regexes in
   `scripts/feedback_sanitize.py` that catch Korean PII, and the taxonomy in
   `skills/avoid-ai-writing/korean-tells.md` whose entire subject *is* Korean
   text. The Korean here is the input alphabet, not commentary.
3. **Test fixtures that exercise those detectors.** A Korean sample string in
   a test exists to prove a Korean pattern matches. Keep it, and write its
   surrounding docstring/comment in English.
4. **Quoted evidence.** A user's or reviewer's exact Korean wording, quoted
   because the wording itself is the finding. Quote verbatim; put the
   explanation around it in English.

5. **Beginner onboarding docs — the whole `docs/` folder.** `docs/00_시작하기.md`
   through `docs/14_터미널_읽기좋게.md` are written for lab members who have
   never used an AI agent, in plain Korean with everyday analogies. Their
   reader is a Korean-speaking beginner, so English would defeat the document's
   purpose. Korean filenames included — they are referenced by path from
   `README.md` and from code, so renaming them breaks those links. Reference
   docs *about* the repo's machinery (`docs/feature-connectivity-ledger.md`)
   are not onboarding docs and follow the English rule.

Everything outside those five is prose and gets translated.

### How to translate, and how to prove it

- **Translate meaning, not words.** These docstrings carry measured findings
  ("실측", dated observations, why a naive fix failed). Preserve the finding
  and its date; do not compress it into a generic summary.
- **Never blind find-replace.** Decide per occurrence whether it is prose or
  one of the five exceptions above. A regex sweep cannot tell them apart.
- **Prove it.** `python doctor.py` must end in PASS (it runs every self-test,
  the SHA256SUMS check, and the SENTINEL scan), and
  a translated file's behavior must be unchanged — translation touches
  comments/docstrings/prose only. If a test's expected output was Korean and
  a translation would change it, that literal was category 3 — revert it.
- **Watch for checks that go quiet.** A verifier that finds its target by
  Korean regex stops matching once the text around it is English, and some
  skip silently rather than fail. Measured 260828: translating README/
  QUICKSTART left 5 of the 8 count checks in `tests/test_doc_counts.py`
  matching nothing while the suite still reported pass. After translating a
  file, grep for anything that greps *it*, and confirm the pattern still
  fires — a green test is not proof the check ran.

## Safety baseline (do not override)

The single statement of the safety rules is **`AGENTS.md` §7** (secrets,
destructive git, recursive deletes, cloud-sync folders, PII, ask-before /
proceed-by-default). It is not repeated here so that it cannot drift. Under
Claude Code the four command-level guards are also enforced mechanically by the
scripts in `hooks/` (wired in `hooks/hooks.json` when this package is loaded
as a plugin); the exact command patterns each guard matches are listed in
`CODEX.md` §1–4. Treat the hooks as a backstop, not a substitute for reading
§7 before a destructive or outward-facing action.

## Working style

- Read a file before editing it; don't guess its contents or explore with
  shell commands when a direct read would answer the question.
- New code should stay small and single-purpose (see `AGENTS.md` §1 for the
  full SOLID guidance). Split a script if it mixes unrelated concerns.
- One-off / throwaway scripts belong in a scratch or `scripts/oneshot/`
  folder, not scattered at the project root.
- If you hit a real problem while working on a local branch (a doc that lags
  the actual code, a broken assumption, a missing connector, anything worth
  someone else knowing) — file it as a GitHub issue rather than only fixing
  it silently or leaving a comment in the diff. Assign it to whoever found
  it (the person working the branch), not automatically to the repo owner.

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
