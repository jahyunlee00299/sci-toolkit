---
name: research-search
description: Meta-skill that routes research and search queries to the optimal backend — peer-reviewed papers (OpenAlex, PubMed), preprints (bioRxiv, medRxiv, arXiv), and OA full-text retrieval. Use as the single entry point for any research or information lookup. For synthesizing findings into a review document use literature-review; for ideation/discussion of results use research-ideation.
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
    +-- Preprint / not yet peer reviewed?
    |       |
    |       +-- "has this been posted yet", newest work, 최신 논문 검색
    |               --> biorxiv-database (Europe PMC SRC:PPR + arXiv, no API key)
    |
    +-- General web search / current non-academic information?
    |       |
    |       +-- No web-search skill ships in this package.
    |               --> use your agent's own built-in web search / fetch tool.
    |                   Do not point the user at a skill that is not installed.
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

### 4. biorxiv-database (Preprints)

**When:** The work may be too new to be peer reviewed — "has anyone posted this yet", newest results in a fast-moving field, 최신 논문 검색 before journal publication.

- Europe PMC `SRC:PPR` (bioRxiv, medRxiv, Research Square, ChemRxiv, SSRN) + arXiv Atom API
- No API key, no registration
- Surfaces the **published DOI** when a preprint has since appeared in a journal, so you cite that instead
- Hands results to `scripts/ref_fetch.py` for PDF download and BibTeX

```bash
python preprint_search.py "CRISPR base editing" --source biorxiv --json -o sources/preprints_topic.json
```

**Route here when:** The user asks for preprints, the newest work in a field, or wants to check whether a result has already been posted publicly.

⚠️ bioRxiv's own API **cannot do keyword search** — its `?query=` parameter is silently ignored and returns a full, unfiltered page with HTTP 200. See `../biorxiv-database/references/api_guide.md` for the measured probes; never hand-roll a search against it.

---

### General web search — not in this package

No general web-search skill ships here (they all require a paid API key). For non-academic web information, market data, or news, use the web search / fetch tool built into your agent, and cite the URL. Do not route the user to a skill that is not installed.

---

## Decision Matrix

| Query Type | Primary Route | Fallback |
|------------|--------------|----------|
| "Find papers about X" | research-lookup | openalex-database |
| "PubMed search with MeSH terms" | pubmed-database | — |
| "Author's publication list" | openalex-database | — |
| "Citation analysis for paper X" | openalex-database | — |
| "프리프린트 / 아직 안 나온 최신 결과" | biorxiv-database | research-lookup |
| "이미 누가 올렸는지 확인" | biorxiv-database | openalex-database |
| "What methods did studies use for X" | literature-review | research-lookup |
| "Recent advances in X (2026)" | biorxiv-database | research-lookup |
| "Systematic review on X" | literature-review (workflow) | — |
| "논문 PDF 다운로드 (OA)" | `scripts/ref_fetch.py --doi <DOI> --download` | `--title "<제목>"` |
| "논문 PDF 다운로드 (기관 구독)" | 미지원 — `oa_status: closed` 로 남기고 도서관 경로는 사용자가 직접 | — |
| "Latest news / market data (비학술)" | 에이전트 내장 웹 검색 | — |

## API Key Requirements

| Backend | API Key | Cost |
|---------|---------|------|
| research-lookup | None | Free |
| pubmed-database | Optional (NCBI API key) | Free |
| openalex-database | None | Free |
| biorxiv-database | None | Free |
| `scripts/ref_fetch.py` (OA PDF·BibTeX) | None | Free |

**Every backend in this package is free and keyless.** Nothing here bills per query, so there is no paid route to escalate to — if a query genuinely needs the open web, that is your agent's own web-search tool, not a skill.

## MANDATORY: Save All Results

Every search result MUST be saved to the project's `sources/` folder. See individual skill documentation for filename patterns.

```bash
ls sources/  # Always check existing results before new queries
```

## Relationship to Other Skills

- **literature-review**: Workflow/methodology skill for systematic reviews. It *uses* search backends listed here but is NOT a search tool itself. Keep separate.
- **biorxiv-database**: Preprint front end. Also usable directly; it hands its hits to `scripts/ref_fetch.py`, the same retrieval path this skill points at.
- **research-lookup**: Simplified wrapper over OpenAlex + PubMed. Remains active as the default free route.
