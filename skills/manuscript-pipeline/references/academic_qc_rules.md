# Academic QC Mode — rules and traversal patterns (manuscript-pipeline reference)

> Detailed rules and traversal code for `academic-qc` mode.
> **The single source of truth (SSOT) for notation rules is the `academic-term-rules` skill** —
> R1–R13 below are just an operating table mapping those rules onto docx QC work; the rule
> definitions themselves follow academic-term-rules.

Full-pass correction of academic notation rules. Use on a "fix the academic rules" or
"standardize notation" request.

## Output structure
```
corrections/
  step0_original.docx      copy of the original (untouched)
  step1_enzyme_italic.docx R1: enzyme-name italics   (body + table cells + captions)
  step2_abbrev.docx        R2: abbreviation unification (body + table cells + captions)
  step3_units.docx         R5: unit notation          (body + table cells + captions)
  step4_species_italic.docx R6: species-name italics  (body + table cells + captions)
  step5_comments.docx      R3/R4/R8/R9/R12: flag comments inserted
  step6_final.docx         final merged version
  QC_REPORT.md             R7/R10/R11/R13 diagnosis + font/caption/table verification results
```

## Diagnose first (mandatory before editing): verification report
Generate a **read-only diagnostic report** before any direct edit (step1–4). Table cells,
captions, and fonts produce many false positives, so report → user confirmation → selective
fix is safer than a blanket auto-fix.
Report items: A. font-size consistency (body mode sz / table-cell sz / caption sz), B. caption
notation (R12), C. table-cell body text (R1/R2/R5/R6/R10 violations), D. three-line table (R7).
State the location of every violation (table N row/column, first 30 chars of the caption, para index).

## Applied rule list (definitions in academic-term-rules §N)

| Rule | Description | academic-term-rules | Handling | Scope |
|------|------|------|----------|----------|
| R1 | Enzyme name: only the 2-letter species prefix is italic (`*Xx*GDH`) | §2 | Direct edit | Body + **table cells** + captions |
| R2 | Abbreviation unification (per domain registry) | §3, domain_abbrev_registry.md | Direct edit | Body + **table cells** + captions |
| R3 | Fig./Table numbers cited out of order | §7 | `[NUMBERING]` comment | Body + captions |
| R4 | Citation number moved to end of sentence | — | `[CITATION-LOC]` comment | Body |
| R4b | Citation number goes **after punctuation** (`word.³³`, outside the period) — numeric-superscript journals (RSC/ACS/Nature). `word³³.` is a violation. Auto-handled for EndNote RSC style → an unformatted `[N].` gets a format recommendation | §8a | `[CITATION-LOC]` comment | Body |
| R5 | Unit notation: slash form (g/L, g/g, U/mL), no superscript ⁻¹, space between number and unit | §4 | Direct edit | Body + **table cells** + captions |
| R6 | Species name italics (*E. coli*) | §1 | Direct edit | Body + **table cells** + captions |
| R7 | Three-line table | §13 | `[FIGURE-FORMAT]` comment | **Tables** |
| R8 | Missing first-use definition of an abbreviation | §3 | `[ABBREV]` comment | Body |
| R9 | Sentence starting with a numeral | §6 | `[GRAMMAR]` comment | Body + captions |
| R10 | *K*eq → italic K + subscript eq | §5, §11 | `[NOTATION]` comment | Body + **table cells** + captions |
| R11 | Font-size consistency | — | `[FONT-SIZE]` comment or direct unification | Body + **table cells** + captions |
| R12 | Caption notation (`Figure N.`/`Table SN.` label, number, bold, period) | §7, §13 | `[CAPTION]` comment | Captions |
| R13 | Table-cell arrow (→): allowed in Scheme/equation/table, a violation only in body text | — | Count reported | **Tables** / body |
| R14 | American spelling (titer/optimize/…), preserving proper nouns and quoted titles | §15 | Direct edit | Body + **table cells** + captions |
| R15 | *E*-factor (only E is italic), sEF/cEF roman, green-metric notation | §16 | Direct edit + `[NOTATION]` | Body + **table cells** + captions |

