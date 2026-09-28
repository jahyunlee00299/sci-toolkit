# Displayed Equations — OMML Required

## 18. Displayed Equations — OMML Required [Auto-detectable]

**Rule: all displayed equations in a scientific manuscript document must be inserted as OMML
(`<m:oMath>`), never as plain text.**

Plain-text equations (e.g., `v1 = (Vmax,1 · [S1] · [S2]) / (...)`) violate §5/§11 because:
- subscripts (Vmax, Km, kd) are missing → non-standard notation
- superscripts (NAD⁺, HCOO⁻) are missing
- italic variables (v, K, k, V) are not applied

### When OMML is required

| Equation type | OMML required | Example |
|---|---|---|
| Rate laws (Michaelis-Menten, Bi-Bi) | Yes | v1 = Vmax·[A]·[B] / denom |
| ODE mass balances | Yes | d[NAD⁺]/dt = −v1 + v2 |
| Inline simple expressions | No | n = 3, pH 7.0 |
| Equation labels only | No | (Eq. S7) appended after the OMML block |

### OMML notation rules for kinetics (§5 + §11)

| Symbol | OMML pattern | Rule |
|---|---|---|
| *v* (rate) | `<m:r><m:rPr><m:sty m:val="i"/></m:rPr><m:t>v</m:t></m:r>` | italic |
| *V*max | italic V + `<m:sSub>` subscript "max" | §5 |
| *K*m, *K*iA, *K*mB | italic K + subscript | §5 |
| *k*d, *k*deg | italic k + subscript | §11 |
| *k*cat | italic k + subscript "cat" | §11 |
| *k*La | italic k + subscript "La" (oxygen mass transfer coefficient) | §11 |
| NAD⁺ | NAD + `<m:sSup>` superscript "+" | §11 |
| HCOO⁻ | HCOO + `<m:sSup>` superscript "−" | §11 |
| [species] | `<m:d>` with `begChr="["` `endChr="]"` | §11 |
| σ*i* | sigma (roman) + italic subscript "i" | §5 |
| ρE,*i* | rho E (roman) + italic subscript "i" | §5 |
| α, β | Greek letter (roman unless a variable; italic if a kinetic parameter) | §5 |
| *N* | italic N (e.g. shaking speed, rpm) | §5 |
| fractions | `<m:f><m:num>…</m:num><m:den>…</m:den></m:f>` | — |

### How to insert

See the `docx` skill's `SKILL.md` for OMML equation insertion — full XML templates and the
incremental-edit workflow for adding a `<m:oMath>` block into an existing docx.

### Detection

A plain-text equation paragraph is any `<w:t>` containing `=` with kinetics symbols (`Vmax`, `Km`,
`kd`, `kcat`, `kLa`, `d[`, `/dt`, `sigma`, `rhoE`) that sits outside `<m:oMath>` — flag it as a
violation.
