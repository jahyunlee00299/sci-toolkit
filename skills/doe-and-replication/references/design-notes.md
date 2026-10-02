# Design notes — DoE and replication

Depth behind `SKILL.md`. Run counts below were produced by
`scripts/doe_designs.py` with pydoe 1.5.0.

## Fractional factorials and aliasing

`fractional_factorial(factors, generator)` takes pydoe's Yates notation. For
five factors in 16 runs, `"a b c d abcd"` sets factor E equal to the ABCD
interaction (defining relation I = ABCDE, resolution V): main effects are
aliased only with four-factor interactions and two-factor interactions only
with three-factor ones, so a 5-factor study fits main effects and all
two-factor interactions in 16 runs instead of 32.

| Resolution | Main effects aliased with | Use |
|---|---|---|
| III | two-factor interactions | pure screening, expect to follow up |
| IV | three-factor interactions (two-factor ones alias each other) | screening with some safety |
| V | four-factor interactions | main effects and two-factor interactions are clean |

`plackett_burman` gives main effects only: 12 runs for up to 11 factors. A
factor that looks inactive in a low-resolution design may be two effects
cancelling; confirm with a follow-up before dropping it.

## Response surfaces for three factors (pH x temperature x NAD ratio)

| Design | Runs here | Points sit at | Pick it when |
|---|---|---|---|
| CCD circumscribed (default) | 20 with `center=(4, 2)` | axial points OUTSIDE the stated box | the box is a region of interest, not an operating limit |
| CCD inscribed | 20 | everything inside the box; factorial corners pulled in | the box is a hard limit (enzyme denatures, buffer range) |
| CCD faced | 20 | axial points on the faces of the box | three levels per factor, corners kept |
| Box-Behnken (`center=3`) | 15 | edge midpoints, no corners | extreme corners are infeasible or wasteful |

A circumscribed CCD on pH 6 to 8 reaches pH 5.37 and 8.63: always read the
column minimum and maximum before ordering buffers. Center runs estimate pure
error and test aggregate curvature; they do not identify each quadratic term,
the axial runs do. The fit itself (quadratic model, lack-of-fit test) is a
regression job: `statsmodels`, then `scientific-validation` for whether the
predicted optimum is physical.

## Blocking in a plate-reader or HPLC campaign

- Treat plate, day and instrument session as blocks. Put every condition of
  interest on every block, or at least a shared reference condition on every
  plate to estimate and subtract the plate offset.
- Randomize within a block, never across blocks that cannot be mixed. The
  wrappers shuffle globally, so keep a `block` column and shuffle per group
  yourself (`groupby("block")` and a seeded `permutation`).
- For an HPLC sequence interleave a standard every ~10 injections and
  randomize the sample order; drift then shows up as a trend in the standards
  instead of hiding inside a condition.
- Technical replicates inside a block reduce pipetting noise; they never
  replace independent preparations for a claim at the preparation level.

## Reproducibility record (put it in the lab-record EXP)

Design type and generator string, factor ranges and face option, seed, pydoe
and numpy versions, the exported CSV, and which column is the replicate unit.
