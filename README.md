# sci-toolkit

**A shared Claude Code skillset for the lab.** A collection of instructions that
gets the AI to handle literature search/writing, molecular biology, figures,
statistics, the lab portal, and work-logging the same way every time. Every
workflow ends in a **verification gate** — it doesn't stop at "it ran," it
stops after "confirmed the result is correct."

```
40 skills · 39 regression tests · 7 safety guards
python doctor.py   ->   15 checks · 0 FAIL
```

No personal accounts, PII, or funding information included. Undisclosed
research content is filtered out by a mechanical check (`doctor.py` SENTINEL).

| I am… | start here |
|---|---|
| 초심자, not sure what's what | [docs/00_시작하기](docs/00_시작하기.md) (Getting Started) |
| just want to install first | [QUICKSTART.md](QUICKSTART.md) — install only the skills you need |
| want to understand how it works | [docs/10_전체_워크플로우_지도](docs/10_전체_워크플로우_지도.md) (Full Workflow Map) |
| the AI keeps going off track | [AGENTS.md](AGENTS.md) §0 routing table -> say "follow §0" |
| want to work with Word/PDF/PPT/Excel | just ask — it's a built-in Claude Code capability. See the [module list](#module-list) |
| found something annoying while using it | [docs/11_불편한점_남기기](docs/11_불편한점_남기기.md) (Filing Feedback) — say it and it's recorded automatically |
| **I use Codex, not Claude Code** | [CODEX.md](CODEX.md) — hooks don't work there; separate notes |

---

## What is sci-toolkit?

Each folder under `skills/` is a set of instructions organized as "in this
situation, do this," with a helper script attached where needed. It's
documents, not code, so Claude Code reads the conversation context and picks
the right one on its own — nothing needs to be run directly.

**Base environment: Claude Code + a subscription (Pro/Max), used first.**
Most skills need no separate API key; only a handful of external-database
lookup skills use a free API or an optional key, and each `SKILL.md` states
which.

## Module list

논문검색·작성 / 분자생물학 / figure / 통계 / 포털 / 작업로그 — six areas the
lab actually works in. Not every area is a `skills/` folder; a few are a
script or a doc instead, and that's noted below.

