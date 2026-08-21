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
| `docs/` | Korean numbered onboarding guides (00–12: setup, API/MCP, tokens, rules, external services, Notion/Asana integration, remote server use) + `feature-connectivity-ledger.md` |
| `doctor.py` / `doctor.ps1` | Environment/health-check entry points (bash+PowerShell) |
| `config/` | `catalog.json`, `institutions.json`, `credentials.example.json` (template only, no live secrets) |
| `hooks/` | Guard scripts (git safety, secret scan, destructive-delete, multiline, cloud-path) + `hooks.json` wiring |
| `skills/` | Bundled skill directories (academic-term-rules, biorxiv-database, code-quality, conda-env-manager, endnote-citation-injection, experiment-hub, generate-image, git-workflow-manager, journal-presentation-maker, lab-data-analysis, literature-review, manuscript-pipeline, markdown-mermaid-writing, markitdown, openalex-database, paper-extract, primer-design, publication-figures, pubmed-database, research-ideation/-lookup/-search, scientific-validation, skill-developer, stats-workflow, statsmodels, get-available-resources) |
| `scripts/` | Utility scripts backing the skills (DOI verify, Excel formula check, HPLC parser, JCR batch verify, primer/variant checks, reference cache/fetch, SI fetch, checksum manifest) |
| `evals/` | Routing probe + Codex compliance probe/schema |
| `install/install.py` | Installer |
| `tests/` | Pytest suite covering hooks/guards, doctor sentinel, DOI verify, feedback log/sanitize, checksums, skill references, install non-destructiveness |
| `out/` | Run output artifacts (should be gitignored) |
| `SHA256SUMS` | Checksum manifest for distributed files |
| `.distignore` | Files excluded from distribution packaging |
