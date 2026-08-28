# External service connectors

A collection of connectors for driving mail, GitHub, Asana, Notion, calendar,
and shared sheets from the command line. Design principles follow
[`docs/05_외부서비스_연동.md`](../../docs/05_외부서비스_연동.md) and
[`AGENTS.md §9`](../../AGENTS.md) — **reading is free, outbound stops at a
draft.**

> **Default policy — avoid MCP**: for the six services below, **use these
> connectors instead of connecting via MCP (the app-connection button).**
> MCP opens a standing, account-wide channel, while a connector only touches
> the scope the running command actually requested. If you switch to a
> connector, **turn off** that service's MCP connection in app settings right
> away (that's an account-setting change, so it's something you do yourself).
> Keep MCP as a last resort, only for tasks that truly can't be replaced by
> an API, like browser exploration.
>
> As of 260816, calendar and shared sheets also have connectors, so the
> **"service with no connector" exception no longer exists.** The two
> Google services need a one-time OAuth consent (§5·§6), but after that they
> run on stdlib alone, same as the rest.

> These scripts are **templates that don't need to know your real account.**
> No credentials live in the code — they're read from
> `config/credentials.json` (or environment variables) at runtime. Real keys
> never ship in the distribution or a commit (excluded via
> `.distignore`/`.gitignore`).

## 0. Setup — credentials

1. Copy `config/credentials.example.json` to `credentials.json` in the same
   folder
2. Fill in your account info. For real keys/passwords, prefer the
   `"ENV:name"` form and inject via environment variable:
   ```bash
   export SCITK_MAIL_WORK_PASSWORD='...'      # mail app password
   export SCITK_GITHUB_TOKEN='...'            # GitHub PAT (least privilege)
   export SCITK_ASANA_TOKEN='...'
   export SCITK_NOTION_TOKEN='...'
   ```
3. Verify the setup (values are masked in output):
   ```bash
   python scripts/connectors/_credentials.py
   ```

## 1. Mail — `mail_connector.py` (draft-first)

```bash
# Read (safe)
python mail_connector.py list  --account work --n 10
python mail_connector.py read  --account work --uid 1234

# Compose a draft → saved only to Drafts. Never sends automatically.
python mail_connector.py draft --account work --to a@b.com --subject "Subject" --body "Body"
python mail_connector.py reply --account work --uid 1234 --body "Reply body"

# Actually sending = one single path. Requires --send flag + typing 'SEND' in the terminal as a second confirmation.
python mail_connector.py send  --account work --to a@b.com --subject "Subject" --body "Body" --send
```
- `draft`/`reply` never call SMTP at all → sending is impossible, only a
  draft gets saved.
- `send` is refused without `--send`, and also refused in a non-interactive
  (piped/automated) context.
- School/work mail = `--account work`, personal = `--account personal`.

## 2. GitHub — `github_connector.py` (read-first, fork-guard)

```bash
# Read
python github_connector.py issues --repo owner/name
python github_connector.py prs    --repo owner/name
python github_connector.py repo   --repo owner/name      # shows fork status/upstream

# Creating a PR = always a draft, requires --write. Refused if the target is upstream.
python github_connector.py open-pr --repo my-fork/name --head feat --base main \
    --title "..." --body "..." --write
```
- A PR is **always created as draft**, and there is **no merge subcommand**.
- Refused if the target repo is the fork's original (upstream) — only push
  to your own fork.

## 3. Asana — `asana_connector.py` (read-first)

