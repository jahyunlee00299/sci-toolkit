# Primer Design Suite -- Detailed Reference

## New Environment Installation

```bash
git clone https://github.com/<your-github-username>/claude-scientific-skills <skill-root>
cp -r <skill-root>/scientific-skills/primer-design <install-dir>/primer-design
pip install -r <install-dir>/primer-design/requirements.txt
# Register MCP in your Claude settings.json (refer to SKILL.md)
```

> Vector `.dna` files are resolved relative to the package (no manual path setup needed) for each computer.

---

## MCP Tool Details

### Tool 1: `design_re_cloning_primers`

Designs RE cloning primers for inserting a gene into an expression vector. Internally performs reading frame validation, expression viability check, and SnapGene file generation.

**Parameters**

| Parameter | Type | Default | Description |
|---------|------|--------|------|
| `insert_seq` | str | required | Insert CDS sequence (ATG ~ stop) |
| `re_5prime` | str | required | 5' restriction enzyme name (e.g., `"BamHI"`, `"NdeI"`, `"NheI"`) |
| `re_3prime` | str | required | 3' restriction enzyme name (e.g., `"XhoI"`, `"NotI"`, `"HindIII"`) |
| `vector_name` | str or None | None | Vector name -- auto-validates reading frame when specified (e.g., `"pET-28a(+)"`) |
| `include_start_codon` | bool | True | Whether to include ATG in F primer (NdeI/NcoI already contain ATG in RE site) |
| `include_stop_codon` | bool | False | Whether to add stop codon to R primer (True -> blocks C-terminal tag) |
| `target_tm` | float | 62.0 | Target Tm for annealing region (degrees C) |
| `gene_name` | str | `"Insert"` | Label for report and SnapGene feature |
| `output_dir` | str or None | None | Directory to save PNG report + .dna file |

**Primer Structure**

```
F: 5'-[protection(4-6 bp)]-[RE5 site]-[annealing(~20 bp)]---3'
R: 5'-[protection(4-6 bp)]-[RE3 site]-[RC(stop)?]-[RC annealing(~20 bp)]---3'

Tm calculation: annealing region only (RE tail does not bind template, so does not contribute to Tm)
Protection bases: 6-cutter -> 4 bp, 8-cutter (NotI, etc.) -> 6 bp (GCGC... pattern, NEB guidelines)
```

**Auto-warning Items**

- If RE site exists within insert: `"CRITICAL: RE cuts within insert"`
- NdeI/NcoI used with `include_start_codon=True`: `"RE site itself provides start codon"`
- Compatible overhang pairs (BamHI+BglII, EcoRI+MfeI, SalI+XhoI, etc.): bidirectional insertion warning
- Blunt-end enzyme (EcoRV): no directionality warning
- Primer length > 60 nt, homopolymer, no 3' GC clamp

**Key Return Fields**

| Key | Description |
|----|------|
| `f_full`, `r_full` | Final primer sequences (tail + annealing) |
| `f_tail`, `r_tail` | protection + RE site + spacer |
| `f_ann`, `r_ann` | Annealing region only |
| `f_tm`, `r_tm` | Annealing region Tm (degrees C) |
| `anneal_temp` | Recommended PCR annealing temperature = min(Tm) + 1 (degrees C) |
| `f_qc`, `r_qc` | Hairpin/homodimer QC (PASS/WARNING/FAIL) |
| `frame_check` | Reading frame validation result (when vector_name specified) |
| `expression_check` | Expression viability analysis result -- `verdict`: PASS/WARNING/FAIL |
| `report_image_path` | PNG report path (when output_dir specified) |
| `snapgene_path` | SnapGene .dna file path (when output_dir specified) |
| `internal_re_sites_5/3` | List of RE site positions within insert |
| `warnings` | List of warning messages |

**`expression_check` Details**

Comprehensive expression viability assessment analyzing 6 items:

1. **Vector expression context**: promoter, inducer, RBS, expression type (e.g., T7/lac, IPTG, cytoplasmic high-level)
2. **Fusion protein topology**: N/C-terminal tag information, tag-insert junction sequence (linker AA)
3. **Full expressed protein sequence**: MW calculation, fusion protein length including N/C linker
4. **RE site within insert**: whether the restriction enzyme used cuts within the insert (`CRITICAL` verdict)
5. **Premature stop codon**: position of premature stop codons within ORF
6. **CDS quality**: CAI, rare codon frequency, strain recommendation, signal peptide

