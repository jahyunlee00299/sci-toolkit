---
name: lab-record
description: Unified lab record for experiment METHODS and research DISCUSSION — protocol versions (PROT), experiment runs (EXP), result interpretation / literature comparison / lab-meeting discussion (DISC) and research decisions (DEC), linked into one traceable chain with ID allocation, integrity lint and trace/impact queries. Use to write or version a protocol, log a run, interpret or discuss results, record a lab-meeting discussion, structure a paper's Discussion section, record a decision, or answer "which runs/decisions rest on this protocol?". 한국어 트리거 — 실험 기록, 프로토콜 기록·버전, 메소드 정리, 결과 해석, 디스커션, 디스커션 기록, 랩미팅 정리, 문헌이랑 비교, Discussion 어떻게 쓸까, 결정 기록, 이 결정 근거, 이 프로토콜 쓴 실험. For designing conditions / DoE / pipetting workbooks / trendlines use experiment-hub; for raw data analysis use lab-data-analysis; for statistics use stats-workflow; for brainstorming new hypotheses use research-ideation; for actually drafting manuscript prose use manuscript-pipeline.
license: MIT
---

# Lab Record — methods + discussion in one chain

```
PROT@vN ──▶ EXP ──▶ DISC ──▶ DEC ──▶ (PROT@vN+1 | new EXP | manuscript section | task proposal)
```

The contract (IDs, frontmatter, integrity rules, layout) is `references/schema.md`. Read it before
writing the first record of a session. This file says WHEN to write which record and HOW to do the
thinking that goes into DISC; the script does the bookkeeping.

## Setup (once per machine)

1. Copy `config.example.json` to `~/.config/lab-record/config.json` (or pass `--config`).
2. Set `root` to the folder that holds the records; fill `people` with short keys
   (`"person1": "..."`). Real display names live in config files, never in records.
3. `python scripts/lab_record.py lint` → exit 0 on an empty root.

**Shared config.** A lab can ship ONE `lab-record.config.json` inside the root (`people` +
`projects`, each project with `folder` relative to the root and optionally `asana_project`).
Members then need only the folder: run the tool from anywhere inside the root (it walks up from
the cwd to find that file) or give a local config with just `root` and any personal overrides
(local wins per key). A `root` key inside the shared file is ignored.

Root resolution: `--root` > env `LAB_RECORD_ROOT` > local config `root` > cwd walk-up. Notifications
are off by design: writing a record never posts to Notion, Asana or Telegram.

**Project folders and `@/`.** With `projects.<key>.folder` set, a path value such as
`raw_data: ["@/sub/run.csv"]` (also `workbook`, `matrix_config`, `links[].path`) means "inside this
record's project folder". Set `project:` on the record, or lint flags it (RULE7).

**Sync-conflict copies.** OneDrive/Dropbox conflict files (`EXP-...-DESKTOP-AB12.md`, `... (1).md`)
are reported by lint RULE8 (duplicate id / filename ≠ id). Resolve by diffing the two, keeping the
canonically named file, and deleting the copy; never rename a copy to the canonical name over the
original.

**Catalog.** Optional `<root>/catalog.json` names the lab's enzymes, standards and sheets
(`kind → name → {project, path, aliases, note}`). Link them from PROT/EXP as
`links: [{rel: enzyme, name: "<name or alias>"}]` (rel = `enzyme | standard | sheet`) instead of
free text; lint checks that the name resolves and the file exists, RULE9 flags stale catalog paths.
"이 효소 쓴 실험" → `uses <name>`; overview → `catalog [--kind K]`.

## Mode → record

| Mode | User says | Record | Procedure |
|------|-----------|--------|-----------|
| P. Protocol | "프로토콜 만들어/기록", "method 정리" | PROT | Delegate condition design to experiment-hub Mode 1 (reference search) / Mode 10 (matrix). Then `new prot`. Changing a method = `new prot --from-prot PROT-xxx` (new version, old one superseded) — never edit a used version in place. |
| E. Run | "실험 기록해줘", "결과 들어왔어" | EXP | `new exp --protocol PROT-xxx@vN`. Record only conditions that differ from the protocol default, every unplanned deviation, raw-data paths. Observations only — no interpretation. |
| M1. Interpret | "이 결과 어떻게 해석?", "메커니즘?" | DISC mode M1 | Context checklist → ranked interpretations (below). |
| M2. Compare | "문헌이랑 비교", "이전 실험이랑 왜 달라" | DISC mode M2 | Three-way comparison (below). Pure numeric run-vs-run delta → experiment-hub Mode 7 first, then interpret here. |
| M3. Structure | "Discussion 어떻게 쓸까" | DISC mode M3 | 7-step skeleton; prose drafting → manuscript-pipeline. |
| Meeting | "랩미팅 정리", "디스커션 기록" | DISC mode meeting | Who/what/which runs, interpretations raised, open questions; spin off a DEC for every agreed outcome. |
| D. Decide | "이걸로 가자", "결정 기록" | DEC | `new dec --from DISC-...`. Alternatives rejected + why, `revisit_if`, `next`. |
| Q. Query | "이 결정 근거", "이 프로토콜 쓴 실험", "이 효소 쓴 실험", "안 끝난 거" | — | `trace` / `impact` / `uses` / `catalog` / `open`. |

