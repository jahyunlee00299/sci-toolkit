# Phase 2 — Dual DOI verification common findings

Measured distribution from a real thesis review run (34 refs), useful for calibrating how much
of a batch will typically need Phase 3 hallucination recovery:

- Hallucinated DOI (resolves to wrong paper): ~10% of refs
- Title hint paraphrased/wrong despite valid DOI: ~5%
- DOI 404 (typo in identifier): ~3%
- Unresolved (no DOI, search no match): ~25%
- Clean: ~55%
