---
name: research-search
description: Meta-skill that routes research and search queries to the optimal backend — academic papers (OpenAlex, PubMed), AI-powered web search (Perplexity), general web search (Parallel). Use as the single entry point for any research or information lookup. For synthesizing findings into a review document use literature-review; for ideation/discussion of results use research-ideation.
license: MIT license
metadata:
    skill-author: K-Dense Inc.
---

# Research Search (Meta-Skill)

## Overview

This is a **routing meta-skill** that dispatches research and search queries to the most appropriate backend skill. Instead of choosing between 5+ search skills manually, describe what you need and this skill determines the optimal route.

## When to Use This Skill

Use this skill whenever you need to:

- Search for academic papers or scientific literature
- Look up current information from the web
- Find structured experimental data from papers
- Conduct comprehensive research on any topic
- Verify facts or find citations

**Do NOT use this skill for:**
- Systematic literature reviews (use `literature-review` directly — it is a workflow skill, not a search tool)
- Simple in-context questions that don't require external lookup

---

## Routing Logic

```
Query arrives
    |
    +-- Academic paper search (general scholarly)?
    |       |
    |       +-- Simple search (find papers, citations, basic lookup)
    |       |       --> research-lookup (auto-routes OpenAlex / PubMed)
    |       |
    |       +-- Advanced query (Boolean, MeSH, field tags, batch)?
    |       |       |
    |       |       +-- Biomedical / life sciences
    |       |       |       --> pubmed-database (E-utilities, MeSH terms)
    |       |       |
    |       |       +-- General scholarly (any field)
    |       |               --> openalex-database (filters, bibliometrics)
    |
    +-- 논문 원문 PDF 다운로드? (DOI 기반, OA 경로만)
    |       |
    |       +-- DOI를 알고 있음
    |       |       --> ../../scripts/ref_fetch.py --doi <DOI> --download
    |       |           (CrossRef → OpenAlex → Unpaywall 교차검증 후 OA PDF만 수집,
    |       |            API 키 불필요; 자세한 옵션은 `python ../../scripts/ref_fetch.py --help`)
    |       |
    |       +-- 제목만 알고 있음
    |       |       --> ../../scripts/ref_fetch.py --title "<제목>" --download
    |       |           (제목으로 DOI를 먼저 해석한 뒤 동일하게 진행)
    |       |
    |       +-- 기관 구독 저널(페이월) 논문 — OA 링크 없음
    |               --> ref_fetch.py는 페이월 우회/로그인 기능이 없다.
    |                   결과 JSON의 oa_status가 "closed"면 그대로 남기고,
    |                   기관 도서관 경로는 사용자가 직접 확인한다.
    |
    +-- Web search / current information?
    |       |
    |       +-- General web search, market research, news, industry data
    |       |       --> parallel-web (search or research command)
    |       |
    |       +-- AI-synthesized answer with citations (recent science, tech, facts)
    |               --> perplexity-search (sonar-pro or sonar-pro-search)
    |
    +-- Mixed / unclear?
            --> research-lookup (free, no API key, good default)
```

---

## Backend Skills Reference

### 1. research-lookup (Default Route)

**When:** Simple academic searches, quick paper lookups, default for unclear queries.

- Auto-routes between OpenAlex (240M+ works) and PubMed (biomedical)
- No API key required (completely free)
- Returns titles, authors, citations, DOIs, abstracts

```bash
python research_lookup.py "CRISPR gene editing 2025" -o sources/research_topic.md
python research_lookup.py "mRNA vaccine efficacy" --force-backend pubmed -o sources/papers_topic.md
```

**Route here when:** User asks "find papers about X", "what research exists on Y", or any general scholarly query.

---

### 2. pubmed-database (Advanced Biomedical)

**When:** Complex biomedical queries requiring Boolean operators, MeSH terms, field tags, or systematic review searches.

- NCBI E-utilities REST API
- MeSH controlled vocabulary for precise searching
- PICO framework support for clinical queries
- Publication type filtering (RCT, meta-analysis, etc.)

