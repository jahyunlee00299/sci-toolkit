# Manuscript DOCX QC Checklist

Before calling a manuscript/SI docx "final," run through this entire list **every time**.
Tooling: python (not `python3`) + zipfile to inspect `word/document.xml` directly. Guard UTF-8 stdout.
No substitution of any kind is allowed inside an EndNote field (`<w:instrText>`, `<w:fldChar begin>..<end>`).

## A. Structural integrity (4-stage preflight — mandatory)
1. **ZIP CRC**: `zipfile.ZipFile(p).testzip()` is None.
2. **XML well-formed**: every `.xml`/`.rels` passes `ET.fromstring`.
3. **Comment integrity**: zero dangling `commentReference` (id <-> comments.xml definitions match 1:1).
4. **Word COM ground-truth**: open via `New-Object -ComObject Word.Application` and confirm it OPENS without "corrupted," with pages/tables/fields/comments counts intact. **A file can be XML well-formed and still get rejected by Word** (OOXML schema violation — common after an agent edits a docx). Confirm pages/tables/fields are preserved.

## B. Table layout / footnotes
5. **Caption -> table -> footnote order**: every table's caption is immediately followed by the table, and the table immediately followed by its footnote. Hunt down any caption/footnote that landed in the wrong place (past case: Main Table 3 broke into caption -> footnote -> ... -> table).
6. **Footnote marker <-> definition 1:1**: superscript markers in cells ([a], a, etc.) match footnote definitions with no dangling/orphan entries.
7. **Two-table sync**: the same item appears in both the Main table and the SI table, with matching values/entries (Main Table 3 <-> SI Table S6).

## C. Numeric provenance (single source of truth)
8. **Trace back to raw-data Excel**: the same number appearing in body text/table/figure traces to a single raw-data file (`<rawdata>.xlsx`, This-work = Efactor_FINAL sheet, literature = Lit_Efactor_FINAL sheet).
9. **Verify literature comparison values against the original**: sEF/cEF and similar values from someone else's paper get recalculated from that paper's original reported conditions. **No assumed values** (assumed DCW, abstract-only yield, etc.) — even without a stated volume, a per-L mass calculation is possible from a concentration (g/L); mark only genuinely non-derivable items as n.c./n.a.
10. **Check unit conversions**: mM <-> g/L (via MW), yield = product / measured-total-input.

## D. References/citations
11. **Zero unformatted tags**: no leftover `{Author, Year #N}` after a Word "Update Citations." If any remain, tell the user to run Word's "Update Citations."
12. **Author-year -> [N]**: no in-text "(Akagi 2002)"-style citations — must be EndNote [N]. (Author-year labels inside table cells are the exception and are allowed.)
13. **No empty RecNum**: `{Author, Year #}` (blank RecNum) breaks on Update — look it up in the EndNote DB (`...My EndNote Library_2025.Data\sdb\sdb.eni`, refs table, trash_state=0) and fill it in.
14. **Citation numbering continuity**: check for gaps across [1..max] (a legitimate gap is fine — just report it).
15. **Citation clusters <=3**; no clusters in paragraphs that reference a Table N.

## E. refs_pdfs file integrity
16. **Filename <-> content match**: page-1 title/authors/year of each PDF matches its filename and citation (frequent past cases: filename mismatched the actual content, or an HTML page got saved as a PDF by mistake). For a suspect PDF, check whether `head -c 5` reads `%PDF-`.

## F. Italics (exhaustive pass)
17. **Species names**: genus/binomial (Acetobacter aceti, E. coli, etc.) italic, `sp.` roman. Scan long runs in windows to rule out false positives from partial italics.
18. ***ee*** (enantiomeric excess): italicize the physical-quantity symbol.
19. ***E*-factor**: only the E in "E-factor"/"E factor" is italic; sEF/cEF stay roman.
20. **Enzyme prefixes**: only the species prefix is italic, e.g. *Xx*GDH.

## G. Spelling/notation consistency
21. **Unify spelling**: apply American or British spelling consistently per the target journal's convention (e.g. American = titer/optimize/modeling/isomerization...). Substitute field-aware (protect field codes, titles, DOIs).
22. **Abbreviation consistency**: use the standard abbreviation consistently after its first definition. Exceptions: full enzyme names, sentence-initial words, titles, captions.
23. **Numeric-range dashes**: en-dash (-, U+2013), never hyphen (-). (Citation ranges [N-M], DOIs, and page numbers are EndNote's domain — leave those alone.)
24. **Unit slash format**: g/L, U/mL (no superscript -1 form).
25. **Arrows**: no `X -> Y` in body text — use "-to-" or natural language instead.

## H. Basic formatting
26. **Font**: every body/table-cell/caption run's rFonts = Arial (flag anything non-Arial).
27. **Font size**: body sz=24 (12pt) / table cell sz~=17 / caption consistent (flag any table-to-table drift).
28. **Line spacing**: table cells line=240 lineRule=auto; body text follows the journal's specified value.
29. **Table borders**: three-line style (outer sz12, divider sz4) — flag any leftover sz6/8, or left/right/internal vertical lines.
30. **Alignment (w:jc)**: consistent caption/cell alignment.

## Working principles
- No changing numbers/data without user approval; once the user gives an answer, accept it immediately.
- Delegating docx structural edits to an agent carries real corruption risk -> **always verify via Word COM** before adopting the result (agent-edited files getting rejected by Word as "corrupted" is a recurring failure mode).
- Record decisions in the single source-of-truth location (e.g. the `Decision_Log/` folder).
