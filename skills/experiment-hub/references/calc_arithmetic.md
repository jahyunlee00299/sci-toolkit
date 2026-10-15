# One-off pipetting / dilution arithmetic (`reaction_matrix.py calc`)

Moved out of SKILL.md (Mode 1b) to keep SKILL.md under the size cap; the rule itself stays there.

Bench arithmetic done in prose goes wrong in the same two ways again and again: a top-up computed from the plan
instead of from what is already in the tube ("I already added 29.53, so add 1.5 more"), and a dilution factor
that ignores an earlier step (a 2-fold pre-dilution followed by the usual 10-fold is DF 20, not 10). A pipetting
number that someone will act on is never computed in a sentence.

Rule: every volume, top-up, C1V1 or dilution-factor number that goes to the bench or into a calculation comes
from `reaction_matrix.py` (workbook for a design, `calc` for a one-off), and the printed formula line is
quoted in the reply:

```bash
python reaction_matrix.py calc topup --target 31.03 --have 29.53   # add 1.5
python reaction_matrix.py calc df --stages 2 10                    # DF 20
python reaction_matrix.py calc df --sample 10 --total 80           # DF 8
python reaction_matrix.py calc c1v1 --c1 1000 --c2 100 --v2 50     # v1 5, diluent 45
python reaction_matrix.py calc topup-conc --have 0.8 --target 1.0 --vol 100 --stock 100
python reaction_matrix.py calc back --measured 0.17108 --df 20     # 3.4216
```

- Restate the physical state first, in one line, before computing: what is already in the tube (which
  version of the mix), what the target is, which dilution steps really happened. A user's "I already put
  X in" is the input; do not substitute the plan's amounts for it.
- DF = total / sample volume per step, and compound steps multiply. Back-calculated concentrations use
  the DF of THAT tube (a tube with 80 uL instead of 100 uL has DF 8, not 10).
- Exit 2 means the question is impossible as posed (overfilled, diluting upward, under- or
  over-determined): report that to the user instead of picking a number. Exact decimal arithmetic, no float noise.
- A design with many tubes still goes through the config workbook above, not a loop of `calc` calls.
