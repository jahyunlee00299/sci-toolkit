# Phase 5 — `citation_rewrite_plan.json` schema and operation types

Full worked example and the complete operation-type catalog for the citation rewrite plan
that `ref-resolver` produces in Phase 5.

## Worked example

```json
{
  "transformations": [
    {
      "para_idx": 127,
      "original_substring": "(Tong et al., 2022; Park et al., 2011)",
      "new_substring": "{Bayu, 2021 #PLACEHOLDER_ALT28; Xu, 2014 #PLACEHOLDER_ALT22}",
      "ref_ids_used": [28, 22],
      "operation": "REPLACE_WITH_ALT"
    }
  ]
}
```

PLACEHOLDER tokens are filled in Phase 6 after EndNote DB INSERT returns the actual record IDs.

## Operation types

- `RETAIN`: clean ref, just convert format
- `REPLACE`: ref entry metadata changes (#14 author, #17 venue, etc.)
- `REPLACE_NARRATIVE`: "Author et al. (Year)" form — replace text + add EndNote tag
- `REPLACE_WITH_ALT`: substitute alt paper
- `REMOVE_CITATION_BUNDLE`: drop entire group
- `REMOVE_CITATION_PARTIAL`: keep some, drop others in same group
- `INSERT_NEW_SENTENCE`: relocate citation (e.g., epimerase paper out of LAI cluster)
