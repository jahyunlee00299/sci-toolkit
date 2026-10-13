> English translation of [01_설치와_첫_명령.md](../01_설치와_첫_명령.md). The Korean original is canonical; if they differ, the Korean version wins.

# 01. Installation and Your First Command — Actually Giving One a Try

> If the earlier [00_getting-started](00_getting-started.md) gave you a feel for "what an AI agent is,"
> this document takes you through **actually installing the program, layering this toolkit on top, and giving your first command.**
> Just follow along in order. If you get stuck, simply ask a senior labmate.

---

## 0. Checklist

- A computer (Windows and Mac both work)
- A Claude subscription account (Pro or Max). If you don't have one, subscribe first at [claude.ai](https://claude.ai).
  You **do not need** an API key. (For why, see [02_api-and-mcp](02_api-and-mcp.md).)
- This toolkit folder (`sci-toolkit`) — the very folder this document is in.

---

## 1. Install Claude Code

There are **three ways** to use Claude Code. All three are the same Claude Code,
you **log in with the same subscription account**, and **this toolkit is layered on in exactly the same way.**
The only difference is "where you chat."

### Which one should I pick?

| If this describes you | Use this |
|---|---|
| The terminal is unfamiliar / you just want to try it | **Desktop app** |
| You already work on code and data in VS Code | **VS Code extension** |
| You're comfortable in the terminal / you use it on a server | **Terminal (CLI)** |

> If you can't decide, start with the **desktop app**. If you switch later, you won't have to redo your setup.
> Installing all three at once causes no conflicts.

### Method A — Desktop app (recommended for beginners)

