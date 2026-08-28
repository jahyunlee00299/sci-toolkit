# Edit Categories — backup filename convention (manuscript-pipeline reference)

When saving `working.docx` in stages during a long edit, use a meaningful
filename suffix. (Optional) If a changelog-recording helper such as
`manuscript_workdir.py record` is in use, pair each save with that call to
stay consistent.

## Naming convention

```
{base}_backup_{category}.docx
```

`{category}` is one of the entries below:

| Category | Meaning | When to use |
|---|---|---|
| `restructure` | section restructuring | moving/merging large units |
| `{N}fix` | fix to section N | micro-edits within a section (e.g. `21fix`, `211_23fix`) |
| `{N}_{M}_replace` | replace sections N and M | replacing two sections at once |
| `doi_fix` | DOI/citation fix | reference consistency |
| `table_fix`, `table_v{N}` | table fix | table numbering/columns/data |
| `pre_abbrev` | abbreviation unification (domain vocabulary) | a bulk nomenclature cleanup |
| `body_accuracy` | body-text accuracy | after verifying numbers/citations |
| `separation_edit` | split edit | saving a large change as two pieces |
| `rebuild_base` | base rebuild | after recovering from corruption |
| `reftest` | reflects reference-verification results | after reference_validator.py |
| `tracked` | tracked-changes version | for review before accepting |
| `accepted` | tracked changes accepted | final clean version |
| `commented` | comments-only version | for circulating to the paper's authors |
| `reviewed` | review completed by another author | after receiving mentor/co-author markup |
| `QCfixed` | after passing QC | final review |

**Rule:** when calling `record`, include the category in `--rationale`. Example:
```bash
manuscript_workdir.py record paper1 "Section 2.4" "..." "..." --rationale "[ABBREV] unified sugar abbreviations"
```

## User-made backups vs. agent-made backups

- A backup the user copies directly into a cloud-sync folder → reference only
- A backup the agent makes → a separate working directory `~/manuscripts/{paper_id}/working_history/{ts}_{category}.docx`
- The two never conflict (different directories)

## Watch for cloud-sync folder conflicts
If the DOCX in the sync folder is open in Word, an overwrite will fail →
work in a temp folder instead and save as `_v2`.
