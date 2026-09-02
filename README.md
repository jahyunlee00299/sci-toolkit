# sci-toolkit

**A shared Claude Code skillset for the lab.** A collection of instructions that
gets the AI to handle literature search, manuscript writing, figure production,
and data analysis the same way every time. Every workflow ends in a
**verification gate** — it doesn't stop at "it ran," it stops after
"confirmed the result is correct."

A shared Claude Code skillset for lab work — literature search, manuscript writing,
figure production, data analysis. Every workflow ends in a **verification gate**:
the artifact isn't done until the gate passes, and the gate is a script, not a
suggestion.

```
37 skills · 30 regression tests · 7 safety guards
python doctor.py   ->   12 OK / 0 FAIL
```

No personal accounts, PII, or funding information included. Undisclosed research
content is filtered out by a mechanical check (`doctor.py` SENTINEL).

| I am… | start here |
|---|---|
| new here, not sure what's what | [docs/00_시작하기](docs/00_시작하기.md) (Getting Started) |
| just want to install first | [QUICKSTART.md](QUICKSTART.md) — install only the skills you need |
| want to understand how it works | [docs/10_전체_워크플로우_지도](docs/10_전체_워크플로우_지도.md) (Full Workflow Map) |
| the AI keeps going off track | [AGENTS.md](AGENTS.md) §0 routing table -> say "follow §0" |
| want to work with Word/PDF/PPT/Excel | just ask — it's a built-in Claude Code capability. See the [module list](#-word--pdf--ppt--excel) for manuscript QC tools |
| found something annoying while using it | [docs/11_불편한점_남기기](docs/11_불편한점_남기기.md) (Filing Feedback) — say it and it's recorded automatically |
| the terminal is hard to read (colors, Korean-character width, tabs) | [docs/14_터미널_읽기좋게](docs/14_터미널_읽기좋게.md) (Making the Terminal Readable) — `python scripts/terminal_setup.py` |
| **I use Codex, not Claude Code** | [CODEX.md](CODEX.md) — hooks don't work there; separate notes |

---

## What is sci-toolkit?

Each folder under `skills/` is a set of instructions organized as "in this
situation, do this," with a helper script attached where needed. It's documents,
not code, so Claude Code reads the conversation context and picks the right one
on its own — nothing needs to be run directly.

## What's inside (37 skills)

| Area | Skills |
|---|---|
| **Literature search & writing** | `research-search` (entry point) · `research-lookup` · `openalex-database` · `pubmed-database` · `biorxiv-database` · `web-scraping` · `paper-extract` · `literature-review` · `research-ideation` · `manuscript-pipeline` · `academic-term-rules` · `endnote-citation-injection` |
| **Molecular biology & experiments** | `primer-design` · `experiment-hub` |
| **Figures** | `publication-figures` · `markdown-mermaid-writing` · `generate-image` |
| **Data & statistics** | `data-quality-checks` (pre-analysis table check) · `lab-data-analysis` · `stats-workflow` · `statsmodels` · `analysis-code-testing` · `conda-env-manager` · `get-available-resources` |
| **Document conversion** | `markitdown` (PDF/docx/xlsx/image OCR -> Markdown) · `journal-presentation-maker` |
| **Verification & development discipline** | `scientific-validation` · `spec-first-development` · `test-first-development` · `code-quality` · `avoid-ai-writing` · `git-workflow-manager` · `skill-developer` · `token-efficient-routing` · `debugging-loop` · `test-quality` · `spec-driven-research-dev` |

> **Word, PDF, PPT, Excel** are handled without a skill — a built-in Claude Code
> capability. The 7 manuscript QC tools live under `skills/manuscript-pipeline/scripts/`.

## How to use it

Just talk to it normally.

```
"find papers on this topic"     "design a primer for me"      "what stats test should I use for this data?"
"redraw this figure"            "check the manuscript notation"    "does this result make sense?"
```

Install only what you need:

```bash
python install/install.py --list                      # check the catalog
python install/install.py --preset paper-writing --apply
python doctor.py                                      # PASS means ready
```

---

<details>
<summary><b>📄 Word · PDF · PPT · Excel — why there's no skill folder for these</b></summary>

<br>

Document work runs without a skill. Say "fix this Word file" and it's handled
the normal way. These skills aren't in the repository not because the
capability is missing, but because they are Anthropic-owned assets that
cannot be redistributed ([docs/12](docs/12_문서스킬_직접_준비하기.md), "Preparing Document Skills Yourself").

Use `markitdown` when a PDF/document needs to be read as text. It converts
PDF/docx/pptx/xlsx/images (OCR) to Markdown, and `paper-extract` and
`journal-presentation-maker` both go through this path when reading a paper PDF.

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
| `docs/` | 15 beginner docs (getting started -> install -> API/MCP -> tokens & cost -> ... -> full workflow map -> getting a token via Chrome) |
| `tests/` | 30 regression tests (secrets/research markers, reference existence, routing consistency, non-destructive install, capability loss, bidirectional hooks, hook file wiring, Codex hook adapter, doctor auto-run after install, feedback channel/sanitization gate, dual-credentials-store detection, connector dry-run/`--write` gate, service/skill routing target existence, adopted-discipline-skill clause existence, development-discipline-skill clause existence, spec-driven 4-stage contract existence, adopted-skill clause existence, dead-automation detection). `doctor.py` runs all of them automatically |
| `doctor.py` | Integrity/environment check. `PASS` means it's ready |
| `evals/` | Headless measurement of whether routing **actually fires** (slow, costs money — run manually) |
| `scripts/capability_diff.py` | After a skill gets rewritten, structurally diffs **whether a capability quietly disappeared** |
| `scripts/feedback_log.py` | Records inconveniences/errors (no account or token needed) |
| `SHA256SUMS` | Hashes for every file — verify integrity after copying/transferring |

</details>

<details>
<summary><b>⚙️ Install details — where, and how</b></summary>

<br>

A skill is just a directory — there's no separate registration step.

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

**Base environment**: Claude Code (subscription). Most skills need no API key;
only a few external-database lookup skills use a free API or an optional key.
Each `SKILL.md` states which.

If using another agent such as Codex, read [CODEX.md](CODEX.md) first.

</details>

---

<details>
<summary><b>🔒 Safety notice — what's NOT included</b></summary>

<br>

- No PII, account credentials, or funding information is included.
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

This distribution ships with no personal data, account credentials, or funding
information: `.distignore` strips it at packaging time, and `doctor.py`'s SENTINEL
scan checks for it mechanically. If you extend it, don't add personal tokens, emails,
or grant numbers — and check with the lab admin before redistributing outside the lab.

</details>
