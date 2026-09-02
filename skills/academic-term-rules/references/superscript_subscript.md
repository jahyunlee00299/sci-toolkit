# Superscript / Subscript Rules

## 11. Superscript / Subscript Rules [Auto-detectable]

In .docx XML, check `<w:vertAlign w:val="superscript"/>` or `<w:vertAlign w:val="subscript"/>`.

### Must be superscript

| Text | Superscript part | Example |
|---|---|---|
| NAD⁺ | + | `NAD<sup>+</sup>` |
| NADP⁺ | + | `NADP<sup>+</sup>` |
| Mg²⁺, Ca²⁺, Fe³⁺, Zn²⁺ | charge number + sign | `Mg<sup>2+</sup>` |
| kcat | — (but see §5 for italic) | |

### Must be subscript

| Text | Subscript part | Example |
|---|---|---|
| CO₂ | 2 | `CO<sub>2</sub>` |
| H₂O | 2 | `H<sub>2</sub>O` |
| H₂O₂ | both 2s | `H<sub>2</sub>O<sub>2</sub>` |
| O₂ | 2 | `O<sub>2</sub>` |
| NH₄⁺ | 4 (sub) + (sup) | `NH<sub>4</sub><sup>+</sup>` |
| FADH₂ | 2 | `FADH<sub>2</sub>` |
| Km | m | `K<sub>m</sub>` (italic K) |
| Vmax | max | `V<sub>max</sub>` (italic V) |
| kcat | cat | `k<sub>cat</sub>` (italic k) |
| Tm (melting) | m | `T<sub>m</sub>` (italic T) |

### Common errors

| Error | Correct |
|---|---|
| NAD+ (plain) | NAD⁺ or NAD`<sup>+</sup>` |
| CO2 (plain) | CO₂ or CO`<sub>2</sub>` |
| H2O (plain) | H₂O |
| Km (plain, no sub) | K`<sub>m</sub>` |
| 10^5 or 10^-3 | 10⁵ or 10⁻³ (superscript exponent) |

### XML detection pattern

```xml
<!-- Correct superscript in docx XML -->
<w:r>
  <w:rPr><w:vertAlign w:val="superscript"/></w:rPr>
  <w:t>+</w:t>
</w:r>

<!-- Correct subscript -->
<w:r>
  <w:rPr><w:vertAlign w:val="subscript"/></w:rPr>
  <w:t>2</w:t>
</w:r>
```

