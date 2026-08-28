# Manuscript/Word/DOCX multi-agent workflow rules (finalized 260529)

**Principle: analysis runs in parallel, editing a single file runs serially by one agent (map-reduce).**
Applies to **any work touching a single docx file** — manuscript, Word, docx, SI, tables, citations, proofing, etc.

## Why
`word/document.xml` is a single XML file. If two agents each modify and save
the same file, last-write-wins destroys the earlier change, and byte offsets
shift out of sync, corrupting the OOXML (Word reports "file corrupted"). So
**there is always exactly one editor.**

## Standard 3-stage flow

### 1) MAP — parallel analysis/diagnosis (split up the slow part)
Multiple agents run **read/diagnose/verify-against-source/draft-patch
generation only** in parallel. Split the scope:
- by table (Table S1-S2 / S3-S4 / S5-S6 / ...), by section
  (Intro/Methods/Results), or by axis (numbers/citations/italics/spelling).
- Slow work — especially **close-reading the source PDF and recomputing
  literature values** — benefits most from parallelization.
- Each agent **does not modify the file** — it only returns a "patch spec":
  a list of `{target table/block, run text to find (unique), replacement
  content, reason}`.

### 2) REDUCE — serial edit (one agent applies the collected patches)
- **One fixer (or the main agent)** applies every patch in order to a
  single `word/document.xml`.
- Replace only document.xml via zipfile. EndNote fields (`<w:instrText>`,
  `<w:fldChar begin>..<end>`) are untouchable.
- Because this is serial, a patch conflict (two patches touching the same
  run) is caught and resolved immediately.

### 3) VERIFY — one QC agent (Word COM required)
- The 4-stage preflight + **Word COM ground-truth** + formatting
  (font/line-spacing/borders/alignment).
- Only replace the OneDrive original after this passes. Send back to the
  fixer on failure.

## Choosing a tool
- **Interactive delegation** (whatever sub-agent/task tool the agent
  provides): when a human needs to step in between stages to review and
  decide (report analysis results -> user decision -> edit). Don't tie this
  to a specific vendor API name — sub-agent for Claude Code, `spawn_agent`
  for Codex, or sequential execution in one context if neither exists.
- **Workflow tool**: when a deterministic pipeline is needed and the user
  has opted into "workflow." Fan out per-table analysis via
  `pipeline(tables, analyze, ...)` -> collect patches -> edit in a single
  reduce stage. The edit stage must always be a **single agent()**
  (worktree isolation is meaningless for docx — it's binary zip data).

## Use Track Changes + Comments heavily (per the user's 260529 instruction)

So the user can **review and accept/reject edits in Word**, wherever possible:
- **Body/table text changes -> a tracked change**: an insertion is
  `<w:ins w:id=".." w:author="Claude" w:date="..">…<w:r>…</w:r></w:ins>`, a
  deletion is `<w:del …><w:r><w:delText>…</w:delText></w:r></w:del>`. Use
  "Claude" consistently as the author.
- **Anywhere that needs judgment, rationale, or an alternative -> a
  comment**: commentRangeStart/End + commentReference +
  comments.xml (+ commentsExtended/Ids/Extensible sidecars). E.g.: "this
  figure is on a measured-total basis," "why this citation uses ref
  RecNum #N," "line spacing has been 2.0 since the original."
- Leaving a short comment for each decision/edit explaining **why it was
  done that way** creates a second, redundant trail alongside the
  Decision_Log.

**Comply with the 5 docx prohibitions** (docx integrity): pack.py /
missing delText inside a del / a nested del inside an ins / a floating
delText / a misinserted comment anchor. A comment anchor's id must be
max+1, commentRangeStart must sit at a run boundary directly under w:p, and
`rfind('<w:del ')` must be followed by a space. incremental_edit.py + the
4-stage preflight. (Details -> the docx skill, not in this repo — see
docs/12)

**When to use tracked changes vs. a direct edit:**
- Any body/table/figure/wording change the user should review -> **tracked
  + comment recommended**.
- Mechanical/structural work (unifying fonts, marker format, ZIP build) ->
  a direct edit is fine (but log it in the Decision_Log).
- If the user says "with tracking / add a comment," always use tracked +
  comment.

## Prohibited
- Two agents Writing/saving the same docx concurrently is prohibited.
- Splitting docx editing across worktrees in parallel and attempting a git
  merge is prohibited (it's binary).
- Adopting an agent's edited copy without Word COM verification is
  prohibited (this session's SI v36 corruption incident).

Related: `manuscript_qc_checklist.md`, the docx skill (not in this repo —
see docs/12) (preflight/integrity SSOT).
