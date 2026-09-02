<!-- Moved verbatim from AGENTS.md on 2026-09-02 so that AGENTS.md stays under the 32 KiB that Codex reads (`project_doc_max_bytes`). AGENTS.md keeps a stub with the rules in force. -->

## 6. Model Routing Philosophy

Match model/agent capability to task difficulty — this saves cost and
often improves quality (a heavy model overthinking a trivial task can
introduce unnecessary changes).

- **Simple, mechanical, or shallow tasks** (read a file, run a lookup,
  extract a field, compare two short things, count something, apply a
  known formula) → use the cheapest/fastest model tier available.
- **Standard implementation work** (write a function, fix a bug with a
  known cause, refactor a single file) → use a mid-tier model.
- **Deep reasoning tasks** (architecture decisions, adversarial/security
  review, physics or numerical plausibility diagnosis, cross-validation
  of a scientific result, multi-objective optimization design) → use the
  strongest available model.
- Don't spawn a sub-agent/session at all for something answerable in one
  or two direct read/search calls — the overhead of spinning up a fresh
  agent context can exceed the cost of just doing it directly.
- When in doubt about which tier a task needs, err toward the cheaper
  tier for exploration/drafting, then escalate to the stronger model
  specifically for the verification pass (Section 2) — this pairs
  naturally with "distrust self-report."
- For adversarial/verification work, a single agent given the *entire*
  output to check is usually more reliable than splitting the check
  across multiple parallel agents (which risks truncation or
  contradictory partial views), unless the checks are on genuinely
  independent axes (different files, different methods) that don't fit
  in one context.

**Diagnose first, escalate second.** When troubleshooting an operational
failure (a service down, a broken connection, a failing request), run a few
direct, cheap diagnostic checks yourself before spawning an agent or an
automated workflow to investigate. Escalate to an agent only if the cause is
still unknown after those checks, or the fix genuinely needs autonomous
multi-step judgment.

**Using a second AI system that doesn't share your rules.** If you have access
to a second AI tool/agent that operates outside your normal rule/config
context (a different app, a different account, a sandbox that doesn't read this
file), do NOT use it as the first-pass executor for rule-dependent or
file-writing work — it will silently violate conventions (naming, safety,
formatting) it never saw.
- Use such a second system only as an independent adversarial *verifier* at
  high-error-cost checkpoints (a number about to enter a publication, a
  structural prediction, a citation list) — not for every task, and never give
  it write access to rule-critical directories.
- Any factual claim it produces (an identifier, a citation, a DOI) still needs
  cross-verification against a primary source before you trust it — don't chain
  trust through an unverified secondary tool.
