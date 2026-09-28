# WORKORDER Write-Time Enforcement

## 18b. WORKORDER Write-Time Enforcement

When drafting `new:` values in any WORKORDER-style manuscript insertion/replacement item, apply
academic-term-rules **at write time** — do not defer to a later QC phase.

**Mandatory self-check before finalizing each `new:` field:**

| Check | Pattern to grep | Fix |
|---|---|---|
| Em-dash list | `—` in body text | Replace with a complete sentence or a semicolon-free rephrasing |
| Semicolon splice | `;` joining two independent clauses | Split into two sentences |
| Colon splice | `:` joining an independent clause to another clause | Split or restructure |
| Origin prefix italic | `EcAdh`, `BsLdh`, `SoXyl1` written without italic markup | Apply italic to the species-prefix only: *Ec*Adh, *Bs*Ldh |
| Cofactor superscript | `NAD+`, `NADP+` without superscript | NAD⁺, NADP⁺ |

**Why at write-time (not QC-time):** QC scripts catch formatting problems in rendered XML, but
WORKORDER `new:` text is plain text that bypasses XML inspection until after it is applied. Errors
introduced in `new:` fields propagate directly into the document and may survive QC if the QC pass
is not re-run afterward.

**Applies to:** all manuscript WORKORDER `new:` fields — captions, body text, headings, table cells,
footnotes.