```
verdict = FAIL    -> Critical issue (internal RE site, premature stop, frameshift, length error)
verdict = WARNING -> Minor issue (low CAI, QC WARNING)
verdict = PASS    -> No issues
```

**Usage Example**

```python
result = design_re_cloning_primers(
    insert_seq="ATGCGTAACCTGGCG...TAA",
    re_5prime="NdeI",
    re_3prime="XhoI",
    vector_name="pET-28a(+)",
    include_start_codon=True,
    include_stop_codon=False,   # maintain C-His6 tag
    gene_name="MyEnzyme",
    output_dir="~/results/primers",
)
print(result["f_full"])           # final F primer
print(result["expression_check"]["verdict"])   # PASS/WARNING/FAIL
print(result["frame_check"]["frame_report"])   # reading frame summary
```

---

### Tool 2: `recommend_re_pair`

Given insert and vector, recommends optimal RE combinations ranked by score. Tests all RE pairs in the vector MCS and scores them by the following criteria.

**Scoring System**

| Criterion | Score |
|------|------|
| Double digest possible (same buffer or CutSmart >= 75%) | +3 |
| Both have CutSmart 100% | +2 |
| Insert-vector reading frame compatible | +2 |
| HF variant exists | +1 |
| If RE site exists within insert, that pair is excluded | -- |

**Return value**: List ranked by score descending; each item includes `re_5prime`, `re_3prime`, `buffer`, `double_digest_ok`, `frame_ok`, `score`, `reason`

```python
recs = recommend_re_pair(
    insert_seq="ATGCGT...",
    vector_name="pET-28a(+)",
    prefer_hf=True,
)
```

---

### Tool 3: `suggest_colony_pcr`

| Parameter | Description |
|---------|------|
| `vector_name` | Vector name (fuzzy matching supported) |
| `insert_length_bp` | Insert length (bp) |

Returns: F/R primer name and sequence, Tm, expected band size, recommended annealing temperature

---

### Tool 4: `analyze_expression`

| Item | Description |
|------|------|
| `basic_info` | Protein length (aa), MW (kDa), GC% |
| `cai` | Codon Adaptation Index (0-1, E. coli K-12 based) |
| `rare_codons` | Rare codon frequency (%), cluster positions |
| `signal_peptide` | Signal peptide prediction |
| `map_removal` | N-terminal Met removal prediction |
| `strain_recommendation` | Recommended expression strain |

---

### Tool 5: `check_reading_frame_tool`

| Parameter | Default | Description |
|---------|--------|------|
| `vector_name` | required | Vector name |
| `re_5prime` | required | 5' restriction enzyme |
| `re_3prime` | required | 3' restriction enzyme |
| `insert_has_atg` | True | Whether insert contains its own ATG |
| `insert_has_stop` | False | Whether insert contains its own stop codon |
| `insert_cds_bp` | None | Insert length (optional) |

Returns: `in_frame_5prime/3prime`, `topology`, `linker_aa`, `frame_report`, `warnings`

---

### Tool 6: `list_vectors`

| Vector | Tag | Features |
|------|------|------|
| `pET-21a(+)` | C-His6 | T7/lac, IPTG |
| `pET-28a(+)` | N-His6+T7tag, C-His6 | T7/lac, IPTG |
| `pMAL-c6T` | N-MBP-TEV | Ptac, amylose purification |
| `pETDuet-1:MCS1` | N-His6 | T7/lac, co-expression |
| `pETDuet-1:MCS2` | S-tag (optional) | co-expression with MCS1 |
| `pACYCDuet-1:MCS1` | N-His6 | CmR, ColA ori, pET compatible |
| `pACYCDuet-1:MCS2` | S-tag (optional) | CmR, co-expression |

### Tool 7: `list_restriction_enzymes`

Supported: BamHI(-HF), XhoI, NdeI, NheI(-HF), NotI(-HF), NcoI(-HF), EcoRI(-HF), HindIII(-HF), SalI(-HF), KpnI(-HF), BglII, EcoRV(-HF), MfeI(-HF), SacI(-HF), AvrII, FseI, AscI, PacI, etc.

### Tool 8: `generate_macrogen_order`

| Parameter | Default | Description |
|---------|--------|------|
| `primers` | required | `[{"name": "...", "sequence": "..."}, ...]` |
| `project_name` | `"primer_order"` | Filename prefix |
| `output_dir` | None | Save directory |

Returns: `file_path`, `total_primers`, `total_length_nt`, `estimated_cost_krw`

### Macrogen Sequencing Order Sheet (`to_macrogen_seq`)

