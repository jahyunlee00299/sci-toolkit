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
    +-- Download the full-text PDF? (DOI-based, OA route only)
    |       |
    |       +-- 🔒 Where did that DOI come from? — decide this BEFORE fetching
    |       |       · The user copied it directly from a browser/PDF   --> proceed as-is
    |       |       · The LLM (me) generated it from memory
    |       |           --> ref_fetch.py --doi-source model --expect-title "<title you were looking for>"
    |       |               Without declaring a title, fetching cannot even start (exit 2).
    |       |               Reason: a sequential DOI block (10.1016/j.xxx.YYYY.NNNNNN, Wiley, ACS)
    |       |               can land on a *real, unrelated paper* from being off by just one digit.
    |       |               Measured — the invented 10.1016/j.biortech.2019.122211 doesn't exist,
    |       |               but 122213 (+2) is a real paper on chromium reduction, and the old gate
    |       |               let it through as OK/exit 0.
    |       |               "It exists" and "it's the paper I was looking for" are different claims.
    |       |
    |       +-- The DOI is known
    |       |       --> ../../scripts/ref_fetch.py --doi <DOI> --download
    |       |           (cross-verifies via CrossRef → OpenAlex → Unpaywall, then fetches OA PDF only,
    |       |            no API key needed; see `python ../../scripts/ref_fetch.py --help` for options)
    |       |
    |       +-- Only the title is known
    |       |       --> ../../scripts/ref_fetch.py --title "<title>" --download
    |       |           (resolves the DOI from the title first, then proceeds the same way)
    |       |
    |       +-- Supplementary information (SI) is also needed
    |       |       --> ref_fetch.py ... --with-si   (or scripts/si_fetch.py standalone)
    |       |           Body text and SI have different access levels — SI can be open even
    |       |           when the body is paywalled. The only automated route is Europe PMC
    |       |           (the sole path achievable with the standard library alone).
    |       |           Measured: a publisher landing page returns only a stripped-down page
    |       |           via urllib, and a direct PMC file link returns a "Preparing to download"
    |       |           JS interstitial.
    |       |           For a paper not on PMC, only the link is given — no workaround is used.
    |       |
    |       +-- Journal behind an institutional subscription (paywall) — no OA link
    |               --> ref_fetch.py ... --institution <key>   (config/institutions.json)
    |                   When oa_status is "closed", build a **human-clickable** institutional
    |                   library link and place it in the report and on screen. No login, no
    |                   download performed.
    |                   🔒 Why this is not automated: a university library's fair-use policy
    |                   lists, as its first violation example, "downloading full text by
    |                   electronic or mechanical means (a downloader program, engine, bot,
    |                   macro, RPA, etc.)." Even after a human logs in with their own account,
    |                   handing the rest to a script violates the policy by the means alone,
    |                   and the penalty is a one-year library-service restriction plus primary
    |                   civil liability.
    |                   Rate limits (e.g. 30/day per publisher, 50/day per machine) are also
    |                   reported alongside.
    |
    +-- Preprint / not yet peer reviewed?
    |       |
    |       +-- "has this been posted yet", newest work, searching for the latest paper
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

**When:** The work may be too new to be peer reviewed — "has anyone posted this yet", newest results in a fast-moving field, searching for the latest paper before journal publication.

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
| "Preprint / newest result not yet published" | biorxiv-database | research-lookup |
| "Check whether someone already posted this" | biorxiv-database | openalex-database |
| "What methods did studies use for X" | literature-review | research-lookup |
| "Recent advances in X (2026)" | biorxiv-database | research-lookup |
| "Systematic review on X" | literature-review (workflow) | — |
| "Download paper PDF (OA)" | `scripts/ref_fetch.py --doi <DOI> --download` | `--title "<title>"` |
| "Download paper PDF (institutional subscription)" | Not supported — leave as `oa_status: closed`, user follows the library route themselves | — |
| "Latest news / market data (non-academic)" | agent's built-in web search | — |

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
