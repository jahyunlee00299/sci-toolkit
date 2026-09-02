<!-- Moved verbatim from AGENTS.md on 2026-09-02 so that AGENTS.md stays under the 32 KiB that Codex reads (`project_doc_max_bytes`). AGENTS.md keeps a stub with the rules in force; this file is the full text. -->

## 9. External Service Connections (mail, GitHub, Asana, Notion, calendar, shared sheets)

Connecting the agent to external services (mail, code host, task/doc
managers, calendar, shared spreadsheets) adds power but also the ability to
take OUTWARD, hard-to-undo actions. These rules govern how to do it safely;
they extend §7 (Safety Baseline).

### Credentials & connection

- **Avoid MCP-style always-on connections.** For any service that already
  ships a REST/API connector script (`scripts/connectors/`) — mail, GitHub,
  Asana, Notion, calendar, shared sheets — use that connector with a scoped
  personal token (or, for calendar/sheets, a one-time OAuth consent) instead
  of the tool's built-in "connect" button. A connector invocation only
  touches what that one command asked for; an MCP connection stays open to
  the whole account for every future turn regardless of whether the current
  task needs it. Treat MCP as a last resort: only for a service that has no
  connector yet, or for exploratory browser work that has no API
  equivalent.
- Once a service has been switched to its connector, disconnect that
  service's MCP connection in the app's own settings (a human action, not
  something the agent does on its own) so the standing access shrinks to
  what's actually in use.
- When a token IS required (e.g. a code-host personal access token), store
  it in a secrets store or the tool's credential manager, NEVER inline in
  code, chat, commits, or a plaintext file in the repo. Never echo a token
  into visible output.
- Treat tokens like keys: scope them minimally, rotate/revoke on any
  suspected leak. Do not commit anything matching a secret pattern (check
  the diff before committing — this restates §7).

### ⭐ Draft-first for outward actions (the core rule)

- **Anything that goes OUT to other people is draft-first by default:
  compose it and leave it in a draft / staging state; do NOT send/publish/
  submit it.** The human reviews and performs the final send themselves.
  This applies to: email (leave in Drafts, never auto-send), posting/
  commenting on a task or doc, sending a calendar invite to others, opening
  a pull request.
- State clearly when you've left something as a draft and that the human
  must send it. Do not press "send" on a person's behalf unless they
  explicitly, unambiguously ask you to send *this specific* message now.
- Prefer composing via the service's own draft mechanism (a real Drafts
  folder) so the human sends from the normal UI, rather than staging text
  somewhere non-standard.

### The `--write` contract (what a dry-run does and does not prove)

Every write-capable connector command refuses to act without `--write`; it
prints the exact payload instead. Two consequences worth stating, because
getting either backwards is how a preview turns into a surprise:

- **A dry-run runs without credentials.** Previewing a write does not require
  a token, so you can inspect what *would* be sent before any token exists.
  The one deliberate exception is a command whose preview must be checked
  against live schema to mean anything — there, the connector says so and
  asks for the token rather than showing an unvalidated payload.
- **A dry-run is not a rehearsal.** It shows the payload; it does not prove
  the request would be accepted, that the target exists, or that a safety
  check passed. When a connector could not run one of its guards without a
  token, it says so in the preview — read that line rather than assuming
  silence means "checked and fine."

Never remove or weaken a `--write` gate to make an automation smoother. If a
flow needs many writes, have the human approve the batch — do not make the
gate disappear.

### Reading vs. writing vs. sending

- **Reading** your own inbox / repo / task list / sheet / calendar = safe,
  proceed without asking.
- **Writing to your own space** that's easily reversible (a draft, a local
  branch, a scratch row) = proceed, state what you did.
- **Sending outward, deleting shared data, assigning work to a real
  person, force-pushing** = confirm first (and for outward messages,
  draft-first per above).

### Code host (e.g. GitHub) specifics

- Never push unpublished research, private data, or personal info to a
  public repository.
- If a repo has an upstream/original remote (i.e. it's a fork), treat any
  push or PR to that upstream as requiring explicit human confirmation
  EVERY time — an accidental push there can expose unpublished work.
  Default pushes go to your OWN fork/origin, on a feature branch, never
  directly to a shared main/master.
- Pull requests are draft-first: open them for review; do not merge to a
  shared main branch on your own authority.

### Shared spreadsheets / documents

- A shared sheet/doc is multi-person data: prefer additive, reversible
  edits; never bulk-delete or restructure a shared sheet without explicit
  confirmation and ideally a backup/snapshot first.
- When a number will be read by others, it still follows §3 (Number SSOT)
  — trace it to its source, don't hand-type.

These rules exist so the agent can safely touch external systems without
ever taking an irreversible outward action on a human's behalf by
surprise.
