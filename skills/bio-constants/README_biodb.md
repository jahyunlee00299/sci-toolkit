# biodb: key-less lookup and reconciliation of biochemical constants

Re-derives numbers that are normally copied by hand from UniProt, RCSB PDB, Rhea and
eQuilibrator. Public GET only: no key, no account. Polite client: User-Agent, 1 request/s
per host, one retry, 30 s timeout. Python 3.11+ stdlib only (no pip installs).

## CLI (`python -I biodb/bio_const.py ...`)
    uniprot P33160 [--field mass|mature_mass|length|ec|organism|taxon|name|gene] [--json]
    pdb 2NAD [--json]
    rhea --rhea RHEA:21432 | --ec 1.1.1.37
    thermo --reaction "A + B = C" --pH 7.5 --ionic-strength 0.25 --temperature 298.15 --pMg 3.0
           [--source web|package] [--claimed-keq 2.28e-5 --rtol 0.05]
    compare --source uniprot|pdb --id ID --field F --claimed V --unit Da|kDa|aa|A|nm --rtol 0.01

## Exit contract (same as verification-gates)
0 = MATCH / ok, 1 = MISMATCH, 2 = BLIND (network or API failure, ambiguous or inactive
record, missing/wrong unit, unknown field). BLIND is never a pass.

## Rules baked in
- Units are explicit (Da vs kDa); a numeric compare without a valid unit is BLIND.
- `mass` is always UniProt `sequence.molWeight`. Mature-chain mass is computed locally and
  labeled; it is a note on the verdict line, never a silent swap. Tags (His etc.) are unknown.
- Inactive UniProt entries: MERGED (single target) is reported as `merged_to`, never followed;
  DEMERGED/DELETED are BLIND.
- Every thermodynamic line carries pH, I, T and pMg. Keq is recomputed from dG'0.

## Tests
    python -I -m unittest        # 58 tests, offline, replay of recorded public responses
Fixtures live in tests/fixtures (public API data). Re-record: `record_fixtures.py`,
`record_fixtures2.py` (live network, ~1 req/s).

## Known limits
- eQuilibrator `package` route needs compounds.sqlite (1.34 GB, Zenodo) which is not cached;
  it is never downloaded automatically. The `web` route reads the public HTML page (no JSON
  API exists), so it is corroboration, not a contract.
- Rhea: master ids only. Host is www.rhea-db.org (rest.rhea-db.org did not resolve).