| 영역 (Area) | 내용 (What it covers) | 모듈 (Module) |
|---|---|---|
| **논문검색·작성**<br>Paper search & writing | Find/summarize/review papers, draft and polish a manuscript, insert EndNote citations, write a patent disclosure | `research-search` (entry point) · `research-lookup` · `openalex-database` · `pubmed-database` · `biorxiv-database` · `web-scraping` · `paper-extract` · `literature-review` · `research-ideation` · `manuscript-pipeline` · `patent-invention-disclosure` · `academic-term-rules` · `endnote-citation-injection` |
| **분자생물학**<br>Molecular biology | Primer/sequence design, hairpin/dimer QC, variant-QC matrices, public vector fetch, lab experiment tracking | `primer-design` · `experiment-hub` · `scripts/primer_structure_check.py` · `scripts/variant_filter.py` · `scripts/fetch_public_vector.py` |
| **figure** | Publication figures, mermaid diagrams, AI-generated schematics, HPLC chromatogram parsing for plotting | `publication-figures` · `markdown-mermaid-writing` · `generate-image` · `scripts/hplc_parser.py` |
| **통계**<br>Statistics | Pre-analysis data-quality checks, test selection, general stats workflows, statsmodels-based analysis | `data-quality-checks` · `stats-workflow` · `statsmodels` · `lab-data-analysis` |
| **포털**<br>Portal | ⚠️ No dedicated portal skill ships in this package yet. The closest existing pieces are `get-available-resources` (what's installed/available right now) and `doctor.py` (environment/integrity status as a single dashboard-style report). Request a real lab-portal skill from the admin if this is a recurring need. | `get-available-resources` · `doctor.py` |
| **작업로그**<br>Work log | Record what was tried, what failed, and inconveniences hit while using the toolkit — the closest thing to a lab notebook this package ships | `scripts/feedback_log.py` · `experiment-hub` · `CHANGELOG.md` (toolkit's own change log, for reference) |

> **Word, PDF, PPT, Excel** are handled without a skill — a built-in Claude
> Code capability. The 7 manuscript QC tools live under
> `skills/manuscript-pipeline/scripts/`.

## How to load it

A skill is just a directory — there's no separate registration step. Copying
the folder into Claude Code's skills location *is* the install.

```bash
python install/install.py --list                      # check the catalog
python install/install.py --preset paper-writing --apply
python doctor.py                                      # PASS means ready
```

- Default install target: `~/.claude/skills/` (auto-detected). Use `--dest`
  for a different location.
- Existing files are kept; a same-named file is updated, a file that only
  existed at the destination is preserved. `--force` for a full replacement.
- Restart Claude Code (or open a new session) after installing — skills are
  picked up at session start.

See [QUICKSTART.md](QUICKSTART.md) for the 5-minute 초심자 path from a USB
drive, including which install mode to pick.

## How to use it

Just talk to it normally.

```
"find papers on this topic"     "design a primer for me"      "what stats test should I use for this data?"
"redraw this figure"            "check the manuscript notation"    "does this result make sense?"
```

---

<details>
<summary><b>📄 Word · PDF · PPT · Excel — why there's no skill folder for these</b></summary>

<br>

Document work runs without a skill. Say "fix this Word file" and it's handled
the normal way. These skills aren't in the repository not because the
capability is missing, but because they are Anthropic-owned assets that
cannot be redistributed ([docs/12](docs/12_문서스킬_직접_준비하기.md), "Preparing
Document Skills Yourself").

Use `markitdown` when a PDF/document needs to be read as text. It converts
PDF/docx/pptx/xlsx/images (OCR) to Markdown, and `paper-extract` and
`journal-presentation-maker` both go through this path when reading a paper
PDF.

The 7 manuscript QC/editing tools were built in-house by the lab, so they're
included as-is:

```bash
# python-docx text is wrong when tracked changes are present — always check before feeding it in
python skills/manuscript-pipeline/scripts/manuscript_text.py MANUSCRIPT.docx --count-only
python skills/manuscript-pipeline/scripts/figure_caption_check.py MANUSCRIPT.docx
python skills/manuscript-pipeline/scripts/word_com_ops.py --help    # Windows + Word
```

</details>

<details>
<summary><b>🔑 Getting the full paper text — prefer OA, use the campus network for institutional subscriptions</b></summary>

<br>

`scripts/ref_fetch.py` is open-access (OA) only. It cross-verifies via
CrossRef/OpenAlex/Unpaywall to collect OA PDFs, and marks a paywalled paper as
`oa_status: closed` with no workaround.

```bash
python scripts/ref_fetch.py --doi 10.1016/j.example.2026.01.001 --download
```

**Institutionally-subscribed papers** (e.g. via a university library) require
school authentication and cannot be fetched by script. Get them manually in
this order:

1. Pull the DOIs marked `oa_status: closed` from `refs_report.json`
2. Visit the DOI while **on the campus network** or logged into the library's
   remote-access service (e.g. EZproxy)
3. Place the downloaded PDF in the working folder and point to its file path

> ⚠️ **Off-campus access restrictions**
> - Opening an institutional-subscription paper link directly from off-campus
>   only shows the paywall screen. That's not an error — it means
>   authentication hasn't happened yet; log into the library's remote-access
>   service first.
> - A remote-access session expires after a while. If several papers download
>   fine and then it starts failing partway through, that's usually a session
>   expiring — log back in and continue.
> - No automated bulk downloading. Scraping many papers in a short time can
>   get the publisher to block the entire institutional IP range, and the
>   whole lab pays for that. Fetch only what's needed, and do it by hand.
> - This toolkit does not support paywall bypass or scraping (a design
>   principle of `ref_fetch.py`). Never ask the AI to "get around it and
>   fetch it anyway."

</details>

<details>
<summary><b>🧰 Package layout — what does what</b></summary>

<br>

| Item | Purpose |
|---|---|
| `AGENTS.md` | **The operating rules the AI follows.** The §0 routing table decides "which request -> which skill -> which verification" |
| `install/install.py` | Selective install — by preset or individual skill, auto-pulling in dependent skills, merging in without touching existing files |
| `config/catalog.json` | Skill catalog SSOT (categories, dependencies, size, presets) |
| `hooks/` | 7 safety guards — secrets, forced deletes, dangerous git (including fork-upstream pushes), cloud recursive scans, plus 3 for Windows environment mismatches |
| `scripts/` | Research helper tools (HPLC parser, primer check, JCR verification, `ref_fetch.py`, etc.) + external-integration connectors |
| `docs/` | 15 초심자 docs (getting started -> install -> API/MCP -> tokens & cost -> ... -> full workflow map -> getting a token via Chrome) |
| `tests/` | 39 regression tests (secrets/research markers, reference existence, routing consistency, non-destructive install, capability loss, bidirectional hooks, hook file wiring, Codex hook adapter, doctor auto-run after install, feedback channel/sanitization gate, dual-credentials-store detection, connector dry-run/`--write` gate, service/skill routing target existence, adopted-discipline-skill clause existence, development-discipline-skill clause existence, spec-driven 4-stage contract existence, adopted-skill clause existence, dead-automation detection, tool connectivity ratchet, standalone-tool smoke, doctor self-test verdicts: outage vs broken, shared HTTP retry policy, SKILL.md size ratchet, Agent Skills frontmatter contract, per-skill dependency declaration, gitleaks second layer, patent numeric-claim arithmetic gate). `doctor.py` runs all of them automatically |
| `doctor.py` | Integrity/environment check (`doctor_lib/` holds the checks). `PASS` means it's ready; `--offline` keeps every self-test off the network |
| `evals/` | Headless measurement of whether routing **actually fires** (slow, costs money — run manually) |
| `scripts/capability_diff.py` | After a skill gets rewritten, structurally diffs **whether a capability quietly disappeared** |
| `scripts/connectivity_check.py` | Lists every shipped tool that nothing leads to (ORPHAN) or nothing tests (UNTESTED). `doctor.py` runs it |
| `scripts/feedback_log.py` | Records inconveniences/errors (no account or token needed) — the 작업로그 tool |
| `scripts/hplc_parser.py` | HPLC chromatogram `.ch`/`.txt`/`.csv`/`.arw` -> CSV/JSON with auto-detected, integrated peaks (stdlib only) |
| `scripts/primer_structure_check.py` | Hairpin / homodimer dG for a primer list (nearest-neighbor model), PASS/FAIL per primer |
| `scripts/variant_filter.py` | Merges ddG, primer-QC and expression CSVs into one PASS/FAIL matrix per variant |
| `scripts/fetch_public_vector.py` | Fetches a PUBLIC plasmid/vector by NCBI accession for the primer-design registry (network) |
| `scripts/jcr_batch_verify.py` | Enriches a journal impact-factor cache with OpenAlex venue data (network) |
| `scripts/excel_formula_check.py` | Windows-native (Excel COM) scan of a workbook for live `#REF!`/`#DIV/0!`/... errors — no LibreOffice needed |
| `skills/markitdown/scripts/convert_literature.py` | Batch-converts a folder of paper PDFs to Markdown for review (needs the `markitdown` package) |
| `skills/web-scraping/scripts/fetch_github.py` | GitHub repo discovery/monitoring through the official REST API (5th web-scraping mode) |
| `SHA256SUMS` | Hashes for every file — verify integrity after copying/transferring |

</details>

<details>
<summary><b>⚙️ Install details — where, and how</b></summary>

<br>

```bash
python install/install.py --list                          # catalog and presets
python install/install.py --preset paper-writing --apply  # by preset
python install/install.py --skills primer-design --apply  # individually
python install/install.py --skills docx --dest ./my-skills --apply
```

- If `--dest` is omitted, the environment is auto-detected and placed
  accordingly (`~/.claude/skills` for Claude Code). The output shows where it
  landed.
- Existing files are kept. A same-named file gets updated; a file that only
  existed at the destination is preserved. Pass `--force` for a full
  replacement.
- Copying just one folder works too — a full install isn't required.

**Base environment**: Claude Code (subscription) is the default, used first —
most skills need no API key; only a few external-database lookup skills use
a free API or an optional key. Each `SKILL.md` states which. An all-in-one
install (the `all` preset) is a manual, opt-in step (§Step 4 of
[QUICKSTART.md](QUICKSTART.md)), not the recommended default.

If using another agent such as Codex, read [CODEX.md](CODEX.md) first.

</details>

---

<details>
<summary><b>🔒 Safety notice — what's NOT included</b></summary>

<br>

- **No PII, account credentials, or funding information is included.**
  `.distignore` strips these out automatically at packaging time, and
  `doctor.py`'s SENTINEL scan mechanically checks for secrets, personally
  identifiable information, and undisclosed-research markers.
- When adding or editing a skill directly, never include a personal token,
  email, or grant number — `doctor.py` will FAIL if one is present.
- Get admin confirmation before redistributing outside the lab.
- **License**: the repository as a whole is MIT ([LICENSE](LICENSE)), but
  individual skills may carry their own license — check the header of each
  `SKILL.md` before redistributing ([NOTICE.md](NOTICE.md)). `docx`, `pdf`,
  `pptx`, and `xlsx` are Anthropic-owned and therefore not included in this
  repository, though document work itself still works as a built-in Claude
  Code capability.

This distribution ships with no personal data, account credentials, or
funding information: `.distignore` strips it at packaging time, and
`doctor.py`'s SENTINEL scan checks for it mechanically. If you extend it,
don't add personal tokens, emails, or grant numbers — and check with the lab
admin before redistributing outside the lab.

</details>
