# Phase 8 — Integrity verification code

Full code for the three integrity checks run after Phase 7, before showing the user.

```python
# 1. python-docx open test
doc = Document(out_path)
assert len(doc.paragraphs) == orig_paras
assert len(doc.tables) == orig_tables
assert len(doc.inline_shapes) == orig_shapes
assert len(doc.sections) == orig_sections

# 2. namespace count check
import re
o_xml = zipfile.ZipFile(orig).read('word/document.xml').decode()
f_xml = zipfile.ZipFile(out_path).read('word/document.xml').decode()
o_ns = re.search(r'<w:document\s+([^>]+)>', o_xml).group(1).count('xmlns')
f_ns = re.search(r'<w:document\s+([^>]+)>', f_xml).group(1).count('xmlns')
assert o_ns == f_ns, f'xmlns count changed: {o_ns} → {f_ns}'

# 3. ns artifact check (ElementTree leak)
ns_artifact = len(re.findall(r'\bns\d+:', f_xml))
assert ns_artifact == 0, f'ElementTree namespace artifacts: {ns_artifact}'
```

If any check fails — abort, restore from backup, debug. Common cause: switched to
`xml.etree.ElementTree` by accident (see Phase 7's rule against this).
