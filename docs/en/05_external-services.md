> English translation of [05_외부서비스_연동.md](../05_외부서비스_연동.md). The Korean original is canonical; if they differ, the Korean version wins.

# External Service Integration — Safely Handing Mail, GitHub, Asana/Notion, and Calendar to the AI

This document explains, at a beginner's level, "what you need to do so an AI agent can connect to the external
services our lab actually uses (mail, GitHub, Asana/Notion, calendar and shared sheets)."
It comes down to one thing: **connecting should be easy; sending should be careful.**

---

## 0. Introduction

An AI agent becomes truly useful when it does things like "read and organize my mailbox," "fix the code in my GitHub
repository," or "check my to-do list (Asana/Notion) and schedule calendar events."
For that, the AI has to be able to connect to these services, but "connecting it" and "connecting it safely" are different matters.

After reading this document you will know three things.

1. Why this toolkit **avoids MCP connections** and makes **REST connector scripts (`scripts/connectors/`) the
   default**, and why MCP is used only as a last resort when there is truly no alternative
2. How to **keep your tokens (access passes) safe**
3. Why the AI should **save mail and messages only as drafts instead of sending them directly**

---

## 1. If a REST connector exists, use it first

As explained in `docs/en/02_api-and-mcp.md`, MCP is "a standard plug format that connects an AI to external services,"
and it connects with one button. It is true that this is easy, but it is also true that the price is **a pathway into
your whole account that stays open all the time** — it is open even when it has nothing to do with the current task, and it is hard
to check its scope by eye or to switch it on and off per task. So this toolkit **avoids MCP connections** and sets the order
like this.

> Priority 1 (default) — For services that already have a connector (mail, GitHub, Asana, Notion, calendar, shared sheets),
>   **do not connect through MCP**; use the REST scripts in `scripts/connectors/`. For mail, GitHub,
>   Asana, and Notion, you just issue one personal token and register it. Issuing it takes a few clicks in the browser: log in →
>   account settings → "create token" (`docs/en/02_api-and-mcp.md` §5,
>   `scripts/connectors/README.md`). Calendar and shared sheets use OAuth, so a browser consent screen appears only the first
>   time, and after that `scripts/connectors/_google_auth.py` refreshes the token on its own with no extra
>   library (§4-4, `scripts/connectors/README.md` §5 and §6).
> Priority 2 (the only legitimate exception) — Exploratory work where you have to look at a web page and click through it
>   cannot be replaced by REST in the first place, so MCP (the Chrome connection) is used as is.

For a service you have finished moving to a connector, **disconnect its MCP connection right away** in the app settings —
the rule is not "leave it on just in case" but "keep open only the scope this task needs."
Disconnecting changes account settings, so the AI will not click it for you; it is something you do yourself.

> **Note**: MCP connections (connectors) in app settings like these are usually stored **per account**. That is, if you
> disconnect on one device, it is also disconnected on every other device (desktop, laptop, and so on) signed in to the same account
> — it is not a setting you have to switch off device by device. Put the other way around, you cannot
> say "turn it on for just this task on only one device," so judge the timing of switching it on and off
> on an account-wide basis.

> **Summary**: MCP is not "the default you use because it is convenient"; it is **the fallback for when you cannot build
> a REST connector**. If a service already has a REST connector, do not connect it through MCP — only for services without one
> do you use the MCP button as an exception, until a connector exists.

### ⭐ A trap that really happened — when the "preview" ends without confirmation

The MCP tools of some services split an operation into two steps — first they create a "preview," and the change takes effect only when you press the
confirm button on screen. Depending on the kind of screen/session you are using, that confirm click can be skipped, and in that case the AI
replies "I created the preview," but **in reality nothing has been created** — a silent failure that looks like success
on the surface.

This kind of trap shows exactly why REST connectors come first. A REST connector's write operation has
no "stuck halfway at a preview" state — if you do not add `--write`, nothing happens for certain, and if you add it, it runs
for certain. The key advantage is that there is no ambiguous middle ground.

