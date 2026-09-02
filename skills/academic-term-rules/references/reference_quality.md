# Reference Quality Standards

## 14. Reference Quality Standards

Used by manuscript-pipeline Phase 3.5 Deep Reference QC agents.

### Journal Tier Classification

| Tier | Criteria | Examples |
|---|---|---|
| 1 | IF > 30 or field-leading | Nature, Science, Cell, PNAS, Lancet, NEJM |
| 2 | IF 10-30 or top specialized | Angew. Chem., ACS Catal., Metab. Eng., Biotechnol. Bioeng. |
| 3 | IF 3-10 | Enzyme Microb. Technol., Process Biochem., Bioresour. Technol. |
| 4 | IF < 3 or unknown | Flag for review |

### Citation Count Thresholds (age-adjusted)

| Paper Age | Low | Noteworthy | Highly Cited | Landmark |
|---|---|---|---|---|
| 0-3 years | <5 | 20+ | 100+ | 500+ |
| 3-7 years | <20 | 100+ | 500+ | 1000+ |
| 7+ years | <50 | 500+ | 1000+ | 5000+ |

### Recency Scoring
- Review papers: >50% refs within last 5 years expected
- Research papers: >30% refs within last 5 years expected
- Flag: key claims citing only refs >10 years old without recent confirmation

### Red Flags
- Predatory journal (check against known lists)
- Retracted paper (CrossRef retraction status)
- Preprint cited as published (bioRxiv/medRxiv without DOI update)
- Self-citation ratio >30% of total refs
- >5 refs from same author group (citation ring concern)

