---
name: experiment-hub
description: Integrated skill for experiment protocol management, condition optimization, experiment proposal, history recording, and experiment comparison. Use when planning, recording, or reviewing lab experiments. For analyzing data from completed experiments use lab-data-analysis; for statistical testing of results use stats-workflow; for primer/cloning design use primer-design.
license: MIT
---

# Experiment Hub

First read the ~/.claude/commands/research-commons.md file and familiarize yourself with the common rules (citation style, Storage key system, skill integration, trigger branching), then execute the skill below.

Integrated skill for experiment protocol management, condition optimization, experiment proposal, history recording, data visualization, pattern analysis, and experiment comparison.

## Mode Detection -> Execution

Determine the mode from the user request and execute the corresponding procedure.

| Mode | Trigger Example | Core Procedure |
|------|----------|----------|
| **1. Protocol** | "Create a protocol" | Confirm purpose -> Search method references (auto-call research-search) -> Write template -> Enter conditions |
| **2. Optimization** | "How to increase conversion rate?" | Current data -> Select objective/variables -> Choose strategy (OFAT/DoE/RSM) -> Generate experiment matrix |
| **3. Proposal** | "What should I do next?" | Gap analysis -> Literature reference -> Prioritized experiment proposals -> Link to Mode 1 upon acceptance |
| **4. Record** | "Record the results" | Structure conditions/results -> Detect outliers -> If same protocol exists, propose comparison |
| **5. Visualization** | "Draw a graph" | Data -> generate graph / Image -> extract data + auto-fit trendline |
| **6. Pattern Analysis** | "Why these results?" | Variable-result mapping -> Pattern classification -> Quantitative trendline analysis -> Per-variable interpretation -> Causality assessment |
| **7. Comparison** | "Compare with previous experiment" | Identify changed variables -> Result comparison table -> Calculate delta values -> Trend graph -> Analyze cause of difference |

**Auto-chain**: Record(4) -> Comparison(7) -> Pattern Analysis(6) -> Visualization(5) -> Optimization(2)

> **Branching criteria** (COMMONS.md): Data/statistics = here (M6/M7), Mechanism/context = research-discussion (M1/M2)

---

## Mode 1: Protocol -- Auto-search Method References

When writing a protocol, automatically search 3 categories to establish condition rationale:

| Category | Search Target | Applied Items |
|---------|----------|----------|
| Paper methods | Experimental methods from similar reaction papers | Reaction conditions, time, concentration |
| Analytical protocols | HPLC/GC/UV analysis conditions, kit manuals | Mobile phase, column, detection wavelength |
| Manufacturer datasheets | Enzyme/reagent optimal conditions | Optimal temperature/pH, activity units |

- Search results are **suggested defaults**, not forced
- If user selects different conditions, note as "changed from reference"
- Record source in protocol (for future citation)

Protocol format: ID (PROT-{N}), version, reference methods, materials, methods (step-by-step), analysis, safety/disposal, change history.

---

## Mode 2: Optimization Strategy Selection Criteria

| Condition | Strategy |
|------|------|
| 1-2 variables, clear bottleneck | OFAT |
| 3-4 variables, interaction suspected | Full/Fractional Factorial DoE |
| 3+ variables, optimum search | RSM / Central Composite Design |

Output: optimization variables (range/current value), experiment matrix (conditions per run + objective), estimated experiment count/duration.

---

## Mode 5: Trendline Auto-selection Rules

| Data Pattern | Trendline Type |
|------------|-----------|
| Monotone increase/decrease | Linear regression (y = ax + b) |
| Saturation/plateau curve | Nonlinear (Michaelis-Menten etc.) |
| Optimum point exists | Quadratic polynomial |
| Exponential change | Exponential fit |
| Points < 3 or R-squared < 0.5 | No trendline |

Required output: equation, R-squared, key points (maximum/saturation/inflection point).

---

## Mode 6: Pattern Classification Criteria

- **Increase** (positive correlation): linear / diminishing returns
- **Decrease** (negative correlation): linear / threshold collapse
- **Optimum**: left-right symmetric/asymmetric
- **Plateau/Saturation**: saturation reached vs reaction-limited
- **Outlier**: experimental error vs new phenomenon

Causality strength: 5 stars (dose-response + mechanism + reproducibility) to 1 star (insufficient data)

---

## Skill Integration

- exp:log -> research-discussion interpretation (M1)
- exp:pattern -> research-discussion comparison (M2)
- disc:action -> protocol generation (M1)
- experiment proposal (M3) -> research-search for literature (M1)
- exp:result/viz -> manuscript-writer Results/Figure
- ms:revision -> additional experiment protocol (M1) trigger

## Biotechnology Experiment Specialization

- **Enzyme reactions**: Substrate preparation -> enzyme addition -> reaction -> sampling -> analysis
- **Multi-enzyme cascade**: Optimal condition matrix per enzyme
- **Whole-cell catalysis**: Includes OD, permeabilization, aeration conditions

## Notes

- Optimization proposals are statistical suggestions; experimental validation is mandatory
- Always note that trendline extrapolation has low reliability
- Graph-to-number extraction is approximate; consulting original data is recommended

User request: $ARGUMENTS