If you really have to use an MCP "create"-type tool, always query the list/search again right after creating to confirm
it actually took effect — do not trust the "succeeded" wording of the reply.

---

## 2. Keeping tokens and passwords safe

We reuse the analogy from earlier.

> **Token / API key / password = access pass**

The reason you must not handle an access pass carelessly is clear — whoever picks it up can walk in and out of the building under your name.
Just follow the principles below.

- **Do not paste tokens into the chat window.** Do not type a token string straight into the conversation, as in "connect using this token."
  The connection should be made through the app's "Connect" button or a dedicated settings screen.
- **Do not put tokens in code or commits.** If you write a token directly into a script and upload that file to GitHub,
  anyone in the world can see it. A token accidentally pushed to a public repository is commonly **scanned and abused automatically within minutes**.
- **Keep tokens in the app's secure storage.** If you use the app's "Connection" feature, the token is stored in an encrypted place.
  Do not write a token in a separate text file and leave it on the desktop or in a shared folder.
- **If it leaks, revoke it immediately (rotate/revoke).** If a token was exposed by accident, invalidate that token in the service's settings and issue a new one.
  The principle is "lock the door before anyone can abuse it."

### Why this toolkit's `config/credentials.json` is safe

If you decide to use REST connectors (§1), you have to store the tokens somewhere. This repository
solves the problem by splitting it into two files: `config/credentials.json` (the real file filled with personal values) and `config/credentials.example.json`
(an empty template, structure only, no values).

- **`credentials.json` never goes up to the remote (GitHub).** Its name is listed in both `.gitignore` and
  `.distignore` (the exclusion list for the public distribution), so both the git commit path and
  the public distribution path are blocked. If you search the whole repository history with `git log`, you can confirm
  that this file was never committed — it is not that it was uploaded once by mistake and
  deleted later; it was never uploaded in the first place.
- **Only `example.json` is on the remote.** Every value in it is just a placeholder such as `ENV:SCITK_XXX_TOKEN`,
  so it is safe to upload. Do not write real values directly into this example file — the moment you do, they go to the remote.
- **Environment variables take priority.** Each connector script looks at the environment variable (`SCITK_GITHUB_TOKEN`
  and so on) first, and reads `credentials.json` only when it is missing. Instead of writing a value directly into `credentials.json`,
  write something like `"token": "ENV:SCITK_GITHUB_TOKEN"` so the token value itself is not left in
  any file, which is safer (if you already have a logged-in `gh` CLI, you can also reuse its token
  as a shell environment variable — there is no need to copy it into a file).
- **In short**: "do not write it in the code" alone is not enough. Taking the file that holds the values out of the very repository
  where that code gets committed — that is what this structure does.

### Be especially careful with GitHub — the original repository (fork) problem

Some lab code is made by "copying (forking)" someone else's public repository and modifying it for our own use.
In that case the repository may still carry a link to the "original (upstream)."

- **Risk of accidentally making unpublished research public**: the original repository is usually public to the whole world.
  If you accidentally push your changes (research code and data not yet published) to the original side, the unpublished research can be exposed as is.
- **Principle**: push your work **only to your own copy (fork)**. The AI does not push to the original repository on its own;
  that happens only after a person explicitly confirms "yes, it's OK to push this to the original."
- It is fine if you don't know all this — a safely configured AI agent automatically stops and asks when it encounters an operation that pushes to the original repository.
  The only thing to remember from this document is that "pushing to the original always gets one more confirmation."
- The general rule for public repositories is the same: **never put unpublished research, personal information, or credentials in a public repository.**

---

## 3. ⭐ Outgoing actions stop at the draft — do not send automatically

**This is the most important principle in this document.**

Sending an email, registering a to-do in Asana, inviting other people to a calendar event — these are all **"actions that leave your hands and reach someone else."**
Once they go out, they are hard to undo. A sent email cannot be recalled, and an assigned-task notification may already have popped up on the other person's phone.

