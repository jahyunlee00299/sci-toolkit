---
name: research-ideation
description: Unified research ideation skill covering brainstorming, critical evaluation, hypothesis formulation, and result discussion. Use when brainstorming ideas, evaluating evidence quality, formulating testable hypotheses, or discussing experimental results against literature. For finding and retrieving papers use research-search; for writing a full literature review document use literature-review; for formal peer-review writing use manuscript-pipeline.
---

# Research Ideation — Meta-Skill

Integrates: `scientific-brainstorming` + `scientific-critical-thinking` + `hypothesis-generation` + `research-discussion` + `research-commons`

## Trigger

Use when:
- Brainstorming new research directions
- Evaluating experimental observations critically
- Formulating testable hypotheses from data
- Discussing results against published literature
- Designing follow-up experiments

## Phase Flow

```
Observation/Idea
      ↓
Phase 1: Brainstorm  →  Phase 2: Critical Evaluation
                                      ↓
                         Phase 3: Hypothesis Formulation
                                      ↓
                         Phase 4: Discussion & Literature
                                      ↓
                         Phase 5: Experiment Design
```

---

## Phase 1 — Brainstorming

- Generate 5–10 candidate ideas from the observation
- Explore interdisciplinary connections (biochemistry ↔ engineering ↔ computation)
- Challenge core assumptions: "What if X is not the cause?"
- Identify analogues from other fields

**Output:** Ranked list of ideas with rationale

---

## Phase 2 — Critical Evaluation

Assess each idea against:
- **Bias risks**: confirmation bias, selection bias, confounders
- **Design flaws**: lack of controls, small N, multiple comparisons
- **Evidence quality** (GRADE-style):
  - High: RCT, replicated mechanistic data
  - Moderate: controlled observational
  - Low: case report, expert opinion
- **Feasibility**: reagents, time, expertise available

**Output:** Each idea rated High / Medium / Low priority with reasoning

---

## Phase 3 — Hypothesis Formulation

Structure each hypothesis as:

```
IF [condition/intervention]
THEN [measurable outcome]
BECAUSE [mechanistic rationale]
MEASURED BY [specific assay or metric]
FALSIFIED IF [result that would disprove it]
```

Include:
- Null hypothesis (H₀)
- Alternative hypothesis (H₁)
- Expected effect size and direction
- Required controls

---

## Phase 4 — Literature Discussion

- Compare results to 3–5 most relevant published studies
- Identify agreements and discrepancies
- Propose mechanistic explanations for discrepancies
- Contextualize within current field consensus

**Citation format:** Author et al. (Year) *Journal* — key finding in one sentence

---

## Phase 5 — Experiment Design

For each accepted hypothesis:
1. Primary assay and readout
2. Control conditions (positive, negative, vehicle)
3. Sample size estimate (power ≥ 0.8, α = 0.05)
4. Statistical test (→ route to `stats-workflow` if needed)
5. Timeline and dependencies

---

## Replaces

- `deprecated/scientific-brainstorming` — open-ended ideation
- `deprecated/scientific-critical-thinking` — evidence evaluation, bias detection
- `deprecated/hypothesis-generation` — structured hypothesis formulation
- `deprecated/research-discussion` — result interpretation and literature comparison
- `deprecated/research-commons` — shared citation and storage conventions
