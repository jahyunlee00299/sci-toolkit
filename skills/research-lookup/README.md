# Research Lookup Skill

Research information lookup using **free academic APIs** — no API keys required.

## Backends

| Backend | Coverage | API Key |
|---------|----------|---------|
| **OpenAlex** | 240M+ scholarly works (all disciplines) | Not required |
| **PubMed** | 36M+ biomedical articles (MEDLINE) | Not required |

## Usage

### Command Line

```bash
# Auto-routed (recommended)
python research_lookup.py "Recent advances in CRISPR gene editing"

# Force backend
python research_lookup.py "topic" --force-backend openalex
python research_lookup.py "topic" --force-backend pubmed

# Save to file
python research_lookup.py "topic" -o sources/research_topic.md

# JSON output
python research_lookup.py "topic" --json -o sources/research_topic.json

# Batch queries
python research_lookup.py --batch "query 1" "query 2" -o sources/batch.md
```

### Claude Code Integration

Automatically used when you ask research questions in Claude Code.

## Routing Logic

- **Biomedical keywords detected** (clinical trial, gene, drug, patient, etc.) → **PubMed**
- **Everything else** → **OpenAlex**

## Response Data

Each result includes:
- Paper title, authors, year, journal/venue
- Citation counts (OpenAlex) or PMIDs (PubMed)
- DOIs for citation management
- Open access status (OpenAlex)
- Abstract excerpts (OpenAlex)

## Complementary Skills

| Task | Skill |
|------|-------|
| Deep OpenAlex analysis | `openalex-database` |
| Advanced PubMed queries | `pubmed-database` |
| General web search | WebSearch (built-in) |