So the principle is:

> **The AI only creates drafts (Drafts) / saves to the drafts folder, and does not press the send button.**
> **You check the content, and if you want to send it, you press it yourself at that point.**

Concretely:

- **Mail**: the AI writes a reply or a new email and **saves it to the drafts folder**. You open it, check it, and press "Send" yourself.
- **Registering to-dos in Asana/Notion**: for tasks that are actually assigned to other people, or comments that others will see, the AI first shows the content and gets your confirmation.
- **Calendar invitations**: an event only you will see can be registered right away, but **an event that invites other people** (adding attendees) proceeds after confirmation.
- **Deleting shared data**: deleting data from the lab's shared sheets or shared folders is also a "hard-to-undo action," so it gets confirmation first.

### Why do it this way?

- Actions that go outside **cannot be undone.** A wrongly sent email may already have been read by the recipient.
- However well the AI wrote it, **a person pressing the final send button** gives one more chance to catch mistakes.
- Following just this one principle — "the AI does not press the send button in place of a person" — prevents most accidents.

---

## 4. Guide by service

### 4-1. Mail (school/work mail + personal mail)

Labs usually use two kinds of mail — work mail provided by the school/organization (for example, an organization-specific mail system)
and personal mail (for example, Gmail). The principle is the same for both.

- **Connection**: use `scripts/connectors/mail_connector.py` (IMAP/SMTP). Issue an app password for your mail and
  register it with `python scripts/connectors/register_token.py mail --account work` (or
  `personal`), or register it through an environment variable (`SCITK_MAIL_WORK_PASSWORD` and so on) — that's all.
  To be guided through the issuing screen with Chrome, see `docs/en/13_getting-tokens-via-chrome.md` §5; for the detailed
  structure, see `scripts/connectors/README.md` §1. Once you've decided to use the connector, you can disconnect that mail service's MCP
  connection.
- **Reading (search, viewing)**: reading and organizing your own inbox is a safe task — the AI can do it right away.
- **Writing (replies, new mail)**: the AI writes a draft and **saves it to the drafts folder** (the `draft`/`reply`
  subcommands never call SMTP at all). You check it and send it yourself.
- To avoid mixing up school/work mail and personal mail, make the AI ask first whenever "which account should this mail be sent from" is ambiguous.

### 4-2. GitHub (code repositories)

- **Connection**: use `scripts/connectors/github_connector.py`. Issue a minimum-permission token (Personal Access Token)
  in your GitHub account settings and register it through the `SCITK_GITHUB_TOKEN` environment variable.
  Follow the principles in chapter 2 above for the token you issue (do not paste it into the chat window, do not put it in code).
  Once you've moved to the connector, you can disconnect the GitHub MCP connection.
- **Reading (viewing code, checking issues)**: a safe task — it can be done right away.
- **Writing (commits, pushes, creating PRs)**: pushing to your own copy (fork) or your own branch is generally fine, but
  **anything that goes directly to the original repository (upstream) or the main/master branch** proceeds only after confirmation.
- **Check public or private**: if you are unsure whether a repository is public or private, check first so that you never upload unpublished research material.

### 4-3. Asana / Notion (task and document management)

- **Connection**: use `scripts/connectors/asana_connector.py` / `notion_connector.py` (and
  `notion_db_connector.py`). Issue a personal token in each service's settings and
  register it as `SCITK_ASANA_TOKEN` / `SCITK_NOTION_TOKEN`. Once you've moved to the connector, you can
  disconnect the Asana/Notion MCP connections.
- **Reading (checking my to-dos, searching documents)**: a safe task — it can be done right away.
- **Writing (creating/editing to-dos, editing documents)**: documents that are personal notes only you see, or drafts, are fine to create right away.
  But actions that affect other people, such as **assigning a to-do to someone else or commenting on a document others see**,
  need you to show the content first and get confirmation.
- If the lab has rules for registering documents/to-dos (which board gets what), telling the AI those rules too reduces mistakes.

