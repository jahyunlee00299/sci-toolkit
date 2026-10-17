> English translation of [02_API와_MCP.md](../02_API와_MCP.md). The Korean original is canonical; if they differ, the Korean version wins.

# API, MCP, and API Keys: An Easy Explanation for Beginners

> Most of you do not need an API key. Use Claude or ChatGPT as a monthly subscription (flat-rate) app.
> An API key is an optional, advanced feature for "when a developer builds a program directly."

---

## 1. What is an API? ("A restaurant's order window")

API (Application Programming Interface) sounds difficult, but the analogy is very simple.

> API = a restaurant's order window (the window that connects the kitchen and the customer)

- You (a program) can't walk straight into the kitchen (the AI company's server).
- Instead, you make a request at the order window, saying "I'll have this," and the kitchen prepares it and hands it out through the window.
- This "order form and procedure" is the API. It is a set of agreed rules for programs to talk to each other (the window's manual).

For example, the "[Claude API](https://platform.claude.com/docs/en/api/overview)" works like this:

> When my program sends an order slip saying "answer this question" to Anthropic's order window,
> the Anthropic server (the kitchen) produces the answer and sends it back.

It is a way for code to place and receive orders automatically, rather than a person typing into a chat box.

### So who uses an API?

- A developer who wants to "automatically build AI features into my app/script"
- Example: you want to run a script that automatically summarizes 100 papers every dawn → use the API
- Conversely, if you "just want to chat and use it in a chat box" → no API needed; a subscription app is enough

---

## 2. What is MCP? ("A standard plug specification")

[MCP (Model Context Protocol)](https://modelcontextprotocol.io) is a concept one step beyond the API.

> MCP = a standard plug (outlet) specification that works anywhere in the world

Think of electronics. If the refrigerator, vacuum cleaner, and TV each had a different plug shape, every household would need to make separate adapters. But if there is a "standard plug specification," any product made to that specification can be plugged into any outlet and used right away.

- Before MCP: for an AI to use Google Drive, you needed connection code specific to Google Drive; for Notion, connection code specific to Notion, and so on, with new development for every service.
- After MCP: there is now a common plug specification: "if you build to this spec, any AI connects right away." Once Notion, GitHub, Google Calendar, and others make a "plug" to this spec, an AI such as Claude can plug into it directly.

MCP is "a standard specification for connecting an AI to external services (tools)." If an API is "each individual order window," MCP is "those windows standardized so that they can be plugged into any AI app in the same way."

### What a beginner needs to know

- Ordinary users almost never need to build an MCP themselves.
- When you click a "Connect this service" button in a tool such as the [Claude Desktop](https://claude.com/download) app or [Claude Code](https://code.claude.com/docs/en/mcp), you are just using a connection that has already been built to the MCP spec.
- An MCP connection is **a channel that is always on across your whole account**. Once connected, the AI can
  reach that service at any time, and it is hard to see with your own eyes exactly how much scope is open for this task,
  or to switch it off and on per task.
- That is why this toolkit avoids MCP connections. For services that already have a
  REST connector (`scripts/connectors/`), such as mail, GitHub, Asana, and Notion, don't connect via MCP; use that connector
  instead. The reasons are in section 5 below; for actual usage see
  [`docs/05_external-services.md`](05_external-services.md).
  Use MCP only as a last resort, only when there is no alternative: a service for which a REST connector truly can't be built, or
  browser navigation where you must look at a web page directly.

---

## 3. What is an API key? ("An access badge")

To use an API (that is, to use the order window), you need to verify your identity. That is the API key.

> API key = a building access badge (employee ID)

- You need the badge to enter the building (the server) and receive service.
- The badge keeps a record of "who used how much," and you are billed for what you use.
- If you lose the badge (it leaks), someone else can come and go in the building under your name and run up costs, so **never show it to others or upload it to a public repository.**

### When you need an API key (optional/advanced)

- When you want to build your own program/script and automate AI features
- Example: "a bot that automatically summarizes 100 papers every week," "integrating AI features into a company's internal system"

### When you don't need an API key (most beginners)

- Just chatting in Claude.ai or the ChatGPT web/app
- In this case you only pay the monthly subscription fee (flat-rate).

---

## 4. Why we recommend a "subscription (flat-rate)" first

| Category | Monthly subscription (flat-rate) | API key (pay-as-you-go) |
|---|---|---|
| Billing | A fixed amount every month (e.g., [Claude Pro/Max](https://claude.com/pricing), ChatGPT Plus) | Billed for what you use (calculated in tokens) |
| Predicting cost | Easy: the same amount every month | Hard: swings with usage |
| Fit for beginners | Very suitable | Requires programming knowledge, with a management burden |
| Risk if you slip up | Almost none | Unexpectedly large costs possible from a leaked key, an infinite-loop script, etc. |
| Recommended for | General users, everyone who uses it by chatting | Developers, people who build automation programs themselves |

> Beware of pay-as-you-go billing: if you issue and use an API key, you are billed "for what you use." If a bug in your code repeats the same request thousands of times, or if the key leaks and someone else uses it without permission, an unexpectedly large bill can show up in a single day. Cases of "an API key was accidentally made public on GitHub and a big bill followed" are common.
>
> In practice:
> - For general use, always take a monthly subscription (flat-rate). The budget is clear, and a mistake doesn't add extra cost.
> - Treat an API key as an optional, advanced feature, for when you truly need it (automation scripts, etc.). Even then, be sure to set a spending limit.

---

## 5. Why this toolkit uses REST connectors as the default

MCP is convenient, but this toolkit uses REST connector scripts first.
Convenience and safety pull in opposite directions here.

| Category | MCP connection (a button) | REST connector (`scripts/connectors/`) |
|---|---|---|
| Access scope | Always connected across the whole account, so open even when unrelated to the current task | Only the amount that command requests, only at the moment the script runs |
| Token location | Inside the app (not directly visible) | `config/credentials.json` (gitignored) or an environment variable; I know where it is and can revoke it |
| Control over writes (send/delete) | Varies by service, hard to verify by eye | Each connector has a `--write`/`--send` gate, and the default is read/draft only (`AGENTS.md` §9) |
| When no longer needed | You must click a "Disconnect" button (easy to forget) | Just discard the token (rotate/revoke) and you're done |

Issuing tokens is not hard. In most cases, you log in via the browser →
go to account settings → click "Create personal access token" a few times and you're done, and `scripts/connectors/README.md`
lists where to issue the token for each service.

The practical principle is to avoid MCP and use REST connectors by default:
- For services that already have a connector, such as mail, GitHub, Asana, and Notion, don't connect via MCP; use that
  connector. If that service's MCP connection is already on, switch to the connector and disconnect it
  right away (the app's "Disconnect" button; it is an account-settings action you must click yourself).
- For services that don't yet have a connector (e.g., calendar, shared sheets), you can get by with MCP for now, but this too is
  not a "fine default"; it is a stopgap until a connector exists. When it becomes necessary, follow the guidance in
  `scripts/connectors/README.md` to build a connector and move over right away, and after moving over,
  disconnect that service's MCP too.
- Only exploratory tasks where you must look at web pages and click (browser automation) are an exception. Such work
  can't be replaced with REST, so MCP (the Chrome connection) is used as a last resort only in that case.

---

## 6. A short note on Codex

- [Codex](https://developers.openai.com/codex) is an AI tool (agent) made by OpenAI that helps write code. It is included in a ChatGPT subscription (Plus or higher), or you can also use it separately through the API.
- The principles in this document apply to Codex equally. For general code writing or asking questions, using it within a ChatGPT subscription is enough, and issuing and using a separate API key is an advanced option to consider only "when you want to integrate it automatically into my program/pipeline."
- Even when you use Claude Code and Codex together, "subscription-based use" is the default for each, and you add API integration only when needed.
