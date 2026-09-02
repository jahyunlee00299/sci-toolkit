# American Spelling

## 15. American Spelling [Auto-detectable]

Use American spelling throughout (per user policy). Apply to body, tables, captions.

| British | American |
|---|---|
| titre | titer |
| optimise / optimisation | optimize / optimization |
| characterise / characterisation | characterize / characterization |
| analyse | analyze |
| catalyse / catalysed | catalyze / catalyzed |
| colour | color |
| fibre | fiber |
| litre | liter (but unit symbol stays **L**, mL) |
| labelled / labelling | labeled / labeling |
| modelling | modeling |
| neighbour | neighbor |
| centre | center |
| sulphur / sulphate | sulfur / sulfate |

```python
SPELLING_PATTERNS = [
    (r'\btitre\b', 'titer'), (r'\boptimis', 'optimiz'), (r'\bcharacteris', 'characteriz'),
    (r'\banalyse\b', 'analyze'), (r'\bcatalys', 'catalyz'), (r'\bcolour\b', 'color'),
    (r'\bfibre\b', 'fiber'), (r'\blabell', 'labell→label'), (r'\bmodelling\b', 'modeling'),
    (r'\bsulph', 'sulf'), (r'\bcentre\b', 'center'),
]
# CAUTION: do not rewrite proper nouns / journal names / cited titles (preserve as published).
```

