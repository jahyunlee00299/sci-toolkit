# Manuscript SSOT Manifesto — read this BEFORE touching a manuscript

Before starting manuscript work (drafting, proofing, figures, numbers, citations), **read this declaration first, and follow it.**
The most common way trust in a paper breaks down isn't "the code was wrong" —
it's **"a number got copied by hand from somewhere"**. This manifesto exists to stop that.

Core line: **every number, citation, and notation comes from exactly one source of truth (SSOT), and is never copied by hand.**

---

## The Five Declarations (follow these during manuscript work)

### 1. Numbers come from the rawdata SSOT only
- **Every number** used in the body text, tables, figures, captions, and abstract must trace back to
  one canonical rawdata file (or a script that computes directly from that rawdata).
- **Never copy a number by hand** from memory, a prior report, a chat log, or another table.
- When the same value appears in multiple places (body text, table, figure CSV), **all of them must converge on the same rawdata**.
  If you see a discrepancy, don't fix just one spot — unify them against the rawdata.

### 2. Figure/table caption numbers also come from rawdata
- The n, mean, error, and conditions stated in a caption come from **the same rawdata source as the plot** — never typed by hand.
- If a figure is regenerated, its caption numbers must also be regenerated from that same source (never maintained separately).

### 3. Never guess a column name, unit, or definition
- **Never guess the column name, unit, or definition** of a computed quantity like yield, conversion, rate, or titer.
  Open the rawdata and the methods description and confirm before using it.
- Before comparing a model value against an experimental value, confirm they use **the same conditions, the same method, and the same metric definition**
  (apples-to-apples). A mismatch here produces a silently wrong result.

### 4. A number from delegation/remote work is "provisional"
- Treat a number received from another session, a background process, or a remote computation as **provisional**.
- Do not put it in the manuscript until it has been **independently reproduced in one line** from the same rawdata and matches.

### 5. Notation and citations each follow their own SSOT
- The SSOT for **notation rules** (species-name italics, units, kinetics symbols, dashes, capitalization) is a separate
  nomenclature skill/document — don't improvise from general knowledge.
- The SSOT for **DOCX editing** is the safe-editing protocol (preserves structural integrity) — never break the file with an ad hoc save.
- **DOIs/citations** are cross-verified against a primary source (CrossRef, etc.) — never guessed, and never taken on faith from an unverified tool's output.

---

## Before you finalize (the gate)

Before handing a manuscript off as "done", **actually run** the following (see AGENTS.md §8):
- **Numeric consistency**: an automated check that the same quantity doesn't conflict across body text/table/figure
  (`numeric_consistency_check.py` — iterate until it PASSes).
- **Notation check**: confirm the nomenclature lint (advisory).
- If any of the five declarations above was violated (a hand-copied number, a guessed unit, an unverified delegated value),
  **that number is not yet verified** — go back to the rawdata and re-confirm it.

---

## Why go this far

- One wrong number in a paper is enough for a reviewer to **question the trustworthiness of the entire dataset**.
- A hand-copied number can't later be traced back to "where did this come from", and a co-author or reproducer can't find it either.
- Sticking to the rawdata SSOT is actually faster when a value changes — **fix the source and regenerate**, nothing more.

> This manifesto is the principle; the tools and verification commands that execute it live in each skill and in AGENTS.md §3/§8.
> Recall these five declarations at the start of every manuscript task.