1. Go to [claude.ai/download](https://claude.ai/download).
2. Download and install the version for your computer (Windows / Mac).
   (Like any ordinary program: download → run → click "Next," and you're done.)
3. After installing, open the app and log in with your own Claude account.

> That's all. Click the icon → log in → the chat box appears. If you've got this far, you're halfway done.

### Method B — VS Code extension (if you work with code and data in VS Code)

If you're already working on Python scripts or data in VS Code, this is the most convenient.
The AI can see the file you're editing right away, and you can see the results of its changes directly in the editor.

1. Open VS Code and click the **Extensions** icon (four squares) on the left.
2. Type **`Claude Code`** in the search box and **Install** the one made by Anthropic.
3. After it's installed, reopen the window and log in with your Claude account as prompted.
4. **Open `sci-toolkit` as your working folder** (File → Open Folder).

> If you use a JetBrains IDE (such as PyCharm), there is a plugin with the same name.
> Search for `Claude Code` in the plugin marketplace.

### Method C — Terminal (CLI)

Use this method if you're comfortable with the terminal, or if you'll use it on a shared lab server or HPC.

```
npm install -g @anthropic-ai/claude-code
```

After installing, type `claude` in any folder to run it.
(If you don't have `npm`, install Node.js first from [nodejs.org](https://nodejs.org).)

For how to use it on a remote server, see [09_remote-server](09_remote-server.md).

---

## 2. "Layering on" this toolkit

If you only install Claude Code, the AI doesn't yet know "how our lab does things."
Only after you layer this toolkit folder on does it know our rules.

> Analogy: You've hired a new researcher (Claude Code),
> but you haven't handed over our lab manual (sci-toolkit) yet. Now it's time to hand it over.

### The simplest way — open this folder and start

1. In Claude Code, **set the working folder to the `sci-toolkit` folder**.
   What you do is the same regardless of how you installed it.
   - **Desktop app**: choose `sci-toolkit` under "Open folder" or the folder picker at the top.
   - **VS Code**: File → Open Folder → select `sci-toolkit`. Then open the Claude Code panel in that state.
   - **Terminal**: move into the `sci-toolkit` folder, then run `claude`.
2. The AI automatically consults `AGENTS.md`, `config/`, `skills/`, and so on in this folder.
   You don't need to set anything up yourself.

> ⚠️ If you move the whole folder or rename it, references may break.
> To start, leave it exactly as you received it.

### If you also want to use it from other folders (optional)

The method above attaches the skills "only when you've opened the `sci-toolkit` folder."
If you want to use them **no matter which folder you work in**, install just the skills you want.

```
python install/install.py --list                    # See what's available first
python install/install.py --preset paper-writing    # Only the paper-writing set
python install/install.py --skills docx,xlsx --apply
```

They are installed to `~/.claude/skills/`, and **all three installation methods (app, VS Code, terminal)
share this folder.** Install once and it applies wherever you open it.
(If you run it without `--apply`, it only shows a preview and does not actually copy anything.)

### Checking that it's layered on correctly (optional)

Run the following in the `sci-toolkit` folder to check its status.

```
python doctor.py
```

If you see `PASS`, it's working. (If you see `FAIL`, take a screenshot of that line and show it to a senior labmate.)
If you don't use the terminal, you can skip this step —
you can also just tell Claude Code, "Run doctor.py and tell me the result."

### Python version — Uncertainty/units and experimental design features need 3.12 or later

Two features, `uncertainty-and-units` (error propagation, unit conversion, ± notation) and `doe-and-replication` (experimental design, replicate counts, plate layout),
require Python **3.12 or later**. This is because the library they use (`pint`) can be installed only from 3.12 onward.
You can check your Python version with `python --version` in the terminal. If it is lower than 3.12, only these two features are unavailable,
and the rest work as usual. You can install the required packages in one line.

```
pip install pint uncertainties numpy scipy pandas pydoe
```

If the "Skill dependencies" line in `python doctor.py` shows these package names as a **WARN**, it does not mean the installation failed.
It is only a notice that "this feature needs these additional packages," so install them only when you use that feature.

---

## 3. Giving your first command

Now it's time to actually give an order. In the chat box, **just talk in Korean** (or your own language).
You don't need to memorize any commands.

### Warm-up — start with something that isn't scary

```
이 폴더에 어떤 파일들이 있는지 정리해서 알려줘.
```
(“Organize and tell me what files are in this folder.”)

The AI scans the folder and puts together a list with descriptions.
This is a task that **only reads and changes nothing**, so it is safe. It's a good way to get a feel for things.

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

The AI picks and runs the appropriate feature by itself. You don't need to worry about
"which skill should I use?" — just say what you want to do in words.

### Looking back

Before the AI changes or creates anything, it will generally ask **"Is it okay to do it this way?"**
- Check the content, and approve if it looks fine,
- If it doesn't look right, decline or explain again.

At first, keep this confirmation step on and watch alongside it. As you get used to it, you can gradually trust it with more.

---

## 4. Common first-day problems

| Symptom | Try this |
|---|---|
| I can't log in | Check that it's the right subscription account and that Claude Pro/Max is active. If it still doesn't work, restart the app. |
| The AI doesn't seem to know our lab's style | Check that the working folder is set to `sci-toolkit` (step 2). |
| No matter what I ask, it only says "permission is required" | Approve (allow) that request and it will proceed. If the content looks odd, decline. |
| I don't know how to phrase a command | Just write what you want to do casually. If it's ambiguous, the AI will ask you back. |

---

## 5. Codex tips

If you use Codex (OpenAI's similar tool), the big picture is the same.

- Installation: turn on Codex in a ChatGPT subscription (Plus or higher) environment, or install the CLI as instructed.
- Layering on this toolkit: if you open the `sci-toolkit` folder as your working folder, Codex automatically reads `AGENTS.md`.
  (It is set up so that Claude Code consults `AGENTS.md`, and Codex consults the same `AGENTS.md`.)
- First command: likewise, just say what you want to do. Only how you launch it differs a little;
  the flow of "open the folder → ask in words → check and approve" is the same.

---

## 6. Next steps

If you've made it this far, you have already "started using" an AI agent.

- How costs arise and why a subscription is safe → [03_tokens-and-cost](03_tokens-and-cost.md)
- If you want to give the AI more rules, like "this is how we do it" → [04_giving-ai-rules](04_giving-ai-rules.md)
- To safely entrust external services such as mail, GitHub, Asana/Notion, and calendars to the AI → [05_external-services](05_external-services.md)
- Which features need API keys or installation and which just work (most just work) → [06_requirements-by-feature](06_requirements-by-feature.md)
- To connect a Notion database to the AI → [07_notion-guide](07_notion-guide.md)
- To handle Asana tasks, comments, and subtasks with the AI → [08_asana-guide](08_asana-guide.md)

There's no rush. Trying just one or two warm-up commands today is plenty.
If you have questions, ask a senior labmate (mentor) anytime.

---

## One-line summary

- **Installation** = download the Claude Code desktop app and log in (no API key needed)
- **Layering on the toolkit** = set the working folder to `sci-toolkit` and you're done (referenced automatically)
- **First command** = just say what you want to do in the chat box (warm up with read-only tasks)
- **Safeguard** = the AI checks with you before changing anything — watch at first, then trust it with more
