> English translation of [08_아사나_연동_가이드.md](../08_아사나_연동_가이드.md). The Korean original is canonical; if they differ, the Korean version wins.

# 08. Asana Integration Guide: Letting the AI Read Your Task List and Create New Tasks/Comments

> One-line summary: Reading (me/tasks) is free; creating tasks/comments/subtasks happens only when you add --write; there is no complete or delete feature at all.

This document explains, at a beginner's level, how to use `scripts/connectors/asana_connector.py` to let the AI read your Asana
My Tasks (Task) list and to create new tasks, comments, and subtasks.
The big principles of connection and security were already covered in [05_external-services](05_external-services.md), so this document
focuses on the "Asana" case, especially the problem of formatting breaking.

---

## 1. What does the Asana integration do for me?

If you manage tasks (Tasks) in Asana, this integration lets the AI do the following.

1. Read: ask "what tasks do I have?" and the AI looks them up directly in Asana and tells you.
2. Create a task: say "make this one task" and it creates a new task.
3. Add a comment: it leaves progress updates or notes as comments on an existing task.
4. Create a subtask: it breaks a big task into detailed steps as subtasks.

Reading always runs immediately (unlike the write actions in 2, 3, and 4), but write actions (creating tasks/comments/subtasks)
only show a preview (dry-run) by default, and to actually run them you must explicitly
attach a flag called `--write`. (It is in the same vein as document 05's "outgoing actions stop at the draft" principle.)

> Why this connector is better than MCP, a real case: Asana's MCP task-creation
> tool only makes a "preview card," and the task is actually created only after you click a confirm button on screen once more.
> That confirm click can be skipped depending on the kind of session, and in that case the AI replies "I made it," but nothing is actually
> created in Asana. It is a silent failure that looks like success. This connector's `--write` approach has no such ambiguous middle state:
> without it, it is only a preview; with it, it is created. If you used MCP, always query again with `tasks`
> right after creation to confirm it actually took effect.

Assigning a task to someone other than yourself (`--assignee`), or leaving a comment, is an
"outward action" that others can see. In these cases the connector shows an extra notice.

This script has no feature to complete or delete tasks at all. You can let it read and create without worrying about accidentally deleting
or completing someone else's task.

---

## 2. Preparation: Get an Asana Personal Access Token (PAT)

To use the Asana API you need to issue a "Personal Access Token."
Using the analogy from `docs/en/02_api-and-mcp.md`, the token = access pass.

1. Log in at `app.asana.com` in your browser, then go to the profile icon at the top right → "My Settings"
   (shown as "내 설정(My Settings)" in the Korean UI).
2. Go to the "Apps" tab → click "Manage Developer Apps" at the bottom
   (shown as "앱(Apps)" and "개발자 앱 관리(Manage Developer Apps)" in the Korean UI).
3. Press "Create New Personal Access Token" and give it a name
   (an easy-to-recognize name, such as "sci-toolkit-connector"). (Korean UI: "새 개인 액세스 토큰 만들기(Create New Personal Access Token)".)
4. After it is created, the token string is shown only once. This is the access pass. Copy it right there.
5. Register this token in one of the two ways below.
   - Paste it into the `asana.token` slot of `config/credentials.json` (this file is excluded from distribution and commits), or
   - Set the environment variable `SCITK_ASANA_TOKEN` and write something like `"token": "ENV:SCITK_ASANA_TOKEN"` in `credentials.json`
     (the token value itself is not left in the file, which is safer; see `docs/en/05_external-services.md`).

> Do not paste the token into the chat window. It is exactly document 05's "token = access pass" principle.

### Finding your workspace gid

Most commands in Asana need a workspace gid (the unique number of the workspace you belong to).
You don't have to find it yourself. Run the `me` command and the connector shows you the list of workspaces you belong to
with their names and gids.

```bash
python scripts/connectors/asana_connector.py me
```

Example output (for the shape only; actual values differ for each person):

```
이름: ...
gid: ...
email: ...
workspaces:
  - <워크스페이스 이름> (gid=<WORKSPACE_GID>)
```

(The Korean labels are the connector's actual output: `이름` = "Name", `워크스페이스 이름` = "workspace name".)

You use this `<WORKSPACE_GID>` for the `--workspace` argument of later commands.

---

## 3. Basic usage

Run all commands from the toolkit root.

```bash
# 1) Check my profile + workspace list [READ]
python scripts/connectors/asana_connector.py me

# 2) List my tasks [READ]
python scripts/connectors/asana_connector.py tasks --workspace <WORKSPACE_GID>

# 3) Create a new task — first a preview (dry-run) without --write
#    ("예시 작업" in these examples is just a sample name: "Example task")
python scripts/connectors/asana_connector.py add-task --workspace <WORKSPACE_GID> --name "예시 작업"

# 3-1) To actually create it, attach --write
python scripts/connectors/asana_connector.py add-task --workspace <WORKSPACE_GID> --name "예시 작업" --write

# 4) Add a comment to an existing task (plain text)
#    ("진행 상황 메모" = "Progress note")
python scripts/connectors/asana_connector.py add-comment --task <TASK_GID> --text "진행 상황 메모" --write

# 5) Create a subtask
#    ("1단계: 데이터 정리" = "Step 1: Organize data")
python scripts/connectors/asana_connector.py add-subtask --parent <TASK_GID> --name "1단계: 데이터 정리" --write
```

If you run the `tasks` command without `--workspace`, instead of an error it shows you the list of available
workspaces, so you can get started even without knowing the gid.

`add-task` also takes `--notes` (description) and `--assignee` (owner, `me` or another person's gid/email).
If you give `--assignee` a value other than `me`, a notice appears first saying "this task is being assigned to someone else; it is an
outward action."

---

## 4. The most important section: why comment/subtask formatting breaks, and the fix

Users often ran into this problem: when you send a formatted comment straight to the Asana API,
the "formatting often goes wrong" or it even produces an error. This connector is built to
block those traps automatically.

### Short ordinary comments → just use `--text`

```bash
python scripts/connectors/asana_connector.py add-comment --task <TASK_GID> --text "완료했습니다" --write
```

(`"완료했습니다"` = "Done.")

This is sent as is as plain text, and Asana displays it on its own. There is nothing else to worry about.

### If you need formatting (bold, lists, and so on), use `--html`

```bash
python scripts/connectors/asana_connector.py add-comment --task <TASK_GID> \
  --text "<strong>결과 요약</strong>: 진행률 80%, 다음 단계는 분석입니다." \
  --html --write
```

(The text reads: "<strong>Result summary</strong>: progress 80%, the next step is analysis.")

When you attach `--html`, the connector internally automatically validates and corrects Asana's `html_text` formatting rules.
Asana's formatting rules have 4 traps that beginners easily fall into without knowing it.

| # | Trap | What happens | What the connector does |
|---|---|---|---|
| (a) | The whole thing must be wrapped in `<body>...</body>` | If not wrapped, a format error | When `--html` is used and there is no `<body>`, it **wraps it automatically** |
| (b) | The `<p>` tag (paragraph tag) is absolutely forbidden | Including `<p>` makes the request itself fail with `xml_parsing_error` | If the connector finds `<p>`, it **blocks it before running** and tells you "use &#10; for line breaks" |
| (c) | Line breaks use the special code `&#10;`, not an ordinary line break (Enter) | Just putting in Enter breaks the formatting | The connector **automatically converts** the line breaks (Enter) you typed into `&#10;` |
| (d) | The `'→'` (arrow symbol) character is absolutely forbidden | Including it makes the request fail with an XML parsing error | If the connector finds `→`, it **blocks it before running** and tells you "replace it with `->` or a word" |

And the allowed tags are only some: `<strong>` (bold), `<em>` (italic), `<u>` (underline), `<code>`, `<a>` (link),
`<ul>`/`<ol>`/`<li>` (lists), `<h1>`/`<h2>` (headings), and `<table>`/`<tr>`/`<td>`.
Using any other tag may be rejected on Asana's side, so we recommend keeping formatting within this list.

For a subtask's description, attaching the `--html-notes` flag applies the same rules.

```bash
python scripts/connectors/asana_connector.py add-subtask --parent <TASK_GID> \
  --name "2단계: 분석" --notes "<strong>목표</strong>: 결과 검증" --html-notes --write
```

(`"2단계: 분석"` = "Step 2: Analysis"; the notes read "<strong>Goal</strong>: verify results".)

### The problem of Korean text getting garbled

In the past, when the Asana API was called directly with a tool like `curl`, Korean text on Windows could be garbled, sent as
escape codes like `\uXXXX`, or with a mismatched encoding. This connector is built to always specify
`ensure_ascii=False` + `charset=utf-8` in the request, so Korean task
names, comments, and descriptions are sent as is without being garbled. This is handled automatically, so you don't need to
worry about it.

### Conclusion

- For short, unformatted comments/notes → just use `--text` (or `--notes`).
- If you need formatting such as bold or lists, attach `--html` (or `--html-notes`). Rules (a) to (d) above are
  followed automatically by the connector, or, if violated, you are told right away before it runs.

---

## 5. Safety principles

- Reading (`me`/`tasks`) can be run freely at any time. It changes nothing.
- Writing (`add-task`/`add-comment`/`add-subtask`), unless you attach `--write`, only prints a preview (JSON) of what would be
  created and nothing actually happens.
- Assigning to someone else (`--assignee`) or leaving a comment is an "outward action": teammates
  will see it, so we recommend checking the preview content once more before attaching `--write`.
- A task complete (complete) or delete (delete) feature is intentionally absent from this script. If you need that,
  do it directly in Asana.

---

## 6. Safety summary table

| Action | Default behavior | Condition to run |
|---|---|---|
| `me` (check my profile/workspaces) | Runs immediately (read-only) | Always free |
| `tasks` (list my tasks) | Runs immediately (read-only) | Always free |
| `add-task` (without `--write`) | Prints a preview only; nothing is actually created | — |
| `add-task --write` | Actually creates the task. If `--assignee` is not me, an outward-action notice | Explicit `--write` required |
| `add-comment` (without `--write`) | Prints a preview only | — |
| `add-comment --write` | Actually posts the comment (always an outward-action notice — others can see it) | Explicit `--write` required |
| `add-subtask` (without `--write`) | Prints a preview only | — |
| `add-subtask --write` | Actually creates the subtask. If `--assignee` is not me, an outward-action notice | Explicit `--write` required |
| (complete a task) | **Not in this script at all** | — |
| (delete) | **Not in this script at all** | — |

---

## 7. One-line summary

- Asana integration = reading (me/tasks) is free, creating tasks/comments/subtasks needs `--write`, and complete/delete are not there at all.
- If you need a formatted comment, use `--html` (or `--html-notes`); Asana's fussy rules such as no `<p>`, `&#10;` line breaks, and
  no `→` are followed automatically by the connector or blocked before running.
- For a short ordinary comment, plain `--text` is enough; Korean text is also sent as is without being garbled.
