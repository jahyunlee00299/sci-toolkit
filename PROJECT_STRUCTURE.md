# PROJECT_STRUCTURE — sci-toolkit

> Auto-generated structure map (written by TRACK A repo audit, 2026-08-21).

## Purpose

Portable, distributable toolkit of Claude Code skills, hooks, and scripts for
scientific research workflows (citation/DOI verification, HPLC parsing, primer
design, statistics, literature search connectors, environment doctoring). Ships
as a `.claude-plugin` and is the packaging layer that feeds skills into
`~/.claude/skills` and other machines.

## Top-Level Layout

| Path | Description |
|---|---|
| `.claude-plugin/plugin.json` | Plugin manifest |
| `CLAUDE.md` / `AGENTS.md` / `CODEX.md` | Per-harness instruction files |
| `README.md` / `QUICKSTART.md` / `CHANGELOG.md` / `NOTICE.md` / `LICENSE` | Project docs |
| `docs/` | Korean numbered onboarding guides (00–14: setup, API/MCP, tokens, rules, external services, Notion/Asana integration, remote server use) + `feature-connectivity-ledger.md` |
| `docs/agents/` | Full text of `AGENTS.md` §6/§6b/§7-hygiene/§8/§9/§10 (English). Moved out on 2026-09-02 so `AGENTS.md` stays under the 32 KiB Codex reads; `AGENTS.md` keeps a stub per section with the rules in force |
| `doctor.py` / `doctor.ps1` | Environment/health-check entry points (bash+PowerShell) |
| `doctor_lib/` | Modules backing `doctor.py` (result model, SENTINEL/research-marker scan, env checks, repo-integrity checks, dead-automation detector, self-test runner); `doctor.py` stays the thin entry point and re-exports every symbol tests use |
| `config/` | `catalog.json`, `institutions.json`, `credentials.example.json` (template only, no live secrets) |
| `hooks/` | Guard scripts (git safety, secret scan, destructive-delete, multiline, cloud-path) + `hooks.json` wiring |
| `skills/` | Bundled skill directories (academic-term-rules, biorxiv-database, code-quality, conda-env-manager, endnote-citation-injection, experiment-hub, generate-image, git-workflow-manager, journal-presentation-maker, lab-data-analysis, literature-review, manuscript-pipeline, markdown-mermaid-writing, markitdown, openalex-database, paper-extract, patent-invention-disclosure, primer-design, publication-figures, pubmed-database, research-ideation/-lookup/-search, scientific-validation, skill-developer, stats-workflow, statsmodels, get-available-resources) |
| `scripts/` | Utility scripts backing the skills (DOI verify, Excel formula check, HPLC parser, JCR batch verify, primer/variant checks, reference cache/fetch, SI fetch, checksum manifest, `skill_drift.py`, `connectivity_check.py`) |
| `evals/` | Routing probe + Codex compliance probe/schema |
| `install/install.py` | Installer |
| `tests/` | Self-checks in two styles, both run by `doctor.py` and by `pytest tests/`: script-style files (module-level checks + `sys.exit`, run as a subprocess) and pytest-style files (`def test_...`, collected natively — `test_sci_http.py` is the exemplar for converting the rest). `conftest.py` and `doctor_lib/selftests.py` apply the same sniff. Covers hooks/guards, doctor sentinel, DOI verify, feedback log/sanitize, checksums, skill references, install non-destructiveness, tool connectivity ratchet, standalone-tool smoke, SKILL.md size ratchet. Skill-local pytest suites (`skills/*/tests/`) are registered in `SELF_TEST_SCRIPTS` as directory entries. `doctor.py --offline` / `SCI_TOOLKIT_OFFLINE=1` keeps every network probe off |
| `out/` | Run output artifacts (gitignored except `.gitkeep`) |
| `SHA256SUMS` | Checksum manifest for distributed files |
| `.distignore` | Files excluded from distribution packaging |

## Shared skills — which copy is the source of truth

Most of `skills/` is an English distribution copy of skills authored in the
maintainer's runtime tree (`~/.claude/skills`). **The runtime copy is the
authoring SSOT; the toolkit copy is downstream.** Content changes go to the
runtime first and are then ported (translated, sanitized) here; editing a shared
skill here first is only for translation/sanitization. `python
scripts/skill_drift.py` compares the two trees and exits 1 when a runtime copy
changed after the toolkit copy was last touched (LAGGING); on a machine with no
runtime tree it reports "nothing to compare" and exits 0. Skills that exist only
here (`analysis-code-testing`, `biorxiv-database`, `data-quality-checks`,
`debugging-loop`, `spec-*`, `test-*`) are authored here.

## Connectivity — every tool must be reachable and tested

`python scripts/connectivity_check.py` classifies every non-underscore `.py`
under `scripts/`, `scripts/connectors/` and `skills/*/scripts/`: ORPHAN when no
doc, importer, hook or doctor names it (exit 1), UNTESTED when nothing under
`tests/`, `skills/*/tests/` or `doctor.py` names it (WARN, ratcheted by
`tests/test_connectivity.py`). `docs/feature-connectivity-ledger.md` entries
carry `wired-by: <path>` lines that must exist. Doctor check 13 runs it.
