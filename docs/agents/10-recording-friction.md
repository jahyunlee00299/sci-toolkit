<!-- Moved verbatim from AGENTS.md on 2026-09-02 so that AGENTS.md stays under the 32 KiB that Codex reads (`project_doc_max_bytes`). AGENTS.md keeps a stub with the rules in force; this file is the full text. -->

## 10. Recording Friction — when the toolkit itself is the problem

Most friction with a tool gets worked around silently and then forgotten.
The workaround lives in one person's head, and the next person hits the same
wall. A recorded complaint is the only kind that can be fixed.

**Trigger.** The user says something in this toolkit is broken, confusing,
missing, or simply annoying — "이거 왜 안 되지" [why doesn't this work], "자꾸
실패해요" [it keeps failing], "이런 게 있으면 좋겠는데" [it'd be nice if there were
something like this], "this is confusing", "it keeps failing". This includes
the case where you have already solved their immediate problem: the
workaround is *evidence*, not a reason to skip the record.

**What to do.**

1. **Fix or unblock them first.** The record is not a substitute for helping.
2. **Ask at most one question** — whatever you genuinely cannot infer from the
   conversation (usually "what did you expect to happen instead?"). Then stop
   asking. Interrogating someone who is already frustrated is how you get zero
   records. An incomplete record beats no record.
3. **Record it**, filling in what you already know from context:

   ```bash
   python scripts/feedback_log.py add "<what went wrong, in their words>" \
       --kind bug --skill <skill name> \
       --expected "<what they wanted>" --actual "<what happened>"
   ```

   `--kind` is one of `bug`, `friction`, `missing`, `docs`, `idea`.
   Everything except the first argument is optional; omit what you don't know
   rather than guessing.
4. **Tell them it was recorded**, in one line. People stop reporting things
   when reports seem to vanish.

**Where it goes.** `out/feedback.jsonl`, a local file. No account, token, or
network access is required — that is deliberate. Someone who received this
toolkit on a USB stick must be able to record a problem on day one.

**Promotion (maintainers).** Whoever maintains the toolkit collects the records
later:

```bash
python scripts/feedback_log.py list --pending
python scripts/feedback_log.py export                       # print issue bodies
python scripts/feedback_log.py export --github --repo owner/name --write
```

Each exported issue carries its origin (record ID, timestamp, OS, Python and
Claude Code versions) so it can be reproduced without going back to ask.
Per §9 this is an outward action: without `--write` it only previews.

**Do not** record another person's private data, credentials, or unpublished
research content in a feedback entry — it is written to a file that is meant to
be shared upward. Describe the failure, not the material it happened to.