```
diabetes mellitus[mh] AND treatment[tiab] AND systematic review[pt] AND 2023:2024[dp]
```

**Route here when:** User needs MeSH terms, field-specific tags, clinical query structure, or PubMed-specific features.

---

### 3. openalex-database (Advanced Scholarly)

**When:** Advanced bibliometric queries, author/institution analysis, citation networks, publication trends, or complex filtering across all scholarly fields.

- 240M+ works, no API key required
- Two-step entity lookups (name → ID → works)
- Group-by analysis, publication trends, batch lookups
- Collaboration and citation analysis

```python
client = OpenAlexClient(email="user@example.edu")
results = client.search_works(search="topic", filter_params={"cited_by_count": ">100"})
```

**Route here when:** User needs bibliometric analysis, author output analysis, institution comparison, or advanced OpenAlex filters.

---

### 4. parallel-web (General Web Search)

**When:** General web searches, market research, industry analysis, current events, technical documentation, deep research reports.

- Parallel Chat API (OpenAI-compatible)
- `search` command: quick web search with synthesized summary
- `research` command: comprehensive multi-source reports
- `extract` command: URL content extraction (verification only)
- Requires `PARALLEL_API_KEY`

Route the query to the **parallel-web** skill (e.g. `search "latest AI regulation updates"` or `research "EV battery market analysis"`) rather than calling its script directly.

**Route here when:** User needs non-academic web information, market data, news, or comprehensive research reports.

---

### 5. perplexity-search (AI Web Search)

**When:** AI-synthesized answers with source citations, recent scientific developments, real-time information beyond training cutoff.

- Multiple models: sonar, sonar-pro, sonar-pro-search, sonar-reasoning-pro
- Real-time web-grounded answers
- Requires `OPENROUTER_API_KEY`

Route the query to the **perplexity-search** skill (e.g. `"latest CRISPR clinical trial results 2025"` with `--model sonar-pro`) rather than calling its script directly.

**Route here when:** User wants AI-synthesized answers with citations, or needs information that is very recent and may not be indexed in academic databases yet.

---

## Decision Matrix

| Query Type | Primary Route | Fallback |
|------------|--------------|----------|
| "Find papers about X" | research-lookup | openalex-database |
| "PubMed search with MeSH terms" | pubmed-database | — |
| "Author's publication list" | openalex-database | — |
| "Citation analysis for paper X" | openalex-database | — |
| "Latest news about X" | parallel-web | perplexity-search |
| "Market size for X" | parallel-web | — |
| "What methods did studies use for X" | literature-review | research-lookup |
| "Recent advances in X (2025)" | perplexity-search | parallel-web |
| "Compare X vs Y (current state)" | perplexity-search | parallel-web |
| "Systematic review on X" | literature-review (workflow) | — |
| "논문 PDF 다운로드 (OA)" | web-scraping --download | — |
| "논문 PDF 다운로드 (기관 구독)" | web-scraping --download --libkey | --auto-login (EZproxy) |

## API Key Requirements

| Backend | API Key | Cost |
|---------|---------|------|
| research-lookup | None | Free |
| pubmed-database | Optional (NCBI API key) | Free |
| openalex-database | None | Free |
| parallel-web | PARALLEL_API_KEY | Paid |
| perplexity-search | OPENROUTER_API_KEY | Paid (pay-per-query) |

**Recommendation:** Start with free backends (research-lookup) and escalate to paid backends only when needed.

## MANDATORY: Save All Results

Every search result MUST be saved to the project's `sources/` folder. See individual skill documentation for filename patterns.

```bash
ls sources/  # Always check existing results before new queries
```

## Relationship to Other Skills

- **literature-review**: Workflow/methodology skill for systematic reviews. It *uses* search backends listed here but is NOT a search tool itself. Keep separate.
- **parallel-web**: Backend that serves both this meta-skill and other skills. Remains active independently.
- **research-lookup**: Simplified wrapper over OpenAlex + PubMed. Remains active as the default free route.
