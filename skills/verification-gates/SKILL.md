---
name: verification-gates
description: Router for the seven mechanical verification gates that run before a number is trusted - compat-check (environment), provenance-check (data source), fiducial (parameters in code), regress-check (results), endnote_library_audit (references), canon-gate (recorded lab constants), bio-constants (database claims) - with one shared 0/1/2 exit contract. Use to decide which gate holds at the current moment and how to report it. Triggers - "검증 게이트", "검증 돌려", "4축", "5축", "출처 확인", "골든", "회귀 확인", "fiducial 돌려", "서지 검증", "표준값 확인", "분자량 확인", "UniProt 대조", "Keq 대조", "which gate", "verify this number".
license: MIT license
metadata:
    skill-author: Lab Researcher
---

# verification-gates

A routing layer. The tools carry the logic; this skill says which one holds when. The
gates are **not a pipeline**: each fires at a different moment, and none replaces the
judgment checks in `scientific-validation`.

## Shared contract

`0` clean · `1` violations · `2` cannot check (empty declaration, zero files, unreadable
source). **Exit 2 is never "fine".** A gate that checked nothing has not passed: report
it as BLIND, never fold 1 and 2 into one word, and never write "all gates pass" unless
every gate you ran returned 0.

## Which gate now?

| axis | question | tool (skill) | holds when |
|---|---|---|---|
| ① environment | will it install and run here | `compat-check` | once, before adopting a dependency or foreign repo |
| ② data | which dataset produced this constant | `provenance-check` | new raw data landed, or a constant was refit or pasted |
| ③ parameters | is this number allowed to be hard-coded here | `fiducial` | before every commit that carries numbers |
| ④ results | does it come out the same way twice | `regress-check` | before a number leaves the session (manuscript, report, email) |
| ⑤ references | is the citation record itself intact | `endnote-citation-injection/endnote_library_audit.py` | a manuscript's references are about to be trusted, or an EndNote import just ran |
| ⑥ lab constants | does this config contradict a recorded researcher decision | `experiment-hub/canon_gate.py FILE` | a pipetting config or Params sheet is about to be used at the bench |
| ⑦ database constants | does a claimed protein mass, length, EC, PDB fact or equilibrium constant agree with UniProt, PDB, Rhea, eQuilibrator | `bio-constants` (`bio_const.py check bio_claims.toml`) | a number was copied from a database and is about to leave the session: list it as a `[[claim]]` with an explicit unit |

Decision by moment:

1. Bringing in code you do not own → ① first. If ① exits 1 or 2, a clean ③ on that clone
   means little (③ reads the source, it does not run it). Say which exit each gave.
2. A fit finished, or a constant was pasted into params → ② (`provenance-check check provenance.toml`).
3. About to commit code that carries numbers → ③ (`fiducial check`; run it from the
   repo being checked, never from a directory that contains a `fiducial/` folder).
4. A critical number is about to leave the session (manuscript number, converged fit or
   optimizer parameters, a correctness-critical commit, a number from a remote machine)
   → ④ (`regress-check check --explain`). A moved number is explained by the ③ and ②
   output, not argued.
5. A manuscript's references are about to be trusted, or an EndNote import just ran → ⑤
   (`python skills/endnote-citation-injection/endnote_library_audit.py`; `--offline` runs the
   author axis alone, `--doi-limit N` bounds the network pass). It audits the whole LIBRARY,
   which is the gap the docx-side gates leave: a DOI validator only sees the DOIs of the
   document it is given, so a record that no manuscript cites yet is never checked.
6. A pipetting config or a pipetting/methods workbook (Params sheet) is about to be used at the
   bench, or a researcher just decided an experimental constant → ⑥ (`canon_gate.py FILE`; 1 =
   contradicts a canonical entry, 2 = BLIND, a WARN about a differing working stock is not a
   failure). A new decision is recorded by editing the canonical constants file with value,
   date, who decided and what it supersedes, never by loosening the checker. A hand-built
   workbook with no Params sheet is BLIND.
7. A number copied from UniProt, PDB, Rhea or eQuilibrator (mass, length, EC, resolution, Keq)
   is about to be trusted → ⑦ (`python -I skills/bio-constants/scripts/biodb/bio_const.py check bio_claims.toml`).
   A tag-corrected mass (His-tag etc.) is a documented MISMATCH, not a tool error; the
   eQuilibrator `web` route is corroboration (its 1-sigma band can be very wide), only
   `--source package` is a precision check. Hand the output to the verifier.
8. Whatever the gates cannot decide (physical plausibility, identifiability, mass
   balance, claim versus source) → `scientific-validation`. For a multi-axis or
   high-stakes claim, hand the gate output to ONE independent verifier agent instead of
   re-deriving it; a self-review is not a verification.

## Anti-shortcut rules (encoded in the tools; do not route around them)

- Freezing a golden needs a reason (`regress-check freeze --reason ...`); the history is the audit trail.
- A widened tolerance is a violation until re-frozen with a reason. Never loosen `rtol` or `atol` to reach green.
- A constant with no dataset binding is undeclared, not "probably fine". List it in `[provenance].expect` so its absence fails.
- Identity is a hash, never a file mtime.
- A number from a remote or delegated run stays provisional until ④ passes locally.
- A ④ violation across machines is first a question of which upstream step is nondeterministic (e.g. hydrogen placement, random seeds, solver or thread order), not of tolerance. Pin that input (reuse the golden run's artifact), rerun several times on each machine, and report the spread. If the verdict flips with the unpinned step, the result is borderline: say so, and do not call a threshold-edge pass robust.

## Reporting format

One line per axis actually run: `axis | tool | exit | N violations / M blind | worst finding`.
Axes not run are listed as `not run` with the reason.

## Setup for a new project (minimal)

```
provenance.toml     # constants + source + sha256 + measured_at + instrument (+ valid_range, value_ref)
regress.toml        # goldens: actual = "<file>:<dotted.key>", rtol/atol, critical tag
regress.lock.json   # written by `regress-check freeze --reason ...`, committed
.fiducial.toml      # enable only rules that have targets, or the run is blind
```

## Related skills

- `compat-check`, `provenance-check`, `fiducial`, `regress-check` — the gates themselves.
- `endnote-citation-injection` — owns `endnote_library_audit.py` (gate ⑤).
- `bio-constants` — gate ⑦: database constants versus UniProt, PDB, Rhea and eQuilibrator.
- `experiment-hub` — owns `canon_gate.py` and the pipetting-workbook checks.
- `scientific-validation` — the judgment axes the gates leave open.
- `code-quality` — its verification gate points here for numbers.
