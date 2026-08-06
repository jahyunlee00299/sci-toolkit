---
name: primer-design
description: Integrated skill for iPCR mutagenesis (substitution/deletion), RE cloning, Colony PCR, E. coli expression analysis, and Macrogen order sheet generation.
license: MIT
---

# Primer Design Suite

Base directory for this skill: `<skill-root>/primer-design` (wherever you installed it)

Integrated skill for iPCR mutagenesis (substitution/deletion), RE cloning, Colony PCR, E. coli expression analysis, and Macrogen order sheet generation.

**Source code**: `./src/primer_design/`
**Detailed documentation**: `./REFERENCE.md` <- For parameters, return values, examples, and detailed content, refer to this file

## MCP Server

```json
{
  "mcpServers": {
    "primer-design": {
      "command": "python",
      "args": ["-m", "src.primer_design.mcp_server"],
      "cwd": "<path-to-skill-root>/primer-design"
    }
  }
}
```

## Features & Tool Mapping

| Feature | MCP Tool / Class | Purpose |
|------|-------------------|------|
| Amino acid substitution (SDM) | `iPCRSubstDesigner` | back-to-back iPCR mutagenesis |
| Codon deletion | `iPCRDelDesigner` | in-frame/frameshift deletion |
| RE cloning primers | `design_re_cloning_primers` | Primers for expression vector insertion + frame/expression validation |
| RE pair recommendation | `recommend_re_pair` | Auto-search for optimal RE combination |
| Colony PCR | `suggest_colony_pcr` | Universal primers + band size prediction |
| Expression analysis | `analyze_expression` | CAI, rare codons, strain recommendation |
| Reading frame validation | `check_reading_frame_tool` | Frame compatibility check before cloning |
| Vector/RE list | `list_vectors`, `list_restriction_enzymes` | Query supported vectors and enzymes |
| Macrogen order sheet | `generate_macrogen_order` | Auto-generate XLSX |

## Method Selection

| Situation | Recommended |
|------|------|
| Amino acid substitution (1 to tens of nt) | `iPCRSubstDesigner` |
| Codon deletion | `iPCRDelDesigner` |
| Gene -> expression vector insertion | `design_re_cloning_primers` |
| Unknown RE combination | Run `recommend_re_pair` first |
| Post-cloning verification | `suggest_colony_pcr` |
| Insertion > 100 nt | Consider Gibson Assembly |

## Validation Checklist (Required)

- Overlap complementarity: `overlap_verified: True`
- Confirm reading frame preservation
- RE cloning: `expression_check.verdict != "FAIL"`
- QC: PASS or WARNING allowed; if FAIL, redesign

## Detailed Usage

For **parameters, return values, code examples, design principles, troubleshooting**, refer to `REFERENCE.md`:
```
Read <skill-root>/primer-design/REFERENCE.md
```
