# Docs genre: README, install guides, how-tos

Read this when the text under audit is a README, quickstart, install guide or tutorial
that carries links, code blocks and tables, or a Korean/English pair of such guides.
The general rules in `SKILL.md` still apply; this file says how to apply them to the
parts that prose rules ignore, and what the measured targets are. Source: the sci-toolkit
README and docs/00-14 (ko + en), edited 261017.

## 1. Calibrate against human docs, not the generic rules

Twelve human-written docs (first commit before 2022, named author; 8 English, 4 Korean)
gave these targets, per 1,000 words unless noted:

| Metric | English median | Korean median |
|---|---|---|
| em dash | 0 | 0 |
| bold spans | 1.3 | 4.9 |
| bullet share of non-empty lines | 0.125 | 0.385 |
| blockquote share | 0 | 0.125 |
| mean sentence length (words) | 7.9 | 7.75 (SD about 4) |

How those docs write: they open with one plain sentence saying what the thing is, with no
welcome; a warning is one inline line ("Note: ..."); a step is a short sentence plus a code
block; the tone is matter-of-fact; there is almost no cheerleading; the doc just stops (a
link list, a license, or a leftover detail), with no closing summary.

Treat the Korean column as directional only: the set was four short student notes
(400 to 1,000 words), not lab-software guides. No collector tool covers the README genre, so
this reference set was picked by hand (`gh api repos/O/R/commits?path=FILE`, oldest commit
date). Refresh it the same way when the targets matter.

Before editing, measure: `python scripts/doc_metrics.py FILE...` prints em dash, bold,
bullet and quote share, heading dashes and sentence statistics per file.

## 2. Element protocol

| Element | Rule |
|---|---|
| Prose paragraph | Edit as in `SKILL.md`. Cut a reassurance only when it states no checkable fact; keep a practical "ask a lab member" line |
| Heading | Remove dash and emoji. If the wording changes, grep the repo for the old anchor slug first |
| Table cell | Prose-only swaps (dash to colon or comma, unbold emphasis). A lone `—` is an empty-cell marker: keep it. Never touch data cells |
| Bold on a UI label | Keep (`Yes`, `No`, `Manual`, a button name): it marks something the reader must find on screen |
| Code block | Never edit the code. A comment inside it is prose: swap its dash |
| Inline code, URLs, link targets, numbers | Byte-identical |
| Quoted tool output (a connector message, an error text) | Keep verbatim even when it contains a dash |
| Emoji legend (green circle, padlock) | Replace with the word it stands for, the same word everywhere in that doc |
| Closing "summary" section or recap table | Delete when the body already carries every fact; keep a trailing "Next:" link line |
| Rule files read by agents (`AGENTS.md`, `CLAUDE.md`) and ledgers | Out of scope: tests grep their clauses |

## 3. Bilingual pairs

Find out which side is canonical (the translation header usually says). Edit the canonical
file first, then bring the translation to say what the edited original says. Keep the
translation header line. Do not let the two drift in meaning; if one must differ on purpose,
list it in the report.

## 4. Mechanical gates

`python scripts/preserve_check.py REPO_ROOT FILE...` compares each file with `git show HEAD:FILE`
and reports any change in code fences, inline code, link targets, bare URLs, table rows and
digit tokens, plus any `#anchor` link that no longer matches a heading. A deliberate deletion
(a summary section that held inline code) shows up as a DIFF: list those in the report instead
of forcing the check green. Run it and the metrics script after editing, and report before and
after numbers.

## 5. Traps measured on this job

- Windows Python `Path.write_text` turns `\n` into `\r\n`. With `eol=lf` in `.gitattributes`
  git then warns "CRLF will be replaced" and the diff gets noisy. Write bytes
  (`write_bytes(text.encode("utf-8"))`) and check `git ls-files --eol`.
- A count pinned by a test (`16 beginner docs`) goes quiet when its word is translated: the
  README said "초심자 docs", the regex wanted "beginner docs", and the check silently stopped
  checking. After touching a line that holds a number, run the test and confirm it counted
  that line.
- Regenerate checksum manifests after the edit, and stage new files first: the generator
  skips untracked files and says so.
- Parallel lanes (one agent per file group) work when file lists are disjoint and each lane
  must report `preserve_check` and metrics. An agent notice that says it is "waiting on
  background work" may be interim: read the files, not the report.
- A guide can be clean and still assume something it never says (here: the repository
  folder already exists). Missing steps are content work, not tell removal: write them as
  a separate change with verifiable facts, and flag the gap.
- Do not add a number, step or caveat the file did not hold. If a vague claim has no
  concrete detail available, cut it or leave it.
