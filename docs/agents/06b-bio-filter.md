<!-- Moved verbatim from AGENTS.md on 2026-09-02 so that AGENTS.md stays under the 32 KiB that Codex reads (`project_doc_max_bytes`). AGENTS.md keeps a stub with the rules in force; this file is the full text. -->

## 6b. Life-science requests can be blocked ABOVE the model

Molecular-biology, primer-design, and enzyme-engineering prompts can be refused
by a provider-side safety classifier **before any model reads them**. On the
Anthropic API this surfaces as an API error carrying `Details: [bio]`. It is not
the assistant declining — nothing in the prompt was reasoned about, so framing,
credentials, or an institutional preamble have no effect on the outcome.

Measured over 16 calls (2026-08-26). Reproduce before trusting any of it:

| Property | What was measured |
|---|---|
| Deterministic | One blocked prompt re-sent unchanged 3x → 3/3 blocked. A bare retry is always wasted. |
| Whole-call kill | A 5-question batch died entirely; the same questions sent one-per-call returned 11/12 answers. There is no partial refusal. |
| Legitimate vocabulary mostly passes | `virulence factor`, `toxin`, `pathogenic isolate`, `lethal dose`, `knockout` all returned full technical answers. |
| Real boundaries still hold | A request to increase a toxin's potency was blocked. That is correct, and a tactic that unblocked it would be a bad tactic. |
| Rewording is NOT a lever | Same question, two phrasings: the naive wording passed; the "sanitized" academic wording was blocked 3/3. |

### Operating rules

1. **One request, one subject.** The only lever with a measured, consistent
   direction. Never bundle several life-science questions into one delegated
   call — one flagged item kills all of them and you cannot tell which.
2. **Never re-send a blocked prompt unchanged.** Split it instead.
3. **Do not self-censor standard terminology.** Rewriting normal scientific
   vocabulary wastes effort and, per the measurement above, can make it worse.
4. **Read the error text — the forms mean opposite things.**
   - Language admitting the safeguards are broad and "can sometimes flag
     legitimate coding, cybersecurity, and biology tasks" → false positive.
     Split, retry, and report it.
   - A terse "can't help with this" with no such language → real boundary. Do
     not retry, do not reword, do not switch models looking for one that
     answers. Say so plainly and stop.
5. **Do not shop for a model tier that answers a blocked prompt.** Requesting a
   smaller model did not evade the classifier in testing (the call was served by
   the larger model anyway, as dual-use prompts fall back). Whether a genuinely
   smaller served tier would pass was never tested — treat tier-shopping as out
   of bounds regardless, and downgrade only for cost or latency.
6. **A blocked branch is UNRUN, not empty.** In a parallel fan-out, a blocked
   sub-agent returns nothing, which reads as "no findings". Before believing an
   empty result, check its error text for the block tag.

### Report false positives — the only upstream fix

The provider's own support material states that reports of incorrectly blocked
requests are what narrow the safeguards, and the error text names the reporting
channel (`/feedback` in Claude Code). Capture the request ID from the error and
file it; batching several IDs of the same kind into one report carries more
signal than singletons.

A small triage script is worth keeping: classify the two error forms, extract the
request ID, and append false positives to a log so the backlog is visible.
**Record only false positives — never file a report about a correct refusal**,
which is noise in the one channel that fixes the cause. Anchor the classification
on the error line itself rather than the whole pasted blob; judging surrounding
context lets a genuine boundary be misfiled as reportable.

> No dual-use biology allowlist is generally available at time of writing. Note
> that credit-grant research programs typically do **not** exempt anyone from the
> usage policy — do not present one internally as a bypass route.
