> English translation of [00_시작하기.md](../00_시작하기.md). The Korean original is canonical; if they differ, the Korean version wins.

# 00. Getting Started (A Guide for First-Time Users)

This guide is for people who have never used an AI agent. It starts from "what is an AI agent?" and takes about ten minutes to read.

---

## 1. What is an AI agent?

A chatbot answers your questions in words. An AI agent goes one step further: it does the work itself instead of only talking.

An analogy:

- Chatbot = a senior labmate who tells you how to do an experiment, in words
- AI agent = a lab assistant who stands beside you and opens the files, organizes the tables, and draws the graphs

If you ask in everyday language, "Take the replicate averages in this Excel file and plot them," the agent reads the file inside your computer, does the calculation, and creates the result files. You don't need to know how to code.

## 2. What is this sci-toolkit?

The sci-toolkit is a toolbox that gathers the tasks labs do often so that an agent can do them better.

- If the agent is a general assistant, this toolbox is the lab-specific manual and tools you put in its hands.
- It guides the agent to do data cleanup, plotting, statistics checks, and manuscript polishing "the way our lab does it."
- Each tool comes with a written guide, so the agent reads it and follows it on its own. You don't need to memorize anything.

## 3. What is Claude Code?

[Claude Code](https://code.claude.com/docs/en/overview) is a program that lets you use [Anthropic](https://www.anthropic.com)'s AI, "Claude," as an agent. It is the base program of this toolbox, and it is where the assistant described above lives.

There are several ways to use it, but for beginners the desktop app is the easiest.

| Method | What it looks like | Recommendation |
|---|---|---|
| [Desktop app](https://code.claude.com/docs/en/desktop-quickstart) | Opens in a window like an ordinary program, and you chat | Choose this if you're new |
| [Terminal (the black window)](https://code.claude.com/docs/en/quickstart) | You type commands on a text-only screen | After you get comfortable |

### Steps to get started

1. Install the [Claude desktop app](https://claude.com/download) and log in. (If you don't have an account, ask your lab's point person. Plans are listed on the [pricing page](https://claude.com/pricing).)
2. In the app, choose the folder you want to work in. It's like telling the assistant, "Work at this bench."
3. In the chat box, type what you want to do in your everyday words. For example:
   - "Read the Excel files in this folder and tell me what data they contain."
   - "Plot the concentration-over-time data as a graph."
4. When the agent shows you what it intends to do, check it and click **Allow**. ([About permissions](https://code.claude.com/docs/en/permissions))

> If you want to use Codex: OpenAI's [Codex](https://developers.openai.com/codex) works the same way. Open your working folder in the [app](https://developers.openai.com/codex/app) or [terminal](https://developers.openai.com/codex/cli) and ask in words just the same. The names and locations of the settings files are a little different, so see [Codex's AGENTS.md guide](https://developers.openai.com/codex/guides/agents-md) and [04. Giving AI rules](04_giving-ai-rules.md).

## 4. If you're new, remember just these

- Ask in words. There is no required phrasing; write as casually as you would in a lab notebook.
- Ask for one thing at a time and you'll get better results.
- **Always check the results with your own eyes.** An agent is sometimes wrong. Compare any number that goes into a paper or report against the original.
- If you don't understand, ask back. If you say, "Explain what you just did in simple terms," it will break it down for you.
- Don't enter personal information or passwords. Be careful with research data that must not be made public, too.

## 5. Common worries

- If you're worried about breaking a file: before changing or deleting a file, the agent usually asks for permission first. For important originals, make a copy before you start.
- If you can't code: the agent writes the code. You only have to say what you want.
- If you made a mistake: in most cases it can be undone. If something is wrong, say, "Do it again."

## 6. Next step

If you don't have the toolkit folder yet, start with [15. Setting up Git and GitHub](15_github-setup.md). Once you have it, move on to [01. Install and first command](01_install-and-first-command.md). For your first time, try a single small file in this order: "read it → organize it → plot it."

If you get stuck, ask a labmate or your point person.
