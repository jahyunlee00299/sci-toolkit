# Memory hook — what to save after a run (worked example)

Save the following to memory after each successful run:
- Project name + manuscript file path
- Date applied
- Number of refs processed (N inserted, M alt'd, K dropped)
- EndNote record id range (start–end) so future updates know where these came from

Example note to keep alongside the project (`endnote_injection_<project>.md`):
```
DOI verification by ref-resolver caught 3 hallucinated DOIs and 1 typo (e.g. wrong year 2017 vs 2019).
Direct SQLite INSERT works with EN_MAKE_SORT_KEY + locale stubs.
Track Changes via lxml preserved 35 xmlns declarations (vs ET which drops to 10).
```
