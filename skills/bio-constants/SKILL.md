---
name: bio-constants
description: "Key-less lookup and claim-vs-live reconciliation of biochemical constants from UniProt, RCSB PDB, Rhea and eQuilibrator; gate ⑦ of verification-gates (0 match / 1 mismatch / 2 BLIND). Triggers: 단백질 분자량 확인, UniProt 조회, PDB 해상도, Rhea 반응, eQuilibrator, Keq 대조, dG'0, 상수 출처, 문헌값 대조, bio_claims, 효소 분자량 맞아, 바이오 상수 검증, EC 번호 확인."
license: MIT license
metadata:
    skill-author: Lab Researcher
---

# bio-constants (verification gate ⑦)

Re-derives numbers that are usually copied by hand: protein mass/length/EC/organism (UniProt),
structure facts (PDB), reaction records (Rhea) and thermodynamics (eQuilibrator). Public GET only: no key,
no account. Python stdlib only (3.11+ for tomllib). Details and limits: `README_biodb.md`.

## Commands (`python -I scripts/biodb/bio_const.py ...`, run from this skill folder)

| Command | Use |
| --- | --- |
| `uniprot P33160 --field mass` / `pdb 2NAD` / `rhea --ec 1.1.1.37` | look a value up |
| `compare --source uniprot --id ID --field F --claimed V --unit Da` | one claim vs live |
| `thermo --reaction "A + B = C" --pH --ionic-strength --temperature --pMg [--claimed-keq]` | dG'0 and Keq, conditions mandatory |
| `check bio_claims.toml` | every `[[claim]]` in a file (template: `bio_claims.example.toml`) |

## Gate contract (same as verification-gates)

`0` all claims match / `1` any MISMATCH / `2` BLIND (network failure, ambiguous or inactive record,
missing or wrong unit, unknown field, empty claims file). **Exit 2 is never a pass.** MISMATCH beats BLIND
in the final code, and the SUMMARY line counts both.

## Rules baked in

- Units are explicit (Da vs kDa). `mass` is UniProt `sequence.molWeight`; a mature-chain mass is computed
  locally and shown as a note, never swapped in silently. Tags (His etc.) are unknown to the databases:
  a claimed tag-corrected mass is a documented MISMATCH, not a tool error.
- Inactive UniProt entries: MERGED is reported as `merged_to` (not followed); DEMERGED/DELETED are BLIND.
- Every thermodynamic line carries pH, I, T and pMg. Keq is recomputed from dG'0. The `web` route reads the
  public HTML page (no JSON API exists): corroboration with a +-1 sigma band that can be far wider than the
  value needs, not a precision check. The `package` route is the precise one: `equilibrator-api` is imported
  from the running interpreter or from a separate venv at `~/.venvs/equilibrator` (called as a subprocess), and
  needs `compounds.sqlite` (1.34 GB) in the equilibrator cache dir; it is never downloaded automatically.
  Ambiguous names ("D-glucose 6-phosphate") are BLIND on `package`; use `kegg:C00092` ids there (the web route
  cannot parse kegg: ids).
- Fixture tests are offline replays of recorded public responses; re-record with `record_fixtures*.py`.

## Tests

`python -I -m unittest discover -s scripts` from this skill folder (58 offline tests, no network).

## Related

`verification-gates` (router; this is its gate ⑦), `scientific-validation` (plausibility the gate cannot decide).
For a high-stakes number hand this gate's output to ONE independent verifier agent instead of re-deriving it.
