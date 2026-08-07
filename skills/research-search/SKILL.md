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
    |       +-- 🔒 그 DOI를 어디서 얻었는가? — 수집 전에 먼저 정한다
    |       |       · 사용자가 브라우저/PDF에서 직접 복사   --> 그대로 진행
    |       |       · LLM(나)이 기억에서 생성했다
    |       |           --> ref_fetch.py --doi-source model --expect-title "<찾던 제목>"
    |       |               제목을 선언하지 않으면 수집에 진입조차 못 한다(exit 2).
    |       |               이유: 순차 DOI 대역(10.1016/j.xxx.YYYY.NNNNNN, Wiley, ACS)은
    |       |               한 자리만 틀려도 *실재하는 무관한 논문*에 착지한다. 실측 —
    |       |               지어낸 10.1016/j.biortech.2019.122211 은 없지만 +2 인 122213 은
    |       |               실재하는 크롬 환원 논문이고, 옛 게이트는 OK/exit 0 으로 통과시켰다.
    |       |               "존재함"과 "내가 찾던 그 논문임"은 다른 명제다.
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
    |       +-- 보충자료(SI)도 필요함
    |       |       --> ref_fetch.py ... --with-si   (또는 scripts/si_fetch.py 단독)
    |       |           본문과 SI는 접근성이 다르다 — 본문이 페이월이어도 SI는 열려 있을 수 있다.
    |       |           자동 수집 경로는 Europe PMC 하나뿐이다(표준 라이브러리로 되는 유일한 길).
    |       |           실측: 출판사 landing page 는 urllib 로 축소 페이지만 오고,
    |       |           PMC 파일 직링크는 "Preparing to download" JS 인터스티셜을 준다.
    |       |           PMC 에 없는 논문은 링크만 안내한다 — 우회하지 않는다.
    |       |
    |       +-- 기관 구독 저널(페이월) 논문 — OA 링크 없음
    |               --> ref_fetch.py ... --institution <키>   (config/institutions.json)
    |                   oa_status 가 "closed" 면 **사람이 클릭할** 기관 도서관 링크를
    |                   만들어 리포트와 화면에 넣는다. 로그인도 다운로드도 하지 않는다.
    |                   🔒 왜 자동화하지 않는가: 대학 도서관 공정이용 규정은 위반 사례
    |                   첫 항목으로 "전자적, 기계적 수단(다운로딩 프로그램, 엔진, 로봇,
    |                   매크로, RPA 등)으로 원문을 다운로드하는 행위"를 든다. 본인 계정으로
    |                   로그인했더라도 그 뒤를 스크립트가 받으면 수단 자체가 위반이고,
    |                   제재는 도서관 서비스 1년 제한 + 민사 책임 1차 부담이다.
    |                   한도(예: 동일 출판사 30건/일, 동일 PC 50건/일)도 함께 안내된다.
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
