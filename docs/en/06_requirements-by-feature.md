> English translation of [06_기능별_준비물.md](../06_기능별_준비물.md). The Korean original is canonical; if they differ, the Korean version wins.

# 06. Requirements by Feature: "What do I need to prepare to use this feature?"

> Bottom line first: most features work right away with no preparation, with only your subscription login.
> Only a few need an API key or a separate installation, and even those usually have a free workaround.
> This document is a one-page checklist of "what each feature requires."

Related earlier documents: for concepts see [02_api-and-mcp](02_api-and-mcp.md), for external service integration and security see
[05_external-services](05_external-services.md), and for the actual integration scripts see
[`scripts/connectors/README.md`](../../scripts/connectors/README.md).

---

## 1. Four kinds of requirements

Each feature needs something different, but there are four kinds.

| Mark | Meaning | Burden for beginners |
|---|---|---|
| Subscription only | Works right away as long as you are logged in to your Claude/ChatGPT subscription | None |
| API key | A key for a specific service is needed (most have a free alternative) | Low to medium |
| MCP connection | You need to "connect" the service in the app, or run a small server | Medium |
| Local tool | A program must be installed on your computer (LibreOffice, etc.) | Medium |

> Most features need only a subscription. In the tables below, pay attention to the ones that do not.

---

## 2. Requirements table by feature

### Features that just work (nothing to prepare)

These features work right away with only your subscription login. Most features belong here.

| Feature (skill) | What it does | Notes |
|---|---|---|
| `research-lookup` | Paper lookup ([OpenAlex](https://openalex.org)+[PubMed](https://pubmed.ncbi.nlm.nih.gov)) | Free, no key needed (the skill states this itself) |
| `openalex-database` | OpenAlex paper DB | Fully open, no key needed |
| `pubmed-database` | PubMed search | Works without a key (a key only improves speed; optional) |
| `biorxiv-database` | Preprint search ([bioRxiv](https://www.biorxiv.org), medRxiv, arXiv) | Free, no key or sign-up needed |
| `stats-workflow` | Statistical tests and reporting | Python packages only |
| `scientific-validation` | Validity check of results | Standard library |
| `academic-term-rules` | Terminology and notation rules | Rules document (nothing to run) |
| `lab-data-analysis` | Lab data analysis and safety information | [PubChem](https://pubchem.ncbi.nlm.nih.gov) free API |
| `paper-extract` | Extract tables, figures, and body text from papers | Already-installed libraries |
| `research-ideation` | Ideas and hypotheses | Pure thinking workflow |
| `research-search` | Search meta-router (papers, preprints, web) | All free, no key needed |
| `pdf` | PDF handling (basic features) | Pure Python (OCR is the only exception ↓) |

### Features that need an API key (only a few, most with a free way around)

| Feature | What is needed | Required? | Free workaround |
|---|---|---|---|
| `markitdown` | File → Markdown | Optional | Basic conversion is completely free. Only the AI image-description feature needs an [OPENROUTER](https://openrouter.ai) key |
| `literature-review` | Literature review document | Optional | [Semantic Scholar](https://www.semanticscholar.org/product/api) has a free tier (key recommended). Search and document generation themselves work |

> For how to enter a key, see [02_api-and-mcp](02_api-and-mcp.md) and the connector's
> `config/credentials.example.json` approach (environment variables). If you are not in a hurry, we recommend trying the
> free route first, without a key.

### Features that need an MCP connection

| Feature | What is needed | Required? |
|---|---|---|
| `primer-design` | Run a local MCP server (`python -m src.primer_design.mcp_server`) | Required: this skill works as an MCP server |

> For what MCP is, see the "standard plug" analogy in [02_api-and-mcp](02_api-and-mcp.md).
> primer-design only works when the primer design tool is running as a small server. The setup is in that skill's
> SKILL.md. If you're not sure, ask your administrator, "How do I turn on the primer-design MCP?"

### Features that need a local program installed

| Feature | What to install | When it is needed |
|---|---|---|
| `xlsx` | [LibreOffice](https://www.libreoffice.org) | When recalculating or verifying Excel formulas (not needed for simple reading/writing) |
| `docx` | [`pandoc`](https://pandoc.org), LibreOffice, (final verification on Windows + MS Word) | Document conversion, applying tracked changes, final corruption check |
| `literature-review` | `pandoc` + [LaTeX](https://www.latex-project.org) (xelatex) | Only when producing PDF output (not needed for Markdown output) |
| `endnote-citation-injection` | [EndNote](https://endnote.com) 2025 + library file | This feature itself depends on EndNote |
| `publication-figures` | [`scikit-image`](https://scikit-image.org) (pip) | Only for figure reconstruction (Route 5) |
| `uncertainty-and-units` | Python 3.12+ and `pint`, `uncertainties` (pip) | When running the error-propagation and unit-conversion scripts (see [document 01](01_install-and-first-command.md)) |
| `doe-and-replication` | Python 3.12+ and `pydoe`, `pandas` (pip) | When building experimental design tables (factorial and central composite designs) |

> These programs are often already installed on lab PCs. If they are not, install them only when
> you use the corresponding feature; the other features are not affected.

---

## 3. What about external services (mail, GitHub, Asana, Notion, calendar, sheets)?

These are integrations, not skills, so they are covered separately in [05_external-services](05_external-services.md):
- Connection: the REST connectors in `scripts/connectors/` are the default → API key (token), or for calendar and sheets, OAuth
  with one-time consent. The app's "Connect" button (MCP) is a last resort only for exploratory work that REST cannot replace.
- To use them from scripts: the connectors in `scripts/connectors/` + `config/credentials.json` (environment variables).
- Outgoing actions stop at the draft: sending or deleting mail always requires confirmation / a double lock.

---

## 3-2. How big is it?

The entire distribution is about 5MB (it fits on a USB stick as is). Installing selectively makes it even smaller.
Running `python install/install.py --list` shows the size of each feature and preset.

- On the heavy side: `docx` (1.4MB) · `xlsx` (1.2MB) · `primer-design` (697KB). These three are the big ones.
- Most others: very light, at 4 to 130KB.
- Preset examples: manuscript writing 820KB · literature survey 281KB · data and figures 332KB · document work 2.8MB · everything 5MB.

> Size is almost never a concern. It is 5MB even all together. Picking and choosing is mainly about
> "not cluttering things with features you don't use."

---

## 4. So what should I do first?

1. Prepare nothing, and start with the subscription-only features while logged in to your subscription
   (paper search, statistics, data analysis, figures, and so on; most features belong here).
2. If a feature says "a key is needed / turn on a server," find its row in this document's tables and
   first check whether there is a free workaround. There usually is.
3. Prepare only the keys and installations you really need, as the need arises. There is no need to get everything ready in advance.

If you get stuck, capture the relevant row of this document's tables and ask a lab senior (the administrator).