**Scope caution (critical):** R1, R2, R5, R6, R10, R11 traverse not just body paragraphs but
every `<w:tc>` cell inside a `<w:tbl>`, down to figure/table caption paragraphs. Looking only at
top-level body `<w:p>` easily misses table cells and captions.

**★ Multi-agent workflow** (`references/docx_multiagent_workflow.md`): when multiple agents
process a single docx, use **parallel analysis + serial editing (map–reduce)**. ① MAP: diagnosis,
verification, and proposed replacements run in parallel (no file edits) ② REDUCE: one fixer edits
serially ③ VERIFY: one QC pass via Word COM. Concurrent editing is forbidden.

**★ Full-pass QC checklist** (`references/manuscript_qc_checklist.md`): 30 items to run before
declaring a "final version." When docx structural editing is delegated, **Word COM verification
before acceptance is mandatory**.

## Integrated procedure (agents must follow)

0. **Diagnostic report first** (`QC_REPORT.md`) — full scan of body, table cells, and captions;
   record violation classification and location
1. Create the `corrections/` folder, copy `step0_original.docx`
2. Apply each rule stage → `step1`–`step5`. When applying R1/R2/R5/R6/R10, traverse table-cell
   and caption paragraphs too
3. Before generating `step6_final.docx`, **check for duplicate comment IDs**: find the existing
   max comment ID → assign starting from `max_id + 1`
4. Full ZIP-integrity verification of `step6_final.docx` + **Word COM**
5. On PASS: back up the original to `_archive/{original_name}_pre_correction.docx`, then replace
6. On FAIL: report the problem only, do not replace

## Traversal target pattern (full pass over body + table cells + captions)

Looking only at top-level `<w:body>` `<w:p>` misses table cells and captions. The text rules
(R1/R2/R5/R6/R10) and font verification (R11) traverse **all three** kinds of paragraph below.

```python
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

def iter_target_paragraphs(root):
    """Yield every w:p in the body + table cells (iter() recurses into w:p inside table cells too)."""
    body = root.find(f'{{{W}}}body')
    for p in body.iter(f'{{{W}}}p'):
        yield p

def is_in_table(p):
    anc = p.getparent()
    while anc is not None:
        if anc.tag == f'{{{W}}}tc':
            return True
        anc = anc.getparent()
    return False

def is_caption(p):
    """Caption heuristic: starts with Figure/Table/Fig./Scheme (SI captions get an S prefix)."""
    txt = ''.join(t.text or '' for t in p.iter(f'{{{W}}}t')).strip()
    return bool(re.match(r'^(Figure|Table|Fig\.|Scheme)\s*S?\d', txt))

def cell_iter(root):
    """Table-unit traversal: (tbl_idx, row_idx, col_idx, tc_element)."""
    body = root.find(f'{{{W}}}body')
    for ti, tbl in enumerate(body.iter(f'{{{W}}}tbl')):
        for ri, tr in enumerate(tbl.findall(f'{{{W}}}tr')):
            for ci, tc in enumerate(tr.findall(f'{{{W}}}tc')):
                yield ti, ri, ci, tc
```

**Font size (R11)**: the body mode sz is the most common run `w:sz/@w:val` among paragraphs
where `is_in_table=False and not is_caption`. Table-cell sz and caption sz are tallied
separately, and only runs that deviate from the mode are reported. A run without `w:sz` is
resolved against the default sz in styles.xml.

**Three-line table (R7)**: for each `<w:tbl>`, if `w:left`/`w:right`/`w:insideV` under
`w:tblPr/w:tblBorders` or `w:tc/w:tcPr/w:tcBorders` has `w:val != "nil"/"none"`, that is a
vertical-rule violation. (Border thickness/order is defined in academic-term-rules §13.)

## Note: DOCX editing must follow the docx skill protocol (not in this repository — see docs/12)
`python-docx` `Document().save()` is forbidden. Preserve the original ZIP structure (use an
`incremental_edit.py` session). Details → the docx skill (not in this repository — see docs/12).
