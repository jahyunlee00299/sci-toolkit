> English translation of [13_토큰_발급_Chrome으로_받기.md](../13_토큰_발급_Chrome으로_받기.md). The Korean original is canonical; if they differ, the Korean version wins.

# 13. Getting Tokens the Easy Way with Chrome (Claude Code + Chrome Extension)

> In one line: **Claude takes you right to the correct settings screen, but clicking the "Generate" button and copying the
> value are always done by you.** Claude never reads or stores the token value on your behalf.

`docs/07_notion-guide.md` and `docs/08_asana-guide.md` explain how to find each menu by hand.
If Claude Code has a Chrome MCP connection, you can cut down on the effort of hunting for menus — but what
matters is **how far to automate and where the human has to take over.**

---

## 1. Principle — why Claude doesn't see the token value

- A GitHub/Notion/Asana token is shown on screen **only once**, right after it is generated, and can't be viewed again.
- If Claude reads the screen and repeats that value in chat, **at that moment the token is left in the conversation history**
  — which is, in effect, the same as the "pasting a token into the chat window" that `docs/05_external-services.md` §2 forbids.
- Pressing the "generate token" button is also **an action that changes account settings**, so it isn't the kind of thing
  Claude should press on its own.
- **Claude can't judge whose account is logged in.** A screenshot shows whether the page is logged in,
  but whether "it's OK to issue a token from this account" is always your call — if it's a service
  you're using for the first time, log in with your usual own account on the login screen, or create a new
  one if you don't have one (§3, step 2). The token is stored in `config/credentials.json`, and this file is
  **separate on each machine** and is not shared with other PCs — so even if you think you picked the wrong account, you can just
  delete that file and issue again.

So the roles are divided like this.

| Step | Who does it |
|---|---|
| Check the login state, navigate to the exact settings page | Claude (Chrome MCP) |
| Check that the scope/permission checkboxes are selected as intended | Claude checks via screenshot + guides you |
| **Click the "Generate/Create" button** | **You** |
| **Copy the token value** | **You** |
| Register the value in `credentials.json` | You (run `register_token.py` — paste once, not visible on screen) |
| Confirm that it was registered (value masked) | Claude (`_credentials.py`) |

---

## 2. Shortcut URLs by service

| Service | Shortcut URL | Notes |
|---|---|---|
| GitHub (classic PAT) | `https://github.com/settings/tokens/new?scopes=repo&description=sci-toolkit` | The `scopes` parameter can pre-check scopes. If you only need repository access, `repo` is enough |
| GitHub (fine-grained, safer) | `https://github.com/settings/personal-access-tokens/new` | Issue with minimum permissions by choosing repositories one by one (recommended), though scopes are not pre-filled |
| Notion | `https://www.notion.so/my-integrations/new` | A personal account is enough — whether the workspace is shared doesn't matter. After creating it, a separate step is needed to **share it with the target database (Connections)** — `docs/07` §3 |
| Asana | `https://app.asana.com/0/developer-console` | A screen where the "Create new personal access token" button is immediately visible |
| Gmail (app password) | `https://myaccount.google.com/apppasswords` | The menu only appears if 2-step verification is turned on. You issue a new **app password**, not your login password — see §5 |

This table covers only the **"one token and you're done" services** (GitHub/Notion/Asana/Gmail app password).
Google Calendar/Drive use an OAuth login flow (consent screen), not a PAT, so the procedure is completely
different from this table and outside the scope of this document — follow `docs/05_external-services.md` §4-4 and the
"Calendar / shared spreadsheets" section of `scripts/connectors/README.md` (there is no connector
yet, so for now it is handled with the MCP connect button).

---

## 3. Steps (for one service)

1. Ask "OO 토큰 받는 거 도와줘" (“help me get the OO token”).
2. Claude opens a new tab with the URL from the table above, and checks by screenshot whether you are logged in.
   - If you're not logged in, Claude does not log in; it **asks you to log in yourself**
     (entering credentials is prohibited).
   - If it's your first login, you can create a new account or log in with your own existing account —
     either way there's nothing special to worry about.
3. Claude checks the name/scope input fields on the screen and tells you "you can create it as is"
   (Claude can fill in the text inputs — the name and scope selection are not secret values).
