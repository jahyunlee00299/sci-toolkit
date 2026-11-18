# Tm, annealing temperature and cycling for designed primers

A primer set can pass the primer3 QC (no FAIL, hairpin/heterodimer only marginal) and still be a poor
order. Check these before declaring the set ready.

## Tm scale
- The module's default Tm uses generic salt/primer conditions (about 50 mM Na+, 2 mM Mg2+, 500 nM).
  High-fidelity polymerase buffers (e.g. Q5) differ, and the vendor's Tm calculator can give clearly
  different values. Label every number as "module Tm" and tell the user to confirm Ta with the vendor
  calculator for the polymerase actually used.
- Never present a calculated Tm-derived value as a program setting. Report calculated Tm and the
  recommended cycling program separately.

## Cycling for high-Tm primers
- Annealing step must not exceed the extension temperature in a 3-step program. If the recommended Ta
  is at or above the extension temperature (primer Tm roughly >= 72 C for Q5), use a 2-step program
  (denature, then combined anneal/extend) rather than writing an annealing step above extension.
- GC-rich blocks (common primer GC near 75% or more): suggest GC enhancer or DMSO and a 2-step program.

## Tm spread inside a block (iPCR / back-to-back)
- Primers of one mutagenesis block share a PCR program, so compute min/max Tm per block and across
  blocks. A spread of more than about 3 C within a block, or several C between blocks that must run
  in the same program, is a design problem even when QC passes.
- Find which oligo pulls the block minimum down; it is often the shared (common) primer.
- Fix by extending the free 3' end of that common primer. In back-to-back designs the 5' ends are
  fixed by the junction, so 3' extension keeps the abutting junction and the template-identical
  common primer adds no codon risk. Leave the mutant primers untouched.
- Re-run QC (hairpin, homodimer, heterodimer, 3' clamp, homopolymer runs) after any extension.
- Check the design topology matches the user's order sheet (overlapping KLD-style vs non-overlapping
  back-to-back with PNK); `iPCRSubstDesigner` rules apply only to the topology it implements.