| Parameter | Default | Description |
|---------|--------|------|
| `sample_primer_pairs` | required | `[{"sample_name": "...", "primer_name": "...", ...}]` |
| `output_path` | None | Save path |

Fields per item:

| Field | Required | Description |
|------|------|------|
| `sample_name` | Y | Sample name (English, only `-`, `_`) |
| `primer_name` | Y | Primer name |
| `sample_conc` | N | **Leave blank** -- experimenter fills in actual value after miniprep |
| `primer_seq` | N | Primer sequence (5'->3') |
| `primer_conc` | N | pmol/ul (omit for universal primer) |
| `product_size` | N | Template size (bp) |

> **Note**: Do not put arbitrary default values (e.g., 100) in `sample_conc`. Leave blank so experimenter can fill in the actual measured concentration.

---

## Direct Python Usage -- Mutagenesis

### Substitution -- `iPCRSubstDesigner`

```python
from src.primer_design import iPCRSubstDesigner

designer = iPCRSubstDesigner()
result = designer.design(
    seq=template_seq,
    subst_pos=100,
    old_seq="ACG",
    new_seq="GAT",
    target_tm=61.0,
    overlap_len=18,
    min_len=18,
    max_len=35,
)
```

**Design Principles**

```
overlap = up_tail(k1 bp) + new_seq + dn_tail(k2 bp)
F: 5'-[up_tail]-[new_seq]-[dn_tail]-[annealing_downstream]-3'
R: 5'-RC(dn_tail)-RC(new_seq)-RC(up_tail)-[annealing_upstream]-3'
Tm: full effective binding of tail + annealing
k1 = (overlap_len - len(new_seq)) // 2
k2 = overlap_len - len(new_seq) - k1
```

Hairpin avoidance: 2-pass logic (Pass 1 failure -> rank all candidates PASS>WARNING>FAIL)

### Deletion -- `iPCRDelDesigner`

```python
from src.primer_design import iPCRDelDesigner

designer = iPCRDelDesigner()
result = designer.design(
    seq=template_seq,
    del_start=30,
    del_end=33,
    target_tm=61.0,
    overlap_len=18,
    min_len=18,
    max_len=35,
    cds_start=0,
)
```

Frameshift: `del_len % 3 == 0` -> in-frame, otherwise `frameshift_warning: True`

### Load SnapGene File

```python
from src.primer_design import parse_snapgene
seq, is_circular, features = parse_snapgene(r"path\to\vector.dna")
```

---

## Notes

### SDM Codon Selection

```
Homopolymer >= 4 bp? -> YES: change synonymous codon (expression impact <5%) / NO: E. coli preferred codon
```

| AA | Preferred | Alternative | If homopolymer |
|----|------|------|---------------|
| Lys | AAA (76%) | AAG | AAA->AAG |
| Glu | GAA (68%) | GAG | GAA->GAG |
| Ile | ATT (51%) | ATC | ATT->ATC |

### Post-PCR: KLD Reaction (NEB #M0554)

```
1 uL PCR + 1 uL KLD Enzyme Mix + 5 uL KLD Buffer + 3 uL water -> 25 degrees C 5 min -> Transform
```

### Troubleshooting

| Problem | Solution |
|------|------|
| `ValueError: Mismatch` | Re-check position in SnapGene |
| Tm too low | Increase `max_len` or lower `target_tm` |
| `overlap_verified: False` | Manually check `k1/k2` |
| Persistent QC FAIL | Adjust `overlap_len` |
| `primer3 not available` | `pip install primer3-py` |
| `expression_check FAIL` | Re-check insert sequence, remove site with SDM |

---

## Script Structure

```
src/primer_design/
+-- subst_primer_mode.py         # iPCRDesignerBase + iPCRSubstDesigner
+-- del_primer_mode.py           # iPCRDelDesigner
+-- restriction_cloning_mode.py  # RestrictionCloningDesigner
+-- colony_pcr_mode.py           # ColonyPCRDesigner
+-- expression_analyzer.py       # ExpressionAnalyzer
+-- order_sheet.py               # Macrogen XLSX
+-- snapgene_parser.py           # .dna parser
+-- snapgene_writer.py           # .dna generator
+-- vector_registry.py           # Vector/RE DB
+-- vector_dna_config.py         # .dna path mapping
+-- cloning_report.py            # PNG report
+-- mcp_server.py                # FastMCP server (8 tools)
+-- clients/                     # project-specific mutagenesis clients (user-supplied, not bundled)
```
