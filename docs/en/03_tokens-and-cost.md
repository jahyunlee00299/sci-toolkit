> English translation of [03_토큰과_비용.md](../03_토큰과_비용.md). The Korean original is canonical; if they differ, the Korean version wins.

# 03. Tokens and Cost: Why Some Conversations Cost More and Others Less

This document explains the concept of the token, which you must understand when using Claude (and most LLM tools).
Once you understand tokens, you can answer questions like "Why did that last question take so long?" and "Why is my usage so high this month?" on your own.

---

## 1. What is a token? ("A piece of text, which is money")

An AI model doesn't read a sentence as a whole. It cuts the sentence into small pieces called tokens and processes those.

- A token can be a whole word, part of a word, or a single space or punctuation mark.
- In English, roughly "one word ≈ 1 to 1.3 tokens," but Korean tends to be split into finer, character-level pieces, so it is common for a sentence with the same meaning to produce more tokens than in English.
- A rough feel (the exact count differs by model, but this gives you a sense):
  - `"안녕하세요"` ("hello" in Korean) → roughly 3 to 5 tokens
  - `"Hello"` → roughly 1 to 2 tokens

How tokens become cost:

AI services usually [set prices](https://platform.claude.com/docs/en/about-claude/pricing) based on the number of input tokens + the number of output tokens. That is:

- The question I sent, the code I attached, the whole conversation history → input tokens
- What the AI answered → output tokens

Cost arises for the sum of the two, so the number of tokens is the cost. If you paste a long document whole and ask a question, that entire document is counted as input tokens every time.

### Why does a session get more expensive the longer it goes?

To "remember" earlier conversation, a conversational AI feeds the entire conversation so far back into the model on every turn. That is:

- 1st question: input = 1 question
- 2nd question: input = question 1 + answer 1 + question 2 (cumulative total)
- 10th question: input = all 9 prior turns + question 10

So the longer a session goes, the more the input tokens per turn snowball. (There is a technique called "caching" that eases this problem, but the direction of the conversation continuing to pile up doesn't change.)

---

## 2. How do I see my usage? (`/usage`)

Claude Code (Claude used in the terminal) lets you check your [current usage and limits](https://code.claude.com/docs/en/costs) with the `/usage` command.

```
/usage
```

When you enter this, you can see information roughly like the following.

- How much you've used during the current period (e.g., a 5-hour window, or weekly)
- What percentage of your limit remains
- When the limit resets

Tips for beginners

- Always check the exact numbers directly with `/usage`. Rather than judging by "it feels like I used a lot/a little," it is important to build the habit of looking at measured values.
- If your usage suddenly spikes, it is usually one of the following.
  1. You pasted a very long file/document whole
  2. You dragged a single session (conversation) out for too long
  3. You kept using a more powerful (expensive) model than needed for a simple task

---

## 3. How to use it sparingly: 3 habits for beginners

### (1) Give simple jobs to a cheaper model

[Models come in tiers](https://code.claude.com/docs/en/model-config). They are commonly divided into "light and fast models" and "heavy and smart models," and the price difference is considerable.

- Simple tasks (typo checks, simple summaries, reading one file and answering, format conversion) → a cheap, fast model is enough.
- Hard tasks (complex code refactoring, design decisions that span multiple files, rigorous logical verification) → you need a smarter but more expensive model.

You don't need to use the most expensive model for every question. Choosing a model that fits the difficulty of the task changes your costs greatly.

### (2) Split long sessions

If you ask all sorts of things in a single chat window all day, then because of the "cumulative input tokens" problem explained earlier, each turn gets more expensive the further you go.

- It is good to move to a new session at the point where the topic changes, or when one stage of work ends.
- Example: when "fixing a code bug" is done, start a new session for the next job, "writing a document."
- If previous context that is no longer needed (e.g., an error log that is already resolved, file contents you no longer use) keeps piling up mid-conversation, it is cheaper and faster to wrap up the session and start fresh.

### (3) Before pasting, ask once: "Do I need all of this?"

- Show only the relevant part, not the whole file
- Paste only the part where the error occurred, not the whole log
- Start fresh for a conversation that already has its answer

Following these three habits cuts unnecessary token (= money) waste.

---

## 4. (Reference) How we use these principles in tool automation

Below is a publicly shareable explanation of how this project actually uses the token/cost concepts in automation. It does not include actual usage figures, billing/settlement information, or personal server scripts.

### 4-1. The principle of measuring tokens: "read the session logs directly"

Tools such as Claude Code store conversation sessions locally as log files (JSONL format: a file that records one message per line as JSON). Inside these logs, the number of input/output tokens used on each turn is recorded too.

That means "How many tokens did I use in this session?" can be answered not by estimation but by parsing the log files and totaling the actual numbers. What the `/usage` command shows is, in the end, a summary of this kind of measured data. The key is the principle of "not judging by feel, but reading the recorded facts."

### 4-2. The idea of model routing: "place the model that fits the difficulty of the job"

Before handing off a task, first judge "is this job easy or hard?"

- Easy jobs (simple lookups, checking one file, routine repetitive work) → assign to a cheap, fast model
- Hard jobs (design decisions across multiple files, adversarial verification, and other work needing deep reasoning such as diagnosing physical/logical validity) → assign to a more powerful model

Assigning different models by task difficulty like this is called model routing. For people, it is the same principle as "simple inquiries go to a new hire, complex decisions go to an expert." This keeps overall quality while lowering the average cost.

### 4-3. The idea of a verification gate: "don't trust a result as is; check it once more"

If the same party that produced a result (code, calculation, text) reviews it themselves, they easily miss their own mistakes. So for important deliverables, we make them pass through a separate, independent checking step. This is called a verification gate.

The procedure has three steps.

1. Produce the result
2. Check it again with an independent view (one not stuck in the same context)
3. If there's no problem, it passes; if there is, send it back and fix it

This procedure matters especially for work that is hard to undo (e.g., an email that is actually sent), where numbers must be exact (e.g., calculation results), or where mistakes accumulate and become hard to find later, as with code. Saving cost matters, but trusting a wrong result and moving on is the bigger cost in the long run, so the principle is not to finish everything with only a cheap model or a single check, but to put in a verification step where it is needed.

### 4-4. (Optional) When calling Claude from a script: "the API if you have a key, `claude -p` if not"

Sometimes a script you wrote needs to ask Claude one simple question, such as "summarize this text in one line." There are two ways to call it.

| Method | Where the charge comes from | What you need |
|---|---|---|
| Anthropic API | Deducted from my API credits for what I use (a small model usually costs well under 1 won per request) | `ANTHROPIC_API_KEY` environment variable |
| `claude -p` | Consumes my Claude subscription limit (a base setup-token overhead is added even for small jobs) | Claude Code logged in as usual |

`scripts/llm_call.py` chooses between these automatically. If a key exists it uses the API first, and if there is no key, credits have run out, or the internet is unstable, it falls back to `claude -p`. It works even without a key, so setting one is not required.

```python
import sys; sys.path.insert(0, "scripts")
from llm_call import complete
print(complete("다음 문장을 한 줄로 요약해줘: ...", max_tokens=200))
```
(The prompt string above is Korean for “Summarize the following sentence in one line: ...”.)

- You issue the key yourself in the [Anthropic console (console.anthropic.com)](https://console.anthropic.com/) and put it in the `ANTHROPIC_API_KEY` environment variable. **Do not paste the key into code, documents, or chat.**
- If you set the environment variable `LLM_CALL_API=0`, it skips the API and always uses `claude -p`.
- If you set the environment variable `LLM_CALL_LOG=file path`, one line per call (which route was used, and the token count) is recorded.
- Using tools, touching files, and running skills are not what this helper is for. For those, use `claude -p` directly.

---

## Summary

| Concept | One-line description |
|---|---|
| Token | The smallest unit in which an AI processes text. Also the basis of cost |
| `/usage` | The command to check my actual usage and limits |
| Model choice | Easy job = cheap model, hard job = strong model |
| Session management | The longer a conversation, the more expensive → start a new session when the topic changes |
| (Advanced) Token measurement | Parse session logs (JSONL) and total the actual numbers |
| (Advanced) Model routing | Automatically assign different models by task difficulty |
| (Advanced) Verification gate | Check important results once more, independently |
| (Optional) `scripts/llm_call.py` | A script's simple question: the API if you have a key, `claude -p` if not |
