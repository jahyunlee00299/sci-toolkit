---
name: token-efficient-routing
description: >
  Route work to the cheapest model tier that can do it correctly, and verify the
  routing actually fires. Three-gate decision tree (spawn? → tier? → structure?),
  the inherited-model trap, hard-gate hook patterns with typo-safe killswitches,
  and log-based measurement before tightening or relaxing any gate. Use when
  tokens run low, when configuring agent/subagent model selection, or when
  building enforcement hooks. 한국어 트리거 — 토큰 아껴, 토큰 효율, 토큰 최적화,
  모델 라우팅, 소넷으로 돌려, 라우팅 개선, opus 아껴, 에이전트 모델 선택.
license: Proprietary
---

# token-efficient-routing

Spending a frontier-tier model on shallow work is the single largest silent token
leak in agentic setups. This skill encodes a routing doctrine that has been
measured in production: most waste comes not from explicit bad choices but from
**defaults** — unpinned subagents inheriting an expensive parent model, and
guidance text that drifts out of sync with the rules it claims to enforce.

## The three-gate decision tree

Evaluate in order. Each gate is a different axis — do not collapse them.

### Gate 1 — Spawn at all?

If the task ends in **one** Read/Grep/Bash call, or touches only a small file
(<500 lines) for lookup/confirm/find-replace: **do it directly in-session.**
A subagent carries a system-prompt overhead of roughly 10K tokens; for
single-call work the overhead exceeds the work. Common no-spawn cases: single
file read, one grep, `git log/diff/status`, one curl/pgrep, one ssh command.

Only work past that threshold (multi-file, large-file, repeated extraction,
QC sweeps) is a delegation candidate.

### Gate 2 — Which tier?

If spawning, match tier to task depth, not to habit:

| Task class | Tier |
| --- | --- |
| Trivial: count, list, rename, single extraction, logging | smallest (haiku-class) |
| Standard: multi-file edit, extraction sweep, QC, compare, non-deep review | mid (sonnet-class) |
| Deep: adversarial verification, physics/plausibility diagnosis, architecture, refactor trade-offs, cross-validation, optimization/fitting reasoning | frontier (opus-class) |

Two traps:

- **The inherited-model trap.** Omitting `model` on a subagent inherits the
  parent session's model. On a frontier-tier session, every unpinned spawn is a
  frontier-tier spawn. In one measured week this was the dominant leak — the
  majority of gate warnings were "model unspecified → inherited opus" on shallow
  tasks. Always pin `model` explicitly on shallow spawns.
- **Forks don't save.** A forked agent inherits the parent model by design;
  forking for shallow work has zero savings. Use a fresh agent with an explicit
  cheap tier.

### Gate 3 — Orchestration structure (deep work only)

- Single deep agent is the default — no team ceremony for one hard question.
- Fan-out (N agents → verify → synthesize) only when ALL of: autonomy needed,
  adversarial verification needed, and ≥3 truly independent axes.
- Adversarial verification default = **one** agent given the full artifact
  (avoids truncation and cross-agent contradiction). Multi-agent verify only
  when the axes are genuinely independent (different files, different checks,
  unanswerable in one prompt).
- In workflows, pin `model`/`effort` per `agent()` call: cheap tiers for
  mechanical stages, frontier only for the hardest verify/judge stages.

## Enforcement: the gate-hook pattern

Advice decays; gates persist. Enforce Gate 2 with a PreToolUse hook on agent
spawn calls:

1. Parse the requested model. If absent, **recover the inherited model from the
   session transcript** — an unpinned spawn is not exempt, it is the main case.
2. Classify the task prompt as shallow (extract / compare / count / QC /
   find-replace / lookup / logger / paper-read) vs deep-justified (adversarial
   verify / plausibility diagnosis / architecture / optimization reasoning).
3. Shallow + frontier-tier → block with a message that names the fix
   (`re-spawn with model="sonnet"`) and the exemption path (state the deep
   signal in the prompt if it is genuinely deep).

Three hard-won implementation rules:

- **Typo-safe killswitch.** Parse the gate's env flag tri-state
  (`block` / `warn` / `off`), and map any *unknown* value to `warn`, never
  `off`. A gate that silently disarms on a config typo is how a hard block sat
  inert for weeks while its flag said `"warn"` and the code compared `== "1"`.
- **One keyword SSOT.** If a prompt-side router (UserPromptSubmit classifier)
  and a spawn-side gate (PreToolUse) both classify text, they must load the
  same keyword list from one file. Two hardcoded lists drift, and the failure
  mode is self-contradiction: the router advises a frontier tier for a deep
  prompt while the gate blocks it — and the retry round-trip is pure waste.
- **Fail-open on infrastructure faults.** A missing helper, unreadable json, or
  unparsable payload must never stop the session; the gate judges only when it
  can actually judge.

## Prompt-side routing (advisory layer)

A UserPromptSubmit classifier (keywords + word count, zero API calls) that tags
each prompt trivial/standard/deep and injects one short guidance line for
shallow prompts ("delegate past the one-call threshold to a sonnet-class agent;
handle single-call work directly") keeps the doctrine in front of the model
without a human remembering it. Keep injections conditional and short — an
unconditional injection is itself a per-turn token cost.

## Measurement discipline

- **Wiring is part of the feature.** A gate is not delivered until it is
  registered in the hook config AND fired once against a synthetic payload
  (expect the block exit code) plus a should-pass payload (expect 0). A
  wired-but-never-fired gate and a written-but-never-wired gate look identical
  from the outside: both produce nothing.
- **Log every fire; decide from logs.** Record block/warn events with the
  triggering keywords. Relax a gate only when logs show false positives, and
  tighten only when logs show leaks — never from impression. (Measured example:
  136 shallow-on-frontier warnings in one week justified promoting warn→block;
  the same logs later separate false blocks from true saves.)
- **Zero output is ambiguous.** A gate that never fires may be healthy or dead.
  Re-run the synthetic-payload test after any config sync or refactor.

## Anti-patterns (all observed, all measured)

- Spawning an agent for a one-read question (overhead > work).
- Unpinned subagents on a frontier-tier session (the dominant leak).
- Forking to "save" on shallow work (inherits parent tier — saves nothing).
- Verifying everything with a frontier tier; verification tier follows the
  claim's cost, not a habit.
- Guidance text hardcoding a threshold that a rules doc later changed —
  injected advice must quote the SSOT, not restate it.
- A gate flag value the parser doesn't recognize (`"warn"` vs `== "1"`)
  silently disarming enforcement.
