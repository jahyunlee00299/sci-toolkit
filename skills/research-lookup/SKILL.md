---
name: research-lookup
description: Look up current research information using free academic APIs — OpenAlex (240M+ scholarly works) and PubMed E-utilities (biomedical). No API keys required. Automatically routes queries to the best backend. Use for finding papers, gathering research data, and verifying scientific information.
license: MIT license
compatibility: No API keys required (OpenAlex + PubMed are free)
metadata:
    skill-author: K-Dense Inc.
---

# Research Information Lookup (Free APIs)

## Overview

This skill provides research information lookup using **free academic APIs** with intelligent backend routing:

- **OpenAlex API**: Default backend for all scholarly queries. 240M+ works, no API key required.
- **PubMed E-utilities**: Used for biomedical/life science queries. No API key required.

No paid API keys needed. Both backends are completely free.

## When to Use This Skill

Use this skill when you need:

- **Current Research Information**: Latest studies, papers, and findings
- **Literature Verification**: Check facts, statistics, or claims against current research
- **Background Research**: Gather context and supporting evidence for scientific writing
- **Citation Sources**: Find relevant papers and studies to cite
- **Biomedical Literature**: PubMed-indexed papers, clinical trials, medical research

## Automatic Backend Selection

```
Query arrives
    |
    +-- Contains biomedical keywords? (clinical trial, patient, gene, drug, etc.)
    |       YES --> PubMed E-utilities
    |
    +-- Everything else (general scholarly, engineering, CS, physics, etc.)
            --> OpenAlex API
```

### Biomedical Keywords (Routes to PubMed)

- Clinical: `clinical trial`, `patient`, `treatment`, `diagnosis`, `therapy`
- Molecular: `protein`, `gene`, `enzyme`, `receptor`, `antibody`
- Medical: `cancer`, `disease`, `surgery`, `pharmaceutical`
- Journals: `pubmed`, `nejm`, `lancet`, `jama`

### Everything Else (Routes to OpenAlex)

All other scholarly queries, including:
- Computer science and AI research
- Engineering and physical sciences
- Social sciences and humanities
- Interdisciplinary research
- General academic search

### Manual Override

```bash
python research_lookup.py "your query" --force-backend openalex
python research_lookup.py "your query" --force-backend pubmed
```

---

## Core Capabilities

### 1. General Scholarly Search (OpenAlex)

**Default backend.** Searches 240M+ scholarly works with citation counts, DOIs, and open access status.

```
Query Examples:
- "Recent advances in CRISPR gene editing 2025"
- "Transformer attention mechanisms NeurIPS"
- "Renewable energy policy impact assessment"
```

**Response includes:**
- Paper titles, authors, year, journal/venue
- Citation counts for each paper
- DOIs and open access indicators
- Abstract excerpts
- Total result count

### 2. Biomedical Literature Search (PubMed)

**Used for biomedical queries.** Searches MEDLINE/PubMed indexed literature.

```
Query Examples:
- "CRISPR clinical trials gene therapy"
- "mRNA vaccine efficacy systematic review"
- "Immunotherapy non-small cell lung cancer"
```

**Response includes:**
- Paper titles, authors, year, journal
- PMIDs and DOIs
- Full journal names

---

## Command-Line Usage

```bash
# Auto-routed research (recommended) — ALWAYS save to sources/
python research_lookup.py "your query" -o sources/research_YYYYMMDD_topic.md

# Force specific backend
python research_lookup.py "your query" --force-backend openalex -o sources/research_topic.md
python research_lookup.py "your query" --force-backend pubmed -o sources/papers_topic.md

# JSON output for structured data
python research_lookup.py "your query" --json -o sources/research_topic.json

# Batch queries
python research_lookup.py --batch "query 1" "query 2" -o sources/batch_topic.md

# Control result count
python research_lookup.py "your query" -n 20
```

---

## MANDATORY: Save All Results to Sources Folder

**Every research-lookup result MUST be saved to the project's `sources/` folder.**

| Backend | Filename Pattern |
|---------|-----------------|
| OpenAlex | `research_YYYYMMDD_HHMMSS_<topic>.md` |
| PubMed | `papers_YYYYMMDD_HHMMSS_<topic>.md` |
| Batch | `batch_research_YYYYMMDD_HHMMSS_<topic>.md` |

### Before Making a New Query, Check Sources First

```bash
ls sources/  # Check existing saved results
```

---

## Paper Quality and Popularity Prioritization

### Citation-Based Ranking

| Paper Age | Citation Threshold | Classification |
|-----------|-------------------|----------------|
| 0-3 years | 20+ citations | Noteworthy |
| 0-3 years | 100+ citations | Highly Influential |
| 3-7 years | 100+ citations | Significant |
| 3-7 years | 500+ citations | Landmark Paper |
| 7+ years | 500+ citations | Seminal Work |
| 7+ years | 1000+ citations | Foundational |

### Venue Quality Tiers

**Tier 1 - Premier Venues** (Always prefer):
- **General Science**: Nature, Science, Cell, PNAS
- **Medicine**: NEJM, Lancet, JAMA, BMJ
- **Field-Specific**: Nature Medicine, Nature Biotechnology, Nature Methods

**Tier 2 - High-Impact Specialized** (Strong preference):
- Journals with Impact Factor > 10
- Top conferences (NeurIPS, ICML, ICLR, ACL, CVPR)

---

## Integration with Scientific Writing

1. **Literature Review Support**: Gather current research for introduction and discussion
2. **Methods Validation**: Verify protocols against current standards
3. **Results Contextualization**: Compare findings with recent similar studies
4. **Citation Management**: Provide structured citations with DOIs

## Complementary Tools

| Task | Tool |
|------|------|
| Deep OpenAlex analysis | `openalex-database` skill |
| PubMed advanced queries | `pubmed-database` skill |
| Sequence/bio analysis | `biopython` library (Bio.Entrez) |
| General web search | WebSearch (built-in Claude Code tool) |

---

## Advantages Over Paid Alternatives

- **No API keys required** — works out of the box
- **No cost** — OpenAlex and PubMed are free public APIs
- **Structured data** — returns citation counts, DOIs, PMIDs, authors
- **Reliable** — backed by NIH (PubMed) and OurResearch (OpenAlex)
- **Comprehensive** — 240M+ works (OpenAlex) + 36M+ biomedical articles (PubMed)
