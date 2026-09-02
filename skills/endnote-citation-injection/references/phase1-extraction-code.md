# Phase 1 — Two-docx analysis extraction code

Worked extraction code for pulling ref entries out of the refs docx and citations out of the
body docx.

```python
from docx import Document
import re

doc_refs = Document("v2_refs.docx")
doc_body = Document("v2.docx")

# Extract refs from refs.docx (typically last 30+ paragraphs)
refs = []
for i, p in enumerate(doc_refs.paragraphs):
    t = p.text
    if re.search(r'\bdoi\s*[:.]?\s*10\.', t, re.IGNORECASE):
        refs.append({'idx': i, 'text': t})

# Extract parenthetical/narrative citations from body
pat_paren = re.compile(r'\([A-Z][A-Za-zçéèáñ\-]+(?:\s+et\s+al\.)?(?:,?\s*&\s*[A-Z][A-Za-z\-]+)?,?\s*\d{4}[a-z]?\)')
pat_narrative = re.compile(r'[A-Z][A-Za-z\-]+(?:\s+et\s+al\.|\s+and\s+[A-Z][A-Za-z\-]+)?\s+\(\d{4}\)')
```
