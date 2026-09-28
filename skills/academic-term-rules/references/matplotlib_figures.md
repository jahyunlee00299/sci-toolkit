# matplotlib Figure Text Implementation Rules

## 20. matplotlib Figure Text Implementation Rules [Auto-detectable]

### Enzyme/gene names — a single mathtext SSOT helper (one mathtext block, no split blocks)

```python
# CORRECT — single block, suffix in plain roman
theme.enz_label('EcAdh')    # -> '$\it{Ec}\mathrm{Adh}$'
theme.enz_label('BsLdhV2')  # -> '$\it{Bs}\mathrm{LdhV2}$'

# Compound label
ADH_LDH = theme.enz_label('EcAdh') + ':' + theme.enz_label('BsLdhV2')

# WRONG — bold suffix
r'$\it{Ec}\mathbf{Adh}$'   # bold suffix is forbidden
# WRONG — split blocks
r'$\it{Ec}$$\mathrm{Adh}$'  # the second block's prefix renders as roman, breaking the italic
```

### Plasmid names — §9 italic, suffix plain

```python
# CORRECT
ax.text(x, y, r'$\it{pETDuet}$-$\it{1}$ (Amp$^r$)', fontweight='normal')

# WRONG — fontweight='bold' also bolds the suffix
ax.text(x, y, r'$\it{pETDuet}$-1', fontweight='bold')
```

### Font-style summary

| Element | italic | bold | Implementation |
|---|---|---|---|
| Enzyme origin prefix (*Ro*, *Ps*) | yes | no | `$\it{Xx}` (inside a single block) |
| Rest of the enzyme name (Gdh, Xyl1) | no | no | `\mathrm{...}$` (plain roman) |
| Plasmid name (*pETDuet-1*) | yes | no | `$\it{...}$` segment |
| Plasmid suffix (Amp^r) | no | no | plain, `fontweight='normal'` |
| Strain name (JW-D1) | no | yes | `fontweight='bold'` |

### Legend — a single `smart_legend()`-style SSOT helper

Use one legend helper (`theme.smart_legend(ax)`) called after `tight_layout()` and right before
`savefig()`. Never hardcode `loc`.

```python
# CORRECT
fig.tight_layout()
theme.smart_legend(ax)   # auto-selects a corner (upper-right -> lower-right -> lower-left ->
                          # upper-left, verified against the actual bbox)
fig.savefig(...)

# WRONG
ax.legend(loc='upper left')   # hardcoded loc — can overlap the data
theme.smart_legend(ax)        # called before tight_layout() — overlap is misjudged
fig.tight_layout()
```

For `fig.legend` (a shared legend, e.g. for a donut/pie-chart panel), the smart-legend helper does
not apply — adjust `bbox_to_anchor` + `rect` manually instead.