### 4-4. Calendar / shared spreadsheets

- **Connection**: use `scripts/connectors/calendar_connector.py` / `sheets_connector.py`.
  Like the other connectors, they work with only the standard library (`urllib`), so no separate installation is
  needed. Authentication is OAuth — a browser login consent screen appears only the first time, and after that
  `scripts/connectors/_google_auth.py` refreshes automatically with the refresh token, with no library. The setting keys, as before, are
  `google.oauth_client_path` / `google.token_cache_path` in `config/credentials.json`. If you already have a Google token file in the standard format
  (`access_token`/`refresh_token`/`expiry_date`), just point
  `token_cache_path` at that file — you do not need to issue a new one.
  Once you've moved to the connector, you can disconnect the calendar/sheet MCP connections.
- **Reading (checking events, querying sheet data)**: for the calendar, `calendars` (list)/`list`/`agenda`;
  for sheets, `info`/`read` — they run right away with no flag. These are safe tasks.
- **Writing (registering events, appending sheet values)**:
  - The calendar has only `add-event` (requires `--write`) — edit and delete subcommands are intentionally
    absent. Adding attendees with `--attendee` is **outward** (invitations are sent to other people), so
    a warning appears in advance at the dry-run stage. For an event that invites other people, first show what will be registered
    and get confirmation.
  - Sheets have only `append` (requires `--write`) — it is **append-only** and there is no update/delete.
    Overwriting a shared sheet makes the values other people entered vanish irrecoverably, so the design
    deliberately has no subcommand that could touch existing values in the first place.
- For detailed subcommands and options, see `scripts/connectors/README.md` §5 (calendar) and §6 (sheets) —
  they are not duplicated here.

---

## 5. What to ask about, and what to just do

The criterion is simple: **"is it only reading my own stuff, or does it affect other people?"**

| OK to just do (reading, internal use) | Needs confirmation (writing, external/shared use) |
|---|---|
| Reading and searching my inbox | Sending mail (→ stop at a draft) |
| Viewing my GitHub repositories/issues | Pushing to the original repository or main branch |
| Checking my Asana/Notion to-dos | Assigning a to-do to someone else, commenting on a public document |
| Checking my calendar events | Registering an event that invites other people |
| Reading and analyzing shared sheet data | Editing or deleting shared sheet values |
| Writing my own personal notes/drafts | Editing material other people see |

In a word: **reading is always fine; anything that goes out to others or is hard to undo always gets confirmation or stops at a draft.**

---

## 6. Codex tips

- The same principles apply when other AI coding tools, Codex included, are connected to GitHub, mail, calendar, and so on:
  **if a REST connector exists, use it first; if not, use an MCP/token connection; and hard-to-undo actions like
  sending, deleting, or assigning always go through human confirmation.**
- In particular, the "do not push to the original (upstream) repository" principle for GitHub must be followed the same way whichever AI tool you use.
  A different tool does not change the principle.
- If you use several AI tools together, writing rules such as "mail always stops at a draft" and "pushing to the original repository only after confirmation"
  into the `AGENTS.md`/`CLAUDE.md` explained in `docs/en/04_giving-ai-rules.md` keeps the principles in place even when the tool changes.

---

## 7. One-line summary

- **Connection** = for mail, GitHub, Asana, Notion, calendar, and sheets, always use the
  **REST connectors in `scripts/connectors/` first**, and once switched, disconnect that service's MCP. MCP only as a last resort, for
  exploratory web work that REST cannot replace
- **Tokens/passwords** = access pass — never expose them in chat windows, code, or public repositories; keep them only in the app's secure storage
- **GitHub original (upstream) repository** = push only to your own copy (fork); anything going to the original is always confirmed by a person
- **⭐ The most important principle**: for anything that **goes out externally**, such as mail, task assignment, or calendar invitations, create only a draft, and you always send it yourself
- **Rule of thumb** = reading (checking your own stuff) proceeds as is; writing (affecting others) gets confirmation or stops at a draft