4. **You click the "Generate" button yourself.**
5. **You copy** the token value shown on the screen **yourself**, and run the following in the terminal (yourself,
   without asking Claude — for example, in Claude Code, with a command that starts with `!`):
   ```bash
   python scripts/connectors/register_token.py github   # for notion / asana, just change the service name
   python scripts/connectors/register_token.py notion
   python scripts/connectors/register_token.py asana
   ```
   When the hidden-input prompt appears, paste the value and press Enter — **what you type is not shown on screen**,
   and it is written straight into the matching field of `config/credentials.json`. Claude neither reads this value nor
   repeats it in the conversation — it goes from the keyboard directly to the file, and that's the end of it.
   (If you want to use an environment variable directly, `export SCITK_GITHUB_TOKEN='...'` still works as before.)
6. Confirm:
   ```bash
   python scripts/connectors/_credentials.py
   ```
   If it says "configured" (the Korean message "설정됨") with the value masked, you're done.

---

## 5. The Gmail app password procedure is slightly different

Gmail (personal mail) doesn't have a "generate token" screen; it has an **app password** issuing screen. You can go in through the §2
shortcut above (`myaccount.google.com/apppasswords`), but two things differ.

- **If 2-step verification is off, the menu doesn't even appear.** You first have to turn on 2-step verification
  on your Google account and then go back in — you do this setting yourself, too.
- **When registering, specify which mailbox with `--account`.** This is because personal mail (Gmail) and work/organization
  mail use separate paths inside `config/credentials.json` (`mail.accounts.personal.password`
  / `mail.accounts.work.password`):
  ```bash
  python scripts/connectors/register_token.py mail --account personal   # Gmail
  python scripts/connectors/register_token.py mail --account work       # work/organization mail
  ```
  (If you omit `--account`, the default is `work`. If the environment-variable method is simpler,
  `export SCITK_MAIL_PERSONAL_PASSWORD='...'` / `SCITK_MAIL_WORK_PASSWORD` still
  works.)
- The IMAP/SMTP server values (`imap_host`, `smtp_host`, etc.) for work/organization mail aren't tokens; they are values you
  fill in directly in `config/credentials.json` by following your institution's IT instructions —
  they are not secret values, so it's fine for Claude to fill them in.

---

## 4. Common sticking points (Windows)

The first time you actually try this, you will almost always get stuck on the following three things — know them in advance.

- **The `python` command doesn't work** (the "term is not recognized" error): this is common when "Add to PATH" was not
  checked while installing Python on Windows, or when you use a distribution like Anaconda that isn't
  on PATH by default. In that case, try **`py`** first instead of `python` (it is a launcher that is almost always
  installed alongside Python on Windows, so it is likely to be on PATH):
  ```
  py scripts\connectors\register_token.py github
  ```
  If that still doesn't work, find the install path and run it with the full path (`where python`, or
  check the Python install folder in File Explorer).
- **Claude may fail when trying to open Notepad/a terminal for you**: Claude tries launching `notepad`/
  `explorer` first, but the commands Claude Code runs are often in an environment where the session is
  separated from the screen (desktop), so in practice the window frequently doesn't appear. If no window
  shows up after a short wait, Claude will tell you "it didn't open," and then immediately give you the exact file path (or
  open the folder containing that file in advance) — paste that path into the File Explorer address bar,
  or press the Windows key → type `cmd` → Enter to open it yourself.
- **It's easy to open the wrong file**: your computer may have several files named something like `credentials.json` or `secrets.json`
  (backups, other projects, old versions). Instead of searching,
  **paste the path Claude gave you straight into the File Explorer address bar** to open the exact file.
  After saving, don't re-check the value by eye; confirm only with the masked confirmation message
  that `register_token.py` shows right after registration (`[등록됨] ... = xx****...`, where "등록됨" means “registered”).

## 5. One-line summary

- Claude goes only as far as **navigation** (moving to the exact URL + checking the screen); **the generate button and copying the value are always yours**
- Claude does not read the token value off the screen and repeat it — so that it doesn't end up in the chat history
- The issued token is stored in `config/credentials.json`, and this file is **separate on each machine** —
  it isn't shared with other PCs, so there's no need to worry too much about which account you pick
- For per-service shortcuts, see the §2 table above; Google Calendar/Drive use a separate OAuth flow
