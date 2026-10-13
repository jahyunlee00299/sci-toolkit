> English translation of [07_노션_연동_가이드.md](../07_노션_연동_가이드.md). The Korean original is canonical; if they differ, the Korean version wins.

# 07. Notion Integration Guide — Letting the AI Read Your To-Do/Project Databases

> One-line summary: **Reading is free; adding a new item happens only when you add --write; there is no delete feature at all.**

This document explains, at a beginner's level, how to use `scripts/connectors/notion_db_connector.py` to let the AI read a Notion **database (DB)**
and add new items in a draft-like way.
The big principles of connection and security were already covered in [05_external-services](05_external-services.md), so this document
focuses on the "Notion DB" case.

---

## 1. What does the Notion integration do for me?

If you manage a "to-do" list or a "project" list in Notion as a database (something shaped like a table),
this integration lets the AI do two things.

1. **Read**: ask "what to-dos are in progress right now?" and the AI looks it up directly in the Notion DB and tells you.
2. **Add (draft-like)**: say "add this one to-do" and the AI creates a new item. By default, though, this action only
   **shows a preview**; to actually add it, you must explicitly attach a flag called `--write`.
   (It is in the same vein as document 05's "outgoing actions stop at the draft" principle — a hard-to-undo action gets one more confirmation.)

This script **has no delete feature at all.** You can let it read and add without worrying about accidental deletion.

---

## 2. Preparation 1 — Create a Notion Integration and get a token

To use the Notion API you have to create something called an "Integration." Using the analogy from `docs/en/02_api-and-mcp.md`,
an **Integration = the counter that issues your access pass**.

1. In your browser, go to `notion.so/my-integrations`.
2. Click "New integration" and give it a name (an easy-to-recognize name, such as "sci-toolkit-connector").
3. After it is created, an "Internal Integration Token" (a secret token string) appears. This is the **access pass**.
4. Register this token in one of the two ways below.
   - Paste it into the `notion.token` slot of `config/credentials.json` (this file is excluded from distribution and commits), or
   - Set the environment variable `SCITK_NOTION_TOKEN` and write something like `"token": "ENV:SCITK_NOTION_TOKEN"` in `credentials.json` (the token value itself is not left in the file, which is safer).

> Do not paste the token into the chat window. It is exactly document 05's "token = access pass" principle.

---

## 3. Preparation 2 (⭐ the most common trap) — Share the Integration with the target DB

Even after creating the Integration and registering the token, there are very many cases where running `list-dbs` **shows nothing**.
The reason is just one.

> **A Notion Integration by default "cannot see any DB."** For every DB you want it to see, you have to
> share it individually (Connections), saying "this Integration is allowed to look here."

Here is how.

1. In Notion, open the database page you want to connect.
2. Click the **"..."** (more) menu at the top right.
3. Find and click the **"Connections"** item (shown as **"연결(Connections)"** in the Korean UI).
4. Search for the name of the Integration you just created and select it.

If you skip this process:
- that DB will not appear in the `list-dbs` list at all, and
- even if you try `schema`/`query`/`add-row` directly with that DB's id, you get a **404 error**.

The script is also built to show the guidance message "check whether the Integration has been shared" when this error occurs.
When a 404 or 403 appears, suspect this step first.

---

## 4. How to find the DB ID

When you open a Notion database in your browser, a URL like this appears in the address bar.

```
https://www.notion.so/workspace-name/<32-character-alphanumeric>?v=...
```

This `<32-character alphanumeric>` part is the database ID. Even if hyphens (-) are mixed in, just copy it as is
and use it. You put this ID in the `--db` argument.

> Tip: if you don't know a DB's ID, first run `list-dbs` and check the id along with the name
> (note that you must do the "sharing" from step 2 first for it to appear in the list).

---

## 5. Basic usage

Run all commands from the toolkit root.

```bash
# 1) List the databases I can see (= that were shared with me) [READ]
python scripts/connectors/notion_db_connector.py list-dbs

# 2) Check a specific DB's properties (schema) — which fields exist and their types [READ]
python scripts/connectors/notion_db_connector.py schema --db <YOUR_DATABASE_ID>

# 3) Query the DB's rows (items), the latest 10 [READ]
python scripts/connectors/notion_db_connector.py query --db <YOUR_DATABASE_ID>

# 3-1) Simple filtering by status value
python scripts/connectors/notion_db_connector.py query --db <YOUR_DATABASE_ID> --status "In progress"

# 4) Add a new item — first a preview (dry-run) without --write
#    ("예시 항목" in these examples is just a sample title: "Example item")
python scripts/connectors/notion_db_connector.py add-row --db <YOUR_DATABASE_ID> --title "예시 항목" --prop Status="In progress"

# 4-1) To actually add it, attach --write
python scripts/connectors/notion_db_connector.py add-row --db <YOUR_DATABASE_ID> --title "예시 항목" --prop Status="In progress" --write
```

`--prop NAME=VALUE` can be repeated to fill in several properties at once.

```bash
python scripts/connectors/notion_db_connector.py add-row \
  --db <YOUR_DATABASE_ID> \
  --title "예시 항목" \
  --prop Status="In progress" \
  --prop Tags="urgent,review" \
  --write
```

> Before it runs, `add-row` always internally looks up that DB's schema (`schema`) first,
> checks whether the property names you specified actually exist and what type they are, and then sends the
> values in the appropriate form. If you use a property name that does not exist, it immediately tells you with the error "There is no such property; available properties:
> ...".

---

## 6. ⭐ Safety summary

| Action | Default behavior | Can it be undone? |
|---|---|---|
| `list-dbs` / `schema` / `query` | Runs immediately (read-only) | Changes nothing to begin with |
| `add-row` (without `--write`) | Prints a preview only; nothing actually happens | — |
| `add-row --write` | Actually creates a new item | Can be undone by deleting it manually in Notion |
| (delete/archive) | **Not in this script at all** | — |

- Reading (`list-dbs`/`schema`/`query`) can be run freely at any time.
- Adding an item (`add-row`) only shows a preview of what would be created unless you attach `--write`.
- When adding to a **DB that others also see** (a team-shared DB), we recommend checking the preview content
  once more before attaching `--write` — it is the same as document 05's principle of "get confirmation for actions that affect others."
- This script cannot delete or archive items. If you need to delete, do it
  directly in Notion (this is intentional design).

---

## 7. Common property types in Notion databases

Notion DBs, in any project or lab, use property (column) types of roughly similar shapes. Below is
a **general explanation of the types themselves** (not actual values from any particular lab).

| Property type | Meaning | Form, as an example |
|---|---|---|
| `title` | The item's title. Every DB has exactly one | "Summarize experiment results" |
| `status` | Progress state (staged). Usually a few stages such as "not started / in progress / done" | Not started / In progress / Done |
| `select` | Single-choice list (for classification) | Choose one category value |
| `multi_select` | Multi-choice list (several can be chosen at once, like tags) | Several tags |
| `person` | Assign an owner/related person (a Notion workspace member) | One or more owners |
| `date` | A date or date range | Due date, start date |
| `number` | A numeric value (e.g., progress %) | A number between 0 and 100 |
| `relation` | Link to an item in another database (e.g., "to-do" DB ↔ "project" DB) | References between items |
| `rich_text` | Ordinary text (formatting allowed) | Notes, descriptions |
| `checkbox` | True/false checkbox | Check for completion |

For example, a "to-do management" DB is usually made up of a combination of title + status + select (type) +
multi_select (tags) + person (owner) + date + relation (linked to the project DB), and a "project management" DB is made up of
title + status + select (period unit: week/month/quarter, etc.) +
number (progress %) + relation (linked to the to-do DB), and so on. Which properties actually exist
differs by lab/project, so always check directly with `schema --db <id>` — if you guess and put in
a `--prop` name, it will be caught as an error.

---

## 8. Troubleshooting checklist

1. **401 error** → the token is wrong or not filled in. Check `notion.token` in `config/credentials.json` or the
   environment variable again.
2. **403/404 error** → almost always the case where "Chapter 3. Share the Integration with the target DB" was skipped.
   Re-check in Notion: that DB page's "..." → Connections → select the Integration.
3. **400 error (add-row)** → the property name or type differs from the actual DB. First check the exact property names and types with
   `schema --db <id>`, then retry with matching `--prop` values.
4. **list-dbs result is empty** → no DB has been shared yet. Follow chapter 3 and share at least
   one DB.

---

## 9. One-line summary

- Notion DB integration = **reading (list-dbs/schema/query) is free, adding (add-row) needs `--write`, and there is no delete at all.**
- The most common mistake = issuing only the token and **forgetting to share the Integration with the target DB (Connections).**
- If you are unsure about property names, always run `schema --db <id>` first.
