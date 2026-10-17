> English translation of [12_문서스킬_직접_준비하기.md](../12_문서스킬_직접_준비하기.md). The Korean original is canonical; if they differ, the Korean version wins.

# 12. About the Document Skills (docx, pdf, pptx, xlsx)

## First: document work just works

"이 워드 파일 고쳐줘" (“fix this Word file”), "PDF에서 표 뽑아줘" (“pull the tables out of this PDF”), "엑셀로 정리해줘" (“organize this in Excel”): just say it the usual way.
The ability to handle document files is provided on the [Claude Code](https://code.claude.com/docs/en/overview) side, so this toolkit does not need to fill that role.

This document explains why those skill folders are not in the repository
and describes the lab's own tools that are included anyway.

## Why they aren't in the repository

These four skills are made and distributed by Anthropic, and the accompanying `LICENSE.txt`
explicitly prohibits the following.

> - Extract these materials from the Services or **retain copies of these materials
>   outside the Services**
> - **Distribute**, sublicense, or transfer these materials to any third party

In other words, keeping a copy in this repository is itself a license violation. It is the same even if the repository
is private: the clause "do not keep copies outside the Services" applies regardless of whether it is public.

So we left out the files and kept only the connection. The installer knows its
dependencies on these skills and tells you the above when it matters.

## How to prepare them

In most cases you don't have to do anything.

If document work doesn't go well, get the relevant skill through the route Anthropic provides and place it under
`~/.claude/skills/`. The distribution route differs by Claude Code version, so we don't
put a specific link here. An outdated link is more confusing.

## Manuscript work you can still do with this toolkit

Of the manuscript QC and editing tools, the ones this lab built itself are included as they are.
They used to sit inside the `docx` skill folder, but since they aren't Anthropic code, we moved them to `manuscript-pipeline`.

| Tool | What it does |
|---|---|
| `manuscript_text.py` | Extracts the correct text from a docx with tracked changes. python-docx silently drops inserted text. Check with `--count-only` first |
| `word_com_ops.py` | Editing through Word COM: accept tracked changes, find-replace across run boundaries, replace captions, edit table cells |
| `word_live_edit.py` | Live-edits a document the user has open in Word (requires Windows + pywin32) |
| `manuscript_ref_order.py` | Diagnoses the citation order of Figures/Tables |
| `figure_caption_check.py` | Caption-to-figure consistency QC (numbers, citation order, labels) |
| `endnote_biblio_check.py` | Whether a bibliography entry actually exists for each cited number |
| `visual_check.py` | Renders the document to PNGs page by page, to check the layout by eye |

All of them are in `skills/manuscript-pipeline/scripts/`. For example:

```bash
python skills/manuscript-pipeline/scripts/manuscript_text.py MANUSCRIPT.docx --count-only
# exit 10 = tracked changes present → extract with --mode accept

python skills/manuscript-pipeline/scripts/figure_caption_check.py MANUSCRIPT.docx
```

These tools work with just python-docx (PyPI, open source), and do not
depend on the Anthropic skills.