Chain shortcut (M1 → M2 → M3 → DEC): run the modes in order, one DISC per mode or one DISC
updated before closing, then a DEC for each conclusion.

After writing or editing any record: `lint` (exit 1 = fix before reporting done), then `index`.

## M1 — interpretation rules

**Context checklist (mandatory, before interpreting).** Reaction temperature · pH/buffer · time ·
substrate identity/concentration · enzyme identity/concentration · cofactors · volume; when
relevant: oxygen, enzyme origin, purification level, analytical method. Fill
`context_checklist` with `ok | unknown | n/a`. An `unknown` item is never assumed — say what it
blocks. Pull history with `impact` on the protocol and from the EXP records named in `about`.

**Output shape.**
```
Result: <observed> | Conditions: <key conditions>
Interpretation 1 (most likely) ★★★  explanation / evidence (data, literature, mechanism) / how to confirm
Interpretation 2 (alternative) ★★☆  ...
Excluded: <claim> — <reason>
Conclusion & next step
```
Mirror this into `interpretations` / `excluded` / `open_questions` in the frontmatter.

**Interaction matrix (mandatory when ≥3 species are present in vitro).**
1. Chemical stability / degradation (spontaneous hydrolysis, isomerisation, oxidation, metal ions)
2. Non-enzymatic modification of the enzyme (acetylation, phosphorylation, glycation, chelation)
3. Direct species–species reactions (metal–phosphate precipitation, pH drift)
4. Inhibition (substrate / product / cofactor, reverse-reaction equilibrium, dead-end); for
   isomerisation/equilibrium steps compare observed [P]/[S] with theoretical Keq(T, pH)
5. Time-dependent change (early → mid → late behaviour)

Multi-enzyme cascades: close the carbon balance (Σ species = const); a deficit is a hidden product.

## M2 — comparison rules

Three sources: this result · earlier EXP records (same protocol via `impact`, or named) ·
literature (research-search). Topic folders of background material (reviews, vendor docs, earlier
notebooks) are cited with `links: [{rel: background, path: "@/<topic folder>"}]` — lint checks only
that the path exists. Classify every difference:
- **[intended]** a parameter deliberately changed (appears in `conditions`)
- **[unintended]** something not changed on purpose (check `deviations`)
- **[implementation]** reference method/code vs. literature differences
- **[condition]** differing experimental conditions between sources

## M3 — Discussion skeleton

① key finding → ② interpretation → ③ literature comparison → ④ contribution/significance →
⑤ limitations → ⑥ future work → ⑦ conclusion. Each step cites the DISC/EXP IDs it rests on, so
manuscript-pipeline can trace every Discussion claim back to a run.

## Asana (read-only context)

Asana is context, never a target. When writing a DISC/DEC for a project whose config has
`asana_project`, first read that project's recent tasks and comments through the
toolkit connector `scripts/connectors/asana_connector.py` (read commands only: `me`, `tasks`; never `add-task`, `add-comment`, `add-subtask`), use them as background, and cite the tasks you relied on with
`links: [{rel: asana, task: "<gid>"}]` (or `{rel: asana, project: "<gid>"}`); lint checks the digits
only. This skill never posts, comments on or creates anything in Asana — follow-ups stay `DEC.next
kind: task` proposals for the researcher to act on.

## Citations

APA 7th in prose: (Kim, 2024) · (Kim & Park, 2024) · (Kim et al., 2024). Every reference carries a
DOI (PubMed URL if no DOI) — DOIs go into `literature:`; a reference list closes the DISC body.
Numbers taken from a paper are verified against the paper, not restated from memory.

## Rules

- Interpretations are proposals; the researcher decides (a DEC is written only when the user
  agrees on an outcome).
- Never edit a closed record — add `## Addendum (YYYY-MM-DD)` or write a new record with
  `supersedes:`. Lint RULE1 enforces it.
- Show the target path before writing a new record outside the configured root.
- Raw data is referenced by path, never copied into a record, and never bulk-read from cloud
  folders (existence check only).
- Old notebook files are not migrated; cite them with `links: [{rel: legacy, path: ...}]`.
- When writing a PROT/EXP, link enzymes, standards and sheets by catalog name, not free text.
- A protocol bug found later → `impact PROT-xxx@vN` lists every run and decision to revisit.

## Related skills

- **experiment-hub** — condition design (Mode 1 references, Mode 2 DoE/RSM, Mode 10 reaction
  matrix / pipetting workbook), trendlines (M5), pattern analysis (M6), run-vs-run deltas (M7).
  Its outputs land here as PROT / EXP.
- **lab-data-analysis** · **stats-workflow** — analysis feeding an EXP or DISC.
- **doe-and-replication** — the design, seed, pydoe version and replicate level (technical vs independent preparation) belong in the EXP record; **uncertainty-and-units** — what the `±` in a recorded result is.
- **research-search** · **literature-review** — literature for M1/M2.
- **research-ideation** — open-ended brainstorming / hypotheses; a hypothesis worth testing
  becomes a PROT or EXP here.
- **manuscript-pipeline** — turns an M3 skeleton into prose; its Decision Log for manuscript edits
  is separate from DEC (research decisions).
- **scientific-validation** — before a number from an EXP goes into a DEC or a manuscript.
