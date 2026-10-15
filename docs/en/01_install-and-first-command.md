> English translation of [01_설치와_첫_명령.md](../01_설치와_첫_명령.md). The Korean original is canonical; if they differ, the Korean version wins.

# 01. Installation and Your First Command: Actually Giving One a Try

> If the earlier [00_getting-started](00_getting-started.md) gave you a feel for "what an AI agent is,"
> this document takes you through actually installing the program, layering this toolkit on top, and giving your first command.
> Follow the steps in order. If you get stuck, ask a senior labmate.

---

## 0. Checklist

- A computer (Windows and Mac both work)
- A Claude subscription account ([Pro or Max](https://claude.com/pricing)). If you don't have one, subscribe first at [claude.ai](https://claude.ai).
  You **do not need** an API key. (For why, see [02_api-and-mcp](02_api-and-mcp.md).)
- This toolkit folder (`sci-toolkit`): the folder this document is in.

---

## 1. Install Claude Code

There are three ways to use [Claude Code](https://code.claude.com/docs/en/overview). All three are the same Claude Code,
you log in with the same subscription account, and this toolkit is layered on in exactly the same way.
The only difference is "where you chat."

### Which one should I pick?

| If this describes you | Use this |
|---|---|
| The terminal is unfamiliar / you just want to try it | Desktop app |
| You already work on code and data in VS Code | VS Code extension |
| You're comfortable in the terminal / you use it on a server | Terminal (CLI) |

> If you can't decide, start with the desktop app. If you switch later, you won't have to redo your setup.
> Installing all three at once causes no conflicts.

### Method A: Desktop app (recommended for beginners)

1. Go to [claude.ai/download](https://claude.ai/download).
2. Download and install the version for your computer (Windows / Mac).
   (Like any ordinary program: download → run → click "Next," and you're done.)
3. After installing, open the app and log in with your own Claude account. ([Get started with the desktop app](https://code.claude.com/docs/en/desktop-quickstart))

> That's all. Click the icon → log in → the chat box appears.

### Method B: VS Code extension (if you work with code and data in VS Code)

If you're already working on Python scripts or data in [VS Code](https://code.visualstudio.com/), this is the most convenient.
The AI can see the file you're editing right away, and you can see the results of its changes directly in the editor.

1. Open VS Code and click the Extensions icon (four squares) on the left.
2. Type `Claude Code` in the search box and Install [the one made by Anthropic](https://marketplace.visualstudio.com/items?itemName=anthropic.claude-code).
3. After it's installed, reopen the window and log in with your Claude account as prompted.
4. Open `sci-toolkit` as your working folder (File → Open Folder).

> If you use a [JetBrains](https://code.claude.com/docs/en/jetbrains) IDE (such as PyCharm), there is a plugin with the same name.
> Search for `Claude Code` in the plugin marketplace.

### Method C: Terminal (CLI)

Use this method if you're comfortable with the terminal, or if you'll use it on a shared lab server or HPC.

```
npm install -g @anthropic-ai/claude-code
```

After installing, type `claude` in any folder to run it. ([Official setup guide](https://code.claude.com/docs/en/setup))
(If you don't have `npm`, install Node.js first from [nodejs.org](https://nodejs.org).)

For how to use it on a remote server, see [09_remote-server](09_remote-server.md).

---

## 2. "Layering on" this toolkit

If you only install Claude Code, the AI doesn't yet know "how our lab does things."
Only after you layer this toolkit folder on does it know our rules.

> Analogy: Claude Code is a new researcher you've hired.
> The lab manual you hand them is sci-toolkit.

### The simplest way: open this folder and start

1. In Claude Code, set the working folder to the `sci-toolkit` folder.
   What you do is the same regardless of how you installed it.
   - Desktop app: choose `sci-toolkit` under "Open folder" or the folder picker at the top.
   - VS Code: File → Open Folder → select `sci-toolkit`. Then open the Claude Code panel in that state.
   - Terminal: move into the `sci-toolkit` folder, then run `claude`.
2. The AI automatically consults `AGENTS.md`, `config/`, `skills/`, and so on in this folder.
   You don't need to set anything up yourself.

> ⚠️ If you move the whole folder or rename it, references may break.
> To start, leave it exactly as you received it.

### If you also want to use it from other folders (optional)

The method above attaches the skills "only when you've opened the `sci-toolkit` folder."
If you want to use them no matter which folder you work in, install just the skills you want.

```
python install/install.py --list                    # See what's available first
python install/install.py --preset paper-writing    # Only the paper-writing set
python install/install.py --skills docx,xlsx --apply
```

They are installed to `~/.claude/skills/`, and all three installation methods (app, VS Code, terminal)
share this folder. Install once and it applies wherever you open it.
(If you run it without `--apply`, it only shows a preview and does not actually copy anything.)

### Checking that it's layered on correctly (optional)

Run the following in the `sci-toolkit` folder to check its status.

```
python doctor.py
```

If you see `PASS`, it's working. (If you see `FAIL`, take a screenshot of that line and show it to a senior labmate.)
If you don't use the terminal, you can skip this step.
You can also just tell Claude Code, "Run doctor.py and tell me the result."

### Python version: Uncertainty/units and experimental design features need 3.12 or later

Two features, `uncertainty-and-units` (error propagation, unit conversion, ± notation) and `doe-and-replication` (experimental design, replicate counts, plate layout),
require [Python](https://www.python.org/downloads/) 3.12 or later. This is because the library they use (`pint`) can be installed only from 3.12 onward.
You can check your Python version with `python --version` in the terminal. If it is lower than 3.12, only these two features are unavailable,
and the rest work as usual. You can install the required packages in one line.

```
pip install pint uncertainties numpy scipy pandas pydoe
```

If the "Skill dependencies" line in `python doctor.py` shows these package names as a WARN, it does not mean the installation failed.
It is only a notice that "this feature needs these additional packages," so install them only when you use that feature.

---

## 3. Giving your first command

In the chat box, talk in Korean (or your own language).
You don't need to memorize any commands.

### Warm-up: start with something that isn't scary

```
이 폴더에 어떤 파일들이 있는지 정리해서 알려줘.
```
(“Organize and tell me what files are in this folder.”)

The AI scans the folder and puts together a list with descriptions.
This is a task that only reads and changes nothing, so it is safe. It's a good way to get a feel for things.

### Trying the toolkit's real features

This toolkit includes features (skills) such as paper search, plotting, statistics, and document work.
For example:

```
효소 반응속도(kinetics) 관련 최근 논문 5편만 찾아서 요약해줘.
```
(“Find just 5 recent papers on enzyme reaction kinetics and summarize them.”)

```
이 엑셀 파일(파일명 알려주세요)로 막대그래프를 그려줘. 논문에 넣을 수 있는 스타일로.
```
(“Draw a bar chart from this Excel file (tell me the filename). In a style I can put in a paper.”)

The AI picks and runs the appropriate feature by itself. You don't need to choose a skill;
say what you want to do in words.

### Looking back

Before the AI changes or creates anything, it will generally ask "Is it okay to do it this way?"
(How often it asks depends on the permission mode; see section 4 below.)
- Check the content, and approve if it looks fine,
- If it doesn't look right, decline or explain again.

At first, keep this confirmation step on and watch alongside it. As you get used to it, you can gradually trust it with more.

---

## 4. Permission settings: handling the "Allow" prompt

The confirmation box the AI shows before it changes a file or runs a command is a **permission request**.
For the first few days, watching these prompts is the best way to learn what the AI is doing.

### When an allow prompt appears

The prompt says what the AI wants to do (the file it will change, the command it will run), and usually offers these choices.

| Choice | Meaning |
|---|---|
| **Yes** | Allow this one time |
| **Yes, and don't ask again for …** | Don't ask again for the same kind of action |
| **No** | Decline. You can then ask "why do you want to do this?" |

Before you click, check three things.

- **Which file?** If it wants to change a file outside the working folder, or your original data, decline first and ask why.
- **Is it deleting something?** If you see `rm`, `del`, or "delete", read it once more.
- **Is it sending something out?** `git push`, sending mail, and uploads are hard to undo.

If you don't know what a command means, click **No** and ask "what does that command do?"
Once you understand it, ask again.

How long "don't ask again" lasts depends on the kind of action. A command is remembered for that folder from then on;
a file edit is remembered only until this conversation ends. ([Official explanation](https://code.claude.com/docs/en/permissions))

### Choosing a permission mode

How often the AI asks is set by the **permission mode**. Change it with the mode selector next to the send button
in the desktop app, the mode indicator in the VS Code prompt box, or `Shift+Tab` in the terminal.

| Mode | Does without asking | When to use |
|---|---|---|
| **Manual** | Reading only | **Start here.** You check every change |
| **Accept edits** | Reading, editing files | Once you're comfortable, for repetitive work. Other commands still ask |
| **Plan** | Reading (proposes a plan, changes nothing) | When you want to see "how" before a big task |
| **Auto** | Most things (a second AI screens risky actions in the background) | When prompts get too frequent |
| **Bypass permissions** | Everything | **Don't use it.** For isolated test environments only |

Recent versions of the terminal and VS Code can **start in Auto**, so you may see almost no allow prompts.
Switch to Manual at first and watch. The desktop app remembers the last mode you picked for each folder.
([Permission modes docs](https://code.claude.com/docs/en/permission-modes))

### Auto-allow and deny rules (optional)

If you keep clicking "Yes" for the same question, you can turn it into a rule. Usually clicking
"don't ask again" in the prompt saves the rule for you, so you rarely need to write one by hand.
To write one yourself, put it in the working folder's `.claude/settings.json` (this folder only) or `~/.claude/settings.json` (your whole computer).

```json
{
  "permissions": {
    "allow": ["Bash(git diff *)", "Bash(git log *)"],
    "deny": ["Bash(git push *)", "Bash(rm -rf *)"]
  }
}
```

- `allow`: runs without asking (the example allows commands that only look at history and change nothing)
- `deny`: never runs even if asked (the example blocks uploading and deleting a whole folder)
- `*` means "whatever comes after". A broad rule like `Bash(python *)` effectively lets any code run
  without asking, so avoid it.

The rule syntax and where settings files live are in the official [permissions](https://code.claude.com/docs/en/permissions)
and [settings](https://code.claude.com/docs/en/settings) docs.

---

## 5. Common first-day problems

| Symptom | Try this |
|---|---|
| I can't log in | Check that it's the right subscription account and that Claude Pro/Max is active. If it still doesn't work, restart the app. |
| The AI doesn't seem to know our lab's style | Check that the working folder is set to `sci-toolkit` (step 2). |
| No matter what I ask, it only says "permission is required" | Approve (allow) that request and it will proceed. If the content looks odd, decline. See section 4 for what to check. |
| I don't know how to phrase a command | Just write what you want to do casually. If it's ambiguous, the AI will ask you back. |

---

## 6. Codex tips

If you use [Codex](https://developers.openai.com/codex) (OpenAI's similar tool), the big picture is the same.

- Installation: turn on Codex in a ChatGPT subscription (Plus or higher) environment, or install the CLI as instructed.
- Layering on this toolkit: if you open the `sci-toolkit` folder as your working folder, Codex automatically reads `AGENTS.md`.
  (It is set up so that Claude Code consults `AGENTS.md`, and Codex consults the same `AGENTS.md`.)
- First command: likewise, just say what you want to do. Only how you launch it differs a little;
  the flow of "open the folder → ask in words → check and approve" is the same.

---

## 7. Next steps

You have now started using an AI agent.

- How costs arise and why a subscription is safe → [03_tokens-and-cost](03_tokens-and-cost.md)
- If you want to give the AI more rules, like "this is how we do it" → [04_giving-ai-rules](04_giving-ai-rules.md)
- To safely entrust external services such as mail, GitHub, Asana/Notion, and calendars to the AI → [05_external-services](05_external-services.md)
- Which features need API keys or installation and which just work (most just work) → [06_requirements-by-feature](06_requirements-by-feature.md)
- To connect a Notion database to the AI → [07_notion-guide](07_notion-guide.md)
- To handle Asana tasks, comments, and subtasks with the AI → [08_asana-guide](08_asana-guide.md)

Trying one or two warm-up commands today is enough.
If you have questions, ask a senior labmate (mentor).

---

## One-line summary

- Installation = download the Claude Code desktop app and log in (no API key needed)
- Layering on the toolkit = set the working folder to `sci-toolkit` and you're done (referenced automatically)
- First command = just say what you want to do in the chat box (warm up with read-only tasks)
- Safeguard = the AI checks with you before changing anything. Watch at first, then trust it with more