```bash
python asana_connector.py me
python asana_connector.py tasks --workspace <gid>
# Creating a task = --write. Assigning to someone else (--assignee) triggers an outward-action warning.
python asana_connector.py add-task --workspace <gid> --name "..." --notes "..." --write
# Comment (plain by default; --html auto-validates formatting)
python asana_connector.py add-comment --task <gid> --text "..." --write
# Subtask (/tasks/{parent}/subtasks)
python asana_connector.py add-subtask --parent <gid> --name "..." --write
```
- **Automatic formatting correction**: `--html` comments/`--html-notes`
  descriptions enforce Asana's rules — auto-wraps in `<body>`, forbids
  `<p>`, uses `&#10;` for line breaks, rejects `→`. Non-ASCII text stays
  intact via `ensure_ascii=False`. (Resolves the old "comment/subtask
  formatting looks wrong" problem.) Details →
  [`docs/08_아사나_연동_가이드.md`](../../docs/08_아사나_연동_가이드.md)

## 4. Notion — `notion_connector.py` (read-first)

```bash
python notion_connector.py search --query "keyword"
python notion_connector.py page   --id <page_id>
# Append a paragraph to a page = --write (append-only, no delete/archive).
python notion_connector.py append --page-id <id> --text "..." --write
```

## 5. Calendar — `calendar_connector.py` (read-first)

```bash
# Read (safe)
python calendar_connector.py calendars                    # list accessible calendars
python calendar_connector.py agenda --days 7              # grouped by day
python calendar_connector.py list --calendar primary --days 30

# Creating an event = --write. Adding attendees sends invites, so a warning shows first.
python calendar_connector.py add-event --summary "Meeting"     --start 2026-08-20T14:00:00 --end 2026-08-20T15:00:00 --write
```
- A date alone (`2026-08-20`) creates an all-day event; adding a time
  creates a timed event.
- `--attendee` is **outward** — invitations go out on someone else's
  calendar. dry-run tells you up front how many people it would go to.
- **There is no edit/delete subcommand.** This tool should be structurally
  incapable of the mistake of deleting someone else's event.

## 6. Shared sheets — `sheets_connector.py` (append-only)

```bash
# Read (safe)
python sheets_connector.py info --sheet <ID>              # tab list, size
python sheets_connector.py read --sheet <ID> --range "Sheet1!A1:D20"

# Adding a row = --write. Existing cells are never touched.
python sheets_connector.py append --sheet <ID> --range "Sheet1!A:D"     --row 'a,"b,c",d' --write
```
- The sheet ID comes from the URL: `docs.google.com/spreadsheets/d/<ID>/edit`
- `--row` follows CSV rules — wrap a value in `"..."` if it contains a comma.
- **`update`/`delete` are not provided.** Overwriting an existing cell in a
  shared sheet erases whatever value someone else entered, with effectively
  no way back (same reasoning as the Notion connector being
  additive-only). Editing an existing value is a human's job, done in the
  browser.

### Google auth — browser only the first time, automatic after that

Unlike the other connectors, Google uses OAuth, so there's one extra
token-issuance step. But **once a refresh token is obtained, it auto-renews
from then on with no library needed**, so day-to-day use is identical to the
other connectors (`_google_auth.py`, stdlib only).

Fill in the two `google` entries in `config/credentials.json`:

| Key | What it is |
|---|---|
| `oauth_client_path` | path to the OAuth client JSON obtained from Google Cloud Console |
| `token_cache_path` | path where the issued token is stored (default `~/.sci-toolkit/google_token.json`) |

The token file just needs to be in Google's standard format
(`access_token`/`refresh_token`/`expiry_date`) — **if you've already
generated a Google token with another tool, just point this at that file's
path; there's no need to issue a new one.**

Initial issuance requires browser consent, so this package does not
automate it (a script clicking through the consent screen on someone's
behalf shouldn't happen). Create an OAuth client in the console and consent
once with the scopes you need:

- Calendar read: `.../auth/calendar.readonly` · up to event creation:
  `.../auth/calendar.events`
- Sheets read: `.../auth/spreadsheets.readonly` · up to row append:
  `.../auth/spreadsheets`

If you only need to read, give it just the readonly scope — even if the
token leaks, it can't write.

Verify setup:
```bash
python scripts/connectors/_google_auth.py     # prints masked values if the token is valid
```


## Safety summary

| Action | Default | Actual execution condition |
|---|---|---|
| Read (list/read/issues/prs/tasks/search) | runs immediately | — |
| Mail draft | saved as draft | — (not a send) |
| Mail send | **refused** | `--send` + typing `SEND` in the terminal |
| GitHub PR | dry-run | `--write` (+ always draft, upstream refused) |
| Asana/Notion write | dry-run | `--write` |
| Calendar event creation | dry-run | `--write` (outward warning first if attendees present) |
| Sheet row append | dry-run | `--write` (append-only — existing cells untouched) |
| Delete/merge/archive/cell edit | **none** | not provided |

### dry-run runs without a token (one exception)

A write command called without `--write` shows the payload that would be
sent **even with no token**. You can check "what would go out" before ever
issuing a token.

```bash
# Works even without a token — just prints the payload
python github_connector.py open-pr --repo me/r --head feat --base main --title "..."
```

But **dry-run is not a rehearsal.** It only shows the payload — it does not
tell you whether that request would be accepted, whether the target exists,
or whether it passed a safety check. If a check couldn't run because there's
no token, the connector states that in the preview — don't read silence as
"the check passed." (E.g., `open-pr`'s fork/upstream check needs a
repository lookup, so with no token it's performed at `--write` time
instead.)

**Exception — `notion_db_connector.py add-row`** requires a token even
without `--write`. This command's preview is only meaningful if it compares
property names/types against the actual DB schema — showing a payload built
without that comparison could be mistaken for something already validated.

> Regression test: `python tests/test_connectors.py` (no credentials or
> network required). `doctor.py` runs it automatically.
